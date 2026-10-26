import { test } from 'node:test';
import assert from 'node:assert/strict';
import { BIRD_STRIDE, birdMesh, packBird, type BirdPose } from '../src/index';

test('birds: one small body, wings marked by side and span, every triangle on a vertex', () => {
  const m = birdMesh();
  const n = m.positions.length / 3;
  assert.equal(m.parts.length, n * 2);
  assert.ok(n < 80 && m.indices.length / 3 < 120, `${n} vertices, ${m.indices.length / 3} triangles`);
  for (const i of m.indices) assert.ok(i < n);
  let left = 0, right = 0;
  for (let v = 0; v < n; v++) {
    const side = m.parts[v * 2], span = m.parts[v * 2 + 1];
    if (side < 0) { left++; assert.ok(m.positions[v * 3] < 0); }
    if (side > 0) { right++; assert.ok(m.positions[v * 3] > 0); }
    assert.ok(span >= 0 && span <= 1);
    // One unit long, beak forward (+z).
    assert.ok(Math.abs(m.positions[v * 3 + 2]) <= 0.65);
  }
  assert.ok(left > 0 && left === right, 'two wings alike');
});

test('birds: a pose packs relative to the origin, its heading turned to face +z', () => {
  const place = new Float32Array(BIRD_STRIDE * 2), turn = new Float32Array(BIRD_STRIDE * 2), look = new Float32Array(BIRD_STRIDE * 2);
  const p: BirdPose = { x: -32000.5, y: 80, z: 32001, heading: 0, pitch: 0.2, bank: -0.1, size: 0.2, wing: 0.5, fold: 1, r: 0.1, g: 0.2, b: 0.3 };
  packBird(p, { x: -32000, y: 79, z: 32000 }, place, turn, look, 1);
  assert.deepEqual([...place.slice(4, 7)], [-0.5, 1, 1]);
  // Heading 0 is +x: turned a quarter about y from +z.
  assert.ok(Math.abs(place[7] - Math.PI / 2) < 1e-6);
  assert.deepEqual([...turn.slice(4)].map((v) => +v.toFixed(3)), [0.2, -0.1, 0.2, 0.5]);
  assert.deepEqual([...look.slice(4)].map((v) => +v.toFixed(3)), [0.1, 0.2, 0.3, 1]);
});
