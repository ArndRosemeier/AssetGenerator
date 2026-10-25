import { test } from 'node:test';
import assert from 'node:assert/strict';
import { Rng } from '@futuremagic/core';
import { anatomyOf, fleshOf, grow, PLANS, speciesName } from '../src/index';

test('creatures: a species grows the same from the same seed, every plan fits the shared skeleton', () => {
  const a = grow(new Rng(7), 'hunter', 0.3, 'a'), b = grow(new Rng(7), 'hunter', 0.3, 'a');
  assert.deepEqual(a, b);
  for (const [i, plan] of PLANS.entries()) {
    const sp = grow(new Rng(100 + i), 'hunter', 0.2, `p${i}`, { plan });
    assert.equal(sp.plan, plan);
    const an = anatomyOf(sp);
    assert.ok(an.bones.length > 0 && an.bones.length <= 96, `${plan}: ${an.bones.length} bones`);
    assert.ok(speciesName(sp).length > 0);
  }
});

test('creatures: an eight-legged chitin hunter meshes into a closed skinned body', () => {
  const sp = grow(new Rng(3), 'hunter', 0.1, 'spider', { plan: 'octopod', integument: 'chitin' });
  const an = anatomyOf(sp);
  const f = fleshOf(an, sp, 40);
  const n = f.positions.length / 3;
  assert.ok(n > 300 && f.indices.length > n, `${n} vertices`);
  assert.equal(f.skinIndex.length, n * 4);
  for (let i = 0; i < f.skinIndex.length; i++) assert.ok(f.skinIndex[i] < an.bones.length);
  for (let v = 0; v < n; v++) {
    const w = f.skinWeight[v * 4] + f.skinWeight[v * 4 + 1] + f.skinWeight[v * 4 + 2] + f.skinWeight[v * 4 + 3];
    assert.ok(Math.abs(w - 1) < 1e-3);
  }
});
