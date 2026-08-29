# -*- coding: utf-8 -*-
"""Pure-geometry solver for the orc mouth aperture. No bpy, no Blender.

This module owns ONE definition of where the mouth is on a MakeHuman-style head
and how large the oral cavity is. ``bake_human_orc`` collects head-weighted
vertex positions in body object space, hands them here, and the returned
:class:`MouthAperture` is the single authority used by

  * the cavity carve (which verts move, and how far),
  * the tusk author (where a tusk starts, which way it grows, how long),
  * the still gate (is a tusk vert inside the aperture volume).

Why this module exists
----------------------
Earlier bakes defined "the mouth" three separate times -- a mouth-corner hunt,
a lip-band box, and an aperture axis -- each with its own hand-tuned millimetre
windows, and the three disagreed:

  * the corner hunt returned jaw-side verts at ``|x-cx| ~ 0.082`` (a 164 mm
    wide "mouth"), because its only lateral guard was an absolute 95 mm cap;
  * the lip band then anchored its Y window on that commissure depth, but on a
    real head the mid-sagittal lips protrude ~30 mm in front of the jaw sides,
    so the band could only ever contain lateral verts:
    ``pool=36 min_|x-cx|=0.0649``;
  * with no centre lips, the lip part refused and the tusk seating downstream
    of it never ran.

The mouth was never missing from the mesh. The region was a box in Y on a
surface that curves in Y, so the box excluded the very verts it was hunting.

Everything here is instead measured from the cloud itself: the nose tip and the
chin are extrema of the mid-sagittal forward profile, the lip slit is a fixed
fraction of the measured chin-to-nose span, and every size is a fraction of the
measured head width. No absolute millimetre window decides whether the mouth is
found.

Conventions (same as the bake script's body object space)
--------------------------------------------------------
``+X`` right, ``+Y`` into the head (the face looks down ``-Y``), ``+Z`` up.
Units are metres.

Run ``python tools/orc_mouth_geometry.py`` for the self-test.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

Point = tuple[float, float, float]

# --- landmark detection -----------------------------------------------------
# Mid-sagittal strip half-widths to try, as fractions of the head width. The
# first that samples the profile densely enough wins; the widest is still
# narrower than the philtrum, so it cannot pick up cheek verts.
MIDLINE_STRIP_FRACS = (0.07, 0.10, 0.14, 0.18)
# The nose tip must sit at least this far up the head cloud. Head vertex groups
# bleed down the neck, so the cloud is taller than a bare head; the nose still
# lands well above a third of it. A violation means the most-forward midline
# vert is the chin or the throat -- i.e. an earlier restyle step built a muzzle
# that out-projects the nose, and the landmarks would be garbage.
NOSE_MIN_HEIGHT_FRAC = 0.30
# Walking down the front profile, the surface may recede this fraction of the
# head width behind the nose tip and still count as face. The chin front sits
# ~0.12*W behind the nose tip; the submental / throat below it keeps receding,
# so this separates chin from throat without an absolute millimetre cut.
CHIN_MAX_RECESS_FRAC = 0.20
# Lip slit as a fraction of the measured chin-bottom -> nose-tip span.
# Anthropometry: subnasale->stomion ~22 mm, stomion->gnathion ~44 mm, and the
# nose tip sits ~14 mm above subnasale, so pronasale->gnathion ~80 mm and the
# slit lands a little over half way up from the chin.
MOUTH_ABOVE_CHIN_FRAC = 0.56
# Second, independent estimate: pronasale->stomion is ~0.24 of the head width.
# This uses a different landmark (nose, not chin) and a different scale (head
# width, not face height), so agreement between the two is real evidence.
MOUTH_BELOW_NOSE_FRAC = 0.24
# Refuse only a landmark catastrophe. Both estimates normally land within a few
# millimetres of each other; this is not here to arbitrate millimetres.
MOUTH_ESTIMATE_MAX_DISAGREE_FRAC = 0.18

# --- aperture sizing --------------------------------------------------------
# All three are fractions of the measured head width W. For W = 0.155 m this is
# a 62 mm wide, 40 mm tall, 31 mm deep maw: wide for a human, right for an orc,
# and nowhere near the 108 mm face-wide part earlier bakes were refusing.
MOUTH_HALF_WIDTH_FRAC = 0.20
MOUTH_HALF_HEIGHT_FRAC = 0.13
MOUTH_DEPTH_FRAC = 0.20
# Fraction of the rim radius that is carved to full depth before the wall ramps
# back out to the lip. Bigger means a boxier cavity with more room for tusks
# off the centre line; smaller means gentler walls.
BORE_PLATEAU_R = 0.62
# The aperture must stay inside the face. Measured against the actual head
# half-width in the mouth slab, so this cannot drift into a face-wide part
# however the head is proportioned.
MOUTH_MAX_FACE_WIDTH_FRAC = 0.62

# --- cloud sanity -----------------------------------------------------------
HEAD_WIDTH_MIN = 0.10
HEAD_WIDTH_MAX = 0.26
MIN_CLOUD_POINTS = 60
MIN_MIDLINE_POINTS = 12
MIN_FRONT_BELOW_POINTS = 6
# Nose tip to chin bottom must span at least this fraction of the head width,
# else the "face" we measured is a flat blob and the ratio is meaningless.
MIN_FACE_HEIGHT_FRAC = 0.20


class MouthGeometryError(RuntimeError):
    """Raised when the head cloud cannot support a measured mouth aperture.

    Always carries the numbers that failed, so a local bake log is diagnostic
    on its own.
    """


@dataclass(frozen=True)
class MouthAperture:
    """The one authoritative mouth aperture, in body object space.

    ``center`` is on the lip surface at the mid-sagittal plane: the rim plane of
    the oral cavity. ``half_width`` / ``half_height`` are the rim ellipse radii
    along ``+X`` / ``+Z``. ``depth`` is how far the cavity bores along ``+Y``.
    """

    center: Point
    half_width: float
    half_height: float
    depth: float
    head_center_x: float
    head_width: float
    head_z_min: float
    head_z_max: float
    nose_z: float
    nose_y: float
    chin_z: float
    mouth_z_from_chin: float
    mouth_z_from_nose: float
    face_half_width_at_mouth: float
    cloud_points: int
    midline_points: int
    midline_strip_half: float

    @property
    def center_x(self) -> float:
        return self.center[0]

    @property
    def center_y(self) -> float:
        return self.center[1]

    @property
    def center_z(self) -> float:
        return self.center[2]

    def aperture_coords(self, p: Point) -> tuple[float, float, float]:
        """Return ``(u, w, d)``: lateral, vertical and inward offsets from the rim.

        ``u`` along ``+X``, ``w`` along ``+Z``, ``d`` along ``+Y`` (into the
        head). ``d == 0`` is the rim plane, ``d == depth`` is the cavity floor.
        """
        return (
            float(p[0]) - self.center[0],
            float(p[2]) - self.center[2],
            float(p[1]) - self.center[1],
        )

    def radial(self, u: float, w: float) -> float:
        """Normalised ellipse radius: ``<= 1`` is inside the rim."""
        return math.hypot(u / self.half_width, w / self.half_height)

    def falloff(self, u: float, w: float) -> float:
        """Bore profile weight: 1 across the plateau, 0 at the rim.

        The carve displaces every vert to ``depth * falloff``, so this is the
        shape of the cavity. It is a flat-bottomed bore rather than a
        paraboloid, for two reasons:

          * an oral cavity is a rounded box, not a dish;
          * a pure raised cosine leaves almost no depth off the centre line, so
            a tusk seated on the canine line would be embedded in the cavity
            wall instead of standing in open air. ``BORE_PLATEAU_R`` is what
            gives the tusks somewhere to be.

        Continuous everywhere and exactly 0 at the rim, with zero slope at both
        ends of the ramp, so the carve cannot open a cliff between neighbours.
        """
        return bore_frac(self.radial(u, w))

    def bore_depth(self, u: float, w: float) -> float:
        """Cavity depth at ``(u, w)``.

        A lower bound on how far the skin was pushed back there: the carve only
        ever moves a vert *to* this profile, never in front of it, so anything
        shallower than this is in open air. The tusk gate uses that.
        """
        return self.depth * self.falloff(u, w)

    def contains(self, p: Point, *, margin: float = 0.0) -> bool:
        """True when ``p`` is inside the cavity volume (rim ellipse x depth)."""
        u, w, d = self.aperture_coords(p)
        if d < -margin or d > self.depth + margin:
            return False
        if self.half_width <= 0.0 or self.half_height <= 0.0:
            return False
        ru = u / (self.half_width + margin)
        rw = w / (self.half_height + margin)
        return math.hypot(ru, rw) <= 1.0

    def describe(self) -> str:
        return (
            f"center=({self.center[0]:.4f},{self.center[1]:.4f},{self.center[2]:.4f}) "
            f"half=({self.half_width:.4f},{self.half_height:.4f}) "
            f"depth={self.depth:.4f} head_width={self.head_width:.4f} "
            f"nose_z={self.nose_z:.4f} chin_z={self.chin_z:.4f} "
            f"mouth_z_from_chin={self.mouth_z_from_chin:.4f} "
            f"mouth_z_from_nose={self.mouth_z_from_nose:.4f} "
            f"face_half_width_at_mouth={self.face_half_width_at_mouth:.4f} "
            f"cloud={self.cloud_points} midline={self.midline_points} "
            f"midline_strip_half={self.midline_strip_half:.4f}"
        )


def bore_frac(r: float) -> float:
    """Cavity depth fraction at normalised rim-ellipse radius ``r``."""
    if r >= 1.0:
        return 0.0
    if r <= BORE_PLATEAU_R:
        return 1.0
    t = (r - BORE_PLATEAU_R) / (1.0 - BORE_PLATEAU_R)
    return 0.5 * (1.0 + math.cos(math.pi * t))


def smoothstep(t: float) -> float:
    """Continuous 0..1 ramp with zero slope at both ends."""
    if t <= 0.0:
        return 0.0
    if t >= 1.0:
        return 1.0
    return t * t * (3.0 - 2.0 * t)


def band_falloff(value: float, lo: float, hi: float, edge: float) -> float:
    """Weight for ``value`` inside ``[lo, hi]``, easing to 0 over ``edge``.

    Every restyle displacement is scaled by one of these. A hard band -- move
    48 mm at dz=-0.144, move nothing at dz=-0.146 -- is exactly how the chin
    needle and the pec spikes were authored: two adjacent verts torn apart by
    the full displacement. With an eased band the same displacement cannot
    open a gap larger than the local vertex spacing times the ramp slope.
    """
    if edge <= 0.0:
        raise ValueError(f"band_falloff needs edge > 0, got {edge}")
    if value <= lo - edge or value >= hi + edge:
        return 0.0
    if value < lo:
        return smoothstep((value - (lo - edge)) / edge)
    if value > hi:
        return smoothstep((hi + edge - value) / edge)
    return 1.0


def _percentile(sorted_values: list[float], frac: float) -> float:
    if not sorted_values:
        raise MouthGeometryError("_percentile on empty sequence")
    idx = int(round(frac * (len(sorted_values) - 1)))
    return sorted_values[max(0, min(len(sorted_values) - 1, idx))]


def forward_profile(points: list[Point], *, bins: int = 48) -> list[tuple[float, float, int]]:
    """Most-forward ``y`` per ``z`` bin: ``[(z_mid, y_front, count), ...]``.

    Diagnostic only. The bake logs this so a local run reports the real shape
    of the face it measured instead of leaving us to guess from a single
    refused threshold.
    """
    if bins < 2:
        raise ValueError(f"forward_profile needs bins >= 2, got {bins}")
    if not points:
        return []
    zs = [p[2] for p in points]
    z0, z1 = min(zs), max(zs)
    span = z1 - z0
    if span <= 0.0:
        return []
    step = span / bins
    front: list[float | None] = [None] * bins
    count = [0] * bins
    for p in points:
        i = int((p[2] - z0) / step)
        if i >= bins:
            i = bins - 1
        count[i] += 1
        cur = front[i]
        if cur is None or p[1] < cur:
            front[i] = p[1]
    out: list[tuple[float, float, int]] = []
    for i in range(bins):
        f = front[i]
        if f is None:
            continue
        out.append((z0 + (i + 0.5) * step, f, count[i]))
    return out


def solve_mouth_aperture(points: list[Point]) -> MouthAperture:
    """Measure the mouth aperture from a head-weighted vertex cloud.

    ``points`` must be body-object-space positions of skull verts (head vertex
    group dominant, neck excluded). Raises :class:`MouthGeometryError` with the
    offending numbers rather than falling back to an invented aperture.
    """
    if len(points) < MIN_CLOUD_POINTS:
        raise MouthGeometryError(
            f"head cloud too small for a measured mouth ({len(points)} < {MIN_CLOUD_POINTS})"
        )
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    zs = [p[2] for p in points]
    x_min, x_max = min(xs), max(xs)
    y_min, y_max = min(ys), max(ys)
    z_min, z_max = min(zs), max(zs)
    head_width = x_max - x_min
    head_height = z_max - z_min
    if not HEAD_WIDTH_MIN <= head_width <= HEAD_WIDTH_MAX:
        raise MouthGeometryError(
            f"head cloud width {head_width:.4f} outside [{HEAD_WIDTH_MIN}, {HEAD_WIDTH_MAX}] "
            f"— cloud is not a head (x=[{x_min:.4f},{x_max:.4f}], n={len(points)})"
        )
    if head_height <= 0.0:
        raise MouthGeometryError(f"head cloud has no height (z={z_min:.4f}..{z_max:.4f})")
    center_x = 0.5 * (x_min + x_max)
    center_y_cloud = 0.5 * (y_min + y_max)

    # Sampling density is a property of the mesh, not of the head, so the strip
    # widens until the profile is sampled. The cap keeps it mid-sagittal: at
    # 0.18*W the strip is still narrower than the philtrum-to-canine span, so a
    # widened strip cannot start reporting cheek verts as the profile.
    midline: list[Point] = []
    front_below: list[Point] = []
    nose_y = 0.0
    nose_z = 0.0
    strip_half = 0.0
    for frac in MIDLINE_STRIP_FRACS:
        strip_half = max(0.006, frac * head_width)
        midline = [p for p in points if abs(p[0] - center_x) <= strip_half]
        if len(midline) < MIN_MIDLINE_POINTS:
            continue
        nose = min(midline, key=lambda p: p[1])
        nose_y, nose_z = float(nose[1]), float(nose[2])
        recess_limit = nose_y + CHIN_MAX_RECESS_FRAC * head_width
        front_below = [p for p in midline if p[2] < nose_z and p[1] <= recess_limit]
        if len(front_below) >= MIN_FRONT_BELOW_POINTS:
            break
    if len(midline) < MIN_MIDLINE_POINTS:
        raise MouthGeometryError(
            f"mid-sagittal strip too sparse ({len(midline)} < {MIN_MIDLINE_POINTS}) even at "
            f"|x-{center_x:.4f}| <= {strip_half:.4f}; head_width={head_width:.4f} "
            f"cloud={len(points)}"
        )
    if len(front_below) < MIN_FRONT_BELOW_POINTS:
        raise MouthGeometryError(
            f"too few midline verts on the face below the nose "
            f"({len(front_below)} < {MIN_FRONT_BELOW_POINTS}) at strip_half={strip_half:.4f}; "
            f"nose=({nose_y:.4f},{nose_z:.4f}) "
            f"recess_limit_y={nose_y + CHIN_MAX_RECESS_FRAC * head_width:.4f} "
            f"head_width={head_width:.4f}"
        )

    nose_height_frac = (nose_z - z_min) / head_height
    if nose_height_frac < NOSE_MIN_HEIGHT_FRAC:
        raise MouthGeometryError(
            f"most-forward midline vert sits at height_frac={nose_height_frac:.3f} "
            f"< {NOSE_MIN_HEIGHT_FRAC} (z={nose_z:.4f} in [{z_min:.4f},{z_max:.4f}]) — "
            f"that is a chin/throat, not a nose tip. An earlier restyle step has "
            f"out-projected the nose; landmarks would be garbage."
        )

    chin_z = _percentile(sorted(p[2] for p in front_below), 0.03)
    face_height = nose_z - chin_z
    if face_height < MIN_FACE_HEIGHT_FRAC * head_width:
        raise MouthGeometryError(
            f"nose-to-chin span {face_height:.4f} < "
            f"{MIN_FACE_HEIGHT_FRAC} * head_width ({MIN_FACE_HEIGHT_FRAC * head_width:.4f}); "
            f"nose_z={nose_z:.4f} chin_z={chin_z:.4f}"
        )

    mouth_z_from_chin = chin_z + MOUTH_ABOVE_CHIN_FRAC * face_height
    mouth_z_from_nose = nose_z - MOUTH_BELOW_NOSE_FRAC * head_width
    disagree = abs(mouth_z_from_chin - mouth_z_from_nose)
    if disagree > MOUTH_ESTIMATE_MAX_DISAGREE_FRAC * head_width:
        raise MouthGeometryError(
            f"the two independent lip-slit estimates disagree by {disagree:.4f} "
            f"(> {MOUTH_ESTIMATE_MAX_DISAGREE_FRAC} * head_width = "
            f"{MOUTH_ESTIMATE_MAX_DISAGREE_FRAC * head_width:.4f}): "
            f"from_chin={mouth_z_from_chin:.4f} from_nose={mouth_z_from_nose:.4f} "
            f"(nose_z={nose_z:.4f} chin_z={chin_z:.4f} head_width={head_width:.4f})"
        )
    # Two independent estimates that agree; average them so neither landmark
    # alone can drag the aperture off the mouth.
    mouth_z = 0.5 * (mouth_z_from_chin + mouth_z_from_nose)

    half_width = MOUTH_HALF_WIDTH_FRAC * head_width
    half_height = MOUTH_HALF_HEIGHT_FRAC * head_width
    depth = MOUTH_DEPTH_FRAC * head_width

    band_half = 0.30 * face_height
    band = [p for p in midline if abs(p[2] - mouth_z) <= band_half]
    if len(band) < 4:
        band_half = 0.55 * face_height
        band = [p for p in midline if abs(p[2] - mouth_z) <= band_half]
    if len(band) < 4:
        raise MouthGeometryError(
            f"no midline verts within {band_half:.4f} of the lip slit z={mouth_z:.4f} "
            f"(midline n={len(midline)}, nose_z={nose_z:.4f}, chin_z={chin_z:.4f})"
        )
    mouth_y = min(p[1] for p in band)

    slab = [
        p
        for p in points
        if abs(p[2] - mouth_z) <= half_height and p[1] < center_y_cloud
    ]
    if not slab:
        raise MouthGeometryError(
            f"no front-face verts in the mouth slab z={mouth_z:.4f} +/- {half_height:.4f}"
        )
    face_half_width_at_mouth = max(abs(p[0] - center_x) for p in slab)
    if half_width > MOUTH_MAX_FACE_WIDTH_FRAC * face_half_width_at_mouth:
        raise MouthGeometryError(
            f"aperture half-width {half_width:.4f} > {MOUTH_MAX_FACE_WIDTH_FRAC} * "
            f"face half-width at mouth height ({face_half_width_at_mouth:.4f}) — "
            f"refusing a face-wide part"
        )

    # A mouth cannot reach past the nose or below the chin. These are the two
    # landmarks the slit was interpolated between, so a violation means one of
    # them was mis-detected -- most likely a chin cut off by neck weights --
    # and the carve would otherwise bore a maw through the nose or the jaw.
    if mouth_z + half_height >= nose_z:
        raise MouthGeometryError(
            f"aperture top rim {mouth_z + half_height:.4f} reaches the nose tip "
            f"{nose_z:.4f} (slit={mouth_z:.4f} half_height={half_height:.4f}); "
            f"chin_z={chin_z:.4f} from_chin={mouth_z_from_chin:.4f} "
            f"from_nose={mouth_z_from_nose:.4f} — a landmark is wrong"
        )
    if mouth_z - half_height <= chin_z:
        raise MouthGeometryError(
            f"aperture bottom rim {mouth_z - half_height:.4f} reaches the chin "
            f"{chin_z:.4f} (slit={mouth_z:.4f} half_height={half_height:.4f}); "
            f"nose_z={nose_z:.4f} from_chin={mouth_z_from_chin:.4f} "
            f"from_nose={mouth_z_from_nose:.4f} — a landmark is wrong"
        )

    return MouthAperture(
        center=(center_x, mouth_y, mouth_z),
        half_width=half_width,
        half_height=half_height,
        depth=depth,
        head_center_x=center_x,
        head_width=head_width,
        head_z_min=z_min,
        head_z_max=z_max,
        nose_z=nose_z,
        nose_y=nose_y,
        chin_z=chin_z,
        mouth_z_from_chin=mouth_z_from_chin,
        mouth_z_from_nose=mouth_z_from_nose,
        face_half_width_at_mouth=face_half_width_at_mouth,
        cloud_points=len(points),
        midline_points=len(midline),
        midline_strip_half=strip_half,
    )


# --------------------------------------------------------------------------
# Self-test: synthetic MakeHuman-like head, ground truth known.
# --------------------------------------------------------------------------


def _synthetic_head(
    *,
    mouth_z: float = 1.600,
    nose_z: float = 1.635,
    chin_z: float = 1.548,
    crown_z: float = 1.760,
    neck_z: float = 1.470,
    half_width: float = 0.0775,
    chin_front_y: float = -0.086,
    rings: int = 64,
    per_ring: int = 48,
) -> list[Point]:
    """Profile-driven head point cloud with known nose / lip / chin landmarks.

    Front depth and half-width are functions of height, so the resulting cloud
    reproduces the property that broke the old lip-band box: at mouth height
    the mid-sagittal lips protrude well in front of the jaw sides.
    """
    skull_top = crown_z - 0.010

    def half_w(z: float) -> float:
        if z >= chin_z:
            t = (z - chin_z) / max(skull_top - chin_z, 1e-6)
            t = max(0.0, min(1.0, t))
            return half_width * (0.52 + 0.48 * math.sin(math.pi * min(1.0, 0.35 + 0.65 * t)))
        t = (chin_z - z) / max(chin_z - neck_z, 1e-6)
        return half_width * (0.52 - 0.10 * min(1.0, t))

    def front_y(z: float) -> float:
        """Most-forward Y of the mid-sagittal profile at height ``z`` (negative)."""
        if z > nose_z + 0.060:
            return -0.072  # forehead / crown
        if z > nose_z:
            t = (z - nose_z) / 0.060
            return -0.098 + t * (-0.072 + 0.098)
        if z > mouth_z + 0.014:
            t = (nose_z - z) / max(nose_z - (mouth_z + 0.014), 1e-6)
            return -0.105 + t * 0.014  # nose tip -> subnasale recess
        if z > mouth_z:
            return -0.096  # upper lip
        if z > mouth_z - 0.012:
            return -0.095  # lower lip
        if z > chin_z + 0.008:
            t = (mouth_z - 0.012 - z) / max((mouth_z - 0.012) - (chin_z + 0.008), 1e-6)
            return -0.095 + t * (chin_front_y + 0.095)  # sulcus -> chin
        if z >= chin_z:
            return chin_front_y
        t = (chin_z - z) / max(chin_z - neck_z, 1e-6)
        return chin_front_y + 0.048 * min(1.0, 3.0 * t)  # submental recedes hard

    back_y = 0.098
    pts: list[Point] = []
    for i in range(rings):
        z = neck_z + (crown_z - neck_z) * i / (rings - 1)
        hw = half_w(z)
        fy = front_y(z)
        by = back_y * (0.55 + 0.45 * min(1.0, max(0.0, (z - chin_z) / 0.10)))
        cy = 0.5 * (fy + by)
        ry = 0.5 * (by - fy)
        if hw <= 0.0 or ry <= 0.0:
            continue
        for j in range(per_ring):
            ang = 2.0 * math.pi * j / per_ring
            pts.append((hw * math.sin(ang), cy + ry * math.cos(ang), z))
    return pts


def _selftest() -> int:
    truth_mouth_z = 1.600
    pts = _synthetic_head()
    ap = solve_mouth_aperture(pts)
    print(f"solved: {ap.describe()}")
    profile = forward_profile([p for p in pts if abs(p[0] - ap.head_center_x) <= 0.008], bins=24)
    print("mid-sagittal forward profile (z, y_front, n):")
    for z, y, n in profile:
        print(f"  z={z:.4f} y_front={y:.4f} n={n}")

    failures: list[str] = []

    def check(name: str, ok: bool, detail: str) -> None:
        print(f"[{'ok  ' if ok else 'FAIL'}] {name}: {detail}")
        if not ok:
            failures.append(name)

    check(
        "nose tip found",
        abs(ap.nose_z - 1.635) <= 0.006,
        f"nose_z={ap.nose_z:.4f} expected 1.6350",
    )
    check(
        "chin bottom found",
        abs(ap.chin_z - 1.548) <= 0.008,
        f"chin_z={ap.chin_z:.4f} expected 1.5480",
    )
    check(
        "lip slit within one aperture half-height of truth",
        abs(ap.center_z - truth_mouth_z) <= ap.half_height,
        f"center_z={ap.center_z:.4f} truth={truth_mouth_z:.4f} half_height={ap.half_height:.4f}",
    )
    check(
        "aperture is a mouth, not a face-wide part",
        0.020 <= ap.half_width <= 0.045,
        f"half_width={ap.half_width:.4f}",
    )
    check(
        "cavity has usable depth",
        0.020 <= ap.depth <= 0.045,
        f"depth={ap.depth:.4f}",
    )
    check(
        "rim sits on the lip surface, not inside the head",
        ap.center_y <= -0.080,
        f"center_y={ap.center_y:.4f}",
    )

    # The failure mode this module replaces: a Y window anchored on the jaw
    # sides cannot reach the midline lips. Prove the synthetic head has that
    # property, so the self-test is actually exercising the real problem.
    jaw = [
        p
        for p in pts
        if abs(abs(p[0] - ap.head_center_x) - 0.062) <= 0.004
        and abs(p[2] - ap.center_z) <= 0.010
        and p[1] < 0.0
    ]
    if jaw:
        jaw_y = min(p[1] for p in jaw)
        check(
            "midline lips protrude in front of the jaw sides",
            jaw_y - ap.center_y > 0.012,
            f"jaw_front_y={jaw_y:.4f} lip_y={ap.center_y:.4f} "
            f"delta={jaw_y - ap.center_y:.4f} (old 24 mm Y window anchored here)",
        )

    # Falloff must be continuous and vanish exactly at the rim.
    check(
        "falloff is 1 at centre",
        abs(ap.falloff(0.0, 0.0) - 1.0) < 1e-9,
        f"falloff(0,0)={ap.falloff(0.0, 0.0):.6f}",
    )
    check(
        "falloff vanishes at the rim",
        ap.falloff(ap.half_width, 0.0) == 0.0 and ap.falloff(0.0, ap.half_height) == 0.0,
        "falloff(rim)=0",
    )
    worst_step = 0.0
    steps = 400
    for i in range(steps):
        u0 = ap.half_width * i / steps
        u1 = ap.half_width * (i + 1) / steps
        worst_step = max(worst_step, abs(ap.falloff(u1, 0.0) - ap.falloff(u0, 0.0)))
    check(
        "falloff has no cliff",
        worst_step < 0.02,
        f"max step over {steps} samples = {worst_step:.5f}",
    )

    check(
        "cavity volume contains its own centre-line",
        ap.contains((ap.center_x, ap.center_y + 0.5 * ap.depth, ap.center_z)),
        "centre-line point inside",
    )
    check(
        "cavity volume excludes a cheek point",
        not ap.contains((ap.center_x + 3.0 * ap.half_width, ap.center_y + 0.005, ap.center_z)),
        "cheek point outside",
    )
    check(
        "cavity volume excludes a point in front of the lip",
        not ap.contains((ap.center_x, ap.center_y - 0.010, ap.center_z), margin=0.004),
        "outside-the-lip point rejected",
    )

    # band_falloff continuity is the anti-needle guarantee for restyle offsets:
    # the weight must be Lipschitz-bounded by 1.5/edge, so two verts spaced
    # `s` apart can never differ by more than 1.5*s/edge of the amplitude.
    edge = 0.030
    samples = 4000
    spacing = 0.60 / samples
    worst_band = 0.0
    prev = band_falloff(-0.30, -0.145, -0.055, edge)
    for i in range(1, samples + 1):
        v = -0.30 + 0.60 * i / samples
        cur = band_falloff(v, -0.145, -0.055, edge)
        worst_band = max(worst_band, abs(cur - prev))
        prev = cur
    lipschitz_bound = 1.5 * spacing / edge
    check(
        "band_falloff respects the 1.5/edge Lipschitz bound",
        worst_band <= lipschitz_bound + 1e-9,
        f"max step = {worst_band:.6f} bound = {lipschitz_bound:.6f}",
    )
    check(
        "band_falloff is 0 outside the eased band and 1 inside",
        band_falloff(-0.200, -0.145, -0.055, edge) == 0.0
        and band_falloff(-0.100, -0.145, -0.055, edge) == 1.0,
        "band ends behave",
    )

    # Sweep proportions and sampling density. The solver must land the rim
    # within one half-height of the true slit on every one of these, or it is
    # tuned to a single synthetic head instead of measuring a real one.
    print("\nproportion / density sweep:")
    sweep = [
        ("baseline", {}),
        ("narrow head", {"half_width": 0.066}),
        ("broad head", {"half_width": 0.088}),
        ("long face", {"chin_z": 1.532, "nose_z": 1.642, "mouth_z": 1.596}),
        ("short face", {"chin_z": 1.562, "nose_z": 1.628, "mouth_z": 1.603}),
        ("high mouth", {"mouth_z": 1.610}),
        ("low mouth", {"mouth_z": 1.590}),
        ("receding chin", {"chin_front_y": -0.072}),
        ("jutting chin", {"chin_front_y": -0.098}),
        ("low-poly proxy", {"rings": 26, "per_ring": 20}),
        ("dense", {"rings": 96, "per_ring": 72}),
    ]
    for name, kwargs in sweep:
        truth = float(kwargs.get("mouth_z", 1.600))
        try:
            got = solve_mouth_aperture(_synthetic_head(**kwargs))
        except MouthGeometryError as exc:
            check(f"sweep {name}", False, f"refused: {exc}")
            continue
        err = abs(got.center_z - truth)
        check(
            f"sweep {name}",
            err <= got.half_height,
            f"center_z={got.center_z:.4f} truth={truth:.4f} err={err * 1000:.1f}mm "
            f"half_height={got.half_height * 1000:.1f}mm "
            f"(from_chin={got.mouth_z_from_chin:.4f} from_nose={got.mouth_z_from_nose:.4f})",
        )

    print()
    # A cloud that is not a head, or a head too coarse to measure, must be
    # refused loudly rather than defaulted to an invented aperture.
    for name, bad in (
        ("tiny cloud", [(0.0, 0.0, 0.0)] * 10),
        (
            "torso-wide cloud",
            [(x * 0.001 - 0.4, 0.0, 1.5 + 0.001 * x) for x in range(800)],
        ),
        ("head too coarse to measure", _synthetic_head(rings=18, per_ring=16)),
    ):
        try:
            solve_mouth_aperture(bad)
        except MouthGeometryError as exc:
            check(f"refuses {name}", True, str(exc)[:110])
        else:
            check(f"refuses {name}", False, "solver accepted a non-head cloud")

    if failures:
        print(f"\nSELFTEST FAILED: {failures}")
        return 1
    print("\nSELFTEST OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(_selftest())
