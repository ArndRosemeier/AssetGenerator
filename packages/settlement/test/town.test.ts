import { test } from 'node:test';
import assert from 'node:assert/strict';
import { intersection, planTown, pointInPoly, shapeArea, strokePolylines, shapesToPolys, type SettlementSize, type TownSite, wallBlocks, wallMesh } from '../src/index';

/** Gently rolling ground, a river along z = 140 to the south-east of the market. */
const site = (seed: number, river = false): TownSite => ({
  seed, x: 1000, z: -500,
  height: (x, z) => 40 + 3 * Math.sin(x / 60) + 2 * Math.cos(z / 45),
  water: river ? (_x, z) => (Math.abs(z - (-500 + 140)) < 12 ? 1 : 0) : undefined,
});

test('settlement: the same site gives the same town', () => {
  assert.deepEqual(planTown(site(7)), planTown(site(7)));
  assert.notDeepEqual(planTown(site(7)).buildings.map((b) => b.cx), planTown(site(8)).buildings.map((b) => b.cx));
});

test('settlement: a small town has its houses, temple, hall, inn, smithy and well', () => {
  for (const seed of [1, 2, 3, 4, 5]) {
    const t0 = performance.now();
    const town = planTown(site(seed));
    const ms = performance.now() - t0;
    const kinds = new Set(town.buildings.map((b) => b.kind));
    assert.ok(town.buildings.length >= 50 && town.buildings.length <= 260, `seed ${seed}: ${town.buildings.length} buildings`);
    for (const k of ['house', 'inn', 'hall', 'smithy', 'temple']) assert.ok(kinds.has(k as never), `seed ${seed}: no ${k}`);
    assert.ok(town.fixtures.some((f) => f.kind === 'well'), `seed ${seed}: no well`);
    assert.ok(town.fixtures.some((f) => f.kind === 'anvil'), `seed ${seed}: no anvil`);
    assert.ok(ms < 1500, `seed ${seed}: planned in ${ms.toFixed(0)} ms`);
  }
});

test('settlement: buildings stand clear of each other, of the streets and of the market', () => {
  for (const [seed, size] of [[1, 'town'], [2, 'town'], [3, 'town'], [1, 'hamlet'], [2, 'village']] as const) {
    const town = planTown({ ...site(seed), size });
    const bs = town.buildings;
    for (let i = 0; i < bs.length; i++) for (let j = i + 1; j < bs.length; j++) {
      const a = intersection([bs[i].poly], [bs[j].poly]).reduce((s, x) => s + shapeArea(x), 0);
      assert.ok(a < 0.5, `seed ${seed}: buildings ${i} and ${j} overlap by ${a.toFixed(1)} m²`);
    }
    const ways = shapesToPolys(strokePolylines(town.streets.filter((s) => !s.closed).map((s) => s.pts), 1.5));
    for (const b of bs) {
      const a = intersection([b.poly], ways).reduce((s, x) => s + shapeArea(x), 0);
      assert.ok(a < 0.5, `seed ${seed}: building ${b.id} (${b.kind}) stands on a street (${a.toFixed(1)} m²)`);
      assert.ok(!pointInPoly(town.market, b.cx, b.cz), `seed ${seed}: building ${b.id} on the market`);
      assert.ok(b.floorY >= b.groundY, 'floor below the ground');
    }
    for (const f of town.fixtures) for (const b of bs) assert.ok(!pointInPoly(b.poly, f.x, f.z), `seed ${seed}: ${f.kind} inside building ${b.id}`);
  }
});

test('settlement: nothing is built in the water, and a mill stands by it', () => {
  let mills = 0;
  for (const seed of [1, 2, 3, 4]) {
    const town = planTown(site(seed, true));
    for (const b of town.buildings) for (let i = 0; i < b.poly.length; i += 2) assert.ok(Math.abs(b.poly[i + 1] - (-360)) >= 12, `seed ${seed}: building ${b.id} in the river`);
    if (town.buildings.some((b) => b.kind === 'mill')) mills++;
  }
  assert.ok(mills >= 2, `mills in ${mills} of 4 towns`);
});

test('settlement: one planner makes every size, from a hamlet round its green to a capital', () => {
  const kinds = (size: SettlementSize, seed: number) => {
    const t = planTown({ ...site(seed), size });
    return { t, has: new Set(t.buildings.map((b) => b.kind)), people: t.buildings.reduce((n, b) => n + b.household, 0) };
  };
  for (const seed of [1, 2]) {
    const hamlet = kinds('hamlet', seed), village = kinds('village', seed), town = kinds('town', seed);
    // A hamlet: a few cottages and farmsteads, no temple, inn or stalls; a well on its green.
    assert.ok(hamlet.t.buildings.length >= 5 && hamlet.t.buildings.length <= 20, `hamlet ${hamlet.t.buildings.length} buildings`);
    for (const k of ['temple', 'inn', 'hall', 'smithy', 'house']) assert.ok(!hamlet.has.has(k as never), `a hamlet with a ${k}`);
    assert.ok(hamlet.t.fixtures.some((f) => f.kind === 'well') && !hamlet.t.fixtures.some((f) => f.kind === 'stall'));
    assert.equal(hamlet.t.streets.filter((s) => s.kind === 'lane').length, 0);
    // A village: its temple, inn and smithy, but no moot hall; bigger than the hamlet, smaller than the town.
    for (const k of ['temple', 'inn', 'smithy']) assert.ok(village.has.has(k as never), `seed ${seed}: a village without a ${k}`);
    assert.ok(!village.has.has('hall'));
    assert.ok(hamlet.people < village.people && village.people < town.people, `${hamlet.people} < ${village.people} < ${town.people} people`);
    assert.ok(hamlet.t.radius < village.t.radius && village.t.radius < town.t.radius);
  }
  // The capital is prepared (plan B3): far bigger, more roads out, planned in well under a second.
  const t0 = performance.now(), capital = kinds('capital', 3), ms = performance.now() - t0;
  assert.ok(capital.t.radius >= 240 && capital.t.buildings.length > 500 && ms < 2000, `capital: ${capital.t.buildings.length} buildings in ${ms.toFixed(0)} ms`);
  assert.ok(capital.t.streets.filter((s) => s.kind === 'road').length >= 5);
});

test('settlement: a capital has a wall with a gate on every road, a seat of rule, quarters and more of each trade', () => {
  for (const seed of [3, 4]) {
    const t = planTown({ ...site(seed), size: 'capital' }), w = t.wall!;
    const roads = t.streets.filter((s) => s.kind === 'road');
    assert.ok(w && w.gates.length === roads.length, `seed ${seed}: ${w?.gates.length} gates for ${roads.length} roads`);
    assert.ok(w.towers.length >= w.gates.length * 2 + 6, `${w.towers.length} towers`);
    // The whole town is inside the wall, the farms outside it.
    const farmIds = new Set(t.farms.flatMap((f) => [f.house, f.barn, f.stable]));
    for (const b of t.buildings) {
      const inside = pointInPoly(w.ring, b.cx, b.cz), farm = farmIds.has(b.id);
      assert.equal(inside, !farm, `seed ${seed}: ${b.kind} ${b.id} ${inside ? 'inside' : 'outside'} the wall`);
    }
    for (const f of t.fields) assert.ok(!pointInPoly(w.ring, f.poly[0], f.poly[1]), 'no field inside the wall');
    // Its gates stand on the roads, its towers on the ring.
    for (const g of w.gates) assert.ok(Math.min(...roads.map((r) => nearest(r.pts, g.x, g.z))) < 1, 'a gate on its road');
    // The seat of rule: a great stone hall in its own grounds near the market.
    const seat = t.buildings.find((b) => b.trade === 'ruler')!;
    assert.ok(seat && seat.wall === 'stone' && seat.floors === 3 && seat.hu * seat.hv > 60, 'a seat of rule');
    assert.ok(t.seatGrounds && pointInPoly(t.seatGrounds.outer, seat.cx, seat.cz));
    assert.deepEqual(['crafts', 'seat', 'temple'].filter((k) => t.quarters!.some((q) => q.kind === k)), ['crafts', 'seat', 'temple']);
    const n = (k: string) => t.buildings.filter((b) => b.kind === k).length;
    assert.ok(n('inn') >= 2 && n('smithy') >= 2 && n('bakery') >= 2 && n('workshop') >= 12, `${n('inn')} inns, ${n('smithy')} smithies, ${n('bakery')} bakeries, ${n('workshop')} workshops`);
  }
  // Walkers come in through the gates only; the wall and towers stop them, and it is drawn.
  const t = planTown({ ...site(3), size: 'capital' }), w = t.wall!;
  for (const g of w.gates) {
    const ux = Math.cos(g.angle), uz = Math.sin(g.angle), sx = -uz, sz = ux;
    for (const d of [-4, 0, 4]) assert.ok(!wallBlocks(w, g.x + ux * d, g.z + uz * d, 0.4), 'through the gate');
    assert.ok(wallBlocks(w, g.x + sx * (g.half + w.towerHalf), g.z + sz * (g.half + w.towerHalf), 0.4), 'not through its towers');
  }
  const n2 = w.ring.length >> 1;
  for (let i = 0; i < n2; i += 7) {
    const x = w.ring[i * 2], z = w.ring[i * 2 + 1];
    if (w.gates.some((g) => Math.hypot(g.x - x, g.z - z) < g.half + w.towerHalf + 1)) continue;
    assert.ok(wallBlocks(w, x, z, 0.4), 'the wall is solid');
  }
  assert.ok(!wallBlocks(w, t.centre[0], t.centre[1], 0.4), 'the market is free');
  assert.equal(w.ringY.length, n2);
  const near = wallMesh(w, [0, 0, 0]), far = wallMesh(w, [0, 0, 0], false);
  assert.ok(far.index.length > 0 && near.index.length > far.index.length, 'merlons near only');
  assert.equal(near.position.length / 3, near.tint.length / 3);
  assert.ok(near.position.every(Number.isFinite));
  const half = wallMesh(w, [0, 0, 0], true, (x) => x < t.centre[0]);
  assert.ok(half.index.length > 0 && half.index.length < near.index.length, 'picked by cell');
  // A town keeps no wall and no seat (and plans just as before).
  const town = planTown(site(3));
  assert.ok(!town.wall && !town.quarters && !town.buildings.some((b) => b.trade === 'ruler'));
});

const nearest = (pts: number[], x: number, z: number) => { let m = Infinity; for (let i = 0; i < pts.length; i += 2) m = Math.min(m, Math.hypot(pts[i] - x, pts[i + 1] - z)); return m; };

test('settlement: a waystation is an inn and a stable facing each other across the road through it', () => {
  for (const seed of [1, 2, 3, 4, 5, 6, 7, 8]) {
    const t = planTown({ ...site(seed), size: 'waystation', farmland: false });
    assert.deepEqual(t.buildings.map((b) => b.kind).sort(), ['inn', 'stable'], `seed ${seed}`);
    assert.equal(t.streets.filter((s) => s.kind === 'road').length, 2);
    const road = shapesToPolys(strokePolylines(t.streets.filter((s) => s.kind === 'road').map((s) => s.pts), 3, 'round', 'round'));
    for (const b of t.buildings) {
      assert.ok(!intersection([b.poly], road).some((x) => shapeArea(x) > 0.5), `seed ${seed}: the ${b.kind} stands off the road`);
      // Its door faces the road, a few steps from it.
      const d = Math.hypot(b.door[0] - t.centre[0], b.door[1] - t.centre[1]);
      assert.ok(d < 16, `seed ${seed}: the ${b.kind}'s door is by the road through the middle (${d.toFixed(1)} m)`);
    }
    const [inn, stable] = [t.buildings.find((b) => b.kind === 'inn')!, t.buildings.find((b) => b.kind === 'stable')!];
    assert.ok(inn.household > 0 && inn.floors >= 2);
    assert.ok(!intersection([inn.poly], [stable.poly]).some((x) => shapeArea(x) > 0.01), 'they do not overlap');
  }
});
