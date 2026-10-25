import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import * as THREE from 'three/webgpu';
import { randomAppearance, setHumanAssetBase, RIDE, HORSE_RIDE, pedalAt } from '../src/index';
import { Humanoid, clipLibraryReady, type Wardrobe } from '../src/three/index';

// The assets come from disk: fetch of file:// URLs, which node's fetch does not do.
const base = new URL('../assets/', import.meta.url);
const realFetch = globalThis.fetch;
globalThis.fetch = (async (u: string | URL) => {
  if (!String(u).startsWith('file:')) return realFetch(u);
  const b = readFileSync(fileURLToPath(String(u)));
  return { ok: true, json: async () => JSON.parse(b.toString()), arrayBuffer: async () => b.buffer.slice(b.byteOffset, b.byteOffset + b.byteLength) };
}) as typeof fetch;
setHumanAssetBase(base.href);

const NAKED: Wardrobe = { resolve: () => null, itemDef: () => undefined, buildItem: () => new THREE.Group(), disposeItem: () => {} };
const at = (h: Humanoid, n: string) => h.char.bone(n).getWorldPosition(new THREE.Vector3());

test('riding a bicycle: on the saddle, hands on the bars, feet on the pedals going round with the distance, one pedal down when stopped', async () => {
  await clipLibraryReady();
  const h = await Humanoid.create(randomAppearance('human', 7), { wardrobe: NAKED });
  const saddle = 0.92, v = 4; // yaw 0 faces -z: riding at 4 m/s that way
  const dt = 1 / 60;
  let t = 0;
  const step = (speed: number) => {
    h.update({ pos: [0, 0, 0], vel: [0, 0, -speed], yaw: 0, anim: { move: 'ride', seat: saddle } }, dt, t, () => 0);
    h.object.updateMatrixWorld(true);
    t += dt;
  };
  for (let k = 0; k < 60; k++) step(v);
  const lows: number[] = [];
  let prev = at(h, 'foot.L').y, falling = false;
  for (let k = 0; k < 120; k++) {
    step(v);
    const hip = at(h, 'upperleg01.L').add(at(h, 'upperleg01.R')).multiplyScalar(0.5);
    assert.ok(hip.y > saddle && hip.y < saddle + 0.15, `hips ${hip.y.toFixed(2)} m on a ${saddle} m saddle`);
    assert.ok(Math.abs(hip.z) < 0.15, `hips over the saddle (z ${hip.z.toFixed(2)})`);
    for (const s of ['L', 'R'] as const) {
      const w = at(h, `wrist.${s}`);
      assert.ok(Math.abs(w.y - (saddle + RIDE.barsUp)) < 0.12 && Math.abs(-w.z - RIDE.barsAhead) < 0.15, `${s} hand at the bars (${w.y.toFixed(2)} up, ${(-w.z).toFixed(2)} ahead)`);
    }
    const f = at(h, 'foot.L');
    if (f.y > prev && falling) lows.push(t);
    falling = f.y < prev;
    prev = f.y;
  }
  // One turn of the cranks per RIDE.perTurn m: the left foot is lowest once a turn.
  assert.ok(lows.length >= 3, `the left foot goes round (${lows.length} low points in 2 s)`);
  const turn = (lows.at(-1)! - lows[0]) / (lows.length - 1);
  assert.ok(Math.abs(turn - RIDE.perTurn / v) < 0.05, `a turn takes ${turn.toFixed(3)} s at ${v} m/s (want ${(RIDE.perTurn / v).toFixed(3)})`);
  // Stopped: the cranks come round to one pedal down, and stay.
  for (let k = 0; k < 120; k++) step(0);
  const L = at(h, 'foot.L').y, R = at(h, 'foot.R').y;
  const low = RIDE.crankUp + pedalAt(0)[1] + 0.08, high = RIDE.crankUp + pedalAt(Math.PI)[1] + 0.08;
  assert.ok(Math.abs(Math.min(L, R) - low) < 0.05 && Math.abs(Math.max(L, R) - high) < 0.05, `stopped with one pedal down (feet at ${L.toFixed(2)} and ${R.toFixed(2)} m)`);
  step(0);
  assert.ok(Math.abs(at(h, 'foot.L').y - L) < 0.002, 'the feet rest');
});

test('riding a horse: upright on the saddle, the knees round the barrel, the feet hanging below, the hands on the reins', async () => {
  await clipLibraryReady();
  const h = await Humanoid.create(randomAppearance('human', 7), { wardrobe: NAKED });
  const saddle = 1.32, dt = 1 / 60;
  let t = 0;
  for (let k = 0; k < 90; k++) {
    // The saddle rises and falls a little with the trot.
    const y = 0.03 * Math.sin(t * 9);
    h.update({ pos: [0, y, 0], vel: [0, 0, -3.5], yaw: 0, anim: { move: 'ride', mount: 'horse', seat: saddle } }, dt, t, () => 0);
    h.object.updateMatrixWorld(true);
    t += dt;
  }
  const y = 0.03 * Math.sin((t - dt) * 9);
  const hipL = at(h, 'upperleg01.L'), hipR = at(h, 'upperleg01.R');
  const hip = hipL.clone().add(hipR).multiplyScalar(0.5);
  assert.ok(hip.y > y + saddle && hip.y < y + saddle + 0.15, `hips ${(hip.y - y).toFixed(2)} m on a ${saddle} m saddle`);
  assert.ok(Math.abs(hip.z) < 0.15 && Math.abs(hip.x) < 0.05, `hips over the saddle (${hip.x.toFixed(2)}, ${hip.z.toFixed(2)})`);
  // Upright: the neck over the hips, not leaning over bars.
  const neck = at(h, 'neck01');
  assert.ok(neck.y - hip.y > 0.4 && Math.abs(neck.z - hip.z) < 0.2, `upright (neck ${(neck.y - hip.y).toFixed(2)} up, ${(hip.z - neck.z).toFixed(2)} ahead)`);
  for (const s of ['L', 'R'] as const) {
    const knee = at(h, `lowerleg01.${s}`), foot = at(h, `foot.${s}`), wrist = at(h, `wrist.${s}`);
    const out = Math.abs(knee.x);
    assert.ok(out > HORSE_RIDE.barrel, `${s} knee ${out.toFixed(2)} m out, round the barrel (${HORSE_RIDE.barrel})`);
    assert.ok(Math.sign(knee.x) === Math.sign((s === 'L' ? hipL : hipR).x), `${s} knee on its own side`);
    assert.ok(knee.y < hip.y && foot.y < knee.y - 0.2, `${s} foot hangs below the knee (${foot.y.toFixed(2)}, knee ${knee.y.toFixed(2)})`);
    assert.ok(Math.abs(foot.z - hip.z) < 0.35, `${s} foot under the rider (${(hip.z - foot.z).toFixed(2)} ahead)`);
    assert.ok(Math.abs(Math.abs(foot.x) - out) < 0.08, `${s} shin hangs down from the knee (foot ${foot.x.toFixed(2)}, knee ${knee.x.toFixed(2)})`);
    assert.ok(wrist.y > hip.y + 0.05 && wrist.y < hip.y + 0.45 && hip.z - wrist.z > 0.2 && hip.z - wrist.z < 0.6, `${s} hand low in front (${(wrist.y - hip.y).toFixed(2)} up, ${(hip.z - wrist.z).toFixed(2)} ahead)`);
  }
});
