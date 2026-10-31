/**
 * Small fish for ambient life (a shoal in the sea, fish in a river): one low-poly body that every fish shares,
 * drawn many at once (./three/batch.ts) by one shader (../node.ts `fishMaterial`). The body faces +z, its back is
 * +y, and it is one unit long (a fish's `size` is its length in metres). Each vertex carries how far back along
 * the body it sits (0 at the snout, 1 at the tail's tip), so the shader can sweep the body side to side, more
 * towards the tail, as a fish swims. Pure (no three.js).
 */
import { packPose, POSE_STRIDE } from './pose';

/** The shared body: positions (xyz), per vertex how far back it sits (0..1), triangles. */
export interface FishMesh {
  readonly positions: Float32Array;
  readonly back: Float32Array;
  readonly indices: Uint16Array;
}

/** Body rings from snout to the tail's root: z, half width, half height, the centre's height. */
const RINGS: readonly (readonly [number, number, number, number])[] = [
  [0.42, 0.03, 0.04, 0],
  [0.3, 0.07, 0.1, 0.005],
  [0.12, 0.085, 0.13, 0.01],
  [-0.08, 0.07, 0.11, 0.01],
  [-0.24, 0.035, 0.05, 0.005],
  [-0.32, 0.018, 0.028, 0],
];
const SIDES = 6;
/** The snout's tip and the tail fin's fork (z), and how tall the fin stands (half, y). */
const SNOUT = 0.5, TAIL_ROOT = -0.3, TAIL_TIP = -0.5, TAIL_SPAN = 0.15;

/** How far back a point at z sits: 0 at the snout, 1 at the tail's tip. */
const backOf = (z: number) => (SNOUT - z) / (SNOUT - TAIL_TIP);

export function fishMesh(): FishMesh {
  const pos: number[] = [], back: number[] = [], idx: number[] = [];
  const vert = (x: number, y: number, z: number) => {
    pos.push(x, y, z);
    back.push(backOf(z));
    return pos.length / 3 - 1;
  };
  const rings = RINGS.map(([z, hw, hh, cy]) => Array.from({ length: SIDES }, (_, k) => {
    const a = (k / SIDES) * Math.PI * 2 + Math.PI / 2;
    return vert(Math.cos(a) * hw, cy + Math.sin(a) * hh, z);
  }));
  const snout = vert(0, 0, SNOUT);
  for (let k = 0; k < SIDES; k++) {
    const k1 = (k + 1) % SIDES;
    idx.push(snout, rings[0][k1], rings[0][k]);
    for (let r = 0; r + 1 < rings.length; r++) {
      const a = rings[r][k], b = rings[r][k1], c = rings[r + 1][k], d = rings[r + 1][k1];
      idx.push(a, b, c, b, d, c);
    }
  }
  // The tail fin: upright, forked (two lobes from its root), and a little dorsal fin on the back.
  const root = vert(0, 0, TAIL_ROOT), up = vert(0, TAIL_SPAN, TAIL_TIP), fork = vert(0, 0, TAIL_TIP + 0.07), down = vert(0, -TAIL_SPAN, TAIL_TIP);
  idx.push(root, up, fork, root, fork, down);
  const d0 = vert(0, 0.12, 0.14), d1 = vert(0, 0.2, 0.02), d2 = vert(0, 0.1, -0.08);
  idx.push(d0, d1, d2);
  return { positions: Float32Array.from(pos), back: Float32Array.from(back), indices: Uint16Array.from(idx) };
}

/** One fish as drawn this frame. Angles in radians; positions in metres. */
export interface FishPose {
  x: number;
  y: number;
  z: number;
  /** Heading in the level plane: the direction it faces is (cos, sin) on (x, z). */
  heading: number;
  /** Snout up (+) or down (−). */
  pitch: number;
  /** Rolled over (+: right side down), as a fish turning hard flashes its flank. */
  roll: number;
  /** Length, metres (a sprat 0.12, a herring 0.3, a cod 0.8). */
  size: number;
  /** Where its sweep is now (radians; the game runs it on, faster the faster it swims). */
  phase: number;
  /** How far the tail sweeps (in body lengths at the tail's tip: 0.1 cruising, 0.2 darting). */
  sweep: number;
  /** Colour of the back, linear RGB; the flanks and belly are silvered. */
  r: number;
  g: number;
  b: number;
}

/** Floats per fish in each of the three instance attributes. */
export const FISH_STRIDE = POSE_STRIDE;

/**
 * Writes one fish's pose into the instance arrays at `i`, positions relative to `origin`:
 * place (x, y, z, turn about y), turn (pitch, roll, size, phase), look (r, g, b, sweep).
 */
export function packFish(p: FishPose, origin: { x: number; y: number; z: number }, place: Float32Array, turn: Float32Array, look: Float32Array, i: number): void {
  packPose(p, origin, [p.pitch, p.roll, p.size, p.phase], [p.r, p.g, p.b, p.sweep], place, turn, look, i);
}
