/** What a humanoid is doing, as the animator reads it. */
import type { Vec3 } from '@futuremagic/core';

export type { Vec3 };

export type MoveState =
  | 'idle' | 'walk' | 'run' | 'sprint' | 'crouch' | 'swim' | 'fly' | 'fall' | 'jump' | 'climb' | 'glide'
  | 'sit' | 'sleep' | 'ride' | 'dead' | 'stunned' | 'knockdown';

/** A one-shot action currently playing (attack, cast, gesture, work...). */
export interface ActionAnim {
  /** Animation id, e.g. "swing_1h", "cast_forward", "gesture_wave", "eat". */
  id: string;
  /** Time (s, the animator's clock) the action started. */
  t0: number;
  /** Duration (s). */
  dur: number;
  /** Optional aim direction for casts/shots. */
  aim?: Vec3;
}

export interface AnimState {
  move: MoveState;
  action?: ActionAnim;
  /** Facial expression hint. */
  mood?: 'neutral' | 'happy' | 'angry' | 'sad' | 'afraid' | 'surprised' | 'disgusted' | 'focused' | 'pain';
  /** True while speaking (lip flap). */
  talking?: boolean;
  /** Look-at target position. */
  lookAt?: Vec3;
  /** Superpower body layer: jump charge, leap, dash. */
  power?: PowerAnim;
  /**
   * Sitting or lying ('sit', 'sleep'): how high the seat or the mattress is above the feet's
   * floor (pos.y), in m. Default: a chair's 0.47 for 'sit', the floor itself for 'sleep'. Keep
   * pos.y on the floor throughout: sitting down, lying down and getting up move the body. A
   * sitter's pos is where they stand to sit, SEAT_REACH in front of the seat's middle.
   * Riding ('ride'): the saddle's height (default RIDE.saddle); pos is the point under the saddle.
   */
  seat?: number;
}

/** Superpower poses layered over locomotion (see Animator.powerLayer). */
export interface PowerAnim {
  /** Super jump charge 0..1 while held, < 0 when not charging. */
  charge: number;
  /** Strength 0..1 of the super jump in progress (0: none); cleared on landing. */
  leap: number;
  /** Animation-clock seconds since the super jump's take-off. */
  leapT: number;
  /** 1 while dashing (fades out after). */
  dash: number;
  /** Flight: body tilt 0 (upright) .. 1 (horizontal), bank (rad), boost 0/1. */
  fly?: { tilt: number; bank: number; boost: number };
}
