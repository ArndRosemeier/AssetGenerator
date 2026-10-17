/**
 * One animated, dressed humanoid: Character + Animator + EquipmentRig, built in one go from loaded
 * assets (the body build takes some tens of milliseconds on the main thread; a game builds its
 * hero before play starts). For crowds, build bodies in a worker and assemble the parts yourself.
 */
import * as THREE from 'three/webgpu';
import type { HumanoidAppearance } from '../types';
import type { EquipmentVisuals } from '../wearable';
import { loadHumanAssets } from '../assets';
import { buildCharacter } from '../characterBuild';
import { getHumanStatic } from './staticData';
import { Character, CharacterGeometry } from './Character';
import { Animator, type GroundFn } from './anim/Animator';
import { clipLibraryReady } from './anim/clips';
import { EquipmentRig, type Wardrobe } from './equipment';
import type { AnimState, Vec3 } from './anim/types';
import { ghostly, ghostFade, type Ghost, type GhostFade } from './ghost';
import { skeletal, type Bones } from './skeletal';

export interface HumanoidOptions {
  wardrobe: Wardrobe;
  castShadow?: boolean;
  /** Facial expressions (moods, blinking). */
  expressions?: boolean;
  /** Seen through and glowing at the rim, in this tint (src/three/ghost.ts); casts no shadow. */
  ghost?: Ghost;
  /** Only its bones (src/three/skeletal.ts): the flesh taken away, the skeleton shown and animated as the living. */
  bones?: Bones;
}

/** What the humanoid does this frame. */
export interface HumanoidFrame {
  /** Feet position. */
  pos: Vec3;
  /** World velocity (m/s). */
  vel: Vec3;
  /** Facing (rad): the model's −Z turned by yaw about +Y. */
  yaw: number;
  anim: AnimState;
  combat?: boolean;
  sneaking?: boolean;
}

export class Humanoid {
  readonly object = new THREE.Group();
  readonly char: Character;
  readonly animator: Animator;
  readonly equipment: EquipmentRig;

  /** Loads the body assets and the animation clips, then builds. */
  static async create(app: HumanoidAppearance, opts: HumanoidOptions): Promise<Humanoid> {
    const [as] = await Promise.all([loadHumanAssets(), clipLibraryReady()]);
    return new Humanoid(new CharacterGeometry(getHumanStatic(as), buildCharacter(as, app)), app, opts);
  }

  constructor(geo: CharacterGeometry, readonly app: HumanoidAppearance, opts: HumanoidOptions) {
    this.object.name = 'humanoid-rig';
    this.char = new Character(geo, app, { castShadow: opts.castShadow, expressions: opts.expressions });
    this.animator = new Animator(this.char);
    this.equipment = new EquipmentRig(this.char, opts.wardrobe);
    this.object.add(this.char.object);
    if (opts.bones) this.own = skeletal(this.char, opts.bones, opts.castShadow !== false);
    this.ghost = opts.ghost ?? null;
    if (this.ghost) ghostly(this.object, this.ghost, this.fadeU);
  }

  private readonly ghost: Ghost | null;
  /** What a skeleton added (its bones' mesh and materials). */
  private own: ReturnType<typeof skeletal> | null = null;
  private readonly fadeU: GhostFade = ghostFade();

  /** A ghost's fade, 0 (gone) to 1 (fully there); nothing for the living. Set any frame (a uniform). */
  get fade(): number { return this.fadeU.value; }
  set fade(v: number) { this.fadeU.value = v; }

  /** Height of the built body (m). */
  get height(): number { return this.char.geo.build.body.height; }

  /** Dress (rebuilds only what changed). */
  dress(eq: EquipmentVisuals | undefined): void {
    this.equipment.set(eq);
    if (this.ghost) ghostly(this.object, this.ghost, this.fadeU);
  }

  /** A socket ('head', 'grip.R', 'hip.L', ...) or null. */
  socket(name: string): THREE.Object3D | null {
    return this.char.sockets.get(name) ?? null;
  }

  /** Pose for this frame; `ground` lets the feet find uneven floor. */
  update(f: HumanoidFrame, dt: number, time: number, ground: GroundFn | null = null): void {
    this.object.position.set(f.pos[0], f.pos[1], f.pos[2]);
    this.object.rotation.y = f.yaw;
    const eq = this.equipment;
    const combat = !!f.combat;
    eq.setDrawn(combat);
    this.animator.update(
      { anim: f.anim, vel: f.vel, yaw: f.yaw, time, main: eq.drawn ? eq.main : 'none', off: eq.drawn ? eq.off : 'none', combat, sneaking: !!f.sneaking },
      dt,
      this.char.lod,
      ground,
    );
    eq.update(time);
  }

  dispose(): void {
    this.equipment.dispose();
    for (const g of this.own?.geometries ?? []) g.dispose();
    for (const m of this.own?.materials ?? []) m.dispose();
    this.char.dispose();
    this.object.removeFromParent();
  }
}
