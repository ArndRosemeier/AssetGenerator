"""Bake the dense sculpt's coat onto the light mesh: a colour map (with its own shading in the folds) and a
normal map of the hair.

The dense mesh carries the colours as a vertex attribute and two stretched coordinates for the hair;
its shader turns those into strands and tufts, Cycles bakes them (selected to active) into the light
mesh's UV layout. Everything procedural ends up in two images, so the glTF carries it.
"""

from __future__ import annotations

import bpy
import numpy as np

from blender.lib.scene import activate


def _attr(obj: bpy.types.Object, name: str, data: np.ndarray, kind: str) -> None:
    me = obj.data
    if kind == "FLOAT_COLOR":
        a = me.color_attributes.new(name, "FLOAT_COLOR", "POINT")
        a.data.foreach_set("color", np.concatenate([data, np.ones((len(data), 1))], axis=1).ravel())
    else:
        a = me.attributes.new(name, "FLOAT_VECTOR", "POINT")
        a.data.foreach_set("vector", data.ravel())


def coat_material(
    obj: bpy.types.Object, colours: np.ndarray, hair: np.ndarray, tufts: np.ndarray
) -> bpy.types.Material:
    """The dense mesh's shader: colours darkened between strands, the strands and tufts as a bump."""
    _attr(obj, "coat", colours, "FLOAT_COLOR")
    _attr(obj, "hair", hair, "FLOAT_VECTOR")
    _attr(obj, "tuft", tufts, "FLOAT_VECTOR")
    m = bpy.data.materials.new("coat_dense")
    m.use_nodes = True
    nt = m.node_tree
    n, links = nt.nodes, nt.links
    bsdf = n["Principled BSDF"]
    bsdf.inputs["Roughness"].default_value = 0.85

    def attribute(name: str) -> bpy.types.NodeSocket:
        a = n.new("ShaderNodeAttribute")
        a.attribute_name = name
        return a

    def noise(vec: bpy.types.NodeSocket, detail: float) -> bpy.types.NodeSocket:
        t = n.new("ShaderNodeTexNoise")
        t.inputs["Scale"].default_value = 1.0
        t.inputs["Detail"].default_value = detail
        t.inputs["Roughness"].default_value = 0.55
        links.new(vec, t.inputs["Vector"])
        return t.outputs["Fac"]

    def math(op: str, a: object, b: object = 0.0) -> bpy.types.NodeSocket:
        node = n.new("ShaderNodeMath")
        node.operation = op
        for i, v in enumerate((a, b)):
            if isinstance(v, bpy.types.NodeSocket):
                links.new(v, node.inputs[i])
            else:
                node.inputs[i].default_value = float(v)
        return node.outputs[0]

    # Strands: ridged noise in hair space, sharpened.
    s = noise(attribute("hair").outputs["Vector"], 1.5)
    s = math("SUBTRACT", 1.0, math("ABSOLUTE", math("SUBTRACT", math("MULTIPLY", s, 2.0), 1.0)))
    s = math("POWER", s, 2.0)
    c = noise(attribute("tuft").outputs["Vector"], 2.0)
    shade = math(
        "MULTIPLY", math("ADD", math("MULTIPLY", s, 0.6), 0.6), math("ADD", math("MULTIPLY", c, 0.5), 0.75)
    )
    col = attribute("coat")
    mul = n.new("ShaderNodeMix")
    mul.data_type = "RGBA"
    mul.blend_type = "MULTIPLY"
    mul.inputs[0].default_value = 1.0
    links.new(col.outputs["Color"], mul.inputs[6])
    comb = n.new("ShaderNodeCombineColor")
    for i in range(3):
        links.new(shade, comb.inputs[i])
    links.new(comb.outputs[0], mul.inputs[7])
    links.new(mul.outputs[2], bsdf.inputs["Base Color"])
    height = math("ADD", math("MULTIPLY", s, 0.6), math("MULTIPLY", c, 0.4))
    bump = n.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.6
    bump.inputs["Distance"].default_value = 0.0025
    links.new(height, bump.inputs["Height"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    obj.data.materials.clear()
    obj.data.materials.append(m)
    return m


def _image(name: str, res: int, data: bool) -> bpy.types.Image:
    img = bpy.data.images.new(name, res, res, alpha=False, float_buffer=False)
    img.colorspace_settings.name = "Non-Color" if data else "sRGB"
    return img


def _target(mat: bpy.types.Material, img: bpy.types.Image) -> None:
    n = mat.node_tree.nodes
    for node in list(n):
        if node.name.startswith("bake_target"):
            n.remove(node)
    t = n.new("ShaderNodeTexImage")
    t.name = "bake_target"
    t.image = img
    t.select = True
    n.active = t


def _emit_colour(mat: bpy.types.Material) -> None:
    """Show the base colour as emission, so an EMIT bake takes it unlit."""
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    src = bsdf.inputs["Base Color"].links[0].from_socket
    nt.links.new(src, bsdf.inputs["Emission Color"])
    bsdf.inputs["Emission Strength"].default_value = 1.0


def bake(
    dense: bpy.types.Object, light: bpy.types.Object, name: str, res: int, samples: int
) -> tuple[bpy.types.Image, bpy.types.Image]:
    """Colour (with ambient occlusion worked in) and tangent-space normals, from `dense` onto `light`'s UVs."""
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    rb = scene.render.bake
    rb.use_selected_to_active = True
    rb.cage_extrusion = 0.012
    rb.max_ray_distance = 0.03
    rb.margin = 6
    rb.use_pass_direct = False
    rb.use_pass_indirect = False
    rb.normal_space = "TANGENT"
    lmat = bpy.data.materials.new(f"{name}_coat")
    lmat.use_nodes = True
    light.data.materials.clear()
    light.data.materials.append(lmat)
    activate(light)
    dense.select_set(True)
    dmat = dense.data.materials[0]

    colour = _image(f"{name}_albedo", res, False)
    normal = _image(f"{name}_normal", res, True)
    occl = _image(f"{name}_ao", res, True)
    _emit_colour(dmat)
    scene.cycles.samples = 1
    _target(lmat, colour)
    bpy.ops.object.bake(type="EMIT")
    _target(lmat, normal)
    bpy.ops.object.bake(type="NORMAL")
    scene.cycles.samples = samples
    _target(lmat, occl)
    bpy.ops.object.bake(type="AO")

    px = np.empty(res * res * 4, dtype=np.float32)
    colour.pixels.foreach_get(px)
    ao = np.empty(res * res * 4, dtype=np.float32)
    occl.pixels.foreach_get(ao)
    px = px.reshape(-1, 4)
    a = ao.reshape(-1, 4)[:, :1]
    px[:, :3] *= 0.4 + 0.6 * a
    colour.pixels.foreach_set(px.ravel())
    bpy.data.images.remove(occl)
    colour.pack()
    normal.pack()
    return colour, normal


def light_material(
    light: bpy.types.Object, colour: bpy.types.Image, normal: bpy.types.Image
) -> bpy.types.Material:
    """The exported coat: the two maps on a rough Principled BSDF."""
    mat = light.data.materials[0]
    nt = mat.node_tree
    for node in list(nt.nodes):
        if node.name.startswith("bake_target"):
            nt.nodes.remove(node)
    bsdf = nt.nodes["Principled BSDF"]
    bsdf.inputs["Roughness"].default_value = 0.85
    t = nt.nodes.new("ShaderNodeTexImage")
    t.image = colour
    nt.links.new(t.outputs["Color"], bsdf.inputs["Base Color"])
    tn = nt.nodes.new("ShaderNodeTexImage")
    tn.image = normal
    nm = nt.nodes.new("ShaderNodeNormalMap")
    nt.links.new(tn.outputs["Color"], nm.inputs["Color"])
    nt.links.new(nm.outputs["Normal"], bsdf.inputs["Normal"])
    return mat
