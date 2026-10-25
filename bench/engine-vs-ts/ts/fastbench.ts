import { Noise } from '../../../packages/core/src/noise.ts';
import { surfaceNets, PAD } from '../../../packages/volume/src/surfaceNets.ts';
import { surfaceNetsFast } from './sn_fast.ts';
import { density, CHUNKS, N, NS } from './work.ts';
const noise = new Noise(1234);
const grids = CHUNKS.map((c) => density(noise, ...c));
const run = (f: any) => { let tris = 0; const t0 = performance.now(); grids.forEach((d, q) => { const [x, y, z] = CHUNKS[q]; const m = f({ n: NS, d }, x * N, y * N, z * N, 1, NS, d); tris += m ? m.indices.length / 3 : 0; }); return [performance.now() - t0, tris]; };
const orig = (g: any, ox: number, oy: number, oz: number, s: number) => surfaceNets(g, ox, oy, oz, s);
const fast = (_g: any, ox: number, oy: number, oz: number, s: number, n: number, d: Float32Array) => surfaceNetsFast(n, d, ox, oy, oz, s);
for (let w = 0; w < 3; w++) { run(orig); run(fast); }
const med = (f: any) => { const r = [0,1,2,3,4].map(() => run(f)); r.sort((a, b) => a[0] - b[0]); return r[2]; };
const a = med(orig), b = med(fast);
console.log(`ts mesh original: ${a[0].toFixed(1)} ms tris=${a[1]}; ts mesh rewritten: ${b[0].toFixed(1)} ms tris=${b[1]}`);
