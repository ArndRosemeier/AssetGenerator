import { test } from 'node:test';
import assert from 'node:assert/strict';
import { planShip, shipMesh, shipFloor, hullHalf } from '../src/index';

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
    assert.equal(shipFloor(p, (p.hatch.a0 + p.hatch.a1) / 2, 0), null);
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
    }
    assert.deepEqual(harbourMoorings(t.harbour!, seed), ms);
  }
  assert.ok(ships >= 2 && boats >= 2, `${ships} ships, ${boats} boats`);
});
