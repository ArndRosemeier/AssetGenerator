/**
 * A town wall (a capital's): a ring of stone round the town a little outside its edge track, a gate where
 * each road goes through it (a gatehouse with a tower each side, an arch over the road, two oak leaves:
 * `gateLeaves`), and towers along it between. The plan
 * (`townWall`: where the ring runs, the ground under it, where the gates and towers stand, how high), its
 * meshes in the building format (`wallMesh`, drawn with the buildings' shader) and what it blocks
 * (`wallBlocks`: a walker goes through the gates only). Pure.
 */
import { hash2f } from '@futuremagic/core';
import { BuildingMat, Frame, Out, type BuildingMesh, type RGB } from './building';
import type { DoorLeaf } from './interior';
import { offset, shapesToPolys } from './clip';
import { chaikin, distSqPointSeg, ensureCCW, pointInPoly, polyArea, polyPerimeter, segIntersect, type Poly } from './geom2';

export interface TownGate {
  /** Where the road goes through the ring (world metres), and the road's way out (radians, atan2(z, x)). */
  x: number;
  z: number;
  angle: number;
  /** Half the gateway's width, m (the road and a little more). */
  half: number;
  /** The road (index into the plan's roads) it lets through. */
  road: number;
  /** The ground there. */
  y: number;
}

/** A tower: where it stands, the way the wall runs there (radians, atan2(z, x)), the lowest ground under it. */
export interface TownTower {
  x: number;
  z: number;
  angle: number;
  y: number;
}

export interface TownWall {
  /** The wall's middle line, closed, counter-clockwise, and the ground under each of its corners. */
  ring: Poly;
  ringY: number[];
  gates: TownGate[];
  /** Towers along it (the gates' flanks first). */
  towers: TownTower[];
  /** Wall height above the ground, its thickness, a tower's height and half width, m. */
  height: number;
  thick: number;
  towerH: number;
  towerHalf: number;
}

export interface WallRules {
  /** How far outside the town's outline the wall runs, m. */
  out: number;
  height: number;
  /** Towers about this far apart along the wall, m. */
  every: number;
}

/** The wall round an outline, with a gate for each road that leaves through it; `height`: the ground. */
export function townWall(outline: Poly, roads: readonly number[][], rules: WallRules, roadWidth: number, height: (x: number, z: number) => number): TownWall {
  const grown = shapesToPolys(offset([outline], rules.out, 'round')).sort((a, b) => Math.abs(polyArea(b)) - Math.abs(polyArea(a)))[0] ?? outline;
  // A smooth, even line: the offset's corners rounded off, no tiny steps.
  const ring = ensureCCW(evenRing(chaikin([...grown, grown[0], grown[1]], 1).slice(0, -2), 6));
  const gates: TownGate[] = [];
  const towerHalf = 3, towers: TownTower[] = [], half = roadWidth / 2 + 1;
  roads.forEach((road, ri) => {
    const hit = crossing(ring, road);
    // Two roads leaving side by side go out through one gate (else each gate's towers would stand in the other).
    if (hit && !gates.some((g) => Math.hypot(g.x - hit.x, g.z - hit.z) < 2 * (half + 2 * towerHalf))) gates.push({ ...hit, half, road: ri, y: height(hit.x, hit.z) });
  });
  const lowest = (x: number, z: number) => Math.min(height(x, z), height(x + towerHalf, z + towerHalf), height(x - towerHalf, z + towerHalf), height(x + towerHalf, z - towerHalf), height(x - towerHalf, z - towerHalf));
  // Each gate between two towers, square to the road.
  for (const g of gates) {
    const sx = -Math.sin(g.angle), sz = Math.cos(g.angle), w = g.half + towerHalf, across = g.angle + Math.PI / 2;
    for (const k of [1, -1]) towers.push({ x: g.x + sx * w * k, z: g.z + sz * w * k, angle: across, y: lowest(g.x + sx * w * k, g.z + sz * w * k) });
  }
  // Then along the ring, about `every` apart, not crowding a gate.
  const L = polyPerimeter(ring), n = Math.max(3, Math.round(L / rules.every));
  for (let i = 0; i < n; i++) {
    const s = (i / n) * L, [x, z] = alongRing(ring, s), [x2, z2] = alongRing(ring, s + 1);
    if (gates.some((g) => Math.hypot(g.x - x, g.z - z) < g.half + towerHalf * 2 + 8)) continue;
    if (towers.some((t) => Math.hypot(t.x - x, t.z - z) < rules.every * 0.5)) continue;
    towers.push({ x, z, angle: Math.atan2(z2 - z, x2 - x), y: lowest(x, z) });
  }
  const ringY: number[] = [];
  for (let i = 0; i < ring.length; i += 2) ringY.push(height(ring[i], ring[i + 1]));
  return { ring, ringY, gates, towers, height: rules.height, thick: 2.2, towerH: rules.height + 3.5, towerHalf };
}

/** Whether a walker of radius `r` at (x, z) runs into the wall: its towers, or its ring anywhere but through a gate. */
export function wallBlocks(w: TownWall, x: number, z: number, r: number): boolean {
  for (const t of w.towers) if (Math.abs(x - t.x) < w.towerHalf * 1.5 + r && Math.abs(z - t.z) < w.towerHalf * 1.5 + r && inTower(w, t, x, z, r)) return true;
  for (const g of w.gates) if (Math.hypot(x - g.x, z - g.z) < g.half + w.towerHalf) return false;
  const reach = (w.thick / 2 + r) ** 2, n = w.ring.length >> 1, R = w.ring;
  for (let i = 0; i < n; i++) {
    const j = (i + 1) % n;
    if (distSqPointSeg(x, z, R[i * 2], R[i * 2 + 1], R[j * 2], R[j * 2 + 1]) < reach) return true;
  }
  return false;
}

function inTower(w: TownWall, t: TownTower, x: number, z: number, r: number): boolean {
  const ux = Math.cos(t.angle), uz = Math.sin(t.angle), dx = x - t.x, dz = z - t.z;
  return Math.abs(dx * ux + dz * uz) < w.towerHalf + r && Math.abs(-dx * uz + dz * ux) < w.towerHalf + r;
}

/** Dressed stone, a little lighter or darker piece by piece. */
const STONE: RGB = [178, 170, 156];
/** The wall goes this far into the ground (m), and the gateway's opening is this high. */
const FOOT = 1.6, GATEWAY = 5.2;
/** Merlons: this wide, high and deep, with gaps as wide between (m). */
const MERLON = { w: 1, h: 1, d: 0.6 };

/**
 * The wall's meshes in the building format, positions relative to `origin`: every piece (a stretch of the
 * ring, a tower, a gatehouse's span over its road) whose middle `pick` takes (a merge cell's; default all).
 * `detail` false: no merlons (the far version).
 */
export function wallMesh(w: TownWall, origin: [number, number, number], detail = true, pick: (x: number, z: number) => boolean = () => true): BuildingMesh {
  const out = new Out(new Frame({ cx: 0, cz: 0, ux: 1, uz: 0, vx: 0, vz: 1, y: 0 }, origin));
  const n = w.ring.length >> 1, R = w.ring;
  const shade = (x: number, z: number): RGB => { const k = 0.93 + 0.12 * hash2f(Math.round(x), Math.round(z), 5); return STONE.map((c) => Math.min(255, Math.round(c * k))) as RGB; };
  for (let i = 0; i < n; i++) {
    const j = (i + 1) % n, ax = R[i * 2], az = R[i * 2 + 1], bx = R[j * 2], bz = R[j * 2 + 1], mx = (ax + bx) / 2, mz = (az + bz) / 2;
    if (!pick(mx, mz) || w.gates.some((g) => Math.hypot(g.x - mx, g.z - mz) < g.half + w.towerHalf)) continue;
    const ya = w.ringY[i], yb = w.ringY[j];
    stretch(out, w, ax, az, bx, bz, Math.min(ya, yb) - FOOT, (ya + yb) / 2 + w.height, shade(mx, mz), detail);
  }
  for (const t of w.towers) if (pick(t.x, t.z)) tower(out, w, t, shade(t.x, t.z), detail);
  for (const g of w.gates) if (pick(g.x, g.z)) gateSpan(out, w, g, shade(g.x, g.z), detail);
  return {
    position: Float32Array.from(out.pos), normal: Float32Array.from(out.nrm), uv: Float32Array.from(out.uv),
    mat: Uint8Array.from(out.mat), tint: Uint8Array.from(out.tint), index: Uint32Array.from(out.idx),
  };
}

/** A box turned to `angle` round (x, z): a along the angle, b across, from y0 to y1. */
function turnedBox(o: Out, x: number, z: number, angle: number, a0: number, a1: number, b0: number, b1: number, y0: number, y1: number, c: RGB): void {
  const ux = Math.cos(angle), uz = Math.sin(angle), vx = -uz, vz = ux;
  const P = (a: number, y: number, b: number) => [x + ux * a + vx * b, y, z + uz * a + vz * b];
  const faces: [number[][], number[], number[][]][] = [
    [[P(a0, y0, b0), P(a1, y0, b0), P(a1, y1, b0), P(a0, y1, b0)], [-vx, 0, -vz], [[a0, y0], [a1, y0], [a1, y1], [a0, y1]]],
    [[P(a1, y0, b1), P(a0, y0, b1), P(a0, y1, b1), P(a1, y1, b1)], [vx, 0, vz], [[a1, y0], [a0, y0], [a0, y1], [a1, y1]]],
    [[P(a0, y0, b1), P(a0, y0, b0), P(a0, y1, b0), P(a0, y1, b1)], [-ux, 0, -uz], [[b1, y0], [b0, y0], [b0, y1], [b1, y1]]],
    [[P(a1, y0, b0), P(a1, y0, b1), P(a1, y1, b1), P(a1, y1, b0)], [ux, 0, uz], [[b0, y0], [b1, y0], [b1, y1], [b0, y1]]],
    [[P(a0, y1, b0), P(a1, y1, b0), P(a1, y1, b1), P(a0, y1, b1)], [0, 1, 0], [[a0, b0], [a1, b0], [a1, b1], [a0, b1]]],
  ];
  for (const [p, nrm, uv] of faces) o.quad(p, nrm, uv, BuildingMat.Ashlar, c);
}

/** Merlons along the outer edge of a top from a0 to a1 (at b, facing out), standing on y. */
function merlons(o: Out, x: number, z: number, angle: number, a0: number, a1: number, b: number, y: number, c: RGB): void {
  const L = a1 - a0, k = Math.max(1, Math.floor(L / (MERLON.w * 2))), step = L / k;
  for (let i = 0; i < k; i++) {
    const m = a0 + step * (i + 0.25);
    turnedBox(o, x, z, angle, m, m + MERLON.w, b - MERLON.d, b, y, y + MERLON.h, c);
  }
}

/** One stretch of the ring from a to b: the wall, its walk on top, merlons on the outside (to the right going round). */
function stretch(o: Out, w: TownWall, ax: number, az: number, bx: number, bz: number, y0: number, y1: number, c: RGB, detail: boolean): void {
  const L = Math.hypot(bx - ax, bz - az), angle = Math.atan2(bz - az, bx - ax), t = w.thick / 2;
  // The ring runs counter-clockwise: outside is to the right of the way it goes, which is −b in this frame.
  turnedBox(o, ax, az, angle, -0.15, L + 0.15, -t, t, y0, y1, c);
  if (detail) merlons(o, ax, az, angle + Math.PI, -L, 0, t, y1, c);
}

/** A tower: square, higher than the wall, merlons all round its top. */
function tower(o: Out, w: TownWall, t: TownTower, c: RGB, detail: boolean): void {
  const h = w.towerHalf, top = t.y + w.towerH;
  turnedBox(o, t.x, t.z, t.angle, -h, h, -h, h, t.y - FOOT, top, c);
  if (!detail) return;
  for (let k = 0; k < 4; k++) merlons(o, t.x, t.z, t.angle + (k * Math.PI) / 2, -h, h, h, top, c);
}

/** A gateway's arch: its half span (to the towers' faces and a little into them), and its spring and rise over the road, m. */
interface Arch { a: number; spring: number; rise: number }
const archOf = (g: TownGate): Arch => { const a = g.half + 0.2, rise = Math.min(a, 3.2); return { a, spring: g.y + GATEWAY + 0.6 - rise, rise }; };
/** The arch's underside `s` metres across the road from its middle (half an ellipse from tower to tower). */
const archY = (A: Arch, s: number): number => A.spring + A.rise * Math.sqrt(Math.max(0, 1 - (s / A.a) ** 2));
/** Pieces the arch is drawn in, and the width of the ring of darker voussoirs round it (m). */
const ARCH_SEG = 12, VOUSSOIR = 0.7;

/** A gate's own frame: a across the road (from tower to tower), b along it (+b into the town), y as the world's. */
function gateFrame(g: TownGate, origin: [number, number, number]): Frame {
  const across = g.angle + Math.PI / 2, ux = Math.cos(across), uz = Math.sin(across);
  return new Frame({ cx: g.x, cz: g.z, ux, uz, vx: -uz, vz: ux, y: 0 }, origin);
}

/** A gatehouse's span: the wall carried over the road between its two towers, an arch over the gateway below. */
function gateSpan(o: Out, w: TownWall, g: TownGate, c: RGB, detail: boolean): void {
  const A = archOf(g), b = w.thick / 2 + 0.6, top = g.y + w.height + 1.2;
  // World positions (the Out subtracts the origin), and directions, in the gate's frame.
  const F = gateFrame(g, [0, 0, 0]);
  const P = (s: number, y: number, d: number) => F.point(s, y, d), D = (s: number, d: number) => F.dir(s, 0, d);
  const ring = c.map((k) => Math.round(k * 0.84)) as RGB;
  const outer: Arch = { a: A.a + VOUSSOIR, spring: A.spring, rise: A.rise + VOUSSOIR };
  for (let k = 0; k < ARCH_SEG; k++) {
    const s0 = -A.a + (2 * A.a * k) / ARCH_SEG, s1 = s0 + (2 * A.a) / ARCH_SEG, y0 = archY(A, s0), y1 = archY(A, s1);
    // The faces, outside (-b) and in (+b), from the arch up to the top.
    for (const side of [-1, 1]) {
      const d = side * b;
      o.quad([P(s0, y0, d), P(s1, y1, d), P(s1, top, d), P(s0, top, d)], D(0, side), [[s0, y0], [s1, y1], [s1, top], [s0, top]], BuildingMat.Ashlar, c);
      // The voussoirs: a ring of darker stone round the arch, a hand proud of the face.
      if (detail) {
        const e = d + side * 0.04, z0 = archY(outer, s0), z1 = archY(outer, s1);
        o.quad([P(s0, y0, e), P(s1, y1, e), P(s1, z1, e), P(s0, z0, e)], D(0, side), [[s0, y0], [s1, y1], [s1, z1], [s0, z0]], BuildingMat.Ashlar, ring);
      }
    }
    // The arch's underside, facing in towards its middle.
    const sm = (s0 + s1) / 2, ym = archY(A, sm) - A.spring, nu = -sm / (A.a * A.a), ny = -ym / (A.rise * A.rise), nl = Math.hypot(nu, ny) || 1;
    const h = F.dir(nu, 0, 0), k2 = Math.abs(nu) / nl;
    o.quad([P(s0, y0, -b), P(s1, y1, -b), P(s1, y1, b), P(s0, y0, b)], [h[0] * k2, ny / nl, h[2] * k2], [[s0, -b], [s1, -b], [s1, b], [s0, b]], BuildingMat.Ashlar, ring);
  }
  o.quad([P(-A.a, top, -b), P(A.a, top, -b), P(A.a, top, b), P(-A.a, top, b)], [0, 1, 0], [[-A.a, -b], [A.a, -b], [A.a, b], [-A.a, b]], BuildingMat.Ashlar, c);
  const across = g.angle + Math.PI / 2;
  if (detail) for (const side of [1, -1]) merlons(o, g.x, g.z, across + (side > 0 ? 0 : Math.PI), -A.a, A.a, b, top, c);
}

/**
 * Oak planks and the iron that binds them. The oak layer is dark oak already (as a house's bare door, doorFace):
 * its tint lifts it, else the leaves read as black slabs at night. The iron bands stand proud of the planks.
 */
const GATE_OAK: RGB = [226, 191, 158], IRON: RGB = [150, 150, 158];
/** A plank's width, the seam between two, and its shade (m). */
const PLANK = 0.34, SEAM = 0.025, SEAM_OAK: RGB = [120, 96, 76];
/** An iron band's height, and how far it stands out of the leaf's faces (m). */
const BAND = 0.16, BAND_OUT = 0.04;
/** A leaf's thickness, and the gap between the two leaves and to the arch (m). */
const LEAF = 0.14, LEAF_GAP = 0.03;

/**
 * A gate's two leaves (`origin` as for `wallMesh`): oak with iron bands, hung inside the arch at its sides, shut;
 * each turns on its hinge (a game swings them: open by day, shut at night, opened for whoever comes).
 */
export function gateLeaves(w: TownWall, g: TownGate, origin: [number, number, number]): DoorLeaf[] {
  const A = archOf(g), F = gateFrame(g, origin), d0 = w.thick / 2 + 0.6 + 0.04, d1 = d0 + LEAF, inward = F.dir(0, 0, 1);
  const hingeS = g.half - 0.15, PIECES = 4;
  return [1, -1].map((side) => {
    const o = new Out(F);
    // From the hinge (s = side · hingeS) to the middle; each piece's top under the arch.
    const at = (k: number) => side * (hingeS - ((hingeS - LEAF_GAP) * k) / PIECES);
    for (let k = 0; k < PIECES; k++) {
      const s0 = at(k), s1 = at(k + 1), y0 = g.y, t0 = archY(A, s0) - LEAF_GAP, t1 = archY(A, s1) - LEAF_GAP;
      for (const [d, n] of [[d0, -1], [d1, 1]] as const) o.quad([[s0, y0, d], [s1, y0, d], [s1, t1, d], [s0, t0, d]], [0, 0, n], [[s0, y0], [s1, y0], [s1, t1], [s0, t0]], BuildingMat.Oak, GATE_OAK);
      const sg = Math.sign(s1 - s0);
      o.quad([[s0, t0, d0], [s1, t1, d0], [s1, t1, d1], [s0, t0, d1]], [-(t1 - t0) * sg, (s1 - s0) * sg, 0], [[s0, d0], [s1, d0], [s1, d1], [s0, d1]], BuildingMat.Oak, GATE_OAK);
    }
    // Its edges: at the hinge and where the leaves meet.
    for (const s of [at(0), at(PIECES)]) {
      const t = archY(A, s) - LEAF_GAP;
      o.quad([[s, g.y, d0], [s, g.y, d1], [s, t, d1], [s, t, d0]], [Math.sign(s) * (s === at(0) ? 1 : -1), 0, 0], [[d0, g.y], [d1, g.y], [d1, t], [d0, t]], BuildingMat.Oak, GATE_OAK);
    }
    // The planks' seams, dark lines down both faces.
    const lo = Math.min(at(0), at(PIECES)), hi = Math.max(at(0), at(PIECES));
    for (let s = lo + PLANK; s < hi - PLANK / 2; s += PLANK) {
      o.box(s - SEAM / 2, s + SEAM / 2, g.y + 0.05, archY(A, s) - LEAF_GAP - 0.05, d0 - 0.008, d1 + 0.008, BuildingMat.Oak, SEAM_OAK);
    }
    // Three iron bands across both faces, the top one under the arch's spring.
    for (const y of [g.y + 0.7, g.y + 1.9, A.spring - 0.3]) o.box(lo + 0.05, hi - 0.05, y, y + BAND, d0 - BAND_OUT, d1 + BAND_OUT, BuildingMat.Slate, IRON);
    const hinge = F.point(side * hingeS, g.y, (d0 + d1) / 2);
    // From the hinge the leaf runs towards the middle; opened it turns into the town, flat against the gatehouse.
    const dir = F.dir(-side, 0, 0), turned = [dir[2], -dir[0]];
    const open = (turned[0] * inward[0] + turned[1] * inward[2] > 0 ? 1 : -1) * (Math.PI / 2);
    return {
      mesh: { position: Float32Array.from(o.pos), normal: Float32Array.from(o.nrm), uv: Float32Array.from(o.uv), mat: Uint8Array.from(o.mat), tint: Uint8Array.from(o.tint), index: Uint32Array.from(o.idx) },
      hinge, open,
    };
  });
}

/** Whether a point is inside the wall's ring (the town's side). */
export const insideWall = (w: TownWall, x: number, z: number): boolean => pointInPoly(w.ring, x, z);

/** Where a road (from the middle outwards) first goes out through the ring, and its way there. */
function crossing(ring: Poly, road: readonly number[]): { x: number; z: number; angle: number } | null {
  const n = ring.length >> 1;
  for (let k = 0; k + 3 < road.length; k += 2) {
    const ax = road[k], az = road[k + 1], bx = road[k + 2], bz = road[k + 3];
    for (let i = 0; i < n; i++) {
      const j = (i + 1) % n;
      const t = segIntersect(ax, az, bx, bz, ring[i * 2], ring[i * 2 + 1], ring[j * 2], ring[j * 2 + 1]);
      if (t) return { x: ax + (bx - ax) * t[0], z: az + (bz - az) * t[0], angle: Math.atan2(bz - az, bx - ax) };
    }
  }
  return null;
}

/** The point `s` metres along a closed ring from its first corner. */
export function alongRing(ring: Poly, s: number): [number, number] {
  const n = ring.length >> 1;
  for (let i = 0; i < n; i++) {
    const j = (i + 1) % n, ax = ring[i * 2], az = ring[i * 2 + 1], bx = ring[j * 2], bz = ring[j * 2 + 1];
    const l = Math.hypot(bx - ax, bz - az);
    if (s <= l || i === n - 1) { const t = l ? Math.min(1, s / l) : 0; return [ax + (bx - ax) * t, az + (bz - az) * t]; }
    s -= l;
  }
  return [ring[0], ring[1]];
}

/** A closed ring resampled to corners about `step` metres apart. */
function evenRing(ring: Poly, step: number): Poly {
  const L = polyPerimeter(ring), n = Math.max(8, Math.round(L / step)), out: Poly = [];
  for (let i = 0; i < n; i++) out.push(...alongRing(ring, (i / n) * L));
  return out;
}
