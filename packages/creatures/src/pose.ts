/**
 * Small creatures drawn many at once (birds, fish: ./three/batch.ts): each instance's pose packed into three
 * attributes of four floats, its place relative to an origin near the camera. Pure (no three.js).
 */

/** Floats per instance in each of the three instance attributes. */
export const POSE_STRIDE = 4;

/**
 * Writes one instance at `i`: place (x, y, z relative to `origin`, the turn about y that faces the body's +z along
 * `heading`), turn (four floats of the kind's own), look (four floats of the kind's own).
 */
export function packPose(
  at: { readonly x: number; readonly y: number; readonly z: number; readonly heading: number }, origin: { readonly x: number; readonly y: number; readonly z: number },
  turn4: readonly [number, number, number, number], look4: readonly [number, number, number, number],
  place: Float32Array, turn: Float32Array, look: Float32Array, i: number,
): void {
  const o = i * POSE_STRIDE;
  place[o] = at.x - origin.x;
  place[o + 1] = at.y - origin.y;
  place[o + 2] = at.z - origin.z;
  // The body faces +z: turned by φ about y it faces (sin φ, cos φ), so φ = π/2 − heading.
  place[o + 3] = Math.PI / 2 - at.heading;
  for (let k = 0; k < 4; k++) { turn[o + k] = turn4[k]; look[o + k] = look4[k]; }
}
