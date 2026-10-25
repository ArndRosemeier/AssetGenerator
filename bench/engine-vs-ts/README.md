# Engine (Rust) vs TS stack: CPU benchmark

Same world-gen workload in three runtimes: 64 chunks of 32³ cells (39³ padded samples),
density = `Noise.fbm3` (5 octaves) from `@futuremagic/core`, meshed with `surfaceNets` from
`@futuremagic/volume`. The Rust code in `rs/` is a line-by-line port; every run prints
`check tris=… verts=… sum=…`, which must match across runtimes (it does: 125258 / 107503 / 4793.296).

`ts/sn_fast.ts` is the same mesher rewritten with typed arrays instead of `number[]` + closures,
to separate "language" from "code style".

```
npm install
node bench/engine-vs-ts/run.mjs
```
