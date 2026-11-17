import { test } from 'node:test';
import assert from 'node:assert/strict';
import { Vector3 } from 'three/webgpu';
import { HOLD_RATE, LadderClimb, RATLINE, footropeY, shroudWays, type ClimbStep, type Yard } from '../src/index';

const BODY = { height: 1.8, hipHeight: 0.93 };
/** A brig's main shrouds to starboard, in her frame (x forward, y up from the waterline, z to starboard; the mast at x = z = 0). */
const RIG = { foot: [-0.6, 2.6, 4.4], stave: [-0.3, 13.2, 1.15], rim: [-0.3, 14.3, 1.9], floor: 2.9 } as const;
/** Her main yard, across the ship just forward of the mast; men stand abaft it, facing forward. */
const YARD: Yard = { x: 0.35, y: 13.0, z: 0, ax: 0, az: 1, reach: 7.5, nx: 1, nz: 0 };

/** Runs a climb to its end, frame by frame; returns its time and the largest move of the body and of any hand or foot in one frame. */
function run(c: LadderClimb, each: (c: LadderClimb, t: number) => void = () => undefined, dt = 1 / 30): { t: number; body: number; limb: number } {
  let t = 0, body = 0, limb = 0;
  const last = new Map<string, Vector3>();
  while (c.active && t < 120) {
    c.advance(dt);
    t += dt;
    each(c, t);
    const L = c.limbs;
    for (const [k, p] of [['pos', c.pos], ['L', L?.L], ['R', L?.R], ['footL', L?.footL], ['footR', L?.footR]] as const) {
      const at = p instanceof Vector3 ? p : p && p.w > 0.5 ? p.p : null;
      if (!at) { last.delete(k); continue; }
      const was = last.get(k);
      if (was) { const d = at.distanceTo(was); if (k === 'pos') body = Math.max(body, d); else limb = Math.max(limb, d); }
      last.set(k, at.clone());
    }
  }
  return { t, body, limb };
}

function upTheShrouds(c: LadderClimb): ClimbStep[] {
  const { shroud, futtock } = shroudWays(RIG);
  return [
    { kind: 'walk', ladder: shroud },
    { kind: 'foot', ladder: shroud, dir: 'on' },
    { kind: 'climb', ladder: shroud, from: shroud.floor, to: futtock.lo },
    { kind: 'climb', ladder: futtock, from: futtock.lo, to: c.rimFeet(futtock, BODY) },
    { kind: 'rim', ladder: futtock, dir: 'off' },
  ];
}

test('rigging: shrouds lean in to the stave, futtock shrouds lean out to the rim, in step and meeting', () => {
  const { shroud, futtock } = shroudWays(RIG);
  assert.ok(shroud.lean! > 0.2 && futtock.lean! < -0.2, `${shroud.lean} ${futtock.lean}`);
  assert.equal(shroud.rung, RATLINE);
  const strides = (futtock.lo - shroud.floor) / (2 * RATLINE);
  assert.ok(Math.abs(strides - Math.round(strides)) < 1e-9, 'the futtock shrouds start a whole stride of the gait up');
  assert.ok(futtock.lo <= RIG.stave[1] && futtock.lo > RIG.stave[1] - 2 * RATLINE);
  // The two lines meet where the futtock shrouds start.
  const sx = shroud.x + shroud.nx * shroud.lean! * (futtock.lo - shroud.floor), sz = shroud.z + shroud.nz * shroud.lean! * (futtock.lo - shroud.floor);
  assert.ok(Math.hypot(sx - futtock.x, sz - futtock.z) < 1e-9);
  assert.equal(shroud.above, futtock);
  assert.equal(futtock.below, shroud);
  assert.equal(futtock.floor, RIG.rim[1]);
});

test('rigging: from the rail up the shrouds, round the futtock shrouds and over the rim onto the top, without a jump', () => {
  const c = new LadderClimb();
  const { shroud } = shroudWays(RIG);
  let onSides = 0, frames = 0;
  c.play(upTheShrouds(c), 0, 2.6, 3.5, 0, BODY);
  const r = run(c, (c) => {
    const L = c.limbs;
    if (!L?.L || L.L.w < 1 || c.pos.y < 4 || c.pos.y > 11) return;
    // On the shrouds the hands hold the outer shrouds: as far apart across as the shrouds are wide.
    frames++;
    const across = (L.R!.p.x - L.L.p.x) * -shroud.nz + (L.R!.p.z - L.L.p.z) * shroud.nx;
    if (Math.abs(across - 2 * shroud.halfWidth) < 0.02) onSides++;
  });
  assert.ok(Math.abs(c.pos.y - RIG.rim[1]) < 0.02, `stands on the top (${c.pos.y})`);
  assert.equal(c.pose, null);
  assert.ok(r.t > 8 && r.t < 20, `${r.t.toFixed(1)} s`);
  // At 30 frames a second nothing moves more than a swinging limb does (no jump between ladders or into the rim).
  assert.ok(r.body < 0.13, `body ${r.body.toFixed(3)} m in a frame`);
  assert.ok(r.limb < 0.16, `limb ${r.limb.toFixed(3)} m in a frame`);
  assert.ok(onSides > 0.95 * frames, `${onSides} of ${frames}`);
});

test('rigging: onto the footrope, out to the yardarm and back, sidling, hands on the jackstay, off again', () => {
  const c = new LadderClimb();
  const from = [-0.45, 12.4, 0.9] as const;
  let feet = 0, hands = 0, belly = 0, n = 0;
  c.play([
    { kind: 'footrope', yard: YARD, dir: 'on', at: 1, from },
    { kind: 'yard', yard: YARD, from: 1, to: 6.5 },
    { kind: 'yard', yard: YARD, from: 6.5, to: 1 },
    { kind: 'footrope', yard: YARD, dir: 'off', at: 1, from },
  ], from[0], from[1], from[2], 0, BODY);
  let out = 0;
  const r = run(c, (c, t) => {
    const L = c.limbs;
    if (!L || t < 2.4 || t > 21) return; // along the yard
    n++;
    out = Math.max(out, c.pos.z);
    for (const f of [L.footL!, L.footR!]) feet = Math.max(feet, Math.abs(f.p.y - 0.07 - footropeY(YARD, f.p.z)));
    for (const h of [L.L!, L.R!]) hands = Math.max(hands, Math.abs(h.p.y - YARD.y));
    const hips = c.pos.y + BODY.hipHeight;
    if (hips > YARD.y - 0.45 && hips < YARD.y - 0.1) belly++;
  });
  assert.ok(feet < 0.06, `feet on the rope (${feet.toFixed(3)})`);
  assert.ok(hands < 0.09, `hands on the jackstay, lifted a little to move (${hands.toFixed(3)})`);
  assert.equal(belly, n, 'leaning over the yard all the way');
  assert.ok(out > 6.3, `out to the yardarm (${out.toFixed(2)})`);
  assert.ok(c.pos.distanceTo(new Vector3(...from)) < 1e-6, 'back where it got on');
  assert.ok(r.body < 0.05 && r.limb < 0.1, `${r.body} ${r.limb}`);
});

/** Gravity's up in her frame (z to starboard) for a heel of `a` radians to starboard (+: her masts lean to +z). */
function heel(c: LadderClimb, a: number): void { c.up.set(0, Math.cos(a), -Math.sin(a)); }

test('rigging: at sea she slows the climb as she heels, and a hard roll makes the climber stop and hold on', () => {
  const calm = new LadderClimb(), heeled = new LadderClimb(), rolled = new LadderClimb();
  calm.play(upTheShrouds(calm), 0, 2.6, 3.5, 0, BODY);
  const tCalm = run(calm).t;
  // Heeled 25° to starboard, her lee shrouds hang over the climber; the climb is slower but gets there.
  heeled.play(upTheShrouds(heeled), 0, 2.6, 3.5, 0, BODY);
  const tHeeled = run(heeled, (c) => heel(c, 0.44)).t;
  assert.ok(tHeeled > tCalm * 1.15, `${tHeeled.toFixed(1)} vs ${tCalm.toFixed(1)} s`);
  assert.ok(Math.abs(heeled.pos.y - RIG.rim[1]) < 0.02);
  // A hard roll for two seconds part way up: the climber stops, grips and goes on once it eases.
  rolled.play(upTheShrouds(rolled), 0, 2.6, 3.5, 0, BODY);
  let heldAt = NaN, maxGrip = 0, movedWhileHeld = 0, prevY = 0;
  const r = run(rolled, (c, t) => {
    const hard = t > 5 && t < 7;
    heel(c, hard ? 0.3 * Math.sin((t - 5) * 4) : 0); // 1.2 rad/s at its fastest
    if (hard && c.grip > 0.99) {
      if (Number.isNaN(heldAt)) heldAt = c.pos.y;
      movedWhileHeld = Math.max(movedWhileHeld, Math.abs(c.pos.y - prevY));
    }
    maxGrip = Math.max(maxGrip, c.grip);
    prevY = c.pos.y;
  });
  assert.ok(4 * 0.3 > HOLD_RATE);
  assert.ok(maxGrip === 1 && !Number.isNaN(heldAt), 'held on');
  assert.ok(movedWhileHeld < 0.01, `still while holding on (${movedWhileHeld})`);
  assert.equal(rolled.grip, 0);
  assert.ok(Math.abs(rolled.pos.y - RIG.rim[1]) < 0.02, 'went on to the top');
  assert.ok(r.t > tCalm + 1.5, `${r.t.toFixed(1)} vs ${tCalm.toFixed(1)} s`);
});

test('rigging: a yard sloping too steeply along its length is held on to; the body hangs to the low side', () => {
  const c = new LadderClimb();
  c.play([{ kind: 'yard', yard: YARD, from: 1, to: 5 }], 0, 12, 1, 0, BODY);
  // Heeled 30° (the yard across her slopes as much): too steep, held.
  for (let i = 0; i < 60; i++) { heel(c, 0.52); c.advance(1 / 30); }
  assert.equal(c.pace, 0);
  assert.ok(c.grip > 0.99);
  const z = c.pos.z;
  // Back to 10° within a second or so: on it goes, slower than on a level yard.
  for (let i = 0; i < 60; i++) { heel(c, Math.max(0.17, 0.52 - i * 0.03)); c.advance(1 / 30); }
  assert.ok(c.pace > 0.3 && c.pace < 0.9, `${c.pace}`);
  assert.ok(c.pos.z > z + 0.05, 'moving out again');
  // Heeled to starboard, the body hangs out towards starboard (+z): gravity pulls it there.
  const level = new LadderClimb(), tilted = new LadderClimb();
  level.sidle(YARD, 3, BODY);
  heel(tilted, 0.17);
  tilted.sidle(YARD, 3, BODY);
  assert.ok(tilted.pos.z > level.pos.z + 0.02, `${tilted.pos.z} vs ${level.pos.z}`);
});

test('rigging: a steered climb (cling) reports its pace, slower on the futtock shrouds than on the shrouds', () => {
  const { shroud, futtock } = shroudWays(RIG);
  const c = new LadderClimb();
  c.cling(shroud, 3, true, BODY, 1 / 30);
  const onShrouds = c.pace;
  c.cling(futtock, 0.5, true, BODY, 1 / 30);
  assert.ok(onShrouds === 1 && c.pace < 0.9 && c.pace > 0.2, `${onShrouds} ${c.pace}`);
  assert.ok(c.limbs && c.pose);
});
