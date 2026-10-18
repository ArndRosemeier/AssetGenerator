import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import * as THREE from 'three/webgpu';
import { randomAppearance, setHumanAssetBase } from '../src/index';
import { Humanoid, clipLibraryReady, type AnimState, type Wardrobe } from '../src/three/index';
import { clipSettings } from '../src/three/anim/clips';
import { SEAT_REACH } from '../src/seating';

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
const hips = (h: Humanoid) => at(h, 'upperleg01.L').add(at(h, 'upperleg01.R')).multiplyScalar(0.5);

/** Run `h` through `script` (seconds → its state) at 60 fps; the hips (and head) every frame. */
function run(h: Humanoid, script: (t: number) => AnimState, secs: number, t0 = 0): { t: number; hip: THREE.Vector3; head: THREE.Vector3 }[] {
  const out = [];
  const dt = 1 / 60;
  for (let k = 0; k < secs * 60; k++) {
    const t = t0 + k * dt;
    h.update({ pos: [0, 0, 0], vel: [0, 0, 0], yaw: 0, anim: script(t) }, dt, t, () => 0);
    h.object.updateMatrixWorld(true);
    out.push({ t, hip: hips(h), head: at(h, 'head') });
  }
  return out;
}

for (const clips of [true, false]) test(`sitting down on a bench, sitting, getting up: smooth, onto the seat and back to standing (clips ${clips ? 'on' : 'off'})`, async () => {
  await clipLibraryReady();
  clipSettings.enabled = clips;
  const h = await Humanoid.create(randomAppearance('human', 7), { wardrobe: NAKED });
  const seat = 0.44;
  const stand = run(h, () => ({ move: 'idle' }), 1).at(-1)!.hip;
  const down = run(h, () => ({ move: 'sit', seat }), 3, 1);
  const up = run(h, () => ({ move: 'idle' }), 2.5, 4);
  const all = [...down, ...up];
  for (let i = 1; i < all.length; i++) {
    const d = all[i].hip.distanceTo(all[i - 1].hip);
    assert.ok(d < 0.035, `the hips jump ${d.toFixed(3)} m at ${all[i].t.toFixed(2)} s`);
  }
  const sat = down.at(-1)!.hip;
  assert.ok(sat.y > seat + 0.02 && sat.y < seat + 0.2, `seated hips ${sat.y.toFixed(2)} m over a ${seat} m seat`);
  // Yaw 0 faces -z: the seat is behind them, at +SEAT_REACH.
  assert.ok(Math.abs(sat.z - SEAT_REACH) < 0.2, `seated over the seat's middle (z ${sat.z.toFixed(2)})`);
  // Sitting down takes a while (not a snap): half a second in, the hips are still well above the seat.
  const early = down[Math.round(0.3 * 60)].hip;
  assert.ok(early.y > sat.y + 0.15, `already down at 0.3 s (${early.y.toFixed(2)} m)`);
  // Getting up keeps them on the seat at first, then up on their feet in front of it.
  assert.ok(up[Math.round(0.15 * 60)].hip.y < sat.y + 0.12, 'still on the seat as they start to get up');
  const stood = up.at(-1)!.hip;
  assert.ok(Math.abs(stood.y - stand.y) < 0.05 && Math.abs(stood.z - stand.z) < 0.1, `back on their feet where they stood (${stood.y.toFixed(2)}, ${stood.z.toFixed(2)} vs ${stand.y.toFixed(2)}, ${stand.z.toFixed(2)})`);
  clipSettings.enabled = true;
});

test('lying down on a bed from sitting on its edge, and getting up: on the mattress, the head behind (yaw 0 faces -z), smooth', async () => {
  await clipLibraryReady();
  const h = await Humanoid.create(randomAppearance('human', 11), { wardrobe: NAKED });
  const bed = 0.5;
  run(h, () => ({ move: 'sit', seat: bed }), 3);
  const lie = run(h, () => ({ move: 'sleep', seat: bed }), 3, 3);
  for (let i = 1; i < lie.length; i++) {
    const d = lie[i].head.distanceTo(lie[i - 1].head);
    assert.ok(d < 0.05, `the head jumps ${d.toFixed(3)} m at ${lie[i].t.toFixed(2)} s`);
  }
  // Lying down takes a while.
  assert.ok(lie[Math.round(0.3 * 60)].head.y > bed + 0.6, 'lies down at once');
  const { hip, head } = lie.at(-1)!;
  assert.ok(hip.y > bed && hip.y < bed + 0.3, `hips on the mattress (${hip.y.toFixed(2)} m on a ${bed} m bed)`);
  assert.ok(head.y > bed && head.y < bed + 0.35, `head on the pillow (${head.y.toFixed(2)} m)`);
  assert.ok(head.z - hip.z > 0.4, `head behind the hips: z ${head.z.toFixed(2)} vs ${hip.z.toFixed(2)}`);
  // Getting up: sit up on the edge, then stand.
  const rise = [...run(h, () => ({ move: 'sit', seat: bed }), 2.5, 6), ...run(h, () => ({ move: 'idle' }), 2.5, 8.5)];
  for (let i = 1; i < rise.length; i++) {
    const d = rise[i].head.distanceTo(rise[i - 1].head);
    assert.ok(d < 0.05, `getting up, the head jumps ${d.toFixed(3)} m at ${rise[i].t.toFixed(2)} s`);
  }
  assert.ok(rise.at(-1)!.head.y > 1.3, `on their feet (head at ${rise.at(-1)!.head.y.toFixed(2)} m)`);
});

test('seated and lying, the hands rest on the body (thighs, lap, belly) or the mattress, never up in the air, each character their own way', async () => {
  await clipLibraryReady();
  const ways = new Set<string>();
  for (const seed of [3, 7, 11, 19, 23, 31]) {
    const h = await Humanoid.create(randomAppearance('human', seed), { wardrobe: NAKED });
    run(h, () => ({ move: 'sit', seat: 0.46 }), 3);
    const hipL = at(h, 'upperleg01.L'), kneeL = at(h, 'lowerleg01.L'), hipR = at(h, 'upperleg01.R'), kneeR = at(h, 'lowerleg01.R');
    const way: string[] = [];
    for (const [s, hip, knee] of [['L', hipL, kneeL], ['R', hipR, kneeR]] as const) {
      const w = at(h, `wrist.${s}`);
      // Over the thighs, between the hips and the knees, a hand's height above them.
      const fwd = new THREE.Vector3().subVectors(knee, hip);
      const u = new THREE.Vector3().subVectors(w, hip).dot(fwd) / fwd.lengthSq();
      assert.ok(u > -0.2 && u < 1.15, `seed ${seed}: ${s} hand over the thigh or lap (u ${u.toFixed(2)})`);
      assert.ok(w.y > hip.y - 0.05 && w.y < Math.max(hip.y, knee.y) + 0.2, `seed ${seed}: ${s} hand rests (${w.y.toFixed(2)} m, hips ${hip.y.toFixed(2)})`);
      way.push(Math.abs(w.x - (hipL.x + hipR.x) / 2) < Math.abs(hip.x - (hipL.x + hipR.x) / 2) ? 'lap' : 'thigh');
    }
    ways.add(way.join());
    run(h, () => ({ move: 'sleep', seat: 0.5 }), 4, 3);
    const mid = at(h, 'upperleg01.L').add(at(h, 'upperleg01.R')).multiplyScalar(0.5);
    for (const s of ['L', 'R']) {
      const w = at(h, `wrist.${s}`);
      assert.ok(w.y < mid.y + 0.18, `seed ${seed}: lying, the ${s} hand rests (${w.y.toFixed(2)} m, hips ${mid.y.toFixed(2)})`);
    }
  }
  assert.ok(ways.size >= 2, `everyone rests their hands the same way (${[...ways].join(' / ')})`);
});
