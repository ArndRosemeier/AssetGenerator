/**
 * Ships for the harbours and the seas: a sailing ship with a forecastle, a sterncastle over the captain's cabin,
 * masts, yards, sails set or furled and the rigging, and a fishing boat with one mast. Seeded and pure; one planner,
 * a bigger ship only longer and with more masts. The plan says where its floors are (for walking on its decks), the
 * mesh draws it in its own frame: `a` along it (bow +a), `y` up from the waterline, `b` across (port, its left, +b).
 */
import { Rng } from '@futuremagic/core';
import { BuildingMat, Frame, Out, beam, mergeOuts, type BuildingMesh, type RGB } from './building';
import { drawFixture, type InteriorFixture } from './interior';

export type ShipKind = 'ship' | 'boat';

/** A raised deck at one end (a castle), from `a0` to `a1` along the ship, its floor `y`. */
export interface Castle {
  a0: number;
  a1: number;
  y: number;
}

export interface Mast {
  /** Where it stands along the ship, the floor it stands on and its top. */
  a: number;
  foot: number;
  top: number;
  /** Its yards (heights over the waterline) and their half spans. */
  yards: { y: number; half: number }[];
}

export interface ShipPlan {
  kind: ShipKind;
  seed: number;
  /** Length of the hull, its widest beam and how deep it lies (m). */
  length: number;
  beam: number;
  draft: number;
  /** The main deck's floor and the top of the rail beside it, over the waterline (m). */
  deckY: number;
  railY: number;
  /** The castles (none on a boat): at the stern (a < 0) and at the bow (a > 0). */
  aft: Castle | null;
  fore: Castle | null;
  masts: Mast[];
  /** The cargo hatch to the hold, on the main deck (a0..a1 along, half across), its grating walked over; null on a boat. */
  hatch: { a0: number; a1: number; half: number } | null;
  /** The lower deck under the main deck (from a0 to a1 along, its floor y), down the companionway; null on a boat. */
  hold: { a0: number; a1: number; y: number } | null;
  /** The companionway: an open hatch in the main deck (a0..a1 along, b0..b1 across), a ladder down its fore side; null on a boat. */
  companion: { a0: number; a1: number; b0: number; b1: number } | null;
  /** The gangway: an opening in the rail on both sides amidships (a0..a1 along), where a plank comes aboard; null on a boat. */
  gangway: { a0: number; a1: number } | null;
  /** Hull colours: planking, the painted strake under the rail. */
  hull: RGB;
  strake: RGB;
}

/** The lower deck lies this far under the main deck (m). */
const HOLD_DOWN = 2.2;
const SHIP_MIN = 20, SHIP_MAX = 34, BOAT_MIN = 6.5, BOAT_MAX = 9.5;
/** A ship's hull and rail are drawn in this many panels along its length; the gangway is two of them from this one. */
const SHIP_PANELS = 28, GANGWAY = 17;

/** A ship (`length` between 20 and 34 m) or a fishing boat (6.5 to 9.5 m), its look from the seed. */
export function planShip(seed: number, kind: ShipKind, length?: number): ShipPlan {
  const r = new Rng(seed * 2654435761 + (kind === 'ship' ? 11 : 23));
  const L = Math.min(kind === 'ship' ? SHIP_MAX : BOAT_MAX, Math.max(kind === 'ship' ? SHIP_MIN : BOAT_MIN, length ?? (kind === 'ship' ? r.range(24, 32) : r.range(7, 9))));
  const B = L * (kind === 'ship' ? r.range(0.28, 0.32) : r.range(0.32, 0.36));
  const draft = kind === 'ship' ? L * 0.11 : L * 0.08;
  const deckY = kind === 'ship' ? 1.2 + L * 0.035 : 0.35;
  const railY = deckY + (kind === 'ship' ? 1.0 : 0.45);
  const half = L / 2;
  const aft = kind === 'ship' ? { a0: -half, a1: -half * 0.55, y: deckY + 2.3 } : null;
  const fore = kind === 'ship' ? { a0: half * 0.68, a1: half, y: deckY + 2.0 } : null;
  const masts: Mast[] = [];
  if (kind === 'ship') {
    const main = deckY + L * 0.95, mb = B * 0.95;
    masts.push({ a: half * 0.05, foot: deckY, top: main, yards: [{ y: deckY + L * 0.62, half: mb }, { y: deckY + L * 0.86, half: mb * 0.62 }] });
    masts.push({ a: half * 0.55, foot: deckY, top: deckY + L * 0.75, yards: [{ y: deckY + L * 0.5, half: mb * 0.78 }, { y: deckY + L * 0.68, half: mb * 0.5 }] });
    if (L > 27) masts.push({ a: -half * 0.72, foot: aft!.y, top: aft!.y + L * 0.45, yards: [{ y: aft!.y + L * 0.36, half: mb * 0.5 }] });
  } else {
    masts.push({ a: half * 0.25, foot: deckY, top: deckY + L * 0.8, yards: [{ y: deckY + L * 0.72, half: B * 0.75 }] });
  }
  // The cargo hatch forward of the main mast, over the cargo; the companionway to starboard before the sterncastle,
  // clear of its door, down to the passengers' cabins.
  const hatch = kind === 'ship' ? { a0: half * 0.15, a1: half * 0.32, half: B * 0.16 } : null;
  const hold = kind === 'ship' ? { a0: aft!.a1 + 0.1, a1: fore!.a0 - 0.1, y: deckY - HOLD_DOWN } : null;
  const companion = kind === 'ship' ? { a0: aft!.a1 + 0.5, a1: aft!.a1 + 1.5, b0: -1.95, b1: -1.05 } : null;
  // Two of the rail's panels (the mesh draws it in SHIP_PANELS along the length) forward of the main mast's shrouds.
  const gangway = kind === 'ship' ? { a0: (-1 + (2 * GANGWAY) / SHIP_PANELS) * half, a1: (-1 + (2 * (GANGWAY + 2)) / SHIP_PANELS) * half } : null;
  const hull = r.pick<RGB>([[92, 66, 44], [78, 58, 42], [104, 78, 52]]);
  const strake = r.pick<RGB>([[120, 42, 34], [36, 58, 92], [44, 76, 52], [160, 128, 60]]);
  return { kind, seed, length: L, beam: B, draft, deckY, railY, aft, fore, masts, hatch, hold, companion, gangway, hull, strake };
}

/** Half the hull's width at `a` along it and `y` over the waterline (0 outside the hull). */
export function hullHalf(p: ShipPlan, a: number, y: number): number {
  const t = (a / p.length) * 2;
  if (t <= -1 || t >= 1) return 0;
  const k = keelAt(p, t), s = sheerAt(p, t);
  if (y < k || y > s + 1e-6) return 0;
  return halfAtDeck(p, t) * section((y - k) / (s - k));
}

/** The top floor at (a, b) on the ship's decks (null: none there, over the side). The hatch's grating is walked over. */
export function shipFloor(p: ShipPlan, a: number, b: number): number | null {
  const f = shipFloors(p, a, b);
  return f.length ? f[f.length - 1] : null;
}

/**
 * Every floor at (a, b), lowest first: the lower deck (under the main deck, and under the companionway's open hatch),
 * the main deck (under a castle, its cabin's floor) or the hatch's grating, a castle's deck.
 */
export function shipFloors(p: ShipPlan, a: number, b: number): number[] {
  const out: number[] = [];
  const h = p.hold;
  if (h && a >= h.a0 && a <= h.a1 && Math.abs(b) <= holdHalf(p, a)) out.push(h.y);
  const c = p.companion;
  if (c && a > c.a0 && a < c.a1 && b > c.b0 && b < c.b1) return out;
  if (p.hatch && a >= p.hatch.a0 && a <= p.hatch.a1 && Math.abs(b) <= p.hatch.half) { out.push(p.deckY + GRATING); return out; }
  if (Math.abs(b) <= hullHalf(p, a, p.deckY) - INNER) out.push(p.deckY);
  for (const k of [p.aft, p.fore]) if (k && a >= k.a0 && a <= k.a1 && Math.abs(b) <= hullHalf(p, a, k.y) - INNER) out.push(k.y);
  return out;
}

/** The lower deck's inner half width at `a` (low down, where the hull narrows it most); 0 outside it. */
function holdHalf(p: ShipPlan, a: number): number {
  const h = p.hold;
  return h && a >= h.a0 - 1e-6 && a <= h.a1 + 1e-6 ? Math.max(0, hullHalf(p, a, h.y + 0.3) - INNER) : 0;
}

/**
 * The room a point (a, b, at height h) is in: the lower deck, or the aft or fore castle's cabin (null: none, out on
 * deck, outside the hull or in its timbers). For keeping a camera in the room its hero is in.
 */
export function shipRoom(p: ShipPlan, a: number, b: number, h: number): 'hold' | 'aft' | 'fore' | null {
  const k = p.hold;
  if (k && h > k.y - 0.1 && h < p.deckY - 0.1 && a > k.a0 + 0.05 && a < k.a1 - 0.05 && Math.abs(b) < holdHalf(p, a) - 0.05) return 'hold';
  for (const c of [p.aft, p.fore]) if (c && h > p.deckY - 0.1 && h < c.y - 0.12 && a > c.a0 + 0.05 && a < c.a1 - 0.05 && Math.abs(b) < cabinHalf(p, a) - 0.05) return c === p.aft ? 'aft' : 'fore';
  return null;
}

/** Whether (a, b), feet at `y`, is inside the ship where it is walked: on the lower deck, or in a castle's cabin. */
export function shipInside(p: ShipPlan, a: number, b: number, y: number): boolean {
  const h = p.hold;
  if (h && y > h.y - 0.5 && y < p.deckY - 0.5) return Math.abs(b) < holdHalf(p, a);
  for (const c of [p.aft, p.fore]) if (c && y > p.deckY - 0.5 && y < c.y - 0.5 && a > c.a0 && a < c.a1) return Math.abs(b) < cabinHalf(p, a);
  return false;
}

/**
 * A ladder aboard, up a castle's front from the main deck: its rungs' line at its foot (`a`, `b`, the floor `y0`),
 * up to the deck `y1` it climbs to. It leans back towards the castle by `lean` metres over that height; `dir` is the
 * way from the castle's front out over the main deck (+1: along +a). Its rungs are `rung` apart, the first one rung
 * over the foot, the last one rung under the top.
 */
export interface ShipLadder {
  a: number;
  b: number;
  y0: number;
  y1: number;
  dir: 1 | -1;
  lean: number;
  rung: number;
}

/** Rungs about 0.3 m apart, a whole number of them over a height `H`. */
const rungs = (H: number) => H / Math.max(3, Math.round(H / 0.3));

/** The castle doors' half width (m); a castle's ladder stands beside its door. */
const DOOR = 0.55;

/** The ladders up the castles' fronts, and down the companionway to the lower deck (none on a boat). */
export function shipLadders(p: ShipPlan): ShipLadder[] {
  const out: ShipLadder[] = [];
  for (const c of [p.aft, p.fore]) if (c) {
    const face = c === p.aft ? c.a1 : c.a0, dir = c === p.aft ? 1 : -1, lean = 0.35;
    out.push({ a: face + dir * (0.45 + lean), b: DOOR + 0.45, y0: p.deckY, y1: c.y, dir, lean, rung: rungs(c.y - p.deckY) });
  }
  // Down the companionway: upright against its fore side, got onto from the deck forward of it.
  const cw = p.companion, h = p.hold;
  if (cw && h) out.push({ a: cw.a1 - 0.12, b: (cw.b0 + cw.b1) / 2, y0: h.y, y1: p.deckY, dir: -1, lean: 0, rung: rungs(p.deckY - h.y) });
  return out;
}

/** The castles' cabins' fixtures, as planned once per ship; the walk kept free down a cabin's middle (half of it, m). */
const AISLE = 0.45;
const FIXTURES = new WeakMap<ShipPlan, InteriorFixture[]>();

/**
 * What is in the castles' cabins, on the main deck under them: aft the captain's (his table with the chart on it, his
 * bunk, his sea chest), forward the crew's and the galley (the stove, a table between benches, a berth, barrels); and
 * each cabin's door, standing open, swung back against the front to starboard. In the ship's frame, `h` over the main
 * deck (storey 0).
 */
export function shipFixtures(p: ShipPlan): InteriorFixture[] {
  let out = FIXTURES.get(p);
  if (out) return out;
  out = [];
  const list = out;
  const put = (kind: InteriorFixture['kind'], a: number, b: number, w: number, d: number, h: number) => list.push({ kind, storey: 0, a, b, w, d, h });
  for (const c of [p.aft, p.fore]) if (c) {
    const aft = c === p.aft, face = aft ? c.a1 : c.a0, dir = aft ? 1 : -1, depth = c.a1 - c.a0;
    /** `d` metres in from the cabin's front; the room across there (inner half width, at hip height), the least over `w` along. */
    const at = (d: number) => face - dir * d;
    const room = (d: number, w = 0) => Math.min(cabinHalf(p, at(d - w / 2)), cabinHalf(p, at(d + w / 2)));
    // Against a side, if it leaves the middle free to walk (an aisle of AISLE either side of the keel line).
    const byWall = (kind: InteriorFixture['kind'], d: number, w: number, deep: number, h: number, s: 1 | -1) => {
      const b = room(d, w) - deep / 2 - 0.04;
      if (b - deep / 2 >= AISLE && d + w / 2 < depth - 0.1) put(kind, at(d), s * b, w, deep, h);
    };
    // In the middle, if there is room to walk round it on both sides.
    const amid = (kind: InteriorFixture['kind'], d: number, w: number, deep: number, h: number, b = 0) => {
      if (room(d, w) - Math.abs(b) - deep / 2 >= 0.75 && d + w / 2 < depth - 0.3) put(kind, at(d), b, w, deep, h);
    };
    put('door', at(0.1), -(DOOR + 0.55), 0.06, 1.1, 1.95);
    if (aft) {
      amid('table', depth * 0.45, 1.0, 1.5, 0.78);
      byWall('bed', depth - 1.25, 1.9, 0.85, 0.55, 1);
      byWall('chest', 1.5, 0.9, 0.5, 0.55, -1);
    } else {
      byWall('oven', 1.0, 0.9, 0.8, 0.9, -1);
      byWall('bed', 1.1, 1.7, 0.75, 0.5, 1);
      byWall('barrel', 2.0, 0.55, 0.55, 0.8, -1);
      amid('table', 2.3, 0.8, 0.6, 0.75);
    }
  }
  FIXTURES.set(p, out);
  return out;
}

/** A castle cabin's inner half width at `a` along the ship (low down, where its planking narrows it most). */
function cabinHalf(p: ShipPlan, a: number): number {
  return Math.max(0, hullHalf(p, a, p.deckY + 0.3) - INNER);
}

/** A wall standing on the lower deck (a thin box, a0..a1 along, b0..b1 across), from its floor to the deck over it. */
export interface HoldWall { a0: number; a1: number; b0: number; b1: number }

/** The lower deck's things and walls, and its lanterns (a, b), as planned once per ship. */
const HOLDS = new WeakMap<ShipPlan, { fixtures: InteriorFixture[]; walls: HoldWall[]; lamps: [number, number][] }>();
/** Half the passage down the lower deck's middle (m), a passenger's cabin's length, its door's width. */
const PASSAGE = 0.7, BERTH = 2.2, BERTH_DOOR = 0.8;

/**
 * The lower deck, down the companionway: by its foot the passengers' cabins either side of a passage down the middle
 * (each a bunk along the hull, its door onto the passage), forward of them the cargo (crates and barrels along the
 * sides, the way between them kept free, clear of the masts going down to the keel). Fixtures `h` over its floor
 * (storey -1); lanterns hung over the passage.
 */
export function shipHold(p: ShipPlan): { fixtures: InteriorFixture[]; walls: HoldWall[]; lamps: [number, number][] } {
  let out = HOLDS.get(p);
  if (out) return out;
  const fixtures: InteriorFixture[] = [], walls: HoldWall[] = [], lamps: [number, number][] = [];
  out = { fixtures, walls, lamps };
  HOLDS.set(p, out);
  const h = p.hold;
  if (!h) return out;
  const r = new Rng(p.seed * 7919 + 5);
  const room = (a0: number, a1: number) => Math.min(holdHalf(p, a0), holdHalf(p, (a0 + a1) / 2), holdHalf(p, a1));
  const put = (kind: InteriorFixture['kind'], a: number, b: number, w: number, d: number, hh: number) => fixtures.push({ kind, storey: -1, a, b, w, d, h: hh });
  const masts = p.masts.filter((m) => m.foot === p.deckY);
  const clearOfMasts = (a0: number, a1: number) => masts.every((m) => m.a < a0 - 0.5 || m.a > a1 + 0.5);
  // The landing at the companionway's foot, then the cabins, two a side, while the hull is wide enough for them.
  let a = h.a0 + 2.0;
  lamps.push([h.a0 + 1.2, 0]);
  for (let k = 0; k < 2; k++) {
    const a1 = a + BERTH;
    if (a1 > h.a1 - 1 || room(a, a1) < PASSAGE + 1.6 || !clearOfMasts(a, a1)) break;
    for (const s of [1, -1]) {
      const w = room(a, a1);
      // Its walls: across the hull at each end, and along the passage, its door at the aft end.
      for (const e of k === 0 ? [a, a1] : [a1]) walls.push({ a0: e - 0.03, a1: e + 0.03, b0: Math.min(s * PASSAGE, s * (w + 0.1)), b1: Math.max(s * PASSAGE, s * (w + 0.1)) });
      walls.push({ a0: a + 0.15 + BERTH_DOOR, a1, b0: s * PASSAGE - 0.03, b1: s * PASSAGE + 0.03 });
      if (k === 0) walls.push({ a0: a, a1: a + 0.15, b0: s * PASSAGE - 0.03, b1: s * PASSAGE + 0.03 });
      put('bed', a1 - 0.1 - 0.95, s * (w - 0.42), 1.9, 0.8, 0.5);
      if (w - 0.82 - PASSAGE > 1.0) put('chest', a1 - 0.4, s * (PASSAGE + 0.3), 0.5, 0.45, 0.45);
    }
    lamps.push([a + BERTH / 2, 0]);
    a = a1;
  }
  // The cargo, forward: crates and barrels along both sides, a row or two, the middle kept free.
  a += 0.4;
  let lampAt = a + 1.5;
  while (a < h.a1 - 0.8) {
    const crate = r.chance(0.55), w = crate ? 0.8 : 0.6, a1 = a + w;
    if (!clearOfMasts(a, a1) || a1 > h.a1 - 0.2) { a += 0.3; continue; }
    for (const s of [1, -1]) {
      const kind = r.chance(0.5) === crate ? 'chest' : 'barrel', d = kind === 'chest' ? 0.8 : 0.6, tall = kind === 'chest' ? 0.75 : 0.85;
      let b = room(a, a1) - d / 2 - 0.05;
      for (let row = 0; row < 2 && b - d / 2 >= 0.95; row++) {
        if (row === 1 && r.chance(0.4)) break;
        put(kind, a + w / 2, s * b, w, d, tall);
        b -= d + 0.08;
      }
    }
    if (a > lampAt) { lamps.push([a, 0]); lampAt = a + 3.5; }
    a = a1 + 0.12;
  }
  return out;
}

/** The deck's floor at `a` along the ship: a castle's or the main deck. */
function deckAt(p: ShipPlan, a: number): number {
  for (const c of [p.aft, p.fore]) if (c && a >= c.a0 - 1e-6 && a <= c.a1 + 1e-6) return c.y;
  return p.deckY;
}

/**
 * Whether a body of radius `r` at (a, b), its feet at `y` (all in the ship's frame), touches the ship: its rail and
 * planking round the deck, its masts, and its hull under the deck (a swimmer goes round it). `gangway`: open there (a
 * plank laid to it in harbour); at sea it is closed (a bar across it).
 */
export function shipWall(p: ShipPlan, a: number, b: number, r: number, y: number, gangway = false): boolean {
  const half = p.length / 2;
  if (Math.abs(a) > half + r || Math.abs(b) > p.beam / 2 + r) return false;
  const t = (a / p.length) * 2, f = deckAt(p, a), w = Math.max(hullHalf(p, a, f), hullHalf(p, Math.sign(a) * Math.max(0, Math.abs(a) - r), f));
  // In a castle's cabin, or at its front from the main deck: through its doorway only.
  for (const c of [p.aft, p.fore]) if (c && y > p.deckY - 0.5 && y < c.y - 0.5 && a + r > c.a0 && a - r < c.a1) return cabinWall(p, c, a, b, r, y);
  // On the lower deck, inside the hull.
  if (p.hold && y > p.hold.y - 0.5 && y < p.deckY - 0.5 && Math.abs(b) < holdHalf(p, a)) return holdWall(p, a, b, r, y);
  if (y < f - 0.5) {
    // Below the deck: the hull itself, as wide as it is up at the head (it flares out from the keel to the deck).
    const mid = Math.min(f - 0.1, y + 1.7), wm = Math.max(hullHalf(p, a, mid), hullHalf(p, Math.sign(a) * Math.max(0, Math.abs(a) - r), mid));
    return wm > 0 && Math.abs(b) < wm + r && y + 1.7 > keelAt(p, Math.max(-1, Math.min(1, t)));
  }
  for (const m of p.masts) if (y + 1 > m.foot && Math.hypot(a - m.a, b) < r + (p.kind === 'ship' ? 0.26 : 0.1)) return true;
  // The rail round the companionway's open hatch, on all but its fore side (where its ladder goes down).
  const cw = p.companion;
  if (cw && y < p.deckY + 0.9 && y > p.deckY - 0.3) for (const [a0, a1, b0, b1] of companionRails(cw)) if (a + r > a0 && a - r < a1 && b + r > b0 && b - r < b1) return true;
  // Over the rail (jumped): clear of it.
  if (Math.abs(t) < 1 && y > sheerAt(p, t) + 0.05) return false;
  // The transom across the stern, above its deck.
  if (a - r < -half && Math.abs(b) < w + r && y < sheerAt(p, -1) + 0.05) return true;
  const g = p.gangway;
  if (gangway && g && a - r * 0.5 >= g.a0 && a + r * 0.5 <= g.a1) return false;
  return Math.abs(b) > w - INNER - r && Math.abs(b) < w + r;
}

/**
 * A castle's cabin to a body of radius `r` at (a, b), its feet at `y` on the main deck: its front but for the doorway
 * (the whole body through it), the planking along its sides and the transom, what stands in it.
 */
function cabinWall(p: ShipPlan, c: Castle, a: number, b: number, r: number, y: number): boolean {
  const face = c === p.aft ? c.a1 : c.a0, dir = c === p.aft ? 1 : -1, inside = (face - a) * dir;
  if (Math.abs(inside) < r) return Math.abs(b) > DOOR - r;
  // Outside, its middle on the main deck before the front: the deck's own walls (the rail along it).
  if (inside < 0) return Math.abs(b) > hullHalf(p, a, p.deckY) - INNER - r;
  if (a - r < -p.length / 2 + 0.12) return true;
  if (Math.abs(b) > Math.min(cabinHalf(p, a - r), cabinHalf(p, a), cabinHalf(p, a + r)) - r) return true;
  for (const f of shipFixtures(p)) {
    if (f.storey !== 0 || y > p.deckY + f.h - 0.1) continue;
    if (Math.abs(a - f.a) < f.w / 2 + r && Math.abs(b - f.b) < f.d / 2 + r) return true;
  }
  return false;
}

/** The lower deck to a body of radius `r` at (a, b), its feet at `y`: the hull's sides, its ends, the masts going down to the keel, the cabins' walls and what stands there. */
function holdWall(p: ShipPlan, a: number, b: number, r: number, y: number): boolean {
  const h = p.hold!;
  if (a - r < h.a0 || a + r > h.a1) return true;
  if (Math.abs(b) > Math.min(holdHalf(p, a - r), holdHalf(p, a), holdHalf(p, a + r)) - r) return true;
  for (const m of p.masts) if (m.foot === p.deckY && Math.hypot(a - m.a, b) < r + 0.26) return true;
  const H = shipHold(p);
  for (const w of H.walls) if (a + r > w.a0 && a - r < w.a1 && b + r > w.b0 && b - r < w.b1) return true;
  for (const f of H.fixtures) if (y < h.y + f.h - 0.1 && Math.abs(a - f.a) < f.w / 2 + r && Math.abs(b - f.b) < f.d / 2 + r) return true;
  return false;
}

/** The planking's thickness inside the hull (m), and the hatch's grating over the deck. */
const INNER = 0.18, GRATING = 0.25;

// The hull's lines, in t = a / (length / 2): -1 at the stern's transom, 1 at the stem.
/** Half the beam at the main deck: full amidships, fine to the stem, a broad transom at the stern. */
function halfAtDeck(p: ShipPlan, t: number): number {
  const full = p.beam / 2;
  if (t >= 0) return full * Math.sqrt(Math.max(0, 1 - t ** 2.4));
  return full * (0.42 + 0.58 * Math.sqrt(Math.max(0, 1 - (-t) ** 3)));
}
/** The keel: deepest amidships, rising to the stem and stern posts. */
function keelAt(p: ShipPlan, t: number): number {
  return -p.draft * (1 - Math.abs(t) ** 3.2) + (t > 0 ? t ** 6 * p.railY * 0.6 : 0);
}
/** The rail along the hull: rising to bow and stern, and up round the castles. */
function sheerAt(p: ShipPlan, t: number): number {
  let s = p.railY + (t > 0 ? 0.6 : 0.45) * t * t * (p.kind === 'ship' ? 1 : 0.4);
  const h = p.length / 2;
  if (p.aft) s += (p.aft.y - p.deckY) * smooth((-t * h - -p.aft.a1 + 1.2) / 1.2);
  if (p.fore) s += (p.fore.y - p.deckY) * smooth((t * h - p.fore.a0 + 1.0) / 1.0);
  return s;
}
/** A section's half width (as a share of the deck's) at u from the keel (0) to the rail (1): round in the bilge. */
function section(u: number): number {
  const v = Math.min(1, u * 1.35);
  return Math.pow(Math.sin((v * Math.PI) / 2), 0.55);
}
const smooth = (x: number) => { const c = Math.min(1, Math.max(0, x)); return c * c * (3 - 2 * c); };

const DECK: RGB = [158, 128, 92], DECK_DARK: RGB = [112, 88, 62], ROPE: RGB = [104, 90, 66], LINEN: RGB = [226, 216, 192];
const IRON: RGB = [62, 62, 66], TAR: RGB = [40, 34, 28], GLASS: RGB = [70, 86, 96], CHART: RGB = [214, 198, 160];

/**
 * The ship's mesh at (x, z) heading along (ux, uz), its waterline at `y`, relative to `origin`. `sails`: 'set' draws
 * the sails full of wind, 'furled' bundled on their yards. `detail` false leaves out the rigging, rungs and fittings.
 */
export function shipMesh(p: ShipPlan, x: number, z: number, ux: number, uz: number, y: number, origin: [number, number, number], sails: 'set' | 'furled' = 'furled', detail = true): BuildingMesh {
  const o = new Out(new Frame({ cx: x, cz: z, ux, uz, vx: -uz, vz: ux, y }, origin));
  const half = p.length / 2, NA = p.kind === 'ship' ? SHIP_PANELS : 16, NU = p.kind === 'ship' ? 9 : 6;
  const g = p.gangway, port = (i: number) => !!g && ts[i] * half >= g.a0 - 1e-6 && ts[i + 1] * half <= g.a1 + 1e-6;
  const ts = Array.from({ length: NA + 1 }, (_, i) => -1 + (2 * i) / NA);
  // Where the gangway opens the rail, the hull's skin stops at the deck.
  const topU = (i: number) => (port(i) ? (p.deckY - keelAt(p, ts[i])) / (sheerAt(p, ts[i]) - keelAt(p, ts[i])) : 1);
  // The hull's skin, port and starboard, in strips from keel to rail; the strake under the rail painted.
  const P = (t: number, u: number, side: number): number[] => {
    const k = keelAt(p, t), s = sheerAt(p, t);
    return [t * half, k + (s - k) * u, side * halfAtDeck(p, t) * section(u)];
  };
  for (const side of [1, -1]) for (let i = 0; i < NA; i++) for (let j = 0; j < NU; j++) {
    const top = topU(i), u0 = j / NU, u1 = Math.min(top, (j + 1) / NU);
    if (u0 >= top - 1e-6) continue;
    const q = [P(ts[i], u0, side), P(ts[i + 1], u0, side), P(ts[i + 1], u1, side), P(ts[i], u1, side)];
    const n = faceNormal(q, [0, 0, side]);
    const c = j === NU - 1 ? p.strake : j === NU - 2 && p.kind === 'ship' ? TAR : p.hull;
    o.quad(q, n, q.map((v) => [v[0], v[1]]), BuildingMat.Oak, c);
  }
  // The transom across the stern.
  for (let j = 0; j < NU; j++) {
    const u0 = j / NU, u1 = (j + 1) / NU, q = [P(-1, u0, 1), P(-1, u0, -1), P(-1, u1, -1), P(-1, u1, 1)];
    o.quad(q, [-1, 0, 0], q.map((v) => [v[2], v[1]]), BuildingMat.Oak, j === NU - 1 ? p.strake : p.hull);
  }
  // The inside of the rail (bulwark) above each deck, and the cap along its top.
  const floorAt = (a: number) => { for (const c of [p.aft, p.fore]) if (c && a >= c.a0 - 1e-6 && a <= c.a1 + 1e-6) return c.y; return p.deckY; };
  for (const side of [1, -1]) for (let i = 0; i < NA; i++) {
    const a0 = ts[i] * half, a1 = ts[i + 1] * half, f0 = floorAt(a0), f1 = floorAt(a1);
    const s0 = sheerAt(p, ts[i]), s1 = sheerAt(p, ts[i + 1]);
    const w0 = halfAtDeck(p, ts[i]) - INNER, w1 = halfAtDeck(p, ts[i + 1]) - INNER;
    if (w0 <= 0.05 && w1 <= 0.05) continue;
    // At its foot, the deck's own edge (where the hull still narrows below the rail, as up a castle near the bow), so
    // no sliver of the sea shows between the deck and the rail.
    const d0 = Math.max(0, hullHalf(p, a0, f0) - INNER), d1 = Math.max(0, hullHalf(p, a1, f1) - INNER);
    if (port(i)) {
      // The gangway: the deck's edge planked over, the rail's cut ends faced.
      const e = [[a0, f0, side * w0], [a1, f1, side * w1], [a1, f1, side * (w1 + INNER)], [a0, f0, side * (w0 + INNER)]];
      o.quad(e, [0, 1, 0], e.map((v) => [v[0], v[2]]), BuildingMat.Oak, DECK_DARK);
      for (const [k, dir] of [[i, -1], [i + 1, 1]] as const) {
        const ak = ts[k] * half, sk = sheerAt(p, ts[k]), wk = halfAtDeck(p, ts[k]);
        const neighbour = dir < 0 ? port(i - 1) : port(i + 1);
        if (neighbour) continue;
        const c = [[ak, f0, side * (wk - INNER)], [ak, f0, side * wk], [ak, sk + 0.06, side * wk], [ak, sk + 0.06, side * (wk - INNER)]];
        o.quad(c, [-dir, 0, 0], c.map((v) => [v[2], v[1]]), BuildingMat.Oak, p.hull);
      }
      continue;
    }
    const q = [[a0, f0, side * d0], [a1, f1, side * d1], [a1, s1, side * w1], [a0, s0, side * w0]];
    o.quad(q, [0, 0, -side], q.map((v) => [v[0], v[1]]), BuildingMat.Oak, p.hull);
    const cap = [[a0, s0 + 0.06, side * (w0 + INNER + 0.04)], [a1, s1 + 0.06, side * (w1 + INNER + 0.04)], [a1, s1 + 0.06, side * (w1 - 0.04)], [a0, s0 + 0.06, side * (w0 - 0.04)]];
    o.quad(cap, [0, 1, 0], cap.map((v) => [v[0], v[2]]), BuildingMat.Oak, DECK_DARK);
  }
  // Decks: the main deck between the castles (round the hatch and the companionway), the castles' decks over them.
  const deckStrip = (a0: number, a1: number, fy: number, holes: readonly Hole[] = [], down = false, ww = fy, at0: readonly number[] = []) => {
    const n = Math.max(1, Math.ceil((a1 - a0) / 1.2)), cuts = new Set<number>();
    for (let i = 0; i <= n; i++) cuts.add(a0 + ((a1 - a0) * i) / n);
    for (const h of holes) for (const e of [h.a0, h.a1]) if (e > a0 && e < a1) cuts.add(e);
    // (And at the rail's panels: their edges meet it along the same straight pieces.)
    for (const t of ts) if (t * half > a0 + 0.05 && t * half < a1 - 0.05) cuts.add(t * half);
    // (And at `at0`: a lining's stations under it, so its edge never falls inside the lining's.)
    for (const e of at0) if (e > a0 && e < a1) cuts.add(e);
    const at = [...cuts].sort((q, w) => q - w);
    for (let i = 0; i + 1 < at.length; i++) {
      const b0 = at[i], b1 = at[i + 1];
      const w0 = Math.max(0, hullHalf(p, b0, ww) - INNER), w1 = Math.max(0, hullHalf(p, b1, ww) - INNER);
      if (w0 + w1 < 0.1) continue;
      const strip = (z0a: number, z0b: number, z1a: number, z1b: number) => {
        if (z1a - z0a < 1e-3 && z1b - z0b < 1e-3) return;
        const q = [[b0, fy, z0a], [b1, fy, z0b], [b1, fy, z1b], [b0, fy, z1a]];
        o.quad(q, [0, down ? -1 : 1, 0], q.map((v) => [v[0], v[2]]), BuildingMat.Oak, down ? DECK_DARK : DECK);
      };
      // Across it, the deck less the holes over this stretch (each from b0 to b1).
      const gaps = holes.filter((h) => h.a0 <= b0 + 1e-6 && h.a1 >= b1 - 1e-6).sort((q, w) => q.b0 - w.b0);
      let fromA = -w0, fromB = -w1;
      for (const g of gaps) { strip(fromA, fromB, Math.max(fromA, g.b0), Math.max(fromB, g.b0)); fromA = Math.min(w0, g.b1); fromB = Math.min(w1, g.b1); }
      strip(fromA, fromB, w0, w1);
    }
  };
  const mainA0 = p.aft ? p.aft.a1 : -half, mainA1 = p.fore ? p.fore.a0 : half;
  const holes: Hole[] = [];
  if (p.hatch) holes.push({ a0: p.hatch.a0, a1: p.hatch.a1, b0: -p.hatch.half, b1: p.hatch.half });
  if (p.companion) holes.push(p.companion);
  deckStrip(mainA0, mainA1, p.deckY, holes);
  const ladders = shipLadders(p), outsCabins: Out[] = [];
  for (const c of [p.aft, p.fore]) if (c) {
    // (From its front wall forward; aft, just inside the transom.)
    const d0 = c === p.aft ? c.a0 + 0.05 : c.a0;
    deckStrip(d0, c.a1, c.y);
    // Its front to the main deck: a bulkhead with a door (the captain's cabin aft, the crew's forward).
    const face = c === p.aft ? c.a1 : c.a0, dir = c === p.aft ? 1 : -1, w = hullHalf(p, face, c.y) - INNER;
    const door = DOOR, top = c.y;
    // (Both its faces: the cabin behind it is walked in. Its door stands open, a fixture of the cabin.)
    const wall = (b0: number, b1: number, y0: number, y1: number) => {
      const q = [[face, y0, b0], [face, y0, b1], [face, y1, b1], [face, y1, b0]];
      o.quad(q, [dir, 0, 0], q.map((v) => [v[2], v[1]]), BuildingMat.Oak, DECK_DARK);
      o.quad(q, [-dir, 0, 0], q.map((v) => [v[2], v[1]]), BuildingMat.Oak, DECK_DARK);
    };
    wall(-w, -door, p.deckY, top);
    wall(door, w, p.deckY, top);
    wall(-door, door, p.deckY + 1.95, top);
    if (detail) cabin(o, p, c, x, z, ux, uz, y, origin, outsCabins);
    // A rail along the castle's front edge, and a ladder up beside the door.
    for (const s of [1, -1]) beam(o, [face, c.y + 0.9, s * (door + 0.9)], [face, c.y + 0.9, s * (w - 0.05)], 0.04, DECK_DARK);
    if (detail) ladder(o, ladders[c === p.aft ? 0 : 1]);
    // Its underside: the cabin's ceiling below it (drawn with the cabin, along its own lining's pieces).
    if (!detail) deckStrip(d0, c.a1, c.y - 0.08, [], true);
  }
  // The lower deck under the main deck, its ceiling the main deck's underside; the companionway down to it.
  if (detail && p.hold) {
    const h = p.hold, n = holdStations(h);
    deckStrip(mainA0, mainA1, p.deckY - 0.06, holes, true, p.deckY, Array.from({ length: n + 1 }, (_, i) => h.a0 + ((h.a1 - h.a0) * i) / n));
    lowerDeck(o, p, x, z, ux, uz, y, origin, outsCabins);
  }
  if (detail && p.companion) {
    const cw = p.companion, ry = p.deckY + 0.9;
    for (const [a0, a1, b0, b1] of companionRails(cw)) {
      o.box(a0, a1, p.deckY, p.deckY + 0.12, b0, b1, BuildingMat.Oak, DECK_DARK);
      o.box(a0, a1, ry - 0.05, ry, b0, b1, BuildingMat.Oak, DECK_DARK, true);
    }
    for (const [pa, pb] of [[cw.a0, cw.b0], [cw.a0, cw.b1], [cw.a1, cw.b0], [cw.a1, cw.b1]]) o.box(pa - 0.04, pa + 0.04, p.deckY, ry, pb - 0.04, pb + 0.04, BuildingMat.Oak, DECK_DARK);
    ladder(o, ladders[2]);
  }
  // The stern: cabin windows across the transom, a lantern over it.
  if (p.aft) {
    for (const b of [-0.9, 0, 0.9]) o.box(-half - 0.06, -half + 0.02, p.aft.y - 1.3, p.aft.y - 0.5, b - 0.32, b + 0.32, BuildingMat.Glass, GLASS);
    const ly = sheerAt(p, -1);
    o.box(-half - 0.2, -half + 0.2, ly, ly + 0.15, -0.2, 0.2, BuildingMat.Slate, IRON);
    o.box(-half - 0.15, -half + 0.15, ly + 0.15, ly + 0.6, -0.15, 0.15, BuildingMat.Glass, [238, 196, 120]);
    // The helm on the sterncastle: a wheel on its post.
    const ha = p.aft.a1 - 1.6;
    o.box(ha - 0.1, ha + 0.1, p.aft.y, p.aft.y + 1.0, -0.1, 0.1, BuildingMat.Oak, DECK_DARK);
    if (detail) for (let k = 0; k < 8; k++) {
      const t0 = (k / 8) * Math.PI * 2, t1 = ((k + 1) / 8) * Math.PI * 2, R = 0.5, hy = p.aft.y + 1.05;
      beam(o, [ha + 0.12, hy + Math.sin(t0) * R, Math.cos(t0) * R], [ha + 0.12, hy + Math.sin(t1) * R, Math.cos(t1) * R], 0.03, DECK_DARK);
      beam(o, [ha + 0.12, hy, 0], [ha + 0.12, hy + Math.sin(t0) * (R + 0.14), Math.cos(t0) * (R + 0.14)], 0.018, DECK_DARK);
    }
  }
  // The hatch: a coaming round it and a grating over it.
  if (p.hatch) {
    const h = p.hatch, cy = p.deckY + 0.3;
    for (const s of [1, -1]) {
      o.box(h.a0 - 0.1, h.a1 + 0.1, p.deckY, cy, s * h.half - 0.1, s * h.half + 0.1, BuildingMat.Oak, DECK_DARK);
    }
    for (const a of [h.a0, h.a1]) o.box(a - 0.1, a + 0.1, p.deckY, cy, -h.half, h.half, BuildingMat.Oak, DECK_DARK);
    const g = [[h.a0, cy - 0.05, -h.half], [h.a1, cy - 0.05, -h.half], [h.a1, cy - 0.05, h.half], [h.a0, cy - 0.05, h.half]];
    o.quad(g, [0, 1, 0], g.map((v) => [v[0] * 3, v[2] * 3]), BuildingMat.Oak, TAR);
    // Its underside too: the sea under the deck never shows through it.
    const u = [g[3], g[2], g[1], g[0]];
    o.quad(u, [0, -1, 0], u.map((v) => [v[0] * 3, v[2] * 3]), BuildingMat.Oak, TAR);
  }
  // The boat's thwarts (its benches) and a rudder; the ship's rudder on the stern post.
  if (p.kind === 'boat') {
    for (const f of [-0.45, 0.05, 0.55]) { const a = f * half, w = hullHalf(p, a, p.deckY + 0.3) - INNER; o.box(a - 0.15, a + 0.15, p.deckY + 0.25, p.deckY + 0.32, -w, w, BuildingMat.Oak, DECK_DARK); }
  }
  // The rudder: a blade on the stern post, from the keel up to the rail, its tiller or the helm's rope inboard.
  const rw = p.kind === 'ship' ? 1.1 : 0.45, rt = p.kind === 'ship' ? 0.12 : 0.05;
  o.box(-half - rw, -half - 0.02, -p.draft * 0.95, p.deckY * 0.6, -rt, rt, BuildingMat.Oak, p.hull, true);
  o.box(-half - 0.25, -half - 0.02, p.deckY * 0.6, p.railY, -rt, rt, BuildingMat.Oak, p.hull);
  // The bowsprit out over the stem (a boat's is a short stub for the stay).
  const stemTop = sheerAt(p, 1);
  const spritEnd = p.kind === 'ship' ? [half + p.length * 0.22, stemTop + p.length * 0.1, 0] : [half + 0.6, stemTop + 0.15, 0];
  beam(o, [half - (p.kind === 'ship' ? 1.5 : 0.5), stemTop - 0.1, 0], spritEnd, p.kind === 'ship' ? 0.13 : 0.04, DECK_DARK);
  // Masts, yards, sails and rigging.
  const outs = [o, ...outsCabins];
  for (const [mi, m] of p.masts.entries()) {
    const R = (p.kind === 'ship' ? 0.24 : 0.08) * (mi === 0 ? 1 : 0.85);
    beam(o, [m.a, (p.hold && m.foot === p.deckY ? p.hold.y : m.foot) - 0.2, 0], [m.a, m.top, 0], R, DECK_DARK);
    // The main mast's top: a round platform for the lookout.
    if (mi === 0 && p.kind === 'ship') {
      const ty = m.yards[0].y + 1.2;
      for (let k = 0; k < 8; k++) {
        const t0 = (k / 8) * Math.PI * 2, t1 = ((k + 1) / 8) * Math.PI * 2, rr = 1.3;
        const q = [[m.a, ty, 0], [m.a + Math.cos(t0) * rr, ty, Math.sin(t0) * rr], [m.a + Math.cos(t1) * rr, ty, Math.sin(t1) * rr]];
        o.tri(q, [0, 1, 0], q.map((v) => [v[0], v[2]]), BuildingMat.Oak, DECK_DARK);
        o.tri(q, [0, -1, 0], q.map((v) => [v[0], v[2]]), BuildingMat.Oak, DECK_DARK);
        o.quad([[m.a + Math.cos(t0) * rr, ty, Math.sin(t0) * rr], [m.a + Math.cos(t1) * rr, ty, Math.sin(t1) * rr], [m.a + Math.cos(t1) * rr, ty + 0.5, Math.sin(t1) * rr], [m.a + Math.cos(t0) * rr, ty + 0.5, Math.sin(t0) * rr]], [Math.cos((t0 + t1) / 2), 0, Math.sin((t0 + t1) / 2)], [[0, 0], [1, 0], [1, 0.5], [0, 0.5]], BuildingMat.Oak, DECK_DARK);
      }
    }
    for (const [yi, yd] of m.yards.entries()) {
      beam(o, [m.a + R + 0.1, yd.y, -yd.half], [m.a + R + 0.1, yd.y, yd.half], R * 0.45, DECK_DARK);
      // The sail hangs from this yard down to the next below (or over the deck).
      const below = m.yards[yi - 1]?.y ?? m.foot + (p.kind === 'ship' ? 2.6 : 0.9);
      const lowerHalf = m.yards[yi - 1]?.half ?? yd.half * 1.05;
      if (sails === 'set') outs.push(sail(p, m.a + R + 0.2, yd.y - 0.15, below + 0.2, yd.half * 0.96, lowerHalf * 0.96, x, z, ux, uz, y, origin));
      else beam(o, [m.a + R + 0.4, yd.y - 0.3, -yd.half * 0.9], [m.a + R + 0.4, yd.y - 0.3, yd.half * 0.9], R * 1.15, LINEN, BuildingMat.Plaster);
    }
    if (!detail) continue;
    // Shrouds from below the first yard down to the rail on both sides; a stay forward.
    const hy = m.yards[0].y - 0.4;
    for (const side of [1, -1]) for (const da of [-0.9, 0, 0.9]) {
      const fa = m.a + da - 0.6, fy = sheerAt(p, (fa / p.length) * 2);
      beam(o, [m.a, hy, 0], [fa, fy, side * (halfAtDeck(p, (fa / p.length) * 2) + 0.05)], 0.025, ROPE);
    }
    const next = p.masts.filter((n) => n.a > m.a).sort((q, w) => q.a - w.a)[0];
    beam(o, [m.a, m.top - 0.3, 0], next ? [next.a, next.foot + 1, 0] : spritEnd, 0.03, ROPE);
  }
  return mergeOuts(outs);
}

/**
 * A gangplank `length` long, from its foot at the origin up along +a (its frame: `a` along it, `b` across, `y` up),
 * its top face at y = 0: planks with cleats across them to tread on. Laid from the quay to a ship's gangway.
 */
export function gangplankMesh(length: number): BuildingMesh {
  const o = new Out(new Frame({ cx: 0, cz: 0, ux: 1, uz: 0, vx: 0, vz: 1, y: 0 }, [0, 0, 0]));
  o.box(0, length, -0.07, 0, -PLANK, PLANK, BuildingMat.Oak, DECK, true);
  for (let a = 0.25; a < length - 0.1; a += 0.4) o.box(a - 0.03, a + 0.03, 0, 0.035, -PLANK + 0.04, PLANK - 0.04, BuildingMat.Oak, DECK_DARK);
  return mergeOuts([o]);
}
/** Half a gangplank's width (m). */
export const PLANK = 0.34;

/** A sail full of wind between its yard (yT, half hT) and the yard or deck below (yB, half hB), bellied forward. */
function sail(p: ShipPlan, a: number, yT: number, yB: number, hT: number, hB: number, x: number, z: number, ux: number, uz: number, y: number, origin: [number, number, number]): Out {
  const o = new Out(new Frame({ cx: x, cz: z, ux, uz, vx: -uz, vz: ux, y }, origin));
  const NU = 6, NV = 5, belly = Math.min(hT, yT - yB) * 0.22;
  const at = (i: number, j: number) => {
    const u = i / NU, v = j / NV, hh = hT + (hB - hT) * v, bulge = Math.sin(Math.PI * u) * Math.sin(Math.PI * Math.min(1, v * 1.15)) * belly;
    return [a + bulge, yT + (yB - yT) * v, -hh + 2 * hh * u];
  };
  for (let i = 0; i < NU; i++) for (let j = 0; j < NV; j++) {
    const q = [at(i, j), at(i + 1, j), at(i + 1, j + 1), at(i, j + 1)], uv = q.map((v) => [v[2], v[1]]);
    const n = faceNormal(q, [1, 0, 0]);
    // Both faces: a sail is seen from either side.
    o.quad(q, n, uv, BuildingMat.Plaster, LINEN);
    o.quad(q, [-n[0], -n[1], -n[2]], uv, BuildingMat.Plaster, [204, 194, 170]);
  }
  void p;
  return o;
}

/**
 * A castle's cabin, on the main deck under its deck: the floor, its sides planked inside (and the transom aft, under
 * the stern windows), a lantern hung from the beams, what stands in it (shipFixtures); a stove's pipe out through the
 * deck above. Its fixtures go in an Out of their own, from the main deck up.
 */
function cabin(o: Out, p: ShipPlan, c: Castle, x: number, z: number, ux: number, uz: number, y: number, origin: [number, number, number], outs: Out[]): void {
  const half = p.length / 2, aft = c === p.aft, ceil = c.y - 0.08, n = Math.max(2, Math.ceil((c.a1 - c.a0) / 0.8));
  const a0 = aft ? Math.max(c.a0, -half + 0.12) : c.a0;
  const w = (a: number, h: number) => Math.max(0, hullHalf(p, a, h) - INNER), mid = (p.deckY + ceil) / 2;
  let end = a0;
  for (let i = 0; i < n; i++) {
    const b0 = a0 + ((c.a1 - a0) * i) / n, b1 = a0 + ((c.a1 - a0) * (i + 1)) / n;
    if (w(b0, p.deckY) + w(b1, p.deckY) < 0.1) continue;
    end = b1;
    const fl = [[b0, p.deckY, -w(b0, p.deckY)], [b1, p.deckY, -w(b1, p.deckY)], [b1, p.deckY, w(b1, p.deckY)], [b0, p.deckY, w(b0, p.deckY)]];
    o.quad(fl, [0, 1, 0], fl.map((v) => [v[0], v[2]]), BuildingMat.Oak, DECK);
    // The ceiling, the castle deck's underside, along the same pieces as the lining (no seam of the sea between).
    const ce = [fl[3], fl[2], fl[1], fl[0]].map((v) => [v[0], ceil, Math.sign(v[2]) * w(v[0], ceil)]);
    o.quad(ce, [0, -1, 0], ce.map((v) => [v[0], v[2]]), BuildingMat.Oak, DECK_DARK);
    // The sides, in two bands (the hull flares out going up).
    for (const side of [1, -1]) for (const [h0, h1] of [[p.deckY, mid], [mid, ceil]]) {
      const q = [[b0, h0, side * w(b0, h0)], [b1, h0, side * w(b1, h0)], [b1, h1, side * w(b1, h1)], [b0, h1, side * w(b0, h1)]];
      o.quad(q, [0, 0, -side], q.map((v) => [v[0], v[1]]), BuildingMat.Oak, DECK_DARK);
    }
  }
  // Forward, where the bow closes in under the floor: a bulkhead across the cabin's end.
  if (!aft && end < c.a1 - 1e-6) for (const [h0, h1] of [[p.deckY, mid], [mid, ceil]]) {
    const q = [[end, h0, w(end, h0)], [end, h0, -w(end, h0)], [end, h1, -w(end, h1)], [end, h1, w(end, h1)]];
    o.quad(q, [-1, 0, 0], q.map((v) => [v[2], v[1]]), BuildingMat.Oak, DECK_DARK);
  }
  if (aft) {
    const wa = Math.max(0, hullHalf(p, a0, ceil) - INNER), q = [[a0, p.deckY, -wa], [a0, p.deckY, wa], [a0, ceil, wa], [a0, ceil, -wa]];
    o.quad(q, [1, 0, 0], q.map((v) => [v[2], v[1]]), BuildingMat.Oak, DECK_DARK);
    // The stern windows, from inside.
    for (const b of [-0.9, 0, 0.9]) o.box(a0, a0 + 0.03, c.y - 1.3, c.y - 0.5, b - 0.32, b + 0.32, BuildingMat.Glass, GLASS);
  }
  const fx = new Out(new Frame({ cx: x, cz: z, ux, uz, vx: -uz, vz: ux, y: y + p.deckY }, origin)), H = ceil - p.deckY;
  for (const f of shipFixtures(p)) {
    if (f.a < c.a0 || f.a > c.a1) continue;
    drawFixture(fx, f, H);
    if (f.kind === 'table' && aft) fx.box(f.a - 0.3, f.a + 0.25, f.h, f.h + 0.01, f.b - 0.4, f.b + 0.35, BuildingMat.Plaster, CHART);
    if (f.kind === 'oven') beam(o, [f.a, p.deckY + H, f.b], [f.a, c.y + 0.8, f.b], 0.09, IRON, BuildingMat.Slate);
  }
  // The lantern over the middle of the cabin.
  const la = (c.a0 + c.a1) / 2 + (aft ? 0.6 : -0.6);
  beam(o, [la, ceil, 0], [la, ceil - 0.35, 0], 0.012, IRON, BuildingMat.Slate);
  o.box(la - 0.09, la + 0.09, ceil - 0.62, ceil - 0.35, -0.09, 0.09, BuildingMat.Glass, [238, 196, 120], true);
  outs.push(fx);
}

/** The companionway's rails (a0, a1, b0, b1): aft of it and along both its sides. */
function companionRails(cw: Hole): [number, number, number, number][] {
  return [[cw.a0 - 0.05, cw.a0, cw.b0 - 0.05, cw.b1 + 0.05], [cw.a0, cw.a1, cw.b0 - 0.05, cw.b0], [cw.a0, cw.a1, cw.b1, cw.b1 + 0.05]];
}

/** How many pieces the lower deck's lining is drawn in, along the ship (the ceiling over it is cut at the same stations). */
const holdStations = (h: { a0: number; a1: number }) => Math.max(2, Math.ceil((h.a1 - h.a0) / 0.8));

/** An opening in a deck: a0..a1 along, b0..b1 across. */
interface Hole { a0: number; a1: number; b0: number; b1: number }

/**
 * The lower deck: its floor, the hull planked inside, its ends, the beams under the main deck, the cabins' walls, what
 * stands on it (shipHold) and its lanterns. The fixtures go in an Out of their own, from its floor up.
 */
function lowerDeck(o: Out, p: ShipPlan, x: number, z: number, ux: number, uz: number, y: number, origin: [number, number, number], outs: Out[]): void {
  const h = p.hold!, top = p.deckY - 0.06, n = holdStations(h);
  const w = (a: number, hh: number) => Math.max(0, hullHalf(p, a, hh) - INNER);
  const bands = [h.y, h.y + (top - h.y) / 3, h.y + (2 * (top - h.y)) / 3, top];
  for (let i = 0; i < n; i++) {
    const b0 = h.a0 + ((h.a1 - h.a0) * i) / n, b1 = h.a0 + ((h.a1 - h.a0) * (i + 1)) / n;
    const fl = [[b0, h.y, -w(b0, h.y)], [b1, h.y, -w(b1, h.y)], [b1, h.y, w(b1, h.y)], [b0, h.y, w(b0, h.y)]];
    o.quad(fl, [0, 1, 0], fl.map((v) => [v[0], v[2]]), BuildingMat.Oak, DECK);
    for (const side of [1, -1]) for (let k = 0; k < 3; k++) {
      const h0 = bands[k], h1 = bands[k + 1];
      const q = [[b0, h0, side * w(b0, h0)], [b1, h0, side * w(b1, h0)], [b1, h1, side * w(b1, h1)], [b0, h1, side * w(b0, h1)]];
      o.quad(q, [0, 0, -side], q.map((v) => [v[0], v[1]]), BuildingMat.Oak, DECK_DARK);
    }
  }
  // Its ends: the bulkheads fore and aft.
  for (const [a, dir] of [[h.a0, 1], [h.a1, -1]] as const) {
    const q = [[a, h.y, -w(a, h.y)], [a, h.y, w(a, h.y)], [a, top, w(a, top)], [a, top, -w(a, top)]];
    o.quad(q, [dir, 0, 0], q.map((v) => [v[2], v[1]]), BuildingMat.Oak, DECK_DARK);
  }
  // The beams under the main deck, across it.
  for (let a = h.a0 + 0.55; a < h.a1 - 0.2; a += 1.1) o.box(a - 0.08, a + 0.08, top - 0.16, top, -w(a, top), w(a, top), BuildingMat.Oak, DECK_DARK, true);
  const H = shipHold(p);
  for (const wl of H.walls) o.box(wl.a0, wl.a1, h.y, top, wl.b0, wl.b1, BuildingMat.Oak, DECK, true);
  const fx = new Out(new Frame({ cx: x, cz: z, ux, uz, vx: -uz, vz: ux, y: y + h.y }, origin));
  for (const f of H.fixtures) drawFixture(fx, f, top - h.y);
  for (const [la, lb] of H.lamps) {
    beam(o, [la, top - 0.16, lb], [la, top - 0.45, lb], 0.012, IRON, BuildingMat.Slate);
    o.box(la - 0.09, la + 0.09, top - 0.72, top - 0.45, lb - 0.09, lb + 0.09, BuildingMat.Glass, [238, 196, 120], true);
  }
  outs.push(fx);
}

/** A ladder up a castle's front: its stiles (on past the top, to hold on by), its rungs. */
function ladder(o: Out, l: ShipLadder): void {
  const H = l.y1 - l.y0, slope = l.lean / H, top = H + 0.6;
  for (const s of [-0.25, 0.25]) beam(o, [l.a, l.y0, l.b + s], [l.a - l.dir * slope * top, l.y0 + top, l.b + s], 0.035, DECK_DARK);
  const n = Math.round(H / l.rung);
  for (let k = 1; k < n; k++) {
    const h = k * l.rung, ra = l.a - l.dir * slope * h;
    beam(o, [ra, l.y0 + h, l.b - 0.25], [ra, l.y0 + h, l.b + 0.25], 0.022, DECK_DARK);
  }
}

/** A quad's normal, turned to the side of `toward`. */
function faceNormal(q: number[][], toward: number[]): number[] {
  const e1 = [q[2][0] - q[0][0], q[2][1] - q[0][1], q[2][2] - q[0][2]], e2 = [q[3][0] - q[1][0], q[3][1] - q[1][1], q[3][2] - q[1][2]];
  let n = [e1[1] * e2[2] - e1[2] * e2[1], e1[2] * e2[0] - e1[0] * e2[2], e1[0] * e2[1] - e1[1] * e2[0]];
  const l = Math.hypot(n[0], n[1], n[2]) || 1;
  n = n.map((v) => v / l);
  return n[0] * toward[0] + n[1] * toward[1] + n[2] * toward[2] < 0 ? n.map((v) => -v) : n;
}
