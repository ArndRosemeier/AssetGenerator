"""Skeletons, poses, skin weights and clips as plain data.

The one idea that makes this simple: a pose is a **rigid motion of the rest skeleton per bone**,
in the asset's own space (metres, Z up, front -Y). Moving a vertex is then just
`sum(weight * motion(vertex))` (linear blend skinning), the same sum Blender's armature
modifier computes, and the Blender backend turns each motion into the bone's local transform
from Blender's own rest matrices. Bone roll and per-version bone conventions never reach a
generator.

Turns are given in the rest pose's own axes, about the bone's head, after its parent has moved:

    pitch  about X: a creature's nose, or a limb's far end, up/forward (+)
    yaw    about Z: towards the creature's left, +X (+)
    roll   about Y: its right side (-X) down (+)

Bones named `*.L` sit on the +X side (the creature's left); `Skeleton.with_twins` adds the
mirrored `*.R` bone for each.

Plain Python floats in all pose maths, so a clip is the same bit for bit everywhere.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field

Vec = tuple[float, float, float]
Quat = tuple[float, float, float, float]  # w, x, y, z

IDENTITY: Quat = (1.0, 0.0, 0.0, 0.0)
ZERO: Vec = (0.0, 0.0, 0.0)


# --------------------------------------------------------------------------------------------
# Small vector and quaternion maths (plain floats: deterministic)
# --------------------------------------------------------------------------------------------


def add(a: Vec, b: Vec) -> Vec:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def sub(a: Vec, b: Vec) -> Vec:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def scale(a: Vec, s: float) -> Vec:
    return (a[0] * s, a[1] * s, a[2] * s)


def dot(a: Vec, b: Vec) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def cross(a: Vec, b: Vec) -> Vec:
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def length(a: Vec) -> float:
    return math.sqrt(dot(a, a))


def unit(a: Vec) -> Vec:
    n = length(a)
    if n < 1e-12:
        raise ValueError("cannot normalise a zero vector")
    return scale(a, 1.0 / n)


def mirror(v: Vec) -> Vec:
    return (-v[0], v[1], v[2])


def q_mul(a: Quat, b: Quat) -> Quat:
    aw, ax, ay, az = a
    bw, bx, by, bz = b
    return (
        aw * bw - ax * bx - ay * by - az * bz,
        aw * bx + ax * bw + ay * bz - az * by,
        aw * by - ax * bz + ay * bw + az * bx,
        aw * bz + ax * by - ay * bx + az * bw,
    )


def q_conj(q: Quat) -> Quat:
    return (q[0], -q[1], -q[2], -q[3])


def q_axis(axis: Vec, angle: float) -> Quat:
    x, y, z = unit(axis)
    s = math.sin(angle / 2)
    return (math.cos(angle / 2), x * s, y * s, z * s)


def q_rotate(q: Quat, v: Vec) -> Vec:
    w, x, y, z = q
    # v + 2w(q x v) + 2 q x (q x v), with q the vector part
    tx, ty, tz = 2 * (y * v[2] - z * v[1]), 2 * (z * v[0] - x * v[2]), 2 * (x * v[1] - y * v[0])
    return (
        v[0] + w * tx + (y * tz - z * ty),
        v[1] + w * ty + (z * tx - x * tz),
        v[2] + w * tz + (x * ty - y * tx),
    )


def q_from_matrix(m: Sequence[Sequence[float]]) -> Quat:
    """A rotation matrix (rows) as a unit quaternion."""
    trace = m[0][0] + m[1][1] + m[2][2]
    if trace > 0:
        s = math.sqrt(trace + 1.0) * 2
        q = (0.25 * s, (m[2][1] - m[1][2]) / s, (m[0][2] - m[2][0]) / s, (m[1][0] - m[0][1]) / s)
    elif m[0][0] > m[1][1] and m[0][0] > m[2][2]:
        s = math.sqrt(1.0 + m[0][0] - m[1][1] - m[2][2]) * 2
        q = ((m[2][1] - m[1][2]) / s, 0.25 * s, (m[0][1] + m[1][0]) / s, (m[0][2] + m[2][0]) / s)
    elif m[1][1] > m[2][2]:
        s = math.sqrt(1.0 + m[1][1] - m[0][0] - m[2][2]) * 2
        q = ((m[0][2] - m[2][0]) / s, (m[0][1] + m[1][0]) / s, 0.25 * s, (m[1][2] + m[2][1]) / s)
    else:
        s = math.sqrt(1.0 + m[2][2] - m[0][0] - m[1][1]) * 2
        q = ((m[1][0] - m[0][1]) / s, (m[0][2] + m[2][0]) / s, (m[1][2] + m[2][1]) / s, 0.25 * s)
    n = math.sqrt(sum(c * c for c in q))
    return (q[0] / n, q[1] / n, q[2] / n, q[3] / n)


def q_matrix(q: Quat) -> tuple[Vec, Vec, Vec]:
    w, x, y, z = q
    return (
        (1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)),
        (2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)),
        (2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)),
    )


def turn(pitch: float = 0.0, yaw: float = 0.0, roll: float = 0.0) -> Quat:
    """A turn in degrees, in the rest pose's axes: roll first, then pitch, then yaw."""
    q = IDENTITY
    if roll:
        q = q_mul(q_axis((0.0, 1.0, 0.0), -math.radians(roll)), q)
    if pitch:
        q = q_mul(q_axis((1.0, 0.0, 0.0), -math.radians(pitch)), q)
    if yaw:
        q = q_mul(q_axis((0.0, 0.0, 1.0), math.radians(yaw)), q)
    return q


# --------------------------------------------------------------------------------------------
# Skeleton and motions
# --------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Bone:
    name: str
    head: Vec
    tail: Vec
    parent: str | None = None

    @property
    def length(self) -> float:
        return length(sub(self.tail, self.head))


def twin_name(name: str) -> str | None:
    """'ear.L' -> 'ear.R' (and back); None for a bone on the middle line."""
    if name.endswith(".L"):
        return name[:-2] + ".R"
    if name.endswith(".R"):
        return name[:-2] + ".L"
    return None


class Skeleton:
    """Bones, parents before children. Validated: unique names, known parents, no cycles,
    no bone shorter than a millimetre."""

    def __init__(self, bones: Iterable[Bone]) -> None:
        given = list(bones)
        names = [b.name for b in given]
        if len(set(names)) != len(names):
            raise ValueError(f"bone names repeat: {sorted({n for n in names if names.count(n) > 1})}")
        by_name = {b.name: b for b in given}
        for b in given:
            if b.parent is not None and b.parent not in by_name:
                raise ValueError(f"bone '{b.name}': no parent bone '{b.parent}'")
            if b.length < 1e-3:
                raise ValueError(f"bone '{b.name}' is {b.length * 1000:.2f} mm long; bones need 1 mm or more")
        ordered: list[Bone] = []
        placed: set[str] = set()
        while len(ordered) < len(given):
            progress = False
            for b in given:
                if b.name not in placed and (b.parent is None or b.parent in placed):
                    ordered.append(b)
                    placed.add(b.name)
                    progress = True
            if not progress:
                stuck = sorted(set(names) - placed)
                raise ValueError(f"bones {stuck} are their own ancestors")
        self.bones: tuple[Bone, ...] = tuple(ordered)
        self.by_name: dict[str, Bone] = {b.name: b for b in ordered}
        self.names: tuple[str, ...] = tuple(b.name for b in ordered)

    def __contains__(self, name: str) -> bool:
        return name in self.by_name

    def __getitem__(self, name: str) -> Bone:
        if name not in self.by_name:
            raise KeyError(f"no bone '{name}'; bones are {list(self.names)}")
        return self.by_name[name]

    @staticmethod
    def with_twins(bones: Iterable[Bone]) -> Skeleton:
        """The bones plus, for every '*.L' bone, its mirror image '*.R' (its parent mirrored too
        when that is a '.L' bone). Model one side; get both."""
        given = list(bones)
        names = {b.name for b in given}
        out = list(given)
        for b in given:
            twin = twin_name(b.name)
            if b.name.endswith(".L") and twin not in names:
                parent = b.parent
                if parent is not None and parent.endswith(".L"):
                    parent = twin_name(parent)
                out.append(Bone(twin, mirror(b.head), mirror(b.tail), parent))
        return Skeleton(out)


@dataclass(frozen=True)
class Motion:
    """A rigid motion of the rest skeleton: x -> rotation(x) + translation, in asset space."""

    rotation: Quat = IDENTITY
    translation: Vec = ZERO

    def apply(self, point: Vec) -> Vec:
        return add(q_rotate(self.rotation, point), self.translation)

    def then(self, other: Motion) -> Motion:
        """`other` after `self`."""
        return Motion(
            q_mul(other.rotation, self.rotation),
            add(q_rotate(other.rotation, self.translation), other.translation),
        )

    @staticmethod
    def about(pivot: Vec, rotation: Quat) -> Motion:
        """Turn about `pivot`."""
        return Motion(rotation, sub(pivot, q_rotate(rotation, pivot)))


# --------------------------------------------------------------------------------------------
# Poses: turns, a lift, and legs put down where they should be
# --------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Leg:
    """A two-bone limb (`upper`, `lower`) whose far end is placed by inverse kinematics, and an
    optional `foot` kept level on the ground. The knee bends the way the rest pose bends it;
    for a leg modelled straight, `knee` says which way (asset axes, e.g. (0, -1, 0): forward)."""

    upper: str
    lower: str
    foot: str | None = None
    knee: Vec | None = None


@dataclass
class Pose:
    #: Per bone: a turn about its head, in rest axes, after its parent's motion.
    turns: dict[str, Quat] = field(default_factory=dict)
    #: Moves the whole skeleton (applied to every root bone): bob, sway, hop.
    lift: Vec = ZERO
    #: Per leg (keyed by its upper bone): where its far end (the lower bone's tail) goes, in asset space.
    reach: dict[str, Vec] = field(default_factory=dict)

    def add_turn(self, bone: str, q: Quat) -> None:
        self.turns[bone] = q_mul(q, self.turns.get(bone, IDENTITY))


def solve(skeleton: Skeleton, pose: Pose, legs: Mapping[str, Leg] | None = None) -> dict[str, Motion]:
    """Every bone's motion for `pose`. Legs in `pose.reach` are solved by two-bone IK."""
    legs = legs or {}
    motion: dict[str, Motion] = {}
    solved: set[str] = set()
    for bone in skeleton.bones:
        if bone.name in solved:
            continue
        if bone.name in pose.reach:
            leg = legs.get(bone.name)
            if leg is None:
                raise ValueError(f"pose reaches with '{bone.name}', which starts no leg")
            motion.update(_solve_leg(skeleton, leg, pose.reach[bone.name], motion, pose))
            solved.update(n for n in (leg.upper, leg.lower, leg.foot) if n)
            continue
        own = Motion.about(bone.head, pose.turns.get(bone.name, IDENTITY))
        if bone.parent is None:
            motion[bone.name] = own.then(Motion(IDENTITY, pose.lift))
        else:
            motion[bone.name] = own.then(motion[bone.parent])
    return motion


def _frame(direction: Vec, lateral: Vec) -> tuple[Vec, Vec, Vec]:
    """Columns x (lateral, made square to y), y (direction), z."""
    y = unit(direction)
    x = unit(sub(lateral, scale(y, dot(lateral, y))))
    z = cross(x, y)
    return x, y, z


def _aim(head0: Vec, tail0: Vec, lateral0: Vec, head: Vec, tail: Vec, lateral: Vec) -> Motion:
    """The rigid motion taking a bone from (head0, tail0) to (head, tail), its sideways axis
    from lateral0 to lateral."""
    a = _frame(sub(tail0, head0), lateral0)
    b = _frame(sub(tail, head), lateral)
    # R = B A^T, with A and B given by columns.
    rows = tuple(tuple(sum(b[k][i] * a[k][j] for k in range(3)) for j in range(3)) for i in range(3))
    rotation = q_from_matrix(rows)
    return Motion(rotation, sub(head, q_rotate(rotation, head0)))


def _solve_leg(
    skeleton: Skeleton, leg: Leg, target: Vec, motion: dict[str, Motion], pose: Pose
) -> dict[str, Motion]:
    upper, lower = skeleton[leg.upper], skeleton[leg.lower]
    if lower.parent != upper.name:
        raise ValueError(f"leg '{leg.upper}': '{leg.lower}' must be the child of '{leg.upper}'")
    base = motion[upper.parent] if upper.parent else Motion(IDENTITY, pose.lift)
    hip = base.apply(upper.head)
    a, b = upper.length, lower.length
    rest_hip, rest_knee, rest_ankle = upper.head, upper.tail, lower.tail
    # Which way the knee bends: the rest pose's bend, carried along by the parent.
    line = unit(sub(rest_ankle, rest_hip))
    bend0 = sub(sub(rest_knee, rest_hip), scale(line, dot(sub(rest_knee, rest_hip), line)))
    if length(bend0) < 1e-4 * (a + b):
        if leg.knee is None:
            raise ValueError(f"leg '{leg.upper}' is modelled straight: give it a `knee` direction")
        bend0 = leg.knee
    reach = sub(target, hip)
    distance = min(max(length(reach), abs(a - b) + 1e-6), a + b - 1e-6)
    axis = unit(reach) if length(reach) > 1e-9 else line
    bend = q_rotate(base.rotation, unit(bend0))
    side = sub(bend, scale(axis, dot(bend, axis)))
    side = unit(side) if length(side) > 1e-9 else unit(cross(axis, (1.0, 0.0, 0.0)))
    cos_a = max(-1.0, min(1.0, (a * a + distance * distance - b * b) / (2 * a * distance)))
    knee = add(hip, add(scale(axis, a * cos_a), scale(side, a * math.sqrt(1 - cos_a * cos_a))))
    ankle = add(hip, scale(axis, distance))
    # The leg's plane turns as a whole: its normal is the bones' sideways axis.
    normal0 = cross(sub(rest_knee, rest_hip), bend0)
    if length(normal0) < 1e-12:
        normal0 = cross(line, bend0)
    normal = cross(sub(knee, hip), side)
    out = {
        upper.name: _aim(rest_hip, rest_knee, normal0, hip, knee, normal),
        lower.name: _aim(lower.head, rest_ankle, normal0, knee, ankle, normal),
    }
    if leg.foot is not None:
        # Level on the ground as at rest, carried along by the ankle.
        out[leg.foot] = Motion(IDENTITY, sub(ankle, rest_ankle))
    return out


# --------------------------------------------------------------------------------------------
# Clips and skins
# --------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Clip:
    """A named animation: one `{bone: Motion}` per frame, for every bone. A loop's frames run
    from t = 0 up to (not including) 1; the backend closes it by repeating the first frame."""

    name: str
    fps: int
    loop: bool
    frames: tuple[dict[str, Motion], ...]

    @property
    def seconds(self) -> float:
        return len(self.frames) / self.fps if self.loop else (len(self.frames) - 1) / self.fps


@dataclass(frozen=True)
class Skin:
    """Per vertex, up to four (bone index, weight) pairs summing to 1. `bones` are names in
    the asset's skeleton."""

    bones: tuple[str, ...]
    indices: tuple[tuple[int, ...], ...]
    weights: tuple[tuple[float, ...], ...]

    def __post_init__(self) -> None:
        if len(self.indices) != len(self.weights):
            raise ValueError("skin indices and weights differ in length")
        for i, (idx, w) in enumerate(zip(self.indices, self.weights, strict=True)):
            if not idx or len(idx) != len(w) or len(idx) > 4:
                raise ValueError(f"vertex {i}: needs 1 to 4 influences, got {len(idx)}")
            if abs(sum(w) - 1.0) > 1e-6:
                raise ValueError(f"vertex {i}: weights sum to {sum(w)}, not 1")
