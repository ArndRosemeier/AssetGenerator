"""Parametric rock with procedural PBR bake.

Geometry: icosphere → non-uniform stretch → seeded noise displace → optional
smooth → sit on Z=0. Materials: a procedural Principled shader (base grit +
mineral veins + bump) is baked to albedo / roughness / normal so the maps
survive glTF export.
"""

from __future__ import annotations

import random
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import bmesh
import bpy
from mathutils import Matrix, Vector, noise

from blender.lib.bake import apply_baked_principled, bake_maps
from blender.lib.scene import activate, unwrap, world_bounds
from blender.lib.spec import (
    AssetSpec,
    SpecError,
    as_float,
    as_int,
    as_str,
    positive_float,
    positive_int,
    reject_unknown,
    require_key,
    require_materials,
)

MATERIAL_SLOTS: tuple[str, ...] = ("rock", "vein")

_PARAM_KEYS = (
    "size",
    "subdivisions",
    "elongation",
    "stretch_axis",
    "smoothness",
    "displace_amount",
    "noise_scale",
    "noise_detail",
    "vein_amount",
    "vein_scale",
    "vein_contrast",
    "vertical_squash",
    "flat_base",
    "texture_resolution",
    "bake_samples",
    "seed",
)

_AXES = ("x", "y", "z")


@dataclass(frozen=True)
class RockParams:
    size: float
    subdivisions: int
    elongation: float
    stretch_axis: str
    smoothness: float
    displace_amount: float
    noise_scale: float
    noise_detail: int
    vein_amount: float
    vein_scale: float
    vein_contrast: float
    ## Scale Z after shaping ( <1 settles the rock into a low fieldstone silhouette).
    vertical_squash: float
    ## Fraction of height from the bottom flattened into a seating face (0 = none).
    flat_base: float
    texture_resolution: int
    bake_samples: int
    seed: int


def _unit_interval(value: object, path: str) -> float:
    number = as_float(value, path)
    if not 0.0 <= number <= 1.0:
        raise SpecError(f"{path}: expected 0..1, got {number}")
    return number


def parse_params(raw: Mapping[str, object]) -> RockParams:
    path = "params"
    reject_unknown(raw, _PARAM_KEYS, path)
    params = RockParams(
        size=positive_float(require_key(raw, "size", path), f"{path}.size"),
        subdivisions=positive_int(require_key(raw, "subdivisions", path), f"{path}.subdivisions"),
        elongation=positive_float(require_key(raw, "elongation", path), f"{path}.elongation"),
        stretch_axis=as_str(require_key(raw, "stretch_axis", path), f"{path}.stretch_axis"),
        smoothness=_unit_interval(require_key(raw, "smoothness", path), f"{path}.smoothness"),
        displace_amount=positive_float(
            require_key(raw, "displace_amount", path), f"{path}.displace_amount"
        ),
        noise_scale=positive_float(require_key(raw, "noise_scale", path), f"{path}.noise_scale"),
        noise_detail=positive_int(require_key(raw, "noise_detail", path), f"{path}.noise_detail"),
        vein_amount=_unit_interval(require_key(raw, "vein_amount", path), f"{path}.vein_amount"),
        vein_scale=positive_float(require_key(raw, "vein_scale", path), f"{path}.vein_scale"),
        vein_contrast=positive_float(
            require_key(raw, "vein_contrast", path), f"{path}.vein_contrast"
        ),
        vertical_squash=_unit_interval(
            require_key(raw, "vertical_squash", path), f"{path}.vertical_squash"
        ),
        flat_base=_unit_interval(require_key(raw, "flat_base", path), f"{path}.flat_base"),
        texture_resolution=positive_int(
            require_key(raw, "texture_resolution", path), f"{path}.texture_resolution"
        ),
        bake_samples=positive_int(require_key(raw, "bake_samples", path), f"{path}.bake_samples"),
        seed=as_int(require_key(raw, "seed", path), f"{path}.seed"),
    )
    _validate(params)
    return params


def _validate(params: RockParams) -> None:
    if params.stretch_axis not in _AXES:
        raise SpecError(f"params.stretch_axis must be one of {_AXES}, got {params.stretch_axis!r}")
    if not 1.0 <= params.elongation <= 4.0:
        raise SpecError(f"params.elongation ({params.elongation}) must be between 1 and 4")
    # bmesh icosphere: 1=20, 2=80, 3=320, 4=1280, 5=5120 tris (off-by-one vs the UI).
    if params.subdivisions < 3 or params.subdivisions > 5:
        raise SpecError(f"params.subdivisions ({params.subdivisions}) must be between 3 and 5")
    if params.noise_detail > 8:
        raise SpecError(f"params.noise_detail ({params.noise_detail}) must be <= 8")
    if params.texture_resolution not in {256, 512, 1024, 2048}:
        raise SpecError(
            f"params.texture_resolution ({params.texture_resolution}) must be 256, 512, 1024 or 2048"
        )
    if params.bake_samples > 128:
        raise SpecError(f"params.bake_samples ({params.bake_samples}) must be <= 128")
    if params.vertical_squash < 0.35:
        raise SpecError(
            f"params.vertical_squash ({params.vertical_squash}) must be >= 0.35 "
            f"(or the rock collapses to a pancake)."
        )


def _axis_scales(params: RockParams) -> Vector:
    scales = Vector((1.0, 1.0, 1.0))
    index = _AXES.index(params.stretch_axis)
    scales[index] = params.elongation
    # Keep the longest axis near `size`.
    return scales * (params.size / max(scales))


def _displace(bm: bmesh.types.BMesh, params: RockParams, rng: random.Random) -> None:
    # mathutils.noise uses a process-global seed; offset coords for extra variety.
    noise.seed_set(params.seed)
    origin = Vector(
        (
            rng.uniform(-50.0, 50.0),
            rng.uniform(-50.0, 50.0),
            rng.uniform(-50.0, 50.0),
        )
    )
    amount = params.displace_amount * params.size * (1.0 - 0.65 * params.smoothness)
    for vert in bm.verts:
        sample = (vert.co * params.noise_scale) + origin
        value = noise.turbulence(
            sample,
            params.noise_detail,
            True,
            noise_basis="PERLIN_ORIGINAL",
            amplitude_scale=0.5,
            frequency_scale=2.0,
        )
        centered = (value - 0.5) * 2.0
        vert.co += vert.normal * centered * amount


def _smooth(bm: bmesh.types.BMesh, smoothness: float) -> None:
    if smoothness <= 0.01:
        return
    iterations = max(1, int(round(1 + smoothness * 5)))
    factor = 0.35 + 0.5 * smoothness
    bmesh.ops.smooth_vert(
        bm,
        verts=list(bm.verts),
        factor=factor,
        use_axis_x=True,
        use_axis_y=True,
        use_axis_z=True,
    )
    for _ in range(iterations - 1):
        bmesh.ops.smooth_vert(
            bm,
            verts=list(bm.verts),
            factor=factor * 0.7,
            use_axis_x=True,
            use_axis_y=True,
            use_axis_z=True,
        )


def _flatten_base(bm: bmesh.types.BMesh, flat_base: float) -> None:
    """Crush the bottom of the mesh into a seating plane so it rests on the ground."""
    if flat_base <= 0.01 or not bm.verts:
        return
    zs = [vert.co.z for vert in bm.verts]
    z_min = min(zs)
    z_max = max(zs)
    height = z_max - z_min
    if height <= 1e-6:
        return
    cut = z_min + height * flat_base
    for vert in bm.verts:
        if vert.co.z < cut:
            vert.co.z = cut


def _build_mesh(params: RockParams, rng: random.Random) -> bpy.types.Mesh:
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=params.subdivisions, radius=0.5)
    bmesh.ops.transform(bm, verts=list(bm.verts), matrix=Matrix.Diagonal((*_axis_scales(params), 1.0)))
    if abs(params.vertical_squash - 1.0) > 1e-4:
        bmesh.ops.transform(
            bm,
            verts=list(bm.verts),
            matrix=Matrix.Diagonal((1.0, 1.0, params.vertical_squash, 1.0)),
        )
    bm.normal_update()
    _displace(bm, params, rng)
    bm.normal_update()
    _smooth(bm, params.smoothness)
    _flatten_base(bm, params.flat_base)
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))

    mesh = bpy.data.meshes.new("rock_mesh")
    bm.to_mesh(mesh)
    bm.free()
    return mesh


def _mix_rgba(
    nodes: bpy.types.Nodes,
    links: bpy.types.NodeLinks,
    *,
    location: tuple[float, float],
    factor: bpy.types.NodeSocket,
    color_a: bpy.types.NodeSocket,
    color_b: bpy.types.NodeSocket,
) -> bpy.types.NodeSocket:
    """ShaderNodeMix with explicit RGBA sockets (name-based 'A'/'B' is ambiguous)."""
    mix = nodes.new(type="ShaderNodeMix")
    mix.data_type = "RGBA"
    mix.location = location
    links.new(factor, mix.inputs[0])
    links.new(color_a, mix.inputs[6])
    links.new(color_b, mix.inputs[7])
    return mix.outputs[2]


def _build_procedural_material(spec: AssetSpec, params: RockParams) -> bpy.types.Material:
    rock = spec.materials["rock"]
    vein = spec.materials["vein"]

    material = bpy.data.materials.new(name=f"{spec.asset_id}_proc")
    material.use_nodes = True
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    nodes.clear()

    output = nodes.new(type="ShaderNodeOutputMaterial")
    output.location = (900, 0)
    principled = nodes.new(type="ShaderNodeBsdfPrincipled")
    principled.location = (650, 0)
    principled.inputs["Metallic"].default_value = rock.metallic
    links.new(principled.outputs["BSDF"], output.inputs["Surface"])

    # Generated coords bake reliably; Object coords can go flat in headless emits.
    tex_coord = nodes.new(type="ShaderNodeTexCoord")
    tex_coord.location = (-800, 100)
    seed_shift = float(params.seed % 1000)

    grit_map = nodes.new(type="ShaderNodeMapping")
    grit_map.location = (-600, 220)
    grit_map.inputs["Scale"].default_value = (
        params.noise_scale * 2.2,
        params.noise_scale * 2.2,
        params.noise_scale * 2.2,
    )
    grit_map.inputs["Location"].default_value = (seed_shift * 0.13, seed_shift * 0.07, seed_shift * 0.03)
    links.new(tex_coord.outputs["Generated"], grit_map.inputs["Vector"])
    grit_noise = nodes.new(type="ShaderNodeTexNoise")
    grit_noise.location = (-400, 220)
    grit_noise.inputs["Scale"].default_value = 1.0
    grit_noise.inputs["Detail"].default_value = float(params.noise_detail)
    grit_noise.inputs["Roughness"].default_value = 0.6
    links.new(grit_map.outputs["Vector"], grit_noise.inputs["Vector"])

    vein_map = nodes.new(type="ShaderNodeMapping")
    vein_map.location = (-600, -40)
    vein_map.inputs["Scale"].default_value = (1.0, params.vein_scale * 2.5, 1.0)
    vein_map.inputs["Rotation"].default_value = (0.0, 0.0, 0.7 + seed_shift * 0.01)
    vein_map.inputs["Location"].default_value = (seed_shift * 0.05, seed_shift * 0.11, 0.0)
    links.new(tex_coord.outputs["Generated"], vein_map.inputs["Vector"])
    # Wave texture → clear mineral streaks that survive baking.
    vein_wave = nodes.new(type="ShaderNodeTexWave")
    vein_wave.location = (-400, -40)
    vein_wave.wave_type = "BANDS"
    vein_wave.bands_direction = "X"
    vein_wave.wave_profile = "SIN"
    # Lower scale → fewer bands; distortion warps them into mineral streaks.
    vein_wave.inputs["Scale"].default_value = max(0.4, params.vein_scale * 0.35)
    vein_wave.inputs["Distortion"].default_value = 1.2 + params.vein_contrast * 0.25
    vein_wave.inputs["Detail"].default_value = 2.0
    vein_wave.inputs["Detail Scale"].default_value = 1.0
    links.new(vein_map.outputs["Vector"], vein_wave.inputs["Vector"])

    # Keep only wave peaks → a handful of streaks instead of contour fill.
    vein_mask = nodes.new(type="ShaderNodeMapRange")
    vein_mask.location = (-200, -40)
    vein_mask.inputs["From Min"].default_value = 0.78
    vein_mask.inputs["From Max"].default_value = 0.96
    vein_mask.inputs["To Min"].default_value = 0.0
    vein_mask.inputs["To Max"].default_value = 1.0
    vein_mask.clamp = True
    links.new(vein_wave.outputs["Fac"], vein_mask.inputs["Value"])

    vein_amt = nodes.new(type="ShaderNodeMath")
    vein_amt.location = (0, -40)
    vein_amt.operation = "MULTIPLY"
    vein_amt.inputs[1].default_value = params.vein_amount
    links.new(vein_mask.outputs["Result"], vein_amt.inputs[0])

    rock_rgb = nodes.new(type="ShaderNodeRGB")
    rock_rgb.location = (-200, 320)
    rock_rgb.outputs[0].default_value = rock.base_color
    dark_rgb = nodes.new(type="ShaderNodeRGB")
    dark_rgb.location = (-200, 480)
    dark_rgb.outputs[0].default_value = (
        max(0.0, rock.base_color[0] * 0.45),
        max(0.0, rock.base_color[1] * 0.45),
        max(0.0, rock.base_color[2] * 0.45),
        1.0,
    )
    vein_rgb = nodes.new(type="ShaderNodeRGB")
    vein_rgb.location = (0, 120)
    vein_rgb.outputs[0].default_value = vein.base_color

    grit_color = _mix_rgba(
        nodes,
        links,
        location=(0, 280),
        factor=grit_noise.outputs["Fac"],
        color_a=dark_rgb.outputs[0],
        color_b=rock_rgb.outputs[0],
    )
    surface_color = _mix_rgba(
        nodes,
        links,
        location=(220, 80),
        factor=vein_amt.outputs["Value"],
        color_a=grit_color,
        color_b=vein_rgb.outputs[0],
    )
    links.new(surface_color, principled.inputs["Base Color"])

    rough_math = nodes.new(type="ShaderNodeMath")
    rough_math.location = (220, -160)
    rough_math.operation = "MULTIPLY_ADD"
    rough_math.inputs[1].default_value = 0.3
    rough_math.inputs[2].default_value = rock.roughness * 0.8
    links.new(grit_noise.outputs["Fac"], rough_math.inputs[0])
    clamp_rough = nodes.new(type="ShaderNodeClamp")
    clamp_rough.location = (400, -160)
    clamp_rough.inputs["Min"].default_value = 0.25
    clamp_rough.inputs["Max"].default_value = 1.0
    links.new(rough_math.outputs["Value"], clamp_rough.inputs["Value"])
    links.new(clamp_rough.outputs["Result"], principled.inputs["Roughness"])

    bump = nodes.new(type="ShaderNodeBump")
    bump.location = (400, -320)
    bump.inputs["Strength"].default_value = 0.7 + 0.4 * (1.0 - params.smoothness)
    bump.inputs["Distance"].default_value = 0.1 * params.size
    bump_add = nodes.new(type="ShaderNodeMath")
    bump_add.location = (220, -320)
    bump_add.operation = "ADD"
    links.new(grit_noise.outputs["Fac"], bump_add.inputs[0])
    links.new(vein_mask.outputs["Result"], bump_add.inputs[1])
    links.new(bump_add.outputs["Value"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], principled.inputs["Normal"])

    return material


def build(spec: AssetSpec) -> list[bpy.types.Object]:
    require_materials(spec.materials, MATERIAL_SLOTS, spec.generator)
    params = parse_params(spec.params)
    rng = random.Random(params.seed)

    mesh = _build_mesh(params, rng)
    obj = bpy.data.objects.new(spec.asset_id, mesh)
    bpy.data.scenes[0].collection.objects.link(obj)

    for polygon in mesh.polygons:
        polygon.use_smooth = True

    lower, upper = world_bounds([obj])
    shift = Vector((-(lower.x + upper.x) * 0.5, -(lower.y + upper.y) * 0.5, -lower.z))
    if shift.length > 1e-6:
        mesh.transform(Matrix.Translation(shift))
        mesh.update()

    unwrap(obj)
    material = _build_procedural_material(spec, params)
    mesh.materials.clear()
    mesh.materials.append(material)

    texture_dump = Path(__file__).resolve().parents[2] / "assets" / "out" / "textures"
    maps = bake_maps(
        obj,
        asset_id=spec.asset_id,
        resolution=params.texture_resolution,
        samples=params.bake_samples,
        dump_dir=texture_dump,
    )
    apply_baked_principled(obj, maps, metallic=spec.materials["rock"].metallic)

    activate(obj)
    return [obj]
