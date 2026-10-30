import { test } from 'node:test';
import assert from 'node:assert/strict';
import { planTown, harbourMesh, pierDist, intersection, shapeArea, distToPoly, type TownSite } from '../src/index';

/** A coast along z = 0 (the sea to the south, +z), the land rising gently inland; the town's middle 60 m in. */
const height = (x: number, z: number) => -z * 0.06 + 1.2 * Math.sin(x / 70);
const water = (x: number, z: number) => Math.max(0, -height(x, z));
const site = (seed: number, size: TownSite['size'] = 'village'): TownSite => ({
  seed, x: 0, z: -60, size, height, water, harbour: { x: 0, z: 0, dx: 0, dz: 1 },
});

test('harbour: a town by the sea gets a quay on the waterline, piers out to deep water and berths', () => {
  for (const seed of [1, 2, 3]) for (const size of ['village', 'town'] as const) {
    const t = planTown(site(seed, size)), h = t.harbour;
    assert.ok(h, `seed ${seed} ${size}: no harbour`);
    assert.ok(h.edge.length >= 16, 'a quay of some length');
    for (let i = 0; i < h.edge.length; i += 2) assert.ok(Math.abs(height(h.edge[i], h.edge[i + 1])) < 1, 'the quay front is on the waterline');
    assert.ok(h.quayY >= 1.4);
    assert.ok(h.piers.length >= 1);
    for (const p of h.piers) assert.ok(water(p.x1, p.z1) >= 3 || Math.hypot(p.x1 - p.x0, p.z1 - p.z0) >= 70, 'a pier reaches deep water');
    assert.ok(h.berths.length >= 1, 'a ship can moor');
    for (const b of h.berths) {
      assert.ok(b.depth >= 2);
      // A ship there keeps off every pier's deck.
      for (const p of h.piers) assert.ok(pierDist(p, b.x, b.z) > 2.5);
    }
    // Nothing is built on the quay; the harbour's trades front it.
    for (const b of t.buildings) assert.ok(intersection([b.poly], [h.quay]).reduce((s, x) => s + shapeArea(x), 0) < 0.5, `seed ${seed}: building ${b.id} on the quay`);
    const front = (trade: string) => t.buildings.filter((b) => b.trade === trade).map((b) => distToPoly(h.quay, b.door[0], b.door[1]));
    // (A village's few houses may stand back from a quay that runs along a wandering shore: the nearest then.)
    const by = size === 'town' ? 6 : 30;
    assert.ok(front('harbourmaster').length === 1 && front('harbourmaster')[0] < by, 'the harbour master by the quay');
    if (size === 'town') assert.ok(front('warehouse').length >= 1, 'a warehouse');
    assert.ok(front('innkeeper').some((d) => d < by), 'the tavern on the quay');
    const kinds = new Set(t.fixtures.map((f) => f.kind));
    for (const k of ['crane', 'cargo']) assert.ok(kinds.has(k as never), `seed ${seed}: no ${k}`);
    const crane = t.fixtures.find((f) => f.kind === 'crane')!;
    assert.ok(['warehouse', 'harbourmaster'].includes(t.buildings[crane.building]?.trade), 'a crane is worked from a warehouse');
  }
});

test('harbour: the same site gives the same harbour; its mesh is whole', () => {
  assert.deepEqual(planTown(site(4)).harbour, planTown(site(4)).harbour);
  const h = planTown(site(4)).harbour!;
  const m = harbourMesh(h, height, [0, 0, -100]);
  assert.ok(m.index.length > 300 && m.index.length % 3 === 0);
  for (const v of m.position) assert.ok(Number.isFinite(v));
  assert.ok(Math.max(...m.index) < m.position.length / 3);
});

test('harbour: no shore near the site, no harbour', () => {
  const t = planTown({ ...site(1), water: () => 0 });
  assert.equal(t.harbour, undefined);
});
