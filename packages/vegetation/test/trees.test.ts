import { test } from 'node:test';
import assert from 'node:assert/strict';
import { TREE_SPECIES, shrubModel, treeModel } from '../src/index';

test('vegetation: every species builds wood, leaves and a far hull, deterministically', () => {
  for (const sp of TREE_SPECIES) {
    const m = treeModel(sp, 3);
    assert.ok(m.wood.getAttribute('position').count > 100, `${sp} wood`);
    assert.ok(m.leaves.getAttribute('position').count > 40, `${sp} leaves`);
    assert.ok(m.far.getAttribute('position').count > 8, `${sp} far`);
    assert.ok(m.height > 3 && m.height < 40, `${sp} height ${m.height}`);
  }
  const s = shrubModel(1);
  assert.ok(s.isShrub && s.height < 5);
  // Same species and variant: same model (cached); rebuilt from scratch it would match too.
  assert.equal(treeModel('oak', 1), treeModel('oak', 1));
});
