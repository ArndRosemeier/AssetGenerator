# -*- coding: utf-8 -*-
"""Pure visibility math for the orc stills. No bpy, no Blender.

``bake_human_orc`` supplies camera parameters and world-space points; this
module answers the only question the Art Reviewer actually asks of a still:
**are the tusks visible in it?**

Why this exists
---------------
f4d2059 baked EXIT 0 with every numeric gate passed, and the review was:

    Punch: tusks not readable on this still
    Death: tusks not readable on this still

Both are correct renders of correct geometry. On Punch the character's own
guard hand is in front of his mouth; on Death the overhead camera sees the top
of a supine head and the face points away. No amount of tusk-placement gating
can fix a still whose camera cannot see the mouth, so the camera has to be
chosen by measuring visibility rather than by a fixed offset — and a still that
cannot show the tusks has to fail loudly instead of shipping.

Two measurements, both here:

* **Screen footprint.** Perspective projection for a Blender camera, so the
  tusk cluster's height in pixels is a number rather than a hope. For scale:
  the body still frames a 1.8 m figure from ~5 m on a 50 mm lens at 640x800,
  about 4.4 mm per pixel.
* **Occlusion.** Whether other geometry sits between the camera and each tusk
  vertex. This is what catches the guard hand.

Run ``python tools/orc_still_visibility.py`` for the self-test.
"""
from __future__ import annotations

import math

Vec3 = tuple[float, float, float]


def sub(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def add(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def mul(a: Vec3, s: float) -> Vec3:
    return (a[0] * s, a[1] * s, a[2] * s)


def dot(a: Vec3, b: Vec3) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def length(a: Vec3) -> float:
    return math.sqrt(dot(a, a))


def normalise(a: Vec3) -> Vec3:
    n = length(a)
    if n <= 0.0:
        raise ValueError("cannot normalise a zero vector")
    return (a[0] / n, a[1] / n, a[2] / n)


def cross(a: Vec3, b: Vec3) -> Vec3:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def sensor_extent(
    sensor_width: float, sensor_height: float, res_x: int, res_y: int, fit: str
) -> tuple[float, float]:
    """Effective sensor size in mm for Blender's sensor-fit modes.

    ``AUTO`` gives ``sensor_width`` to whichever image dimension is larger,
    which is why a 720x720 frame and a 640x800 frame with the same lens do not
    have the same horizontal field of view.
    """
    if res_x <= 0 or res_y <= 0:
        raise ValueError(f"bad resolution {res_x}x{res_y}")
    if fit == "AUTO":
        if res_x >= res_y:
            return sensor_width, sensor_width * res_y / res_x
        return sensor_width * res_x / res_y, sensor_width
    if fit == "HORIZONTAL":
        return sensor_width, sensor_width * res_y / res_x
    if fit == "VERTICAL":
        return sensor_height * res_x / res_y, sensor_height
    raise ValueError(f"unknown sensor fit {fit!r}")


def project_camera_space(
    p_cam: Vec3,
    *,
    lens: float,
    sensor_x: float,
    sensor_y: float,
    res_x: int,
    res_y: int,
) -> tuple[float, float, float, bool] | None:
    """Project a camera-space point to pixels. ``None`` when behind the camera.

    Blender cameras look down local ``-Z``, so depth is ``-p_cam.z``. Returns
    ``(px, py, depth, in_frame)`` with pixel origin at the bottom-left.
    """
    depth = -p_cam[2]
    if depth <= 1e-9:
        return None
    half_x = depth * (sensor_x * 0.5) / lens
    half_y = depth * (sensor_y * 0.5) / lens
    u = p_cam[0] / half_x
    v = p_cam[1] / half_y
    px = (u * 0.5 + 0.5) * res_x
    py = (v * 0.5 + 0.5) * res_y
    in_frame = -1.0 <= u <= 1.0 and -1.0 <= v <= 1.0
    return px, py, depth, in_frame


def world_to_camera_space(p: Vec3, cam_origin: Vec3, basis: tuple[Vec3, Vec3, Vec3]) -> Vec3:
    """Express a world point in camera space given the camera's world basis.

    ``basis`` is ``(right, up, back)``: the camera's local +X, +Y and +Z in
    world space, matching Blender's convention that the view direction is
    ``-Z``.
    """
    rel = sub(p, cam_origin)
    right, up, back = basis
    return (dot(rel, right), dot(rel, up), dot(rel, back))


def camera_basis(cam_origin: Vec3, look_at: Vec3, up_hint: Vec3) -> tuple[Vec3, Vec3, Vec3]:
    """Right/up/back basis for a camera at ``cam_origin`` aimed at ``look_at``."""
    back = normalise(sub(cam_origin, look_at))
    right = cross(up_hint, back)
    if length(right) < 1e-9:
        # up_hint is parallel to the view axis; pick any perpendicular.
        fallback = (1.0, 0.0, 0.0) if abs(back[0]) < 0.9 else (0.0, 1.0, 0.0)
        right = cross(fallback, back)
    right = normalise(right)
    up = normalise(cross(back, right))
    return right, up, back


Triangle = tuple[Vec3, Vec3, Vec3]


def ray_triangle_distance(origin: Vec3, d: Vec3, tri: Triangle, eps: float = 1e-12) -> float | None:
    """Möller-Trumbore: distance along unit ``d`` to ``tri``, or ``None``."""
    v0, v1, v2 = tri
    e1 = sub(v1, v0)
    e2 = sub(v2, v0)
    h = cross(d, e2)
    a = dot(e1, h)
    if -eps < a < eps:
        return None  # ray parallel to the triangle plane
    f = 1.0 / a
    s = sub(origin, v0)
    u = f * dot(s, h)
    if u < 0.0 or u > 1.0:
        return None
    q = cross(s, e1)
    v = f * dot(d, q)
    if v < 0.0 or u + v > 1.0:
        return None
    t = f * dot(e2, q)
    if t <= 0.0:
        return None
    return t


def is_occluded(
    cam_origin: Vec3,
    target: Vec3,
    occluders: list[Triangle],
    *,
    near_eps: float = 0.004,
    far_eps: float = 0.004,
) -> bool:
    """True when some triangle sits between the camera and ``target``.

    Triangles, not vertices. A vertex-based test asks whether any vertex is
    within some radius of the sight line, which means it sees straight through
    the gaps of a mesh whose spacing exceeds that radius — a hand at 8 mm
    spacing tested with an 8 mm radius reports the mouth as visible through the
    hand. Exact segment-triangle intersection has no such gap.

    ``far_eps`` keeps geometry level with the target — the lip rim, the cavity
    wall right behind a tusk — from counting as blocking it.
    """
    rel = sub(target, cam_origin)
    dist = length(rel)
    if dist <= near_eps:
        return False
    d = mul(rel, 1.0 / dist)
    limit = dist - far_eps
    for tri in occluders:
        t = ray_triangle_distance(cam_origin, d, tri)
        if t is not None and near_eps < t < limit:
            return True
    return False


def visibility_report(
    cam_origin: Vec3,
    look_at: Vec3,
    up_hint: Vec3,
    targets: list[Vec3],
    occluders: list[Triangle],
    *,
    lens: float,
    sensor_width: float,
    sensor_height: float,
    res_x: int,
    res_y: int,
    fit: str = "AUTO",
) -> dict:
    """How much of ``targets`` this camera can actually see, in pixels.

    ``visible_frac`` is the share of targets that are in frame, in front of the
    camera, and unoccluded. ``px_h`` / ``px_w`` are the pixel extent of those
    visible targets, which is what decides whether a reviewer can see anything.
    """
    if not targets:
        raise ValueError("visibility_report needs at least one target")
    sensor_x, sensor_y = sensor_extent(sensor_width, sensor_height, res_x, res_y, fit)
    basis = camera_basis(cam_origin, look_at, up_hint)
    xs: list[float] = []
    ys: list[float] = []
    in_frame = 0
    visible = 0
    for t in targets:
        proj = project_camera_space(
            world_to_camera_space(t, cam_origin, basis),
            lens=lens,
            sensor_x=sensor_x,
            sensor_y=sensor_y,
            res_x=res_x,
            res_y=res_y,
        )
        if proj is None:
            continue
        px, py, _depth, inside = proj
        if not inside:
            continue
        in_frame += 1
        if is_occluded(cam_origin, t, occluders):
            continue
        visible += 1
        xs.append(px)
        ys.append(py)
    n = float(len(targets))
    return {
        "in_frame_frac": in_frame / n,
        "visible_frac": visible / n,
        "visible": visible,
        "targets": len(targets),
        "px_w": (max(xs) - min(xs)) if xs else 0.0,
        "px_h": (max(ys) - min(ys)) if ys else 0.0,
    }


def view_directions(
    out: Vec3, up: Vec3, azimuths_deg: tuple, elevations_deg: tuple
) -> list[tuple[float, float, Vec3]]:
    """Candidate view directions around ``out``, swept in azimuth and elevation.

    ``out`` points out of the mouth and ``up`` is the aperture's up axis, so
    azimuth swings around the head and elevation tilts above or below the
    mouth axis. Ordered so the straight-on view comes first: it is the one that
    shows the cavity best, and the sweep only exists for when something is in
    the way.
    """
    side = cross(up, out)
    if length(side) < 1e-9:
        raise ValueError("view_directions: up is parallel to out")
    side = normalise(side)
    out_n = normalise(out)
    up_n = normalise(cross(out_n, side))
    out_list = []
    for el in elevations_deg:
        for az in azimuths_deg:
            a = math.radians(az)
            e = math.radians(el)
            horiz = add(mul(out_n, math.cos(a)), mul(side, math.sin(a)))
            d = add(mul(horiz, math.cos(e)), mul(up_n, math.sin(e)))
            out_list.append((float(az), float(el), normalise(d)))
    out_list.sort(key=lambda t: (abs(t[0]) + abs(t[1]), abs(t[0])))
    return out_list


# --------------------------------------------------------------------------
# Self-test
# --------------------------------------------------------------------------


def _selftest() -> int:
    failures: list[str] = []

    def check(name: str, ok: bool, detail: str) -> None:
        print(f"[{'ok  ' if ok else 'FAIL'}] {name}: {detail}")
        if not ok:
            failures.append(name)

    # --- sensor fit
    sx, sy = sensor_extent(36.0, 24.0, 720, 720, "AUTO")
    check("square frame gets a square sensor", abs(sx - 36.0) < 1e-9 and abs(sy - 36.0) < 1e-9,
          f"{sx:.1f}x{sy:.1f} mm")
    sx, sy = sensor_extent(36.0, 24.0, 640, 800, "AUTO")
    check(
        "portrait frame gives the sensor width to height",
        abs(sy - 36.0) < 1e-9 and abs(sx - 28.8) < 1e-6,
        f"{sx:.1f}x{sy:.1f} mm",
    )

    # --- projection
    kw = dict(lens=50.0, sensor_x=36.0, sensor_y=36.0, res_x=720, res_y=720)
    on_axis = project_camera_space((0.0, 0.0, -1.0), **kw)
    check(
        "on-axis point lands at the frame centre",
        on_axis is not None and abs(on_axis[0] - 360.0) < 1e-6 and abs(on_axis[1] - 360.0) < 1e-6,
        f"{on_axis}",
    )
    behind = project_camera_space((0.0, 0.0, 1.0), **kw)
    check("point behind the camera is rejected", behind is None, f"{behind}")
    # At 1 m the visible half-height is 1 * 18/50 = 0.36 m.
    edge = project_camera_space((0.0, 0.36, -1.0), **kw)
    check(
        "sensor edge lands on the frame border",
        edge is not None and abs(edge[1] - 720.0) < 1e-6 and edge[3],
        f"{edge}",
    )
    outside = project_camera_space((0.0, 0.40, -1.0), **kw)
    check("beyond the sensor is out of frame", outside is not None and not outside[3], f"{outside}")

    # --- the framing claim in the bake script: ~90 px of tusk on the close-up,
    #     ~10 px on the body still. Both are asserted here so the numbers in the
    #     comments cannot quietly go stale.
    tusk = 0.026
    close_h = project_camera_space((0.0, tusk * 0.5, -0.296), **kw)[1] - project_camera_space(
        (0.0, -tusk * 0.5, -0.296), **kw
    )[1]
    check(
        "close-up shows a 26 mm tusk at ~90 px",
        80.0 <= close_h <= 100.0,
        f"{close_h:.0f} px at 0.296 m on a 50 mm lens, 720x720",
    )
    bsx, bsy = sensor_extent(36.0, 24.0, 640, 800, "AUTO")
    bkw = dict(lens=50.0, sensor_x=bsx, sensor_y=bsy, res_x=640, res_y=800)
    body_h = project_camera_space((0.0, tusk * 0.5, -4.9), **bkw)[1] - project_camera_space(
        (0.0, -tusk * 0.5, -4.9), **bkw
    )[1]
    check(
        "body still shows the same tusk at ~10 px",
        body_h <= 15.0,
        f"{body_h:.0f} px at 4.9 m on a 50 mm lens, 640x800 — "
        f"{close_h / max(body_h, 1e-9):.0f}x smaller than the close-up",
    )

    # --- occlusion
    cam = (0.0, -0.3, 0.0)
    target = (0.0, 0.0, 0.0)

    def plate(y: float, half: float = 0.05) -> list[Triangle]:
        """Two triangles forming a square plate in the z=x plane at depth y."""
        a = (-half, y, -half)
        b = (half, y, -half)
        c = (half, y, half)
        dd = (-half, y, half)
        return [(a, b, c), (a, c, dd)]

    aside = [((0.20, -0.15, -0.05), (0.30, -0.15, -0.05), (0.30, -0.15, 0.05))]
    check(
        "clear line of sight is not occluded",
        not is_occluded(cam, target, aside),
        "plate 20 cm off the sight line",
    )
    check(
        "geometry on the sight line occludes",
        is_occluded(cam, target, plate(-0.15)),
        "plate halfway along the sight line",
    )
    check(
        "geometry behind the target does not occlude",
        not is_occluded(cam, target, plate(0.10)),
        "plate 10 cm past the target",
    )
    check(
        "geometry level with the target does not occlude",
        not is_occluded(cam, target, plate(-0.002)),
        "plate 2 mm in front, inside far_eps",
    )
    check(
        "a coarse mesh cannot be seen through between its verts",
        is_occluded(cam, target, plate(-0.15, half=0.5)),
        "a wide plate blocks regardless of how far apart its corners are",
    )

    # --- a fist over the mouth: straight on fails, the sweep finds a way past.
    mouth = (0.0, 0.0, 1.60)
    out = (0.0, -1.0, 0.0)
    up = (0.0, 0.0, 1.0)
    tusks = [
        (0.012 * sx_, 0.006, 1.594 + 0.004 * i)
        for sx_ in (-1.0, 1.0)
        for i in range(6)
    ]
    # A guard hand in front of the mouth: a 90 x 90 mm slab standing 60 mm
    # off the lips, which is where Punch_Cross puts it.
    def slab(depth: float, half: float) -> list[Triangle]:
        y = mouth[1] - depth
        a = (-half, y, mouth[2] - half)
        b = (half, y, mouth[2] - half)
        c = (half, y, mouth[2] + half)
        dd = (-half, y, mouth[2] + half)
        return [(a, b, c), (a, c, dd)]

    fist = slab(0.060, 0.045)
    report_kw = dict(
        lens=50.0,
        sensor_width=36.0,
        sensor_height=24.0,
        res_x=720,
        res_y=720,
    )
    reach = 0.28
    straight = visibility_report(
        add(mouth, mul(out, reach)), mouth, up, tusks, fist, **report_kw
    )
    check(
        "a fist on the mouth axis hides the tusks straight on",
        straight["visible_frac"] < 0.2,
        f"visible_frac={straight['visible_frac']:.2f} px_h={straight['px_h']:.0f}",
    )
    best = None
    for az, el, d in view_directions(out, up, (0, 20, -20, 40, -40, 60, -60, 80, -80), (12, 0, 28)):
        r = visibility_report(add(mouth, mul(d, reach)), mouth, up, tusks, fist, **report_kw)
        if best is None or r["visible_frac"] > best[0]["visible_frac"]:
            best = (r, az, el)
    check(
        "the direction sweep finds a view past the fist",
        best is not None and best[0]["visible_frac"] >= 0.4 and best[0]["px_h"] > 0.0,
        f"best visible_frac={best[0]['visible_frac']:.2f} at azimuth {best[1]:.0f} "
        f"elevation {best[2]:.0f}, px_h={best[0]['px_h']:.0f}",
    )

    # --- with nothing in the way, straight on wins and is tried first.
    clear = visibility_report(add(mouth, mul(out, reach)), mouth, up, tusks, [], **report_kw)
    check(
        "an unobstructed mouth is fully visible straight on",
        clear["visible_frac"] == 1.0,
        f"visible_frac={clear['visible_frac']:.2f} px_h={clear['px_h']:.0f}",
    )
    first = view_directions(out, up, (0, 20, -20), (0, 12))[0]
    check(
        "the sweep tries the straight-on view first",
        abs(first[0]) < 1e-9 and abs(first[1]) < 1e-9,
        f"first candidate azimuth={first[0]:.0f} elevation={first[1]:.0f}",
    )

    if failures:
        print(f"\nSTILL VISIBILITY SELFTEST FAILED: {failures}")
        return 1
    print("\nSTILL VISIBILITY SELFTEST OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(_selftest())
