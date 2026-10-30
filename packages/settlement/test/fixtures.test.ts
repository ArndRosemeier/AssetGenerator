import { test } from 'node:test';
import { floatOf } from '@futuremagic/core';
import assert from 'node:assert/strict';
import { BENCH_SEAT, Footprints, buildingEntrance, buildingMesh, distToPoly, fixtureBlocks, fixtureClear, fixtureMesh, fixtureSight, fixtureStand, planTown, pointInPoly, wayRound, type FixtureKind } from '../src/index';

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
    assert.ok(lo <= h(f.x, f.z) + 1e-3 && lo > h(f.x, f.z) - 0.5, `${k} stands on the ground (${(lo - h(f.x, f.z)).toFixed(2)})`);
    if (k !== 'garden') assert.ok(floatOf(h, m.position) <= 0, `no edge of the ${k} floats (${floatOf(h, m.position).toFixed(3)})`);
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

test('fixtures: none stands in a wall, nor its users (the inn table drinkers stood in its front wall)', () => {
  for (const size of ['hamlet', 'town', 'capital'] as const) for (const seed of [1, 2, 3]) {
    const t = planTown({ ...site(seed), size });
    const polys = t.buildings.map((b) => b.poly);
    for (const f of t.fixtures) assert.ok(fixtureClear(f, polys, pointInPoly, distToPoly), `${size} ${seed}: the ${f.kind} at ${f.x.toFixed(1)}, ${f.z.toFixed(1)} keeps off the walls`);
    const inn = t.buildings.find((b) => b.kind === 'inn');
    if (inn) assert.equal(t.fixtures.filter((f) => f.kind === 'table' && f.building === inn.id).length, 2, `${size} ${seed}: the inn keeps both its tables (moved off the wall)`);
    for (const f of t.fixtures) {
      const [x, z] = fixtureStand(f);
      for (const p of polys) assert.ok(!pointInPoly(p, x, z) && distToPoly(p, x, z) >= 0.45, `${size} ${seed}: one at the ${f.kind} stands clear`);
    }
  }
});

test('fixtures: a way round the houses, never through one', () => {
  const t = planTown(site(3));
  const foot = new Footprints(t.buildings.map((b) => b.poly));
  // From the front of one row to the back of it: straight through the houses.
  const b = t.buildings.find((x) => x.kind === 'house' && x.attached) ?? t.buildings[0];
  const [fx, fz] = b.door, bx = b.cx + b.vx * (b.hv + 2), bz = b.cz + b.vz * (b.hv + 2);
  const way = wayRound([fx, fz, bx, bz], foot);
  assert.deepEqual(way.slice(0, 2), [fx, fz]);
  assert.deepEqual(way.slice(-2), [bx, bz]);
  assert.ok(way.length > 4, 'it turns');
  for (let k = 2; k < way.length; k += 2) {
    const n = Math.ceil(Math.hypot(way[k] - way[k - 2], way[k + 1] - way[k - 1]) / 0.1);
    for (let i = 0; i <= n; i++) {
      const x = way[k - 2] + ((way[k] - way[k - 2]) * i) / n, z = way[k - 1] + ((way[k + 1] - way[k - 1]) * i) / n;
      assert.ok(!foot.polys.some((p) => pointInPoly(p, x, z)), `step ${k / 2} keeps out of the houses`);
    }
  }
  // A clear way stays as it is.
  assert.deepEqual(wayRound([fx, fz, fx - b.vx * 2, fz - b.vz * 2], foot), [fx, fz, fx - b.vx * 2, fz - b.vz * 2]);
});

test('fixtures: a long way through a house (a walk out to someone far off) is gone round in pieces, quickly', () => {
  const t = planTown(site(3));
  const foot = new Footprints(t.buildings.map((b) => b.poly));
  const b = t.buildings.find((x) => x.kind === 'house' && x.attached) ?? t.buildings[0];
  const [fx, fz] = b.door, bx = b.cx + b.vx * (b.hv + 600), bz = b.cz + b.vz * (b.hv + 600);
  // One grid over the whole 600 m took a fifth of a second (seconds for longer ways, on the main thread).
  const t0 = performance.now(), way = wayRound([fx, fz, bx, bz], foot), ms = performance.now() - t0;
  assert.ok(ms < 100, `${ms.toFixed(0)} ms`);
  assert.deepEqual(way.slice(0, 2), [fx, fz]);
  assert.deepEqual(way.slice(-2), [bx, bz]);
  for (let k = 2; k < way.length; k += 2) {
    const n = Math.ceil(Math.hypot(way[k] - way[k - 2], way[k + 1] - way[k - 1]) / 0.1);
    for (let i = 0; i <= n; i++) {
      const x = way[k - 2] + ((way[k] - way[k - 2]) * i) / n, z = way[k - 1] + ((way[k + 1] - way[k - 1]) * i) / n;
      assert.ok(!foot.polys.some((p) => pointInPoly(p, x, z)), `step ${k / 2} keeps out of the houses`);
    }
  }
});

test('fixtures: a stall\'s awning and a well\'s roof stand in the eye\'s way, a bench does not', () => {
  const t = planTown(site(3)), h = site(3).height;
  const stall = t.fixtures.find((f) => f.kind === 'stall')!, well = t.fixtures.find((f) => f.kind === 'well')!, bench = t.fixtures.find((f) => f.kind === 'bench')!;
  const g = (f: { x: number; z: number }) => h(f.x, f.z);
  // Under the awning's middle (over the buyers' side of the counter) at 2.1 m: in it; 1.5 m up there: clear of it.
  const ax = stall.x - Math.cos(stall.yaw) * 0.5, az = stall.z - Math.sin(stall.yaw) * 0.5;
  assert.ok(fixtureSight(stall, g(stall), ax, g(stall) + 2.1, az) < 0, 'in the awning');
  assert.ok(fixtureSight(stall, g(stall), ax, g(stall) + 1.5, az) > 0.2, 'under it');
  assert.ok(fixtureSight(stall, g(stall), stall.x, g(stall) + 5, stall.z) > 2.5, 'well over it');
  assert.ok(fixtureSight(well, g(well), well.x, g(well) + 2.3, well.z) < 0, 'in the well\'s roof');
  assert.equal(fixtureSight(bench, g(bench), bench.x, g(bench) + 0.5, bench.z), Infinity);
});
