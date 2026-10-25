/**
 * Organic street cuts: a polygon split again and again across its long side, with a jittered angle and
 * offset, until the pieces are block sized. The cuts are the streets. From Scale `src/plan/cell.ts`
 * (splitStreets, the organic branch; v1.0).
 */
import type { Rng } from '@futuremagic/core';
import { minAreaRect, polyArea, polyCentroid, splitPolyByLine, type Poly } from './geom2';

export interface Cuts {
  /** The finished pieces (block sized). */
  pieces: Poly[];
  /** The cut lines, each [ax, az, bx, bz] (several per cut through a concave piece). */
  cuts: number[][];
}

/**
 * Split `poly` into pieces whose short and long sides are near `block` = [short, long] (m). `minCut`:
 * shorter cut lines are kept out of `cuts` (they become no street).
 */
export function organicCuts(poly: Poly, block: [number, number], rng: Rng, minCut = 20): Cuts {
  const [shortT, longT] = block;
  const out: Cuts = { pieces: [], cuts: [] };
  const queue: { poly: Poly; depth: number }[] = [{ poly, depth: 0 }];
  const sliver = (q: Poly) => Math.abs(polyArea(q)) < shortT * shortT * 0.35;
  const keep = (chords: number[][]) => { for (const ch of chords) if (Math.hypot(ch[2] - ch[0], ch[3] - ch[1]) > minCut) out.cuts.push(ch); };
  let guard = 0;
  while (queue.length && guard++ < 600) {
    const { poly: p, depth } = queue.shift()!;
    const area = Math.abs(polyArea(p));
    const obb = minAreaRect(p);
    const longLen = Math.max(obb.hu, obb.hv) * 2;
    const shortLen = Math.min(obb.hu, obb.hv) * 2;
    if ((area < shortT * longT * 1.35 && longLen < longT * 1.4) || (shortLen < shortT * 0.9 && longLen < longT * 1.6)) { out.pieces.push(p); continue; }
    // Cut across the long axis, the angle and the place jittered.
    const longAxisU = obb.hu >= obb.hv;
    const lx = longAxisU ? obb.ux : -obb.uz, lz = longAxisU ? obb.uz : obb.ux;
    const c = polyCentroid(p);
    const ja = rng.range(-0.3, 0.3);
    const nx = lx * Math.cos(ja) - lz * Math.sin(ja), nz = lx * Math.sin(ja) + lz * Math.cos(ja);
    const shift = rng.range(-0.18, 0.18) * longLen;
    const { pieces, chords } = splitPolyByLine(p, c[0] + nx * shift, c[1] + nz * shift, -nz, nx);
    if (pieces.length < 2) { out.pieces.push(p); continue; }
    if (pieces.some(sliver)) {
      // Retry once with a centred, straight cut.
      const r2 = depth < 3 ? splitPolyByLine(p, c[0], c[1], -lz, lx) : null;
      if (r2 && r2.pieces.length >= 2 && !r2.pieces.some(sliver)) {
        keep(r2.chords);
        for (const q of r2.pieces) queue.push({ poly: q, depth: depth + 1 });
      } else out.pieces.push(p);
      continue;
    }
    keep(chords);
    for (const q of pieces) queue.push({ poly: q, depth: depth + 1 });
  }
  for (const q of queue) out.pieces.push(q.poly);
  return out;
}
