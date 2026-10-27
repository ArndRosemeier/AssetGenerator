/**
 * Hands-on control of an Actors figure's skeleton after its clips have played: sockets that carry
 * things on the bones (the head, a fist's grip, the hip, the forearm), a pose layer (bend the spine,
 * lift the chin, put an arm or a leg somewhere) and reaching (two-bone IK for the hands and feet,
 * fingers curled round a rung or laid flat on a floor). The ladder climb drives it.
 *
 * Directions are in the body's frame: +Z forward, +Y up, +X the figure's left (Actors' bodies face
 * +Z). Arm and leg angles follow the old humans' poses: `fwd` raises an arm forward from hanging
 * down, `out` lifts it sideways, `elbow` bends it; `flex` lifts a thigh forward, `knee` bends it back.
 */
import { Group, Matrix4, Quaternion, Vector3, type Bone, type Object3D } from 'three/webgpu';

export type Side = 'L' | 'R';

/** A hand or foot to put somewhere: a world point, how much (0..1), and which way the elbow or knee goes (body frame: out for this side, up, forward). */
export interface LimbGoal {
  p: Vector3;
  w: number;
  pole?: readonly [number, number, number];
  /** Hands: laid flat, palm down, the fingers pointing this (world) way. */
  flat?: Vector3 | null;
}

export interface LimbGoals {
  L?: LimbGoal; R?: LimbGoal;
  footL?: LimbGoal; footR?: LimbGoal;
  /** Finger curl per hand (a grip ≈ 1.2, a flat palm ≈ 0.1) and its weight. */
  curl?: { L?: number; R?: number };
  curlW?: number;
}

/** What a pose function sets: called once a frame, its weight given by the caller. */
export interface Pose {
  spine(x: number): void;
  neck(x: number): void;
  arm(side: Side, fwd: number, out: number, twist?: number, elbow?: number, pron?: number): void;
  leg(side: Side, flex: number, abd?: number, twist?: number, knee?: number, ankle?: number): void;
}

/** Where things are carried. */
export type SocketName = 'head' | 'grip.R' | 'grip.L' | 'hip.R' | 'forearm.L';

interface Chain {
  a: Bone;
  b: Bone;
  c: Bone;
}

const FINGERS = ['index', 'middle', 'ring', 'pinky'] as const;
const _a = new Vector3(), _b = new Vector3(), _c = new Vector3(), _d = new Vector3(), _e = new Vector3(), _p = new Vector3(), _t = new Vector3();
const _q = new Quaternion(), _q2 = new Quaternion(), _q3 = new Quaternion(), _m = new Matrix4(), _m2 = new Matrix4();

export class FigureRig {
  private readonly bones = new Map<string, Bone>();
  private readonly sockets = new Map<SocketName, Group>();
  /** Hip (pelvis) height over the feet in the bind pose, metres. */
  hipHeight = 0.9;
  /** Head radius (for hats), metres. */
  headRadius = 0.095;
  private readonly arms: Record<Side, Chain>;
  private readonly legs: Record<Side, Chain>;
  /** Saved quaternions, for weighting a change. */
  private readonly saved = new Map<Bone, Quaternion>();
  /** Each bone's turn in the bind pose (`fit`), and the bones turned since the last `relax`. */
  private readonly bind = new Map<Bone, Quaternion>();
  private readonly turned = new Set<Bone>();

  /** `body`: the figure's own frame (+Z forward); `bones`: Actors' skeleton (game_engine names). */
  constructor(private readonly body: Object3D, bones: readonly Bone[]) {
    for (const b of bones) this.bones.set(b.name, b);
    const chain = (a: string, b: string, c: string): Chain => ({ a: this.bone(a), b: this.bone(b), c: this.bone(c) });
    this.arms = { L: chain('upperarm_l', 'lowerarm_l', 'hand_l'), R: chain('upperarm_r', 'lowerarm_r', 'hand_r') };
    this.legs = { L: chain('thigh_l', 'calf_l', 'foot_l'), R: chain('thigh_r', 'calf_r', 'foot_r') };
    for (const s of ['head', 'grip.R', 'grip.L', 'hip.R', 'forearm.L'] as const) {
      const g = new Group();
      g.name = `socket:${s}`;
      this.sockets.set(s, g);
    }
  }

  bone(name: string): Bone {
    const b = this.bones.get(name);
    if (!b) throw new Error(`no bone ${name}`);
    return b;
  }

  /** A socket: a group riding a bone, its axes the body's in the bind pose (grips: see `fit`). */
  socket(name: SocketName): Group {
    return this.sockets.get(name)!;
  }

  /**
   * Measure the body and hang the sockets; call with the bones in the bind pose (after a new shape).
   * `height`: the standing height.
   */
  fit(height: number): void {
    const body = this.body;
    for (const b of this.bones.values()) this.bind.set(b, b.quaternion.clone());
    this.turned.clear();
    body.updateMatrixWorld(true);
    const bodyQ = body.getWorldQuaternion(new Quaternion());
    const feetY = body.getWorldPosition(new Vector3()).y;
    const pos = (n: string, out = new Vector3()) => this.bone(n).getWorldPosition(out);
    this.hipHeight = pos('pelvis').y - feetY;
    const headY = pos('head').y - feetY;
    this.headRadius = Math.max(0.07, (height - headY) * 0.5);
    // Head: between the ears, a little above the head bone; axes as the body's.
    this.hang('head', 'head', pos('head').add(_d.set(0, this.headRadius * 0.6, 0)), bodyQ);
    for (const side of ['L', 'R'] as const) {
      const s = side.toLowerCase();
      const hand = pos(`hand_${s}`), mid = pos(`middle_01_${s}`), index = pos(`index_01_${s}`), pinky = pos(`pinky_01_${s}`);
      // The grip: the fist's middle; +Y out of the thumb side (pinky → index), +Z along the fingers.
      const fingers = new Vector3().subVectors(mid, hand).normalize();
      const across = new Vector3().subVectors(index, pinky).normalize();
      const z = fingers.clone().sub(across.clone().multiplyScalar(fingers.dot(across))).normalize();
      const x = new Vector3().crossVectors(across, z);
      const q = new Quaternion().setFromRotationMatrix(_m.makeBasis(x, across, z));
      const at = hand.clone().lerp(mid, 0.55);
      this.hang(side === 'R' ? 'grip.R' : 'grip.L', `hand_${s}`, at, q);
    }
    // The hip: beside the right thigh's head, outward and a little back; body axes.
    const hip = pos('thigh_r').add(_d.set(-0.11, -0.02, -0.03).applyQuaternion(bodyQ));
    this.hang('hip.R', 'pelvis', hip, bodyQ);
    // The left forearm: halfway along it, +Z out from the arm's outside, +Y along it to the wrist.
    const elbow = pos('lowerarm_l'), wrist = pos('hand_l');
    const along = new Vector3().subVectors(wrist, elbow).normalize();
    const out = new Vector3(1, 0, 0).applyQuaternion(bodyQ);
    const fz = out.clone().sub(along.clone().multiplyScalar(out.dot(along))).normalize();
    const fx = new Vector3().crossVectors(along, fz);
    this.hang('forearm.L', 'lowerarm_l', elbow.clone().lerp(wrist, 0.5).add(fz.clone().multiplyScalar(0.04)), new Quaternion().setFromRotationMatrix(_m.makeBasis(fx, along, fz)));
  }

  /** Put socket `name` under bone `bone` at world point `at` with world rotation `q` (the bone as it is now). */
  private hang(name: SocketName, bone: string, at: Vector3, q: Quaternion): void {
    const b = this.bone(bone), s = this.socket(name);
    b.add(s);
    b.updateMatrixWorld(true);
    _m.copy(b.matrixWorld).invert();
    s.position.copy(at).applyMatrix4(_m);
    s.quaternion.copy(b.getWorldQuaternion(_q).invert().multiply(q));
    s.updateMatrixWorld(true);
  }

  /**
   * Put the bones turned since the last call back as they were bound, before the clips play the
   * next frame: a bone no clip moves (a finger) would otherwise keep last frame's turn and add to it.
   */
  relax(): void {
    for (const b of this.turned) { const q = this.bind.get(b); if (q) b.quaternion.copy(q); }
    this.turned.clear();
  }

  // ------------------------------------------------------------------ pose layer

  /** The pose `fn` sets, laid over what the clips did by weight `w` (0..1). */
  pose(fn: (p: Pose) => void, w: number): void {
    if (w <= 0) return;
    this.body.updateMatrixWorld(true);
    const touched: Bone[] = [];
    const keep = (b: Bone) => { if (!this.saved.has(b)) this.saved.set(b, new Quaternion()); this.saved.get(b)!.copy(b.quaternion); touched.push(b); };
    // Bend a run of bones forward by shares of `x`; put a limb's end where the pose angles say.
    const bend = (x: number, run: readonly (readonly [string, number])[]) => { for (const [n, k] of run) { const b = this.bone(n); keep(b); this.turnWorld(b, this.axis(1, 0, 0), -x * k); } };
    const limb = (c: Chain, side: Side, a: number, b: number, mid: number, sense: 1 | -1) => {
      keep(c.a); keep(c.b);
      const { target, pole } = this.limbTarget(c, side, a, b, mid, sense);
      this.reach(c, target, pole);
    };
    const p: Pose = {
      spine: (x) => bend(x, [['spine_01', 0.3], ['spine_02', 0.35], ['spine_03', 0.35]]),
      neck: (x) => bend(x, [['neck_01', 0.6], ['head', 0.4]]),
      arm: (side, fwd, out, _twist = 0, elbow = 0) => limb(this.arms[side], side, fwd, out, elbow, 1),
      leg: (side, flex, abd = 0, _twist = 0, knee = 0) => limb(this.legs[side], side, flex, abd, knee, -1),
    };
    fn(p);
    if (w < 1) for (const b of touched) b.quaternion.slerpQuaternions(this.saved.get(b)!, b.quaternion.clone(), w);
    this.body.updateMatrixWorld(true);
  }

  /** Hands and feet to their goals, fingers curled, hands laid flat. */
  reachFor(g: LimbGoals): void {
    this.body.updateMatrixWorld(true);
    for (const [key, side, arm] of [['L', 'L', true], ['R', 'R', true], ['footL', 'L', false], ['footR', 'R', false]] as const) {
      const goal = g[key];
      if (!goal || goal.w <= 0) continue;
      const c = arm ? this.arms[side] : this.legs[side];
      const qa = c.a.quaternion.clone(), qb = c.b.quaternion.clone(), qc = c.c.quaternion.clone();
      const pole = this.poleFrom(c, side, goal.pole ?? (arm ? [0.7, -1, -0.3] : [0.2, 0.2, 1]));
      this.reach(c, goal.p, pole);
      if (arm && goal.flat) this.layFlat(side, goal.flat);
      if (goal.w < 1) {
        c.a.quaternion.slerpQuaternions(qa, c.a.quaternion.clone(), goal.w);
        c.b.quaternion.slerpQuaternions(qb, c.b.quaternion.clone(), goal.w);
        c.c.quaternion.slerpQuaternions(qc, c.c.quaternion.clone(), goal.w);
      }
      c.a.updateMatrixWorld(true);
    }
    const cw = g.curlW ?? 0;
    if (cw > 0) for (const side of ['L', 'R'] as const) { const k = g.curl?.[side]; if (k !== undefined) this.curl(side, k, cw); }
  }

  /** Curl a hand's fingers by `amount` radians a joint (≈1.2 a fist), by weight `w`. */
  curl(side: Side, amount: number, w = 1): void {
    const s = side.toLowerCase();
    this.bone(`hand_${s}`).updateMatrixWorld(true);
    const across = _a.subVectors(this.bone(`index_01_${s}`).getWorldPosition(_b), this.bone(`pinky_01_${s}`).getWorldPosition(_c)).normalize();
    // Curling turns the fingers about the knuckle line, towards the palm.
    const sign = side === 'R' ? 1 : -1;
    for (const f of FINGERS) for (let j = 1; j <= 3; j++) {
      const b = this.bone(`${f}_0${j}_${s}`);
      const q0 = b.quaternion.clone();
      this.turnWorld(b, across.clone(), sign * amount * (j === 1 ? 0.8 : 1));
      if (w < 1) b.quaternion.slerpQuaternions(q0, b.quaternion.clone(), w);
      b.updateMatrixWorld(true);
    }
  }

  // ------------------------------------------------------------------ helpers

  /** A body-frame direction in world space. */
  private axis(x: number, y: number, z: number): Vector3 {
    return new Vector3(x, y, z).applyQuaternion(this.body.getWorldQuaternion(_q3)).normalize();
  }

  /** Turn bone `b` by `angle` about world axis `axis` (its children follow). */
  private turnWorld(b: Bone, axis: Vector3, angle: number): void {
    const parent = b.parent!;
    parent.updateMatrixWorld(true);
    const pq = parent.getWorldQuaternion(_q);
    _q2.setFromAxisAngle(axis, angle);
    // local' = parent⁻¹ · R · parent · local
    b.quaternion.premultiply(pq).premultiply(_q2).premultiply(pq.invert());
    b.updateMatrixWorld(true);
    this.turned.add(b);
  }

  /** Where a limb's end goes for pose angles (arm: `sense` 1, the forearm bending forward; leg: −1, the shin bending back), and its elbow or knee. */
  private limbTarget(c: Chain, side: Side, lift: number, out: number, bend: number, sense: number): { target: Vector3; pole: Vector3 } {
    const root = c.a.getWorldPosition(new Vector3());
    const l1 = root.distanceTo(c.b.getWorldPosition(_b)), l2 = _b.distanceTo(c.c.getWorldPosition(_c));
    const outward = side === 'R' ? -1 : 1;
    // Hanging down, raised forward by `lift`, then out sideways by `out`.
    const u = new Vector3(0, -Math.cos(lift), Math.sin(lift));
    u.applyAxisAngle(new Vector3(0, 0, 1), -outward * out);
    const hinge = new Vector3(1, 0, 0).applyAxisAngle(new Vector3(0, 0, 1), -outward * out);
    const f = u.clone().applyAxisAngle(hinge, -sense * bend);
    const toWorld = this.body.getWorldQuaternion(new Quaternion());
    u.applyQuaternion(toWorld); f.applyQuaternion(toWorld);
    const elbow = root.clone().addScaledVector(u, l1);
    return { target: elbow.clone().addScaledVector(f, l2), pole: elbow };
  }

  /** A pole point for a limb from a body-frame direction (out for this side, up, forward). */
  private poleFrom(c: Chain, side: Side, dir: readonly [number, number, number]): Vector3 {
    const outward = side === 'R' ? -1 : 1;
    const d = this.axis(dir[0] * outward, dir[1], dir[2]);
    const at = c.b.getWorldPosition(new Vector3());
    return at.addScaledVector(d, 0.5);
  }

  /** Two-bone IK: turn `a` and `b` so `c` reaches `target`, the middle joint towards `pole`. */
  private reach(c: Chain, target: Vector3, pole: Vector3): void {
    c.a.updateMatrixWorld(true);
    const a = c.a.getWorldPosition(_a), b = c.b.getWorldPosition(_b), e = c.c.getWorldPosition(_c);
    const l1 = a.distanceTo(b), l2 = b.distanceTo(e);
    const to = _t.subVectors(target, a);
    const dist = Math.min(l1 + l2 - 1e-4, Math.max(Math.abs(l1 - l2) + 1e-4, to.length()));
    const dir = to.normalize();
    const cosA = (l1 * l1 + dist * dist - l2 * l2) / (2 * l1 * dist);
    const sinA = Math.sqrt(Math.max(0, 1 - cosA * cosA));
    const side = _p.subVectors(pole, a);
    side.addScaledVector(dir, -side.dot(dir));
    if (side.lengthSq() < 1e-8) side.subVectors(b, a).addScaledVector(dir, -_d.subVectors(b, a).dot(dir));
    side.normalize();
    const mid = _d.copy(a).addScaledVector(dir, l1 * cosA).addScaledVector(side, l1 * sinA);
    const reachTo = _e.copy(a).addScaledVector(dir, dist);
    // Upper bone: from where its child is to where the middle joint must be.
    this.aim(c.a, b.clone().sub(a).normalize(), mid.clone().sub(a).normalize());
    // Lower bone: from where the end is now to the target.
    const b2 = c.b.getWorldPosition(new Vector3()), e2 = c.c.getWorldPosition(new Vector3());
    this.aim(c.b, e2.sub(b2).normalize(), reachTo.sub(b2).normalize());
  }

  /** Turn bone `b` (in the world) so world direction `from` becomes `to`. */
  private aim(b: Bone, from: Vector3, to: Vector3): void {
    const r = new Quaternion().setFromUnitVectors(from, to);
    const pq = b.parent!.getWorldQuaternion(new Quaternion());
    b.quaternion.premultiply(pq).premultiply(r).premultiply(pq.invert());
    b.updateMatrixWorld(true);
    this.turned.add(b);
  }

  /** Lay a hand flat, palm down, its fingers along `flat` (world, horizontal). */
  private layFlat(side: Side, flat: Vector3): void {
    const s = side.toLowerCase(), hand = this.bone(`hand_${s}`);
    hand.updateMatrixWorld(true);
    const h = hand.getWorldPosition(new Vector3());
    const fingers = this.bone(`middle_01_${s}`).getWorldPosition(new Vector3()).sub(h).normalize();
    const across = this.bone(`index_01_${s}`).getWorldPosition(new Vector3()).sub(this.bone(`pinky_01_${s}`).getWorldPosition(new Vector3())).normalize();
    const palm = new Vector3().crossVectors(fingers, across).multiplyScalar(side === 'R' ? 1 : -1).normalize();
    const want = new Vector3(flat.x, 0, flat.z).normalize();
    const down = new Vector3(0, -1, 0);
    _m.makeBasis(fingers, palm, new Vector3().crossVectors(fingers, palm));
    _m2.makeBasis(want, down, new Vector3().crossVectors(want, down));
    const r = new Quaternion().setFromRotationMatrix(_m2).multiply(new Quaternion().setFromRotationMatrix(_m).invert());
    const pq = hand.parent!.getWorldQuaternion(new Quaternion());
    hand.quaternion.premultiply(pq).premultiply(r).premultiply(pq.invert());
    hand.updateMatrixWorld(true);
    this.turned.add(hand);
  }
}

/** Piecewise curve through [t, value] keys with smoothstep easing between keys. */
export function kf(t: number, keys: readonly (readonly [number, number])[]): number {
  if (t <= keys[0][0]) return keys[0][1];
  for (let i = 1; i < keys.length; i++) {
    if (t <= keys[i][0]) {
      const [t0, v0] = keys[i - 1], [t1, v1] = keys[i];
      const u = (t - t0) / Math.max(1e-6, t1 - t0);
      return v0 + (v1 - v0) * u * u * (3 - 2 * u);
    }
  }
  return keys[keys.length - 1][1];
}
