import { test } from 'node:test';
import assert from 'node:assert/strict';
import { Rider, floorUnder, frameToLocal, frameToWorld, standAt, stepDeckBody, upInFrame, vertical, type DeckGait, type DeckGround, type Frame, type Vec3 } from '../src/index';

/** A frame turned by yaw about y, then pitched about x and rolled about z (row-major, frame into world). */
function frame(origin: Vec3, yaw: number, pitch: number, roll: number): Frame {
  const cy = Math.cos(yaw), sy = Math.sin(yaw), cp = Math.cos(pitch), sp = Math.sin(pitch), cr = Math.cos(roll), sr = Math.sin(roll);
  // R = Ry · Rx · Rz
  const rx = [1, 0, 0, 0, cp, -sp, 0, sp, cp], ry = [cy, 0, sy, 0, 1, 0, -sy, 0, cy], rz = [cr, -sr, 0, sr, cr, 0, 0, 0, 1];
  const mul = (a: number[], b: number[]) => a.map((_, i) => [0, 1, 2].reduce((s, k) => s + a[Math.floor(i / 3) * 3 + k]! * b[k * 3 + (i % 3)]!, 0));
  return { origin, rotation: mul(mul(ry, rx), rz) };
}

test('deck: a point of the frame goes into the world and back', () => {
  const f = frame({ x: 4, y: 0.4, z: -3 }, 0.7, 0.08, -0.2);
  const w = frameToWorld(f, 2, 1.5, -6), l = frameToLocal(f, w.x, w.y, w.z);
  assert.ok(Math.abs(l.x - 2) < 1e-12 && Math.abs(l.y - 1.5) < 1e-12 && Math.abs(l.z + 6) < 1e-12);
  const up = upInFrame(frame({ x: 0, y: 0, z: 0 }, 0, 0, 0.3));
  assert.ok(Math.abs(Math.hypot(up.x, up.y, up.z) - 1) < 1e-12 && up.x > 0.29, 'rolled: up leans');
});

test('deck: the vertical through a spot meets a level of a tilted frame where the frame says', () => {
  const f = frame({ x: 1, y: -0.5, z: 2 }, 1.1, 0.12, 0.25);
  const c = vertical(f, 3.3, -1.2, 2.4), back = frameToLocal(f, 3.3, c.y, -1.2);
  assert.ok(Math.abs(back.y - 2.4) < 1e-12 && Math.abs(back.x - c.x) < 1e-12 && Math.abs(back.z - c.z) < 1e-12);
});

test('deck: the floor under the feet is the highest within a step of them, met along the vertical', () => {
  // A level frame: a deck at 3, and under a castle (x < 0) a cabin's floor at 3 and the castle's deck at 5.
  const f = frame({ x: 0, y: 0, z: 0 }, 0, 0, 0);
  const floors = (x: number) => (x < 0 ? [3, 5] : [3]);
  assert.equal(floorUnder(f, floors, -1, 0, 3), 5, 'no feet: the highest');
  assert.equal(floorUnder(f, floors, -1, 0, 3, 3), 3, 'feet in the cabin: its floor');
  assert.equal(floorUnder(f, floors, -1, 0, 3, 4.7), 5, 'feet a step under the castle deck: onto it');
  assert.equal(floorUnder(f, floors, 1, 0, 3, 1), null, 'feet far under the deck: none');
  // Pitched bow (-z) up: the floor at a spot forward is higher in the world.
  const p = frame({ x: 0, y: 0, z: 0 }, 0, 0.1, 0);
  assert.ok(floorUnder(p, () => [3], 0, -4, 3)! > floorUnder(p, () => [3], 0, 4, 3)!);
});

test('deck: a rider is carried by the deck it stands on, and not carried back once put elsewhere', () => {
  const body = { x: 2, y: 3, z: 1 }, rider = new Rider<string>(() => body);
  const f0 = frame({ x: 0, y: 0, z: 0 }, 0, 0, 0), f1 = frame({ x: 0.5, y: 0.4, z: -0.2 }, 0.1, 0.05, -0.1);
  rider.board('brig', f0);
  assert.equal(rider.on, 'brig');
  rider.carry('brig', f1);
  const l = frameToLocal(f1, body.x, body.y, body.z);
  assert.ok(Math.abs(l.x - 2) < 1e-12 && Math.abs(l.y - 3) < 1e-12 && Math.abs(l.z - 1) < 1e-12, 'the same spot of the deck');
  rider.carry('sloop', f0);
  assert.ok(Math.abs(frameToLocal(f1, body.x, body.y, body.z).x - 2) < 1e-12, 'another deck does not move it');
  body.x = 40;
  rider.carry('brig', f0);
  assert.equal(body.x, 40, 'put elsewhere: stays');
  rider.drop('brig');
  assert.equal(rider.on, null);
});

/** A room 4 m by 4 m with a wall across its middle (z = 0) and a gap in it for x in 1..1.6; the beams over its far half (z < 0) are low. */
const room: DeckGround<string> = {
  stand(x, z) {
    if (Math.abs(x) > 2 || Math.abs(z) > 2) return null;
    if (Math.abs(z) < 0.3 && !(x > 1.3 - 0.05 && x < 1.3 + 0.05)) return null;
    return { place: z < 0 ? 'fore' : 'aft', floor: 0 };
  },
  headroom: (_x, z) => (z < -0.5 ? 1.3 : Infinity),
};
const gait: DeckGait = { walk: 1.6, back: 0.8, side: 1, grip: 8, tall: 1.78, least: 1.05, clear: 0.1, stoop: 6, stepUp: 0.45, ahead: 0.4 };

test('deck: a body walks, slides along a wall it walks into at a slant, and never steps through it', () => {
  let b = standAt({ place: 'aft', floor: 0 }, -1, 1, gait.tall);
  // Toward the wall at a slant (heading a little left of -z, forward and a little to the right).
  for (let i = 0; i < 120; i++) b = stepDeckBody(b, { forward: 1, strafe: 0.6, heading: 0 }, gait, room, 1 / 60);
  assert.equal(b.place, 'aft');
  assert.ok(b.z >= 0.3 - 1e-9, `through the wall: z ${b.z}`);
  assert.ok(b.x > -0.6, `slid along it: x ${b.x.toFixed(2)}`);
  // Very fast, straight at it: still not through.
  let c = standAt({ place: 'aft', floor: 0 }, -1, 1, gait.tall);
  for (let i = 0; i < 10; i++) c = stepDeckBody(c, { forward: 1, strafe: 0, heading: 0 }, { ...gait, walk: 40, grip: 1000 }, room, 1 / 30);
  assert.ok(c.z >= 0.3 - 1e-9 && c.place === 'aft');
});

test('deck: through the gap and under the low beams it stoops before it gets there, never into them', () => {
  let b = standAt({ place: 'aft', floor: 0 }, 1.3, 1.2, gait.tall);
  let lowest = Infinity;
  for (let i = 0; i < 180; i++) {
    b = stepDeckBody(b, { forward: 1, strafe: 0, heading: 0 }, gait, room, 1 / 60);
    if (b.z < -0.5) assert.ok(b.height <= 1.3 - gait.clear + 1e-9, `head in the beams at z ${b.z.toFixed(2)}: ${b.height.toFixed(2)}`);
    lowest = Math.min(lowest, b.height);
  }
  assert.equal(b.place, 'fore');
  assert.ok(Math.abs(lowest - 1.2) < 0.01);
  // Back out: it straightens again.
  for (let i = 0; i < 240; i++) b = stepDeckBody(b, { forward: -1, strafe: 0, heading: 0 }, gait, room, 1 / 60);
  assert.ok(b.place === 'aft' && b.height > gait.tall - 0.01);
});

test('deck: a floor more than a step up is not walked onto', () => {
  const ledge: DeckGround<string> = { stand: (x) => ({ place: x > 1 ? 'up' : 'down', floor: x > 1 ? 0.6 : 0 }) };
  let b = standAt({ place: 'down', floor: 0 }, 0, 0, gait.tall);
  for (let i = 0; i < 120; i++) b = stepDeckBody(b, { forward: 1, strafe: 0, heading: -Math.PI / 2 }, gait, ledge, 1 / 60);
  assert.ok(b.place === 'down' && b.x <= 1 && b.x > 0.9);
});
