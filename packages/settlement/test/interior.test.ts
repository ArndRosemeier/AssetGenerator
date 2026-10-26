import { test } from 'node:test';
import assert from 'node:assert/strict';
import { BUILDING_MAT_COUNT, buildingMesh, houseShape, INSIDE_LIGHT, interiorBlocked, interiorMesh, interiorSolids, planInterior, planTown, reachable, storeyAt, WALL_THICK } from '../src/index';

const towns = [3, 4, 5, 6, 7, 8].map((seed) => planTown({ seed, x: 500, z: 200, height: () => 20 }));
const town = { buildings: towns.flatMap((t) => t.buildings) };

test('interior: every building is furnished for what it is, and every spot can be walked to from where one comes in', () => {
  const want: Record<string, string[]> = { inn: ['counter', 'table', 'hearth'], smithy: ['forge', 'anvil'], bakery: ['oven'], temple: ['basin', 'bench'] };
  const uses: Record<string, string[]> = { inn: ['serve', 'drink'], smithy: ['smith', 'stoke'], bakery: ['bake'], temple: ['pray', 'tend'], house: ['sit'] };
  const seen = new Set<string>();
  for (const b of town.buildings) {
    const p = planInterior(b);
    assert.ok(p.ha > 1 && p.hb > 1 && p.height >= 2.3);
    for (const k of want[b.kind] ?? []) assert.ok(p.fixtures.some((f) => f.kind === k), `${b.kind} has a ${k}`);
    for (const f of p.fixtures) {
      const st = p.storeys[f.storey];
      assert.ok(f.a - f.w / 2 >= st.a0 - 1e-6 && f.a + f.w / 2 <= st.a1 + 1e-6 && f.b - f.d / 2 >= st.b0 - 1e-6 && f.b + f.d / 2 <= st.b1 + 1e-6, `${b.kind}: ${f.kind} inside storey ${f.storey}`);
    }
    for (const k of uses[b.kind] ?? []) assert.ok(p.spots.some((s) => s.kind === k), `${b.kind} #${b.id} can be used to ${k}`);
    for (const s of p.spots) {
      const reach = reachable(p, s.storey);
      // A spot on a bench or bed is reached from the floor beside it (within a metre).
      const near = [0, 0.4, 0.7, 1.0].some((d) => Array.from({ length: 16 }, (_, k) => (k / 16) * 2 * Math.PI).some((t) => reach(s.a + d * Math.cos(t), s.b + d * Math.sin(t))));
      assert.ok(near, `${b.kind} #${b.id}: ${s.kind} spot at ${s.a.toFixed(1)}, ${s.b.toFixed(1)} on storey ${s.storey} cannot be reached`);
    }
    seen.add(b.kind);
  }
  for (const k of ['inn', 'smithy']) assert.ok(seen.has(k), `the town has a ${k}`);
});

test('interior: as many storeys inside as outside, stairs up to each, the hearth under the chimney', () => {
  let stairs = 0;
  for (const b of town.buildings) {
    const S = houseShape(b), p = planInterior(b);
    assert.equal(p.storeys.length, S.storeys.length, `${b.kind} #${b.id}: storeys`);
    for (let k = 0; k + 1 < p.storeys.length; k++) {
      const s = p.stairs.find((x) => x.storey === k);
      assert.ok(s, `${b.kind} #${b.id} (${(2 * b.hu).toFixed(1)} x ${(2 * b.hv).toFixed(1)}): stairs up from storey ${k}`);
      stairs++;
      // The flight climbs the storey, in steps one walks.
      assert.ok(Math.abs(s.steps * s.riser - (p.storeys[k + 1].y - p.storeys[k].y)) < 1e-6);
      assert.ok(s.riser <= 0.25 && s.tread >= 0.17);
      // Its foot is walked to, and off its top the floor above is.
      assert.ok(reachable(p, k)(s.a - s.da * 0.5, s.b - s.db * 0.5), `${b.kind} #${b.id}: the stair's foot`);
      const up = p.storeys[k + 1];
      assert.ok(reachable(p, k + 1)(up.entry[0], up.entry[1]), `${b.kind} #${b.id}: off the top`);
    }
    if (S.chimney) {
      const c = S.chimney, fire = p.fixtures.find((f) => f.storey === 0 && (f.kind === 'hearth' || f.kind === 'forge' || f.kind === 'oven'));
      if (b.kind !== 'temple') assert.ok(fire, `${b.kind} #${b.id}: a fire`);
      if (fire) assert.ok(Math.abs(fire.a - c.a) < fire.w / 2 + 0.05 && Math.abs(fire.b - c.b) < fire.d / 2 + 0.05, `${b.kind} #${b.id}: the ${fire.kind} under the chimney`);
      for (let k = 1; k < p.storeys.length; k++) assert.ok(p.fixtures.some((f) => f.storey === k && f.kind === 'flue'), `${b.kind} #${b.id}: the breast on storey ${k}`);
    }
  }
  assert.ok(stairs > 20, `${stairs} flights`);
});

test('interior: a body walks up the stairs and stands upstairs, walled in by the solids', () => {
  const b = town.buildings.find((x) => x.floors > 1 && x.kind === 'house')!, p = planInterior(b), s = p.stairs[0], solids = interiorSolids(p);
  const top = (a: number, bb: number, y: number) => {
    let h = -Infinity;
    for (const q of solids) if (a > q.a0 && a < q.a1 && bb > q.b0 && bb < q.b1 && q.y1 <= y + 0.45) h = Math.max(h, q.y1);
    return h;
  };
  // Climbing: each step a little higher, never more than a walker's step.
  let y = p.storeys[0].y;
  for (let x = -0.33; x < s.steps * s.tread + 0.5; x += 0.1) {
    const h = top(s.a + s.da * x, s.b + s.db * x, y);
    assert.ok(h - y < 0.45 && h >= y - 0.5, `at ${x.toFixed(1)} m: ${h.toFixed(2)} from ${y.toFixed(2)}`);
    y = h;
  }
  assert.ok(Math.abs(y - p.storeys[1].y) < 1e-6, 'up on the next floor');
  assert.equal(storeyAt(p, y), 1);
  // The rails keep one from walking into the hole from the side.
  const well = p.fixtures.find((f) => f.kind === 'well' && f.storey === 1)!;
  assert.ok(p.fixtures.some((f) => f.kind === 'rail' && f.storey === 1));
  assert.ok(!interiorBlocked(p, well.a, well.b, 0.3, 1), 'walked through on the stairs');
  assert.ok(interiorBlocked(p, well.a, well.b, 0.3, 1, true), 'no standing in the hole');
});

test('interior mesh: sound buffers, inside the building, the windows open, daylight on every inside face', () => {
  for (const b of town.buildings.filter((x) => ['inn', 'smithy', 'temple', 'house', 'barn'].includes(x.kind)).slice(0, 12)) {
    const p = planInterior(b), S = houseShape(b);
    const m = interiorMesh(p, b, [b.cx, 0, b.cz]);
    const n = m.position.length / 3;
    assert.equal(m.normal.length, n * 3);
    assert.equal(m.uv.length, n * 2);
    assert.equal(m.tint.length, n * 3);
    for (const i of m.index) assert.ok(i < n);
    for (let k = 0; k < n; k++) {
      assert.ok(m.mat[k] % INSIDE_LIGHT < BUILDING_MAT_COUNT && m.mat[k] >= INSIDE_LIGHT, 'a material and a daylight level');
      assert.ok(Math.hypot(m.position[k * 3], m.position[k * 3 + 2]) < Math.hypot(b.hu, b.hv) + 1, 'within the building');
      assert.ok(m.position[k * 3 + 1] >= b.floorY - 1e-3 && m.position[k * 3 + 1] <= b.floorY + S.top + 0.01, 'between floor and roof');
    }
    assert.ok(m.index.length / 3 < 12000, `${b.kind}: ${m.index.length / 3} triangles`);
    // No inside face covers a window: a ray from the room out through each one's middle meets nothing.
    const ux = Math.cos(b.angle), uz = Math.sin(b.angle);
    const tri = (i: number) => [0, 1, 2].map((j) => { const v = m.index[i + j]; const x = m.position[v * 3], y = m.position[v * 3 + 1], z = m.position[v * 3 + 2]; return [x * ux + z * uz, y - b.floorY, x * b.vx + z * b.vz]; });
    S.storeys.forEach((st) => {
      for (const w of st.walls) for (const q of w.opens) {
        const len = Math.hypot(w.a1 - w.a0, w.b1 - w.b0), da = (w.a1 - w.a0) / len, db = (w.b1 - w.b0) / len, s = (q.s0 + q.s1) / 2, t = st.y0 + (q.t0 + q.t1) / 2;
        const pa = w.a0 + da * s, pb = w.b0 + db * s;
        for (let i = 0; i < m.index.length; i += 3) {
          const [A, B, C] = tri(i);
          // Hits the segment from 0.5 m inside to the outer face, at the opening's middle?
          if (segHits([pa - db * 0.5, t, pb + da * 0.5], [pa, t, pb], A, B, C)) assert.fail(`${b.kind} #${b.id}: something inside covers a ${q.door ? 'door' : 'window'}`);
        }
      }
    });
  }
});

test('open building: no door leaf in its doorway, otherwise as shut', () => {
  for (const b of town.buildings.slice(0, 10)) {
    const shut = buildingMesh(b, [0, 0, 0]), open = buildingMesh(b, [0, 0, 0], true, { open: true });
    assert.equal(shut.index.length - open.index.length, 6 * houseShape(b).storeys[0].walls.find((w) => w.id === 0)!.opens.filter((q) => q.door).length, 'one quad less per door');
  }
  // Nothing of the outside lies flat at the ground floor's height inside the walls (the plinth's top
  // would fight the floor boards for the same depth).
  for (const b of town.buildings.filter((_, i) => i % 3 === 0)) {
    const m = buildingMesh(b, [0, 0, 0], true, { open: true }), y = b.floorY + planInterior(b).storeys[0].y;
    const ux = Math.cos(b.angle), uz = Math.sin(b.angle);
    for (let t = 0; t < m.index.length; t += 3) {
      const c = [0, 1, 2].map((k) => (m.position[m.index[t] * 3 + k] + m.position[m.index[t + 1] * 3 + k] + m.position[m.index[t + 2] * 3 + k]) / 3);
      const a = (c[0] - b.cx) * ux + (c[2] - b.cz) * uz, bb = (c[0] - b.cx) * b.vx + (c[2] - b.cz) * b.vz;
      if (m.normal[m.index[t] * 3 + 1] > 0.9 && Math.abs(a) < b.hu - 0.4 && Math.abs(bb) < b.hv - 0.4)
        assert.ok(Math.abs(c[1] - y) > 0.02, `${b.kind} #${b.id}: an outside face at the floor`);
    }
  }
});

function segHits(p: number[], q: number[], A: number[], B: number[], C: number[]): boolean {
  const d = [q[0] - p[0], q[1] - p[1], q[2] - p[2]];
  const e1 = [B[0] - A[0], B[1] - A[1], B[2] - A[2]], e2 = [C[0] - A[0], C[1] - A[1], C[2] - A[2]];
  const h = [d[1] * e2[2] - d[2] * e2[1], d[2] * e2[0] - d[0] * e2[2], d[0] * e2[1] - d[1] * e2[0]];
  const det = e1[0] * h[0] + e1[1] * h[1] + e1[2] * h[2];
  if (Math.abs(det) < 1e-9) return false;
  const f = 1 / det, s = [p[0] - A[0], p[1] - A[1], p[2] - A[2]];
  const u = f * (s[0] * h[0] + s[1] * h[1] + s[2] * h[2]);
  if (u < 0 || u > 1) return false;
  const qq = [s[1] * e1[2] - s[2] * e1[1], s[2] * e1[0] - s[0] * e1[2], s[0] * e1[1] - s[1] * e1[0]];
  const v = f * (d[0] * qq[0] + d[1] * qq[1] + d[2] * qq[2]);
  if (v < 0 || u + v > 1) return false;
  const t = f * (e2[0] * qq[0] + e2[1] * qq[1] + e2[2] * qq[2]);
  return t > 1e-4 && t < 1 - 1e-4;
}

void WALL_THICK;

test('interior: a hatch down to a cellar lies on free floor one can walk to, in every kind of building', () => {
  for (const b of town.buildings.filter((_, i) => i % 2 === 0)) {
    const p = planInterior(b, { hatch: true }), h = p.fixtures.filter((f) => f.kind === 'hatch');
    assert.equal(h.length, 1, `${b.kind} #${b.id}: one hatch`);
    assert.ok(reachable(p)(h[0].a, h[0].b), `${b.kind} #${b.id}: the hatch can be walked to`);
    assert.ok(Math.abs(h[0].a) + 0.45 <= p.ha + 1e-6 && Math.abs(h[0].b) + 0.45 <= p.hb + 1e-6, 'inside');
    assert.equal(planInterior(b).fixtures.some((f) => f.kind === 'hatch'), false, 'only when asked');
  }
});
