import { Noise } from '../../../packages/core/src/noise.ts';
import { surfaceNets, PAD } from '../../../packages/volume/src/surfaceNets.ts';

export const N = 32, NS = N + 2 * PAD + 1, STEP = 1;
export function density(noise: Noise, cx: number, cy: number, cz: number): Float32Array {
  const d = new Float32Array(NS * NS * NS);
  const ox = cx * N, oy = cy * N, oz = cz * N;
  let p = 0;
  for (let k = 0; k < NS; k++) for (let j = 0; j < NS; j++) for (let i = 0; i < NS; i++) {
    const x = ox + (i - PAD) * STEP, y = oy + (j - PAD) * STEP, z = oz + (k - PAD) * STEP;
    d[p++] = noise.fbm3(x * 0.02, y * 0.02, z * 0.02, 5) * 20 + (y - 64) * 0.5;
  }
  return d;
}
export function chunk(noise: Noise, cx: number, cy: number, cz: number) {
  const t0 = performance.now();
  const d = density(noise, cx, cy, cz);
  const t1 = performance.now();
  const m = surfaceNets({ n: NS, d }, cx * N, cy * N, cz * N, STEP);
  const t2 = performance.now();
  let sum = 0; for (let q = 0; q < d.length; q += 97) sum += d[q];
  return { noiseMs: t1 - t0, meshMs: t2 - t1, tris: m ? m.indices.length / 3 : 0, verts: m ? m.positions.length / 3 : 0, sum };
}
export const CHUNKS: [number, number, number][] = [];
for (let z = 0; z < 4; z++) for (let y = 0; y < 4; y++) for (let x = 0; x < 4; x++) CHUNKS.push([x, y, z]);
