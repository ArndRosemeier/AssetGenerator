import { test } from 'node:test';
import assert from 'node:assert/strict';
import { LadderClimb, faceYaw, rimWalk, type Ladder } from '../src/index';

/** A way down: rungs against the wall on +x, the floor at 0, rungs from −2.4 to 0. */
const SHAFT: Ladder = { x: 0, z: 0, nx: 1, nz: 0, lo: -2.4, hi: 0, floor: 0, halfWidth: 0.25, rim: true };
/** A ladder up from a floor at −3: got on at its foot. */
const FOOT: Ladder = { x: 5, z: 0, nx: 1, nz: 0, lo: -2.7, hi: -0.5, floor: -3, halfWidth: 0.25, rim: false, rung: 0.32 };
const BODY = { height: 1.8, hipHeight: 0.93 };

/** Runs a climb to its end in steps of `dt`, calling `each` every frame. */
function run(c: LadderClimb, each: (c: LadderClimb) => void, dt = 1 / 30): number {
  let t = 0;
  while (c.active && t < 60) { c.advance(dt); each(c); t += dt; }
  return t;
}

test('ladder: down a shaft over the rim, through a change of place, off at the foot of another ladder', () => {
  const c = new LadderClimb();
  let swapped = 0, darkAtSwap = -1, posed = 0;
  c.play([
    { kind: 'walk', ladder: SHAFT },
    { kind: 'rim', ladder: SHAFT, dir: 'on' },
    { kind: 'climb', ladder: SHAFT, from: c.rimFeet(SHAFT), to: -2, fade: 'out' },
    { kind: 'call', then: () => { swapped++; darkAtSwap = c.fade; } },
    { kind: 'climb', ladder: FOOT, from: -1.6, to: -3, fade: 'in' },
    { kind: 'foot', ladder: FOOT, dir: 'off' },
  ], 2, 0, 1, 0, BODY);
  const t = run(c, (c) => { if (c.pose) posed++; });
  assert.equal(swapped, 1);
  assert.ok(darkAtSwap > 0.95, `dark at the swap (${darkAtSwap})`);
  assert.ok(posed > 30, 'posed while on the ladders');
  assert.ok(Math.abs(c.pos.y - -3) < 0.05, `stands on the floor below (${c.pos.y})`);
  assert.equal(c.fade, 0);
  assert.equal(c.pose, null);
  assert.ok(t > 3 && t < 15, `a few seconds (${t.toFixed(1)} s)`);
  assert.ok(Math.abs(c.yaw - faceYaw(FOOT)) < 1e-6, 'faces the ladder');
});

test('ladder: walking to the rim moves the feet with a velocity, then turns to face the wall', () => {
  const c = new LadderClimb();
  c.play([{ kind: 'walk', ladder: SHAFT }], 3, 0, 2, Math.PI, BODY);
  c.advance(0.2);
  assert.ok(c.walking && Math.hypot(c.vel[0], c.vel[2]) > 0.5);
  run(c, () => undefined);
  // It stands 0.62 m past the rungs, on the floor beyond the rim (the hole behind it).
  assert.ok(Math.hypot(c.pos.x - 0.62, c.pos.z) < 0.02, `${c.pos.x}, ${c.pos.z}`);
});

test('ladder: a walk goes round a hole, never over it', () => {
  const out: [number, number] = [0, 0];
  for (let f = 0; f <= 1; f += 0.05) {
    rimWalk(-2, 0, 2, 0, [0, 0, 1], f, out);
    assert.ok(Math.hypot(out[0], out[1]) >= 1.44, `${f}: ${out}`);
  }
});

test('ladder: a walk can end facing the hole; holding still reports its progress; a turn faces about', () => {
  const c = new LadderClimb(), seen: number[] = [];
  const hole = faceYaw(SHAFT) + Math.PI;
  c.play([
    { kind: 'walk', ladder: SHAFT, face: hole },
    { kind: 'hold', dur: 1, each: (u) => seen.push(u) },
    { kind: 'turn', to: faceYaw(SHAFT) },
  ], 2, 0, 0, 0, BODY);
  let faced = false;
  run(c, (c) => { if (seen.length === 1) faced = Math.abs(Math.cos(c.yaw - hole) - 1) < 1e-3; });
  assert.ok(faced, 'faces the hole while it holds');
  assert.ok(seen.length > 20 && seen[seen.length - 1] > 0.999, `${seen.length} ${seen[seen.length - 1]}`);
  assert.ok(Math.abs(Math.cos(c.yaw - faceYaw(SHAFT)) - 1) < 1e-6, 'turned to the wall');
});

test('ladder: clinging to a leaning rock face, steered frame by frame: hands and feet on it, higher holds further in', () => {
  const c = new LadderClimb();
  const face: Ladder = { x: 0, z: 0, nx: 0, nz: -1, lo: 0, hi: 30, floor: 0, halfWidth: 0.35, rim: false, lean: 0.25 };
  const body = { height: 1.8, hipHeight: 0.93 };
  c.cling(face, 1, true, body);
  assert.ok(c.pose && c.limbs, 'posed');
  const low = c.limbs!.footR!.p.z, hand = c.limbs!.L!.p.z;
  assert.ok(hand < low - 0.2, `the hand (z ${hand.toFixed(2)}) further into the face than the foot (${low.toFixed(2)})`);
  c.cling(face, 11, true, body);
  assert.ok(c.limbs!.footR!.p.z < low - 2, 'ten metres up, the holds are further in');
  assert.ok(c.pos.y > 10, 'the body is up there');
  assert.ok(!c.active, 'nothing played meanwhile');
});

test('ladder: on a rock face the hands take hold over the head (reach), on a ladder at the chest', () => {
  const c = new LadderClimb();
  const body = { height: 1.8, hipHeight: 0.93 };
  const face: Ladder = { x: 0, z: 0, nx: 0, nz: -1, lo: 0, hi: 30, floor: 0, halfWidth: 0.35, rim: false };
  c.cling(face, 3, true, body);
  const chest = Math.max(c.limbs!.L!.p.y, c.limbs!.R!.p.y) - c.pos.y;
  c.cling({ ...face, reach: 1.9 }, 3, true, body);
  const over = Math.max(c.limbs!.L!.p.y, c.limbs!.R!.p.y) - c.pos.y;
  assert.ok(chest < 1.6, `ladder holds ${chest.toFixed(2)} m over the feet`);
  assert.ok(over > 1.85, `rock holds ${over.toFixed(2)} m over the feet: over the head`);
  // A small climber reaches as high for their size.
  c.cling({ ...face, reach: 1.9 }, 3, true, { height: 0.93, hipHeight: 0.45 });
  assert.ok(Math.max(c.limbs!.L!.p.y, c.limbs!.R!.p.y) - c.pos.y > 0.9);
});
