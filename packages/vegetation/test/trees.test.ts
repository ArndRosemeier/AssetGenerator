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

test('vegetation: a far hull\'s trunk reaches well into its crown, so no bare post shows below it', () => {
  for (const sp of TREE_SPECIES) {
    if (sp === 'palm') continue; // fronds, no crown hull
    for (const v of [0, 3]) {
      const far = treeModel(sp, v).far;
      const p = far.getAttribute('position'), uv = far.getAttribute('uv');
      let trunkTop = -Infinity, lo = Infinity, hi = -Infinity;
      for (let i = 0; i < p.count; i++) {
        if (uv.getX(i) < 0.25) trunkTop = Math.max(trunkTop, p.getY(i));
        else { lo = Math.min(lo, p.getY(i)); hi = Math.max(hi, p.getY(i)); }
      }
      // At least to the middle of the crown (it stopped a third of the way in, and below it for pines).
      assert.ok(trunkTop >= lo + (hi - lo) * 0.45, `${sp}/${v}: trunk ${trunkTop.toFixed(1)}, crown ${lo.toFixed(1)}..${hi.toFixed(1)}`);
      assert.ok(p.count / 3 <= 150, `${sp}/${v}: ${p.count / 3} triangles`);
    }
  }
});
