import { test } from 'node:test';
import assert from 'node:assert/strict';
import { BUILDING_MAT_COUNT, CROPS, farmlandReach, intersection, planTown, pointInPoly, polyCentroid, propMesh, shapeArea, strokePolylines, shapesToPolys, type TownSite } from '../src/index';

const site = (seed: number, radius: number, river = false): TownSite => ({
  seed, x: 1000, z: -500, radius,
  height: (x, z) => 40 + 3 * Math.sin(x / 60) + 2 * Math.cos(z / 45),
  water: river ? (_x, z) => (Math.abs(z - (-500 + 170)) < 14 ? 1 : 0) : undefined,
});
const area = (polys: number[][]) => polys.reduce((s, p) => s + shapeArea({ outer: p, holes: [] }), 0);

test('farmland: a bigger town tills more land and has more farms', () => {
  const hamlet = planTown(site(3, 45)), town = planTown(site(3, 140));
  assert.ok(farmlandReach(140) > farmlandReach(45));
  assert.ok(town.farms.length > hamlet.farms.length, `farms ${hamlet.farms.length} vs ${town.farms.length}`);
  assert.ok(area(town.fields.map((f) => f.poly)) > area(hamlet.fields.map((f) => f.poly)) * 1.5, 'field area');
  assert.ok(hamlet.farms.length >= 2 && hamlet.fields.length >= 20, `a hamlet has ${hamlet.farms.length} farms, ${hamlet.fields.length} fields`);
  assert.equal(planTown({ ...site(3, 45), farmland: false }).fields.length, 0, 'farmland can be left out');
});

test('farmland: every farm has its house, barn, stable, paddock, fields and the work spots of a farm', () => {
  for (const seed of [1, 2, 3]) {
    const plan = planTown(site(seed, 72));
    assert.ok(plan.farms.length >= 2, `seed ${seed}: ${plan.farms.length} farms`);
    for (const fm of plan.farms) {
      const h = plan.buildings[fm.house];
      assert.equal(h.kind, 'farmhouse');
      assert.equal(h.trade, 'farmer');
      assert.ok(h.household >= 3);
      assert.equal(plan.buildings[fm.barn].kind, 'barn');
      assert.equal(plan.buildings[fm.stable].kind, 'stable');
      const pd = plan.paddocks[fm.paddock];
      assert.ok(pd.animals >= 2 && pd.animals <= 4);
      assert.ok(pointInPoly(pd.poly, pd.gate[0] + Math.cos(pd.gate[2]) * 2, pd.gate[1] + Math.sin(pd.gate[2]) * 2), 'the gate opens into the paddock');
      assert.ok(fm.fields.length >= 3, `farm ${fm.id}: ${fm.fields.length} fields`);
      const work = plan.fixtures.filter((f) => f.building === fm.house);
      for (const k of ['field', 'paddock', 'trough', 'hayrack']) assert.ok(work.some((f) => f.kind === k), `seed ${seed} farm ${fm.id}: no ${k}`);
      for (const f of work.filter((f) => f.kind === 'field')) {
        const field = plan.fields.find((x) => pointInPoly(x.poly, f.x, f.z));
        assert.ok(field && field.farm === fm.id && field.crop !== 'meadow', 'field work lies in a tilled field of the farm');
      }
      // A track runs from a road into the yard.
      const [yx, yz] = polyCentroid(fm.yard);
      assert.ok(plan.streets.some((s) => s.kind === 'path' && Math.hypot(s.pts[s.pts.length - 2] - yx, s.pts[s.pts.length - 1] - yz) < 3), 'a track into the yard');
    }
    for (const f of plan.fields) assert.ok(CROPS.includes(f.crop));
  }
});

test('farmland: fields keep off the town, the roads, the buildings, each other and the water', () => {
  for (const seed of [1, 2]) {
    const plan = planTown(site(seed, 72, true));
    const roads = shapesToPolys(strokePolylines(plan.streets.filter((s) => s.kind === 'road').map((s) => s.pts), 2.5));
    const tilled = plan.fields.filter((f) => f.paddock < 0);
    for (const f of tilled) {
      const on = (polys: number[][]) => intersection([f.poly], polys).reduce((s, x) => s + shapeArea(x), 0);
      assert.ok(on([plan.outline]) < 1, `seed ${seed}: field ${f.id} in the town`);
      assert.ok(on(roads) < 1, `seed ${seed}: field ${f.id} on a road`);
      assert.ok(on(plan.buildings.map((b) => b.poly)) < 0.5, `seed ${seed}: field ${f.id} under a building`);
      for (let i = 0; i < f.poly.length; i += 2) assert.ok(Math.abs(f.poly[i + 1] - (-330)) >= 14, `seed ${seed}: field ${f.id} in the river`);
    }
    for (let i = 0; i < tilled.length; i++) for (let j = i + 1; j < tilled.length; j++) {
      assert.ok(intersection([tilled[i].poly], [tilled[j].poly]).reduce((s, x) => s + shapeArea(x), 0) < 0.5, `seed ${seed}: fields ${i} and ${j} overlap`);
    }
  }
});

test('farmland: fences and haystacks mesh soundly, the far ones lighter', () => {
  const plan = planTown(site(2, 72));
  assert.ok(plan.props.some((p) => p.kind === 'fence') && plan.props.some((p) => p.kind === 'haystack'));
  for (const p of plan.props) {
    const near = propMesh(p, [1000, 0, -500]), far = propMesh(p, [1000, 0, -500], false);
    const n = near.position.length / 3;
    assert.ok(near.index.length > 0 && near.index.length % 3 === 0);
    for (const i of near.index) assert.ok(i < n);
    for (let k = 0; k < n; k++) assert.ok(Math.abs(Math.hypot(near.normal[k * 3], near.normal[k * 3 + 1], near.normal[k * 3 + 2]) - 1) < 1e-3 && near.mat[k] < BUILDING_MAT_COUNT);
    assert.ok(far.index.length < near.index.length);
  }
});
