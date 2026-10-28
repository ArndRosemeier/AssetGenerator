/**
 * A town wall (a capital's): a ring of stone round the town a little outside its edge track, a gate where
 * each road goes through it (a gatehouse with a tower each side), and towers along it between. The plan
 * (`townWall`: where the ring runs, the ground under it, where the gates and towers stand, how high), its
 * meshes in the building format (`wallMesh`, drawn with the buildings' shader) and what it blocks
 * (`wallBlocks`: a walker goes through the gates only). Pure.
 */
import { hash2f } from '@futuremagic/core';
import { BuildingMat, Frame, Out, type BuildingMesh, type RGB } from './building';
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
  roads.forEach((road, ri) => {
    const hit = crossing(ring, road);
    if (hit) gates.push({ ...hit, half: roadWidth / 2 + 1, road: ri, y: height(hit.x, hit.z) });
  });
  const towerHalf = 3, towers: TownTower[] = [];
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

/** A gatehouse's span: the wall carried over the road between its two towers, the gateway open below. */
function gateSpan(o: Out, w: TownWall, g: TownGate, c: RGB, detail: boolean): void {
  // Across the road (a) from tower to tower, along it (b) the wall's depth and a little more.
  const across = g.angle + Math.PI / 2, a = g.half + 0.2, b = w.thick / 2 + 0.6, top = g.y + w.height + 1.2;
  turnedBox(o, g.x, g.z, across, -a, a, -b, b, g.y + GATEWAY, top, c);
  // The gateway's underside (seen from the road below).
  const ux = Math.cos(across), uz = Math.sin(across), vx = -uz, vz = ux, y = g.y + GATEWAY;
  const P = (s: number, d: number) => [g.x + ux * s + vx * d, y, g.z + uz * s + vz * d];
  o.quad([P(-a, -b), P(a, -b), P(a, b), P(-a, b)], [0, -1, 0], [[-a, -b], [a, -b], [a, b], [-a, b]], BuildingMat.Ashlar, c);
  if (detail) for (const side of [1, -1]) merlons(o, g.x, g.z, across + (side > 0 ? 0 : Math.PI), -a, a, b, top, c);
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
