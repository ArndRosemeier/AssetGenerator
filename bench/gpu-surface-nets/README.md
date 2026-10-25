# Surface nets on the GPU (WebGPU compute prototype)

`surfaceNetsGpu.ts` is `packages/volume` `surfaceNets` as WGSL compute shaders. It meshes a whole
batch of same-size chunks in one command buffer (11 dispatches, no CPU round trip in between) and
gives the same mesh as the TS mesher: vertices in the same scan order, chunk-local indices in the same
order, positions and normals equal up to f32 rounding. Overlap masks (`SIDE`) are supported per chunk.

How the order is kept: a vertex's index is the prefix sum of "cell has a sign change" over the cells
in scan order, and a sample's first quad is the prefix sum of its quad counts (0..3). Passes:
classify → scan → vertices → count quads → scan → chunk info → write quads (see the file header).

The mesh stays on the GPU (`positions`, `normals`, `indices`, `info` buffers); `run()` also reads it
back as one `MeshData` per chunk, a drop-in for the CPU mesher.

## Run

Same workload as `bench/engine-vs-ts` (64 chunks of 32³, fbm3 density, made on the CPU).

```
npm install
npm i --no-save playwright          # once; or use --serve and open the URL in Chrome
node bench/gpu-surface-nets/run.mjs --headed
```

Options go in a `?query` argument: `?runs=15` (timed runs, default 15), `?chunks=4` (fewer chunks),
`?cap=1000` (start with a tiny index buffer to test that it grows). The run exits 1 when the GPU mesh
does not match the TS mesh. `adapter` in the output names the GPU; `swiftshader` means software.

Reported times (median):

- `tsOriginalMs`, `tsFastMs`: the TS mesher and its typed-array rewrite, in the same browser.
- `gpuMeshWallMs`: meshing only, density already on the GPU, mesh stays there: submit to done.
- `gpuMeshTimestampMs`: the same on the GPU clock (when the adapter has `timestamp-query`).
- `gpuUploadMeshReadbackMs`: upload densities, mesh, read back `MeshData` per chunk.

## Results (2026-10-25, RTX 5070, Ryzen 5 9600X, Chromium 156, PC idle)

All 64 chunks match the TS mesh (125258 tris, 107503 verts, max position error 1.5e-5). Median of 3 runs:

| | ms |
| --- | --- |
| TS mesher (original) | 56 |
| TS mesher (typed-array rewrite) | 50 |
| GPU meshing, submit to done | 2.5 |
| GPU meshing, GPU clock | 0.33 |
| GPU upload + mesh + read back per chunk | 15.5 |
