// Browser benchmark: TS surfaceNets vs the WebGPU prototype on the engine-vs-ts workload (64 chunks of 32³).
import { Noise } from '../../packages/core/src/noise.ts';
import { surfaceNets } from '../../packages/volume/src/surfaceNets.ts';
import { surfaceNetsFast } from '../engine-vs-ts/ts/sn_fast.ts';
import { density, CHUNKS, N, NS, STEP } from '../engine-vs-ts/ts/work.ts';
import { GpuSurfaceNets, type MeshData } from './surfaceNetsGpu.ts';

const out = document.getElementById('out')!;
const log = (s: string) => { out.textContent += s + '\n'; console.log(s); };
const median = (a: number[]) => [...a].sort((x, y) => x - y)[a.length >> 1];
const qp = new URLSearchParams(location.search);
const RUNS = Number(qp.get('runs') ?? 15);
const COUNT = Number(qp.get('chunks') ?? CHUNKS.length); // fewer chunks for slow software GPUs

async function main() {
  const res: Record<string, unknown> = {};
  const noise = new Noise(1234);
  // A smaller test takes chunks from the layers the surface crosses (y = 1, 2).
  const chunks = COUNT >= CHUNKS.length ? CHUNKS : CHUNKS.filter((c) => c[1] === 1 || c[1] === 2).slice(0, COUNT);
  const grids = chunks.map((c) => density(noise, ...c));
  const all = new Float32Array(grids.length * NS ** 3);
  grids.forEach((g, q) => all.set(g, q * NS ** 3));
  const params = chunks.map(([x, y, z]) => ({ ox: x * N, oy: y * N, oz: z * N, step: STEP }));

  // CPU reference (same browser, same V8).
  const cpu = (f: (d: Float32Array, q: number) => MeshData | null) => grids.map(f);
  const orig = (d: Float32Array, q: number) => surfaceNets({ n: NS, d }, params[q].ox, params[q].oy, params[q].oz, STEP);
  const fast = (d: Float32Array, q: number) => surfaceNetsFast(NS, d, params[q].ox, params[q].oy, params[q].oz, STEP);
  const ref = cpu(orig);
  for (let w = 0; w < 3; w++) { cpu(orig); cpu(fast); }
  const time = (f: () => unknown) => { const t = performance.now(); f(); return performance.now() - t; };
  res.tsOriginalMs = median(Array.from({ length: 7 }, () => time(() => cpu(orig))));
  res.tsFastMs = median(Array.from({ length: 7 }, () => time(() => cpu(fast))));

  log(`ts done: ${(res.tsOriginalMs as number).toFixed(1)} / ${(res.tsFastMs as number).toFixed(1)} ms`);
  if (!navigator.gpu) throw new Error('no WebGPU in this browser');
  const adapter = await navigator.gpu.requestAdapter({ powerPreference: 'high-performance' });
  if (!adapter) throw new Error('no WebGPU adapter');
  const ts = adapter.features.has('timestamp-query');
  const device = await adapter.requestDevice({
    requiredFeatures: ts ? ['timestamp-query'] : [],
    requiredLimits: { maxStorageBufferBindingSize: adapter.limits.maxStorageBufferBindingSize, maxBufferSize: adapter.limits.maxBufferSize },
  });
  device.addEventListener('uncapturederror', (e) => log('GPU error: ' + (e as GPUUncapturedErrorEvent).error.message));
  const ai = adapter.info;
  res.adapter = `${ai.vendor} ${ai.architecture} ${ai.device} ${ai.description}`.trim();

  const gpu = new GpuSurfaceNets(device, NS, grids.length, Number(qp.get('cap')) || undefined); // ?cap=1000 tests index-buffer growth
  res.passes = gpu.passCount;
  gpu.upload(all, params);
  log(`adapter: ${res.adapter}; meshing on GPU...`);
  const meshes = await gpu.run(); // also sizes the index buffer
  log('first GPU mesh done');

  // Check against the TS mesher: same counts and indices, positions/normals within f32 rounding.
  let compared = 0, tris = 0, verts = 0, idxDiff = 0, posErr = 0, norErr = 0, nullDiff = 0;
  ref.forEach((r, q) => {
    const g = meshes[q];
    if (!r || !g) { if (!r !== !g) nullDiff++; return; }
    compared++; tris += r.indices.length / 3; verts += r.positions.length / 3;
    if (r.indices.length !== g.indices.length || r.positions.length !== g.positions.length) { idxDiff++; return; }
    for (let i = 0; i < r.indices.length; i++) if (r.indices[i] !== g.indices[i]) { idxDiff++; break; }
    for (let i = 0; i < r.positions.length; i++) posErr = Math.max(posErr, Math.abs(r.positions[i] - g.positions[i]));
    for (let i = 0; i < r.normals.length; i++) norErr = Math.max(norErr, Math.abs(r.normals[i] - g.normals[i]));
  });
  res.check = { chunks: chunks.length, chunksWithSurface: compared, tris, verts, chunksWithIndexMismatch: idxDiff, chunksNullMismatch: nullDiff, maxPosErr: posErr, maxNormalErr: norErr };
  res.match = compared > 0 && idxDiff === 0 && nullDiff === 0 && posErr < 1e-3 && norErr < 1e-3;

  // 1) GPU meshing only: density already on the GPU, mesh stays there (what a GPU world-gen would do).
  const done = async (f: (e: GPUCommandEncoder) => void) => {
    const e = device.createCommandEncoder(); f(e);
    const t = performance.now(); device.queue.submit([e.finish()]); await device.queue.onSubmittedWorkDone();
    return performance.now() - t;
  };
  for (let w = 0; w < 5; w++) await done((e) => gpu.encode(e));
  res.gpuMeshWallMs = median(await seq(RUNS, () => done((e) => gpu.encode(e))));

  // Same, measured on the GPU's clock (no submit/wait overhead), when the adapter has timestamps.
  if (ts) {
    const qs = device.createQuerySet({ type: 'timestamp', count: 2 });
    const rb = device.createBuffer({ size: 16, usage: GPUBufferUsage.QUERY_RESOLVE | GPUBufferUsage.COPY_SRC });
    const ms: number[] = [];
    for (let r = 0; r < RUNS; r++) {
      const rd = device.createBuffer({ size: 16, usage: GPUBufferUsage.MAP_READ | GPUBufferUsage.COPY_DST });
      const e = device.createCommandEncoder();
      gpu.encode(e, { querySet: qs, beginningOfPassWriteIndex: 0, endOfPassWriteIndex: 1 });
      e.resolveQuerySet(qs, 0, 2, rb, 0); e.copyBufferToBuffer(rb, 0, rd, 0, 16);
      device.queue.submit([e.finish()]);
      await rd.mapAsync(GPUMapMode.READ);
      const t = new BigUint64Array(rd.getMappedRange());
      ms.push(Number(t[1] - t[0]) / 1e6); rd.destroy();
    }
    res.gpuMeshTimestampMs = median(ms);
  }

  // 2) Drop-in replacement for the CPU mesher: upload densities, mesh, read back MeshData per chunk.
  res.gpuUploadMeshReadbackMs = median(await seq(RUNS, async () => {
    const t = performance.now(); gpu.upload(all, params); await gpu.run(); return performance.now() - t;
  }));

  log(JSON.stringify(res, null, 2));
  (window as any).__result = res;
}

async function seq(n: number, f: () => Promise<number>) { const a: number[] = []; for (let i = 0; i < n; i++) a.push(await f()); return a; }

main().catch((e) => { log('ERROR ' + (e?.stack ?? e)); (window as any).__result = { error: String(e) }; });
