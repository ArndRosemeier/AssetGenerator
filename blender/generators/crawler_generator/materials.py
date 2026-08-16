"""Procedural chitin / abdomen shaders, baked to glTF-safe maps."""

from __future__ import annotations

from pathlib import Path

import bpy

from blender.generators.crawler_generator.params import CrawlerParams
from blender.lib.bake import apply_baked_principled, bake_maps
from blender.lib.spec import AssetSpec, MaterialSpec
from blender.lib.scene import unwrap


def _mix_rgba(
    nodes: bpy.types.Nodes,
    links: bpy.types.NodeLinks,
    *,
    location: tuple[float, float],
    factor: bpy.types.NodeSocket,
    color_a: bpy.types.NodeSocket,
    color_b: bpy.types.NodeSocket,
) -> bpy.types.NodeSocket:
    mix = nodes.new(type="ShaderNodeMix")
    mix.data_type = "RGBA"
    mix.location = location
    links.new(factor, mix.inputs[0])
    links.new(color_a, mix.inputs[6])
    links.new(color_b, mix.inputs[7])
    return mix.outputs[2]


def _build_slot_material(
    name: str,
    spec: MaterialSpec,
    params: CrawlerParams,
    *,
    grit_scale: float,
    bump_strength: float,
) -> bpy.types.Material:
    material = bpy.data.materials.new(name=name)
    material.use_nodes = True
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    nodes.clear()

    output = nodes.new(type="ShaderNodeOutputMaterial")
    output.location = (820, 0)
    principled = nodes.new(type="ShaderNodeBsdfPrincipled")
    principled.location = (560, 0)
    principled.inputs["Metallic"].default_value = spec.metallic
    links.new(principled.outputs["BSDF"], output.inputs["Surface"])

    tex_coord = nodes.new(type="ShaderNodeTexCoord")
    tex_coord.location = (-780, 80)
    seed_shift = float(params.seed % 1000)

    mapping = nodes.new(type="ShaderNodeMapping")
    mapping.location = (-560, 120)
    mapping.inputs["Scale"].default_value = (grit_scale, grit_scale, grit_scale)
    mapping.inputs["Location"].default_value = (
        seed_shift * 0.11,
        seed_shift * 0.07,
        seed_shift * 0.03,
    )
    links.new(tex_coord.outputs["Generated"], mapping.inputs["Vector"])

    noise_node = nodes.new(type="ShaderNodeTexNoise")
    noise_node.location = (-340, 120)
    noise_node.inputs["Scale"].default_value = 1.0
    noise_node.inputs["Detail"].default_value = 5.0
    noise_node.inputs["Roughness"].default_value = 0.55
    links.new(mapping.outputs["Vector"], noise_node.inputs["Vector"])

    base_rgb = nodes.new(type="ShaderNodeRGB")
    base_rgb.location = (-340, 340)
    base_rgb.outputs[0].default_value = spec.base_color
    dark_rgb = nodes.new(type="ShaderNodeRGB")
    dark_rgb.location = (-340, 500)
    dark_rgb.outputs[0].default_value = (
        max(0.0, spec.base_color[0] * 0.42),
        max(0.0, spec.base_color[1] * 0.42),
        max(0.0, spec.base_color[2] * 0.42),
        1.0,
    )
    surface = _mix_rgba(
        nodes,
        links,
        location=(0, 200),
        factor=noise_node.outputs["Fac"],
        color_a=dark_rgb.outputs[0],
        color_b=base_rgb.outputs[0],
    )
    links.new(surface, principled.inputs["Base Color"])

    rough = nodes.new(type="ShaderNodeMath")
    rough.location = (0, -80)
    rough.operation = "MULTIPLY_ADD"
    rough.inputs[1].default_value = 0.22
    rough.inputs[2].default_value = spec.roughness * 0.82
    links.new(noise_node.outputs["Fac"], rough.inputs[0])
    clamp_rough = nodes.new(type="ShaderNodeClamp")
    clamp_rough.location = (220, -80)
    clamp_rough.inputs["Min"].default_value = 0.12
    clamp_rough.inputs["Max"].default_value = 1.0
    links.new(rough.outputs["Value"], clamp_rough.inputs["Value"])
    links.new(clamp_rough.outputs["Result"], principled.inputs["Roughness"])

    bump = nodes.new(type="ShaderNodeBump")
    bump.location = (220, -260)
    bump.inputs["Strength"].default_value = bump_strength
    bump.inputs["Distance"].default_value = 0.008
    links.new(noise_node.outputs["Fac"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], principled.inputs["Normal"])
    return material


def apply_crawler_materials(
    obj: bpy.types.Object,
    spec: AssetSpec,
    params: CrawlerParams,
) -> None:
    unwrap(obj, island_margin=0.012)
    chitin = _build_slot_material(
        f"{spec.asset_id}_chitin_proc",
        spec.materials["chitin"],
        params,
        grit_scale=14.0,
        bump_strength=0.85,
    )
    abdomen = _build_slot_material(
        f"{spec.asset_id}_abdomen_proc",
        spec.materials["abdomen"],
        params,
        grit_scale=7.5,
        bump_strength=0.45,
    )
    obj.data.materials.clear()
    obj.data.materials.append(chitin)
    obj.data.materials.append(abdomen)

    texture_dump = Path(__file__).resolve().parents[3] / "assets" / "out" / "textures"
    maps = bake_maps(
        obj,
        asset_id=spec.asset_id,
        resolution=params.texture_resolution,
        samples=params.bake_samples,
        dump_dir=texture_dump,
    )
    apply_baked_principled(obj, maps, metallic=spec.materials["chitin"].metallic)
