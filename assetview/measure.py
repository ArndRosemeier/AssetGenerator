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
        "coplanar_overlap": _coplanar_overlap(p, t, islands),
    }


COPLANAR = 0.0005  # metres: faces this close in one plane, facing the same way, flicker (z-fight)
COPLANAR_MIN_AREA = 1e-5  # m², 10 mm²: less does not show


def _coplanar_overlap(p: np.ndarray, t: np.ndarray, islands: np.ndarray) -> dict[str, object] | None:
    """Faces of different parts that lie in one plane, face the same way and overlap: the
    renderer cannot tell which is in front, so the overlap flickers (z-fighting). A plank laid
    flush in a frame, a trim plate on a wall at the wall's own depth. The total overlap, where
    the largest is, and the triangles involved (the sheet marks them)."""
    if len(t) < 2:
        return None
    a, b, c = p[t[:, 0]], p[t[:, 1]], p[t[:, 2]]
    cross = np.cross(b - a, c - a)
    twice = np.linalg.norm(cross, axis=1)
    n = cross / np.maximum(twice, 1e-30)[:, None]
    # Faces lying on the ground, facing down, are never seen: they cannot flicker.
    on_ground = (n[:, 2] < -0.99) & (
        np.maximum(np.maximum(a[:, 2], b[:, 2]), c[:, 2]) <= p[:, 2].min() + COPLANAR
    )
    keep = np.nonzero((twice > 1e-10) & ~on_ground)[0]
    d = (n * a).sum(axis=1)
    lo, hi = np.minimum(np.minimum(a, b), c), np.maximum(np.maximum(a, b), c)
    # Group by direction (coarse bins), then sweep each group along the plane offset.
    direction = np.round(n[keep] * 20.0).astype(np.int64)
    _, group = np.unique(direction, axis=0, return_inverse=True)
    group = group.reshape(-1)
    order = keep[np.lexsort((d[keep], group))]
    g_of = np.empty(len(t), dtype=np.int64)
    g_of[keep] = group
    pairs: list[tuple[int, int]] = []
    for k in range(len(order)):
        i = order[k]
        for m in range(k + 1, len(order)):
            j = order[m]
            if g_of[j] != g_of[i] or d[j] - d[i] > COPLANAR:
                break
            if islands[i] == islands[j] or (n[i] * n[j]).sum() < 0.9998:
                continue
            if (lo[i] > hi[j] + COPLANAR).any() or (lo[j] > hi[i] + COPLANAR).any():
                continue
            pairs.append((int(i), int(j)))
        if len(pairs) > 50_000:
            break
    total, best, best_at, tris = 0.0, 0.0, None, set()
    for i, j in pairs:
        area = _overlap_area(p[t[i]], p[t[j]], n[i])
        if area <= 0.0:
            continue
        total += area
        tris.update((i, j))
        if area > best:
            best, best_at = area, (p[t[i]].mean(axis=0) + p[t[j]].mean(axis=0)) / 2.0
    if total < COPLANAR_MIN_AREA:
        return None
    return {"area_m2": round(total, 6), "at": _round(best_at), "triangles": sorted(tris)}


def _overlap_area(tri_a: np.ndarray, tri_b: np.ndarray, normal: np.ndarray) -> float:
    """Area shared by two triangles in (about) one plane: clip one by the other, in the plane."""
    helper = np.array([1.0, 0.0, 0.0]) if abs(normal[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
    u = np.cross(normal, helper)
    u /= np.linalg.norm(u)
    v = np.cross(normal, u)
    pa = [(float(q @ u), float(q @ v)) for q in tri_a]
    pb = [(float(q @ u), float(q @ v)) for q in tri_b]

    def signed(poly: list[tuple[float, float]]) -> float:
        return 0.5 * sum(
            x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(poly, poly[1:] + poly[:1], strict=False)
        )

    if signed(pb) < 0:
        pb.reverse()
    out = pa
    for (x0, y0), (x1, y1) in zip(pb, pb[1:] + pb[:1], strict=False):
        if not out:
            break

        def side(
            q: tuple[float, float], x0: float = x0, y0: float = y0, x1: float = x1, y1: float = y1
        ) -> float:
            return (x1 - x0) * (q[1] - y0) - (y1 - y0) * (q[0] - x0)

        clipped: list[tuple[float, float]] = []
        for s, e in zip(out, out[1:] + out[:1], strict=False):
            ss, se = side(s), side(e)
            if se >= 0:
                if ss < 0:
                    f = ss / (ss - se)
                    clipped.append((s[0] + f * (e[0] - s[0]), s[1] + f * (e[1] - s[1])))
                clipped.append(e)
            elif ss >= 0:
                f = ss / (ss - se)
                clipped.append((s[0] + f * (e[0] - s[0]), s[1] + f * (e[1] - s[1])))
        out = clipped
    return abs(signed(out)) if len(out) >= 3 else 0.0


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
    overlap = report.get("coplanar_overlap")
    if overlap:
        x, y, z = overlap["at"]  # type: ignore[index]
        # Faces of two parts in one plane, facing the same way: they flicker where they overlap.
        flags.append(f"z-fighting {overlap['area_m2'] * 1e4:.1f} cm2 at ({x:.2f}, {y:.2f}, {z:.2f})")  # type: ignore[index]
    lines.append(", ".join(flags))
    return lines
