/**
 * Where water touches the plan (pure): the planner asks a caller's `wet` at points, and a brook can be narrower than
 * a plot or the gap between two samples, so rings are walked a metre and a half at a time.
 */
import { polyCentroid, type Poly } from './geom2';

type Wet = (x: number, z: number) => boolean;

/** Samples along a ring's sides this far apart (m): a narrow brook (2 m) is not stepped over. */
export const WET_STEP = 1.5;

/** The first point along a closed ring's sides, `step` m apart, that is wet; null when dry all round. */
export function edgeWet(p: Poly, wet: Wet, step = WET_STEP): [number, number] | null {
  const n = p.length >> 1;
  for (let i = 0; i < n; i++) {
    const j = (i + 1) % n, ax = p[i * 2], az = p[i * 2 + 1], bx = p[j * 2], bz = p[j * 2 + 1];
    const k = Math.max(1, Math.ceil(Math.hypot(bx - ax, bz - az) / step));
    for (let s = 0; s < k; s++) {
      const x = ax + ((bx - ax) * s) / k, z = az + ((bz - az) * s) / k;
      if (wet(x, z)) return [x, z];
    }
  }
  return null;
}

/**
 * Every wet point along a closed ring's sides (`step` m apart), each at least `apart` m from those found before: where a
 * river runs along an edge, all the stretch it wets, not only its first point.
 */
export function edgeWets(p: Poly, wet: Wet, step = WET_STEP, apart = 12): [number, number][] {
  const out: [number, number][] = [];
  const n = p.length >> 1;
  for (let i = 0; i < n; i++) {
    const j = (i + 1) % n, ax = p[i * 2], az = p[i * 2 + 1], bx = p[j * 2], bz = p[j * 2 + 1];
    const k = Math.max(1, Math.ceil(Math.hypot(bx - ax, bz - az) / step));
    for (let s = 0; s < k; s++) {
      const x = ax + ((bx - ax) * s) / k, z = az + ((bz - az) * s) / k;
      if (wet(x, z) && !out.some(([ox, oz]) => Math.hypot(ox - x, oz - z) < apart)) out.push([x, z]);
    }
  }
  return out;
}

/** Whether water touches a polygon (a plot, a field, a farmstead): anywhere along its sides, or its middle. */
export function polyWet(p: Poly, wet: Wet): boolean {
  if (edgeWet(p, wet)) return true;
  const [x, z] = polyCentroid(p);
  return wet(x, z);
}

/** Whether water lies at (x, z) or anywhere `r` m round it (eight ways). */
export function wetNear(wet: Wet, x: number, z: number, r: number): boolean {
  if (wet(x, z)) return true;
  for (let a = 0; a < 8; a++) if (wet(x + Math.cos((a * Math.PI) / 4) * r, z + Math.sin((a * Math.PI) / 4) * r)) return true;
  return false;
}
