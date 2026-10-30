/**
 * A harbour for a town by the sea: a quay along the waterline, piers out into the water and berths for ships along
 * them. The town planner asks for it when its site names the shore (`TownSite.harbour`); the same planner for every
 * size, a bigger town only gets a longer quay and more piers. Pure.
 */
import { Rng } from '@futuremagic/core';
import { ensureCCW, type Poly } from './geom2';
import { planShip, type ShipPlan } from './ship';
import { BuildingMat, Frame, Out, mergeOuts, type BuildingMesh, type RGB } from './building';

/** Where a harbour goes: a point on the shore near the town and the way out to sea from it (a unit vector). */
export interface HarbourSite {
  x: number;
  z: number;
  dx: number;
  dz: number;
}

/** A pier: a timber deck on piles from the quay's edge out over the water. */
export interface Pier {
  /** Its root at the quay's edge and its head out in the water. */
  x0: number;
  z0: number;
  x1: number;
  z1: number;
  /** Half its width, m. */
  half: number;
  /** Its deck's height. */
  deckY: number;
}

/** A ship's place at a pier: its middle, its heading (radians, atan2(z, x), along the pier), and the length it has. */
export interface Berth {
  x: number;
  z: number;
  yaw: number;
  length: number;
  /** The pier it lies at, and on which side (1: its left looking out, -1: its right). */
  pier: number;
  side: 1 | -1;
  /** Water under it, m. */
  depth: number;
}

export interface HarbourPlan {
  /** The quay's front, along the waterline (x, z, …), and the way out to sea at each of its points (x, z, …). */
  edge: number[];
  out: number[];
  /** The quay's back, inland of each front point (x, z, …): QUAY_DEPTH m past the waterline. */
  back: number[];
  /** The quay: a paved strip from its front to its back, closed, counter-clockwise. */
  quay: Poly;
  /** The quay's top. */
  quayY: number;
  piers: Pier[];
  berths: Berth[];
}

/** How deep inland the quay runs from the water, m. */
export const QUAY_DEPTH = 12;
/** The quay stands this high over the sea at least, m (and as high as the ground behind it, up to QUAY_TOP). */
const QUAY_LOW = 1.4, QUAY_TOP = 3;
/** The quay's front stands in this much water (m), so a boat comes alongside it and the sea washes its face, not a strand. */
const QUAY_WATER = 1.2;
/** Steps along the coast and out to sea, m. */
const STEP = 4;
/** A pier: as long as it takes to reach this depth (m), between these lengths. */
const PIER_DEPTH = 3.5, PIER_MIN = 24, PIER_MAX = 72;
const PIER_HALF = 2.2;
/** One pier for about every this many metres of quay, at most PIERS_MAX. */
const PIER_EVERY = 48, PIERS_MAX = 4;
/** A berth keeps this far from the pier's root (m), and a ship's beam with room to spare is this (m). */
const BERTH_ROOT = 8, BEAM = 6;
/** The longest ship a berth is for, m. */
const SHIP_MAX = 34;

/**
 * The harbour of a town round (cx, cz) with radius `R` (its quay within `R * reach` of the middle), on the shore at
 * `site`; null where the shore there gives no quay of `minLength` metres. `water(x, z)` > 0 in the water, its depth.
 */
export function planHarbour(site: HarbourSite, cx: number, cz: number, R: number, height: (x: number, z: number) => number, water: (x: number, z: number) => number, reach = 1.15, minLength = 30): HarbourPlan | null {
  const tx = -site.dz, tz = site.dx;
  // The quay's front along the coast: from inland, out to sea past the strand until the water is QUAY_WATER deep.
  const line: { x: number; z: number; t: number; strand: number }[] = [];
  const span = R * reach * 1.4;
  for (let t = -span; t <= span; t += STEP) {
    const bx = site.x + tx * t - site.dx * 40, bz = site.z + tz * t - site.dz * 40;
    if (water(bx, bz) > 0) continue;
    let wet = -1;
    for (let s = 0; s < 200; s += 1) {
      const x = bx + site.dx * s, z = bz + site.dz * s, w = water(x, z);
      if (w > 0 && wet < 0) wet = s;
      if (w >= QUAY_WATER) {
        if (Math.hypot(x - cx, z - cz) <= R * reach) line.push({ x, z, t, strand: s - wet });
        break;
      }
    }
  }
  // The longest unbroken run of it (the waterline jumps where a cove or a point comes in), the one nearest the site among equals.
  const runs: (typeof line)[] = [];
  for (const p of line) {
    const run = runs[runs.length - 1], last = run?.[run.length - 1];
    if (last && p.t - last.t <= STEP + 1e-6 && Math.hypot(p.x - last.x, p.z - last.z) < STEP * 2.5) run.push(p);
    else runs.push([p]);
  }
  const lengthOf = (r: typeof line) => r.length * STEP;
  const best = runs.reduce<typeof line | null>((a, r) => (!a || lengthOf(r) > lengthOf(a) ? r : a), null);
  if (!best || lengthOf(best) < minLength) return null;
  // Smoothed (the waterline is in 1 m steps), each point with the way out to sea across the quay's own line.
  const n = best.length, edge: number[] = [], out: number[] = [], deep: number[] = [];
  for (let i = 0; i < n; i++) {
    let x = 0, z = 0, d = 0, k = 0;
    for (let j = Math.max(0, i - 2); j <= Math.min(n - 1, i + 2); j++) { x += best[j].x; z += best[j].z; d += best[j].strand; k++; }
    edge.push(x / k, z / k);
    deep.push(d / k + QUAY_DEPTH);
  }
  for (let i = 0; i < n; i++) {
    const a = Math.max(0, i - 1), b = Math.min(n - 1, i + 1);
    let ux = edge[b * 2] - edge[a * 2], uz = edge[b * 2 + 1] - edge[a * 2 + 1];
    const l = Math.hypot(ux, uz) || 1;
    ux /= l; uz /= l;
    // Of the two normals, the one out to sea.
    const s = -uz * site.dx + ux * site.dz >= 0 ? 1 : -1;
    out.push(-uz * s, ux * s);
  }
  // The quay's top: over the sea, and as high as the ground at its back.
  const back: number[] = [];
  for (let i = 0; i < n; i++) back.push(edge[i * 2] - out[i * 2] * deep[i], edge[i * 2 + 1] - out[i * 2 + 1] * deep[i]);
  let ground = 0;
  for (let i = 0; i < n; i++) ground = Math.max(ground, height(back[i * 2], back[i * 2 + 1]));
  const quayY = Math.min(QUAY_TOP, Math.max(QUAY_LOW, ground));
  const quay: Poly = [];
  for (let i = 0; i < n; i++) quay.push(edge[i * 2], edge[i * 2 + 1]);
  for (let i = n - 1; i >= 0; i--) quay.push(back[i * 2], back[i * 2 + 1]);
  const quayCCW = ensureCCW(quay);
  // Piers, spread along the quay, out to where ships float.
  const count = Math.max(1, Math.min(PIERS_MAX, Math.floor(lengthOf(best) / PIER_EVERY)));
  const piers: Pier[] = [], berths: Berth[] = [];
  for (let p = 0; p < count; p++) {
    const i = Math.min(n - 1, Math.max(0, Math.round(((p + 0.5) / count) * (n - 1))));
    const x0 = edge[i * 2], z0 = edge[i * 2 + 1], ox = out[i * 2], oz = out[i * 2 + 1];
    let len = PIER_MIN;
    while (len < PIER_MAX && water(x0 + ox * len, z0 + oz * len) < PIER_DEPTH) len += 2;
    const pier: Pier = { x0, z0, x1: x0 + ox * len, z1: z0 + oz * len, half: PIER_HALF, deckY: quayY };
    const id = piers.length;
    piers.push(pier);
    // A berth either side, beyond the shallows by the root.
    // Out at the head, where the water is deepest; as long as the pier gives, up to SHIP_MAX.
    const shipLen = Math.min(SHIP_MAX, len - BERTH_ROOT - 2);
    if (shipLen < 12) continue;
    for (const side of [1, -1] as const) {
      const along = len - 1 - shipLen / 2, off = PIER_HALF + BEAM / 2 + 1;
      const x = x0 + ox * along - oz * off * side, z = z0 + oz * along + ox * off * side;
      const depth = water(x, z);
      if (depth < 2) continue;
      berths.push({ x, z, yaw: Math.atan2(oz, ox), length: shipLen, pier: id, side, depth });
    }
  }
  return { edge, out, back, quay: quayCCW, quayY, piers, berths };
}

/** Distance (m) from (x, z) to a pier's deck rectangle (negative inside, as far as its half width goes). */
export function pierDist(p: Pier, x: number, z: number): number {
  const L = Math.hypot(p.x1 - p.x0, p.z1 - p.z0) || 1, ux = (p.x1 - p.x0) / L, uz = (p.z1 - p.z0) / L;
  const a = (x - p.x0) * ux + (z - p.z0) * uz, b = -(x - p.x0) * uz + (z - p.z0) * ux;
  const qa = Math.max(-a, a - L), qb = Math.abs(b) - p.half;
  return Math.hypot(Math.max(qa, 0), Math.max(qb, 0)) + Math.min(Math.max(qa, qb), 0);
}

/** Stone and timber of the harbour. */
const QUAY_STONE: RGB = [178, 170, 156];
const PAVING: RGB = [196, 188, 172];
const DECK: RGB = [150, 122, 92];
const PILE: RGB = [78, 62, 50];
const BOLLARD: RGB = [70, 60, 52];
/** How far below the sea bed the quay's face and the piles reach (m), and how deep they go at least. */
const SUNK = 0.6, LOWEST = -2;
/** Piles along a pier every this many metres. */
const PILE_EVERY = 4;

/**
 * The harbour as one mesh in the building format, positions relative to `origin`: the quay's paving, its stone face
 * down into the water and its back down to the ground behind it; each pier's deck, its piles down into the bed and
 * its bollards. `detail` false leaves out the bollards and every other pile.
 */
export function harbourMesh(h: HarbourPlan, height: (x: number, z: number) => number, origin: [number, number, number], detail = true): BuildingMesh {
  const o = new Out(new Frame({ cx: 0, cz: 0, ux: 1, uz: 0, vx: 0, vz: 1, y: 0 }, origin));
  const n = h.edge.length >> 1, y = h.quayY;
  const E = (i: number) => [h.edge[i * 2], h.edge[i * 2 + 1]];
  const B = (i: number) => [h.back[i * 2], h.back[i * 2 + 1]];
  const bed = (x: number, z: number) => Math.min(LOWEST, height(x, z) - SUNK);
  for (let i = 0; i < n - 1; i++) {
    const [ax, az] = E(i), [bx, bz] = E(i + 1), [cx, cz] = B(i + 1), [dx, dz] = B(i);
    // Paving (local frame is the world's: a = x, b = z).
    o.quad([[ax, y, az], [bx, y, bz], [cx, y, cz], [dx, y, dz]], [0, 1, 0], [[ax, az], [bx, bz], [cx, cz], [dx, dz]], BuildingMat.Ashlar, PAVING);
    // The face to the sea, down past the bed.
    const fx = (h.out[i * 2] + h.out[i * 2 + 2]) / 2, fz = (h.out[i * 2 + 1] + h.out[i * 2 + 3]) / 2;
    const s0 = i * 4, s1 = s0 + Math.hypot(bx - ax, bz - az);
    o.quad([[ax, y, az], [bx, y, bz], [bx, bed(bx, bz), bz], [ax, bed(ax, az), az]], [fx, 0, fz], [[s0, y], [s1, y], [s1, bed(bx, bz)], [s0, bed(ax, az)]], BuildingMat.Ashlar, QUAY_STONE);
    // The back, down to the ground where it lies lower than the quay.
    const g0 = Math.min(y, height(dx, dz) - 0.2), g1 = Math.min(y, height(cx, cz) - 0.2);
    if (g0 < y - 0.05 || g1 < y - 0.05) o.quad([[dx, y, dz], [cx, y, cz], [cx, g1, cz], [dx, g0, dz]], [-fx, 0, -fz], [[s0, y], [s1, y], [s1, g1], [s0, g0]], BuildingMat.Ashlar, QUAY_STONE);
  }
  // The quay's two ends, closed down to the bed.
  for (const [i, s] of [[0, -1], [n - 1, 1]] as const) {
    const [ax, az] = E(i), [dx, dz] = B(i), k = Math.min(n - 1, Math.max(0, i - s)), tx = h.edge[i * 2] - h.edge[k * 2], tz = h.edge[i * 2 + 1] - h.edge[k * 2 + 1];
    o.quad([[ax, y, az], [dx, y, dz], [dx, Math.min(y, height(dx, dz) - 0.2), dz], [ax, bed(ax, az), az]], [tx, 0, tz], [[0, y], [Math.hypot(dx - ax, dz - az), y], [Math.hypot(dx - ax, dz - az), 0], [0, bed(ax, az)]], BuildingMat.Ashlar, QUAY_STONE);
  }
  const outs = [o];
  for (const p of h.piers) {
    const L = Math.hypot(p.x1 - p.x0, p.z1 - p.z0), ux = (p.x1 - p.x0) / L, uz = (p.z1 - p.z0) / L;
    const f = new Out(new Frame({ cx: p.x0, cz: p.z0, ux, uz, vx: -uz, vz: ux, y: 0 }, origin));
    outs.push(f);
    // The deck starts a metre back on the quay, so it meets the paving.
    f.box(-1, L, p.deckY - 0.3, p.deckY + 0.02, -p.half, p.half, BuildingMat.Oak, DECK, true);
    f.box(-1, L, p.deckY - 0.5, p.deckY - 0.3, -p.half + 0.1, -p.half + 0.35, BuildingMat.Oak, PILE);
    f.box(-1, L, p.deckY - 0.5, p.deckY - 0.3, p.half - 0.35, p.half - 0.1, BuildingMat.Oak, PILE);
    let k = 0;
    for (let a = 2; a <= L - 0.2; a += PILE_EVERY, k++) {
      if (!detail && k % 2) continue;
      for (const b of [-p.half + 0.25, p.half - 0.25]) {
        const wx = p.x0 + ux * a - uz * b, wz = p.z0 + uz * a + ux * b;
        f.box(a - 0.17, a + 0.17, bed(wx, wz), p.deckY - 0.3, b - 0.17, b + 0.17, BuildingMat.Oak, PILE);
      }
      if (detail && k % 2 === 1) for (const b of [-p.half + 0.3, p.half - 0.3]) f.box(a - 0.14, a + 0.14, p.deckY, p.deckY + 0.55, b - 0.14, b + 0.14, BuildingMat.Oak, BOLLARD);
    }
  }
  return mergeOuts(outs);
}

/** A ship or boat lying in the harbour: its plan, its middle and its heading (a unit vector, bow first). */
export interface Mooring {
  plan: ShipPlan;
  x: number;
  z: number;
  ux: number;
  uz: number;
}

/**
 * The ships at the harbour's berths (about two in three taken, each as long as its berth and the water under it
 * allow) and fishing boats tied along the piers, seeded. Each lies clear of its pier, bow out to sea.
 */
export function harbourMoorings(h: HarbourPlan, seed: number): Mooring[] {
  const r = new Rng(seed * 7919 + 4099), out: Mooring[] = [];
  for (const [i, b] of h.berths.entries()) {
    if (!r.chance(0.65)) continue;
    const p = h.piers[b.pier], ux = Math.cos(b.yaw), uz = Math.sin(b.yaw);
    // As long as the berth, and no deeper than the water under it (the draft is a ninth of the length).
    const len = Math.min(b.length, (b.depth - 0.4) / 0.11);
    if (len < 20) continue;
    const plan = planShip(seed * 31 + i, 'ship', len);
    const along = (b.x - p.x0) * ux + (b.z - p.z0) * uz, off = p.half + plan.beam / 2 + 0.6;
    out.push({ plan, x: p.x0 + ux * along - uz * off * b.side, z: p.z0 + uz * along + ux * off * b.side, ux, uz });
  }
  // Fishing boats tied along the quay's front between the piers, alongside it, bow one way or the other.
  const n = h.edge.length >> 1;
  for (let i = 2; i < n - 2; i += 3) {
    if (!r.chance(0.45)) continue;
    const ex = h.edge[i * 2], ez = h.edge[i * 2 + 1], ox = h.out[i * 2], oz = h.out[i * 2 + 1];
    if (h.piers.some((p) => Math.hypot(p.x0 - ex, p.z0 - ez) < 9)) continue;
    const plan = planShip(seed * 37 + i, 'boat'), dir = r.chance(0.5) ? 1 : -1;
    const x = ex + ox * (plan.beam / 2 + 0.4), z = ez + oz * (plan.beam / 2 + 0.4);
    if (out.some((m) => Math.hypot(m.x - x, m.z - z) < (m.plan.length + plan.length) / 2 + 0.5)) continue;
    out.push({ plan, x, z, ux: -oz * dir, uz: ox * dir });
  }
  return out;
}
