# TypeScript packages

Runtime code shared by the futuremagic games (Dunfinity, SimWorld, Solarpolis). The Python/Blender
asset pipeline lives next to this in `tools/` and `blender/` and is unaffected.

| Package | What | Came from |
| --- | --- | --- |
| `@futuremagic/core` | Seeded hashing and PRNG (`deriveSeed`, `Rng`), simplex/fbm/ridged/cellular noise, scalar and vector math, a min-heap. No three.js, no DOM. | Scale `src/core` (v0.257) |
| `@futuremagic/humanoid` | Scale's humans. `.`: the pure body build (MakeHuman bodies, races, looks, hair and parts, garment specs), runs in workers and tests. `./three`: `Humanoid` (skinned character, node materials for skin, eyes, hair and garments, garment shells fitted to any body, the animator with mocap clips), `three/webgpu` only. Games bring their clothes through a `Wardrobe`. Assets in `humanoid/assets/` (the host serves them; `setHumanAssetBase`). | Scale `src/humanoid` (v0.257) |
| `@futuremagic/stage` | The shader policy for `three/webgpu` games: `createRenderer` (WebGPU only, or WebGPU with WebGL 2 fallback, the game picks), the `Stage` (`warmUp`, `add`, `prepare`, `warmLater`), the compile cap, the renderer hooks on three r186 internals, and the build monitor. Each game passes its own material registry (`StageOptions.kinds`). | Dunfinity `src/render/stage.ts`, `renderer.ts`, `shaders/` (v0.281) |
| `@futuremagic/sky` | A physical sky for `three/webgpu`: `./node` has `makeSkyNode` (Rayleigh/Mie sky, sun disc and glow, phased moon, clouds, weather, horizon fog, reversed depth) and `makeStarsNode`. `.` is pure: the sun and moon path (`skyPath`, `moonAt`), the light rig as numbers (`skyLight`: key light, hemisphere, fog, exposure, environment) and a seeded `starField`. | Scale `src/render/SkySystem.ts`, `webgpu/sky.ts` (v0.257) |
| `@futuremagic/texgen` | Procedural, tileable PBR texture layers on the CPU (pure, runs in workers): facade walls, roofs and town grounds, plus natural ground (wild grass, forest floor, rock, cliff strata, scree, snow, sand, mud). Each layer gives albedo RGBA (a = roughness) and normal RGBA (rg = normal, b = height, a = AO). | Scale `src/render/texgen` (natural layers new, for MasterWorld) |
| `@futuremagic/vegetation` | Procedural trees and shrubs: 10 species with species-shaped branching wood, leaf-card crowns with baked occlusion and far canopy hulls (`treeModel`, `shrubModel`, pure geometry), the bark and leaf atlases (`vegetationTextures`, canvas), and `./node`: wind-swayed bark, leaf (autumn, translucency) and far-hull node materials. | Scale `src/props/vegetation.ts`, `webgpu/vegetation.ts` (v0.264) |
| `@futuremagic/volume` | Rock volumes in signed distances: `surfaceNets` meshes a padded grid into a smooth, indexed mesh with gradient normals; neighbouring chunks join without gaps or doubles, and `overlap` hides cracks next to coarser chunks. Pure, runs in workers. | Dunfinity `src/gen/surfaceNets.ts` (v0.289) |

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
