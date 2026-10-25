import { test } from 'node:test';
import assert from 'node:assert/strict';
import { BUILDING_MAT_COUNT, buildingMesh, planTown } from '../src/index';

const town = planTown({ seed: 3, x: 500, z: 200, height: (x, z) => 20 + 3 * Math.sin(x / 60) + 2 * Math.cos(z / 45) });

test('building mesh: sound buffers for every kind, near and far', () => {
  const kinds = new Set<string>();
  for (const b of town.buildings) {
    for (const detail of [true, false]) {
      const m = buildingMesh(b, [500, 0, 200], detail);
      const n = m.position.length / 3;
      assert.equal(m.normal.length, n * 3);
      assert.equal(m.uv.length, n * 2);
      assert.equal(m.mat.length, n);
      assert.equal(m.tint.length, n * 3);
      assert.ok(m.index.length > 0 && m.index.length % 3 === 0);
      for (const i of m.index) assert.ok(i < n);
      for (let k = 0; k < n; k++) {
        assert.ok(Number.isFinite(m.position[k * 3]) && Number.isFinite(m.position[k * 3 + 1]), 'finite');
        assert.ok(Math.abs(Math.hypot(m.normal[k * 3], m.normal[k * 3 + 1], m.normal[k * 3 + 2]) - 1) < 1e-3, 'unit normal');
        assert.ok(m.mat[k] < BUILDING_MAT_COUNT);
        // Everything stands within reach of its footprint.
        const x = m.position[k * 3] + 500, z = m.position[k * 3 + 2] + 200;
        assert.ok(Math.hypot(x - b.cx, z - b.cz) < Math.hypot(b.hu, b.hv) + 8, `${b.kind} vertex far from its footprint`);
      }
      const tris = m.index.length / 3;
      assert.ok(tris < (detail ? 9000 : 2500), `${b.kind}: ${tris} triangles`);
    }
    kinds.add(b.kind);
  }
  assert.ok(kinds.has('temple'));
  assert.deepEqual(buildingMesh(town.buildings[5], [0, 0, 0]), buildingMesh(town.buildings[5], [0, 0, 0]), 'deterministic');
});

test('building mesh: the far version is much lighter', () => {
  let near = 0, far = 0;
  for (const b of town.buildings) { near += buildingMesh(b, [0, 0, 0]).index.length; far += buildingMesh(b, [0, 0, 0], false).index.length; }
  assert.ok(far < near * 0.45, `far ${far / 3} vs near ${near / 3} triangles`);
});
