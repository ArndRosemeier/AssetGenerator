/**
 * Climbing a ladder, played out (after Scale's manhole climb): walk to the ladder, get on it (over
 * the rim of a shaft, or at its foot), climb with hands and feet on the rungs, get off. The body is
 * a puppet meanwhile: each frame (`advance`) the climb says where its feet are and which way it faces
 * (`pos`, `yaw`, `walking`, `vel`), the pose to lay over its clips (`pose`) and where its hands and
 * feet go (`limbs`); the game draws it so (FigureRig.pose, FigureRig.reachFor).
 *
 * The game strings steps together (`play`), including a change of place in the middle of a climb (a
 * `fade` out, a `call` that swaps the scene, a fade in on another ladder). Heights are world heights, or the
 * heights of the frame the climb is played in (a ship's: the game carries the pose into the world by her pose).
 *
 * A ship's rig (rigging.ts): shrouds and futtock shrouds are ladders (leaning in, leaning out, held by their sides,
 * giving under a foot), a yard's footrope has steps of its own ('footrope' on and off, 'yard' out along it). At
 * sea the game sets `up` every frame (gravity's up in the climb's frame): the climber slows on a ladder that hangs
 * over them or a yard that slopes, and in a hard roll stops and holds on (`grip`) until it eases. They never fall.
 *
 * The gait follows the CMU motion capture's ladder takes (13_33 to 14_35, Actors' clip library): a foot steps
 * first and the hand on its side follows it a quarter of a stride later, and the body hangs from the holds as
 * gravity pulls it.
 */
import { Vector3 } from 'three/webgpu';
import { clamp, lerpAngle, smoothstep as smooth } from '@futuremagic/core';
import { kf, type LimbGoal, type LimbGoals, type Pose, type Side } from './rig';
import { FOOTROPE_AFT, footropeY, jackstayY, yardPoint, type Yard } from './rigging';

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
  /**
   * How far the rungs lean back into the wall per metre up (0: upright, the default): a rock face that is not
   * quite sheer, its holds (the rungs) on it.
   */
  lean?: number;
  /**
   * How high over the feet the hands take hold, metres for a climber 1.8 m tall (scaled with the climber;
   * default 1.2: a ladder's rungs at the chest). A rock face is climbed with the hands over the head (about 1.9).
   */
  reach?: number;
  /**
   * How far out from the rungs' line the body hangs, metres for a climber 1.8 m tall (default 0.36). Hands
   * over the head (reach) need the body nearer the holds, about 0.2.
   */
  hang?: number;
  /** Where the hands hold: on the rungs (default), or on the sides (shrouds: the hands on the shrouds, the feet on the ratlines). */
  holds?: 'rungs' | 'sides';
  /** How far a rung gives under a foot that bears weight (m; ratlines, default 0). */
  give?: number;
  /**
   * The ladder that goes on above this one (the futtock shrouds over the shrouds; from its `lo` up) and the one
   * below it (under its `lo`): the hands reach up onto the next before the feet, and the body hangs from the one at
   * its height, so a climb goes from one to the other without a jump. Their lines meet where the upper one starts.
   */
  above?: Ladder;
  below?: Ladder;
}

/** The usual rung spacing (m). */
export const RUNG = 0.3;

/** A rim with no ladder under it (a ledge to pull up over): where, which way into it, its top. */
export interface Ledge { x: number; z: number; nx: number; nz: number; floor: number }

/** A climber hanging on a ladder with the feet `h` over its base (as `cling` puts them). */
export interface OnLadder { readonly ladder: Ladder; readonly h: number }

/** The body that climbs: its standing height and its hips' height over the feet (m). */
export interface Climber { height: number; hipHeight: number }

/** Climbing speed, metres per second (for a 1.8 m climber): a climb the game steers (`cling`) goes at this times `pace`. */
export const CLIMB_V = 1.15;
/** Along a footrope: speed (m/s; a way along a yard the game steers, `sidle`, goes at this times `pace`) and how far the feet move each stride (m), for a 1.8 m climber. */
export const SIDLE_V = 0.55;
const SIDLE_STEP = 0.45;
/** Seconds onto (or off) a footrope (at its own pace, whatever the sea). */
export const FOOTROPE_DUR = 2.2;
/** Seconds onto (or off) a ladder at its floor, and more for each metre the climber rises (or drops) getting on from a floor beside it (a deck under a ship's rail). */
const FOOT_DUR = 0.45;
const FOOT_RISE_DUR = 1.1;
/** A ladder hanging over the climber further than this from gravity's up (rad) is too steep to go on: hold on. */
const HANG_MAX = 1.15;
/** A yard sloping along its length more than this (sine of the angle) is too steep to go along: hold on. */
const YARD_SLOPE_MAX = 0.42;
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
  /**
   * Onto a yard's footrope at `at` (metres out along it) from where the climber stands (`from`: a top, the
   * crosstrees, the end of a bowsprit), or off it back there: hands to the jackstay, a foot down onto the rope, the
   * other. Or from a ladder the climber hangs on (`from`: the shrouds, the feet `h` over its base, as `cling`) and
   * back onto it: a hand across to the jackstay, the near foot onto the rope, the other foot, the other hand.
   */
  | { kind: 'footrope'; yard: Yard; dir: 'on' | 'off'; at: number; from: readonly [number, number, number] | OnLadder }
  /** Out (or in) along a yard on its footrope, from `from` to `to` metres out along it, sidling. */
  | { kind: 'yard'; yard: Yard; from: number; to: number }
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
  /**
   * How fast it goes at sea, 0..1, given gravity's up in the climb's frame (0: too steep, hold on). Segments
   * without it (walks, turns, getting on and off) go at their own pace.
   */
  pace?: (up: Vector3) => number;
}

/** A roll (or pitch) this fast makes a climber stop and hold on (rad/s); they go on once it is under 60 % of it. */
export const HOLD_RATE = 0.25;
/** Seconds of calm before a climber who held on goes on. */
const HOLD_EASE = 0.4;

const _v = new Vector3(), _w = new Vector3(), _u = new Vector3(), _from = new Vector3();
/** Where a rim's hands and feet start: the climb's last holds. */
const _held = { L: new Vector3(), R: new Vector3(), footL: new Vector3(), footR: new Vector3() };

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
  /**
   * Gravity's up in the climb's frame, set by the game every frame at sea (a ship's heel and pitch); (0, 1, 0)
   * on land. The body hangs from its holds by it, and the climb slows or holds on by it and by how fast it turns.
   */
  readonly up = new Vector3(0, 1, 0);
  /** How hard the climber holds on now, 0..1 (1: stopped, pressed in, gripping), e.g. for a grunt or a camera shake. */
  grip = 0;
  /** How fast the climb goes this frame, 0..1, at sea (1 on land); a climb the game steers (`cling`, `sidle`) should go at this pace. */
  pace = 1;
  private readonly lastUp = new Vector3(0, 1, 0);
  /** The roll rate (rad/s, smoothed) and how long it has been calm since holding on. */
  private rate = 0;
  private calm = 0;
  private holding = false;
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
  /** The stance the last cling or footrope put the body in (its pose's turns), for a move from one to the other. */
  private stance: Stance | null = null;
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
    this.feel(dt, this.segs[this.seg]?.pace);
    while (this.seg < this.segs.length) {
      const sg = this.segs[this.seg];
      if (sg.until && !sg.until()) {
        this.segs[this.seg + 1]?.pose(0); // posed where the climb goes on
        this.fade = 1;
        break;
      }
      // At sea a climb goes slower, or holds still (still posed: the grip and the body's hang change).
      const k = sg.pace ? this.pace : 1;
      const step = k > 1e-3 ? Math.min(left, (sg.dur - this.segT) / k) : left;
      this.segT += step * k;
      left -= step;
      const u = clamp(this.segT / sg.dur, 0, 1);
      sg.pose(u);
      this.fade = sg.fade === 'out' ? smooth(0.45, 1, u) : sg.fade === 'in' ? 1 - smooth(0, 0.45, u) : sg.fade === 'dark' ? 1 : 0;
      if (this.segT < sg.dur - 1e-6) break;
      this.seg++;
      this.segT = 0;
      if (left <= 1e-6) break;
      this.feel(0, this.segs[this.seg]?.pace);
    }
    const fn = this.poseFn as ((p: Pose) => void) | null;
    this.pose = fn && this.active ? { fn, w: this.overW } : null;
    this.limbs = this.active ? g : null;
    if (!this.walking) this.vel[0] = this.vel[1] = this.vel[2] = 0;
  }

  /**
   * Hang on `l` with the feet `h` over its base, going up (or down): this frame's pose and holds, for a climb
   * the game steers itself (a rock face climbed as the keys say) rather than one played out (`play`). Each
   * frame may pass another ladder (the face under the climber as it moves along).
   */
  cling(l: Ladder, h: number, up: boolean, body: Climber, dt = 0): void {
    this.stop();
    this.k = body.height / 1.8;
    this.hipW = body.hipHeight || 0.52 * body.height;
    const g = this.goals;
    for (const key of ['L', 'R', 'footL', 'footR'] as const) { g[key]!.w = 0; g[key]!.flat = null; }
    this.feel(dt, (u) => this.ladderPace(l, up, u));
    this.climbAt(l, h, up);
    this.pose = this.poseFn ? { fn: this.poseFn, w: this.overW } : null;
    this.limbs = g;
    this.walking = false;
    this.vel[0] = this.vel[1] = this.vel[2] = 0;
  }

  /**
   * On `yard`'s footrope with the body `s` metres out along it: this frame's pose and holds, for a way along a
   * yard the game steers itself. `dt`: the frame's time (for holding on).
   */
  sidle(yard: Yard, s: number, body: Climber, dt = 0): void {
    this.stop();
    this.k = body.height / 1.8;
    this.hipW = body.hipHeight || 0.52 * body.height;
    const g = this.goals;
    for (const key of ['L', 'R', 'footL', 'footR'] as const) { g[key]!.w = 0; g[key]!.flat = null; }
    this.feel(dt, (u) => this.yardPace(yard, u));
    this.yardAt(yard, s);
    this.pose = this.poseFn ? { fn: this.poseFn, w: this.overW } : null;
    this.limbs = g;
    this.walking = false;
    this.vel[0] = this.vel[1] = this.vel[2] = 0;
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
      case 'foot': {
        let from: Vector3 | null = null, fromYaw = 0;
        const on = s.dir === 'on';
        const seg: Segment = {
          dur: FOOT_DUR, pose: (u) => {
            if (!from) {
              from = this.pos.clone();
              fromYaw = this.yaw;
              // Getting on from a floor above or below the ladder's (a deck under the rail the shrouds are got on from) takes longer.
              if (on) seg.dur = FOOT_DUR + FOOT_RISE_DUR * Math.abs(s.ladder.floor - from.y);
              u = 0;
            }
            const w = on ? smooth(0, 1, u) : 1 - smooth(0, 1, u);
            this.climbAt(s.ladder, 0, on);
            // (On the ladder the knees stay bent: the body straightens onto the floor.) Getting on, the body comes
            // from where it stood (on the ladder's floor, or one beside it), in and up to where it hangs, turning to it.
            if (on) {
              this.pos.set(from.x + (this.pos.x - from.x) * w, this.pos.y, from.z + (this.pos.z - from.z) * w);
              this.pos.y += (from.y - this.pos.y) * (1 - w);
              this.yaw = lerpAngle(fromYaw, this.yaw, w);
            } else this.pos.y += (s.ladder.floor - this.pos.y) * (1 - w);
            this.overW = w;
            this.fadeGoals(w);
          },
        };
        return seg;
      }
      case 'climb': {
        const base = this.base(s.ladder);
        const h0 = s.from - base, h1 = s.to - base;
        return {
          dur: Math.max(0.3, Math.abs(h1 - h0) / (CLIMB_V * Math.sqrt(this.k))), fade: s.fade,
          pose: (u) => this.climbAt(s.ladder, h0 + (h1 - h0) * u, h1 > h0), pace: (up) => this.ladderPace(s.ladder, h1 > h0, up),
        };
      }
      case 'yard': return {
        dur: Math.max(0.3, Math.abs(s.to - s.from) / (SIDLE_V * Math.sqrt(this.k))),
        pose: (u) => this.yardAt(s.yard, s.from + (s.to - s.from) * u), pace: (up) => this.yardPace(s.yard, up),
      };
      case 'footrope': {
        const from = s.from;
        return { dur: FOOTROPE_DUR, pose: (u) => (isOnLadder(from) ? this.footropeFromLadder(s.yard, s.at, from, s.dir === 'on' ? u : 1 - u) : this.footrope(s.yard, s.at, from, s.dir === 'on' ? u : 1 - u)) };
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
   * On the ladder with the feet at h over its base: the feet leapfrog (each moving two rungs while the body
   * rises one), the left half a stride after the right, and each hand follows the foot on its side a quarter of a
   * stride later (as in CMU's ladder takes); the body is pushed up by the lower foot and hangs from the holds as
   * gravity pulls it.
   */
  private climbAt(l: Ladder, h: number, up: boolean): void {
    const k = this.k, g = this.goals, base = this.base(l), rung = l.rung ?? RUNG, STEP = 2 * rung;
    const handOff = Math.round(((l.reach ?? 1.2) * k) / rung) * rung, sides = l.holds === 'sides', grip = this.grip;
    let minFoot = Infinity;
    const limbs: [keyof LimbGoals, number, number, boolean][] = [
      ['footR', 0, 1, false], ['footL', 0.5, -1, false], ['R', 0.25, 1, true], ['L', 0.75, -1, true],
    ];
    for (const [key, o, side, hand] of limbs) {
      const x = h / STEP - o, n = Math.floor(x), fr = x - n;
      const a = smooth(0, 0.5, fr), swing = fr < 0.5 ? Math.sin(Math.PI * a) : 0;
      // Nothing under the base, unless the ladder below goes on there.
      const floor = l.below ? -Infinity : 0;
      const y0 = Math.max(floor, n * STEP), y1 = Math.max(floor, (n + 1) * STEP);
      const y = y0 + (y1 - y0) * a;
      const goal = g[key] as LimbGoal;
      if (hand) {
        // On the sides (shrouds) the hands are on the outer shrouds; on rungs a little in from the stiles.
        const s = side * (sides ? l.halfWidth : l.halfWidth - 0.06);
        this.hold(l, s, base + y0 + handOff, _v);
        this.hold(l, s, base + y1 + handOff, _w);
        goal.p.lerpVectors(_v, _w, a);
        g.curl![key as 'L' | 'R'] = 1.25 + 0.3 * grip;
      } else {
        this.at(l, -0.11 * k, side * 0.11, base + y + 0.075 * k, goal.p);
        // A ratline gives under a foot that bears weight (not under one stepping).
        goal.p.y -= (l.give ?? 0) * (1 - swing);
        minFoot = Math.min(minFoot, y);
      }
      // The moving limb comes off the ladder a little (holding on: barely).
      this.toward(l, goal.p, -(hand ? 0.1 : 0.14) * swing * (1 - grip), (hand ? 0.04 : 0.06) * swing);
      goal.w = 1;
    }
    g.curlW = 1;
    // Held on hard, the body is pulled in to the holds.
    const hang = (l.hang ?? 0.36) * k * (1 - 0.35 * grip);
    // Pushed up by the lower foot, but carried on by the arms meanwhile: half the push's surge, half a steady
    // rise (the motion capture's hips rise in waves, not steps).
    this.placeHips(l, -hang, base + 0.5 * (minFoot + h - 0.25 * STEP) + 0.8 * k);
    this.sway(0.5 * hang + 0.1 * k);
    this.yaw = faceYaw(l);
    // Leaning out over the climber (futtock shrouds), the back arches and the head goes back to see the holds.
    const over = Math.max(0, -(l.lean ?? 0));
    const look = up ? 0.3 + 0.4 * over : -0.35, spine = -0.12 + 0.25 * over - 0.15 * grip;
    this.stance = { spine, neck: look, arm: CLING_ARM, leg: CLING_LEG };
    this.poseFn = stancePose(this.stance);
    this.overW = 1;
  }

  /** A hold for a hand at height y, `s` to the right: on the ladder at that height (or the top rung of the topmost), within its width. */
  private hold(l: Ladder, s: number, y: number, out: Vector3): void {
    let top = l;
    while (top.above) top = top.above;
    const h = Math.min(top.hi, y), a = ladderAt(l, h);
    this.at(l, -0.03, Math.sign(s) * Math.min(Math.abs(s), a.holds === 'sides' ? a.halfWidth : a.halfWidth - 0.06), h, out);
  }

  /**
   * The body (`pos`) moved the way gravity pulls it away from its holds: at sea, as she heels and pitches, a
   * climber hangs from the hands. `len`: how far the body hangs (m) below what holds it.
   */
  private sway(len: number): void {
    const u = this.up, n = Math.hypot(u.x, u.y, u.z) || 1;
    const MAX = 0.18 * this.k;
    this.pos.x -= clamp((u.x / n) * len, -MAX, MAX);
    this.pos.z -= clamp((u.z / n) * len, -MAX, MAX);
  }

  /**
   * How fast a climb on `l` goes with gravity's up `up`: full speed while the ladder leans away from the climber
   * (a stair) or stands upright, slower as it hangs over them, and still (hold on) past HANG_MAX; a little
   * slower too the more she heels.
   */
  private ladderPace(l: Ladder, goingUp: boolean, up: Vector3): number {
    const lean = l.lean ?? 0, al = Math.hypot(lean, 1);
    // Up the ladder, and the climber's side of it (towards them, level in the frame).
    _v.set((l.nx * lean) / al, 1 / al, (l.nz * lean) / al);
    _w.set(-l.nx, 0, -l.nz);
    const un = _u.copy(up).normalize();
    _w.addScaledVector(un, -_w.dot(un)).normalize();
    // How far the ladder hangs over the climber from gravity's up (radians; negative: it leans away).
    const over = Math.atan2(_v.dot(_w), _v.dot(un));
    if (over > HANG_MAX) return 0;
    const steep = over > 0 ? 1 - 0.65 * (over / HANG_MAX) : 1;
    return clamp(steep * (1 - 2 * (1 - un.y)) * (goingUp ? 1 : 1.1), 0.15, 1);
  }

  /** How fast a man goes along `yard` with gravity's up `up`: slower as it slopes along its length, still past YARD_SLOPE_MAX. */
  private yardPace(yard: Yard, up: Vector3): number {
    const rise = yard.rise ?? 0, un = _u.copy(up).normalize(), slope = Math.abs(yard.ax * un.x + rise * un.y + yard.az * un.z) / Math.hypot(1, rise);
    if (slope > YARD_SLOPE_MAX) return 0;
    return clamp(1 - 1.6 * slope, 0.2, 1);
  }

  /**
   * How the sea is felt this frame: the roll rate from how `up` turned since the last frame, whether to hold on
   * (a hard roll, or `pace` says too steep) and how fast to go (`this.pace`).
   */
  private feel(dt: number, pace?: (up: Vector3) => number): void {
    if (dt > 0) {
      const turn = this.lastUp.angleTo(this.up) / dt;
      this.rate += (turn - this.rate) * Math.min(1, dt * 6);
      this.lastUp.copy(this.up);
    }
    const p = pace ? pace(this.up) : 1;
    const hard = this.rate > HOLD_RATE || p <= 0;
    if (hard) { this.holding = !!pace; this.calm = 0; }
    else if (this.holding && this.rate < 0.6 * HOLD_RATE) {
      this.calm += dt;
      if (this.calm >= HOLD_EASE) this.holding = false;
    }
    if (!pace) this.holding = false;
    this.grip = clamp(this.grip + (this.holding ? 1 : -1) * dt * 4, 0, 1);
    this.pace = this.holding ? 0 : p * (1 - this.grip);
  }

  /**
   * On `yard`'s footrope with the body `s` metres out: the outer foot slides along the rope and the inner one
   * closes up, each hand following its foot along the jackstay; the man leans over the yard, his belly on it, and
   * the rope dips under the foot that bears him. The stance depends on `s` alone, so the way back plays the way
   * out backwards and getting on or off meets either.
   */
  private yardAt(yard: Yard, s: number): void {
    const k = this.k, g = this.goals, grip = this.grip, give = yard.give ?? 0.05;
    const u = s / SIDLE_STEP;
    // Facing the yard, the climber's right is (-nz, nx): whether the right foot is the outer one (towards +s).
    const right = -yard.nz * yard.ax + yard.nx * yard.az >= 0 ? 1 : -1, leadR = right > 0;
    // Half the feet's and the hands' spread, in strides.
    const feetW = (0.17 * k) / SIDLE_STEP, handsW = (0.32 * k) / SIDLE_STEP;
    const limbs: [keyof LimbGoals, number, boolean, boolean][] = [
      [leadR ? 'footR' : 'footL', 0, true, false], [leadR ? 'footL' : 'footR', 0.5, false, false],
      [leadR ? 'R' : 'L', 0.25, true, true], [leadR ? 'L' : 'R', 0.75, false, true],
    ];
    for (const [key, o, lead, hand] of limbs) {
      const x = u - o, n = Math.floor(x), fr = x - n;
      const a = smooth(0, 0.5, fr), swing = fr < 0.5 ? Math.sin(Math.PI * a) : 0;
      const along = (n + a + o - 0.25 + (lead ? 1 : -1) * (hand ? handsW : feetW)) * SIDLE_STEP;
      const goal = g[key] as LimbGoal;
      if (hand) {
        yardPoint(yard, along, FOOTROPE_AFT + 0.06, jackstayY(yard, along) + 0.03 + 0.05 * swing * (1 - grip), goal.p);
        g.curl![key as 'L' | 'R'] = 1.2 + 0.3 * grip;
      } else {
        // The foot slides along the rope, barely lifted; the rope dips under the one bearing the man.
        yardPoint(yard, along, 0, footropeY(yard, along) + 0.07 * k + 0.04 * swing - give * (1 - swing), goal.p);
      }
      goal.w = 1;
    }
    g.curlW = 1;
    // Hips abaft the rope, just under the yard (his belly on it), swaying over the bearing foot.
    const mid = s + 0.03 * Math.sin(2 * Math.PI * u);
    const rope = footropeY(yard, mid) - give;
    yardPoint(yard, mid, -0.12 * k, rope + 0.84 * this.hipW - this.hipW, this.pos);
    this.sway(0.25 * k);
    this.yaw = Math.atan2(-yard.nx, -yard.nz);
    this.stance = { spine: -0.75 - 0.15 * grip, neck: 0.55, arm: YARD_ARM, leg: YARD_LEG };
    this.poseFn = stancePose(this.stance);
    this.overW = 1;
  }

  /**
   * Between standing at `from` facing the yard (u = 0) and on its footrope at `at` (u = 1): hands to the
   * jackstay, the near foot down onto the rope, the other after it, the body settling over the yard. Getting off
   * plays it backwards.
   */
  private footrope(yard: Yard, at: number, from: readonly [number, number, number], u: number): void {
    const g = this.goals;
    // Where it ends: the stance on the rope (its pose and holds into the goals).
    this.yardAt(yard, at);
    const end = _u.copy(this.pos), stance = this.poseFn!;
    const [fx, fy, fz] = from;
    // Feet: from beside each other where it stands, onto the rope (the right first), each in an arc.
    for (const [key, t0, t1, side] of [['footR', 0.25, 0.55, 1], ['footL', 0.5, 0.8, -1]] as const) {
      const goal = g[key]!, f = smooth(t0, t1, u);
      _v.set(fx - yard.nz * side * 0.11, fy + 0.07 * this.k, fz + yard.nx * side * 0.11);
      goal.p.lerpVectors(_v, goal.p, f);
      goal.p.y += 0.18 * Math.sin(Math.PI * f);
      goal.w = 1;
    }
    // Hands: up from the sides to the jackstay first.
    const hw = smooth(0, 0.25, u);
    g.L!.w = g.R!.w = hw;
    g.curlW = hw;
    // The body: from standing to the stance, once a foot is on the rope.
    const b = smooth(0.2, 0.85, u);
    this.pos.set(fx, fy, fz).lerp(end, b);
    this.yaw = Math.atan2(-yard.nx, -yard.nz);
    const w = smooth(0, 0.6, u);
    this.poseFn = (p) => {
      // Standing to leaning over the yard: the stance's pose comes in as the body goes over.
      if (w > 0) stance(p);
    };
    this.overW = w;
  }

  /**
   * Between hanging on a ladder (u = 0: the feet `on.h` over its base, as `cling`) and on `yard`'s footrope at `at`
   * (u = 1): the hand nearer the yard across to the jackstay, the near foot from its ratline onto the rope, the
   * other foot, the other hand; the body swings across and turns from the ladder to the yard. Getting back onto the
   * ladder plays it backwards.
   */
  private footropeFromLadder(yard: Yard, at: number, on: OnLadder, u: number): void {
    const g = this.goals;
    // Where it starts: hanging on the ladder, its holds kept.
    this.climbAt(on.ladder, on.h, true);
    for (const key of ['L', 'R', 'footL', 'footR'] as const) _held[key].copy(g[key]!.p);
    const cling = this.stance!, start = _from.copy(this.pos), startYaw = this.yaw;
    // Where it ends: the stance on the rope.
    this.yardAt(yard, at);
    const stance = this.stance!;
    // Which way the yard is from the climber facing the ladder: its near hand and foot go first.
    const rx = -on.ladder.nz, rz = on.ladder.nx;
    yardPoint(yard, at, 0, yard.y, _v);
    const near: Side = (_v.x - start.x) * rx + (_v.z - start.z) * rz >= 0 ? 'R' : 'L', far: Side = near === 'R' ? 'L' : 'R';
    const order: ['L' | 'R' | 'footL' | 'footR', number, number][] = [
      [near, 0, 0.3], [near === 'R' ? 'footR' : 'footL', 0.25, 0.55], [near === 'R' ? 'footL' : 'footR', 0.5, 0.8], [far, 0.7, 1],
    ];
    for (const [key, t0, t1] of order) {
      const goal = g[key]!, f = smooth(t0, t1, u);
      goal.p.lerpVectors(_held[key], goal.p, f);
      goal.p.y += 0.15 * Math.sin(Math.PI * f);
      goal.w = 1;
    }
    g.curlW = 1;
    const b = smooth(0.2, 0.85, u);
    this.pos.lerpVectors(start, this.pos, b);
    this.yaw = lerpAngle(startYaw, this.yaw, smooth(0.1, 0.7, u));
    this.stance = blendStance(cling, stance, b);
    this.poseFn = stancePose(this.stance);
    this.overW = 1;
  }

  /**
   * Between the top of a way down (u = 0: feet on the rung where one leaves the ladder) and standing
   * on the floor beyond the rim (u = 1): hands flat on the floor past the edge, the body pushed up,
   * the right foot onto the edge, then the left, standing up. Getting on plays it backwards.
   */
  private rim(l: Ladder, u: number): void {
    const k = this.k, g = this.goals, base = this.base(l), G = l.floor - base, hT = this.hTop(l);
    // Where the climb leaves the hands and feet (u = 0): they go from there, not from nowhere.
    this.climbAt(l, hT, true);
    for (const key of ['L', 'R', 'footL', 'footR'] as const) _held[key].copy(g[key]!.p);
    const hand = 0.36, stand = 0.62, lb = -0.36 * k;
    const lat = kf(u, [[0, lb], [0.3, lb + 0.06], [0.55, hand - 0.25], [0.75, hand - 0.05], [0.9, stand - 0.1], [1, stand]]);
    const hip = kf(u, [[0, hT + 0.8 * k], [0.3, hT + 0.86 * k], [0.55, G + 0.12 * k], [0.75, G + 0.3 * k], [0.9, G + this.hipW * 0.9], [1, G + this.hipW]]);
    this.placeHips(l, lat, base + hip);
    this.yaw = faceYaw(l);
    // Hands from their last holds (the left first) to flat on the floor past the edge until the body is up.
    const hw = 1 - smooth(0.74, 0.86, u);
    for (const [key, sd, t0] of [['L', -1, 0], ['R', 1, 0.12]] as const) {
      const f = smooth(t0, t0 + 0.2, u);
      this.at(l, hand, sd * 0.2, l.floor + 0.03, g[key]!.p);
      g[key]!.p.lerpVectors(_held[key], g[key]!.p, f);
      g[key]!.p.y += 0.12 * Math.sin(Math.PI * f);
      g[key]!.w = hw;
      g[key]!.flat = f > 0.5 ? (g[key]!.flat ?? new Vector3()).set(l.nx, 0, l.nz) : null;
      g.curl![key] = 1.25 + (0.15 - 1.25) * f;
    }
    g.curlW = hw;
    // Feet: on the top rung, the right one onto the edge, then the left.
    const rUp = smooth(0.3, 0.5, u), lUp = smooth(0.7, 0.88, u);
    this.at(l, -0.11 * k, 0.11, base + hT + 0.075 * k, _v); this.at(l, 0.28, 0.13, l.floor + 0.08 * k, _w);
    g.footR!.p.lerpVectors(_v, _w, rUp);
    // (The lower foot comes up onto the top rung first.)
    g.footR!.p.lerp(_held.footR, 1 - smooth(0, 0.25, u));
    this.toward(l, g.footR!.p, -0.15 * Math.sin(Math.PI * rUp), 0.12 * Math.sin(Math.PI * rUp));
    this.at(l, -0.11 * k, -0.11, base + hT + 0.075 * k, _v); this.at(l, stand - 0.05, -0.13, l.floor + 0.08 * k, _w);
    g.footL!.p.lerpVectors(_v, _w, lUp);
    g.footL!.p.lerp(_held.footL, 1 - smooth(0, 0.25, u));
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
    l = ladderAt(l, y);
    // Facing the wall (nx, nz), the right is (-nz, nx); a leaning face is further in the higher up.
    if (l.lean) a += l.lean * (y - this.base(l));
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

/**
 * A stance's pose: the spine's and the neck's bend and the turns of each arm (forward, out, twist, elbow, forearm)
 * and leg (flex, out, twist, knee, ankle), the same on both sides.
 */
interface Stance {
  readonly spine: number;
  readonly neck: number;
  readonly arm: readonly [number, number, number, number, number];
  readonly leg: readonly [number, number, number, number, number];
}
/** Hanging on a ladder: arms up to the holds, knees bent onto the rungs. */
const CLING_ARM = [2.2, 0.3, 0, 1.0, 0.5] as const;
const CLING_LEG = [1.0, 0.12, 0, 1.4, -0.3] as const;
/** On a footrope: leaning over the yard, the arms forward along it, the legs a little bent. */
const YARD_ARM = [1.2, 0.25, 0, 0.7, 0.4] as const;
const YARD_LEG = [0.35, 0.15, 0, 0.5, 0] as const;

function stancePose(s: Stance): (p: Pose) => void {
  return (p) => {
    p.spine(s.spine);
    p.neck(s.neck);
    for (const sd of ['L', 'R'] as const) {
      p.arm(sd, ...s.arm);
      p.leg(sd, ...s.leg);
    }
  };
}

const lerp5 = (a: readonly number[], b: readonly number[], t: number) => a.map((x, i) => x + (b[i]! - x) * t) as unknown as readonly [number, number, number, number, number];
function blendStance(a: Stance, b: Stance, t: number): Stance {
  return { spine: a.spine + (b.spine - a.spine) * t, neck: a.neck + (b.neck - a.neck) * t, arm: lerp5(a.arm, b.arm, t), leg: lerp5(a.leg, b.leg, t) };
}

const isOnLadder = (f: readonly [number, number, number] | OnLadder): f is OnLadder => !Array.isArray(f);

/** The ladder of `l`'s chain (`above`, `below`) at height y. */
function ladderAt(l: Ladder, y: number): Ladder {
  while (l.above && y > l.above.lo) l = l.above;
  while (l.below && y < l.lo) l = l.below;
  return l;
}

/** The facing (yaw) of a climber facing the ladder's wall. */
export function faceYaw(l: Ladder): number {
  return Math.atan2(-l.nx, -l.nz);
}
