/**
 * Sitting and lying, for whoever places a humanoid (pure: game logic, workers). The animator
 * (three/anim/Animator.ts) draws it: AnimState move 'sit' or 'sleep' with `seat` the seat's or
 * mattress's height above the floor.
 */

/**
 * Sitting, the character stands this far (m) in front of the seat's middle: someone walks up to
 * there, turns their back to the seat and sits down, and gets up there again (pos does not move).
 */
export const SEAT_REACH = 0.3;

/** A chair's seat height (m): AnimState.seat when sitting and not given. */
export const SEAT_HEIGHT = 0.47;
