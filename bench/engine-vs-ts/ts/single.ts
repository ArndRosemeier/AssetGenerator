import { Noise } from '../../../packages/core/src/noise.ts';
import { chunk, CHUNKS } from './work.ts';
const noise = new Noise(1234);
for (let w = 0; w < 2; w++) for (const c of CHUNKS) chunk(noise, ...c); // JIT warm-up
const runs: number[][] = [];
for (let r = 0; r < 5; r++) {
  let nz = 0, ms = 0, tris = 0, verts = 0, sum = 0;
  for (const c of CHUNKS) { const o = chunk(noise, ...c); nz += o.noiseMs; ms += o.meshMs; tris += o.tris; verts += o.verts; sum += o.sum; }
  runs.push([nz, ms]);
  if (r === 0) console.log(`check tris=${tris} verts=${verts} sum=${sum.toFixed(3)}`);
}
runs.sort((a, b) => a[0] + a[1] - b[0] - b[1]);
console.log(`ts single: noise ${runs[2][0].toFixed(1)} ms, mesh ${runs[2][1].toFixed(1)} ms (64 chunks, median of 5)`);
