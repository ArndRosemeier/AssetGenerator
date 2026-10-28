import { test } from 'node:test';
import assert from 'node:assert/strict';
import { ROCK_SHAPES, rockModel } from '../src/index';

test('rocks: every shape stands on its flat foot at y 0, normals point out, sizes as its shape', () => {
  for (const shape of ROCK_SHAPES) for (let seed = 1; seed <= 6; seed++) {
    const r = rockModel(shape, seed, 2);
    const n = r.positions.length / 3;
    let lo = Infinity, out = 0;
    for (let v = 0; v < n; v++) {
      lo = Math.min(lo, r.positions[v * 3 + 1]);
      const px = r.positions[v * 3], py = r.positions[v * 3 + 1] - r.height / 2, pz = r.positions[v * 3 + 2];
      if (px * r.normals[v * 3] + py * r.normals[v * 3 + 1] + pz * r.normals[v * 3 + 2] > 0) out++;
    }
    assert.ok(lo > -0.2 && lo <= 0, `${shape} ${seed}: foot at ${lo}`);
    assert.ok(out > n * 0.9, `${shape}: normals out (${out} of ${n})`);
    assert.ok(r.foot > 0.3 && r.foot < 1.6, `${shape}: foot ${r.foot}`);
    if (shape === 'spire') assert.ok(r.height > r.foot * 1.4, 'a spire stands tall');
    if (shape === 'slab') assert.ok(r.height < r.foot, 'a slab lies low');
    for (const c of r.colors) assert.ok(c >= 0.25 && c <= 1);
  }
});

test('rocks: one seed is one rock at every detail; seeds differ', () => {
  const a = rockModel('block', 9, 1), b = rockModel('block', 9, 3), c = rockModel('block', 10, 1);
  assert.ok(Math.abs(a.height - b.height) < 0.12 && Math.abs(a.foot - b.foot) < 0.15, `${a.height} ${b.height} ${a.foot} ${b.foot}`);
  assert.ok(b.indices.length === a.indices.length * 16);
  assert.notDeepEqual(a.positions, c.positions);
  assert.deepEqual(rockModel('block', 9, 1).positions, a.positions);
});
