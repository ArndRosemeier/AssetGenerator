/**
 * The floor under a body's feet on a tilted deck (pure). A deck that pitches and rolls has its floors at heights
 * of its own frame, but a body stands where the world's vertical through its feet meets them: a step aft on a deck
 * pitched bow up is a step down, and a cabin's floor under a castle's deck is a floor only to feet below the castle.
 */
import { vertical, type Crossing, type Frame } from './frame';

/** The floors at a spot of a deck (its frame's x and z): their heights in its frame, lowest first. */
export type FloorsAt = (x: number, z: number) => readonly number[];

/** How high a body's feet step up onto a floor without climbing, m (a stair's step). */
export const STEP_UP = 0.45;

/**
 * The world height of the floor a body stands on at world (x, z), with its feet at `feet` (world y; none: the
 * highest floor there). `level`: the deck's main level in its frame, where the floors to try are found; each floor
 * is then met where the vertical crosses it (a tilted deck's floors lie under different spots of the vertical), and
 * the highest one within `step` of the feet or below them is taken. Null: no floor there for these feet.
 */
export function floorUnder(f: Frame, floorsAt: FloorsAt, x: number, z: number, level: number, feet?: number, step = STEP_UP): number | null {
  const main = vertical(f, x, z, level, mainScratch), floors = floorsAt(main.x, main.z);
  const reach = feet === undefined ? Infinity : feet + step;
  for (let i = floors.length - 1; i >= 0; i--) {
    const h = floors[i]!, c: Crossing = h === level ? main : vertical(f, x, z, h, otherScratch);
    if (c.y <= reach && (c === main || floorsAt(c.x, c.z).includes(h))) return c.y;
  }
  return null;
}
const mainScratch: Crossing = { x: 0, y: 0, z: 0 };
const otherScratch: Crossing = { x: 0, y: 0, z: 0 };
