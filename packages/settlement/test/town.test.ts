import { test } from 'node:test';
import assert from 'node:assert/strict';
import { intersection, planTown, pointInPoly, shapeArea, strokePolylines, shapesToPolys, type TownSite } from '../src/index';

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
  for (const seed of [1, 2, 3]) {
    const town = planTown(site(seed));
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
