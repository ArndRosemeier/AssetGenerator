/**
 * Creatures modelled in Blender (AssetGenerator's creature generators, e.g. `creature_quarry_rat`): one
 * skinned glb with its clips. `ModelledCreature.load` loads it once and gives every part the material the
 * game picks for it by the part's material name (the game keeps its own material registry, and can take
 * the glb's maps into it); `figure()` is a copy with its own skeleton and its own clip player. Clips play
 * one at a time, faded into the next so nothing pops; gaits are paced by distance travelled so the feet
 * stay planted at any speed; a flinch is layered on top. From Dunfinity.
 */
import { AdditiveAnimationBlendMode, AnimationMixer, AnimationUtils, Group, LoopOnce, LoopRepeat, Mesh, type AnimationAction, type AnimationClip, type Material, type Object3D } from 'three/webgpu';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { clone } from 'three/examples/jsm/utils/SkeletonUtils.js';

/** How a clip is played: looped (by time, or by distance with `stride` metres per cycle at size 1), or once and held. */
export interface ClipUse {
  readonly loop: boolean;
  readonly stride?: number;
}

/** The material for a part, by the glb material's name (the loaded one is given, for its maps); null keeps none and throws. */
export type MaterialFor = (name: string, loaded: Material) => Material | null;

export class ModelledCreature {
  private constructor(private readonly template: Object3D, readonly clips: ReadonlyMap<string, AnimationClip>) {}

  static async load(url: string, materialFor: MaterialFor, shadows = true): Promise<ModelledCreature> {
    const gltf = await new GLTFLoader().loadAsync(url);
    gltf.scene.traverse((o) => {
      if (!(o instanceof Mesh)) return;
      const loaded = o.material as Material;
      const m = materialFor(loaded.name, loaded);
      if (!m) throw new Error(`creature ${url}: no material for "${loaded.name}"`);
      if (m !== loaded) loaded.dispose();
      o.material = m;
      o.castShadow = o.receiveShadow = shadows;
      // Its bounds are the rest pose's: a creature rolled over on its side would be culled while in view.
      o.frustumCulled = false;
    });
    const clips = new Map<string, AnimationClip>();
    for (const c of gltf.animations) clips.set(c.name, c);
    return new ModelledCreature(gltf.scene, clips);
  }

  /** A copy with its own skeleton (geometry and materials shared), playing `uses`; `flinch` is layered on top when hurt. */
  figure(uses: Readonly<Record<string, ClipUse>>, flinch?: string): ModelledFigure {
    return new ModelledFigure(clone(this.template), this, uses, flinch);
  }
}

/** One modelled creature drawn: place `root`, `play` a clip, `pace` its stride, `hurt`, then `advance`. */
export class ModelledFigure {
  readonly root = new Group();
  private readonly mixer: AnimationMixer;
  private readonly actions = new Map<string, AnimationAction>();
  private readonly flinch: AnimationAction | null;
  private current = '';
  /** Seconds a change of clip takes to fade over. */
  fade = 0.22;

  constructor(readonly model: Object3D, rig: ModelledCreature, private readonly uses: Readonly<Record<string, ClipUse>>, flinch?: string) {
    this.root.add(model);
    this.mixer = new AnimationMixer(model);
    for (const [name, use] of Object.entries(uses)) {
      const clip = rig.clips.get(name);
      if (!clip) throw new Error(`creature clip "${name}" is missing`);
      const a = this.mixer.clipAction(clip);
      a.setLoop(use.loop ? LoopRepeat : LoopOnce, Infinity);
      a.clampWhenFinished = !use.loop;
      if (use.stride !== undefined) a.timeScale = 0; // its time is set from the distance travelled
      this.actions.set(name, a);
    }
    const f = flinch ? rig.clips.get(flinch) : undefined;
    if (flinch && !f) throw new Error(`creature clip "${flinch}" is missing`);
    if (f) {
      this.flinch = this.mixer.clipAction(AnimationUtils.makeClipAdditive(f.clone()));
      this.flinch.blendMode = AdditiveAnimationBlendMode;
      this.flinch.setLoop(LoopOnce, 1);
      this.flinch.clampWhenFinished = false;
    } else this.flinch = null;
  }

  /** Play `name` (fading from what played before; a clip played once starts over when it is played again after another). */
  play(name: string): void {
    if (name === this.current) return;
    const next = this.actions.get(name);
    if (!next) throw new Error(`creature clip "${name}" is not in use`);
    const prev = this.actions.get(this.current);
    next.reset();
    next.enabled = true;
    next.setEffectiveWeight(1);
    next.play();
    if (prev) prev.crossFadeTo(next, this.fade, false);
    else next.fadeIn(0);
    this.current = name;
  }

  /** The clip playing. */
  get playing(): string { return this.current; }

  /** Set the playing stride clip's phase from `distance` travelled (metres, at size 1). */
  pace(distance: number): void {
    const stride = this.uses[this.current]?.stride, a = this.actions.get(this.current);
    if (!stride || !a) return;
    const d = a.getClip().duration;
    a.time = ((((distance / stride) % 1) + 1) % 1) * d;
  }

  /** Flinch (a hit), on top of whatever is playing. */
  hurt(): void {
    if (!this.flinch) return;
    this.flinch.reset();
    this.flinch.play();
  }

  advance(dt: number): void {
    this.mixer.update(dt);
  }
}
