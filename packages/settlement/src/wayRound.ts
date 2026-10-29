/**
 * A walk out of doors kept off the buildings: each stretch of a way (x, z pairs) that runs through a footprint
 * (or closer to a wall than a body's radius) is replaced by a way round it, found on a fine grid near that
 * stretch and pulled straight. Rows of houses wall to wall are gone round as one. Pure.
 */
import { distSqPointSeg, pointInPoly, segIntersect, type Poly } from './geom2';
import { distToPoly } from './town';

/** Grid step (m), and how far round a blocked stretch the grid reaches (m), then once more, wider. */
const STEP = 0.5;
const REACH = [10, 28];
/** How far from where it should start or end a way may begin or end (from a point too near a wall), m. */
const NEAR_END = 1.5;
/**
 * A blocked stretch longer than this (m) is cut into pieces this long first, and only the blocked pieces get a
 * grid: one grid over a whole long stretch (a walk from the street out to the hero hundreds of metres off) took
 * seconds on the main thread. A grid bigger than GRID_MAX cells is not searched (the stretch stays as it was).
 */
const PIECE = 16;
const GRID_MAX = 160_000;

/** Footprints by where they are (a grid of CELL metres), with the ways round them found so far. */
export class Footprints {
  private readonly cells = new Map<number, number[]>();
  private readonly boxes: [number, number, number, number][] = [];
  /** Ways round found (by their ends to the decimetre); dropped whole when full. */
  readonly found = new Map<string, number[] | null>();
  constructor(readonly polys: readonly Poly[]) {
    polys.forEach((p, i) => {
      const b: [number, number, number, number] = [Infinity, Infinity, -Infinity, -Infinity];
      for (let k = 0; k < p.length; k += 2) { b[0] = Math.min(b[0], p[k]); b[2] = Math.max(b[2], p[k]); b[1] = Math.min(b[1], p[k + 1]); b[3] = Math.max(b[3], p[k + 1]); }
      this.boxes.push(b);
      for (let j = cell(b[1]); j <= cell(b[3]); j++) for (let k = cell(b[0]); k <= cell(b[2]); k++) {
        const key = cellKey(k, j), l = this.cells.get(key);
        if (l) l.push(i); else this.cells.set(key, [i]);
      }
    });
  }

  /** The footprints whose bounds come within `r` of the box round a-b. */
  near(ax: number, az: number, bx: number, bz: number, r: number): Poly[] {
    const x0 = Math.min(ax, bx) - r, x1 = Math.max(ax, bx) + r, z0 = Math.min(az, bz) - r, z1 = Math.max(az, bz) + r;
    const seen = new Set<number>(), out: Poly[] = [];
    for (let j = cell(z0); j <= cell(z1); j++) for (let k = cell(x0); k <= cell(x1); k++) {
      for (const i of this.cells.get(cellKey(k, j)) ?? []) {
        if (seen.has(i)) continue;
        seen.add(i);
        const b = this.boxes[i];
        if (x1 > b[0] && x0 < b[2] && z1 > b[1] && z0 < b[3]) out.push(this.polys[i]);
      }
    }
    return out;
  }

  /** Whether a body of radius `r` at (x, z) stands in a footprint or against a wall. */
  blocked(x: number, z: number, r: number): boolean {
    return this.near(x, z, x, z, r).some((p) => pointInPoly(p, x, z) || distToPoly(p, x, z) < r);
  }
}

const CELL = 8;
const FOUND_MAX = 4096;
const cell = (v: number) => Math.floor(v / CELL);
const cellKey = (i: number, j: number) => (i + 32768) * 65536 + (j + 32768);

/**
 * `way`: the way. `foot`: the footprints. `r`: how far a walker keeps from their walls. A stretch with no way round within
 * reach stays as it was. The ends stay where they are.
 */
export function wayRound(way: readonly number[], foot: Footprints, r = 0.35): number[] {
  // A turn of the way that is itself in a footprint or against a wall (a corner of one house in the next) is left out.
  const pts: number[] = [];
  for (let k = 0; k + 1 < way.length; k += 2) {
    const x = way[k], z = way[k + 1], end = k === 0 || k + 2 >= way.length;
    if (end || !foot.blocked(x, z, r)) pts.push(x, z);
  }
  const out = [pts[0], pts[1]];
  for (let k = 2; k + 1 < pts.length; k += 2) {
    const ax = pts[k - 2], az = pts[k - 1], bx = pts[k], bz = pts[k + 1];
    const near = foot.near(ax, az, bx, bz, r);
    if (!near.length || clear(ax, az, bx, bz, near, r)) { out.push(bx, bz); continue; }
    // A long blocked stretch: in pieces (their cuts off the walls), each blocked one gone round on its own small grid.
    const L = Math.hypot(bx - ax, bz - az), n = Math.ceil(L / PIECE);
    let px = ax, pz = az;
    for (let i = 1; i <= n; i++) {
      // The last piece ends on b itself (not a sum a hair off it).
      const qx = i === n ? bx : ax + ((bx - ax) * i) / n, qz = i === n ? bz : az + ((bz - az) * i) / n;
      if (i < n && foot.blocked(qx, qz, r)) continue;
      roundPiece(out, px, pz, qx, qz, foot, r);
      px = qx; pz = qz;
    }
  }
  return out;
}

/** The stretch a-b onto `out` (a is there already): b, after the way round what blocks it, if one is found. */
function roundPiece(out: number[], ax: number, az: number, bx: number, bz: number, foot: Footprints, r: number): void {
  const near = foot.near(ax, az, bx, bz, r);
  if (near.length && !clear(ax, az, bx, bz, near, r)) {
    const key = [ax, az, bx, bz].map((v) => Math.round(v * 10)).join(',');
    let round = foot.found.get(key);
    if (round === undefined) {
      round = null;
      for (const m of REACH) {
        if ((round = gridWay(ax, az, bx, bz, m, foot.near(ax, az, bx, bz, m + r), r))) break;
      }
      if (foot.found.size >= FOUND_MAX) foot.found.clear();
      foot.found.set(key, round);
    }
    if (round) out.push(...round.slice(2, -2));
  }
  out.push(bx, bz);
}

/** Whether the stretch a-b runs into the footprint or nearer than `r` to its walls. `r` 0: only through it (an edge crossed). */
function segHits(p: Poly, ax: number, az: number, bx: number, bz: number, r: number): boolean {
  const n = p.length >> 1, r2 = r * r;
  for (let i = 0, j = n - 1; i < n; j = i++) {
    const cx = p[j * 2], cz = p[j * 2 + 1], dx = p[i * 2], dz = p[i * 2 + 1];
    if (segIntersect(ax, az, bx, bz, cx, cz, dx, dz)) return true;
    if (r > 0 && Math.min(distSqPointSeg(ax, az, cx, cz, dx, dz), distSqPointSeg(bx, bz, cx, cz, dx, dz), distSqPointSeg(cx, cz, ax, az, bx, bz), distSqPointSeg(dx, dz, ax, az, bx, bz)) < r2) return true;
  }
  return r > 0 && pointInPoly(p, ax, az);
}

/** Whether the stretch is clear: never through a footprint, and off the walls but for its end steps (an end may be near a wall: a woodpile against it). */
function clear(ax: number, az: number, bx: number, bz: number, near: readonly Poly[], r: number): boolean {
  const L = Math.hypot(bx - ax, bz - az);
  if (near.some((p) => segHits(p, ax, az, bx, bz, 0))) return false;
  if (L <= 2 * NEAR_END) return true;
  const ux = (bx - ax) / L, uz = (bz - az) / L;
  const sx = ax + ux * NEAR_END, sz = az + uz * NEAR_END, ex = bx - ux * NEAR_END, ez = bz - uz * NEAR_END;
  return !near.some((p) => segHits(p, sx, sz, ex, ez, r));
}

/** A way from a to b round the footprints `by` (kept `r` off), on a grid reaching `m` metres round the stretch; null if none. */
function gridWay(ax: number, az: number, bx: number, bz: number, m: number, by: readonly Poly[], r: number): number[] | null {
  const x0 = Math.min(ax, bx) - m, z0 = Math.min(az, bz) - m;
  const nx = Math.ceil((Math.max(ax, bx) + m - x0) / STEP), nz = Math.ceil((Math.max(az, bz) + m - z0) / STEP);
  if (nx * nz > GRID_MAX) return null;
  const at = (c: number): [number, number] => { const i = c % nx; return [x0 + (i + 0.5) * STEP, z0 + ((c - i) / nx + 0.5) * STEP]; };
  // Blocked cells: each footprint marks those in its bounds (and r round them) that are in it or near its walls.
  const shut = new Uint8Array(nx * nz);
  for (const p of by) {
    let px0 = Infinity, pz0 = Infinity, px1 = -Infinity, pz1 = -Infinity;
    for (let k = 0; k < p.length; k += 2) { px0 = Math.min(px0, p[k]); px1 = Math.max(px1, p[k]); pz0 = Math.min(pz0, p[k + 1]); pz1 = Math.max(pz1, p[k + 1]); }
    const i0 = Math.max(0, Math.floor((px0 - r - x0) / STEP)), i1 = Math.min(nx - 1, Math.floor((px1 + r - x0) / STEP));
    const j0 = Math.max(0, Math.floor((pz0 - r - z0) / STEP)), j1 = Math.min(nz - 1, Math.floor((pz1 + r - z0) / STEP));
    for (let j = j0; j <= j1; j++) for (let i = i0; i <= i1; i++) {
      const c = j * nx + i;
      if (shut[c]) continue;
      const [x, z] = at(c);
      if (pointInPoly(p, x, z) || distToPoly(p, x, z) < r) shut[c] = 1;
    }
  }
  const free = (i: number, j: number): boolean => !shut[j * nx + i];
  // The free cell nearest each end, within reach of it.
  const end = (x: number, z: number): number => {
    const ci = Math.floor((x - x0) / STEP), cj = Math.floor((z - z0) / STEP), span = Math.ceil(NEAR_END / STEP);
    let best = -1, bd = Infinity;
    for (let j = Math.max(0, cj - span); j <= Math.min(nz - 1, cj + span); j++) for (let i = Math.max(0, ci - span); i <= Math.min(nx - 1, ci + span); i++) {
      const [px, pz] = at(j * nx + i), d = Math.hypot(px - x, pz - z);
      if (d <= NEAR_END && d < bd && free(i, j)) { bd = d; best = j * nx + i; }
    }
    return best;
  };
  const s = end(ax, az), e = end(bx, bz);
  if (s < 0 || e < 0) return null;
  const parent = new Int32Array(nx * nz).fill(-1);
  parent[s] = s;
  const q = [s];
  for (let h = 0; h < q.length && parent[e] < 0; h++) {
    const c = q[h], i = c % nx, j = (c - i) / nx;
    for (const [di, dj] of [[1, 0], [-1, 0], [0, 1], [0, -1], [1, 1], [1, -1], [-1, 1], [-1, -1]]) {
      const ii = i + di, jj = j + dj;
      if (ii < 0 || jj < 0 || ii >= nx || jj >= nz || parent[jj * nx + ii] >= 0 || !free(ii, jj)) continue;
      if (di && dj && (!free(i + di, j) || !free(i, j + dj))) continue;
      parent[jj * nx + ii] = c;
      q.push(jj * nx + ii);
    }
  }
  if (parent[e] < 0) return null;
  const cells: [number, number][] = [];
  for (let c = e; ; c = parent[c]) { cells.push(at(c)); if (c === s) break; }
  cells.reverse();
  const sight = (u: readonly [number, number], v: readonly [number, number]): boolean => !by.some((p) => segHits(p, u[0], u[1], v[0], v[1], r));
  const way = [ax, az, ...pulledStraight(cells, sight)];
  way.push(bx, bz);
  return way;
}

/** A grid way's cells pulled straight: from each turn on to the farthest one in clear `sight`. Flat x, z pairs from the first cell to the last. */
export function pulledStraight(cells: readonly (readonly [number, number])[], sight: (u: readonly [number, number], v: readonly [number, number]) => boolean): number[] {
  const out = [cells[0][0], cells[0][1]];
  for (let i = 0; i < cells.length - 1;) {
    let k = cells.length - 1;
    while (k > i + 1 && !sight(cells[i], cells[k])) k--;
    out.push(cells[k][0], cells[k][1]);
    i = k;
  }
  return out;
}
