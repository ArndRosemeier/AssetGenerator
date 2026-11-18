/**
 * Walking on a deck in its own frame (pure): a body whose feet are kept in the deck's frame goes with her as she
 * rises, pitches, rolls and sails, exactly, without ever sliding off or sinking through; only where it walks to is
 * worked out here. The game says where a body may stand (`DeckGround`: its walk graph, rooms, doors), the input says
 * where it wants to go, and the step decides where it ends up: easing into its pace, sliding along what it walks
 * into, never stepping higher than a stair's step, never jumping a thin wall however fast it goes, and stooping
 * where the beams are low.
 *
 * Axes are the frame's (frame.ts): x and z on the deck, y up. A heading is a yaw as three.js and @futuremagic/figure
 * turn a body: yaw 0 faces -z, a quarter turn (π/2) faces -x.
 */

/** Where on a deck a body stands: the game's own name for the place (a space, a room) and the floor's height there. */
export interface Standing<P> {
  readonly place: P;
  readonly floor: number;
}

/** A body on a deck, in her frame: its feet (x, z; y their height on the floor), its velocity over the deck, how tall it stands now, its place. */
export interface DeckBody<P> extends Standing<P> {
  readonly x: number;
  readonly z: number;
  readonly vx: number;
  readonly vz: number;
  /** Its height now, m: its full height, or less where it stoops under low beams. */
  readonly height: number;
}

/** Where on a deck a body may stand: what the game knows of her decks, rooms and ways. */
export interface DeckGround<P> {
  /** Where a body's middle may stand at (x, z), coming from where it is: its place and floor; null where it cannot (a wall, a shut door, her side). */
  stand(x: number, z: number, from: Standing<P>): Standing<P> | null;
  /** The clear height over the floor at a place, m (Infinity under the sky); none: always room to stand. */
  headroom?(x: number, z: number, at: Standing<P>): number;
}

/** How a body walks: its paces (m/s), how quickly it answers the input (1/s), its height and how low it stoops, the highest step it takes. */
export interface DeckGait {
  readonly walk: number;
  readonly back: number;
  readonly side: number;
  readonly grip: number;
  readonly tall: number;
  /** The least height it goes about at, crouched, m. */
  readonly least: number;
  /** How far under the beams its head keeps, m. */
  readonly clear: number;
  /** How quickly it stoops and straightens (1/s). */
  readonly stoop: number;
  /** The highest step up or down between two floors it takes walking, m. */
  readonly stepUp: number;
  /** How far ahead it looks for low beams, s of its pace: it ducks before it gets there. */
  readonly ahead: number;
}

/** What the player wants: forward (+1) and back (-1), right (+1) and left (-1), and which way is forward (a yaw in the deck's frame). */
export interface DeckIntent {
  readonly forward: number;
  readonly strafe: number;
  readonly heading: number;
}

/** The longest move tried at once, m: under a body's half-breadth, so a body never steps across a thin wall or a shut door. */
export const SUBSTEP = 0.04;
/** A velocity below this is none (m/s). */
const STILL = 1e-4;

/** A body standing still at a spot. */
export function standAt<P>(at: Standing<P>, x: number, z: number, height: number): DeckBody<P> {
  return { place: at.place, floor: at.floor, x, z, vx: 0, vz: 0, height };
}

/** One step of walking: the body eases toward the pace the input asks, moves as far as the ground lets it, and stoops or straightens. */
export function stepDeckBody<P>(b: DeckBody<P>, intent: DeckIntent, gait: DeckGait, ground: DeckGround<P>, dt: number): DeckBody<P> {
  // The pace asked for, in the deck's frame; a body stooping goes slower, as much as it is bent.
  const push = Math.hypot(intent.forward, intent.strafe), scale = push > 1 ? 1 / push : 1;
  const ahead = intent.forward * scale * (intent.forward >= 0 ? gait.walk : gait.back), aside = intent.strafe * scale * gait.side;
  const bent = b.height / gait.tall, s = Math.sin(intent.heading), c = Math.cos(intent.heading);
  const tx = (-s * ahead + c * aside) * bent, tz = (-c * ahead - s * aside) * bent;
  const k = 1 - Math.exp(-gait.grip * dt);
  let vx = b.vx + (tx - b.vx) * k, vz = b.vz + (tz - b.vz) * k;
  if (Math.hypot(vx, vz) < STILL) { vx = 0; vz = 0; }

  let at: Standing<P> = b, x = b.x, z = b.z;
  const steps = Math.ceil((Math.hypot(vx, vz) * dt) / SUBSTEP);
  for (let i = 0; i < steps; i++) {
    const dx = (vx * dt) / steps, dz = (vz * dt) / steps;
    const whole = tryStand(ground, gait, at, x + dx, z + dz);
    if (whole) { at = whole; x += dx; z += dz; continue; }
    // Blocked: slide along what is in the way, the larger share of the move first.
    const alongX = tryStand(ground, gait, at, x + dx, z), alongZ = tryStand(ground, gait, at, x, z + dz);
    const xFirst = Math.abs(dx) >= Math.abs(dz);
    if (alongX && (xFirst || !alongZ)) { at = alongX; x += dx; vz = 0; } else if (alongZ) { at = alongZ; z += dz; vx = 0; } else { vx = 0; vz = 0; break; }
  }

  const room = Math.min(clearAt(ground, gait, at, x, z), clearAt(ground, gait, at, x + vx * gait.ahead, z + vz * gait.ahead));
  const want = Math.max(gait.least, Math.min(gait.tall, room));
  const height = b.height + (want - b.height) * (1 - Math.exp(-gait.stoop * dt));
  // Never through the beams, however quickly it is asked to stoop.
  return { place: at.place, floor: at.floor, x, z, vx, vz, height: Math.min(height, Math.max(gait.least, room)) };
}

/** The room for a body's height at (x, z), coming from `at`: the headroom less what its head keeps clear (Infinity where it cannot stand). */
function clearAt<P>(ground: DeckGround<P>, gait: DeckGait, at: Standing<P>, x: number, z: number): number {
  if (!ground.headroom) return Infinity;
  const s = ground.stand(x, z, at);
  return s ? ground.headroom(x, z, s) - gait.clear : Infinity;
}

/** Where the body stands at (x, z) coming from `at`, if it may: within a step of the floor it is on. */
function tryStand<P>(ground: DeckGround<P>, gait: DeckGait, at: Standing<P>, x: number, z: number): Standing<P> | null {
  const s = ground.stand(x, z, at);
  return s && Math.abs(s.floor - at.floor) <= gait.stepUp ? s : null;
}
