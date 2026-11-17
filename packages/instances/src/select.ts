/**
 * Which instances are drawn, as plain math (no three.js): the rules the GPU culling pass (gpu.ts) runs per
 * instance and the CPU path (cpu.ts) runs per batch rebuild. Tests check both against these.
 */
import { smoothstep } from '@futuremagic/core';

/** Floats per instance record: a 4x4 matrix (column-major, like Matrix4.elements), kind, dither value, frame, one spare. */
export const RECORD = 20;
/**
 * Offsets in a record. FRAME: the moving frame the matrix is given in (DrawOptions.frames): 0 the world (as
 * before frames were added: old records keep working), k the frame `frames[k - 1]`, so a ship's fittings are
 * placed once in her own frame and move with her pose.
 */
export const KIND = 16, DITHER = 17, FRAME = 18;

/**
 * Where record `o`'s frame starts in `frames` (16 floats per frame, column-major, frame k at (k - 1) * 16), or -1
 * when the record is in the world (frame 0, or one not given).
 */
export function frameAt(rec: ArrayLike<number>, o: number, frames?: ArrayLike<number>): number {
  const k = rec[o + FRAME];
  return frames && k >= 1 && k * 16 <= frames.length && k === Math.floor(k) ? (k - 1) * 16 : -1;
}

/**
 * Record `o`'s matrix in the world: its frame's matrix times its own (16 floats into `out` at `at`). In the
 * world frame, a copy.
 */
export function worldMatrix(rec: ArrayLike<number>, o: number, frames: ArrayLike<number> | undefined, out: { [i: number]: number }, at = 0): void {
  const f = frameAt(rec, o, frames);
  if (f < 0) { for (let i = 0; i < 16; i++) out[at + i] = rec[o + i]; return; }
  const F = frames!;
  for (let c = 0; c < 4; c++) {
    const x = rec[o + c * 4], y = rec[o + c * 4 + 1], z = rec[o + c * 4 + 2], w = rec[o + c * 4 + 3];
    for (let r = 0; r < 4; r++) out[at + c * 4 + r] = F[f + r] * x + F[f + 4 + r] * y + F[f + 8 + r] * z + F[f + 12 + r] * w;
  }
}

/** A level of detail: drawn from `near` (default 0) up to `far` metres, optionally dithered out over `fade`. */
export interface LodRange {
  near?: number;
  far: number;
  /** Over [start, end] the instances drop out at random (those whose dither value is below the ramp), so a level has no hard edge. */
  fade?: readonly [number, number];
}

/** Whether an instance at distance `d` with dither value `h` (0..1) is drawn at this level. */
export function inLod(l: LodRange, d: number, h: number): boolean {
  if (d < (l.near ?? 0) || d >= l.far) return false;
  if (!l.fade) return true;
  const t = smoothstep(l.fade[0], l.fade[1], d);
  return !(t > 0 && h < t);
}

/**
 * A sphere against frustum planes (6 × [nx, ny, nz, d], inside where n·p + d >= 0). With `sweep` (the light's
 * direction times how far shadows reach) the sphere counts as visible when its shadow could fall into the
 * view: the sphere moved along the sweep stays in front of every plane at some point.
 */
export function sphereVisible(planes: ArrayLike<number>, x: number, y: number, z: number, r: number, sweep?: readonly [number, number, number]): boolean {
  for (let p = 0; p < 6; p++) {
    const nx = planes[p * 4], ny = planes[p * 4 + 1], nz = planes[p * 4 + 2];
    let d = nx * x + ny * y + nz * z + planes[p * 4 + 3];
    if (sweep) d += Math.max(0, nx * sweep[0] + ny * sweep[1] + nz * sweep[2]);
    if (d < -r) return false;
  }
  return true;
}

/** A record's bounding sphere: the kind's local sphere (cx, cy, cz, r) through the record's matrix (and its frame's, given `frames`). */
export function recordSphere(rec: ArrayLike<number>, o: number, local: readonly [number, number, number, number], frames?: ArrayLike<number>): [number, number, number, number] {
  if (frameAt(rec, o, frames) >= 0) {
    worldMatrix(rec, o, frames, _m);
    return recordSphere(_m, 0, local);
  }
  const [cx, cy, cz, r] = local;
  const x = rec[o] * cx + rec[o + 4] * cy + rec[o + 8] * cz + rec[o + 12];
  const y = rec[o + 1] * cx + rec[o + 5] * cy + rec[o + 9] * cz + rec[o + 13];
  const z = rec[o + 2] * cx + rec[o + 6] * cy + rec[o + 10] * cz + rec[o + 14];
  const s = Math.max(Math.hypot(rec[o], rec[o + 1], rec[o + 2]), Math.hypot(rec[o + 4], rec[o + 5], rec[o + 6]), Math.hypot(rec[o + 8], rec[o + 9], rec[o + 10]));
  return [x, y, z, r * s];
}

const _m = new Float64Array(16);

/** Distance from the camera to a point: in 3D, or across the ground (x, z) when `horizontal`. */
export function viewDistance(cam: readonly [number, number, number], x: number, y: number, z: number, horizontal: boolean): number {
  return horizontal ? Math.hypot(x - cam[0], z - cam[2]) : Math.hypot(x - cam[0], y - cam[1], z - cam[2]);
}

/**
 * Where each level's instances go in the shared output: level list `l` of kind `k` gets room for every
 * instance of that kind (the most it can ever hold), one after the other. `lists[k]` is the number of levels
 * of kind k; returns per list its first slot, and the total.
 */
export function listLayout(counts: readonly number[], lists: readonly number[]): { base: number[]; cap: number[]; total: number } {
  const base: number[] = [], cap: number[] = [];
  let total = 0;
  counts.forEach((n, k) => {
    for (let l = 0; l < lists[k]; l++) { base.push(total); cap.push(n); total += n; }
  });
  return { base, cap, total };
}

/**
 * Which level lists can hold an instance while the camera stays within `slack` metres of `cam`: a list is
 * in use when some instance of its kind has its sphere centre (the distance the cull measures) within
 * [near - slack, far + slack). The view is not tested (shadow casters outside it are drawn too). The GPU
 * path hides the parts of the lists not in use, so they cost no draw call: a town in a clearing had 40 of
 * its 70 tree draws empty, each a draw in the view and another in the sun's shadow map.
 * `local[k]` is kind k's local sphere, `ranges[l]` list l's levels, `listsOf[k]` the levels of kind k, `frames`
 * the moving frames as they stand now (see FRAME).
 */
export function listsInUse(
  rec: ArrayLike<number>, count: number, local: readonly (readonly [number, number, number, number])[],
  ranges: readonly LodRange[], listsOf: readonly number[], cam: readonly [number, number, number], horizontal: boolean, slack: number,
  frames?: ArrayLike<number>,
): boolean[] {
  const first: number[] = [];
  let l = 0;
  for (const n of listsOf) { first.push(l); l += n; }
  const used: boolean[] = ranges.map(() => false);
  let left = ranges.length;
  for (let i = 0; i < count && left > 0; i++) {
    const o = i * RECORD, k = rec[o + KIND];
    if (!(k >= 0 && k < listsOf.length)) continue;
    const [x, y, z] = recordSphere(rec, o, local[k], frames);
    const d = viewDistance(cam, x, y, z, horizontal);
    for (let j = first[k], end = first[k] + listsOf[k]; j < end; j++) {
      if (used[j]) continue;
      const r = ranges[j];
      if (d >= (r.near ?? 0) - slack && d < r.far + slack) { used[j] = true; left--; }
    }
  }
  return used;
}
