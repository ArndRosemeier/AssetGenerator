/**
 * A procedural creature's skin (docs/design/procedural-creatures.md): its anatomy's pieces
 * (src/creatures/anatomy.ts) blended with a smooth minimum into one signed distance field, sampled
 * on a grid around the body and meshed with surface nets, so neck flows into shoulders and haunch
 * into leg. Ported from Norgo's `creatureMesh.ts`, with smooth normals from the field itself, the
 * folds and hollows darkened (ambient occlusion from the field) and the coat painted per vertex.
 *
 * Pieces thinner than the grid can resolve (feelers, whiskers, claw tips) become explicit tubes and
 * balls, so nothing vanishes. Skin weights: each vertex is weighted to the bones of the pieces near
 * it (a soft minimum over their distances), so joints bend smoothly. The same weights blend what
 * the pieces are (skin, horn, shell, glow, mouth) and where they are (body, limb, head) into the
 * colour and the `look` the material reads (src/render/materials.ts `CRITTER`).
 *
 * Pure: typed arrays out, no three.js, so it runs in a worker.
 */
import { Noise, cellular3, clamp, lerp, mixRgb, smin, smoothstep } from '@futuremagic/core';
import type { Anatomy, Prim, V3 } from './anatomy';
import { PAD, surfaceNets } from '@futuremagic/volume';
import type { Integument, Rgb, Species } from './bestiary';

/** A creature's mesh: indexed, skinned to its anatomy's bones. */
export interface FleshData {
  readonly positions: Float32Array;
  readonly normals: Float32Array;
  /** The painted coat, ambient occlusion in it (linear rgb). */
  readonly colors: Float32Array;
  /** Per vertex: roughness, the integument (`INTEGUMENT` index / 8), glow (0..1), see-through (0..1). */
  readonly looks: Float32Array;
  readonly skinIndex: Uint16Array;
  readonly skinWeight: Float32Array;
  readonly indices: Uint32Array;
}

/** The integuments in the order the material's `look.y` counts them. */
export const INTEGUMENT: readonly Integument[] = ['fur', 'hide', 'scales', 'chitin', 'slime', 'stone'];

// ------------------------------------------------------------------ pieces as distance fields

interface Frame {
  readonly p: Prim;
  readonly ax: number; readonly ay: number; readonly az: number;
  readonly sxv: V3;
  readonly upv: V3;
  readonly len: number;
  readonly min: V3;
  readonly max: V3;
  /** Its largest radius. */
  readonly rad: number;
}

function primFrame(p: Prim): Frame {
  let ax = p.b[0] - p.a[0], ay = p.b[1] - p.a[1], az = p.b[2] - p.a[2];
  let l = Math.hypot(ax, ay, az);
  const ell = p.type === 'ellipsoid';
  if (ell || l < 1e-6) { ax = 0; ay = 0; az = 1; l = ell ? 0 : 1e-6; } else { ax /= l; ay /= l; az /= l; }
  let rx = 0, ry = 1, rz = 0;
  if (Math.abs(ay) > 0.95) { rx = 0; ry = 0; rz = 1; }
  let sx = ry * az - rz * ay, sy = rz * ax - rx * az, sz = rx * ay - ry * ax;
  const sl = Math.hypot(sx, sy, sz) || 1;
  sx /= sl; sy /= sl; sz /= sl;
  const ux = ay * sz - az * sy, uy = az * sx - ax * sz, uz = ax * sy - ay * sx;
  const rad = ell ? p.ra * Math.max(p.sx, p.sy, p.b[0]) : Math.max(p.ra, p.rb) * Math.max(p.sx, p.sy);
  const bx = ell ? p.a : p.b;
  const min: V3 = [Math.min(p.a[0], bx[0]) - rad, Math.min(p.a[1], bx[1]) - rad, Math.min(p.a[2], bx[2]) - rad];
  const max: V3 = [Math.max(p.a[0], bx[0]) + rad, Math.max(p.a[1], bx[1]) + rad, Math.max(p.a[2], bx[2]) + rad];
  return { p, ax, ay, az, sxv: [sx, sy, sz], upv: [ux, uy, uz], len: l, min, max, rad };
}

/** Distance to one piece (Inigo Quilez's round cone, ellipsoid and rounded box, in a squashed frame). */
function sdPiece(f: Frame, x: number, y: number, z: number): number {
  const p = f.p;
  const px = x - p.a[0], py = y - p.a[1], pz = z - p.a[2];
  if (p.type === 'ellipsoid') {
    const rx = p.ra * p.sx, ry = p.ra * p.sy, rz = p.ra * p.b[0];
    const k0 = Math.hypot(px / rx, py / ry, pz / rz);
    const k1 = Math.hypot(px / (rx * rx), py / (ry * ry), pz / (rz * rz));
    return k1 > 1e-9 ? (k0 * (k0 - 1)) / k1 : -Math.min(rx, ry, rz);
  }
  const t = px * f.ax + py * f.ay + pz * f.az;
  const s = px * f.sxv[0] + py * f.sxv[1] + pz * f.sxv[2];
  const u = px * f.upv[0] + py * f.upv[1] + pz * f.upv[2];
  if (p.type === 'box') {
    const hl = f.len / 2;
    const hx = p.ra * p.sx, hy = p.ra * p.sy;
    const rr = Math.min(hx, hy) * 0.25;
    const qx = Math.abs(s) - hx + rr, qy = Math.abs(u) - hy + rr, qz = Math.abs(t - hl) - hl + rr;
    return Math.hypot(Math.max(qx, 0), Math.max(qy, 0), Math.max(qz, 0)) + Math.min(Math.max(qx, Math.max(qy, qz)), 0) - rr;
  }
  const ss = s / p.sx, uu = u / p.sy;
  const scale = Math.min(p.sx, p.sy);
  const r1 = p.ra, r2 = p.rb, h = f.len;
  const q = Math.hypot(ss, uu);
  const b = (r1 - r2) / h;
  const a = Math.sqrt(Math.max(0, 1 - b * b));
  const k = -q * b + t * a;
  let d: number;
  if (k < 0) d = Math.hypot(q, t) - r1;
  else if (k > a * h) d = Math.hypot(q, t - h) - r2;
  else d = q * a + t * b - r1;
  return d * scale;
}


/** The blended field of `frames` at a point (positive outside). */
function field(frames: readonly Frame[], x: number, y: number, z: number): number {
  let d = 1e3;
  for (const f of frames) {
    const m = f.p.k + 0.02;
    if (x < f.min[0] - m - d || y < f.min[1] - m - d || z < f.min[2] - m - d || x > f.max[0] + m + d || y > f.max[1] + m + d || z > f.max[2] + m + d) continue;
    d = smin(d, sdPiece(f, x, y, z), Math.max(f.p.k, 1e-6));
  }
  return d;
}

// ------------------------------------------------------------------ building

class Mesh {
  readonly pos: number[] = [];
  readonly nor: number[] = [];
  readonly col: number[] = [];
  readonly look: number[] = [];
  readonly skinI: number[] = [];
  readonly skinW: number[] = [];
  readonly idx: number[] = [];
  get count(): number { return this.pos.length / 3; }
}

/** What a vertex is made of, from the pieces near it. */
interface Blend {
  bones: number[];
  weights: number[];
  /** Shares of keratin, shell, glow, mouth. */
  part: [number, number, number, number];
  /** Shares of limb and head. */
  region: [number, number];
}

const PART_VEC: readonly (readonly number[])[] = [[0, 0, 0, 0], [1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]];
const REGION_VEC: readonly (readonly number[])[] = [[0, 0], [1, 0], [0, 1]];

/**
 * Mesh `anatomy` for `species`, `res` grid cells along its longest side (64 for close up). Its
 * coat is painted from the species' colours and pattern.
 */
export function fleshOf(anatomy: Anatomy, species: Species, res = 64): FleshData {
  const ext = Math.max(anatomy.max[0] - anatomy.min[0], anatomy.max[1] - anatomy.min[1], anatomy.max[2] - anatomy.min[2]);
  // A long thin body (a snake) gets enough cells across its girth.
  const girth = species.length * species.girth * Math.min(species.bodyWidth, species.bodyHeight);
  const h = ext / Math.min(128, Math.max(res, (ext / girth) * 5));
  const frames = anatomy.prims.map(primFrame);
  const thin = h * 1.3;
  const solid: Frame[] = [], fine: Frame[] = [];
  for (const f of frames) {
    const p = f.p;
    const minR = p.type === 'ellipsoid' ? p.ra * Math.min(p.sx, p.sy, p.b[0]) : Math.max(p.ra, p.rb) * Math.min(p.sx, p.sy);
    (minR < thin && p.type !== 'box' ? fine : solid).push(f);
  }
  const m = new Mesh();
  const paint = new Painter(species, anatomy);
  nets(anatomy, solid, frames, h, m, paint);
  for (const f of fine) {
    if (f.p.type === 'ellipsoid') ball(f, 8, m, paint);
    else thinTube(f, 8, m, paint);
  }
  return {
    positions: new Float32Array(m.pos),
    normals: new Float32Array(m.nor),
    colors: new Float32Array(m.col),
    looks: new Float32Array(m.look),
    skinIndex: new Uint16Array(m.skinI),
    skinWeight: new Float32Array(m.skinW),
    indices: new Uint32Array(m.idx),
  };
}

function nets(an: Anatomy, sdf: readonly Frame[], all: readonly Frame[], h: number, m: Mesh, paint: Painter): void {
  if (!sdf.length) return;
  let maxK = 0;
  for (const f of sdf) maxK = Math.max(maxK, f.p.k);
  // A cube of samples round the body (surfaceNets' grid), its faces built inside the padding.
  const pad = (PAD + 2) * h + maxK * 0.3;
  const ox = an.min[0] - pad, oy = an.min[1] - pad, oz = an.min[2] - pad;
  const n = Math.ceil((Math.max(an.max[0] - an.min[0], an.max[1] - an.min[1], an.max[2] - an.min[2]) + pad * 2) / h) + 1;
  const nn = n * n;
  const d = new Float32Array(n * nn).fill(1e3);
  // Each piece only into its own box (grown by its blend).
  for (const f of sdf) {
    const k = f.p.k, g = k + 2 * h;
    const i0 = Math.max(0, Math.floor((f.min[0] - g - ox) / h)), i1 = Math.min(n - 1, Math.ceil((f.max[0] + g - ox) / h));
    const j0 = Math.max(0, Math.floor((f.min[1] - g - oy) / h)), j1 = Math.min(n - 1, Math.ceil((f.max[1] + g - oy) / h));
    const k0 = Math.max(0, Math.floor((f.min[2] - g - oz) / h)), k1 = Math.min(n - 1, Math.ceil((f.max[2] + g - oz) / h));
    for (let kk = k0; kk <= k1; kk++) {
      const z = oz + kk * h;
      for (let j = j0; j <= j1; j++) {
        const y = oy + j * h;
        let idx = i0 + j * n + kk * nn;
        for (let i = i0; i <= i1; i++, idx++) d[idx] = smin(d[idx], sdPiece(f, ox + i * h, y, z), Math.max(k, 1e-6));
      }
    }
  }
  const mesh = surfaceNets({ n, d }, ox + PAD * h, oy + PAD * h, oz + PAD * h, h);
  if (!mesh) return;
  const blend = newBlend(an.bones.length);
  const e = h * 0.5;
  const base = m.count;
  const P = mesh.positions;
  for (let v = 0; v < P.length; v += 3) {
    const x = P[v], y = P[v + 1], z = P[v + 2];
    // The normal from the field itself (central differences), smoother than the grid's.
    let gx = field(sdf, x + e, y, z) - field(sdf, x - e, y, z);
    let gy = field(sdf, x, y + e, z) - field(sdf, x, y - e, z);
    let gz = field(sdf, x, y, z + e) - field(sdf, x, y, z - e);
    const gl = Math.hypot(gx, gy, gz) || 1;
    gx /= gl; gy /= gl; gz /= gl;
    // Hollows and folds: how much the field closes in just outside the skin.
    let occ = 0;
    for (let s = 1; s <= 3; s++) {
      const dd = h * 1.6 * s;
      occ += Math.max(0, dd - field(sdf, x + gx * dd, y + gy * dd, z + gz * dd)) / dd / s;
    }
    const ao = clamp(1 - occ * 0.55, 0.35, 1);
    blendAt(all, x, y, z, h, blend);
    vertex(m, paint, x, y, z, gx, gy, gz, blend, ao);
  }
  for (const i of mesh.indices) m.idx.push(base + i);
}

function newBlend(bones: number): Blend & { acc: Float64Array; ds: number[] } {
  return { bones: [0, 0, 0, 0], weights: [0, 0, 0, 0], part: [0, 0, 0, 0], region: [0, 0], acc: new Float64Array(bones), ds: [] };
}

/** Skin weights and what the vertex is made of, from the distances to the pieces near it. */
function blendAt(all: readonly Frame[], x: number, y: number, z: number, h: number, out: Blend & { acc: Float64Array; ds: number[] }): void {
  const acc = out.acc, ds = out.ds;
  acc.fill(0);
  out.part.fill(0);
  out.region.fill(0);
  let dmin = 1e9;
  for (let i = 0; i < all.length; i++) {
    const f = all[i];
    const g = f.rad + f.p.k + 4 * h;
    if (x < f.min[0] - g || y < f.min[1] - g || z < f.min[2] - g || x > f.max[0] + g || y > f.max[1] + g || z > f.max[2] + g) { ds[i] = 1e9; continue; }
    const d = sdPiece(f, x, y, z);
    ds[i] = d;
    if (d < dmin) dmin = d;
  }
  let total = 0;
  for (let i = 0; i < all.length; i++) {
    if (ds[i] > 1e8) continue;
    const f = all[i];
    const sigma = Math.max(h * 0.7, f.p.k * 0.45 + f.rad * 0.08);
    const w = Math.exp(-(ds[i] - dmin) / sigma);
    if (w < 1e-4) continue;
    acc[f.p.bone] += w;
    const pv = PART_VEC[f.p.part];
    for (let c = 0; c < 4; c++) out.part[c] += pv[c] * w;
    const rv = REGION_VEC[f.p.region];
    out.region[0] += rv[0] * w; out.region[1] += rv[1] * w;
    total += w;
  }
  if (total <= 0) total = 1;
  for (let c = 0; c < 4; c++) out.part[c] /= total;
  out.region[0] /= total; out.region[1] /= total;
  topFour(acc, out.bones, out.weights);
}

function topFour(acc: Float64Array, bones: number[], w: number[]): void {
  for (let s = 0; s < 4; s++) { bones[s] = 0; w[s] = 0; }
  for (let b = 0; b < acc.length; b++) {
    const v = acc[b];
    if (v <= 0) continue;
    for (let s = 0; s < 4; s++) {
      if (v > w[s]) {
        for (let t = 3; t > s; t--) { w[t] = w[t - 1]; bones[t] = bones[t - 1]; }
        w[s] = v;
        bones[s] = b;
        break;
      }
    }
  }
  const sw = w[0] + w[1] + w[2] + w[3] || 1;
  for (let s = 0; s < 4; s++) w[s] /= sw;
}

function vertex(m: Mesh, paint: Painter, x: number, y: number, z: number, nx: number, ny: number, nz: number, b: Blend, ao: number): number {
  m.pos.push(x, y, z);
  m.nor.push(nx, ny, nz);
  for (let i = 0; i < 4; i++) { m.skinI.push(b.bones[i]); m.skinW.push(b.weights[i]); }
  paint.coat(x, y, z, ny, b, ao, m.col, m.look);
  return m.count - 1;
}

// ------------------------------------------------------------------ thin pieces

function thinTube(f: Frame, sides: number, m: Mesh, paint: Painter): void {
  const p = f.p;
  const b = one(p);
  const [sx, sy, sz] = f.sxv, [ux, uy, uz] = f.upv;
  const ax = f.ax, ay = f.ay, az = f.az;
  // A spindle, not a pipe: a thin limb's segment swells along its middle (where its muscle is) and
  // narrows into its joints.
  const along = [0.25, 0.5, 0.75].map((t) => ({ t, r: lerp(p.ra, p.rb, t) * (1 + 0.32 * Math.sin(Math.PI * t)), off: 0, nAx: 0 }));
  const rings = [
    { t: 0, r: p.ra * 0.7, off: -p.ra * 0.7, nAx: -0.7 },
    { t: 0, r: p.ra, off: 0, nAx: 0 },
    ...along,
    { t: 1, r: p.rb, off: 0, nAx: 0 },
    { t: 1, r: p.rb * 0.7, off: p.rb * 0.7, nAx: 0.7 },
  ];
  const start = m.count;
  vertex(m, paint, p.a[0] - ax * p.ra, p.a[1] - ay * p.ra, p.a[2] - az * p.ra, -ax, -ay, -az, b, 1);
  for (const ring of rings) {
    const cx = p.a[0] + (p.b[0] - p.a[0]) * ring.t + ax * ring.off;
    const cy = p.a[1] + (p.b[1] - p.a[1]) * ring.t + ay * ring.off;
    const cz = p.a[2] + (p.b[2] - p.a[2]) * ring.t + az * ring.off;
    for (let s = 0; s < sides; s++) {
      const a = (s / sides) * Math.PI * 2;
      const cs = Math.cos(a) * p.sx, sn = Math.sin(a) * p.sy;
      const rx = sx * cs + ux * sn, ry = sy * cs + uy * sn, rz = sz * cs + uz * sn;
      const nr = Math.sqrt(1 - ring.nAx * ring.nAx);
      vertex(m, paint, cx + rx * ring.r, cy + ry * ring.r, cz + rz * ring.r, rx * nr + ax * ring.nAx, ry * nr + ay * ring.nAx, rz * nr + az * ring.nAx, b, 1);
    }
  }
  const poleB = vertex(m, paint, p.b[0] + ax * p.rb, p.b[1] + ay * p.rb, p.b[2] + az * p.rb, ax, ay, az, b, 1);
  for (let s = 0; s < sides; s++) {
    const s1 = (s + 1) % sides;
    m.idx.push(start, start + 1 + s1, start + 1 + s);
    for (let r = 0; r < rings.length - 1; r++) {
      const a0 = start + 1 + r * sides + s, a1 = start + 1 + r * sides + s1;
      m.idx.push(a0, a1, a1 + sides, a0, a1 + sides, a0 + sides);
    }
    const last = start + 1 + (rings.length - 1) * sides;
    m.idx.push(last + s, last + s1, poleB);
  }
}

function ball(f: Frame, seg: number, m: Mesh, paint: Painter): void {
  const p = f.p;
  const b = one(p);
  const rx = p.ra * p.sx, ry = p.ra * p.sy, rz = p.ra * p.b[0];
  const start = m.count;
  const rows = Math.max(4, Math.round(seg * 0.6));
  for (let r = 0; r <= rows; r++) {
    const th = (r / rows) * Math.PI;
    for (let s = 0; s <= seg; s++) {
      const ph = (s / seg) * Math.PI * 2;
      const nx = Math.sin(th) * Math.cos(ph), ny = Math.cos(th), nz = Math.sin(th) * Math.sin(ph);
      const l = Math.hypot(nx / rx, ny / ry, nz / rz) || 1;
      vertex(m, paint, p.a[0] + nx * rx, p.a[1] + ny * ry, p.a[2] + nz * rz, nx / rx / l, ny / ry / l, nz / rz / l, b, 1);
    }
  }
  for (let r = 0; r < rows; r++)
    for (let s = 0; s < seg; s++) {
      const a = start + r * (seg + 1) + s, c = a + seg + 1;
      m.idx.push(a, a + 1, c + 1, a, c + 1, c);
    }
}

/** A thin piece is all one bone and one part. */
function one(p: Prim): Blend {
  const pv = PART_VEC[p.part], rv = REGION_VEC[p.region];
  return { bones: [p.bone, 0, 0, 0], weights: [1, 0, 0, 0], part: [pv[0], pv[1], pv[2], pv[3]], region: [rv[0], rv[1]] };
}

// ------------------------------------------------------------------ the coat

/** Paints a species' coat onto its vertices: pattern, countershading, horn and shell, glow, the folds. */
class Painter {
  private readonly noise: Noise;
  private readonly seed: number;
  private readonly lin: Record<'base' | 'secondary' | 'belly' | 'accent' | 'glow' | 'keratin', Rgb>;
  private readonly integ: number;

  constructor(private readonly sp: Species, private readonly an: Anatomy) {
    this.seed = sp.seed;
    this.noise = new Noise(sp.seed ^ 0x5eed);
    const c = sp.colors;
    this.lin = { base: lin(c.base), secondary: lin(c.secondary), belly: lin(c.belly), accent: lin(c.accent), glow: lin(c.glow), keratin: lin(c.keratin) };
    this.integ = INTEGUMENT.indexOf(sp.integument);
  }

  coat(x: number, y: number, z: number, ny: number, b: Blend, ao: number, col: number[], look: number[]): void {
    const sp = this.sp, c = sp.colors, L = sp.length;
    // Rest space, in torso lengths: patterns grow with the body.
    const px = x / L, py = y / L, pz = z / L;
    const sc = c.patternScale;
    const warp = this.noise.fbm3(px * 2.1, py * 2.1, pz * 2.1, 2) * 0.5;
    let mk = 0;
    switch (c.pattern) {
      case 'stripes': mk = smoothstep(0.15, 0.55, Math.sin((pz * sc + py * 0.8 + warp * 1.6) * Math.PI * 2)) * smoothstep(-0.6, 0.1, ny); break;
      case 'spots': { const cl = cellular3(this.seed, px * sc * 1.4, py * sc * 1.4, pz * sc * 1.4); mk = 1 - smoothstep(0.22, 0.34, cl.f1 + warp * 0.15); break; }
      case 'bands': mk = smoothstep(0.42, 0.58, frac(pz * sc * 0.55 + warp * 0.25)); break;
      case 'patches': mk = smoothstep(-0.05, 0.08, this.noise.fbm3(px * sc * 0.45, py * sc * 0.45, pz * sc * 0.45, 3)); break;
      case 'mottled': mk = smoothstep(-0.2, 0.35, this.noise.fbm3(px * sc * 1.8, py * sc * 1.8, pz * sc * 1.8, 3)); break;
      case 'saddle': mk = smoothstep(0.1, 0.5, ny + warp * 0.6) * (1 - b.region[0]); break;
      case 'eyespots': { const cl = cellular3(this.seed, px * sc * 0.55, py * sc * 0.55, pz * sc * 0.55); const d = cl.f1; mk = smoothstep(0.2, 0.24, d) * (1 - smoothstep(0.3, 0.34, d)) + (1 - smoothstep(0.1, 0.14, d)) * 2; break; }
    }
    mk *= c.patternContrast * (1 - b.region[0] * 0.55);
    let rgb = mixRgb(this.lin.base, this.lin.secondary, clamp(mk, 0, 1));
    if (c.pattern === 'eyespots' && mk > 1) rgb = mixRgb(rgb, this.lin.accent, clamp(mk - 1, 0, 1));
    // Countershading: a pale belly and a darker back.
    const under = smoothstep(0.15, -0.55, ny);
    rgb = mixRgb(rgb, this.lin.belly, under * c.countershade);
    const top = 1 - smoothstep(0.4, 1, ny) * 0.14 * c.countershade;
    // Points: head and feet a little darker.
    const points = 1 - b.region[0] * 0.1 - b.region[1] * 0.06;
    // Fine mottling everywhere, so no skin is flat paint.
    const fine = 1 + this.noise.n3(px * 40, py * 40, pz * 40) * 0.07;
    rgb = [rgb[0] * top * points * fine, rgb[1] * top * points * fine, rgb[2] * top * points * fine];
    // Horn, shell, mouth, glow.
    const [ker, shell, glowP, mouth] = b.part;
    rgb = mixRgb(rgb, this.lin.keratin, ker);
    const shellRgb = mixRgb(mixRgb(this.lin.secondary, this.lin.base, 0.35), [0.02, 0.02, 0.02], 0.25);
    rgb = mixRgb(rgb, shellRgb, shell * (sp.integument === 'chitin' ? 0.5 : 0.85));
    rgb = mixRgb(rgb, [0.28, 0.07, 0.08], mouth * 0.85);
    // Glow: a lure or sac, and dots or lines on the skin.
    let glow = glowP;
    if (c.glowAmount > 0) {
      let g = 0;
      if (c.glowStyle === 0) { const cl = cellular3(this.seed + 7, px * 16, py * 16, pz * 16); g = (1 - smoothstep(0.08, 0.16, cl.f1)) * (cl.id & 1 ? 0 : 1) * smoothstep(0.6, -0.2, ny + 0.3); }
      else if (c.glowStyle === 1) g = 1 - smoothstep(0, 0.05, Math.abs(frac(pz * 4 + py * 0.5) - 0.5) - 0.42);
      else g = 0.35;
      glow = Math.max(glow, g * c.glowAmount);
    }
    rgb = mixRgb(rgb, this.lin.glow, clamp(glow * 1.2, 0, 1));
    const shade = lerp(ao, 1, glow);
    col.push(rgb[0] * shade, rgb[1] * shade, rgb[2] * shade);
    const rough = lerp(lerp(c.roughness, 0.35, ker), 0.3, shell);
    look.push(rough, (this.integ + 0.5) / 8, clamp(glow, 0, 1), c.translucent * (1 - ker));
    void this.an;
  }
}

function frac(v: number): number {
  return v - Math.floor(v);
}

/** sRGB to linear. */
function lin(c: Rgb): Rgb {
  const f = (v: number) => (v <= 0.04045 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4));
  return [f(c[0]), f(c[1]), f(c[2])];
}
