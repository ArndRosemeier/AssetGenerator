"""What every mushroom monster is made of: the mushroom's own shells (blender/lib/mushroom.py) on a stalk of
three bones under a cap bone, and whatever a species adds; each piece naming the bones it moves with."""

from __future__ import annotations

import math
from dataclasses import dataclass

from blender.generators.quadruped_generator.anatomy import Body
from blender.lib.mushroom import Mushroom, mushroom
from blender.lib.shells import Shell, Vec, lathe

#: The stalk's bones, foot to top; the cap's bone sits on the top.
STALK = ("stalk1", "stalk2", "stalk3")


@dataclass(frozen=True)
class Piece:
    shell: Shell
    slot: str
    #: The bones it moves with: one carries it rigidly; several share it by nearness (`soft`, metres).
    bones: tuple[str, ...]
    soft: float = 0.03


@dataclass(frozen=True)
class Plan:
    body: Body
    pieces: list[Piece]


def stalk_point(m: Mushroom, t: float) -> Vec:
    """The stalk's axis `t` of the way up (as mushroom() bends it), placed as the mushroom is."""
    x, z = m.lean * t * t, m.stalk_height * t
    c, s = math.cos(m.yaw), math.sin(m.yaw)
    return (m.at[0] + x * c, m.at[1] + x * s, m.at[2] + z)


def mushroom_body(m: Mushroom) -> tuple[Body, list[Piece]]:
    """The skeleton (`root` on the ground under the foot, the stalk, the cap) and the mushroom's pieces."""
    b = Body()
    h = m.stalk_height
    foot = stalk_point(m, 0.0)
    b.bone("root", (foot[0], foot[1], 0.0), (foot[0], foot[1] + 0.15 * h, 0.0), None)
    parent = "root"
    for i, name in enumerate(STALK):
        b.bone(name, stalk_point(m, i / 3), stalk_point(m, (i + 1) / 3), parent)
        parent = name
    # The cap tipped the way the stalk leans (as mushroom() tips it).
    top = stalk_point(m, 1.0)
    tip = min(math.atan2(2 * m.lean, h), 0.4)
    up = (math.sin(tip) * math.cos(m.yaw), math.sin(tip) * math.sin(m.yaw), math.cos(tip))
    b.bone("cap", top, tuple(top[i] + up[i] * m.cap_height for i in range(3)), "stalk3")

    pieces: list[Piece] = []
    for shell, slot in mushroom(m):
        if slot in ("cap", "gills", "spots"):
            pieces.append(Piece(shell, slot, ("cap",)))
        elif slot == "stalk":
            pieces.append(Piece(shell, slot, STALK, 0.06 * h))
        else:
            # The ring hangs from the upper stalk; the volva (also 'ring') cups the foot.
            z = sum(v[2] for v in shell[0]) / len(shell[0]) - m.at[2]
            pieces.append(Piece(shell, slot, ("stalk1",) if z < 0.3 * h else ("stalk3",)))
    return b, pieces


def ball(centre: Vec, r: float, segments: int = 10) -> Shell:
    """A sphere (an eye)."""
    rings = max(3, segments // 2)
    prof = [(0.0, -r)]
    prof += [(r * math.sin(math.pi * i / rings), -r * math.cos(math.pi * i / rings)) for i in range(1, rings)]
    prof.append((0.0, r))
    verts, faces = lathe(prof, segments)
    return [(x + centre[0], y + centre[1], z + centre[2]) for x, y, z in verts], faces
