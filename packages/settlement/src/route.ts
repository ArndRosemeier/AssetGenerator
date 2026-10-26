/**
 * Roads between places over open land: the cheapest way over a grid, where the cost grows with the
 * grade, water is crossed only where it is shallow (a ford), and the caller may forbid ground (houses,
 * fences). The grid's zigzag is then simplified and rounded, and a height profile is laid along it that
 * rises and falls smoothly, so the ground can be cut and filled to it. Pure and seeded: runs in workers.
 */
import { MinHeap, hash2f } from '@futuremagic/core';
import { chaikin, resample, simplifyOpen } from './geom2';

/** The land a road crosses. */
export interface RouteSite {
  seed: number;
  /** Ground height, m. */
  height: (x: number, z: number) => number;
  /** Water depth (> 0: water), m. */
  water?: (x: number, z: number) => number;
  /** Ground the road may not cross (a building, a fence). */
  blocked?: (x: number, z: number) => boolean;
}

export interface RouteOptions {
  /** Grid cell, m (default 8). Grown when the search box would hold more than `maxCells`. */
  cell?: number;
  /** A grade the road takes without fuss (default 0.06); twice it costs five times the length. */
  grade?: number;
  /** Steeper than this (default 0.22) a step costs eight times more again: the road winds round. */
  maxGrade?: number;
  /** The deepest water a road wades through (default 0.7 m); deeper water stops it. */
  ford?: number;
  /** How far beyond the ends the search may stray, m (default: 300 m or 60 % of the distance). */
  margin?: number;
  /** Points of the result this far apart, m (default 6). */
  spacing?: number;
  /** Most grid cells searched (default 400 000). */
  maxCells?: number;
}

export interface Route {
  /** Centre line (x, z, ...), from `from` to `to`, about `spacing` apart. */
  pts: number[];
  /** Length, m. */
  length: number;
  /** Grid steps through water. */
  fords: number;
  /** The path's cost (metres of easy road it is worth). */
  cost: number;
}

/** The 16 steps: the eight neighbours, and the knight's moves between them (straighter lines). */
const STEPS: readonly [number, number][] = [
  [1, 0], [1, 1], [0, 1], [-1, 1], [-1, 0], [-1, -1], [0, -1], [1, -1],
  [2, 1], [1, 2], [-1, 2], [-2, 1], [-2, -1], [-1, -2], [1, -2], [2, -1],
];

/** The cheapest road from `from` to `to`, or null where none exists in the search box (deep water all round). */
export function routeRoad(site: RouteSite, from: readonly [number, number], to: readonly [number, number], o: RouteOptions = {}): Route | null {
  const grade = o.grade ?? 0.06, maxGrade = o.maxGrade ?? 0.22, ford = o.ford ?? 0.7, spacing = o.spacing ?? 6;
  const dist = Math.hypot(to[0] - from[0], to[1] - from[1]);
  const margin = o.margin ?? Math.max(300, dist * 0.6);
  const bx0 = Math.min(from[0], to[0]) - margin, bz0 = Math.min(from[1], to[1]) - margin;
  const bw = Math.abs(to[0] - from[0]) + 2 * margin, bh = Math.abs(to[1] - from[1]) + 2 * margin;
  let cell = o.cell ?? 8;
  const maxCells = o.maxCells ?? 400_000;
  while ((bw / cell) * (bh / cell) > maxCells) cell *= 1.5;
  const nx = Math.ceil(bw / cell) + 1, nz = Math.ceil(bh / cell) + 1, N = nx * nz;
  const x0 = Math.floor(bx0 / cell) * cell, z0 = Math.floor(bz0 / cell) * cell;
  const wx = (i: number) => x0 + i * cell, wz = (j: number) => z0 + j * cell;

  // Ground and water per cell, read when first needed (NaN: not yet).
  const hs = new Float32Array(N).fill(NaN), wet = new Float32Array(N).fill(NaN);
  const height = (c: number) => { let h = hs[c]; if (Number.isNaN(h)) h = hs[c] = site.height(wx(c % nx), wz((c / nx) | 0)); return h; };
  const depth = (c: number) => {
    let d = wet[c];
    if (Number.isNaN(d)) {
      const x = wx(c % nx), z = wz((c / nx) | 0);
      d = wet[c] = site.blocked?.(x, z) ? Infinity : Math.max(0, site.water?.(x, z) ?? 0);
    }
    return d;
  };
  const cellOf = (x: number, z: number) => Math.min(nx - 1, Math.max(0, Math.round((x - x0) / cell))) + Math.min(nz - 1, Math.max(0, Math.round((z - z0) / cell))) * nx;
  const start = cellOf(from[0], from[1]), goal = cellOf(to[0], to[1]);
  const gx = goal % nx, gz = (goal / nx) | 0;

  const cost = new Float64Array(N).fill(Infinity), prev = new Int32Array(N).fill(-1);
  const closed = new Uint8Array(N);
  const open = new MinHeap();
  cost[start] = 0;
  open.push(0, start);
  while (open.size) {
    const c = open.pop();
    if (closed[c]) continue;
    closed[c] = 1;
    if (c === goal) break;
    const ci = c % nx, cj = (c / nx) | 0, hc = height(c);
    for (const [di, dj] of STEPS) {
      const i = ci + di, j = cj + dj;
      if (i < 0 || j < 0 || i >= nx || j >= nz) continue;
      const n = i + j * nx;
      if (closed[n]) continue;
      // A knight's move passes between two cells: both must be passable.
      let wade = depth(n);
      if (Math.abs(di) + Math.abs(dj) === 3) wade = Math.max(wade, depth(ci + Math.round(di / 2) + (cj + Math.round(dj / 2)) * nx), depth(ci + Math.trunc(di / 2) + (cj + Math.trunc(dj / 2)) * nx));
      if (wade > ford) continue;
      const L = Math.hypot(di, dj) * cell;
      const g = Math.abs(height(n) - hc) / L;
      let step = L * (1 + (g / grade) ** 2);
      if (g > maxGrade) step *= 8;
      // A ford: worth crossing straight and only once.
      if (wade > 0) step += L * 4 + 30;
      // A little seeded unevenness, so straight runs bend now and then as real roads do.
      step *= 1 + 0.15 * hash2f(site.seed, wx(i), wz(j));
      const total = cost[c] + step;
      if (total >= cost[n]) continue;
      cost[n] = total;
      prev[n] = c;
      open.push(total + Math.hypot(i - gx, j - gz) * cell, n);
    }
  }
  if (!Number.isFinite(cost[goal])) return null;

  const cells: number[] = [];
  for (let c = goal; c >= 0; c = prev[c]) cells.push(c);
  cells.reverse();
  let fords = 0;
  const grid: number[] = [];
  for (const c of cells) {
    if (depth(c) > 0) fords++;
    grid.push(wx(c % nx), wz((c / nx) | 0));
  }
  // Exact ends, the zigzag straightened (staying within half a cell of the path), corners rounded.
  grid[0] = from[0]; grid[1] = from[1];
  grid[grid.length - 2] = to[0]; grid[grid.length - 1] = to[1];
  const smooth = chaikin(simplifyOpen(grid, cell * 0.5), 3);
  const pts = resample(smooth, spacing);
  let length = 0;
  for (let k = 2; k < pts.length; k += 2) length += Math.hypot(pts[k] - pts[k - 2], pts[k + 1] - pts[k - 1]);
  return { pts, length, fords, cost: cost[goal] };
}

/**
 * The height a road runs at along its centre line: the ground under it, averaged over `window` metres
 * (twice, so it eases in and out of every rise), with the ends kept on the ground they meet.
 */
export function roadProfile(pts: readonly number[], height: (x: number, z: number) => number, window = 30): number[] {
  const n = pts.length >> 1;
  let ys = Array.from({ length: n }, (_, k) => height(pts[k * 2], pts[k * 2 + 1]));
  if (n < 3) return ys;
  const step = Math.hypot(pts[2] - pts[0], pts[3] - pts[1]) || 1;
  const r = Math.max(1, Math.round(window / step / 2));
  for (let pass = 0; pass < 2; pass++) {
    const was = ys;
    ys = was.map((_, k) => {
      let s = 0, w = 0;
      for (let q = Math.max(0, k - r); q <= Math.min(n - 1, k + r); q++) { s += was[q]; w++; }
      return s / w;
    });
  }
  // Back onto the ground at the ends, over the same window.
  const end0 = height(pts[0], pts[1]), end1 = height(pts[n * 2 - 2], pts[n * 2 - 1]);
  for (let k = 0; k < n; k++) {
    const a = Math.max(0, 1 - k / (2 * r)), b = Math.max(0, 1 - (n - 1 - k) / (2 * r));
    ys[k] += (end0 - ys[k]) * a * a * (3 - 2 * a) + (end1 - ys[k]) * b * b * (3 - 2 * b);
  }
  return ys;
}
