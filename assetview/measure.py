"""Numbers about an asset that a picture shows badly: holes, loose pieces, balance.

Every finding is a measurement with its value, never a verdict on whether the asset
is good: a hanging chain has no footing on purpose, a floating rune may be meant.
"""

from __future__ import annotations

from collections import Counter

import numpy as np

from assetview.model import ViewModel

CONTACT = 0.002  # metres: parts closer than this touch
FOOTING = 0.005  # metres above the lowest point that still count as standing on the ground ...
FOOTING_SHARE = 0.01  # ... or this share of the height, if more (a 2 cm gap under a house is still standing)


def measure(model: ViewModel) -> dict[str, object]:
    p, t = model.positions, model.triangles
    lower, upper = p.min(axis=0), p.max(axis=0)
    islands = model.islands()
    count = int(islands.max()) + 1 if len(islands) else 0

    edges = Counter()
    for a, b, c in t:
        for u, v in ((a, b), (b, c), (c, a)):
            edges[(min(u, v), max(u, v))] += 1
    holes = sum(1 for n in edges.values() if n == 1)

    a, b, c = p[t[:, 0]], p[t[:, 1]], p[t[:, 2]]
    tetra = np.einsum("ij,ij->i", a, np.cross(b, c)) / 6.0  # signed volume against the origin
    tetra_centre = (a + b + c) / 4.0

    parts = []
    for i in range(count):
        mask = islands == i
        verts = p[np.unique(t[mask])]
        volume = float(tetra[mask].sum())
        centre = (
            (tetra_centre[mask] * tetra[mask][:, None]).sum(axis=0) / volume if abs(volume) > 1e-12 else None
        )
        parts.append(
            {
                "triangles": int(mask.sum()),
                "lower": verts.min(axis=0),
                "upper": verts.max(axis=0),
                "volume": volume,
                "centre": centre,
            }
        )

    footing = max(FOOTING, FOOTING_SHARE * float(upper[2] - lower[2]))
    floating = _floating(parts, float(lower[2]), footing)
    inverted = sum(1 for part in parts if part["volume"] < -1e-12)

    per_slot = {}
    for s, name in enumerate(model.slots):
        mask = model.tri_slot == s
        if mask.any():
            verts = p[np.unique(t[mask])]
            per_slot[name] = {
                "triangles": int(mask.sum()),
                "size_m": _round(verts.max(axis=0) - verts.min(axis=0)),
            }

    return {
        "source": model.source,
        "size_m": _round(upper - lower),
        "base_z": round(float(lower[2]), 4),
        "footprint_centre": _round((lower[:2] + upper[:2]) / 2),
        "triangles": int(len(t)),
        "materials": per_slot,
        "parts": count,
        "floating_parts": [
            {
                "triangles": parts[i]["triangles"],
                "lower": _round(parts[i]["lower"]),
                "upper": _round(parts[i]["upper"]),
            }
            for i in floating
        ],
        "open_edges": holes,
        "inverted_parts": inverted,
        "balance": _balance(parts, p, float(lower[2]), footing),
    }


def _floating(parts: list[dict], ground: float, tolerance: float) -> list[int]:
    """Parts not connected to the ground through a chain of touching parts (by bounds)."""
    n = len(parts)
    grounded = [part["lower"][2] <= ground + tolerance for part in parts]
    touching = [[] for _ in range(n)]
    for i in range(n):
        for j in range(i + 1, n):
            if np.all(parts[i]["lower"] <= parts[j]["upper"] + CONTACT) and np.all(
                parts[j]["lower"] <= parts[i]["upper"] + CONTACT
            ):
                touching[i].append(j)
                touching[j].append(i)
    reached = set(i for i in range(n) if grounded[i])
    stack = list(reached)
    while stack:
        i = stack.pop()
        for j in touching[i]:
            if j not in reached:
                reached.add(j)
                stack.append(j)
    return [i for i in range(n) if i not in reached]


def _balance(parts: list[dict], points: np.ndarray, ground: float, tolerance: float) -> dict[str, object]:
    """Does it stand? Centre of mass (closed parts, uniform density) against the hull of its footing:
    the points within `tolerance` of the lowest one."""
    solid = [part for part in parts if part["centre"] is not None and part["volume"] > 0]
    footing = points[points[:, 2] <= ground + tolerance][:, :2]
    if not solid:
        return {"verdict": "unknown: no closed part to weigh"}
    total = sum(part["volume"] for part in solid)
    centre = sum(part["centre"] * part["volume"] for part in solid) / total
    hull = _hull(footing)
    if len(hull) < 3:
        return {"verdict": "no flat footing (rests on a point or an edge)", "centre_of_mass": _round(centre)}
    margin = _inside_margin(centre[:2], hull)
    span = np.ptp(points[:, :2], axis=0)
    return {
        "verdict": "stands" if margin >= 0 else "tips over",
        "centre_of_mass": _round(centre),
        "margin_m": round(float(margin), 4),
        # How much of the footprint the footing spans: small when the asset rests on one corner or
        # one piece (walls that stop short of the ground leave only the doorstep).
        "footing_share": round(float(_area(hull) / max(span[0] * span[1], 1e-12)), 3),
    }


def _area(hull: np.ndarray) -> float:
    x, y = hull[:, 0], hull[:, 1]
    return 0.5 * abs(float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1))))


def _hull(points: np.ndarray) -> np.ndarray:
    """Convex hull, counter-clockwise (monotone chain)."""
    pts = sorted(set(map(tuple, np.round(points, 6))))
    if len(pts) < 3:
        return np.asarray(pts)

    def cross(o: tuple, a: tuple, b: tuple) -> float:
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower: list[tuple] = []
    for q in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], q) <= 0:
            lower.pop()
        lower.append(q)
    upper: list[tuple] = []
    for q in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], q) <= 0:
            upper.pop()
        upper.append(q)
    return np.asarray(lower[:-1] + upper[:-1])


def _inside_margin(point: np.ndarray, hull: np.ndarray) -> float:
    """Distance from `point` to the hull's edge: positive inside, negative outside."""
    best = np.inf
    inside = True
    for i in range(len(hull)):
        a, b = hull[i], hull[(i + 1) % len(hull)]
        edge = b - a
        length = np.linalg.norm(edge)
        if length < 1e-12:
            continue
        side = (edge[0] * (point[1] - a[1]) - edge[1] * (point[0] - a[0])) / length
        if side < 0:
            inside = False
        t = np.clip(np.dot(point - a, edge) / length**2, 0.0, 1.0)
        best = min(best, float(np.linalg.norm(point - (a + t * edge))))
    return best if inside else -best


def _round(values: np.ndarray) -> list[float]:
    return [round(float(v), 4) for v in values]


def summary(report: dict[str, object]) -> list[str]:
    """The report as a few short lines, for the console and the sheet's header."""
    w, d, h = report["size_m"]  # type: ignore[misc]
    lines = [
        f"size {w:.3f} x {d:.3f} x {h:.3f} m (w x d x h), {report['triangles']} tris, {report['parts']} parts"
    ]
    flags = []
    if report["floating_parts"]:
        flags.append(f"{len(report['floating_parts'])} floating part(s)")  # type: ignore[arg-type]
    if report["open_edges"]:
        flags.append(f"{report['open_edges']} open edge(s)")
    if report["inverted_parts"]:
        flags.append(f"{report['inverted_parts']} inside-out part(s)")
    balance = report["balance"]
    verdict = balance["verdict"]  # type: ignore[index]
    if verdict in ("stands", "tips over"):
        margin = abs(balance["margin_m"]) * 100  # type: ignore[index]
        where = "inside" if verdict == "stands" else "outside"
        share = balance["footing_share"] * 100  # type: ignore[index]
        flags.append(
            f"{verdict} (centre of mass {margin:.1f} cm {where} its footing, {share:.0f}% of footprint)"
        )
    else:
        flags.append(str(verdict))
    lines.append(", ".join(flags))
    return lines
