import { test } from 'node:test';
import assert from 'node:assert/strict';
import { planShip, shipMesh, shipFloor, hullHalf, shipWall, gangplankMesh, shipLadders, shipFixtures } from '../src/index';

test('ship: a sailing ship has castles fore and aft, masts with yards, a hatch, and decks to walk on', () => {
  for (const seed of [1, 2, 3, 4]) {
    const p = planShip(seed, 'ship');
    assert.ok(p.length >= 20 && p.length <= 34, `${p.length} m`);
    assert.ok(p.aft && p.fore && p.hatch);
    assert.ok(p.masts.length >= 2 && p.masts.every((m) => m.top > m.foot + 10 && m.yards.length >= 1));
    // The main deck amidships, the castles over it, nothing over the side or in the hatch.
    assert.equal(shipFloor(p, p.length * 0.15, 0), p.deckY);
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
    const p = planShip(3, 'ship', L), ls = shipLadders(p);
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
