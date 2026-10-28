/**
 * Things set on the ground, so that no edge floats: a piece (a stone, a log, a barrel, a tent) is drawn at
 * y 0 of its own base, then `seat` lowers it to the lowest ground under its foot (a little deeper still, so
 * the drawn ground, straight between its vertices, does not show a gap either). On a slope the uphill side
 * goes into the ground, as a boulder's does. `floatOf` is the same measure turned round, for tests that scan
 * what was placed. Pure: the ground is any height function (terrain, cuts for brooks and roads, decks).
 */

/** The ground's height at (x, z), in the same frame as the piece's positions. */
export type Ground = (x: number, z: number) => number;

/** How much deeper than the lowest ground under it a piece is set by default, metres. */
export const SEAT_SINK = 0.05;
/** How far above a piece's lowest point its foot reaches (what stands on the ground; an awning or a top that overhangs does not), metres. */
export const SEAT_REACH = 0.5;

/** A piece's bottom (its lowest y) and the lowest ground under its foot (its points within `reach` of the bottom). */
export function footOf(ground: Ground, pos: ArrayLike<number>, from = 0, to = pos.length, reach = SEAT_REACH): { bottom: number; under: number } {
  let bottom = Infinity;
  for (let i = from + 1; i < to; i += 3) bottom = Math.min(bottom, pos[i]);
  let under = Infinity;
  for (let i = from; i + 2 < to; i += 3) {
    if (pos[i + 1] > bottom + reach) continue;
    under = Math.min(under, ground(pos[i], pos[i + 2]));
  }
  return { bottom, under };
}

/**
 * How far to move the piece in `pos[from..to)` (x, y, z triples) up (negative: down) so its foot is `sink`
 * below the lowest ground under it. 0 for no points.
 */
export function seatShift(ground: Ground, pos: ArrayLike<number>, from = 0, to = pos.length, sink = SEAT_SINK, reach = SEAT_REACH): number {
  const { bottom, under } = footOf(ground, pos, from, to, reach);
  return Number.isFinite(bottom) && Number.isFinite(under) ? under - sink - bottom : 0;
}

/** Set the piece in `pos[from..to)` on the ground (in place): see `seatShift`. Returns the shift. */
export function seat(ground: Ground, pos: { [i: number]: number; readonly length: number }, from = 0, to = pos.length, sink = SEAT_SINK, reach = SEAT_REACH): number {
  const dy = seatShift(ground, pos, from, to, sink, reach);
  for (let i = from + 1; i < to; i += 3) pos[i] += dy;
  return dy;
}

/**
 * How high the piece in `pos[from..to)` floats: its bottom over the lowest ground under its foot (positive:
 * a gap shows under some edge; 0 or less: it sits in the ground).
 */
export function floatOf(ground: Ground, pos: ArrayLike<number>, from = 0, to = pos.length, reach = SEAT_REACH): number {
  return -seatShift(ground, pos, from, to, 0, reach);
}

/**
 * The height to set a footprint's base at, before it is drawn: the lowest ground over a box `hx` × `hz`
 * (half sizes along its yaw and across) round (x, z), sampled at most a metre apart, less `sink`.
 */
export function seatHeight(ground: Ground, x: number, z: number, hx: number, hz: number, yaw = 0, sink = SEAT_SINK): number {
  const c = Math.cos(yaw), s = Math.sin(yaw);
  const nx = Math.max(1, Math.ceil(hx)), nz = Math.max(1, Math.ceil(hz));
  let low = Infinity;
  for (let i = -nx; i <= nx; i++) for (let j = -nz; j <= nz; j++) {
    const a = (i / nx) * hx, b = (j / nz) * hz;
    low = Math.min(low, ground(x + a * c + b * s, z - a * s + b * c));
  }
  return low - sink;
}
