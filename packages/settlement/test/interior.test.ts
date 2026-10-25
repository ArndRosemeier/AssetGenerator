import { test } from 'node:test';
import assert from 'node:assert/strict';
import { BUILDING_MAT_COUNT, interiorMesh, planInterior, planTown, reachable } from '../src/index';

const towns = [3, 4, 5, 6, 7, 8].map((seed) => planTown({ seed, x: 500, z: 200, height: () => 20 }));
const town = { buildings: towns.flatMap((t) => t.buildings) };

test('interior: every building is furnished for what it is, and every spot can be walked to from the door', () => {
  const want: Record<string, string[]> = { inn: ['counter', 'table', 'hearth'], smithy: ['forge', 'anvil'], bakery: ['oven'], temple: ['basin', 'bench'] };
  const uses: Record<string, string[]> = { inn: ['serve', 'drink'], smithy: ['smith', 'stoke'], bakery: ['bake'], temple: ['pray', 'tend'], house: ['sit'] };
  const seen = new Set<string>();
  for (const b of town.buildings) {
    const p = planInterior(b);
    assert.ok(p.ha > 1 && p.hb > 1 && p.height >= 2.4);
    for (const k of want[b.kind] ?? []) assert.ok(p.fixtures.some((f) => f.kind === k), `${b.kind} has a ${k}`);
    for (const f of p.fixtures) assert.ok(Math.abs(f.a) + f.w / 2 <= p.ha + 1e-6 && Math.abs(f.b) + f.d / 2 <= p.hb + 1e-6, `${b.kind}: ${f.kind} inside`);
    for (const k of uses[b.kind] ?? []) assert.ok(p.spots.some((s) => s.kind === k), `${b.kind} #${b.id} can be used to ${k}`);
    const reach = reachable(p);
    for (const s of p.spots) {
      // A spot on a bench or bed is reached from the floor beside it (within a metre).
      const near = [0, 0.4, 0.7, 1.0].some((d) => Array.from({ length: 16 }, (_, k) => (k / 16) * 2 * Math.PI).some((t) => reach(s.a + d * Math.cos(t), s.b + d * Math.sin(t))));
      assert.ok(near, `${b.kind} #${b.id}: ${s.kind} spot at ${s.a.toFixed(1)}, ${s.b.toFixed(1)} cannot be reached`);
    }
    seen.add(b.kind);
  }
  for (const k of ['inn', 'smithy']) assert.ok(seen.has(k), `the town has a ${k}`);
});

test('interior mesh: sound buffers, inside the footprint', () => {
  for (const b of town.buildings.filter((x) => ['inn', 'smithy', 'temple', 'house'].includes(x.kind)).slice(0, 8)) {
    const p = planInterior(b);
    const m = interiorMesh(p, b, { x: 0, y: -100, z: 0 }, [0, 0, 0]);
    const n = m.position.length / 3;
    assert.equal(m.normal.length, n * 3);
    assert.equal(m.uv.length, n * 2);
    assert.equal(m.tint.length, n * 3);
    for (const i of m.index) assert.ok(i < n);
    for (let k = 0; k < n; k++) {
      assert.ok(m.mat[k] < BUILDING_MAT_COUNT);
      assert.ok(Math.hypot(m.position[k * 3], m.position[k * 3 + 2]) < Math.hypot(p.ha, p.hb) + 0.5, 'within the room');
      assert.ok(m.position[k * 3 + 1] >= -100 - 1e-4 && m.position[k * 3 + 1] <= -100 + p.height + 1e-4, 'between floor and ceiling');
    }
    assert.ok(m.index.length / 3 < 6000, `${b.kind}: ${m.index.length / 3} triangles`);
  }
});

test('interior: a hatch down to a cellar lies on free floor one can walk to, in every kind of building', () => {
  for (const b of town.buildings) {
    const p = planInterior(b, { hatch: true }), h = p.fixtures.filter((f) => f.kind === 'hatch');
    assert.equal(h.length, 1, `${b.kind} #${b.id}: one hatch`);
    assert.ok(reachable(p)(h[0].a, h[0].b), `${b.kind} #${b.id}: the hatch can be walked to`);
    assert.ok(Math.abs(h[0].a) + 0.45 <= p.ha + 1e-6 && Math.abs(h[0].b) + 0.45 <= p.hb + 1e-6, 'inside');
    assert.equal(planInterior(b).fixtures.some((f) => f.kind === 'hatch'), false, 'only when asked');
  }
});
