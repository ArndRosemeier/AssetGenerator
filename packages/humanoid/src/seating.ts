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

/**
 * Riding a bicycle (AnimState move 'ride', `seat` the saddle's height above the feet's ground):
 * the rider's pos is the point under the saddle, facing the way the bicycle goes. Their hands
 * go onto the bars and their feet onto the pedals, which turn with the distance ridden; stopped,
 * the cranks rest with one pedal down. A bicycle drawn to match puts its parts here (m).
 */
export const RIDE = {
  /** Saddle height when not given. */
  saddle: 0.9,
  /** The grips: this far ahead of the saddle, this far above it, this far either side of the middle. */
  barsAhead: 0.55, barsUp: 0.15, barsHalf: 0.22,
  /** The crank axle: this far ahead of the saddle and above the ground. */
  crankAhead: 0.18, crankUp: 0.28,
  /** Crank length, and the distance ridden per turn of the cranks. */
  crank: 0.17, perTurn: 2.1,
  /** The pedals either side of the middle. */
  pedalHalf: 0.11,
} as const;

/**
 * Riding a horse (AnimState move 'ride' with `mount: 'horse'`, `seat` the saddle's lowest point
 * above the feet's ground): pos is the point under the saddle, facing the way the horse goes. The
 * rider sits upright with the thighs round the barrel, the knees bent and the heels down, and the
 * hands low in front on the reins. Whoever places the rider moves pos and seat with the saddle
 * every frame (the horse's back rises and falls with its gait).
 */
export const HORSE_RIDE = {
  /** Saddle height when not given (a horse of about 1.6 m at the withers). */
  saddle: 1.3,
  /** The hands on the reins: this far ahead of the saddle, this far above it, either side of the middle. */
  reinsAhead: 0.4, reinsUp: 0.24, reinsHalf: 0.08,
  /** Half the barrel's width under the rider's thighs: the knees stay outside it. */
  barrel: 0.22,
} as const;

/**
 * The crank angle (rad) after riding `dist` m from angle `from`: 0 is the left pedal straight down,
 * a quarter turn later at the back, then up, then at the front (the cranks turn as the wheels do).
 */
export function crankAfter(from: number, dist: number): number {
  return (from + (dist / RIDE.perTurn) * 2 * Math.PI) % (2 * Math.PI);
}

/**
 * A pedal's place on the crank at angle `a` (the left pedal; the right one is half a turn on):
 * [ahead of the axle, above it] (m).
 */
export function pedalAt(a: number): [number, number] {
  return [-RIDE.crank * Math.sin(a), -RIDE.crank * Math.cos(a)];
}
