/**
 * A square-rigged ship's rig as the climb knows it, pure geometry in the climb's frame (a ship's own frame: the
 * climb is played there and carried into the world by her pose, as MasterWorld's ship ladders are):
 *
 *  - Shrouds with their ratlines are a ladder leaning in towards the mast (`Ladder.lean` > 0), climbed with the
 *    hands on the shrouds (`holds: 'sides'`) and the feet on the ratlines, which give a little under a foot.
 *  - Futtock shrouds run from the futtock stave, a little under the top, out to the top's rim: a ladder that
 *    leans out over the climber (`lean` < 0), got off over the rim onto the top. The shrouds' holds go on to the
 *    futtock shrouds above the stave (`Ladder.above`), so the hands are on them while the feet still climb the
 *    ratlines.
 *  - A yard with its footrope (`Yard`): men stand on the rope abaft the yard, lean over it and hold the jackstay
 *    on top, and sidle out along it (`LadderClimb`'s 'footrope' and 'yard' steps).
 *
 * `shroudWays` makes the two ladders of a mast's shrouds from four points of the rig.
 */
import type { Ladder } from './ladder';

/** A yard and its footrope. Heights are the climb's frame's (a ship's: up from her waterline, say). */
export interface Yard {
  /** The top of the yard at its middle (the slings), where the jackstay runs. */
  x: number;
  y: number;
  z: number;
  /** Unit vector along the yard (to one yardarm; the other is the opposite way), level. */
  ax: number;
  az: number;
  /** From the middle out to where the footrope ends at each yardarm (m). */
  reach: number;
  /** Unit vector, level, from the men on the footrope to the yard: they stand abaft it, facing it. */
  nx: number;
  nz: number;
  /** How far the footrope hangs under the jackstay at its stirrups (m, default 1.0). */
  drop?: number;
  /** How far it sags between stirrups (m, default 0.1), and how far apart the stirrups are (m, default 2.4). */
  sag?: number;
  stirrup?: number;
  /** Where the footrope starts, out from the middle (m, default 0.5: the slings and the mast are inside it). */
  inner?: number;
  /** How far a foot pushes the rope down under the man's weight (m, default 0.05). */
  give?: number;
}

/** A footrope's usual drop under the jackstay (m). */
export const FOOTROPE_DROP = 1.0;
/** How far abaft the yard's top the footrope hangs, loaded (m). */
export const FOOTROPE_AFT = 0.28;

/** The footrope's height at `s` metres out along the yard (signed: + along (ax, az)), unloaded. */
export function footropeY(yard: Yard, s: number): number {
  const drop = yard.drop ?? FOOTROPE_DROP, sag = yard.sag ?? 0.1, st = yard.stirrup ?? 2.4, inner = yard.inner ?? 0.5;
  // Between two stirrups (or the slings and the first) the rope hangs in a curve.
  const f = Math.max(0, Math.abs(s) - inner) / st, u = f - Math.floor(f);
  return yard.y - drop - sag * 4 * u * (1 - u);
}

/**
 * A point by the yard: `s` metres out along it, `a` metres towards it from the line the footrope hangs under its
 * top (+: towards the yard, past it forward), at height `h`.
 */
export function yardPoint(yard: Yard, s: number, a: number, h: number, out: { x: number; y: number; z: number }): void {
  out.x = yard.x + yard.ax * s + yard.nx * (a - FOOTROPE_AFT);
  out.y = h;
  out.z = yard.z + yard.az * s + yard.nz * (a - FOOTROPE_AFT);
}

/** Where a mast's shrouds are on one side, in the climb's frame. */
export interface ShroudRig {
  /** The middle of the shrouds' feet: at the deadeyes in the channel (or wherever their foot is). */
  foot: readonly [number, number, number];
  /** The middle of the shrouds at the futtock stave, a little under the top: where the futtock shrouds start (moved down to a whole stride of the gait: `futtock.lo`). */
  stave: readonly [number, number, number];
  /** The middle of the futtock shrouds' heads at the top's rim, and the top's floor (its height). */
  rim: readonly [number, number, number];
  /** Where one gets on the shrouds: the height of the rail or channel stood on (m). */
  floor: number;
  /** The ratlines' spacing (m, default 0.38: fifteen inches). */
  rung?: number;
  /** Half the width of the shrouds between the hands (m, default 0.3). */
  halfWidth?: number;
}

/** The usual ratline spacing (m). */
export const RATLINE = 0.38;

/**
 * The two ladders of a mast's shrouds on one side: the shrouds, leaning in from their feet, got on at `floor`,
 * whose holds go on to the futtock shrouds above the stave (`above`, and `below` back); and the futtock shrouds, leaning out to the rim, got
 * off over it onto the top. Their rungs are in step (the futtock shrouds' lowest rung a whole stride of the
 * gait over `floor`), so a climb goes from one to the other without a stumble.
 */
export function shroudWays(r: ShroudRig): { shroud: Ladder; futtock: Ladder } {
  const rung = r.rung ?? RATLINE, half = r.halfWidth ?? 0.3, step = 2 * rung;
  const [fx, fy, fz] = r.foot, [sx, sy, sz] = r.stave, [rx, ry, rz] = r.rim;
  // Facing in: level, from the shrouds' feet towards the stave.
  const hx = sx - fx, hz = sz - fz, hl = Math.hypot(hx, hz) || 1, nx = hx / hl, nz = hz / hl;
  const lean = hl / (sy - fy);
  // The rungs' line at a height: the shrouds' line through the foot.
  const shroudAt = (y: number): [number, number] => [fx + nx * lean * (y - fy), fz + nz * lean * (y - fy)];
  const [x0, z0] = shroudAt(r.floor);
  // The futtock shrouds start a whole number of strides over the floor, at or under the stave (the rig plan puts
  // the stave there: `futtock.lo`), from the shrouds' line out to the rim.
  const lo = r.floor + Math.max(1, Math.floor((sy - r.floor) / step)) * step;
  const [x1, z1] = shroudAt(lo);
  // Leaning out over the climber (negative): the rim is outboard of the stave, towards the climber.
  const fl = ((rx - x1) * nx + (rz - z1) * nz) / (ry - lo);
  const futtock: Ladder = { x: x1, z: z1, nx, nz, lo, hi: ry - rung / 2, floor: ry, halfWidth: half * 0.8, rim: true, rung, lean: fl, holds: 'sides', give: 0.03 };
  const shroud: Ladder = { x: x0, z: z0, nx, nz, lo: r.floor + rung, hi: lo, floor: r.floor, halfWidth: half, rim: false, rung, lean, holds: 'sides', give: 0.04, above: futtock };
  futtock.below = shroud;
  return { shroud, futtock };
}
