import { test } from 'node:test';
import assert from 'node:assert/strict';
import { BUILDING_MAT_COUNT, buildingMesh, doorLeaves, HATCH_SHAFT, hatchLidMesh, hatchSides, signPlace, chimneyStack, roofAt, houseShape, INSIDE_LIGHT, interiorBlocked, interiorMesh, interiorSolids, planInterior, planTown, reachable, roomPath, storeyAt, WALL_THICK } from '../src/index';

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

test('interior: a hall (where fighting is taught) has weapon racks, a practice post with its master\'s place, a bench, and no bed or family table downstairs', () => {
  const homes = town.buildings.filter((b) => b.kind === 'house' || b.kind === 'cottage');
  let full = 0, far = 0;
  for (const b of homes) {
    assert.ok(!planInterior(b).fixtures.some((f) => f.kind === 'rack' || f.kind === 'pell'), `plain ${b.kind} #${b.id}`);
    const p = planInterior(b, { hall: true }), reach = reachable(p, 0), down = p.fixtures.filter((f) => f.storey === 0);
    assert.ok(!down.some((f) => f.kind === 'bed' || f.kind === 'table'), `${b.kind} #${b.id}: no bed or table in the hall`);
    const racks = down.filter((f) => f.kind === 'rack').length, pell = down.find((f) => f.kind === 'pell'), drill = p.spots.find((s) => s.kind === 'drill');
    assert.ok(racks >= 1 && pell && drill, `${b.kind} #${b.id}: ${racks} racks, pell ${!!pell}, master ${!!drill}`);
    if (racks >= 2) full++;
    assert.ok(reach(drill!.a, drill!.b), `${b.kind} #${b.id}: the master's place can be walked to`);
    // A few steps in from the door, not where one first stands.
    const [ea, eb] = p.storeys[0].entry;
    // ...and not hidden behind the post from there.
    const along = (pell!.a - ea) * (drill!.b - eb) - (pell!.b - eb) * (drill!.a - ea), off = Math.abs(along) / Math.hypot(pell!.a - ea, pell!.b - eb);
    if (Math.hypot(drill!.a - ea, drill!.b - eb) >= 1.8 && off >= 0.5) far++;
    for (const s of p.spots) if (s.storey === 0) assert.ok([0, 0.4, 0.7, 1.0].some((d) => Array.from({ length: 16 }, (_, k) => (k / 16) * 2 * Math.PI).some((t) => reach(s.a + d * Math.cos(t), s.b + d * Math.sin(t)))), `${b.kind} #${b.id}: ${s.kind} reached`);
    assert.ok(interiorMesh(p, b, [b.cx, 0, b.cz]).position.length > 0);
  }
  assert.ok(full >= homes.length * 0.7, `${full} of ${homes.length} halls have two racks or more`);
  assert.ok(far >= homes.length * 0.9, `${far} of ${homes.length} masters stand 1.8 m or more in from the door, clear of the post`);
});

test('building: a sign over the door adds a shield on the front wall; none without asking', () => {
  for (const b of town.buildings.filter((x) => x.kind === 'house').slice(0, 6)) {
    const plain = buildingMesh(b, [b.cx, 0, b.cz]), signed = buildingMesh(b, [b.cx, 0, b.cz], true, { sign: [150, 50, 36] });
    assert.ok(signed.index.length > plain.index.length, `house #${b.id}`);
    assert.equal(buildingMesh(b, [b.cx, 0, b.cz], true, { open: true, sign: [150, 50, 36] }).index.length - buildingMesh(b, [b.cx, 0, b.cz], true, { open: true }).index.length, signed.index.length - plain.index.length);
  }
});

test('building: the sign sits on the front wall beside the door, under the roof and clear of the windows and shutters, in hamlets, villages and towns', () => {
  let flat = 0, all = 0;
  for (const size of ['hamlet', 'village', 'town'] as const) {
    for (let seed = 1; seed <= 10; seed++) {
      for (const b of planTown({ seed, x: 0, z: 0, height: () => 20, size }).buildings.filter((x) => x.kind === 'house' || x.kind === 'cottage')) {
        const S = houseShape(b), p = signPlace(b, S), st = S.storeys[0], w = st.walls.find((x) => x.id === 0)!;
        assert.ok(p, `${size} ${seed} ${b.kind} #${b.id}: a sign`);
        all++;
        // Under the roof's underside at the wall, and under the storey's top beam.
        // The eave's edge: out past the wall it reaches (0.6 m thatch, 0.42 m else) and falls by the pitch.
        const under = (S.storeys.length === 1 && b.ridgeAlongU ? Math.min(st.y1, S.top) - (b.cover === 'thatch' ? 0.6 : 0.42) * b.pitch - (b.cover === 'thatch' ? 0.38 : 0.14) : st.y1) + 1e-6;
        assert.ok(p!.y + p!.r <= under, `${size} ${seed} ${b.kind} #${b.id}: top ${(p!.y + p!.r).toFixed(2)} over ${under.toFixed(2)}`);
        if (!p!.flat) continue;
        flat++;
        const len = Math.hypot(w.a1 - w.a0, w.b1 - w.b0), s = ((p!.a - w.a0) * (w.a1 - w.a0) + (p!.b - w.b0) * (w.b1 - w.b0)) / len;
        for (const o of w.opens) {
          const pad = o.door ? 0.1 : (o.s1 - o.s0) / 2 + 0.05;
          const hit = s + p!.r > o.s0 - pad && s - p!.r < o.s1 + pad && p!.y + p!.r > o.t0 && p!.y - p!.r < o.t1;
          assert.ok(!hit, `${size} ${seed} ${b.kind} #${b.id}: clear of the ${o.door ? 'door' : 'window'}`);
        }
      }
    }
  }
  assert.ok(flat >= all * 0.85, `${flat} of ${all} flat on the wall`);
});

test('chimney: every stack stands on the roof, within the walls, and rises past the ridge', () => {
  let n = 0;
  for (const b of town.buildings) {
    const S = houseShape(b), k = chimneyStack(b, S);
    if (!k) continue;
    n++;
    const at = `${b.kind} #${b.id}`;
    assert.ok(Math.abs(k.a) + k.half <= b.hu && k.b - k.half >= S.front && k.b + k.half <= S.back, `${at}: within the walls`);
    assert.ok(k.y1 > S.top + (b.ridgeAlongU ? (S.back - S.front) / 2 : b.hu) * b.pitch + 0.5, `${at}: past the ridge`);
    // Just outside each corner of the stack, the drawn roof lies above the stack's foot.
    const m = buildingMesh(b, [0, 0, 0], false), ux = Math.cos(b.angle), uz = Math.sin(b.angle);
    const world = (a: number, y: number, bb: number) => [b.cx + ux * a + b.vx * bb, b.floorY + y, b.cz + uz * a + b.vz * bb];
    for (const da of [-1, 1]) for (const db of [-1, 1]) {
      const a = k.a + da * (k.half + 0.1), bb = k.b + db * (k.half + 0.1);
      assert.ok(roofAt(b, S, a, bb) > k.y0, `${at}: the roof over the stack's foot`);
      const p = world(a, k.y0, bb), q = world(a, k.y0 + 30, bb);
      let hit = false;
      for (let t = 0; t < m.index.length && !hit; t += 3) {
        const v = [0, 1, 2].map((j) => [m.position[m.index[t + j] * 3], m.position[m.index[t + j] * 3 + 1], m.position[m.index[t + j] * 3 + 2]]);
        hit = segHits(p, q, v[0], v[1], v[2]);
      }
      assert.ok(hit, `${at}: roof drawn above the stack's foot (corner ${da}, ${db})`);
    }
  }
  assert.ok(n > 20);
});

test('interior: a way in from the door to every spot on the ground floor, round the fixtures, and out again', () => {
  let ways = 0;
  for (const b of town.buildings) {
    const p = planInterior(b), st = p.storeys[0], door: [number, number] = [0, st.b0 - 0.3];
    for (const s of p.spots) {
      if (s.storey !== 0) continue;
      const w = roomPath(p, door, [s.a, s.b]);
      assert.ok(w, `${b.kind} #${b.id}: a way to the ${s.kind} spot`);
      assert.deepEqual([w[0], w[1], w[w.length - 2], w[w.length - 1]], [door[0], door[1], s.a, s.b]);
      // Between the floor beside each end, nothing in the way (the last leg steps onto a seat).
      for (let k = 2; k + 4 < w.length; k += 2) {
        for (let t = 0; t <= 1; t += 0.1) {
          assert.ok(!interiorBlocked(p, w[k] + (w[k + 2] - w[k]) * t, w[k + 1] + (w[k + 3] - w[k + 1]) * t, 0.29, 0, true), `${b.kind} #${b.id}: the way to ${s.kind} runs through something`);
        }
      }
      const back = roomPath(p, [s.a, s.b], door);
      assert.ok(back && back.length >= 4);
      ways++;
    }
  }
  assert.ok(ways > 50, `${ways} ways`);
});

test('interior: a hatch\'s lid drawn apart leaves a shaft with a ladder under the floor, and its own mesh lies where it was', () => {
  const b = town.buildings.find((x) => x.kind === 'house')!;
  const p = planInterior(b, { hatch: true }), at: [number, number, number] = [b.cx, 0, b.cz];
  const whole = interiorMesh(p, b, at), apart = interiorMesh(p, b, at, { lid: false }), lid = hatchLidMesh(p, b, at)!;
  const f = p.fixtures.find((x) => x.kind === 'hatch')!, ux = Math.cos(b.angle), uz = Math.sin(b.angle), floor = b.floorY + p.storeys[0].y;
  // The shaft: under the floor only within the hatch's rectangle, down to its depth (the whole house has nothing there).
  const under = (m: typeof whole) => {
    let n = 0, deep = 0;
    for (let i = 0; i < m.position.length / 3; i++) {
      const dx = m.position[i * 3], dz = m.position[i * 3 + 2], y = m.position[i * 3 + 1] - floor;
      if (y > -0.05) continue;
      const a = dx * ux + dz * uz, bb = dx * b.vx + dz * b.vz;
      if (Math.abs(a - f.a) <= f.w / 2 + 1e-6 && Math.abs(bb - f.b) <= f.d / 2 + 1e-6) { n++; deep = Math.min(deep, y); }
    }
    return { n, deep };
  };
  assert.equal(under(whole).n, 0);
  const shaft = under(apart);
  assert.ok(shaft.n > 40 && shaft.deep <= -HATCH_SHAFT + 1e-3 && shaft.deep > -HATCH_SHAFT - 0.05, `a shaft with its ladder (${shaft.n} vertices, ${shaft.deep.toFixed(2)} m)`);
  // Drawn open with that hole, the plinth's top leaves the hatch open (no face over its middle at the floor).
  const outside = buildingMesh(b, at, true, { open: true, hole: { a0: f.a - f.w / 2, a1: f.a + f.w / 2, b0: f.b - f.d / 2, b1: f.b + f.d / 2 } });
  const mid = [b.cx + ux * f.a + b.vx * f.b, b.cz + uz * f.a + b.vz * f.b];
  const covers = (m: typeof whole) => {
    for (let t = 0; t < m.index.length; t += 3) {
      const v = [0, 1, 2].map((i) => m.index[t + i] * 3), P = v.map((i) => [m.position[i] + at[0], m.position[i + 1], m.position[i + 2] + at[2]]);
      if (P.some((q) => Math.abs(q[1] - b.floorY) > 0.01)) continue;
      const s = (p: number[], q: number[], r: number[]) => (q[0] - p[0]) * (r[2] - p[2]) - (q[2] - p[2]) * (r[0] - p[0]);
      const c = [mid[0], 0, mid[1]], d = [s(P[0], P[1], c), s(P[1], P[2], c), s(P[2], P[0], c)];
      if (d.every((x) => x >= 0) || d.every((x) => x <= 0)) return true;
    }
    return false;
  };
  assert.ok(covers(buildingMesh(b, at, true, { open: true })), 'the plinth tops the floor');
  assert.ok(!covers(outside), 'the plinth leaves the hatch open');
  // The ladder's side has room to stand before it; the hinge is another side.
  const { ladder, hinge } = hatchSides(p, f);
  assert.ok(!interiorBlocked(p, f.a + ladder[0] * (f.w / 2 + 0.5), f.b + ladder[1] * (f.d / 2 + 0.5), 0.3, f.storey, true));
  assert.ok(hinge[0] !== ladder[0] || hinge[1] !== ladder[1]);
  // Every lid vertex is within the hatch's rectangle, at most a few centimetres over the floor, and lit as inside.
  for (let i = 0; i < lid.position.length / 3; i++) {
    const dx = lid.position[i * 3], dz = lid.position[i * 3 + 2], y = lid.position[i * 3 + 1] - b.floorY - p.storeys[0].y;
    const a = dx * ux + dz * uz, bb = dx * b.vx + dz * b.vz;
    assert.ok(Math.abs(a - f.a) <= f.w / 2 + 1e-6 && Math.abs(bb - f.b) <= f.d / 2 + 1e-6 && y > -1e-6 && y < 0.1);
    assert.ok(lid.mat[i] >= INSIDE_LIGHT);
  }
  assert.equal(hatchLidMesh(planInterior(b), b, at), null);
});

test('interior: the front door\'s leaves drawn apart shut the doorway, and opened stand inside the house', () => {
  let seen = 0;
  for (const b of town.buildings.slice(0, 40)) {
    const p = planInterior(b), at: [number, number, number] = [b.cx, 0, b.cz];
    const leaves = doorLeaves(p, b, at), whole = interiorMesh(p, b, at), apart = interiorMesh(p, b, at, { doors: false });
    if (!leaves.length) continue;
    seen++;
    assert.equal(leaves.length, p.doorW > 0.8 ? 2 : 1, `${b.kind} #${b.id}`);
    assert.ok(apart.index.length < whole.index.length, 'the open leaves left out');
    const S = houseShape(b), front = S.storeys[0].walls.find((w) => w.id === 0)!;
    for (const l of leaves) {
      // Shut: every vertex in the front wall's doorway (between the jambs, inside the wall's thickness).
      const ux = Math.cos(b.angle), uz = Math.sin(b.angle);
      const local = (x: number, z: number) => [(x + at[0] - b.cx) * ux + (z + at[2] - b.cz) * uz, (x + at[0] - b.cx) * b.vx + (z + at[2] - b.cz) * b.vz];
      for (let i = 0; i < l.mesh.position.length / 3; i++) {
        const [a, bb] = local(l.mesh.position[i * 3], l.mesh.position[i * 3 + 2]);
        assert.ok(Math.abs(a) <= p.doorW + 1e-6 && bb >= front.b0 && bb <= front.b0 + WALL_THICK, `${b.kind} #${b.id}: shut in the doorway`);
      }
      // Opened: the leaf's far edge turned about the hinge lies inside the house.
      const [hx, , hz] = l.hinge;
      let far = 0, fx = 0, fz = 0;
      for (let i = 0; i < l.mesh.position.length / 3; i++) {
        const dx = l.mesh.position[i * 3] - hx, dz = l.mesh.position[i * 3 + 2] - hz, d = Math.hypot(dx, dz);
        if (d > far) { far = d; fx = dx; fz = dz; }
      }
      const c = Math.cos(l.open), s = Math.sin(l.open), ox = fx * c + fz * s, oz = -fx * s + fz * c;
      const [, ob] = local(hx + ox, hz + oz);
      assert.ok(ob > front.b0 + 0.3, `${b.kind} #${b.id}: opens inward (${ob.toFixed(2)} vs ${front.b0.toFixed(2)})`);
    }
  }
  assert.ok(seen > 10);
});
