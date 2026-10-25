/**
 * Surface nets: a smooth, indexed mesh from a grid of signed distances (positive in air). From Dunfinity
 * src/gen/surfaceNets.ts (v0.289).
 *
 * The grid pads the chunk's N cells with PAD cells on every side (N + 2·PAD + 1 samples per axis), so
 * faces at and just past the chunk's sides can be built. A face belongs to the chunk whose cell range
 * [0, N) holds its grid edge, so neighbouring chunks of the same size join without gaps or doubles.
 * Triangles wind counter-clockwise seen from the air.
 */

/** A cube of signed distance samples. */
export interface Grid {
  /** Samples per axis (cells + 1). */
  n: number;
  /** Signed distances, x fastest, then y, then z. */
  d: Float32Array;
}

export interface MeshData {
  positions: Float32Array;
  normals: Float32Array;
  indices: Uint32Array;
}

/** Padding cells on each side of a chunk's grid. */
export const PAD = 3;
/** Cells built past an overlapped side. */
export const OVERLAP = 2;

/** Sides for `overlap`: bit 2·axis is the low side, bit 2·axis + 1 the high side (axis x 0, y 1, z 2). */
export const SIDE = { lowX: 1, highX: 2, lowY: 4, highY: 8, lowZ: 16, highZ: 32 } as const;

/**
 * Mesh the grid. `grid.n` = N + 2·PAD + 1 samples per axis; sample (i, j, k) sits at
 * origin + (i - PAD, j - PAD, k - PAD) * step. Returns null when there is no surface.
 *
 * `overlap` (a SIDE mask): also build the faces OVERLAP cells past those sides. A chunk next to a coarser
 * neighbour overlaps it, so the small mismatch between the two meshes shows no crack.
 */
export function surfaceNets(grid: Grid, ox: number, oy: number, oz: number, step: number, overlap = 0): MeshData | null {
  const { n, d } = grid;
  const cells = n - 1;
  const at = (i: number, j: number, k: number) => d[i + n * (j + n * k)];

  // One vertex per cell with a sign change, at the average of its edge crossings.
  const vert = new Int32Array(cells * cells * cells).fill(-1);
  const pos: number[] = [];
  const nor: number[] = [];
  const c = new Float32Array(8);
  for (let k = 0; k < cells; k++) {
    for (let j = 0; j < cells; j++) {
      for (let i = 0; i < cells; i++) {
        let mask = 0;
        for (let q = 0; q < 8; q++) {
          const v = at(i + (q & 1), j + ((q >> 1) & 1), k + ((q >> 2) & 1));
          c[q] = v;
          if (v < 0) mask |= 1 << q;
        }
        if (mask === 0 || mask === 255) continue;
        let sx = 0, sy = 0, sz = 0, count = 0;
        for (const [a, b] of EDGES) {
          const va = c[a], vb = c[b];
          if ((va < 0) === (vb < 0)) continue;
          const t = va / (va - vb);
          sx += (a & 1) + t * ((b & 1) - (a & 1));
          sy += ((a >> 1) & 1) + t * (((b >> 1) & 1) - ((a >> 1) & 1));
          sz += ((a >> 2) & 1) + t * (((b >> 2) & 1) - ((a >> 2) & 1));
          count++;
        }
        vert[i + cells * (j + cells * k)] = pos.length / 3;
        const fx = sx / count, fy = sy / count, fz = sz / count;
        pos.push(ox + (i - PAD + fx) * step, oy + (j - PAD + fy) * step, oz + (k - PAD + fz) * step);
        // Normal: the field's gradient (central differences at the cell's corners), interpolated
        // trilinearly to the vertex, so flat faces at any angle to the grid shade smoothly.
        let gx = 0, gy = 0, gz = 0;
        for (let q = 0; q < 8; q++) {
          const a = i + (q & 1), b = j + ((q >> 1) & 1), e = k + ((q >> 2) & 1);
          const wq = ((q & 1) ? fx : 1 - fx) * (((q >> 1) & 1) ? fy : 1 - fy) * (((q >> 2) & 1) ? fz : 1 - fz);
          gx += wq * (at(Math.min(a + 1, n - 1), b, e) - at(Math.max(a - 1, 0), b, e));
          gy += wq * (at(a, Math.min(b + 1, n - 1), e) - at(a, Math.max(b - 1, 0), e));
          gz += wq * (at(a, b, Math.min(e + 1, n - 1)) - at(a, b, Math.max(e - 1, 0)));
        }
        const len = Math.hypot(gx, gy, gz) || 1;
        nor.push(gx / len, gy / len, gz / len);
      }
    }
  }
  if (!pos.length) return null;

  // One quad per sign-changing grid edge owned by this chunk (samples PAD..PAD+N-1 along each axis,
  // OVERLAP more on overlapped sides), joining the four cells around the edge.
  const idx: number[] = [];
  const N = n - 2 * PAD - 1;
  const lo = (axis: number) => PAD - OVERLAP * ((overlap >> (2 * axis)) & 1);
  const hi = (axis: number) => PAD + N - 1 + OVERLAP * ((overlap >> (2 * axis + 1)) & 1);
  const v = (i: number, j: number, k: number) => vert[i + cells * (j + cells * k)];
  for (let k = lo(2); k <= hi(2); k++) {
    for (let j = lo(1); j <= hi(1); j++) {
      for (let i = lo(0); i <= hi(0); i++) {
        const s0 = at(i, j, k);
        // Edges along x, y, z from sample (i, j, k).
        quad(s0, at(i + 1, j, k), v(i, j, k), v(i, j - 1, k), v(i, j - 1, k - 1), v(i, j, k - 1));
        quad(s0, at(i, j + 1, k), v(i, j, k), v(i, j, k - 1), v(i - 1, j, k - 1), v(i - 1, j, k));
        quad(s0, at(i, j, k + 1), v(i, j, k), v(i - 1, j, k), v(i - 1, j - 1, k), v(i, j - 1, k));
      }
    }
  }
  function quad(a: number, b: number, v0: number, v1: number, v2: number, v3: number): void {
    if ((a < 0) === (b < 0)) return;
    if (v0 < 0 || v1 < 0 || v2 < 0 || v3 < 0) return;
    // Rock at a (a < 0): the air is towards +axis, so keep the order; otherwise flip.
    if (a < 0) idx.push(v0, v1, v2, v0, v2, v3);
    else idx.push(v0, v2, v1, v0, v3, v2);
  }
  if (!idx.length) return null;
  return { positions: new Float32Array(pos), normals: new Float32Array(nor), indices: new Uint32Array(idx) };
}

const EDGES: readonly (readonly [number, number])[] = [
  [0, 1], [2, 3], [4, 5], [6, 7],
  [0, 2], [1, 3], [4, 6], [5, 7],
  [0, 4], [1, 5], [2, 6], [3, 7],
];
