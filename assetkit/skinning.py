"""Skin weights from a sculpt's own parts, and moving a mesh with them. Needs numpy.

A sculpted body knows which part every point of its surface lies on, so its weights need no
painting: each bone carries some parts, and a vertex belongs to the bones whose parts it lies
on. Its weight for a bone falls off with its distance to that bone's nearest part, over
`softness` metres, so a vertex on the shin is all shin, and one in the blend between thigh and
shin (where the shape itself blends) is shared. Limbs do not bleed into a torso they merely
come near, as distance-to-bone weights do: the distance is to the surface, not to the bone.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence

import numpy as np

from assetkit.rig import Clip, Motion, Skin, q_matrix
from assetkit.sdf import Shape

MAX_INFLUENCES = 4
CUTOFF = 0.01  # weights below this are dropped before normalising


def bind(
    points: np.ndarray,
    carriers: Mapping[str, Sequence[Shape]],
    softness: Mapping[str, float],
    default_softness: float,
    parents: Mapping[str, str | None] | None = None,
    faces: np.ndarray | None = None,
    smoothing: int = 4,
) -> Skin:
    """Weights for `points` from each bone's `carriers` (the shapes it carries).

    With the skeleton's `parents`, a vertex is shared only between bones that touch (a bone and
    its parent or child): weight it would give an unrelated bone (the head, near a shoulder; the
    other thigh, between the legs) goes to the bone that joins them, so two bones moving apart
    never tear the skin between them. With `faces`, weights are then smoothed over the surface
    `smoothing` times, spreading each joint's blend over a few vertices.
    """
    names = tuple(carriers)
    if not names:
        raise ValueError("bind: no bone carries a part")
    if parents is not None:
        # Every bone between a carrier and the root takes part, even one that carries nothing.
        chain = list(names)
        for name in names:
            p = parents.get(name)
            while p is not None and p not in chain:
                chain.append(p)
                p = parents.get(p)
        names = tuple(chain)
    distance = np.full((len(points), len(names)), np.inf)
    for j, name in enumerate(names):
        for shape in carriers.get(name, ()):
            distance[:, j] = np.minimum(distance[:, j], shape(points))
    soft = np.array([softness.get(n, default_softness) for n in names], dtype=np.float64)
    nearest = distance.min(axis=1, keepdims=True)
    exponent = -(distance - nearest) / soft[None, :]
    # math.exp, not np.exp: numpy's vectorised exp rounds differently between builds.
    weight = np.array([math.exp(x) if x > -700 else 0.0 for x in exponent.ravel()]).reshape(exponent.shape)
    if parents is not None:
        weight = _to_joining_bones(weight, names, parents)
    if faces is not None and smoothing > 0:
        weight = _smooth(weight, faces, smoothing)
    order = np.argsort(-weight, axis=1, kind="stable")[:, :MAX_INFLUENCES]
    indices: list[tuple[int, ...]] = []
    weights: list[tuple[float, ...]] = []
    for row, picks in zip(weight, order, strict=True):
        kept = [(int(j), float(row[j])) for j in picks if row[j] >= CUTOFF]
        total = math.fsum(w for _, w in kept)
        indices.append(tuple(j for j, _ in kept))
        normed = [w / total for _, w in kept]
        normed[-1] = 1.0 - math.fsum(normed[:-1])  # sum exactly 1
        weights.append(tuple(normed))
    return Skin(bones=names, indices=tuple(indices), weights=tuple(weights))


def _to_joining_bones(
    weight: np.ndarray, names: tuple[str, ...], parents: Mapping[str, str | None]
) -> np.ndarray:
    """Per vertex: weight on a bone that neither is nor touches the strongest bone moves to the
    nearest bone both hang from, and as much again from the strongest bone. Where two unrelated
    bones meet as equals (head and arm at a shoulder), the bone joining them takes over, so the
    skin runs head, body, arm instead of tearing between head and arm."""
    index = {n: i for i, n in enumerate(names)}

    def ancestors(name: str) -> list[str]:
        out = [name]
        while parents.get(out[-1]) is not None:
            out.append(parents[out[-1]])  # type: ignore[arg-type]
        return out

    lines = {n: ancestors(n) for n in names}
    out = weight.copy()
    strongest = np.argmax(weight, axis=1)
    for v in range(len(weight)):
        top = names[strongest[v]]
        near = {top, parents.get(top)} | {n for n in names if parents.get(n) == top}
        for j in np.nonzero(weight[v] > 0)[0]:
            other = names[j]
            if other in near:
                continue
            joint = next((a for a in lines[other] if a in lines[top]), None)
            if joint == other and parents.get(top) is not None:
                # `other` is a more distant ancestor (an arm's hips): the skin between them belongs
                # to the bone the limb hangs from (its chest).
                joint = parents[top]
            if joint is None or joint not in index:
                continue
            share = min(out[v, j], out[v, strongest[v]])
            out[v, index[joint]] += out[v, j] + share
            out[v, strongest[v]] -= share
            out[v, j] = 0.0
    return out


def _smooth(weight: np.ndarray, faces: np.ndarray, rounds: int) -> np.ndarray:
    """Average each vertex's weights with its neighbours', half and half, `rounds` times."""
    edges = np.concatenate([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]])
    edges = np.concatenate([edges, edges[:, ::-1]])
    count = np.bincount(edges[:, 0], minlength=len(weight)).astype(np.float64)
    for _ in range(rounds):
        total = np.zeros_like(weight)
        np.add.at(total, edges[:, 0], weight[edges[:, 1]])
        weight = 0.5 * weight + 0.5 * total / np.maximum(count, 1.0)[:, None]
    return weight


def shared_skin(
    skin: Skin, parents: Mapping[str, str | None], least: float = 0.15
) -> list[tuple[str, str, int]]:
    """Pairs of bones that do not touch in the hierarchy yet share vertices (each holding at least
    `least` of the weight), with how many: a limb fused to the body. Sculpted limbs within the
    smooth-union blend of the body (arms hanging against the flanks, legs against each other)
    are glued to it, and the glued skin tears when the limb moves. Model them apart."""

    def touching(a: str, b: str) -> bool:
        return parents.get(a) == b or parents.get(b) == a

    count: dict[tuple[str, str], int] = {}
    for idx, w in zip(skin.indices, skin.weights, strict=True):
        top = skin.bones[idx[max(range(len(w)), key=lambda k: w[k])]]
        for i, wi in zip(idx, w, strict=True):
            other = skin.bones[i]
            if other != top and wi >= least and not touching(top, other):
                pair = (min(top, other), max(top, other))
                count[pair] = count.get(pair, 0) + 1
    return sorted(((a, b, n) for (a, b), n in count.items() if n >= 3), key=lambda t: -t[2])


def dominant(skin: Skin) -> np.ndarray:
    """Per vertex, the index (into `skin.bones`) of its strongest bone."""
    return np.array([idx[int(np.argmax(w))] for idx, w in zip(skin.indices, skin.weights, strict=True)])


def deform(points: np.ndarray, skin: Skin, motions: Mapping[str, Motion]) -> np.ndarray:
    """Linear blend skinning: each vertex moved by its bones' motions, by weight. The same sum
    Blender's armature modifier computes, so this is what the shipped animation shows."""
    rotations = np.array([q_matrix(motions[b].rotation) for b in skin.bones])  # (B, 3, 3)
    translations = np.array([motions[b].translation for b in skin.bones])  # (B, 3)
    width = MAX_INFLUENCES
    idx = np.zeros((len(points), width), dtype=np.int64)
    wts = np.zeros((len(points), width))
    for i, (ii, ww) in enumerate(zip(skin.indices, skin.weights, strict=True)):
        idx[i, : len(ii)] = ii
        wts[i, : len(ww)] = ww
    moved = np.einsum("vkij,vj->vki", rotations[idx], points) + translations[idx]
    return (moved * wts[..., None]).sum(axis=1)


def clip_report(
    points: np.ndarray, faces: np.ndarray, skin: Skin, clip: Clip, ground: float
) -> dict[str, object]:
    """What can go wrong in a clip, measured over its frames: the body sinking through the floor,
    skin stretching or collapsing (bad weights, a joint bent too far), or nothing moving."""
    edges = np.unique(
        np.sort(np.concatenate([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]]), axis=1), axis=0
    )
    rest_len = np.linalg.norm(points[edges[:, 0]] - points[edges[:, 1]], axis=1)
    # Only edges of ordinary length: a sliver edge (a paint border cut) swings wildly in ratio
    # while moving a fraction of a millimetre.
    keep = rest_len >= 0.5 * np.median(rest_len)
    edges, rest_len = edges[keep], rest_len[keep]
    lowest = math.inf
    stretch_max, stretch_min, moved, strained = 1.0, 1.0, 0.0, 0
    worst_edges: dict[int, float] = {}  # edge index -> how far past the limits it went
    for frame in clip.frames:
        p = deform(points, skin, frame)
        lowest = min(lowest, float(p[:, 2].min()))
        ratio = np.linalg.norm(p[edges[:, 0]] - p[edges[:, 1]], axis=1) / rest_len
        stretch_max = max(stretch_max, float(ratio.max()))
        stretch_min = min(stretch_min, float(ratio.min()))
        bad = (ratio > 2.0) | (ratio < 0.25)
        strained = max(strained, int(((ratio > 1.5) | (ratio < 0.5)).sum()))
        for e in np.nonzero(bad)[0]:
            excess = float(max(ratio[e] / 2.0, 0.25 / ratio[e]))
            worst_edges[int(e)] = max(worst_edges.get(int(e), 0.0), excess)
        moved = max(moved, float(np.linalg.norm(p - points, axis=1).max()))
    # Where it tears or folds: the bones the worst edges' ends belong to, most affected first.
    top = dominant(skin)
    at: dict[str, int] = {}
    for e in worst_edges:
        for v in edges[e]:
            name = skin.bones[top[v]]
            at[name] = at.get(name, 0) + 1
    where = [name for name, _ in sorted(at.items(), key=lambda kv: -kv[1])[:3]]
    return {
        "clip": clip.name,
        "seconds": round(clip.seconds, 3),
        "loop": clip.loop,
        "frames": len(clip.frames),
        "sinks_m": round(max(0.0, ground - lowest), 4),
        "stretch_max": round(stretch_max, 3),
        "stretch_min": round(stretch_min, 3),
        # Edges beyond 1.5x or under 0.5x in the worst frame: a few at a bent joint are normal.
        "strained_edges": strained,
        "edges": int(len(edges)),
        "moves_m": round(moved, 4),
        "where": where,
    }


def clip_flags(report: Mapping[str, object]) -> list[str]:
    """The measurements of `clip_report` worth an agent's attention, in words.

    Some stretch at a bending joint is how skinning works (the outside of a bent knee stretches,
    the inside creases); past 2x the skin tears visibly, under 0.25x it folds through itself.
    """
    flags = []
    if report["moves_m"] < 1e-3:  # type: ignore[operator]
        flags.append("nothing moves")
    if report["sinks_m"] > 0.005:  # type: ignore[operator]
        flags.append(f"sinks {report['sinks_m'] * 100:.1f} cm into the ground")  # type: ignore[operator]
    at = f" at {'/'.join(report['where'])}" if report.get("where") else ""  # type: ignore[arg-type]
    if report["stretch_max"] > 2.0:  # type: ignore[operator]
        flags.append(f"skin tears: stretches to {report['stretch_max']:.1f}x{at}")
    if report["stretch_min"] < 0.25:  # type: ignore[operator]
        flags.append(f"skin folds: collapses to {report['stretch_min']:.2f}x{at}")
    if report["strained_edges"] > 0.05 * report["edges"]:  # type: ignore[operator]
        flags.append(f"{report['strained_edges']} edges strained (weights too hard?)")
    return flags
