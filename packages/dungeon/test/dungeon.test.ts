import { test } from 'node:test';
import assert from 'node:assert/strict';
import { cyclicGraph, layoutDungeon, LayoutGrid, pace, PATTERNS, type GraphSpec } from '../src/index';

const ALL = PATTERNS.map((p) => p.id);
const spec: GraphSpec = { main: ALL, inserts: ALL, insertCount: [1, 2], maxRooms: 14, minLevel: -1 };

test('dungeon: every pattern builds a goal that can be reached, with a shortcut back out', () => {
  for (const id of ALL) for (let s = 0; s < 6; s++) {
    const g = cyclicGraph({ ...spec, main: [id], insertCount: [0, 0] }, 100 + s);
    const p = pace(g);
    assert.ok(p.route.length > 1, `${id}: goal reachable`);
    assert.ok(p.shortcut, `${id}: a shortcut out`);
    assert.equal(p.route[0], g.entrance);
    assert.equal(p.route[p.route.length - 1], g.goal);
  }
});

test('dungeon: tension rises from a calm entrance to the climax, with a safe spot and a reveal', () => {
  let safe = 0;
  for (let s = 0; s < 40; s++) {
    const g = cyclicGraph(spec, s);
    const p = pace(g);
    assert.equal(p.beat[g.entrance], 'entrance');
    assert.equal(p.beat[g.goal], 'climax');
    assert.ok(p.tension[g.entrance] < 0.2 && p.tension[g.goal] === 1);
    assert.ok(p.reveal >= 0, 'a reveal');
    if (p.safe >= 0) safe++;
  }
  assert.ok(safe === 40, `safe spots in ${safe}/40`);
});

test('dungeon: layouts place every room without overlap and route every link', () => {
  for (let s = 0; s < 30; s++) {
    const g = cyclicGraph(spec, s);
    const L = layoutDungeon(g, s, { entrance: { x: -2, z: -2, w: 4, d: 5 } });
    assert.ok(L, `layout ${s}`);
    assert.equal(L.rooms.length, g.rooms.length);
    assert.equal(L.links.length, g.links.length);
    const seen = new Map<string, number>();
    for (const r of L.rooms) for (let l = r.level; l < r.level + r.height; l++) for (let z = r.z; z < r.z + r.d; z++) for (let x = r.x; x < r.x + r.w; x++) {
      const k = `${x},${z},${l}`;
      assert.ok(!seen.has(k), `room cells overlap at ${k}`);
      seen.set(k, r.id);
    }
    L.links.forEach((pl, i) => {
      for (const c of pl.path) for (const l of c.stair ? [c.level, c.level - 1] : [c.level]) {
        const k = `${c.x},${c.z},${l}`;
        assert.ok(!seen.has(k), `passage ${i} crosses ${k}`);
        seen.set(k, -1 - i);
      }
      for (let j = 1; j < pl.path.length; j++) {
        const a = pl.path[j - 1], b = pl.path[j];
        assert.equal(Math.abs(a.x - b.x) + Math.abs(a.z - b.z), 1, `passage ${i} is continuous`);
      }
      const [da, db] = pl.doors;
      assert.equal(da.room, pl.link.a);
      assert.equal(db.room, pl.link.b);
      if (pl.link.kind === 'drop') assert.equal(db.level, L.rooms[pl.link.b].level + 1, 'a drop enters over the ledge');
    });
    const grid = new LayoutGrid(L);
    assert.equal(grid.owner(L.rooms[g.entrance].x, L.rooms[g.entrance].z, 0), g.entrance);
  }
});

test('dungeon: the same seed gives the same dungeon', () => {
  const a = cyclicGraph(spec, 7), b = cyclicGraph(spec, 7);
  assert.deepEqual(a, b);
  assert.deepEqual(layoutDungeon(a, 7), layoutDungeon(b, 7));
});

test('dungeon: every pattern, as the main cycle, lays out', () => {
  for (const id of ALL) {
    let ok = 0;
    for (let s = 0; s < 8; s++) {
      const g = cyclicGraph({ ...spec, main: [id] }, 300 + s);
      if (layoutDungeon(g, s, { entrance: { x: -2, z: -2, w: 4, d: 4 }, attempts: 10 })) ok++;
    }
    assert.ok(ok >= 6, `${id}: ${ok}/8 laid out`);
  }
});

test('dungeon: the library holds 18 distinct patterns', () => {
  assert.equal(new Set(ALL).size, ALL.length);
  assert.ok(ALL.length >= 18, `${ALL.length} patterns`);
});

test('dungeon: caverns many storeys high, far apart along long winding ways', () => {
  let tall = 0, longer = 0;
  for (let s = 0; s < 12; s++) {
    const g = cyclicGraph({ ...spec, minLevel: 0 }, 300 + s);
    // The game raises a room into a cavern after the graph is built.
    const cavern = g.rooms.find((r) => r.id === g.goal)!;
    cavern.height = 6;
    const near = layoutDungeon(g, s, { radius: 40, maxPath: 16 });
    const far = layoutDungeon(g, s, { radius: 40, maxPath: 16, gap: [3, 6], turn: 0.2 });
    if (!near || !far) continue;
    const C = far.rooms[cavern.id];
    assert.equal(C.height, 6);
    const grid = new LayoutGrid(far);
    for (let l = C.level; l < C.level + 6; l++) assert.equal(grid.owner(C.x, C.z, l), C.id, `the cavern owns storey ${l}`);
    for (const pl of far.links) if (pl.link.kind === 'drop' && pl.link.b === C.id) assert.equal(pl.doors[1].level, C.level + 1, 'a drop enters the cavern over its lowest ledge');
    tall++;
    const length = (L: NonNullable<typeof far>) => L.links.reduce((n, pl) => n + pl.path.length, 0);
    if (length(far) > length(near)) longer++;
  }
  assert.ok(tall >= 9, `caverns laid out in ${tall}/12`);
  assert.ok(longer >= tall - 1, `ways longer with a gap in ${longer}/${tall}`);
});
