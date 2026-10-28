/**
 * A town wall (a capital's): a ring of stone round the town a little outside its edge track, a gate where
 * each road goes through it (a gatehouse with a tower each side), and towers along it between. Only the
 * plan: where the ring runs, where the gates and towers stand, how high; the game draws and walks it.
 * Pure.
 */
import { offset, shapesToPolys } from './clip';
import { chaikin, ensureCCW, pointInPoly, polyArea, polyPerimeter, segIntersect, type Poly } from './geom2';

export interface TownGate {
  /** Where the road goes through the ring (world metres), and the road's way out (radians, atan2(z, x)). */
  x: number;
  z: number;
  angle: number;
  /** Half the gateway's width, m (the road and a little more). */
  half: number;
  /** The road (index into the plan's roads) it lets through. */
  road: number;
}

export interface TownWall {
  /** The wall's middle line, closed, counter-clockwise. */
  ring: Poly;
  gates: TownGate[];
  /** Towers along it (gates' flanks first), x and z. */
  towers: [number, number][];
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

/** The wall round an outline, with a gate for each road that leaves through it. */
export function townWall(outline: Poly, roads: readonly number[][], rules: WallRules, roadWidth: number): TownWall {
  const grown = shapesToPolys(offset([outline], rules.out, 'round')).sort((a, b) => Math.abs(polyArea(b)) - Math.abs(polyArea(a)))[0] ?? outline;
  // A smooth, even line: the offset's corners rounded off, no tiny steps.
  const ring = ensureCCW(evenRing(chaikin([...grown, grown[0], grown[1]], 1).slice(0, -2), 6));
  const gates: TownGate[] = [];
  roads.forEach((road, ri) => {
    const hit = crossing(ring, road);
    if (hit) gates.push({ ...hit, half: roadWidth / 2 + 1, road: ri });
  });
  const towerHalf = 3, towers: [number, number][] = [];
  // Each gate between two towers.
  for (const g of gates) {
    const sx = -Math.sin(g.angle), sz = Math.cos(g.angle), w = g.half + towerHalf;
    towers.push([g.x + sx * w, g.z + sz * w], [g.x - sx * w, g.z - sz * w]);
  }
  // Then along the ring, about `every` apart, not crowding a gate.
  const L = polyPerimeter(ring), n = Math.max(3, Math.round(L / rules.every));
  for (let i = 0; i < n; i++) {
    const [x, z] = alongRing(ring, (i / n) * L);
    if (gates.some((g) => Math.hypot(g.x - x, g.z - z) < g.half + towerHalf * 2 + 8)) continue;
    if (towers.some(([tx, tz]) => Math.hypot(tx - x, tz - z) < rules.every * 0.5)) continue;
    towers.push([x, z]);
  }
  return { ring, gates, towers, height: rules.height, thick: 2.2, towerH: rules.height + 3.5, towerHalf };
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
