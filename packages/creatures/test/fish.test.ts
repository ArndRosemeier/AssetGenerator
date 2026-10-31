import { test } from 'node:test';
import assert from 'node:assert/strict';
import { FISH_STRIDE, fishMesh, packFish, type FishPose } from '../src/index';

test('fish: one small body, one unit long snout forward, each vertex marked by how far back it sits', () => {
  const m = fishMesh();
  const n = m.positions.length / 3;
  assert.equal(m.back.length, n);
  assert.ok(n < 60 && m.indices.length / 3 < 90, `${n} vertices, ${m.indices.length / 3} triangles`);
  for (const i of m.indices) assert.ok(i < n);
  let tail = 0;
  for (let v = 0; v < n; v++) {
    const z = m.positions[v * 3 + 2], b = m.back[v];
    assert.ok(Math.abs(z) <= 0.5 + 1e-6 && b >= 0 && b <= 1 + 1e-6);
    // Further back, more of the sweep: the snout holds still, the tail's tip sweeps most.
    if (z > 0.45) assert.ok(b < 0.1);
    if (z < -0.45) { tail++; assert.ok(b > 0.9); assert.ok(Math.abs(m.positions[v * 3]) < 1e-6, 'the tail fin stands upright'); }
  }
  assert.ok(tail >= 2, 'a forked tail');
});

test('fish: a pose packs relative to the origin, heading turned to face +z, phase and sweep carried', () => {
  const place = new Float32Array(FISH_STRIDE * 2), turn = new Float32Array(FISH_STRIDE * 2), look = new Float32Array(FISH_STRIDE * 2);
  const p: FishPose = { x: 100.5, y: -8, z: -40, heading: Math.PI / 2, pitch: 0.1, roll: 0.3, size: 0.3, phase: 2, sweep: 0.15, r: 0.1, g: 0.2, b: 0.3 };
  packFish(p, { x: 100, y: -10, z: -41 }, place, turn, look, 1);
  assert.deepEqual([...place.slice(4, 7)], [0.5, 2, 1]);
  assert.ok(Math.abs(place[7]) < 1e-6, 'heading +z: no turn');
  assert.deepEqual([...turn.slice(4)].map((v) => +v.toFixed(3)), [0.1, 0.3, 0.3, 2]);
  assert.deepEqual([...look.slice(4)].map((v) => +v.toFixed(3)), [0.1, 0.2, 0.3, 0.15]);
});
