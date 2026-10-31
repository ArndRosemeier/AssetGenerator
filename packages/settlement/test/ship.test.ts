import { test } from 'node:test';
import assert from 'node:assert/strict';
import { planShip, shipMesh, shipFloor, shipFloors, hullHalf, shipWall, gangplankMesh, shipLadders, shipFixtures, shipHold, shipInside, shipRoom } from '../src/index';

test('ship: a sailing ship has castles fore and aft, masts with yards, a hatch, and decks to walk on', () => {
  for (const seed of [1, 2, 3, 4]) {
    const p = planShip(seed, 'ship');
    assert.ok(p.length >= 20 && p.length <= 34, `${p.length} m`);
    assert.ok(p.aft && p.fore && p.hatch);
    assert.ok(p.masts.length >= 2 && p.masts.every((m) => m.top > m.foot + 10 && m.yards.length >= 1));
    // The main deck amidships, the castles over it, nothing over the side or in the hatch.
    assert.equal(shipFloor(p, -p.length * 0.1, 0), p.deckY);
    assert.equal(shipFloor(p, -p.length * 0.45, 0), p.aft.y);
    assert.equal(shipFloor(p, p.length * 0.42, 0), p.fore.y);
    assert.equal(shipFloor(p, p.length * 0.15, p.beam), null);
    assert.ok(shipFloor(p, (p.hatch.a0 + p.hatch.a1) / 2, 0)! > p.deckY, 'the hatch grating, a step up');
    // The hull is widest amidships and fine at the stem; it reaches below the water.
    assert.ok(hullHalf(p, 0, p.deckY) > hullHalf(p, p.length * 0.45, p.deckY));
    assert.ok(hullHalf(p, 0, -p.draft * 0.5) > 0);
  }
});

test('ship: a fishing boat is small and open, one mast; the same seed gives the same ship', () => {
  const b = planShip(5, 'boat');
  assert.ok(b.length >= 6.5 && b.length <= 9.5 && !b.aft && !b.fore && !b.hatch && b.masts.length === 1);
  assert.deepEqual(planShip(7, 'ship'), planShip(7, 'ship'));
});

test('ship: its mesh is whole, in the given frame, sails set or furled', () => {
  for (const kind of ['ship', 'boat'] as const) {
    const p = planShip(3, kind);
    const furled = shipMesh(p, 100, 200, 0, 1, 0, [100, 0, 200], 'furled');
    const set = shipMesh(p, 100, 200, 0, 1, 0, [100, 0, 200], 'set');
    for (const m of [furled, set]) {
      assert.ok(m.index.length > 300 && m.index.length % 3 === 0);
      assert.ok(m.position.every(Number.isFinite) && m.normal.every(Number.isFinite));
      for (const i of m.index) assert.ok(i < m.position.length / 3);
      // Heading along +z: its length lies along z, round the given middle (origin taken off).
      let za = Infinity, zb = -Infinity, xa = Infinity, xb = -Infinity;
      for (let i = 0; i < m.position.length; i += 3) { xa = Math.min(xa, m.position[i]); xb = Math.max(xb, m.position[i]); za = Math.min(za, m.position[i + 2]); zb = Math.max(zb, m.position[i + 2]); }
      assert.ok(zb - za > p.length * 0.95 && zb - za < p.length * 1.5, `length ${zb - za}`);
      assert.ok(xb - xa < p.beam * 3.5);
    }
    assert.ok(set.index.length > furled.index.length, 'set sails are cloth, not bundles');
  }
});

test('ship: every face is wound to face its normal, the deck where it narrows to a point at the bow too', () => {
  for (const seed of [1, 2, 3]) {
    const p = planShip(seed, 'ship', seed === 1 ? 22.72 : undefined), m = shipMesh(p, 0, 0, 1, 0, 0, [0, 0, 0]);
    const P = m.position, N = m.normal;
    let wrong = 0;
    for (let k = 0; k < m.index.length; k += 3) {
      const [a, b, c] = [m.index[k] * 3, m.index[k + 1] * 3, m.index[k + 2] * 3];
      const e1 = [P[b] - P[a], P[b + 1] - P[a + 1], P[b + 2] - P[a + 2]], e2 = [P[c] - P[a], P[c + 1] - P[a + 1], P[c + 2] - P[a + 2]];
      const n = [e1[1] * e2[2] - e1[2] * e2[1], e1[2] * e2[0] - e1[0] * e2[2], e1[0] * e2[1] - e1[1] * e2[0]], len = Math.hypot(...n);
      if (len < 1e-6) continue;
      if ((n[0] * N[a] + n[1] * N[a + 1] + n[2] * N[a + 2]) / len < -0.05) wrong++;
    }
    assert.equal(wrong, 0, `seed ${seed}: ${wrong} faces turned away from their normal (unseen from the side they face)`);
  }
});

test('ship: the lower deck\'s end bulkheads meet its lining all the way up (the hull flares: no sliver of the sea)', () => {
  const p = planShip(1, 'ship', 22.72), m = shipMesh(p, 0, 0, 1, 0, 0, [0, 0, 0]), h = p.hold!;
  // Heading +x from the origin: a is x, b is z, y is height. Every lining corner at an end has a bulkhead corner by it.
  for (const [a, nx] of [[h.a0, 1], [h.a1, -1]] as const) {
    const at = (want: (i: number) => boolean) => { const o: number[][] = []; for (let i = 0; i < m.position.length; i += 3) if (Math.abs(m.position[i] - a) < 1e-3 && m.position[i + 1] > h.y - 1e-3 && m.position[i + 1] < p.deckY && want(i)) o.push([m.position[i + 1], Math.abs(m.position[i + 2])]); return o; };
    const wall = at((i) => Math.abs(m.normal[i] - nx) < 1e-3), lining = at((i) => Math.abs(m.normal[i + 2]) > 0.99);
    assert.ok(lining.length > 0 && wall.length > 0);
    for (const [y, b] of lining) assert.ok(wall.some(([wy, wb]) => Math.abs(wy - y) < 1e-3 && Math.abs(wb - b) < 1e-3), `a lining corner at ${y.toFixed(2)} m, ${b.toFixed(2)} out, has no bulkhead corner`);
  }
});

test('ship: a harbour has ships at its berths and boats along its piers, clear of the piers and in water deep enough', async () => {
  const { planTown, harbourMoorings, pierDist } = await import('../src/index');
  const height = (x: number, z: number) => -z * 0.06 + 1.2 * Math.sin(x / 70);
  const water = (x: number, z: number) => Math.max(0, -height(x, z));
  let ships = 0, boats = 0;
  for (const seed of [1, 2, 3, 4, 5]) {
    const t = planTown({ seed, x: 0, z: -60, size: 'town', height, water, harbour: { x: 0, z: 0, dx: 0, dz: 1 } });
    const ms = harbourMoorings(t.harbour!, seed);
    for (const m of ms) {
      if (m.plan.kind === 'ship') ships++; else boats++;
      assert.ok(water(m.x, m.z) >= m.plan.draft, 'afloat');
      for (const p of t.harbour!.piers) assert.ok(pierDist(p, m.x, m.z) > m.plan.beam / 2, 'clear of the pier');
      // Its land side: a ship's pier (or a boat's quay) lies just off its side there.
      if (m.plan.kind === 'ship') {
        const d = m.plan.beam / 2 + 0.9, px = m.x - m.uz * d * m.side, pz = m.z + m.ux * d * m.side;
        assert.ok(t.harbour!.piers.some((p) => pierDist(p, px, pz) < p.half), 'its pier off its side');
      }
    }
    assert.deepEqual(harbourMoorings(t.harbour!, seed), ms);
  }
  assert.ok(ships >= 2 && boats >= 2, `${ships} ships, ${boats} boats`);
});

test('ship: walking its deck: the rail and masts are walls, the gangway open, the hull solid to a swimmer', () => {
  for (const seed of [1, 2, 3]) {
    const p = planShip(seed, 'ship'), r = 0.35, g = p.gangway!, ga = (g.a0 + g.a1) / 2, w = hullHalf(p, ga, p.deckY);
    assert.ok(g.a1 - g.a0 > 1.5, 'room to come aboard');
    assert.ok(!shipWall(p, ga, 0, r, p.deckY), 'free on deck');
    assert.ok(shipWall(p, p.length * 0.1, w - 0.3, r, p.deckY), 'at the rail');
    assert.ok(!shipWall(p, ga, w - 0.3, r, p.deckY, true) && !shipWall(p, ga, -(w + 0.2), r, p.deckY, true), 'through the gangway');
    assert.ok(shipWall(p, ga, w - 0.3, r, p.deckY), 'the gangway barred at sea');
    assert.equal(shipFloor(p, ga, w - 0.3), p.deckY);
    const m = p.masts[0];
    assert.ok(shipWall(p, m.a + 0.3, 0, r, p.deckY), 'the mast');
    assert.ok(shipWall(p, 0, 0, r, -1.2) && shipWall(p, 0, w + 0.2, r, -1.2), 'the hull under water');
    assert.ok(!shipWall(p, 0, w + 0.6, r, -1.2) && !shipWall(p, p.length, 0, r, p.deckY), 'clear of it');
    assert.ok(shipWall(p, -p.length / 2 + 0.1, 0, r, p.aft!.y), 'the transom behind the sterncastle');
    assert.ok(shipWall(p, p.fore!.a0 - r * 0.5, 1.2, r, p.deckY) && !shipWall(p, p.fore!.a0 - r - 0.05, 1.2, r, p.deckY), 'the forecastle front, the whole body out of it');
  }
  const plank = gangplankMesh(2.5);
  assert.ok(plank.index.length > 36 && plank.position.every(Number.isFinite));
});

test('ship: a ladder up each castle, its foot on the main deck before the castle, its top at the castle deck', () => {
  for (const L of [22, 30]) {
    const p = planShip(3, 'ship', L), ls = shipLadders(p).filter((l) => l.lean > 0);
    assert.equal(ls.length, 2);
    for (const l of ls) {
      const c = l.dir === 1 ? p.aft! : p.fore!, face = l.dir === 1 ? c.a1 : c.a0;
      assert.equal(shipFloor(p, l.a, l.b), p.deckY, 'the foot on the main deck');
      assert.equal(l.y1, c.y);
      // Its top line just off the castle's front; whole rungs from the foot to the top.
      const topA = l.a - l.dir * l.lean;
      assert.ok((topA - face) * l.dir > 0.3 && (topA - face) * l.dir < 0.6);
      const n = (l.y1 - l.y0) / l.rung;
      assert.ok(Math.abs(n - Math.round(n)) < 1e-9 && l.rung > 0.25 && l.rung < 0.36);
      assert.ok(!shipWall(p, l.a + l.dir * 0.75, l.b, 0.32, p.deckY), 'room to stand at its foot');
    }
  }
  assert.equal(shipLadders(planShip(3, 'boat')).length, 0);
});

test('ship: the castles\' cabins are walked into through their doors; what stands in them stands inside the hull', () => {
  for (const L of [21, 26, 33]) {
    const p = planShip(5, 'ship', L), r = 0.32, y = p.deckY;
    const things = shipFixtures(p);
    assert.ok(things.some((f) => f.kind === 'table' && f.a < 0) && things.some((f) => f.kind === 'oven'), 'the captain\'s table, the galley stove');
    for (const f of things) for (const [da, db] of [[-1, -1], [1, -1], [1, 1], [-1, 1]]) {
      const a = f.a + (da * f.w) / 2, b = f.b + (db * f.d) / 2;
      assert.ok(Math.abs(b) < hullHalf(p, a, y + 0.3), `${f.kind} at a ${a.toFixed(2)} b ${b.toFixed(2)} sticks out of the hull`);
    }
    for (const c of [p.aft!, p.fore!]) {
      const face = c === p.aft ? c.a1 : c.a0, dir = c === p.aft ? 1 : -1;
      // Straight in through the doorway, from a step before it (the foremast stands a little further out) to a metre inside.
      for (let d = -0.6; d <= 1.0; d += 0.05) assert.ok(!shipWall(p, face - dir * d, 0, r, y), `${L} m: blocked ${d.toFixed(2)} m into the ${c === p.aft ? 'aft' : 'fore'} cabin`);
      // Beside the doorway the front stops a body; inside, the hull's sides do.
      assert.ok(shipWall(p, face, 1.2, r, y) && shipWall(p, face, -1.2, r, y));
      assert.ok(shipWall(p, face - dir * 1, hullHalf(p, face - dir * 1, y), r, y));
    }
  }
});

test('ship: down the companionway to the lower deck: the passengers\' cabins, the cargo, the passage between kept free', () => {
  for (const L of [21, 26, 33]) {
    const p = planShip(6, 'ship', L), h = p.hold!, cw = p.companion!, r = 0.32, H = shipHold(p);
    const down = shipLadders(p).find((l) => l.lean === 0)!;
    assert.ok(down && down.y0 === h.y && down.y1 === p.deckY, 'a ladder from the lower deck up to the main deck');
    // In the companionway's opening only the lower deck; beside it the main deck over the lower deck.
    assert.deepEqual(shipFloors(p, (cw.a0 + cw.a1) / 2, (cw.b0 + cw.b1) / 2), [h.y]);
    assert.deepEqual(shipFloors(p, (cw.a0 + cw.a1) / 2, 0.2), [h.y, p.deckY]);
    // The rail round it to a body on deck, but not on its fore side, where one gets onto the ladder.
    assert.ok(shipWall(p, cw.a0 - 0.2, (cw.b0 + cw.b1) / 2, r, p.deckY) && shipWall(p, (cw.a0 + cw.a1) / 2, cw.b1 + 0.2, r, p.deckY));
    assert.ok(!shipWall(p, cw.a1 + 0.5, (cw.b0 + cw.b1) / 2, r, p.deckY));
    // Cabins and cargo on the lower deck; the way from the ladder's foot down the passage to the far end is free.
    assert.ok(H.fixtures.filter((f) => f.kind === 'bed').length >= 2, `${L} m: berths`);
    assert.ok(H.fixtures.some((f) => f.kind === 'barrel' || f.kind === 'chest'), `${L} m: cargo`);
    const footA = down.a - 0.75;
    for (let b = down.b; b < -0.1; b += 0.05) assert.ok(!shipWall(p, footA, b, r, h.y), `${L} m: from the ladder's foot to the passage, blocked at b ${b.toFixed(2)}`);
    const masts = p.masts.filter((m) => m.foot === p.deckY);
    for (let a = footA; a < h.a1 - 0.5; a += 0.1) {
      const m = masts.find((k) => Math.abs(k.a - a) < 0.7), b = m ? 0.65 : 0;
      assert.ok(!shipWall(p, a, b, r, h.y), `${L} m: the passage blocked at a ${a.toFixed(2)}`);
      assert.ok(shipInside(p, a, b, h.y) && shipRoom(p, a, b, h.y + 1) === 'hold');
    }
    // Into a berth through its door.
    const bed = H.fixtures.find((f) => f.kind === 'bed')!;
    assert.ok(!shipWall(p, bed.a + 0.95 + 0.1 - 2.2 + 0.55, Math.sign(bed.b) * 1.1, r, h.y), 'in through the berth\'s door');
    // The hull to a swimmer outside it, at the lower deck's height.
    assert.ok(shipWall(p, 0, hullHalf(p, 0, h.y + 1) + 0.1, r, h.y));
  }
});
