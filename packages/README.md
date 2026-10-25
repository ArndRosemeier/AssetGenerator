# TypeScript packages

Runtime code shared by the futuremagic games (Dunfinity, SimWorld, Solarpolis). The Python/Blender
asset pipeline lives next to this in `tools/` and `blender/` and is unaffected.

| Package | What | Came from |
| --- | --- | --- |
| `@futuremagic/audio` | Game sound: `./web` `AudioEngine` on Web Audio (crossfading ambience beds, placed HRTF and seeded one-shots, two music decks that crossfade and duck, muffling, room echo, decoded takes under a budget); `.` pure: seeded takes, the footstep clock (`Stride`), the music picker (moods, holds, urgent cuts, no repeats), room impulses; `tools/make.mjs` makes a game's sounds (Seed Audio) and music (Lyria) through OpenRouter from a `sounds.json`. Guide: [audio/README.md](audio/README.md). | Solarpolis `src/audio/sound.ts`, `scripts/sound/make.mjs`; first used by MasterWorld |
| `@futuremagic/core` | Seeded hashing and PRNG (`deriveSeed`, `Rng`), simplex/fbm/ridged/cellular noise, scalar and vector math, a min-heap. No three.js, no DOM. | Scale `src/core` (v0.257) |
| `@futuremagic/dungeon` | Dungeons from cycles, not trees: a library of cycle patterns (lock and key on a loop, the goal seen early, hidden shortcuts, drops into tall halls), `cyclicGraph`, the tension curve along the intended walk (`pace`: safe spot, reveal, climax, shortcut out) and a multi-level grid layout with A* passages, stairs and ledges (`layoutDungeon`). Pure. Guide: [dungeon/README.md](dungeon/README.md). | New, for MasterWorld (after *Unexplored*'s cyclic generation) |
| `@futuremagic/humanoid` | Scale's humans. `.`: the pure body build (MakeHuman bodies, races, looks, hair and parts, garment specs), runs in workers and tests. `./three`: `Humanoid` (skinned character, node materials for skin, eyes, hair and garments, garment shells fitted to any body, the animator with mocap clips), `three/webgpu` only. Games bring their clothes through a `Wardrobe`. Assets in `humanoid/assets/` (the host serves them; `setHumanAssetBase`). | Scale `src/humanoid` (v0.257) |
| `@futuremagic/instances` | Repeated meshes (trees, rocks, buildings, crowds) drawn by distance and view: `createInstanceDraws(renderer, kinds)` takes instance records (matrix, kind, dither) and kinds with levels of detail. On WebGPU, compute passes cull each instance against the view (swept along the light, so shadows of unseen casters stay), pick its level and pack the lists, drawn with indirect draws and nothing read back; elsewhere a CPU path. Instance matrices are iM0..iM3 attributes, so materials need no change (`instancedGeometry`, `batchCap` live here). `npm run test:gpu:instances` checks the GPU against the rules in Chromium. Guide: [instances/README.md](instances/README.md). | New, for MasterWorld (after the volume GPU mesher) |
| `@futuremagic/stage` | The shader policy for `three/webgpu` games: `createRenderer` (WebGPU only, or WebGPU with WebGL 2 fallback, the game picks), the `Stage` (`warmUp`, `add`, `prepare`, `warmLater`), the compile cap, the renderer hooks on three r186 internals, and the build monitor. Each game passes its own material registry (`StageOptions.kinds`). | Dunfinity `src/render/stage.ts`, `renderer.ts`, `shaders/` (v0.281) |
| `@futuremagic/settlement` | Settlement planning on the ground plane, pure: flat polygons (`geom2`), Clipper booleans and offsets (`clip`), plots facing the street (`perimeterLots`), organic street cuts, and `planTown`, a medieval small town (market, roads that follow the land, crooked lanes, houses by zone, a temple, moot hall, inn, smithy, mill, and the fixtures people use). | Scale `src/core/geom2.ts`, `clip.ts`, `src/plan/cell.ts` (v1.0); the town planner new, for MasterWorld |
| `@futuremagic/sky` | A physical sky for `three/webgpu`: `./node` has `makeSkyNode` (Rayleigh/Mie sky, sun disc and glow, phased moon, clouds, weather, horizon fog, reversed depth) and `makeStarsNode`. `.` is pure: the sun and moon path (`skyPath`, `moonAt`), the light rig as numbers (`skyLight`: key light, hemisphere, fog, exposure, environment) and a seeded `starField`. | Scale `src/render/SkySystem.ts`, `webgpu/sky.ts` (v0.257) |
| `@futuremagic/texgen` | Procedural, tileable PBR texture layers on the CPU (pure, runs in workers): facade walls, roofs and town grounds, plus natural ground (wild grass, forest floor, rock, cliff strata, scree, snow, sand, mud). Each layer gives albedo RGBA (a = roughness) and normal RGBA (rg = normal, b = height, a = AO). | Scale `src/render/texgen` (natural layers new, for MasterWorld) |
| `@futuremagic/vegetation` | Procedural trees and shrubs: 10 species with species-shaped branching wood, leaf-card crowns with baked occlusion and far canopy hulls (`treeModel`, `shrubModel`, pure geometry), the bark and leaf atlases (`vegetationTextures`, canvas), and `./node`: wind-swayed bark, leaf (autumn, translucency) and far-hull node materials; `createLeafPasses`: leaves depth first, then lit once per pixel (about 2× faster frames under a canopy); `woodsFromAfar`: whole forests drawn per pixel on the ground past the last trees (crowns, gaps, clumps, glades; footprint-faded). | Scale `src/props/vegetation.ts`, `webgpu/vegetation.ts` (v0.264); woods from Solarpolis `src/render/groundShaders.ts` |
| `@futuremagic/volume` | Rock volumes in signed distances: `surfaceNets` meshes a padded grid into a smooth, indexed mesh with gradient normals; neighbouring chunks join without gaps or doubles, and `overlap` hides cracks next to coarser chunks. Pure, runs in workers. `cpuMesher` / `./gpu` `gpuMesher(device)`: the same mesh behind one async `mesh()` call, on the CPU or on the GPU (WebGPU compute, calls in one tick batched; about 3× faster than the CPU with read-back), so a game switches with one line. `npm run test:gpu` checks the GPU against the CPU in Chromium. How to switch a game: [volume/README.md](volume/README.md). | Dunfinity `src/gen/surfaceNets.ts` (v0.289) |

## Rules

1. **Extract on demand.** A module moves here when a game starts using it, not before.
2. **TypeScript source, no build step.** Consumers compile it (Vite, `tsc`, `tsx`).
3. **Consumers pin a commit** (Dunfinity uses a git submodule and `file:` dependencies).
4. **Every package has headless tests** (`npm test` at the repo root).
5. **Nothing here imports the Rust engine or Godot code.**
6. **Determinism is a contract.** `core` pins hash and PRNG outputs in its tests: changing
   them changes every world built from a seed.

```bash
npm install
npm test
npm run typecheck
```
