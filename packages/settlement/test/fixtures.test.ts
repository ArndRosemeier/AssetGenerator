import { test } from 'node:test';
import assert from 'node:assert/strict';
import { BENCH_SEAT, buildingEntrance, buildingMesh, fixtureBlocks, fixtureMesh, planTown, type FixtureKind } from '../src/index';

const site = (seed: number) => ({ seed, x: 0, z: 0, radius: 120, height: (x: number, z: number) => 10 + Math.sin(x * 0.02) * 2 + Math.cos(z * 0.03) });

test('fixtures: every kind a town plans is drawn on its ground, near and far, and the solid ones stop a walker', () => {
  const t = planTown(site(3)), h = site(3).height;
  const kinds = new Set<FixtureKind>(t.fixtures.map((f) => f.kind));
  for (const k of ['well', 'stall', 'bench', 'table', 'barrel', 'anvil', 'oven', 'woodpile', 'grave'] as FixtureKind[]) assert.ok(kinds.has(k), `the town has a ${k}`);
  for (const k of kinds) {
    if (k === 'field' || k === 'paddock') continue;
    const f = t.fixtures.find((x) => x.kind === k)!;
    const m = fixtureMesh([f], h, [0, 0, 0]), far = fixtureMesh([f], h, [0, 0, 0], false);
    assert.ok(m.index.length > 0 && far.index.length > 0 && far.index.length <= m.index.length, `${k} drawn`);
    let lo = Infinity;
    for (let i = 1; i < m.position.length; i += 3) lo = Math.min(lo, m.position[i]);
    assert.ok(Math.abs(lo - h(f.x, f.z)) < 0.05, `${k} stands on the ground (${(lo - h(f.x, f.z)).toFixed(2)})`);
  }
  const well = t.fixtures.find((f) => f.kind === 'well')!, bench = t.fixtures.find((f) => f.kind === 'bench')!;
  assert.ok(fixtureBlocks(well, well.x, well.z, 0.3) && !fixtureBlocks(well, well.x + 3, well.z, 0.3));
  assert.ok(!fixtureBlocks(bench, bench.x, bench.z, 0.3), 'a bench is sat on, not walked round');
  // The bench's seat is where a sitter's hips go.
  const m = fixtureMesh([bench], h, [0, 0, 0]);
  let hi = -Infinity;
  for (let i = 1; i < m.position.length; i += 3) hi = Math.max(hi, m.position[i]);
  assert.ok(Math.abs(hi - h(bench.x, bench.z) - BENCH_SEAT) < 1e-3);
  // Picked by cell.
  const all = fixtureMesh(t.fixtures, h, [0, 0, 0]), half = fixtureMesh(t.fixtures, h, [0, 0, 0], true, (x) => x < 0);
  assert.ok(half.index.length > 0 && half.index.length < all.index.length);
});

test('fixtures: the seat of rule has towers at its front corners (solid) and a broad landing', () => {
  const t = planTown({ ...site(3), radius: 260, size: 'capital' });
  const seat = t.buildings.find((b) => b.trade === 'ruler')!;
  const e = buildingEntrance(seat);
  assert.equal(e.posts.length, 2, 'two towers');
  assert.ok(e.posts.every((p) => p.top > seat.floors * seat.floorH + 3), 'higher than the roof');
  assert.ok(e.floors[0].u1 - e.floors[0].u0 > 6, 'a broad landing');
  const plain = { ...seat, trade: 'x' };
  assert.ok(buildingMesh(seat, [0, 0, 0]).index.length > buildingMesh(plain, [0, 0, 0]).index.length);
});
