"""Bake Idle / Walk / Run actions onto the crawler armature."""

from __future__ import annotations

import math
import re

import bpy

from blender.generators.crawler_generator.params import CrawlerParams
from blender.lib.scene import activate

_LEG_NAME = re.compile(r"^leg_([LR])(\d+)_(\d+)$")

FPS = 24
IDLE_FRAMES = 48
WALK_CYCLES = 1
RUN_CYCLES = 1


def _ensure_euler(pose_bone: bpy.types.PoseBone) -> None:
    pose_bone.rotation_mode = "XYZ"


def _key_pose(armature: bpy.types.Object, frame: int) -> None:
    for pose_bone in armature.pose.bones:
        pose_bone.keyframe_insert(data_path="rotation_euler", frame=frame)
        pose_bone.keyframe_insert(data_path="location", frame=frame)


def _reset_pose(armature: bpy.types.Object) -> None:
    for pose_bone in armature.pose.bones:
        _ensure_euler(pose_bone)
        pose_bone.rotation_euler = (0.0, 0.0, 0.0)
        pose_bone.location = (0.0, 0.0, 0.0)


def _leg_phase(name: str) -> float:
    match = _LEG_NAME.match(name)
    if match is None:
        raise RuntimeError(f"Not a leg bone: {name}")
    side = match.group(1)
    pair = int(match.group(2))
    side_bit = 0 if side == "L" else 1
    return 0.0 if (pair + side_bit) % 2 == 0 else math.pi


def _apply_walk(armature: bpy.types.Object, cycle_t: float, *, lift: float, swing: float) -> None:
    omega = cycle_t * math.tau
    for pose_bone in armature.pose.bones:
        _ensure_euler(pose_bone)
        match = _LEG_NAME.match(pose_bone.name)
        if match is None:
            continue
        segment = int(match.group(3))
        phase = omega + _leg_phase(pose_bone.name)
        wave = math.sin(phase)
        travel = math.cos(phase)
        if segment == 0:
            pose_bone.rotation_euler = (
                lift * max(0.0, wave),
                swing * travel,
                0.0,
            )
        elif segment == 1:
            pose_bone.rotation_euler = (
                lift * 0.65 * max(0.0, wave),
                swing * -0.35 * travel,
                0.0,
            )
        else:
            pose_bone.rotation_euler = (
                -lift * 0.25 * max(0.0, wave),
                0.0,
                0.0,
            )


def _apply_idle(armature: bpy.types.Object, cycle_t: float, amp: float) -> None:
    omega = cycle_t * math.tau
    bob = amp * 0.006 * math.sin(omega)
    sway = amp * 0.08 * math.sin(omega)
    for pose_bone in armature.pose.bones:
        _ensure_euler(pose_bone)
        pose_bone.rotation_euler = (0.0, 0.0, 0.0)
        pose_bone.location = (0.0, 0.0, 0.0)
        if pose_bone.name == "body":
            pose_bone.location = (0.0, 0.0, bob)
            pose_bone.rotation_euler = (sway * 0.15, 0.0, 0.0)
        elif pose_bone.name == "abdomen":
            pose_bone.rotation_euler = (sway * 0.35, 0.0, 0.0)
        elif pose_bone.name.startswith("antenna_"):
            pose_bone.rotation_euler = (0.0, sway * 0.8, sway * 0.4)
        elif pose_bone.name.startswith("mandible_"):
            sign = 1.0 if pose_bone.name.endswith("_L") else -1.0
            pose_bone.rotation_euler = (0.0, 0.0, sign * amp * 0.12 * math.sin(omega * 2.0))
        elif pose_bone.name.startswith("stinger_"):
            pose_bone.rotation_euler = (amp * 0.2 * math.sin(omega + 0.4), 0.0, 0.0)


def _stash(armature: bpy.types.Object, action: bpy.types.Action, name: str) -> None:
    if armature.animation_data is None:
        armature.animation_data_create()
    track = armature.animation_data.nla_tracks.new()
    track.name = name
    start = int(action.frame_range[0])
    strip = track.strips.new(name, start, action)
    strip.action = action
    strip.name = name


def _record_action(
    armature: bpy.types.Object,
    name: str,
    frames: int,
    apply_frame: object,
) -> bpy.types.Action:
    action = bpy.data.actions.new(name=name)
    armature.animation_data_create()
    armature.animation_data.action = action
    for frame in range(1, frames + 1):
        cycle_t = (frame - 1) / frames
        apply_frame(cycle_t)
        bpy.context.scene.frame_set(frame)
        _key_pose(armature, frame)
    for fcurve in action.fcurves:
        for key in fcurve.keyframe_points:
            key.interpolation = "LINEAR"
    armature.animation_data.action = None
    _stash(armature, action, name)
    _reset_pose(armature)
    return action


def bake_gaits(armature: bpy.types.Object, params: CrawlerParams) -> None:
    activate(armature)
    bpy.context.scene.render.fps = FPS
    bpy.context.scene.frame_start = 1
    _reset_pose(armature)

    walk_frames = max(8, int(round(FPS / params.walk_hz)) * WALK_CYCLES)
    run_frames = max(6, int(round(FPS / params.run_hz)) * RUN_CYCLES)

    _record_action(
        armature,
        "Idle",
        IDLE_FRAMES,
        lambda t: _apply_idle(armature, t, params.idle_amp),
    )
    _record_action(
        armature,
        "Walk",
        walk_frames,
        lambda t: _apply_walk(armature, t, lift=0.38, swing=0.32),
    )
    _record_action(
        armature,
        "Run",
        run_frames,
        lambda t: _apply_walk(armature, t, lift=0.52, swing=0.44),
    )
    armature.data.pose_position = "REST"
    bpy.context.scene.frame_set(1)
