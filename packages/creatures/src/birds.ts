/**
 * Small birds for ambient life (songbirds, starlings, crows, pigeons): one low-poly body that every
 * bird shares, drawn many at once (./three/birds.ts) by one shader (../node.ts `birdMaterial`). The
 * body faces +z, its back is +y, and it is one unit long (a bird's `size` is its length in metres).
 * Each wing vertex carries its side and how far out along the wing it sits, so the shader can beat
 * the wings (curling the outer part more) or fold them along the back. Pure (no three.js).
 */

/** The shared body: positions (xyz), per vertex part (side −1/0/+1, span 0..1 out along the wing), triangles. */
export interface BirdMesh {
  readonly positions: Float32Array;
  readonly parts: Float32Array;
  readonly indices: Uint16Array;
}

/** Where a wing joins the body (|x|, in body lengths). */
export const BIRD_SHOULDER = 0.07;

/** Body rings from beak to rump: z, height of the centre, half width, half height. */
const RINGS: readonly (readonly [number, number, number, number])[] = [
  [0.4, 0.07, 0.05, 0.05],
  [0.32, 0.08, 0.075, 0.08],
  [0.22, 0.05, 0.065, 0.065],
  [0.06, 0.0, 0.12, 0.13],
  [-0.16, 0.0, 0.1, 0.1],
  [-0.3, 0.02, 0.045, 0.045],
];
const SIDES = 6;

/** Wing stations out from the shoulder: span 0..1, x, leading edge z, trailing edge z. */
const WING: readonly (readonly [number, number, number, number])[] = [
  [0, BIRD_SHOULDER, 0.13, -0.12],
  [0.5, 0.42, 0.11, -0.17],
  [1, 0.8, -0.04, -0.2],
];
const WING_Y = 0.07;

export function birdMesh(): BirdMesh {
  const pos: number[] = [], part: number[] = [], idx: number[] = [];
  const vert = (x: number, y: number, z: number, side = 0, span = 0) => {
    pos.push(x, y, z);
    part.push(side, span);
    return pos.length / 3 - 1;
  };
  // The body: rings joined by quads, closed by the beak's tip in front and the rump behind.
  const rings = RINGS.map(([z, cy, hw, hh]) => Array.from({ length: SIDES }, (_, k) => {
    const a = (k / SIDES) * Math.PI * 2;
    return vert(Math.cos(a) * hw, cy + Math.sin(a) * hh, z);
  }));
  const beak = vert(0, 0.06, 0.55);
  const rump = vert(0, 0.02, -0.33);
  for (let k = 0; k < SIDES; k++) {
    const k1 = (k + 1) % SIDES;
    idx.push(beak, rings[0][k1], rings[0][k]);
    for (let r = 0; r + 1 < rings.length; r++) {
      const a = rings[r][k], b = rings[r][k1], c = rings[r + 1][k], d = rings[r + 1][k1];
      idx.push(a, b, c, b, d, c);
    }
    const last = rings[rings.length - 1];
    idx.push(rump, last[k], last[k1]);
  }
  // The tail: a flat fan behind the rump.
  const t0 = vert(-0.04, 0.03, -0.26), t1 = vert(0.04, 0.03, -0.26), t2 = vert(-0.11, 0.0, -0.62), t3 = vert(0.11, 0.0, -0.62);
  idx.push(t0, t1, t2, t1, t3, t2);
  // The wings: a strip of two quads each side.
  for (const side of [-1, 1]) {
    const st = WING.map(([span, x, lead, trail]) => [vert(side * x, WING_Y, lead, side, span), vert(side * x, WING_Y, trail, side, span)]);
    for (let s = 0; s + 1 < st.length; s++) {
      const [a, b] = st[s], [c, d] = st[s + 1];
      if (side > 0) idx.push(a, c, b, b, c, d);
      else idx.push(a, b, c, b, d, c);
    }
  }
  return { positions: Float32Array.from(pos), parts: Float32Array.from(part), indices: Uint16Array.from(idx) };
}

/** One bird as drawn this frame. Angles in radians; positions in metres. */
export interface BirdPose {
  x: number;
  y: number;
  z: number;
  /** Heading in the ground plane: the direction it faces is (cos, sin) on (x, z). */
  heading: number;
  /** Nose up (+) or down (−). */
  pitch: number;
  /** Roll into a turn (+: right wing down). */
  bank: number;
  /** Length, metres (a sparrow 0.15, a starling 0.21, a crow 0.45). */
  size: number;
  /** The wings' beat now: up (+) or down (−) from level, radians. */
  wing: number;
  /** 0: wings spread; 1: folded along the back (perched, on the ground). */
  fold: number;
  /** Colour of the back, linear RGB; the belly is paler. */
  r: number;
  g: number;
  b: number;
}

/** Floats per bird in each of the three instance attributes. */
export const BIRD_STRIDE = 4;

/**
 * Writes one bird's pose into the instance arrays at `i`, positions relative to `origin`:
 * place (x, y, z, turn about y), turn (pitch, bank, size, wing), look (r, g, b, fold).
 */
export function packBird(p: BirdPose, origin: { x: number; y: number; z: number }, place: Float32Array, turn: Float32Array, look: Float32Array, i: number): void {
  const o = i * BIRD_STRIDE;
  place[o] = p.x - origin.x;
  place[o + 1] = p.y - origin.y;
  place[o + 2] = p.z - origin.z;
  // The body faces +z: turned by φ about y it faces (sin φ, cos φ), so φ = π/2 − heading.
  place[o + 3] = Math.PI / 2 - p.heading;
  turn[o] = p.pitch;
  turn[o + 1] = p.bank;
  turn[o + 2] = p.size;
  turn[o + 3] = p.wing;
  look[o] = p.r;
  look[o + 1] = p.g;
  look[o + 2] = p.b;
  look[o + 3] = p.fold;
}
