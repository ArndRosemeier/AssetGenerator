# TypeScript packages

Runtime code shared by the futuremagic games (Dunfinity first). The Python/Blender
asset pipeline lives next to this in `tools/` and `blender/` and is unaffected.

| Package | What | Came from |
| --- | --- | --- |
| `@futuremagic/core` | Seeded hashing and PRNG (`deriveSeed`, `Rng`), simplex/fbm/ridged/cellular noise, scalar and vector math, a min-heap. No three.js, no DOM. | Scale `src/core` (v0.257) |
| `@futuremagic/humanoid` | Scale's humans. `.`: the pure body build (MakeHuman bodies, races, looks, hair and parts, garment specs), runs in workers and tests. `./three`: `Humanoid` (skinned character, node materials for skin, eyes, hair and garments, garment shells fitted to any body, the animator with mocap clips), `three/webgpu` only. Games bring their clothes through a `Wardrobe`. Assets in `humanoid/assets/` (the host serves them; `setHumanAssetBase`). | Scale `src/humanoid` (v0.257) |

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
