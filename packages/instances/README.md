# @futuremagic/instances

Many copies of a few meshes (trees, shrubs, rocks, buildings, crowds), each drawn at the level of detail its
distance asks for, and on WebGPU only where the camera can see it (or its shadow).

```ts
import { createInstanceDraws, RECORD, KIND, DITHER } from '@futuremagic/instances';

const draws = createInstanceDraws(renderer, [
  // kind 0: a tree. Full model up close, its hull beyond, dithered out before 1000 m.
  { lods: [
    { far: 60, parts: [{ geometry: wood, material: bark, castShadow: true }, { geometry: leaves, material: leaf, castShadow: true }] },
    { near: 60, far: 1000, fade: [700, 1000], parts: [{ geometry: hull, material: hullMat, castShadow: true }] },
  ] },
], { horizontal: true, shadow: { dir: sunDirection, reach: 60 } });

const data = new Float32Array(n * RECORD);   // per instance: matrix (16, column-major), kind, dither 0..1, 2 spare
draws.set(data, n);                          // when the instances change (new cells streamed in)
await draws.ready();                         // behind the loading screen: builds the compute shaders
scene.add(draws.group);
// every frame, before renderer.render:
draws.update(camera);
```

Materials read the instance matrix from the vertex attributes `iM0..iM3` (its columns), as the
`@futuremagic/vegetation` materials do. `instancedGeometry` and `batchCap` (one batch on the CPU) live here too.

## The two paths

| | When | What happens per frame |
| --- | --- | --- |
| GPU (`GpuInstanceDraws`) | WebGPU with `indirect-first-instance` | three compute passes: reset the list counters; per instance, its bounding sphere against the frustum (swept along `shadow.dir` × `reach`) and, for each level it is in, an atomic slot in that level's list; per draw, the indirect arguments. One output buffer holds every list; each part draws from its list's first slot. Nothing is read back. |
| CPU (`CpuInstanceDraws`) | WebGL 2, or `opts.cpu` | levels chosen again when the camera has moved `step` m (default 8), batches drawn whole (no view culling). |

`createInstanceDraws` picks the GPU path when it can. Both draw the same thing; the GPU path also skips what is
out of view, and changes levels every frame instead of every `step` metres.

## Notes for games

- **Shaders:** three small compute shaders per `InstanceDraws` (built in `ready()`, a few ms). The draw
  shaders are the materials' own; the GPU path's geometry has the same attributes, so the same pipelines.
- **Room:** a level's list has room for every instance of its kind, so nothing ever overflows; the buffers
  grow on `set` when needed (rarely: give `capacity` for the usual count).
- **Shadows:** the shadow pass draws the same lists. Without `shadow`, casters outside the view lose their
  shadows in it. `reach` is about the tallest instance's shadow length at a low sun.
- **Order:** instances in a list come in no fixed order (atomics). Fine for opaque and alpha-tested
  materials; do not use it for blended ones that need sorting.
- **Counts:** `counts()` reads the drawn counts back (GPU path); for checks and HUDs, not every frame.
- **Check:** `npm i --no-save playwright` once, then `npm run test:gpu:instances`: the GPU counts must equal
  the rules in `select.ts`, the image must equal the CPU path's, with no WebGPU errors; it also times the cull
  of 100k instances.
