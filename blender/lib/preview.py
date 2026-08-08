"""Turntable-style preview renders.

The agent cannot open Blender, so these PNGs are how it inspects an asset.
Cycles on CPU is used deliberately: EEVEE needs a GPU context that is not
reliably available in `--background`, and a preview that silently fails to
render is worse than one that takes a few seconds.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import bpy
from mathutils import Vector

from blender.lib.scene import world_bounds

SENSOR_WIDTH_MM = 36.0
LENS_MM = 55.0
FRAMING_MARGIN = 1.10


@dataclass(frozen=True)
class ViewAngle:
    name: str
    direction: tuple[float, float, float]


VIEW_ANGLES: tuple[ViewAngle, ...] = (
    ViewAngle("hero", (1.0, -1.25, 0.75)),
    ViewAngle("front", (0.0, -1.0, 0.12)),
    ViewAngle("side", (1.0, 0.0, 0.12)),
)


def _configure_render(scene: bpy.types.Scene, resolution: int, samples: int) -> None:
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = samples
    scene.cycles.use_adaptive_sampling = True
    scene.cycles.adaptive_threshold = 0.02
    scene.cycles.use_denoising = True
    scene.cycles.denoiser = "OPENIMAGEDENOISE"
    scene.render.resolution_x = resolution
    scene.render.resolution_y = resolution
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = False
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    # Standard rather than AgX: previews are for judging albedo and form, not for looking cinematic.
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.look = "None"


def _build_world(scene: bpy.types.Scene) -> None:
    world = bpy.data.worlds.new("PreviewWorld")
    world.use_nodes = True
    background = world.node_tree.nodes["Background"]
    background.inputs["Color"].default_value = (0.05, 0.055, 0.06, 1.0)
    background.inputs["Strength"].default_value = 1.0
    scene.world = world


def _build_backdrop(center: Vector, base_z: float, radius: float) -> bpy.types.Object:
    mesh = bpy.data.meshes.new("Backdrop")
    size = radius * 12.0
    half = size * 0.5
    z = base_z - radius * 0.002
    vertices = [
        (center.x - half, center.y - half, z),
        (center.x + half, center.y - half, z),
        (center.x + half, center.y + half, z),
        (center.x - half, center.y + half, z),
    ]
    mesh.from_pydata(vertices, [], [(0, 1, 2, 3)])
    mesh.update()

    material = bpy.data.materials.new("BackdropMaterial")
    material.use_nodes = True
    principled = next(node for node in material.node_tree.nodes if node.type == "BSDF_PRINCIPLED")
    principled.inputs["Base Color"].default_value = (0.28, 0.28, 0.30, 1.0)
    principled.inputs["Roughness"].default_value = 0.9
    mesh.materials.append(material)

    obj = bpy.data.objects.new("Backdrop", mesh)
    bpy.data.scenes[0].collection.objects.link(obj)
    return obj


def _add_area_light(
    name: str,
    center: Vector,
    direction: Vector,
    radius: float,
    power_factor: float,
) -> None:
    light_data = bpy.data.lights.new(name=name, type="AREA")
    light_data.shape = "SQUARE"
    light_data.size = radius * 3.0
    distance = radius * 4.0
    light_data.energy = power_factor * distance * distance

    light = bpy.data.objects.new(name, light_data)
    light.location = center + direction.normalized() * distance
    light.rotation_euler = (center - light.location).to_track_quat("-Z", "Y").to_euler()
    bpy.data.scenes[0].collection.objects.link(light)


def _build_lighting(center: Vector, radius: float) -> None:
    # Power scales with distance squared so exposure is identical for a 5 cm bolt
    # and a 3 m wall. The factors are tuned for a mid-grey subject under Standard view.
    _add_area_light("Key", center, Vector((1.0, -1.1, 1.3)), radius, 9.0)
    _add_area_light("Fill", center, Vector((-1.3, -0.6, 0.4)), radius, 2.5)
    _add_area_light("Rim", center, Vector((-0.4, 1.4, 0.9)), radius, 5.0)


def _framing_distance(
    corners: Sequence[Vector],
    center: Vector,
    forward: Vector,
    right: Vector,
    up: Vector,
    tan_half_x: float,
    tan_half_y: float,
) -> float:
    required = 0.0
    for corner in corners:
        offset = corner - center
        depth_offset = offset.dot(forward)
        required = max(
            required,
            abs(offset.dot(right)) / tan_half_x - depth_offset,
            abs(offset.dot(up)) / tan_half_y - depth_offset,
        )
    return required * FRAMING_MARGIN


def render_previews(
    objects: Sequence[bpy.types.Object],
    output_dir: Path,
    asset_id: str,
    resolution: int,
    samples: int,
) -> dict[str, str]:
    """Render every view angle and return {view name: absolute png path}."""
    scene = bpy.data.scenes[0]
    lower, upper = world_bounds(objects)
    center = (lower + upper) * 0.5
    radius = max((upper - lower).length * 0.5, 1e-3)
    corners = [
        Vector((x, y, z))
        for x in (lower.x, upper.x)
        for y in (lower.y, upper.y)
        for z in (lower.z, upper.z)
    ]

    _configure_render(scene, resolution, samples)
    _build_world(scene)
    _build_backdrop(center, lower.z, radius)
    _build_lighting(center, radius)

    camera_data = bpy.data.cameras.new("PreviewCamera")
    camera_data.lens = LENS_MM
    camera_data.sensor_fit = "HORIZONTAL"
    camera_data.sensor_width = SENSOR_WIDTH_MM
    camera = bpy.data.objects.new("PreviewCamera", camera_data)
    scene.collection.objects.link(camera)
    scene.camera = camera

    tan_half_x = (SENSOR_WIDTH_MM * 0.5) / LENS_MM
    tan_half_y = tan_half_x * (scene.render.resolution_y / scene.render.resolution_x)

    output_dir.mkdir(parents=True, exist_ok=True)
    rendered: dict[str, str] = {}

    for view in VIEW_ANGLES:
        offset_direction = Vector(view.direction).normalized()
        forward = -offset_direction
        orientation = forward.to_track_quat("-Z", "Y")
        right = orientation @ Vector((1.0, 0.0, 0.0))
        up = orientation @ Vector((0.0, 1.0, 0.0))

        distance = _framing_distance(corners, center, forward, right, up, tan_half_x, tan_half_y)
        if not math.isfinite(distance) or distance <= 0.0:
            raise RuntimeError(f"Could not frame view '{view.name}' (distance={distance})")

        camera.location = center + offset_direction * distance
        camera.rotation_euler = orientation.to_euler()
        camera_data.clip_start = max(distance * 0.01, 1e-4)
        camera_data.clip_end = distance * 20.0

        target = output_dir / f"{asset_id}_{view.name}.png"
        scene.render.filepath = str(target)
        bpy.ops.render.render(write_still=True)
        if not target.is_file():
            raise RuntimeError(f"Render of view '{view.name}' produced no file at {target}")
        rendered[f"preview_{view.name}"] = str(target)

    return rendered
