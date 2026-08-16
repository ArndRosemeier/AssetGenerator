"""glTF export and round-trip verification.

Modifiers are applied by the generator before this runs, so the exporter never
re-evaluates the dependency graph and the QA numbers describe exactly what ends
up in the .glb. Draco is deliberately off: it is a delivery-time optimisation
and corrupts geometry when applied twice.
"""

from __future__ import annotations

from pathlib import Path
from collections.abc import Sequence

import bpy

from blender.lib.report import CheckResult, MeshStats, check
from blender.lib.scene import activate, reset_scene


def export_glb(objects: Sequence[bpy.types.Object], destination: Path) -> Path:
    if not objects:
        raise RuntimeError("Nothing to export")
    destination.parent.mkdir(parents=True, exist_ok=True)

    for obj in bpy.data.objects:
        obj.select_set(False)
    for obj in objects:
        obj.select_set(True)
    activate(objects[0])
    for obj in objects:
        obj.select_set(True)

    has_armature = any(obj.type == "ARMATURE" for obj in objects)
    if has_armature:
        for obj in objects:
            if obj.type != "ARMATURE":
                continue
            obj.data.pose_position = "REST"
        bpy.context.view_layer.update()
        bpy.context.scene.frame_set(1)
    bpy.ops.export_scene.gltf(
        filepath=str(destination),
        export_format="GLB",
        use_selection=True,
        export_apply=False,
        export_yup=True,
        export_normals=True,
        export_texcoords=True,
        export_materials="EXPORT",
        export_cameras=False,
        export_lights=False,
        export_skins=has_armature,
        export_animations=has_armature,
        export_animation_mode="NLA_TRACKS",
        export_rest_position_armature=True,
        export_current_frame=False,
        export_leaf_bone=False,
        export_extras=False,
        export_draco_mesh_compression_enable=False,
    )

    if not destination.is_file():
        raise RuntimeError(f"glTF export reported success but {destination} does not exist")
    return destination


def import_glb(source: Path) -> list[bpy.types.Object]:
    """Import a .glb into a freshly emptied scene and return its mesh objects.

    The importer reverses the Y-up conversion with a parent empty and a rotated
    root. Those are baked away here so the reimported asset can be compared with
    the authored scene on equal terms.
    """
    if not source.is_file():
        raise FileNotFoundError(f"No such glb: {source}")
    reset_scene()
    bpy.ops.import_scene.gltf(
        filepath=str(source),
        bone_heuristic="BLENDER",
        guess_original_bind_pose=False,
        disable_bone_shape=True,
    )
    meshes = [obj for obj in bpy.data.objects if obj.type == "MESH"]
    if not meshes:
        raise RuntimeError(f"{source.name} imported without any mesh objects")

    armatures = [obj for obj in bpy.data.objects if obj.type == "ARMATURE"]
    if armatures:
        # Applying transforms on a skinned mesh destroys the bind pose and
        # inflates the AABB. Measure rest-pose world bounds instead.
        for armature in armatures:
            armature.data.pose_position = "REST"
            if armature.animation_data is not None:
                armature.animation_data.action = None
                for track in armature.animation_data.nla_tracks:
                    track.mute = True
            for pose_bone in armature.pose.bones:
                pose_bone.matrix_basis.identity()
        bpy.context.view_layer.update()
        return meshes

    for obj in bpy.data.objects:
        obj.select_set(obj.type == "MESH")
    activate(meshes[0])
    for obj in meshes:
        obj.select_set(True)
    bpy.ops.object.parent_clear(type="CLEAR_KEEP_TRANSFORM")
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)

    for obj in list(bpy.data.objects):
        if obj.type != "MESH":
            bpy.data.objects.remove(obj, do_unlink=True)
    return [obj for obj in bpy.data.objects if obj.type == "MESH"]


def roundtrip_checks(before: MeshStats, after: MeshStats) -> list[CheckResult]:
    """Compare pre-export geometry with what the exported file actually contains."""
    checks: list[CheckResult] = []
    for key in ("triangles", "materials", "uv_layers"):
        checks.append(
            check(
                f"roundtrip_{key}",
                before[key] == after[key],
                f"{before[key]} in scene vs {after[key]} in glb",
            )
        )
    dimension_delta = max(
        abs(a - b) for a, b in zip(before["dimensions_m"], after["dimensions_m"])
    )
    checks.append(
        check(
            "roundtrip_dimensions",
            dimension_delta < 1e-3,
            f"largest axis deviation {dimension_delta:.6f} m",
        )
    )
    return checks
