/**
 * Lots: a street block cut into building plots that face the street, plus the yards left behind.
 * From Scale `src/plan/cell.ts` (makeLots, splitFree, frontEdge; v1.0), freed from Scale's districts.
 */
import type { Rng } from '@futuremagic/core';
import { difference, intersection, shapeArea, shapesToPolys, union, type Shape } from './clip';
import { cleanPoly, distSqPointSeg, ensureCCW, minAreaRect, polyArea, polyCentroid, rectangularity, simplifyClosed, splitPolyByLine, type Poly } from './geom2';

/** A building plot. `front` is the edge on the street, as [ax, az, bx, bz]. */
export interface Lot {
  poly: Poly;
  front: number[];
  /** On more than one street (a corner plot). */
  corner: boolean;
}

export interface LotRules {
  /** Frontage width range, m. */
  width: [number, number];
  /** Depth range from the street, m. */
  depth: [number, number];
}

export interface Lots {
  lots: Lot[];
  /** What the lots did not take: back yards, gardens, courtyards. */
  yards: Shape[];
}

/**
 * Perimeter lots: a ring of plots along every street edge of the block around a yard. Built one depth
 * strip per (simplified) edge, mitred at the corners and cut into frontages; long edges go first and
 * later strips take only what is left, which copes with reflex corners and short edges.
 */
export function perimeterLots(blk: Shape, rules: LotRules, r: Rng): Lots {
  const out: Lots = { lots: [], yards: [] };
  const outer = blk.outer;
  const area = shapeArea(blk);
  if (area < rules.width[1] * rules.depth[1] * 1.3) {
    // A small block: one or two buildings.
    const parts = splitFree(outer, area / (area > rules.width[1] * rules.depth[0] ? 2 : 1), r, 1);
    for (const q of parts) out.lots.push({ poly: q, front: frontEdge(q, outer) ?? longestEdge(q), corner: true });
    return out;
  }
  const depth = r.range(rules.depth[0], rules.depth[1]);
  const simp = ensureCCW(simplifyClosed(outer, 0.9));
  const n = simp.length >> 1;
  if (n < 3) return out;
  const nrm: number[] = [];
  for (let i = 0; i < n; i++) {
    const j = (i + 1) % n;
    const dx = simp[j * 2] - simp[i * 2], dz = simp[j * 2 + 1] - simp[i * 2 + 1];
    const L = Math.hypot(dx, dz) || 1;
    nrm.push(-dz / L, dx / L);
  }
  const inner: number[] = [];
  for (let i = 0; i < n; i++) {
    const a = (i + n - 1) % n;
    let bx = nrm[a * 2] + nrm[i * 2], bz = nrm[a * 2 + 1] + nrm[i * 2 + 1];
    const bl = Math.hypot(bx, bz);
    if (bl < 1e-3) { bx = nrm[i * 2]; bz = nrm[i * 2 + 1]; } else { bx /= bl; bz /= bl; }
    const sc = Math.min(depth * 2.2, depth / Math.max(0.35, bx * nrm[i * 2] + bz * nrm[i * 2 + 1]));
    inner.push(simp[i * 2] + bx * sc, simp[i * 2 + 1] + bz * sc);
  }
  const order = [...Array(n).keys()].sort((x, y) => edgeLen(simp, y) - edgeLen(simp, x));
  const taken: Poly[] = [];
  const minLot = rules.width[0] * depth * 0.45;
  for (const i of order) {
    const j = (i + 1) % n;
    const L = edgeLen(simp, i);
    if (L < 2) continue;
    const strip = [simp[i * 2], simp[i * 2 + 1], simp[j * 2], simp[j * 2 + 1], inner[j * 2], inner[j * 2 + 1], inner[i * 2], inner[i * 2 + 1]];
    const stripClean = union([strip]).filter((sh) => shapeArea(sh) > 1);
    if (!stripClean.length) continue;
    let pieces = intersection(shapesToPolys(stripClean), [outer]);
    if (taken.length) pieces = difference(shapesToPolys(pieces), taken);
    taken.push(...shapesToPolys(stripClean));
    const ax = simp[i * 2], az = simp[i * 2 + 1];
    const dx = (simp[j * 2] - ax) / L, dz = (simp[j * 2 + 1] - az) / L;
    for (const pc of pieces) {
      let rest = ensureCCW(cleanPoly(pc.outer, 0.05));
      if (Math.abs(polyArea(rest)) < minLot) { if (Math.abs(polyArea(rest)) > 20) out.yards.push({ outer: rest, holes: [] }); continue; }
      // Extent of this piece along the edge.
      let t0 = Infinity, t1 = -Infinity;
      for (let k = 0; k < rest.length; k += 2) {
        const t = (rest[k] - ax) * dx + (rest[k + 1] - az) * dz;
        t0 = Math.min(t0, t); t1 = Math.max(t1, t);
      }
      const cutsT: number[] = [];
      let t = t0;
      for (;;) {
        const w = r.range(rules.width[0], rules.width[1]);
        if (t + w > t1 - rules.width[0] * 0.7) break;
        t += w;
        cutsT.push(t);
      }
      const lotsHere: Poly[] = [];
      for (const ct of cutsT) {
        const res = splitPolyByLine(rest, ax + dx * ct, az + dz * ct, -dz, dx);
        if (res.pieces.length < 2) continue;
        // The piece on the low-t side is a finished lot.
        const along = (p: Poly) => { const c = polyCentroid(p); return c[0] * dx + c[1] * dz; };
        res.pieces.sort((p1, p2) => along(p1) - along(p2));
        lotsHere.push(res.pieces[0]);
        rest = res.pieces[res.pieces.length - 1];
        for (let k = 1; k < res.pieces.length - 1; k++) lotsHere.push(res.pieces[k]);
      }
      lotsHere.push(rest);
      for (const q0 of lotsHere) {
        const q = ensureCCW(cleanPoly(q0, 0.05));
        if (q.length < 6 || Math.abs(polyArea(q)) < 20) continue;
        const fr = frontEdge(q, outer) ?? frontEdge(q, simp);
        if (!fr) { out.yards.push({ outer: q, holes: [] }); continue; }
        out.lots.push({ poly: q, front: fr, corner: countFrontEdges(q, simp) > 1 });
      }
    }
  }
  // The yard: whatever the strips did not take.
  for (const s of taken.length ? difference([outer], taken) : []) if (shapeArea(s) >= 30) out.yards.push(s);
  return out;
}

function edgeLen(p: Poly, i: number): number {
  const n = p.length >> 1, j = (i + 1) % n;
  return Math.hypot(p[j * 2] - p[i * 2], p[j * 2 + 1] - p[i * 2 + 1]);
}

/** Recursive splits across the long side of the bounding box until the pieces are near the target area. */
export function splitFree(poly: Poly, target: number, r: Rng, maxDepth: number): Poly[] {
  const out: Poly[] = [];
  const stack: [Poly, number][] = [[poly, 0]];
  while (stack.length) {
    const [q, d] = stack.pop()!;
    const a = Math.abs(polyArea(q));
    if (a < target * 1.6 || d >= maxDepth) { out.push(q); continue; }
    const o = minAreaRect(q);
    const longU = o.hu >= o.hv;
    const lx = longU ? o.ux : -o.uz, lz = longU ? o.uz : o.ux;
    const c = polyCentroid(q);
    const shift = r.range(-0.12, 0.12) * Math.max(o.hu, o.hv);
    const res = splitPolyByLine(q, c[0] + lx * shift, c[1] + lz * shift, -lz, lx);
    if (res.pieces.length < 2) { out.push(q); continue; }
    if (res.pieces.some((pc) => rectangularity(pc) < 0.45 && Math.abs(polyArea(pc)) > 80)) { out.push(q); continue; }
    for (const pc of res.pieces) stack.push([pc, d + 1]);
  }
  return out;
}

/** The edge of q that lies on the block outline (the street side); the longest one wins. */
export function frontEdge(q: Poly, outer: Poly): number[] | null {
  let best: number[] | null = null, bl = 0;
  const n = q.length >> 1;
  for (let i = 0; i < n; i++) {
    const j = (i + 1) % n;
    const ax = q[i * 2], az = q[i * 2 + 1], bx = q[j * 2], bz = q[j * 2 + 1];
    const L = Math.hypot(bx - ax, bz - az);
    if (L < 2.5) continue;
    if (!onOutline((ax + bx) / 2, (az + bz) / 2, outer)) continue;
    if (L > bl) { bl = L; best = [ax, az, bx, bz]; }
  }
  return best;
}

function countFrontEdges(q: Poly, outer: Poly): number {
  let c = 0;
  const n = q.length >> 1;
  for (let i = 0; i < n; i++) {
    const j = (i + 1) % n;
    const L = Math.hypot(q[j * 2] - q[i * 2], q[j * 2 + 1] - q[i * 2 + 1]);
    if (L > 4 && onOutline((q[i * 2] + q[j * 2]) / 2, (q[i * 2 + 1] + q[j * 2 + 1]) / 2, outer)) c++;
  }
  return c;
}

function onOutline(x: number, z: number, outer: Poly): boolean {
  const n = outer.length >> 1;
  for (let i = 0; i < n; i++) {
    const j = (i + 1) % n;
    if (distSqPointSeg(x, z, outer[i * 2], outer[i * 2 + 1], outer[j * 2], outer[j * 2 + 1]) < 0.3) return true;
  }
  return false;
}

/** The longest edge of q, as [ax, az, bx, bz]. */
export function longestEdge(q: Poly): number[] {
  let best = [0, 0, 1, 0], bl = -1;
  const n = q.length >> 1;
  for (let i = 0; i < n; i++) {
    const j = (i + 1) % n;
    const L = Math.hypot(q[j * 2] - q[i * 2], q[j * 2 + 1] - q[i * 2 + 1]);
    if (L > bl) { bl = L; best = [q[i * 2], q[i * 2 + 1], q[j * 2], q[j * 2 + 1]]; }
  }
  return best;
}
