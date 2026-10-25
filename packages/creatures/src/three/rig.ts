/**
 * A procedural creature's animation (docs/design/procedural-creatures.md): nothing is keyframed,
 * every pose is worked out each frame from how the creature moves and what it is doing. Ported from
 * Norgo's creature rig (Arnd's own world).
 *
 *  - Legs: gaits by phase (a walk, a trot, a gallop, a bound, a biped's stride, an insect's
 *    alternating tripod, waves down many legs or round a star's arms). A foot on the ground stays
 *    planted where it stands; a swinging foot arcs to where it will land. Two-bone IK, with a raised
 *    heel held at its lean.
 *  - Body: its height, pitch and roll from where its feet stand, a bob with the gait, the spine
 *    bending into turns and swaying with a sprawler's walk, a snake's waves, a slug's ripple,
 *    breathing.
 *  - Spring chains: tails, feelers, eye stalks, lures and tentacles trail behind turns and
 *    starts, damped so they never wobble.
 *  - The head turns to what it watches (you), spread over the neck; ears twitch; the jaw opens.
 *  - Actions, laid over the walk: bite, lunge, sting, slam, rear, pinch, flinch, die. Each one
 *    winds up before it strikes, so it reads (docs: every action needs a visible animation).
 *
 * The hot path allocates nothing.
 */
import { Euler, Matrix4, Quaternion, Vector3, type Bone, type Object3D } from 'three/webgpu';
import { angleDiff, clamp, damp, lerp, smoothstep } from '@futuremagic/core';
import { solveKnee, type Anatomy, type LegDef, type V3 } from '../anatomy';
import type { Species } from '../bestiary';

/** Where the ground is under a point. */
export type GroundAt = (x: number, z: number) => number;

/** What the rig reads of the creature each frame. */
export interface RigInput {
  readonly x: number;
  readonly y: number;
  readonly z: number;
  readonly yaw: number;
  readonly vx: number;
  readonly vz: number;
  /** Lying still (asleep, dead). */
  readonly dead: boolean;
  /** What it is doing now and how far into it (0..1): 'bite', 'lunge', 'sting', 'slam', 'rear', 'pinch', 'flinch', or ''. */
  readonly action: string;
  readonly actionT: number;
  /** A point it watches, or null. */
  readonly lookAt: readonly [number, number, number] | null;
  /** Running (a faster gait). */
  readonly running: boolean;
  /** At rest: 'feed' (head down, chewing, cropping or licking) or 'rest' (lying down, breathing slow); '' none. */
  readonly pose?: '' | 'feed' | 'rest';
  readonly time: number;
  readonly scale: number;
}

interface LegState {
  readonly def: LegDef;
  readonly bones: Bone[];
  readonly planted: Vector3;
  readonly lift: Vector3;
  readonly target: Vector3;
  swinging: boolean;
  groundY: number;
  offset: number;
  readonly restFoot: Vector3;
  readonly restDirs: Vector3[];
  readonly pole: Vector3;
  readonly foot: Vector3;
  started: boolean;
}

interface Spring {
  readonly bone: Bone;
  yaw: number;
  pitch: number;
  vy: number;
  vp: number;
}

const _v0 = new Vector3(), _v1 = new Vector3(), _v2 = new Vector3(), _v3 = new Vector3(), _v4 = new Vector3();
const _q0 = new Quaternion(), _q1 = new Quaternion(), _q2 = new Quaternion();
const _e0 = new Euler();
const _m0 = new Matrix4();
const _hip: V3 = [0, 0, 0], _tgt: V3 = [0, 0, 0], _pole: V3 = [0, 0, 0], _knee: V3 = [0, 0, 0];

/** World rotation of an object (its matrixWorld, uniformly scaled). */
function worldQuat(o: Object3D, out: Quaternion): Quaternion {
  const e = o.matrixWorld.elements;
  const s = Math.hypot(e[0], e[1], e[2]) || 1;
  _m0.set(e[0] / s, e[4] / s, e[8] / s, 0, e[1] / s, e[5] / s, e[9] / s, 0, e[2] / s, e[6] / s, e[10] / s, 0, 0, 0, 0, 1);
  return out.setFromRotationMatrix(_m0);
}

function setEuler(b: Bone, x: number, y: number, z: number): void {
  _e0.set(x, y, z, 'YXZ');
  b.quaternion.setFromEuler(_e0);
}

/** A damped spring towards `target` (critically damped or close: it settles, never wobbles). */
function spring(s: Spring, ty: number, tp: number, k: number, dt: number): void {
  const c = 2 * Math.sqrt(k) * 0.85;
  s.vy += (k * (ty - s.yaw) - c * s.vy) * dt;
  s.vp += (k * (tp - s.pitch) - c * s.vp) * dt;
  s.yaw += s.vy * dt;
  s.pitch += s.vp * dt;
  setEuler(s.bone, s.pitch, s.yaw, 0);
}

export class CritterRig {
  private readonly legs: LegState[];
  private readonly arms: LegState[];
  private readonly tail: Spring[];
  private readonly feelers: Spring[][];
  private readonly tentacles: Spring[][];
  private readonly lure: Spring[];
  private readonly neck: Bone[];
  private readonly head: Bone;
  private readonly jaw: Bone | null;
  private readonly root: Bone;
  private readonly spine: Bone[];
  private readonly ears: Bone[];
  private readonly pincers: Bone[];
  private readonly bell: Bone | null;

  private phase = 0;
  private yawPrev = NaN;
  private turnRate = 0;
  private speedS = 0;
  private bodyLift = 0;
  private bodyPitch = 0;
  private bodyRoll = 0;
  private headYaw = 0;
  private headPitch = 0;
  private deadT = 0;
  /** How far into feeding and lying down at rest (0..1, eased in and out). */
  private feedA = 0;
  private restA = 0;
  private wavePhase = 0;
  private earTimer = 0;
  private earTwitch = 0;
  private hopLift = 0;
  private readonly seedF: number;
  private readonly legLen: number;
  private readonly walker: boolean;
  private readonly snake: boolean;
  private readonly slug: boolean;
  private readonly floater: boolean;

  constructor(readonly sp: Species, readonly body: Anatomy, bones: readonly Bone[], readonly object: Object3D, private readonly ground: GroundAt) {
    this.root = bones[0];
    this.spine = body.spine.map((i) => bones[i]);
    this.neck = body.neck.map((i) => bones[i]);
    this.head = bones[body.head];
    this.jaw = body.jaw >= 0 ? bones[body.jaw] : null;
    this.ears = body.ears.map((i) => bones[i]);
    this.pincers = body.pincers.map((i) => bones[i]);
    this.bell = body.bell >= 0 ? bones[body.bell] : null;
    this.seedF = (sp.seed % 1000) / 1000;
    this.legLen = body.legLength;
    this.walker = body.legs.length > 0;
    this.snake = sp.plan === 'serpent';
    this.slug = sp.plan === 'slug';
    this.floater = sp.plan === 'floater';
    const mkLeg = (d: LegDef): LegState => {
      const bs = d.bones.map((i) => bones[i]);
      const restDirs = bs.map((_, i) => {
        const next = i + 1 < bs.length ? body.bones[d.bones[i + 1]].pos : d.foot;
        const p = body.bones[d.bones[i]].pos;
        return new Vector3(next[0] - p[0], next[1] - p[1], next[2] - p[2]).normalize();
      });
      const s = d.side;
      const pole = d.pole === 'fwd' ? new Vector3(s * 0.1, 0, 1) : d.pole === 'back' ? new Vector3(s * 0.1, 0, -1) : d.pole === 'up' ? new Vector3(0, 1, 0) : new Vector3(s, 0.3, 0);
      if (d.kind === 'radial') {
        const hp = body.bones[d.bones[0]].pos;
        pole.set(hp[0] * 0.5, 1, hp[2] * 0.5);
      }
      if (d.kind === 'arm' && body.pincers.length) pole.set(s, 0.6, 0);
      return {
        def: d, bones: bs, planted: new Vector3(), lift: new Vector3(), target: new Vector3(), swinging: false, groundY: 0,
        offset: 0, restFoot: new Vector3(...d.foot), restDirs, pole: pole.normalize(), foot: new Vector3(), started: false,
      };
    };
    this.legs = body.legs.map(mkLeg);
    this.arms = body.arms.map(mkLeg);
    const springs = (ids: readonly number[]) => ids.map((i) => ({ bone: bones[i], yaw: 0, pitch: 0, vy: 0, vp: 0 }));
    this.tail = springs(body.tail);
    this.feelers = body.antennae.map((c) => springs(c.bones));
    this.tentacles = body.tentacles.map((c) => springs(c.bones));
    this.lure = springs(body.lure?.bones ?? []);
    this.offsets(false, 1);
  }

  // ------------------------------------------------------------------ gaits

  private gaitKind(running: boolean): string {
    const g = this.sp.gait;
    const n = this.legs.length;
    if (n === 0) return g;
    if (g === 'tripod' || g === 'wave') return g;
    if (n === 2) return 'stride';
    if (!running) return 'walk';
    return g === 'walk' || g === 'stride' || g === 'waddle' ? 'trot' : g;
  }

  /** Each leg's phase offset in the gait (eased towards it when the gait changes). */
  private offsets(running: boolean, blend: number): void {
    const kind = this.gaitKind(running);
    const pairs = Math.max(1, Math.ceil(this.legs.length / 2));
    for (const L of this.legs) {
      const d = L.def;
      const left = d.side > 0;
      let o: number;
      switch (kind) {
        case 'walk': o = (left ? 0 : 0.5) + (d.pairIndex >= 1 ? 0.25 : 0); break;
        case 'trot': o = (left ? 0 : 0.5) + (d.pairIndex >= 1 ? 0.5 : 0); break;
        case 'gallop': o = (left ? 0 : 0.1) + (d.pairIndex >= 1 ? 0.55 : 0); break;
        case 'bound': o = (left ? 0 : 0.06) + (d.pairIndex >= 1 ? 0.5 : 0); break;
        case 'stride': case 'waddle': o = left ? 0 : 0.5; break;
        case 'tripod': o = ((d.pairIndex + (left ? 0 : 1)) % 2) * 0.5; break;
        default: o = d.kind === 'radial' ? d.along : ((((-d.pairIndex / pairs) * 0.85) % 1) + 1) % 1 + (left ? 0 : 0.5);
      }
      o = ((o % 1) + 1) % 1;
      let diff = o - L.offset;
      if (diff > 0.5) diff -= 1;
      if (diff < -0.5) diff += 1;
      L.offset = (((L.offset + diff * blend) % 1) + 1) % 1;
    }
  }

  private duty(running: boolean): number {
    switch (this.gaitKind(running)) {
      case 'walk': return 0.68;
      case 'trot': return 0.5;
      case 'gallop': return 0.36;
      case 'bound': return 0.4;
      case 'stride': case 'waddle': return running ? 0.38 : 0.62;
      case 'tripod': return running ? 0.5 : 0.6;
      default: return running ? 0.6 : 0.75;
    }
  }

  private stride(running: boolean): number {
    const base: Record<string, number> = { walk: 0.9, trot: 1.35, gallop: 2.3, bound: 1.9, stride: running ? 1.9 : 1.05, waddle: 0.6, tripod: running ? 1.1 : 0.8, wave: 0.7 };
    return (base[this.gaitKind(running)] ?? 0.8) * this.legLen;
  }

  // ------------------------------------------------------------------ the pose

  update(dt: number, inp: RigInput): void {
    dt = Math.min(dt, 0.1);
    const sp = this.sp, obj = this.object, scale = inp.scale, t = inp.time;
    if (Number.isNaN(this.yawPrev)) this.yawPrev = inp.yaw;
    obj.position.set(inp.x, inp.y + (this.floater ? sp.altitude * scale : 0), inp.z);
    obj.rotation.set(0, inp.yaw + Math.PI, 0);
    obj.scale.setScalar(scale);
    const dyaw = angleDiff(this.yawPrev, inp.yaw);
    this.yawPrev = inp.yaw;
    this.turnRate = lerp(this.turnRate, dt > 0 ? dyaw / dt : 0, damp(8, dt));
    const hSpeed = Math.hypot(inp.vx, inp.vz);
    this.speedS = lerp(this.speedS, hSpeed, damp(6, dt));
    const dead = inp.dead;
    this.deadT = dead ? Math.min(1, this.deadT + dt * 1.6) : Math.max(0, this.deadT - dt * 2);
    const pose = dead ? '' : inp.pose ?? '';
    this.feedA = clamp(this.feedA + (pose === 'feed' ? dt * 2 : -dt * 3), 0, 1);
    this.restA = clamp(this.restA + (pose === 'rest' ? dt * 0.8 : -dt * 1.5), 0, 1);
    const feed = smoothstep(0, 1, this.feedA), rest = smoothstep(0, 1, this.restA);
    const running = inp.running;
    this.offsets(running, damp(5, dt));
    const duty = this.duty(running);

    // ---- actions, as channels laid over the walk
    const at = clamp(inp.actionT, 0, 1);
    let lunge = 0, crouch = 0, aPitch = 0, aRoll = 0, headP = 0, headY = 0, jawOpen = 0, tailArc = 0, frontRaise = 0, pinch = 0;
    switch (inp.action) {
      case 'bite': {
        const wind = smoothstep(0, 0.35, at) * (1 - smoothstep(0.4, 0.55, at));
        const strike = smoothstep(0.35, 0.55, at) * (1 - smoothstep(0.65, 1, at));
        lunge = strike * 0.22; headP = -wind * 0.35 + strike * 0.3; jawOpen = wind * 0.9 + (at < 0.5 ? strike * 0.8 : 0); crouch = wind * 0.1;
        break;
      }
      case 'lunge': {
        const c = smoothstep(0, 0.35, at) * (1 - smoothstep(0.35, 0.45, at));
        const l = smoothstep(0.35, 0.55, at) * (1 - smoothstep(0.75, 1, at));
        crouch = c * 0.35; aPitch = -l * 0.3 + c * 0.1; frontRaise = l * 0.8; jawOpen = l * 0.8; lunge = l * 0.3;
        break;
      }
      case 'sting': {
        const s = smoothstep(0, 0.4, at) * (1 - smoothstep(0.7, 1, at));
        tailArc = s + smoothstep(0.4, 0.55, at) * (1 - smoothstep(0.6, 0.9, at)) * 0.6; crouch = s * 0.08; aPitch = s * 0.06;
        break;
      }
      case 'slam': {
        const up = Math.sin(Math.PI * clamp(at * 1.2, 0, 1));
        aPitch = -up * 0.25; frontRaise = up; headP = -up * 0.15; jawOpen = up * 0.3; lunge = smoothstep(0.4, 0.6, at) * (1 - smoothstep(0.7, 1, at)) * 0.15;
        break;
      }
      case 'rear': {
        const s = smoothstep(0, 0.25, at) * (1 - smoothstep(0.8, 1, at));
        headP = -s * 0.5; jawOpen = s * 0.8; aPitch = -s * 0.15; frontRaise = s * 0.4; pinch = s;
        break;
      }
      case 'pinch': {
        const open = smoothstep(0, 0.4, at) * (1 - smoothstep(0.45, 0.55, at));
        pinch = open; lunge = smoothstep(0.4, 0.55, at) * (1 - smoothstep(0.7, 1, at)) * 0.15; crouch = open * 0.08;
        break;
      }
      case 'flinch': {
        const s = Math.sin(Math.PI * clamp(at * 1.4, 0, 1));
        aPitch = -s * 0.18; aRoll = s * 0.15 * (this.seedF > 0.5 ? 1 : -1); headY = s * 0.4; crouch = s * 0.08; jawOpen = s * 0.4;
        break;
      }
    }

    // Feeding: the head down to the floor (or the wall, the water, the bloom), the jaw working.
    headP += feed * 0.6 + rest * 0.25;
    jawOpen += feed * Math.max(0, Math.sin(t * 7 + this.seedF * 5)) * 0.35;

    // ---- the body, on the root bone
    const L = this.legLen;
    const gk = this.gaitKind(running);
    const moving = this.speedS > 0.03 * scale;
    const amp = clamp(this.speedS / Math.max(0.1, sp.runSpeed * scale), 0, 1);
    let bob = 0, pitchOsc = 0, rollOsc = 0;
    if (this.walker && moving) {
      const ph = this.phase * Math.PI * 2;
      if (gk === 'gallop' || gk === 'bound') { bob = Math.sin(ph) * 0.06 * L; pitchOsc = Math.sin(ph + 1.2) * 0.12 * amp; }
      else if (gk === 'stride' || gk === 'waddle') { bob = Math.abs(Math.sin(ph)) * 0.04 * L - 0.02 * L; rollOsc = Math.sin(ph) * (gk === 'waddle' ? 0.12 : 0.04); }
      else { bob = Math.sin(ph * 2) * 0.025 * L; rollOsc = Math.sin(ph) * 0.02; }
    }
    const breathe = Math.sin(t * (2.4 + amp * 4) + this.seedF * 7) * 0.015 * (1 + rest * 1.5);

    // Pitch and roll from where the feet stand.
    let targetPitch = 0, targetRoll = 0, targetLift = 0;
    if (this.walker && this.legs[0].started) {
      let fy = 0, fn = 0, by = 0, bn = 0, ly = 0, ln = 0, ry = 0, rn = 0, all = 0;
      for (const Lg of this.legs) {
        const gy = (Lg.swinging ? Lg.groundY : Lg.planted.y) - inp.y;
        all += gy;
        if (Lg.def.along > 0.5) { fy += gy; fn++; } else { by += gy; bn++; }
        if (Lg.def.side > 0) { ly += gy; ln++; } else { ry += gy; rn++; }
      }
      const span = Math.max(0.1, sp.length * scale);
      if (fn && bn) targetPitch = -Math.atan2(fy / fn - by / bn, span) * 0.8;
      if (ln && rn) targetRoll = Math.atan2(ly / ln - ry / rn, span * sp.girth * 2 + 0.1) * 0.5;
      targetLift = clamp(all / this.legs.length, -L * 0.4 * scale, L * 0.4 * scale) / scale;
    }
    this.bodyPitch = lerp(this.bodyPitch, clamp(targetPitch, -0.6, 0.6), damp(6, dt));
    this.bodyRoll = lerp(this.bodyRoll, clamp(targetRoll, -0.4, 0.4), damp(6, dt));
    this.bodyLift = lerp(this.bodyLift, targetLift, damp(8, dt));

    const ph = this.body.pelvisHeight;
    // Lying down: dead, or at rest (folded, not rolled over).
    const lie = Math.max(this.deadT, rest * 0.55);
    const deathRoll = smoothstep(0, 1, this.deadT) * (Math.PI / 2 - 0.25) * (this.seedF > 0.5 ? 1 : -1) * (this.walker && this.legs.length <= 4 ? 1 : 0.15);
    const sinkTo = Math.min(ph, sp.length * sp.girth * sp.bodyHeight * 0.9);
    const rootY = this.bodyLift + bob + this.hopLift - crouch * ph - lie * (ph - sinkTo) * (this.floater ? 0 : 1);
    let rootPitch = this.bodyPitch + pitchOsc + aPitch;
    let rootRoll = this.bodyRoll + rollOsc + aRoll + deathRoll;
    if (this.floater) {
      rootPitch = Math.sin(t * 0.4 + this.seedF * 5) * 0.08 + clamp(-this.speedS * 0.2, -0.3, 0);
      rootRoll = Math.sin(t * 0.33 + this.seedF * 3) * 0.08;
    }
    this.root.position.set(0, rootY - (this.floater ? lie * sp.altitude : 0), lunge * sp.length);
    setEuler(this.root, -rootPitch, 0, rootRoll);

    // ---- spine: sway, waves, breathing
    const nSp = this.spine.length;
    const waves = this.snake || this.slug;
    this.wavePhase += dt * (this.snake ? 1.2 + (this.speedS / Math.max(0.2, sp.length * scale)) * 1.4 : this.slug ? 0.5 + this.speedS * 3 : 0);
    for (let i = 0; i < nSp; i++) {
      const b = this.spine[i];
      const u = nSp > 1 ? i / (nSp - 1) : 0;
      let yawS = 0, pitchS = 0;
      if (this.snake) yawS = Math.sin(this.wavePhase * Math.PI * 2 - u * 4.2) * 0.32 * (moving ? 0.7 + amp * 0.3 : 0.25);
      else if (this.slug) pitchS = Math.sin(this.wavePhase * Math.PI * 2 - u * 5) * 0.025;
      else if (this.walker && moving) {
        // A sprawler's body bends with its walk; a mammal's barely.
        yawS = Math.sin(this.phase * Math.PI * 2 + u * 1.5) * (0.03 + sp.limbs.splay * 0.14) * amp;
        if (gk === 'gallop' || gk === 'bound') pitchS = Math.sin(this.phase * Math.PI * 2 + 0.5) * 0.08 * amp;
      }
      yawS += clamp(this.turnRate * 0.06, -0.15, 0.15) * (i > 0 ? 1 : 0) * (waves ? 2 : 1);
      setEuler(b, pitchS, i === 0 ? 0 : yawS, 0);
      if (i === nSp - 1 || (nSp === 1 && !this.bell)) b.scale.set(1 + breathe, 1 + breathe * 1.4, 1);
    }

    // ---- a drifter's bell pulses
    if (this.bell) {
      const pulse = Math.sin(t * (1.6 + amp * 2) + this.seedF * 6);
      const s = 1 + pulse * 0.09;
      this.bell.scale.set(s, 1 - pulse * 0.07, s);
    }

    // ---- neck and head: watching
    let tYaw = 0, tPitch = 0;
    if (inp.lookAt && !dead) {
      obj.updateMatrixWorld();
      _v1.set(inp.lookAt[0], inp.lookAt[1], inp.lookAt[2]).applyMatrix4(_m0.copy(obj.matrixWorld).invert());
      const hp = this.body.bones[this.body.head].pos;
      _v1.x -= hp[0]; _v1.y -= hp[1]; _v1.z -= hp[2];
      tYaw = Math.atan2(_v1.x, _v1.z);
      tPitch = Math.atan2(_v1.y, Math.hypot(_v1.x, _v1.z));
      if (Math.abs(tYaw) > 2.2) tYaw = 0;
    } else {
      // Glances about, and into turns.
      const g = Math.sin(t * 0.37 + this.seedF * 11) * Math.sin(t * 0.23 + this.seedF * 3);
      tYaw = moving ? clamp(this.turnRate * 0.35, -0.6, 0.6) : g * 0.7;
      tPitch = moving ? 0 : Math.sin(t * 0.29 + this.seedF * 5) * 0.15;
    }
    tYaw = clamp(tYaw + headY, -1.3, 1.3);
    tPitch = clamp(tPitch, -0.7, 0.6);
    this.headYaw = lerp(this.headYaw, tYaw, damp(5, dt));
    this.headPitch = lerp(this.headPitch, tPitch, damp(5, dt));
    const share = 1 / (this.neck.length + 1);
    const pitchDown = headP + lie * 0.5 - this.headPitch;
    for (let i = 0; i < this.neck.length; i++) {
      const sway = moving ? Math.sin(this.phase * Math.PI * 4 + i) * 0.03 : 0;
      setEuler(this.neck[i], pitchDown * share + sway, this.headYaw * share, 0);
    }
    if (this.head !== this.spine[nSp - 1]) setEuler(this.head, pitchDown * share - rootPitch * 0.4, this.headYaw * share, Math.sin(t * 0.5 + this.seedF) * 0.04);
    if (this.jaw) {
      const pant = running ? 0.12 + Math.sin(t * 10) * 0.05 : 0;
      setEuler(this.jaw, clamp(jawOpen + pant + this.deadT * 0.3, 0, 1.1) * 0.55, 0, 0);
    }
    for (let i = 0; i < this.pincers.length; i++) {
      const idle = Math.max(0, Math.sin(t * 1.3 + i * 2.1 + this.seedF * 9)) * 0.15;
      setEuler(this.pincers[i], -(pinch + idle) * 0.6, 0, 0);
    }
    if (this.ears.length) {
      this.earTimer -= dt;
      if (this.earTimer < 0) { this.earTimer = 1.5 + ((((Math.sin(t * 12.9898 + this.seedF * 78.2) * 43758.5) % 1) + 1) % 1) * 5; this.earTwitch = 1; }
      this.earTwitch = Math.max(0, this.earTwitch - dt * 6);
      const pin = inp.action === 'bite' || inp.action === 'rear' ? 0.8 : 0;
      for (let i = 0; i < this.ears.length; i++) {
        const s = i === 0 ? 1 : -1;
        setEuler(this.ears[i], -pin * 0.9 + lie * 0.5, s * this.earTwitch * 0.4 * (i === 0 ? 1 : 0.3), s * pin * 0.3);
      }
    }

    // ---- tail
    const turnK = clamp(-this.turnRate * 0.18, -0.6, 0.6);
    const nT = this.tail.length;
    for (let i = 0; i < nT; i++) {
      const u = (i + 1) / nT;
      let ty = turnK * u + Math.sin(t * (1.3 + amp * 2) - i * 0.6 + this.seedF * 4) * (0.05 + 0.04 * u);
      let tp = -(running ? 0.15 : 0) * (i === 0 ? 1 : 0.25);
      if (this.snake) ty += Math.sin(this.wavePhase * Math.PI * 2 - (1 + u) * 4.2) * 0.3;
      if (dead) ty += 0.45 * (this.seedF > 0.5 ? 1 : -1) * lie;
      if (tailArc > 0) tp -= tailArc * (0.5 + u * 0.5);
      if (this.walker && moving && (gk === 'stride' || gk === 'walk')) ty += Math.sin(this.phase * Math.PI * 2) * 0.06;
      spring(this.tail[i], ty, tp, 60 / (1 + i * 0.4), dt);
    }

    // ---- feelers, stalks, lure, tentacles
    for (let a = 0; a < this.feelers.length; a++) {
      const ch = this.feelers[a];
      for (let i = 0; i < ch.length; i++) spring(ch[i], turnK * 0.5 + Math.sin(t * 3.1 + a * 2 + i) * 0.12, Math.sin(t * 2.3 + a + i * 0.7) * 0.1, 90, dt);
    }
    for (let i = 0; i < this.lure.length; i++) spring(this.lure[i], turnK * 0.4 + Math.sin(t * 1.1 + i * 0.6) * 0.08, Math.sin(t * 0.9 + i) * 0.06 - (moving ? 0.05 : 0), 40, dt);
    const fx = -Math.sin(inp.yaw), fz = -Math.cos(inp.yaw);
    const vFwd = inp.vx * fx + inp.vz * fz, vSide = inp.vx * -fz + inp.vz * fx;
    for (let a = 0; a < this.tentacles.length; a++) {
      const ch = this.tentacles[a];
      for (let i = 0; i < ch.length; i++) {
        // They trail behind its drift, slow waves running down each.
        const tp = clamp(vFwd * 0.25, -0.5, 0.5) + Math.sin(t * 1.4 - i * 0.9 + a * 1.7) * 0.18;
        const ty = clamp(-vSide * 0.25, -0.5, 0.5) + Math.cos(t * 1.1 - i * 0.8 + a) * 0.12;
        spring(ch[i], ty, tp, 30, dt);
      }
    }

    if (this.walker) this.stepLegs(dt, inp, duty, running, frontRaise, lie);
    if (this.arms.length) this.swingArms(dt, inp, frontRaise, lie);
  }

  /** Where a leg's foot stands at rest, in the world (the body's sway left out). */
  private neutral(L: LegState, out: Vector3): Vector3 {
    return out.copy(L.restFoot).applyMatrix4(this.object.matrixWorld);
  }

  private stepLegs(dt: number, inp: RigInput, duty: number, running: boolean, frontRaise: number, lie: number): void {
    const obj = this.object, scale = inp.scale;
    obj.updateMatrixWorld(true);
    const speed = this.speedS;
    const strideLen = Math.max(0.03, this.stride(running) * scale);
    // Shuffle when a foot is far from where it should stand, even standing still.
    let maxErr = 0, anySwing = false;
    for (const L of this.legs) {
      if (!L.started) continue;
      this.neutral(L, _v0);
      maxErr = Math.max(maxErr, Math.hypot(_v0.x - L.planted.x, _v0.z - L.planted.z));
      if (L.swinging) anySwing = true;
    }
    const moving = speed > 0.03 * scale;
    const shuffle = maxErr > strideLen * 0.3;
    const stepping = moving || anySwing || shuffle;
    if (stepping) this.phase = (this.phase + dt * (moving ? clamp(speed / strideLen, 0.6, 9) : 1.6)) % 1;
    const swingH = this.legLen * scale * (running ? 0.26 : 0.17);
    let hopSwing = 0;
    for (const L of this.legs) {
      if (!L.started) {
        this.neutral(L, L.planted);
        L.planted.y = this.ground(L.planted.x, L.planted.z);
        L.groundY = L.planted.y;
        L.foot.copy(L.planted);
        L.started = true;
      }
      const p = (this.phase + L.offset) % 1;
      if (p >= duty && stepping && !L.swinging) { L.swinging = true; L.lift.copy(L.planted); }
      if (L.swinging) {
        const s = clamp((p - duty) / (1 - duty), 0, 1);
        // Land where the foot will stand: its rest spot, half a stance of travel ahead.
        this.neutral(L, L.target);
        const stance = duty / Math.max(0.6, speed / strideLen);
        L.target.x += inp.vx * stance * 0.5;
        L.target.z += inp.vz * stance * 0.5;
        if (s < 0.08 || (s > 0.6 && s < 0.7)) L.groundY = this.ground(L.target.x, L.target.z);
        L.target.y = L.groundY;
        L.foot.lerpVectors(L.lift, L.target, smoothstep(0, 1, s));
        L.foot.y += Math.sin(Math.PI * s) * swingH;
        if (p < duty || s >= 1 || !stepping) {
          L.swinging = false;
          L.planted.copy(L.target);
          L.foot.copy(L.planted);
        }
        if (this.gaitKind(running) === 'bound') hopSwing = Math.max(hopSwing, Math.sin(Math.PI * s));
      } else L.foot.copy(L.planted);
      // A foot hopelessly far off (it was moved): put it back under.
      this.neutral(L, _v0);
      if (_v0.distanceToSquared(L.planted) > (strideLen * 3) ** 2) {
        L.planted.copy(_v0);
        L.planted.y = this.ground(_v0.x, _v0.z);
        L.foot.copy(L.planted);
        L.swinging = false;
      }
    }
    this.hopLift = lerp(this.hopLift, hopSwing * this.legLen * (running ? 0.35 : 0.15), damp(12, dt));

    this.root.updateMatrixWorld(true);
    for (const L of this.legs) {
      _v1.copy(L.foot);
      const d = L.def;
      const raised = frontRaise > 0 && d.along > 0.5 && (d.side > 0 || this.legs.length > 4);
      if (lie > 0.02 || raised) {
        // Pose targets in the body's frame: legs fold when it dies, the front ones rise to strike.
        _v2.copy(L.restFoot);
        const hp = this.body.bones[d.bones[0]].pos;
        if (lie > 0.02) {
          _v3.set(hp[0] + d.side * this.legLen * 0.8, hp[1] - this.legLen * 0.3, hp[2] + (d.along > 0.5 ? 0.3 : -0.3) * this.legLen);
          _v2.lerp(_v3, smoothstep(0, 1, lie));
        }
        if (raised) {
          _v3.set(hp[0], hp[1] - this.legLen * 0.25, hp[2] + this.legLen * 0.8);
          _v2.lerp(_v3, frontRaise);
        }
        _v2.applyMatrix4(this.root.matrixWorld);
        const w = clamp(Math.max(lie, raised ? frontRaise : 0), 0, 1);
        _v1.lerp(_v2, w);
        if (w > 0.5) { L.planted.copy(_v1); L.swinging = false; }
      }
      this.solve(L, _v1, scale);
    }
  }

  /** Arms swing opposite the legs; a crab's claws are held up in front; strikes raise them. */
  private swingArms(dt: number, inp: RigInput, raise: number, lie: number): void {
    this.root.updateMatrixWorld(true);
    for (const A of this.arms) {
      const d = A.def;
      const hp = this.body.bones[d.bones[0]].pos;
      const len = d.lens[0] + d.lens[1];
      const swing = Math.sin((this.phase + (d.side > 0 ? 0.5 : 0)) * Math.PI * 2) * clamp(this.speedS / Math.max(0.2, this.sp.walkSpeed), 0, 1.5) * 0.25;
      _v2.set(d.foot[0], d.foot[1] + Math.abs(swing) * len * 0.1, d.foot[2] + swing * len * (this.pincers.length ? 0.2 : 1));
      if (raise > 0) {
        _v3.set(hp[0] + d.side * len * 0.1, hp[1] + len * 0.45, hp[2] + len * 0.6);
        _v2.lerp(_v3, raise);
      }
      if (lie > 0.02) {
        _v3.set(hp[0] + d.side * len * 0.5, this.body.pelvisHeight * 0.1, hp[2] + len * 0.3);
        _v2.lerp(_v3, lie);
      }
      _v2.applyMatrix4(this.root.matrixWorld);
      if (!A.started) { A.foot.copy(_v2); A.started = true; }
      A.foot.lerp(_v2, damp(14, dt));
      this.solve(A, A.foot, inp.scale);
    }
  }

  /** Two-bone IK (and the raised heel's third segment) in the world, written into the bones' local rotations. */
  private solve(L: LegState, footW: Vector3, scale: number): void {
    const d = L.def, bs = L.bones;
    const hipB = bs[0];
    const parent = hipB.parent as Object3D;
    _v0.copy(hipB.position).applyMatrix4(parent.matrixWorld);
    worldQuat(parent, _q0);
    worldQuat(this.object, _q2);
    _v4.copy(L.pole).applyQuaternion(_q2);
    const l1 = d.lens[0] * scale, l2 = d.lens[1] * scale;
    if (d.digitigrade && bs.length === 3) {
      _v3.set(0, d.ankleUp, d.ankleFwd).normalize().applyQuaternion(_q2).multiplyScalar(d.lens[2] * scale);
      _v1.copy(footW).add(_v3);
    } else _v1.copy(footW);
    _hip[0] = _v0.x; _hip[1] = _v0.y; _hip[2] = _v0.z;
    _tgt[0] = _v1.x; _tgt[1] = _v1.y; _tgt[2] = _v1.z;
    _pole[0] = _v4.x; _pole[1] = _v4.y; _pole[2] = _v4.z;
    solveKnee(_hip, _tgt, l1, l2, _pole, _knee);
    _v2.set(_knee[0], _knee[1], _knee[2]);
    _v3.subVectors(_v2, _v0).normalize().applyQuaternion(_q1.copy(_q0).invert());
    hipB.quaternion.setFromUnitVectors(L.restDirs[0], _v3);
    _q0.multiply(hipB.quaternion);
    _v3.subVectors(_v1, _v2).normalize().applyQuaternion(_q1.copy(_q0).invert());
    bs[1].quaternion.setFromUnitVectors(L.restDirs[1], _v3);
    if (bs.length === 3) {
      _q0.multiply(bs[1].quaternion);
      _v3.subVectors(footW, _v1).normalize().applyQuaternion(_q1.copy(_q0).invert());
      bs[2].quaternion.setFromUnitVectors(L.restDirs[2], _v3);
    }
  }
}
