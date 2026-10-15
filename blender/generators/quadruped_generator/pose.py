"""Posing the skeleton from what an animator thinks in: turns of bones about their joints, in the rest
pose's own axes (+X the dog's left, +Y forward, +Z up), and paws put down where they should be.

A pose gives each bone a rigid motion of the rest skeleton. Turns are taken about the bone's head,
after its parent's motion; legs with a paw target are solved instead (two-bone IK down to the hock or
wrist, the metatarsus / pastern at a given slope down to the paw, the toes flat on the ground).
The result is written as each bone's local transform and keyed.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import bpy
from mathutils import Matrix, Quaternion, Vector

from blender.generators.quadruped_generator.anatomy import Body


def turn(axis: tuple[float, float, float], angle: float) -> Quaternion:
    return Quaternion(Vector(axis).normalized(), angle)


X, Y, Z = (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)


@dataclass
class Paw:
    """Where a leg puts its paw (the ball of the foot), how the lower leg slopes down to it (radians
    from straight down, positive leaning back so the joint above is behind the paw), and how far the
    toes curl (radians)."""

    ball: Vector
    slope: float = 0.0
    curl: float = 0.0


@dataclass
class Pose:
    #: Motion of the whole dog (on the root bone, about the ground under the body).
    lift: Vector = field(default_factory=lambda: Vector((0.0, 0.0, 0.0)))
    roll: Quaternion = field(default_factory=Quaternion)
    #: Turns per bone, about its head, in rest axes.
    turns: dict[str, Quaternion] = field(default_factory=dict)
    #: Paw targets per leg ('fore.L', 'hind.R', ...), in the armature's space.
    paws: dict[str, Paw] = field(default_factory=dict)

    def add(self, bone: str, q: Quaternion) -> None:
        self.turns[bone] = q @ self.turns.get(bone, Quaternion())


LEGS = {
    "fore": ("upperarm", "forearm", "forepaw", "foretoe", -1.0),
    "hind": ("thigh", "shin", "hindpaw", "hindtoe", 1.0),
}


class Rig:
    def __init__(self, armature: bpy.types.Object, body: Body) -> None:
        self.armature = armature
        self.rest = {b.name: b.matrix_local.copy() for b in armature.data.bones}
        self.parent = {b.name: (b.parent.name if b.parent else None) for b in armature.data.bones}
        self.order = [b.name for b in armature.data.bones]
        # Parents before children.
        done: list[str] = []
        while len(done) < len(self.order):
            for n in self.order:
                if n not in done and (self.parent[n] is None or self.parent[n] in done):
                    done.append(n)
        self.order = done
        self.head = {b.name: Vector(b.head) for b in body.bones}
        self.tail = {b.name: Vector(b.tail) for b in body.bones}
        #: The tail's bones, root first (tail1, tail2, ...).
        self.tails = sorted((n for n in self.order if n.startswith("tail")), key=lambda n: int(n[4:]))
        for pb in armature.pose.bones:
            pb.rotation_mode = "QUATERNION"
        self._last: dict[str, Quaternion] = {}

    def neutral_paw(self, leg: str) -> Paw:
        side = leg[-1]
        _, _, meta, toe, _ = LEGS[leg[:-2]]
        ball = self.head[f"{toe}.{side}"].copy()
        d = self.head[f"{toe}.{side}"] - self.head[f"{meta}.{side}"]
        slope = math.atan2(d.y, -d.z)
        return Paw(ball, slope)

    def length(self, bone: str) -> float:
        return (self.tail[bone] - self.head[bone]).length

    def _frame(self, direction: Vector, lateral: Vector) -> Matrix:
        y = direction.normalized()
        x = (lateral - y * lateral.dot(y)).normalized()
        z = x.cross(y)
        return Matrix((x, y, z)).transposed()

    def _aim(self, bone: str, head: Vector, tail: Vector, lateral: Vector) -> Matrix:
        """The rigid motion taking `bone` from its rest place to run from `head` to `tail`, its sideways axis kept along `lateral`."""
        h0, t0 = self.head[bone], self.tail[bone]
        rot = self._frame(tail - head, lateral) @ self._frame(t0 - h0, Vector(X)).transposed()
        return Matrix.Translation(head) @ rot.to_4x4() @ Matrix.Translation(-h0)

    def solve(self, pose: Pose) -> dict[str, Matrix]:
        """Each bone's motion (armature space, of the rest skeleton)."""
        motion: dict[str, Matrix] = {}
        legs = {}
        for key in pose.paws:
            kind, side = key[:-2], key[-1]
            upper, lower, meta, toe, bend = LEGS[kind]
            for n in (upper, lower, meta, toe):
                legs[f"{n}.{side}"] = key
        for n in self.order:
            if n in legs:
                continue
            p = self.parent[n]
            base = motion[p] if p else Matrix.Identity(4)
            q = pose.turns.get(n, Quaternion())
            h = self.head[n]
            local = Matrix.Translation(h) @ q.to_matrix().to_4x4() @ Matrix.Translation(-h)
            if p is None:
                local = Matrix.Translation(pose.lift) @ pose.roll.to_matrix().to_4x4() @ local
            motion[n] = base @ local
        for key, paw in pose.paws.items():
            self._leg(key, paw, motion)
        # Children of solved legs (none today) would follow here.
        return motion

    def _leg(self, key: str, paw: Paw, motion: dict[str, Matrix]) -> None:
        kind, side = key[:-2], key[-1]
        upper, lower, meta, toe, bend = LEGS[kind]
        u, lo, m, t = (f"{upper}.{side}", f"{lower}.{side}", f"{meta}.{side}", f"{toe}.{side}")
        base = motion[self.parent[u]]
        lateral = (base.to_3x3() @ Vector(X)).normalized()
        forward = (base.to_3x3() @ Vector(Y)).normalized()
        top = base @ self.head[u]
        a, b, c = self.length(u), self.length(lo), self.length(m)
        # The joint above the paw (hock or wrist), up the slope from the ball.
        joint = paw.ball + Vector((0.0, -math.sin(paw.slope), math.cos(paw.slope))) * c
        to = joint - top
        d = min(max(to.length, abs(a - b) + 1e-4), a + b - 1e-4)
        axis = to.normalized()
        joint = top + axis * d
        # Bend: the stifle forward, the elbow back, in the leg's plane.
        side_v = axis.cross(lateral).normalized()
        if side_v.dot(forward) * bend < 0:
            side_v = -side_v
        cos_a = (a * a + d * d - b * b) / (2 * a * d)
        knee = top + axis * (a * cos_a) + side_v * (a * math.sqrt(max(0.0, 1 - cos_a * cos_a)))
        ball = joint + (paw.ball - joint).normalized() * c
        tip_dir = Vector((0.0, math.cos(paw.curl), -math.sin(paw.curl)))
        tip = ball + tip_dir * self.length(t)
        motion[u] = self._aim(u, top, knee, lateral)
        motion[lo] = self._aim(lo, knee, joint, lateral)
        motion[m] = self._aim(m, joint, ball, lateral)
        motion[t] = self._aim(t, ball, tip, lateral)

    def key(self, pose: Pose, frame: int) -> None:
        """Write the pose as local transforms and key every bone at `frame`."""
        motion = self.solve(pose)
        for pb in self.armature.pose.bones:
            n = pb.name
            r = self.rest[n]
            p = self.parent[n]
            m = motion[n] if p is None else motion[p].inverted() @ motion[n]
            basis = r.inverted() @ m @ r
            loc, rot, _ = basis.decompose()
            last = self._last.get(n)
            if last is not None and last.dot(rot) < 0:
                rot = -rot
            self._last[n] = rot
            pb.location = loc
            pb.rotation_quaternion = rot
            pb.keyframe_insert("location", frame=frame)
            pb.keyframe_insert("rotation_quaternion", frame=frame)
