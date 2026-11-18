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

const data = new Float32Array(n * RECORD);   // per instance: matrix (16, column-major), kind, dither 0..1, frame, 1 spare
draws.set(data, n);                          // when the instances change (new cells streamed in)
await draws.ready();                         // behind the loading screen: builds the compute shaders
scene.add(draws.group);
// every frame, before renderer.render:
draws.update(camera);
```

Materials read the instance matrix from the vertex attributes `iM0..iM3` (its columns), as the
`@futuremagic/vegetation` materials do. `instancedGeometry` and `batchCap` (one batch on the CPU) live here too.

## Instances in a moving frame

A ship's fittings (blocks, deadeyes, pins, coils, guns) are set once in her own frame and move with her pose.
Give the frames as matrices (frame to world, the camera's space; not origin-relative) and say in each record
which frame its matrix is in:

```ts
const ship = new Matrix4(), gun = new Matrix4();
const draws = createInstanceDraws(renderer, kinds, { frames: [ship, gun], origin });
data[o + FRAME] = 1;             // this record's matrix is in frames[0] (the ship); 0 (the default) is the world
draws.set(data, n);              // once: the fittings never change place in her
// every frame: move the frames, nothing else
ship.compose(pos, quat, one);    // her pose from the simulation
gun.multiplyMatrices(ship, slide); // a frame in a frame: the game multiplies (a gun on its slide, a door on its hinges)
draws.update(camera);
```

The GPU path carries each record through its frame in the cull pass (one more matrix product per instance; the
frames are one uniform, at most a few hundred). The CPU path writes the framed instances again when only the
frames moved, and chooses their levels again once a frame has gone `step` metres. Frames are rigid (turn and
move, no scale); their number is fixed when the draws are made. With a floating origin the frames stay in world
space too: their positions are taken relative to the origin in doubles, so a ship far from zero keeps her
fittings exact.

Materials that shade in the frame's own space (a ship's light below deck, grain laid along her) give
`geometryInstancing(material, space)` the frame's inverse as a uniform: `positionLocal` and `normalLocal` are then
in her frame. Pose the draws' group by the frame (a child of her group), so the mesh takes them back to the world:

```ts
const toShip = uniform(new Matrix4());
geometryInstancing(material, toShip);
shipGroup.add(draws.group);
// every frame, after her group is posed:
ship.copy(shipGroup.matrixWorld); toShip.value.copy(ship).invert();
```

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
  the rules in `select.ts`, the image must equal the CPU path's, with no WebGPU errors, also for two ships far
  from zero whose fittings are in their own moving frames; it also times the cull of 100k instances.
