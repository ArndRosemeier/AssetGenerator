# @futuremagic/volume

Rock volumes in signed distances (positive in air), meshed with surface nets: a smooth, indexed mesh
with gradient normals, seamless between neighbouring chunks. See `src/surfaceNets.ts` for the grid
layout (`PAD`, `OVERLAP`, `SIDE`).

Two meshers give the same mesh, behind one interface:

| | Import | Runs | Notes |
| --- | --- | --- | --- |
| `surfaceNets(grid, ox, oy, oz, step, overlap?)` | `@futuremagic/volume` | sync, CPU, workers | the original |
| `cpuMesher.mesh(...)` | `@futuremagic/volume` | async, CPU, workers | wraps `surfaceNets` |
| `(await gpuMesher(device?)).mesh(...)` | `@futuremagic/volume/gpu` | async, WebGPU compute | same arguments, same result |

The GPU result is the same mesh: the same vertex and index order, exactly the same indices, and positions
and normals equal up to f32 rounding (about 1e-5). `null` in the same cases (no surface).

## Switching a game from `surfaceNets` to the GPU (checklist for agents)

1. **Create the mesher once**, at startup, after the renderer:
   ```ts
   import { cpuMesher, type Mesher } from '@futuremagic/volume';
   import { gpuMesher } from '@futuremagic/volume/gpu';

   await renderer.init();
   const backend = (renderer as any).backend;
   let mesher: Mesher = cpuMesher;
   try {
     // Share three's device when it runs on WebGPU; on the WebGL 2 fallback there is none, gpuMesher asks for its own.
     mesher = await gpuMesher(backend?.isWebGPUBackend ? backend.device : undefined);
   } catch { /* no WebGPU: stay on the CPU */ }
   ```
   Keep `cpuMesher` as the fallback and behind a setting, so both paths stay switchable.
2. **Replace each call** `surfaceNets(grid, ox, oy, oz, step, overlap)` with
   `await mesher.mesh(grid, ox, oy, oz, step, overlap)`. Same arguments, same `MeshData | null`.
   The calling function becomes `async`; follow that up the call chain.
3. **Start all chunks' calls before awaiting any.** The GPU mesher batches the calls made in the same
   tick (per grid size, up to `maxBatch` = 64 chunks per batch) into one GPU submission. Awaiting inside
   a loop meshes one chunk per round trip and loses most of the speed:
   ```ts
   // Good: one batch
   const meshes = await Promise.all(chunks.map((c) => mesher.mesh(c.grid, c.ox, c.oy, c.oz, c.step, c.overlap)));
   // Bad: 64 round trips
   for (const c of chunks) meshes.push(await mesher.mesh(c.grid, c.ox, c.oy, c.oz, c.step, c.overlap));
   ```
4. **Where meshing happens:** density sampling can stay in workers. The GPU mesher runs where the
   device is (usually the main thread, next to the renderer); the main thread only copies the grids into
   one upload and the results out, the meshing itself does not block it. Moving grids from workers:
   transfer `grid.d` (a `Float32Array`). The returned arrays are fresh copies, safe to transfer or keep.
   `gpuMesher()` also works inside a worker (with its own device) if meshing must stay there.
5. **Do not change** grid sizes, `PAD`, `OVERLAP` or overlap masks for the GPU: everything
   `surfaceNets` accepts works the same.
6. **Check it:** in this repo, `npm i --no-save playwright` once, then `npm run test:gpu` (tools/gpu-page.mjs) compares the
   GPU with `surfaceNets` on 73 cases in Chromium and exits 1 on any difference. In the game, compare a
   few chunks' `MeshData` from both meshers once (indices equal, positions within 1e-4).
7. `mesher.destroy()` (GPU) frees its buffers, e.g. when the game shuts its world down.

## What to expect

64 chunks of 32³ (RTX 5070, Chromium 156): `surfaceNets` 50–56 ms on the CPU; `gpuMesher` 15.5 ms
(upload, mesh, read back). The meshing itself takes 2.5 ms; most of the 15.5 ms is moving data. A
renderer that draws straight from the GPU buffers (`GpuSurfaceNets`: `upload` + `encode` leave
`positions`, `normals`, `indices` and the per-chunk ranges in `info` on the GPU) would skip the
read-back; that is not wired to three.js yet.

GPU memory: per grid size, buffers for a batch take about `batch × (n − 1)³ × 40` bytes (about 150 MB
for 64 chunks of 32³). Big grids get smaller batches automatically, so each buffer fits the device's
limits. Pass a smaller `maxBatch` (`gpuMesher(device, 16)`) to use less.
