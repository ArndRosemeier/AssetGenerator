/**
 * Rocks for the land: boulders, blocks, slabs and spires, each a seeded mesh. A rock is a sphere, stretched
 * to its shape, cut by a few planes (the faces where it split), and roughened by noise; its foot is flat, at
 * y 0, so `seat` (@futuremagic/core) sets it on any ground. The same seed at a lower detail gives the same
 * rock with fewer triangles (a far level of detail).
 *
 * Colours are occlusion (linear grey, 3 per vertex): darker in the cuts' corners and toward the foot, where
 * the rock meets the ground. Pure: no three.js, no DOM.
 *
 * Frame: metres for a rock about 2 m across (scale it as it is placed), y up, its foot's middle at the origin.
 */
import { Noise, Rng, clamp } from '@futuremagic/core';

export const ROCK_SHAPES = ['boulder', 'block', 'slab', 'spire'] as const;
export type RockShape = (typeof ROCK_SHAPES)[number];

export interface RockMesh {
  readonly shape: RockShape;
  /** Metres, 3 per vertex. */
  readonly positions: Float32Array;
  /** Unit normals, 3 per vertex. */
  readonly normals: Float32Array;
  /** Occlusion as linear grey, 3 per vertex. */
  readonly colors: Float32Array;
  readonly indices: Uint32Array;
  /** Farthest any point lies from the foot's middle on the ground, metres (what a walker goes round). */
  readonly foot: number;
  /** Top, metres above the foot. */
  readonly height: number;
  /** Bounding sphere round (0, height / 2, 0). */
  readonly radius: number;
}

interface ShapeRule {
  /** Half sizes before the cuts, metres. */
  readonly size: readonly [number, number, number];
  /** How many planes cut it, and how deep (share of the radius left standing: lower cuts deeper). */
  readonly cuts: readonly [number, number];
  readonly keep: readonly [number, number];
  /** How much the cuts lie level (1: all horizontal, as a slab's strata) or upright (-1). */
  readonly level: number;
  /** Roughness by noise (share of the size). */
  readonly rough: number;
  /** Share of the height below the ground (the rest stands). */
  readonly buried: number;
  /** How boxy before the cuts: 2 round, 4 a rounded box (the exponent of its norm). */
  readonly box: number;
  /** Strata: how deep the bands of weathering cut in (share of the size), 0 for none. */
  readonly strata: number;
}

const RULES: Readonly<Record<RockShape, ShapeRule>> = {
  boulder: { size: [1.05, 0.8, 0.9], cuts: [3, 5], keep: [0.7, 0.88], level: 0, rough: 0.07, buried: 0.25, box: 2.6, strata: 0 },
  block: { size: [1.0, 0.85, 0.9], cuts: [6, 9], keep: [0.62, 0.85], level: 0.2, rough: 0.035, buried: 0.15, box: 4.5, strata: 0.03 },
  slab: { size: [1.25, 0.42, 0.95], cuts: [4, 6], keep: [0.65, 0.88], level: 0.6, rough: 0.04, buried: 0.2, box: 4, strata: 0.04 },
  spire: { size: [0.65, 1.7, 0.62], cuts: [5, 7], keep: [0.66, 0.86], level: -0.5, rough: 0.04, buried: 0.1, box: 4, strata: 0.06 },
};

/** Icosphere subdivisions by detail: 0 → 80 triangles, 1 → 320, 2 → 1280, 3 → 5120. */
export const ROCK_DETAILS = [0, 1, 2, 3] as const;

/** The rock of `shape` and `seed` at `detail` (0..3: subdivisions of its sphere). */
export function rockModel(shape: RockShape, seed: number, detail = 2): RockMesh {
  const rule = RULES[shape];
  const rng = new Rng(seed);
  const noise = new Noise(rng.nextU32());
  const { verts, tris } = icosphere(clamp(Math.round(detail), 0, 4));
  const n = verts.length / 3;
  // Its own proportions within the shape's.
  const sx = rule.size[0] * rng.range(0.85, 1.15), sy = rule.size[1] * rng.range(0.85, 1.15), sz = rule.size[2] * rng.range(0.85, 1.15);
  // The cutting planes: unit normals and how far out they stand.
  const cuts: number[] = [];
  for (let k = rng.int(rule.cuts[0], rule.cuts[1]); k > 0; k--) {
    let nx = rng.range(-1, 1), ny = rng.range(-1, 1), nz = rng.range(-1, 1);
    // Strata lie level, a spire's faces stand upright; the foot is never cut (the ground does that).
    ny = rule.level >= 0 ? ny * (1 - rule.level) + Math.sign(ny || 1) * rule.level : ny * (1 + rule.level);
    if (ny < -0.5) ny = -ny;
    const l = Math.hypot(nx, ny, nz) || 1;
    cuts.push(nx / l, ny / l, nz / l, rng.range(rule.keep[0], rule.keep[1]));
  }
  const pos = new Float32Array(n * 3), cutDepth = new Float32Array(n);
  for (let v = 0; v < n; v++) {
    const dx = verts[v * 3], dy = verts[v * 3 + 1], dz = verts[v * 3 + 2];
    // Noise first (round lumps), on the unit sphere so every level of detail samples the same field.
    const lump = 1 + rule.rough * (noise.fbm3(dx * 1.7, dy * 1.7, dz * 1.7, 3) * 2 + noise.fbm3(dx * 5.3 + 7, dy * 5.3, dz * 5.3, 2) * 0.6);
    // Onto a rounded box (the unit sphere of the `box` norm), then to its size.
    const m = rule.box, k = (Math.abs(dx) ** m + Math.abs(dy) ** m + Math.abs(dz) ** m) ** (-1 / m);
    // Strata: bands weathered in along the height (wavering, so they are not ruled lines).
    const band = rule.strata > 0 ? 1 - rule.strata * Math.abs(Math.sin(dy * sy * 7.5 + noise.n3(dx * 2, dy * 2, dz * 2) * 1.5)) : 1;
    let x = dx * k * sx * lump * band, y = dy * k * sy * lump, z = dz * k * sz * lump * band;
    // Each plane takes off what stands beyond it (in the rock's own scale: its radius along that normal).
    for (let k = 0; k < cuts.length; k += 4) {
      const cx = cuts[k], cy = cuts[k + 1], cz = cuts[k + 2];
      const reach = Math.hypot(cx * sx, cy * sy, cz * sz) * cuts[k + 3];
      const over = x * cx + y * cy + z * cz - reach;
      if (over > 0) {
        // A face that is not quite flat: a little of the lump stays on it.
        const keep = over * 0.08;
        x -= cx * (over - keep); y -= cy * (over - keep); z -= cz * (over - keep);
        cutDepth[v] = Math.max(cutDepth[v], over);
      }
    }
    pos[v * 3] = x; pos[v * 3 + 1] = y; pos[v * 3 + 2] = z;
  }
  // The foot: everything below the ground line is pressed flat onto it, then the rock is lifted so it sits at y 0.
  let lo = Infinity, hi = -Infinity;
  for (let v = 0; v < n; v++) { lo = Math.min(lo, pos[v * 3 + 1]); hi = Math.max(hi, pos[v * 3 + 1]); }
  const ground = lo + (hi - lo) * rule.buried;
  let foot = 0, height = 0, radius = 0;
  for (let v = 0; v < n; v++) {
    const y = Math.max(pos[v * 3 + 1], ground - (ground - pos[v * 3 + 1]) * 0.1) - ground;
    pos[v * 3 + 1] = y;
    height = Math.max(height, y);
    if (y < 0.3) foot = Math.max(foot, Math.hypot(pos[v * 3], pos[v * 3 + 2]));
  }
  for (let v = 0; v < n; v++) radius = Math.max(radius, Math.hypot(pos[v * 3], pos[v * 3 + 1] - height / 2, pos[v * 3 + 2]));
  const normals = vertexNormals(pos, tris);
  // Occlusion: darker toward the foot and in the cuts' inner corners (where two planes meet, the vertex was cut deep).
  const colors = new Float32Array(n * 3);
  for (let v = 0; v < n; v++) {
    const up = clamp(pos[v * 3 + 1] / Math.max(0.3, height * 0.5), 0, 1);
    const face = normals[v * 3 + 1];
    const ao = clamp((0.5 + 0.5 * up) * (1 - 0.25 * Math.min(1, cutDepth[v] * 1.5)) * (0.85 + 0.15 * Math.max(0, face)), 0.25, 1);
    colors[v * 3] = colors[v * 3 + 1] = colors[v * 3 + 2] = ao;
  }
  return { shape, positions: pos, normals, colors, indices: tris, foot, height, radius };
}

/** A unit icosphere: vertices (3 per) and triangles, `levels` times subdivided. */
function icosphere(levels: number): { verts: number[]; tris: Uint32Array } {
  const t = (1 + Math.sqrt(5)) / 2;
  const verts: number[] = [];
  const add = (x: number, y: number, z: number) => { const l = Math.hypot(x, y, z); verts.push(x / l, y / l, z / l); return verts.length / 3 - 1; };
  for (const [x, y, z] of [[-1, t, 0], [1, t, 0], [-1, -t, 0], [1, -t, 0], [0, -1, t], [0, 1, t], [0, -1, -t], [0, 1, -t], [t, 0, -1], [t, 0, 1], [-t, 0, -1], [-t, 0, 1]]) add(x, y, z);
  let faces = [0, 11, 5, 0, 5, 1, 0, 1, 7, 0, 7, 10, 0, 10, 11, 1, 5, 9, 5, 11, 4, 11, 10, 2, 10, 7, 6, 7, 1, 8, 3, 9, 4, 3, 4, 2, 3, 2, 6, 3, 6, 8, 3, 8, 9, 4, 9, 5, 2, 4, 11, 6, 2, 10, 8, 6, 7, 9, 8, 1];
  for (let l = 0; l < levels; l++) {
    const mid = new Map<number, number>();
    const m = (a: number, b: number) => {
      const key = a < b ? a * 1e6 + b : b * 1e6 + a;
      let i = mid.get(key);
      if (i === undefined) {
        i = add(verts[a * 3] + verts[b * 3], verts[a * 3 + 1] + verts[b * 3 + 1], verts[a * 3 + 2] + verts[b * 3 + 2]);
        mid.set(key, i);
      }
      return i;
    };
    const next: number[] = [];
    for (let f = 0; f < faces.length; f += 3) {
      const a = faces[f], b = faces[f + 1], c = faces[f + 2];
      const ab = m(a, b), bc = m(b, c), ca = m(c, a);
      next.push(a, ab, ca, b, bc, ab, c, ca, bc, ab, bc, ca);
    }
    faces = next;
  }
  return { verts, tris: Uint32Array.from(faces) };
}

/** Smooth normals: each vertex the area-weighted sum of its triangles' normals. */
function vertexNormals(pos: Float32Array, tris: Uint32Array): Float32Array {
  const out = new Float32Array(pos.length);
  for (let f = 0; f < tris.length; f += 3) {
    const a = tris[f] * 3, b = tris[f + 1] * 3, c = tris[f + 2] * 3;
    const ux = pos[b] - pos[a], uy = pos[b + 1] - pos[a + 1], uz = pos[b + 2] - pos[a + 2];
    const vx = pos[c] - pos[a], vy = pos[c + 1] - pos[a + 1], vz = pos[c + 2] - pos[a + 2];
    const nx = uy * vz - uz * vy, ny = uz * vx - ux * vz, nz = ux * vy - uy * vx;
    for (const i of [a, b, c]) { out[i] += nx; out[i + 1] += ny; out[i + 2] += nz; }
  }
  for (let i = 0; i < out.length; i += 3) {
    const l = Math.hypot(out[i], out[i + 1], out[i + 2]) || 1;
    out[i] /= l; out[i + 1] /= l; out[i + 2] /= l;
  }
  return out;
}
