/**
 * Climbing a ladder, played out (after Scale's manhole climb): walk to the ladder, get on it (over
 * the rim of a shaft, or at its foot), climb with hands and feet on the rungs, get off. The body is
 * a puppet meanwhile: each frame (`advance`) the climb says where its feet are and which way it faces
 * (`pos`, `yaw`, `walking`, `vel`), the pose to lay over its clips (`pose`) and where its hands and
 * feet go (`limbs`); the game draws it so (FigureRig.pose, FigureRig.reachFor).
 *
 * The game strings steps together (`play`), including a change of place in the middle of a climb (a
 * `fade` out, a `call` that swaps the scene, a fade in on another ladder). Heights are world heights.
 */
import { Vector3 } from 'three/webgpu';
import { clamp, lerpAngle, smoothstep as smooth } from '@futuremagic/core';
import { kf, type LimbGoal, type LimbGoals, type Pose } from './rig';

/** A ladder: its rungs, the wall behind them and the floor one gets on or off at. */
export interface Ladder {
  /** The rungs' middle line (x, z). */
  x: number;
  z: number;
  /** Unit vector from the climbing side into the wall. */
  nx: number;
  nz: number;
  /** Rung heights: the lowest and the highest (a multiple of `rung` apart). */
  lo: number;
  hi: number;
  /** The floor where one gets on or off: at the rim over the top (a way down) or at the foot (a way up). */
  floor: number;
  /** Half the width between the stiles. */
  halfWidth: number;
  /** Got on and off over a rim at the top (true), or at the foot (false). */
  rim: boolean;
  /** Rung spacing (m, default RUNG). */
  rung?: number;
}

/** The usual rung spacing (m). */
export const RUNG = 0.3;

/** A rim with no ladder under it (a ledge to pull up over): where, which way into it, its top. */
export interface Ledge { x: number; z: number; nx: number; nz: number; floor: number }

/** The body that climbs: its standing height and its hips' height over the feet (m). */
export interface Climber { height: number; hipHeight: number }

/** Climbing speed, metres per second (for a 1.8 m climber). */
const CLIMB_V = 1.15;
/** Seconds to pull up over a ledge (quicker than off a ladder: nothing to let go of). */
const LEDGE_DUR = 1.5;

/** One part of a climb. Heights are the feet's, world y. */
export type ClimbStep =
  /** `around`: the hole of a way down (x, z, radius), walked round rather than over. */
  | { kind: 'walk'; ladder: Ladder; around?: Hole; face?: number }
  /** Stand still for `dur` s (lifting a lid, looking down): `each` is told how far through (0..1) every frame. */
  | { kind: 'hold'; dur: number; each?: (u: number) => void }
  /** Turn on the spot to face `to` (yaw). */
  | { kind: 'turn'; to: number; dur?: number }
  | { kind: 'rim'; ladder: Ladder; dir: 'on' | 'off' }
  | { kind: 'foot'; ladder: Ladder; dir: 'on' | 'off' }
  | { kind: 'climb'; ladder: Ladder; from: number; to: number; fade?: 'in' | 'out' }
  /** Over the top of a climb on the rock (`Body.ledge`): the pull-up of a rim, with the feet at `feet` to start. */
  | { kind: 'ledge'; ledge: Ledge; feet: number }
  | { kind: 'call'; then: () => void }
  /** Hold still in the dark until `ready` (the next level streamed in). */
  | { kind: 'wait'; ready: () => boolean };

interface Segment {
  dur: number;
  fade?: 'in' | 'out' | 'dark';
  /** Not done before this says so. */
  until?: () => boolean;
  /** u: 0..1 through the segment. */
  pose: (u: number) => void;
}

const _v = new Vector3(), _w = new Vector3();

/** A shaft's opening, as a walk to its ladder must go round it: centre (x, z) and radius. */
export type Hole = readonly [number, number, number];

/** How far from a hole's rim a walk round it keeps, metres. */
const RIM_KEEP = 0.45;

/**
 * The way on foot from (x0, z0) to (x1, z1), round `around` (a hole) rather than over it: the angle
 * round its centre and the distance from it eased from start to end, never nearer than RIM_KEEP to
 * the rim. Returns its length, and puts the point a fraction f along it in `out` (x, z).
 */
export function rimWalk(x0: number, z0: number, x1: number, z1: number, around: Hole | undefined, f: number, out: [number, number]): number {
  if (!around) {
    out[0] = x0 + (x1 - x0) * f; out[1] = z0 + (z1 - z0) * f;
    return Math.hypot(x1 - x0, z1 - z0);
  }
  const [cx, cz, r] = around, keep = r + RIM_KEEP;
  const a0 = Math.atan2(z0 - cz, x0 - cx), d0 = Math.max(keep, Math.hypot(x0 - cx, z0 - cz));
  let da = Math.atan2(z1 - cz, x1 - cx) - a0;
  da -= Math.round(da / (2 * Math.PI)) * 2 * Math.PI; // the short way round
  const d1 = Math.max(keep, Math.hypot(x1 - cx, z1 - cz));
  const a = a0 + da * f, d = d0 + (d1 - d0) * f;
  out[0] = cx + Math.cos(a) * d; out[1] = cz + Math.sin(a) * d;
  return Math.abs(da) * (d0 + d1) / 2 + Math.abs(d1 - d0);
}

export class LadderClimb {
  /** Feet position and facing of the puppet this frame. */
  readonly pos = new Vector3();
  yaw = 0;
  /** Black overlay 0..1 (fading out of one place and into the next). */
  fade = 0;
  /** Walking (to the ladder) this frame, at `vel` (m/s, world); else standing or climbing. */
  walking = false;
  readonly vel: [number, number, number] = [0, 0, 0];
  /** The pose to lay over the clips this frame and its weight (FigureRig.pose); null: none. */
  pose: { readonly fn: (p: Pose) => void; readonly w: number } | null = null;
  /** Where hands and feet go this frame (FigureRig.reachFor); null: nowhere in particular. */
  limbs: LimbGoals | null = null;
  private segs: Segment[] = [];
  private seg = 0;
  private segT = 0;
  private poseFn: ((p: Pose) => void) | null = null;
  private overW = 0;
  private readonly goals: LimbGoals = {
    L: { p: new Vector3(), w: 0, pole: [0.7, -1, -0.3] }, R: { p: new Vector3(), w: 0, pole: [0.7, -1, -0.3] },
    footL: { p: new Vector3(), w: 0, pole: [0.2, 0.2, 1] }, footR: { p: new Vector3(), w: 0, pole: [0.2, 0.2, 1] },
    curl: { L: 1.2, R: 1.2 }, curlW: 0,
  };
  /** The climber's scale (1 at 1.8 m) and rest hip height. */
  private k = 1;
  private hipW = 0.93;

  get active(): boolean { return this.seg < this.segs.length; }

  /** Start a climb from where the climber stands (feet at x, y, z, facing yaw). */
  play(steps: ClimbStep[], x: number, y: number, z: number, yaw: number, body: Climber): void {
    this.pos.set(x, y, z);
    this.yaw = yaw;
    this.k = body.height / 1.8;
    this.hipW = body.hipHeight || 0.52 * body.height;
    this.segs = [];
    // Segments are planned as they come (a walk starts from wherever the last one ended).
    for (const s of steps) this.segs.push(this.plan(s));
    this.seg = 0;
    this.segT = 0;
    this.fade = 0;
  }

  /** Every frame while active, instead of the body's own movement. */
  advance(dt: number): void {
    const g = this.goals;
    for (const key of ['L', 'R', 'footL', 'footR'] as const) { g[key]!.w = 0; g[key]!.flat = null; }
    g.curlW = 0;
    this.poseFn = null;
    this.overW = 0;
    this.walking = false;
    let left = dt;
    while (this.seg < this.segs.length) {
      const sg = this.segs[this.seg];
      if (sg.until && !sg.until()) {
        this.segs[this.seg + 1]?.pose(0); // posed where the climb goes on
        this.fade = 1;
        break;
      }
      const step = Math.min(left, sg.dur - this.segT);
      this.segT += step;
      left -= step;
      const u = clamp(this.segT / sg.dur, 0, 1);
      sg.pose(u);
      this.fade = sg.fade === 'out' ? smooth(0.45, 1, u) : sg.fade === 'in' ? 1 - smooth(0, 0.45, u) : sg.fade === 'dark' ? 1 : 0;
      if (this.segT < sg.dur - 1e-6) break;
      this.seg++;
      this.segT = 0;
      if (left <= 1e-6) break;
    }
    const fn = this.poseFn as ((p: Pose) => void) | null;
    this.pose = fn && this.active ? { fn, w: this.overW } : null;
    this.limbs = this.active ? g : null;
    if (!this.walking) this.vel[0] = this.vel[1] = this.vel[2] = 0;
  }

  /** Let go at once (the climb is over or abandoned). */
  stop(): void {
    this.segs = [];
    this.seg = 0;
    this.fade = 0;
    this.pose = null;
    this.limbs = null;
  }

  // ------------------------------------------------------------------ steps

  private plan(s: ClimbStep): Segment {
    switch (s.kind) {
      case 'walk': return this.walkTo(s.ladder, s.around, s.face);
      case 'hold': return { dur: Math.max(1e-3, s.dur), pose: (u) => s.each?.(u) };
      case 'turn': {
        let from: number | null = null;
        return { dur: s.dur ?? 0.7, pose: (u) => { from ??= this.yaw; this.yaw = lerpAngle(from, s.to, smooth(0, 1, u)); } };
      }
      case 'rim': return { dur: 1.9, pose: (u) => this.rim(s.ladder, s.dir === 'off' ? u : 1 - u) };
      case 'ledge': {
        // A rim with no ladder under it: the feet start one step over the "lowest rung", where the pull-up starts.
        const l = s.ledge, edge: Ladder = { x: l.x, z: l.z, nx: l.nx, nz: l.nz, lo: s.feet - 2 * RUNG, hi: s.feet, floor: l.floor, halfWidth: 0.25, rim: true };
        return { dur: LEDGE_DUR, pose: (u) => this.rim(edge, u) };
      }
      case 'foot': return {
        dur: 0.45, pose: (u) => {
          const w = s.dir === 'on' ? smooth(0, 1, u) : 1 - smooth(0, 1, u);
          this.climbAt(s.ladder, 0, s.dir === 'on');
          // (On the ladder the knees stay bent: the body straightens onto the floor.)
          this.pos.y += (s.ladder.floor - this.pos.y) * (1 - w);
          this.overW = w;
          this.fadeGoals(w);
        },
      };
      case 'climb': {
        const base = this.base(s.ladder);
        const h0 = s.from - base, h1 = s.to - base;
        return { dur: Math.max(0.3, Math.abs(h1 - h0) / (CLIMB_V * Math.sqrt(this.k))), fade: s.fade, pose: (u) => this.climbAt(s.ladder, h0 + (h1 - h0) * u, h1 > h0) };
      }
      case 'wait': {
        return { dur: 1e-3, fade: 'dark', until: s.ready, pose: () => undefined };
      }
      case 'call': {
        let done = false;
        return { dur: 1e-3, pose: () => { if (!done) { done = true; s.then(); } } };
      }
    }
  }

  /** Walk to where one gets on the ladder (round the hole of a way down, never over it), then turn to face the wall (or `faceTo`). */
  private walkTo(l: Ladder, around?: Hole, faceTo?: number): Segment {
    const d0 = this.rimLadder(l) ? 0.62 : -0.75;
    let from: Vector3 | null = null, fromYaw = 0, walkT = 0, heading = 0, speed = 0;
    const to = new Vector3(), v = 1.3 * Math.sqrt(this.k), p: [number, number] = [0, 0], q: [number, number] = [0, 0];
    const face = faceTo ?? faceYaw(l);
    const seg: Segment = {
      dur: 1.6, // (at least: long enough for the few steps beside the ladder; a walk round a shaft takes longer)
      pose: (u) => {
        if (!from) {
          from = this.pos.clone();
          fromYaw = this.yaw;
          this.at(l, d0, 0, l.floor, to);
          const len = rimWalk(from.x, from.z, to.x, to.z, around, 0, p);
          // Never more than a few seconds of being walked about: a long way round goes briskly.
          speed = Math.max(v, len / 3.2);
          walkT = len / speed;
          seg.dur = Math.max(1.6, walkT + 0.5);
          rimWalk(from.x, from.z, to.x, to.z, around, Math.min(1, 0.05 / Math.max(len, 0.05)), q);
          heading = Math.atan2(-(q[0] - from.x), -(q[1] - from.z));
        }
        const t = u * seg.dur, f = walkT > 0 ? clamp(t / walkT, 0, 1) : 1;
        rimWalk(from.x, from.z, to.x, to.z, around, f, p);
        this.pos.set(p[0], from.y + (to.y - from.y) * f, p[1]);
        if (f < 1) {
          this.walking = true;
          // Heading along the way (round a hole it turns as it goes).
          rimWalk(from.x, from.z, to.x, to.z, around, Math.min(1, f + 0.02), q);
          const dx = q[0] - p[0], dz = q[1] - p[1], n = Math.hypot(dx, dz);
          if (n > 1e-4) heading = Math.atan2(-dx, -dz);
          this.vel[0] = n > 1e-4 ? (dx / n) * speed : 0; this.vel[2] = n > 1e-4 ? (dz / n) * speed : 0;
          this.yaw = t < 0.25 ? lerpAngle(fromYaw, heading, smooth(0, 0.25, t)) : heading;
        } else this.yaw = lerpAngle(walkT > 0.05 ? heading : fromYaw, face, smooth(walkT, seg.dur, t));
      },
    };
    return seg;
  }

  /**
   * On the ladder with the feet at h over its base: hands and feet leapfrog in pairs (left hand
   * with right foot, then the right hand with the left foot), each moving two rungs while the
   * body rises one; the body is pushed up by the lower foot.
   */
  private climbAt(l: Ladder, h: number, up: boolean): void {
    const k = this.k, g = this.goals, base = this.base(l), rung = l.rung ?? RUNG, STEP = 2 * rung;
    const handOff = Math.round((1.2 * k) / rung) * rung;
    let minFoot = Infinity;
    const limbs: [keyof LimbGoals, number, number, boolean][] = [
      ['footR', 0, 1, false], ['footL', 0.5, -1, false], ['L', 0, -1, true], ['R', 0.5, 1, true],
    ];
    for (const [key, o, side, hand] of limbs) {
      const x = h / STEP - o, n = Math.floor(x), fr = x - n;
      const a = smooth(0, 0.5, fr), swing = fr < 0.5 ? Math.sin(Math.PI * a) : 0;
      const y0 = Math.max(0, n * STEP), y1 = Math.max(0, (n + 1) * STEP);
      const y = y0 + (y1 - y0) * a;
      const goal = g[key] as LimbGoal;
      if (hand) {
        // Holds above the top rung are the top rung (the rungs of a way down stand above the rim).
        const top = l.hi - base;
        this.at(l, -0.03, side * (l.halfWidth - 0.06), base + Math.min(top, y0 + handOff), _v);
        this.at(l, -0.03, side * (l.halfWidth - 0.06), base + Math.min(top, y1 + handOff), _w);
        goal.p.lerpVectors(_v, _w, a);
        g.curl![key as 'L' | 'R'] = 1.25;
      } else {
        this.at(l, -0.11 * k, side * 0.11, base + y + 0.075 * k, goal.p);
        minFoot = Math.min(minFoot, y);
      }
      // The moving limb comes off the ladder a little.
      this.toward(l, goal.p, -(hand ? 0.1 : 0.14) * swing, (hand ? 0.04 : 0.06) * swing);
      goal.w = 1;
    }
    g.curlW = 1;
    this.placeHips(l, -0.36 * k, base + minFoot + 0.8 * k);
    this.yaw = faceYaw(l);
    const look = up ? 0.3 : -0.35;
    this.poseFn = (p) => {
      p.spine(-0.12);
      p.neck(look);
      for (const s of ['L', 'R'] as const) {
        p.arm(s, 2.2, 0.3, 0, 1.0, 0.5);
        p.leg(s, 1.0, 0.12, 0, 1.4, -0.3);
      }
    };
    this.overW = 1;
  }

  /**
   * Between the top of a way down (u = 0: feet on the rung where one leaves the ladder) and standing
   * on the floor beyond the rim (u = 1): hands flat on the floor past the edge, the body pushed up,
   * the right foot onto the edge, then the left, standing up. Getting on plays it backwards.
   */
  private rim(l: Ladder, u: number): void {
    const k = this.k, g = this.goals, base = this.base(l), G = l.floor - base, hT = this.hTop(l);
    const hand = 0.36, stand = 0.62, lb = -0.36 * k;
    const lat = kf(u, [[0, lb], [0.3, lb + 0.06], [0.55, hand - 0.25], [0.75, hand - 0.05], [0.9, stand - 0.1], [1, stand]]);
    const hip = kf(u, [[0, hT + 0.8 * k], [0.3, hT + 0.86 * k], [0.55, G + 0.12 * k], [0.75, G + 0.3 * k], [0.9, G + this.hipW * 0.9], [1, G + this.hipW]]);
    this.placeHips(l, lat, base + hip);
    this.yaw = faceYaw(l);
    // Hands flat on the floor past the edge until the body is up.
    const hw = 1 - smooth(0.74, 0.86, u);
    for (const [key, sd] of [['L', -1], ['R', 1]] as const) {
      this.at(l, hand, sd * 0.2, l.floor + 0.03, g[key]!.p);
      g[key]!.w = hw;
      g[key]!.flat = (g[key]!.flat ?? new Vector3()).set(l.nx, 0, l.nz);
      g.curl![key] = 0.15;
    }
    g.curlW = hw;
    // Feet: on the top rung, the right one onto the edge, then the left.
    const rUp = smooth(0.3, 0.5, u), lUp = smooth(0.7, 0.88, u);
    this.at(l, -0.11 * k, 0.11, base + hT + 0.075 * k, _v); this.at(l, 0.28, 0.13, l.floor + 0.08 * k, _w);
    g.footR!.p.lerpVectors(_v, _w, rUp);
    this.toward(l, g.footR!.p, -0.15 * Math.sin(Math.PI * rUp), 0.12 * Math.sin(Math.PI * rUp));
    this.at(l, -0.11 * k, -0.11, base + hT + 0.075 * k, _v); this.at(l, stand - 0.05, -0.13, l.floor + 0.08 * k, _w);
    g.footL!.p.lerpVectors(_v, _w, lUp);
    this.toward(l, g.footL!.p, -0.12 * Math.sin(Math.PI * lUp), 0.15 * Math.sin(Math.PI * lUp));
    const up = 1 - smooth(0.88, 1, u);
    g.footR!.w = up;
    g.footL!.w = up * (lUp > 0 ? 1 : 1 - smooth(0.4, 0.55, u) * 0.6);
    this.poseFn = (p) => {
      p.spine(kf(u, [[0, -0.12], [0.3, -0.5], [0.55, -0.8], [0.75, -0.7], [0.9, -0.2], [1, 0]]));
      p.neck(kf(u, [[0, 0.3], [0.55, 0.35], [1, 0]]));
      const af = kf(u, [[0, 2.2], [0.3, 1.0], [0.55, 0.6], [0.85, 0.2], [1, 0]]), ae = kf(u, [[0, 1.0], [0.3, 0.25], [0.55, 0.15], [1, 0]]);
      for (const s of ['L', 'R'] as const) p.arm(s, af, 0.25 * (1 - u), 0, ae, 0.4 * (1 - u));
      p.leg('R', kf(u, [[0, 1.0], [0.3, 0.4], [0.45, 1.9], [0.75, 1.7], [0.92, 0.3], [1, 0]]), 0.1, 0, kf(u, [[0, 1.4], [0.3, 0.3], [0.45, 2.2], [0.75, 1.8], [0.92, 0.3], [1, 0]]));
      p.leg('L', kf(u, [[0, 1.0], [0.3, 0.4], [0.7, 0.2], [0.8, 1.5], [0.92, 0.3], [1, 0]]), 0.1, 0, kf(u, [[0, 1.4], [0.3, 0.3], [0.7, 0.4], [0.8, 1.7], [0.92, 0.3], [1, 0]]));
    };
    this.overW = 1;
  }

  // ------------------------------------------------------------------ helpers

  /** Whether one gets on and off this ladder over a rim at its top. */
  private rimLadder(l: Ladder): boolean { return l.rim; }

  /** Height h = 0 of a ladder: its top-most usable foothold region is measured from here (a rung, or the floor at the foot). */
  private base(l: Ladder): number {
    return l.rim ? l.lo : l.floor;
  }

  /** The feet's height over the base where one leaves a way down for the rim (both feet on a rung); `body`: for that climber. */
  hTop(l: Ladder, body?: Climber): number {
    const k = body ? body.height / 1.8 : this.k;
    const G = l.floor - this.base(l), STEP = 2 * (l.rung ?? RUNG);
    return Math.max(STEP, Math.floor((G - 0.95 * k) / STEP) * STEP);
  }

  /** The feet's world height where one leaves a way down for the rim (`body`: for that climber, before `play`). */
  rimFeet(l: Ladder, body?: Climber): number { return this.base(l) + this.hTop(l, body); }

  /** A point of the ladder's frame: `a` metres into the wall from the rungs, `s` to the right of a climber facing it, at height y. */
  private at(l: Ladder, a: number, s: number, y: number, out: Vector3): Vector3 {
    // Facing the wall (nx, nz), the right is (-nz, nx).
    return out.set(l.x + l.nx * a - l.nz * s, y, l.z + l.nz * a + l.nx * s);
  }

  /** Move a point towards the wall (+) and up. */
  private toward(l: Ladder, p: Vector3, d: number, up: number): void {
    p.x += l.nx * d;
    p.z += l.nz * d;
    p.y += up;
  }

  /** Place the body by its hip height. */
  private placeHips(l: Ladder, a: number, hipY: number): void {
    this.at(l, a, 0, hipY - this.hipW, this.pos);
  }

  private fadeGoals(w: number): void {
    const g = this.goals;
    for (const key of ['L', 'R', 'footL', 'footR'] as const) g[key]!.w *= w;
    g.curlW = (g.curlW ?? 0) * w;
  }
}

/** The facing (yaw) of a climber facing the ladder's wall. */
export function faceYaw(l: Ladder): number {
  return Math.atan2(-l.nx, -l.nz);
}
