import { test } from 'node:test';
import assert from 'node:assert/strict';
import { SEAT_SINK, floatOf, seat, seatHeight } from '../src/index';

/** A slope of one in four down towards +x, with a bump. */
const slope = (x: number, z: number) => -x * 0.25 + Math.sin(z) * 0.1;
/** A box of half sizes hx, hy, hz with its foot at y0, round (x, z): its eight corners. */
const box = (x: number, y0: number, z: number, hx: number, hy: number, hz: number) => {
  const p: number[] = [];
  for (const a of [-1, 1]) for (const b of [0, 2]) for (const c of [-1, 1]) p.push(x + a * hx, y0 + b * hy, z + c * hz);
  return p;
};

test('ground: a piece set at its middle floats on a slope; seated, its downhill edge is in the ground', () => {
  const p = box(3, slope(3, 0), 0, 1, 0.3, 0.5);
  assert.ok(floatOf(slope, p) > 0.2, 'its downhill edge floats');
  const dy = seat(slope, p);
  assert.ok(dy < 0);
  assert.ok(Math.abs(floatOf(slope, p) + SEAT_SINK) < 1e-9, 'sunk SEAT_SINK below the lowest ground under it');
});

test('ground: an overhang high above the foot does not drag a piece down; seatHeight gives the lowest ground over a footprint', () => {
  // A post with a wide top 2 m up: only the post's foot counts.
  const p = [...box(0, 0, 0, 0.1, 1, 0.1), ...box(0, 2, 0, 2, 0.05, 0.1)];
  const dy = seat(slope, p);
  assert.ok(Math.abs(dy - (slope(0.1, 0) - SEAT_SINK)) < 0.03, `${dy}`);
  const y = seatHeight(slope, 0, 0, 2, 0.5, 0, 0);
  assert.ok(Math.abs(y - slope(2, -0.5)) < 1e-9, `${y}`);
});
