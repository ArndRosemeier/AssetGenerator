"""Bake procedural Principled shaders down to glTF-safe image textures.

glTF cannot carry Blender noise nodes, so anything procedural must be baked
before export. Cycles CPU baking works headless.

Albedo is baked via EMIT (Base Color temporarily routed to Emission) because
DIFFUSE COLOR bakes are unreliable for unlit colour extraction in background mode.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import bpy

from blender.lib.scene import activate


@dataclass(frozen=True)
class BakedMaps:
    albedo: bpy.types.Image
    roughness: bpy.types.Image
    normal: bpy.types.Image


def _configure_cycles_for_bake(samples: int) -> None:
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = samples
    scene.render.bake.use_pass_direct = False
    scene.render.bake.use_pass_indirect = False
    scene.render.bake.use_pass_color = True
    scene.render.bake.margin = 8
    scene.render.bake.normal_space = "TANGENT"


def _ensure_uv(obj: bpy.types.Object) -> None:
    mesh = obj.data
    if not mesh.uv_layers:
        raise RuntimeError(f"Object '{obj.name}' has no UV map; unwrap before baking")


def _new_image(name: str, resolution: int, *, is_data: bool) -> bpy.types.Image:
    image = bpy.data.images.new(
        name=name,
        width=resolution,
        height=resolution,
        alpha=False,
        float_buffer=False,
    )
    image.colorspace_settings.name = "Non-Color" if is_data else "sRGB"
    return image


def _slot_materials(obj: bpy.types.Object) -> list[bpy.types.Material]:
    materials: list[bpy.types.Material] = []
    for slot in obj.material_slots:
        if slot.material is None:
            raise RuntimeError(f"Object '{obj.name}' has an empty material slot")
        if slot.material not in materials:
            materials.append(slot.material)
    if not materials:
        raise RuntimeError(f"Object '{obj.name}' has no material to bake")
    return materials


def _active_image_target(material: bpy.types.Material, image: bpy.types.Image) -> bpy.types.ShaderNodeTexImage:
    nodes = material.node_tree.nodes
    for node in list(nodes):
        if node.name.startswith("BakeTarget_"):
            nodes.remove(node)
    target = nodes.new(type="ShaderNodeTexImage")
    target.name = f"BakeTarget_{image.name}"
    target.image = image
    target.select = True
    nodes.active = target
    return target


def _set_bake_targets(materials: Sequence[bpy.types.Material], image: bpy.types.Image) -> None:
    for material in materials:
        _active_image_target(material, image)


def _principled(material: bpy.types.Material) -> bpy.types.ShaderNode:
    for node in material.node_tree.nodes:
        if node.type == "BSDF_PRINCIPLED":
            return node
    raise RuntimeError(f"Material '{material.name}' has no Principled BSDF")


@dataclass
class _EmitRestore:
    material: bpy.types.Material
    base_sockets: list[bpy.types.NodeSocket]
    emit_sockets: list[bpy.types.NodeSocket]
    strength: float


def _prepare_emit_albedo(material: bpy.types.Material) -> _EmitRestore:
    """Route Base Color into Emission so an EMIT bake captures unlit colour."""
    links = material.node_tree.links
    principled = _principled(material)
    base_input = principled.inputs["Base Color"]
    emit_input = principled.inputs["Emission Color"]
    emit_strength = principled.inputs["Emission Strength"]
    previous_base_links = [link.from_socket for link in base_input.links]
    previous_emit_links = [link.from_socket for link in emit_input.links]
    previous_strength = emit_strength.default_value
    if not previous_base_links:
        raise RuntimeError(f"Material '{material.name}' Base Color has no incoming link to bake")
    for link in list(emit_input.links):
        links.remove(link)
    links.new(previous_base_links[0], emit_input)
    emit_strength.default_value = 1.0
    for link in list(base_input.links):
        links.remove(link)
    base_input.default_value = (0.0, 0.0, 0.0, 1.0)
    return _EmitRestore(
        material=material,
        base_sockets=previous_base_links,
        emit_sockets=previous_emit_links,
        strength=previous_strength,
    )


def _restore_emit_albedo(state: _EmitRestore) -> None:
    links = state.material.node_tree.links
    principled = _principled(state.material)
    base_input = principled.inputs["Base Color"]
    emit_input = principled.inputs["Emission Color"]
    emit_strength = principled.inputs["Emission Strength"]
    for link in list(emit_input.links):
        links.remove(link)
    for socket in state.emit_sockets:
        links.new(socket, emit_input)
    emit_strength.default_value = state.strength
    for socket in state.base_sockets:
        links.new(socket, base_input)


def _bake_albedo_via_emit(materials: Sequence[bpy.types.Material], image: bpy.types.Image) -> None:
    """Route Base Color into Emission on every slot, bake EMIT, then restore."""
    _set_bake_targets(materials, image)
    restored = [_prepare_emit_albedo(material) for material in materials]
    bpy.ops.object.bake(type="EMIT")
    for state in restored:
        _restore_emit_albedo(state)


def bake_maps(
    obj: bpy.types.Object,
    *,
    asset_id: str,
    resolution: int,
    samples: int,
    dump_dir: Path | None = None,
) -> BakedMaps:
    """Bake albedo, roughness and tangent normals from every material slot.

    Faces keep their own shaders; all slots write into one UV atlas so a
    two-slot kit cell (plaster + timber) becomes one glTF material.
    """
    materials = _slot_materials(obj)
    for material in materials:
        if not material.use_nodes:
            raise RuntimeError(f"Material '{material.name}' must use nodes for baking")

    _ensure_uv(obj)
    _configure_cycles_for_bake(samples)
    activate(obj)

    albedo = _new_image(f"{asset_id}_albedo", resolution, is_data=False)
    roughness = _new_image(f"{asset_id}_roughness", resolution, is_data=True)
    normal = _new_image(f"{asset_id}_normal", resolution, is_data=True)

    _bake_albedo_via_emit(materials, albedo)

    _set_bake_targets(materials, roughness)
    bpy.ops.object.bake(type="ROUGHNESS")

    _set_bake_targets(materials, normal)
    bpy.ops.object.bake(type="NORMAL")

    for image in (albedo, roughness, normal):
        image.pack()

    if dump_dir is not None:
        dump_dir.mkdir(parents=True, exist_ok=True)
        for image in (albedo, roughness, normal):
            path = dump_dir / f"{image.name}.png"
            image.filepath_raw = str(path)
            image.file_format = "PNG"
            image.save()
            image.pack()

    return BakedMaps(albedo=albedo, roughness=roughness, normal=normal)


def apply_baked_principled(
    obj: bpy.types.Object,
    maps: BakedMaps,
    *,
    metallic: float,
) -> bpy.types.Material:
    """Replace all slots with one Principled material driven by the baked maps."""
    material = bpy.data.materials.new(name=f"{obj.name}_baked")
    material.use_nodes = True
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    nodes.clear()

    output = nodes.new(type="ShaderNodeOutputMaterial")
    output.location = (400, 0)
    principled = nodes.new(type="ShaderNodeBsdfPrincipled")
    principled.location = (100, 0)
    principled.inputs["Metallic"].default_value = metallic
    links.new(principled.outputs["BSDF"], output.inputs["Surface"])

    albedo_node = nodes.new(type="ShaderNodeTexImage")
    albedo_node.location = (-400, 200)
    albedo_node.image = maps.albedo
    albedo_node.image.colorspace_settings.name = "sRGB"
    links.new(albedo_node.outputs["Color"], principled.inputs["Base Color"])

    rough_node = nodes.new(type="ShaderNodeTexImage")
    rough_node.location = (-400, 0)
    rough_node.image = maps.roughness
    rough_node.image.colorspace_settings.name = "Non-Color"
    links.new(rough_node.outputs["Color"], principled.inputs["Roughness"])

    normal_tex = nodes.new(type="ShaderNodeTexImage")
    normal_tex.location = (-400, -220)
    normal_tex.image = maps.normal
    normal_tex.image.colorspace_settings.name = "Non-Color"
    normal_map = nodes.new(type="ShaderNodeNormalMap")
    normal_map.location = (-120, -220)
    normal_map.space = "TANGENT"
    links.new(normal_tex.outputs["Color"], normal_map.inputs["Color"])
    links.new(normal_map.outputs["Normal"], principled.inputs["Normal"])

    obj.data.materials.clear()
    obj.data.materials.append(material)
    return material
