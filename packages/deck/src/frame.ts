/**
 * A deck's frame: where it stands in the world and how it is turned (pure). A ship's pose on the waves becomes a
 * `Frame` (each game has its own pose: heading, pitch, roll, its own axes), and everything else here works on frames:
 * a point of the deck in the world and back, where the world's vertical through a spot meets one of its levels, and
 * which way gravity's up points in the deck's own frame.
 *
 * The frame's own axes are x, y, z with y up on the deck (a ship's height over her waterline, or over her base);
 * which way x and z point along and across her is the game's business.
 */

/** A point or a direction: x, y, z. */
export interface Vec3 {
  x: number;
  y: number;
  z: number;
}

/**
 * A rigid frame: its origin in the world, and its rotation (row-major 3 × 3, the frame's axes into the world's):
 * world = origin + rotation · local.
 */
export interface Frame {
  readonly origin: Vec3;
  readonly rotation: ArrayLike<number>;
}

/** Entries of a 3 × 3 rotation. */
export const ROTATION_ENTRIES = 9;

/** A point of the frame (x, y, z in its own axes) in the world. */
export function frameToWorld(f: Frame, x: number, y: number, z: number, out: Vec3 = { x: 0, y: 0, z: 0 }): Vec3 {
  const r = f.rotation, o = f.origin;
  const wx = o.x + r[0]! * x + r[1]! * y + r[2]! * z;
  const wy = o.y + r[3]! * x + r[4]! * y + r[5]! * z;
  const wz = o.z + r[6]! * x + r[7]! * y + r[8]! * z;
  out.x = wx; out.y = wy; out.z = wz;
  return out;
}

/** A world point in the frame's own axes (the rotation's transpose: it is a rotation). */
export function frameToLocal(f: Frame, x: number, y: number, z: number, out: Vec3 = { x: 0, y: 0, z: 0 }): Vec3 {
  const r = f.rotation, o = f.origin, dx = x - o.x, dy = y - o.y, dz = z - o.z;
  const lx = r[0]! * dx + r[3]! * dy + r[6]! * dz;
  const ly = r[1]! * dx + r[4]! * dy + r[7]! * dz;
  const lz = r[2]! * dx + r[5]! * dy + r[8]! * dz;
  out.x = lx; out.y = ly; out.z = lz;
  return out;
}

/** A world direction in the frame's own axes (gravity's up on a heeled deck: `upInFrame`). */
export function directionToLocal(f: Frame, x: number, y: number, z: number, out: Vec3 = { x: 0, y: 0, z: 0 }): Vec3 {
  const r = f.rotation;
  const lx = r[0]! * x + r[3]! * y + r[6]! * z;
  const ly = r[1]! * x + r[4]! * y + r[7]! * z;
  const lz = r[2]! * x + r[5]! * y + r[8]! * z;
  out.x = lx; out.y = ly; out.z = lz;
  return out;
}

/** Gravity's up (the world's +y) in the frame's own axes: (0, 1, 0) on a level deck, leaning as she heels and pitches. */
export const upInFrame = (f: Frame, out: Vec3 = { x: 0, y: 0, z: 0 }): Vec3 => directionToLocal(f, 0, 1, 0, out);

/** Where the world's vertical through (x, z) meets a level of the frame: the frame's x and z there, and the world's y. */
export interface Crossing {
  x: number;
  z: number;
  y: number;
}

/** Below this a vertical runs along a level and meets it nowhere (the frame lying on its side). */
const PARALLEL = 1e-6;

/**
 * Where the world's vertical through (x, z) meets the frame's level `level` (its own y): the frame's x and z there,
 * and the world's height. A point moves linearly in the frame as it moves up the vertical, so this is exact.
 */
export function vertical(f: Frame, x: number, z: number, level: number, out: Crossing = { x: 0, y: 0, z: 0 }): Crossing {
  // Up the vertical a metre, the frame's point moves by the world's up in the frame (the rotation's second row).
  const r = f.rotation, l0 = frameToLocal(f, x, f.origin.y, z, scratch);
  const k = Math.abs(r[4]!) > PARALLEL ? (level - l0.y) / r[4]! : 0;
  out.x = l0.x + r[3]! * k; out.z = l0.z + r[5]! * k; out.y = f.origin.y + k;
  return out;
}
const scratch: Vec3 = { x: 0, y: 0, z: 0 };
