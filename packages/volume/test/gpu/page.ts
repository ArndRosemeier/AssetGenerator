// In the browser: gpuMesher must give the same meshes as surfaceNets (indices exact, positions and normals
// to f32 rounding), for mixed grid sizes and overlap masks in one tick, then times both.
import { Noise } from '../../../core/src/index';
import { surfaceNets, PAD, SIDE, type Grid, type MeshData } from '../../src/index';
import { gpuMesher } from '../../src/gpu';

const log = (s: string) => { document.getElementById('out')!.textContent += s + '\n'; console.log(s); };
const median = (a: number[]) => [...a].sort((x, y) => x - y)[a.length >> 1];
type Job = { grid: Grid; o: [number, number, number]; step: number; overlap: number; name: string };

function sample(f: (x: number, y: number, z: number) => number, o: [number, number, number], step: number, cells: number): Grid {
  const n = cells + 2 * PAD + 1, d = new Float32Array(n ** 3);
  for (let k = 0, p = 0; k < n; k++) for (let j = 0; j < n; j++) for (let i = 0; i < n; i++) d[p++] = f(o[0] + (i - PAD) * step, o[1] + (j - PAD) * step, o[2] + (k - PAD) * step);
  return { n, d };
}

function compare(a: MeshData | null, b: MeshData | null): string | null {
  if (!a || !b) return !a === !b ? null : `null mismatch (cpu ${!!a}, gpu ${!!b})`;
  if (a.indices.length !== b.indices.length || a.positions.length !== b.positions.length) return `sizes cpu ${a.positions.length / 3}v/${a.indices.length / 3}t, gpu ${b.positions.length / 3}v/${b.indices.length / 3}t`;
  for (let i = 0; i < a.indices.length; i++) if (a.indices[i] !== b.indices[i]) return `index ${i} differs`;
  let pe = 0, ne = 0;
  for (let i = 0; i < a.positions.length; i++) { pe = Math.max(pe, Math.abs(a.positions[i] - b.positions[i]) / (1 + Math.abs(a.positions[i]))); ne = Math.max(ne, Math.abs(a.normals[i] - b.normals[i])); }
  return pe > 1e-5 || ne > 1e-4 ? `position error ${pe}, normal error ${ne}` : null;
}

async function main() {
  const noise = new Noise(1234);
  const terrain = (x: number, y: number, z: number) => noise.fbm3(x * 0.02, y * 0.02, z * 0.02, 5) * 20 + (y - 64) * 0.5;
  const ball = (x: number, y: number, z: number) => Math.hypot(x - 16, y - 16, z - 16) - 10;
  const jobs: Job[] = [];
  const add = (name: string, f: typeof ball, o: [number, number, number], step: number, cells: number, overlap = 0) => jobs.push({ name, grid: sample(f, o, step, cells), o, step, overlap });
  add('ball 32', ball, [0, 0, 0], 1, 32);
  add('ball 16 step 2', ball, [0, 0, 0], 2, 16, SIDE.lowX | SIDE.highY);
  add('air', () => 5, [0, 0, 0], 1, 8);
  add('rock', () => -5, [0, 0, 0], 1, 8);
  for (const ov of [0, SIDE.highX | SIDE.highZ, SIDE.lowX, SIDE.lowY | SIDE.highY, 63]) add(`floor ov=${ov}`, (_x, y) => y - 6.3, [0, 0, 0], 1, 16, ov);
  for (let z = 0; z < 4; z++) for (let y = 0; y < 4; y++) for (let x = 0; x < 4; x++) add(`terrain ${x},${y},${z}`, terrain, [x * 32, y * 32, z * 32], 1, 32, (x + y + z) % 3 === 0 ? SIDE.highX : 0);

  const gpu = await gpuMesher();
  const cpu = jobs.map((j) => surfaceNets(j.grid, ...j.o, j.step, j.overlap));
  const got = await Promise.all(jobs.map((j) => gpu.mesh(j.grid, ...j.o, j.step, j.overlap))); // one tick: batched
  const failures = jobs.flatMap((j, q) => { const e = compare(cpu[q], got[q]); return e ? [`${j.name}: ${e}`] : []; });
  const tris = cpu.reduce((s, m) => s + (m ? m.indices.length / 3 : 0), 0);

  // Timing: the 64 terrain chunks, both ways.
  const terr = jobs.filter((j) => j.name.startsWith('terrain'));
  const cpuRun = () => { const t = performance.now(); terr.forEach((j) => surfaceNets(j.grid, ...j.o, j.step, j.overlap)); return performance.now() - t; };
  const gpuRun = async () => { const t = performance.now(); await Promise.all(terr.map((j) => gpu.mesh(j.grid, ...j.o, j.step, j.overlap))); return performance.now() - t; };
  const runs = Number(new URLSearchParams(location.search).get('runs') ?? 5);
  for (let i = 0; i < 2; i++) { cpuRun(); await gpuRun(); }
  const cpuMs: number[] = [], gpuMs: number[] = [];
  for (let i = 0; i < runs; i++) { cpuMs.push(cpuRun()); gpuMs.push(await gpuRun()); }
  const res = { jobs: jobs.length, tris, failures, match: failures.length === 0, terrainCpuMs: median(cpuMs), terrainGpuMs: median(gpuMs) };
  log(JSON.stringify(res, null, 2));
  (window as any).__result = res;
}
main().catch((e) => { log('ERROR ' + (e?.stack ?? e)); (window as any).__result = { error: String(e) }; });
