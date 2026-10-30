/**
 * Ships for the harbours and the seas: a sailing ship with a forecastle, a sterncastle over the captain's cabin,
 * masts, yards, sails set or furled and the rigging, and a fishing boat with one mast. Seeded and pure; one planner,
 * a bigger ship only longer and with more masts. The plan says where its floors are (for walking on its decks), the
 * mesh draws it in its own frame: `a` along it (bow +a), `y` up from the waterline, `b` across (port, its left, +b).
 */
import { Rng } from '@futuremagic/core';
import { BuildingMat, Frame, Out, beam, mergeOuts, type BuildingMesh, type RGB } from './building';

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
  /** The hatch down to the hold, on the main deck (a0..a1 along, half across); null on a boat. */
  hatch: { a0: number; a1: number; half: number } | null;
  /** Hull colours: planking, the painted strake under the rail. */
  hull: RGB;
  strake: RGB;
}

const SHIP_MIN = 20, SHIP_MAX = 34, BOAT_MIN = 6.5, BOAT_MAX = 9.5;

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
  const hatch = kind === 'ship' ? { a0: -half * 0.25, a1: -half * 0.08, half: B * 0.16 } : null;
  const hull = r.pick<RGB>([[92, 66, 44], [78, 58, 42], [104, 78, 52]]);
  const strake = r.pick<RGB>([[120, 42, 34], [36, 58, 92], [44, 76, 52], [160, 128, 60]]);
  return { kind, seed, length: L, beam: B, draft, deckY, railY, aft, fore, masts, hatch, hull, strake };
}

/** Half the hull's width at `a` along it and `y` over the waterline (0 outside the hull). */
export function hullHalf(p: ShipPlan, a: number, y: number): number {
  const t = (a / p.length) * 2;
  if (t <= -1 || t >= 1) return 0;
  const k = keelAt(p, t), s = sheerAt(p, t);
  if (y < k || y > s + 1e-6) return 0;
  return halfAtDeck(p, t) * section((y - k) / (s - k));
}

/** The floor at (a, b) on the ship's decks (null: no floor there, over the side or in the hatch). */
export function shipFloor(p: ShipPlan, a: number, b: number): number | null {
  for (const c of [p.aft, p.fore]) if (c && a >= c.a0 && a <= c.a1) return Math.abs(b) <= hullHalf(p, a, c.y) - INNER ? c.y : null;
  if (p.hatch && a >= p.hatch.a0 && a <= p.hatch.a1 && Math.abs(b) <= p.hatch.half) return null;
  return Math.abs(b) <= hullHalf(p, a, p.deckY) - INNER ? p.deckY : null;
}

/** The planking's thickness inside the hull (m). */
const INNER = 0.18;

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
const IRON: RGB = [62, 62, 66], TAR: RGB = [40, 34, 28], GLASS: RGB = [70, 86, 96];

/**
 * The ship's mesh at (x, z) heading along (ux, uz), its waterline at `y`, relative to `origin`. `sails`: 'set' draws
 * the sails full of wind, 'furled' bundled on their yards. `detail` false leaves out the rigging, rungs and fittings.
 */
export function shipMesh(p: ShipPlan, x: number, z: number, ux: number, uz: number, y: number, origin: [number, number, number], sails: 'set' | 'furled' = 'furled', detail = true): BuildingMesh {
  const o = new Out(new Frame({ cx: x, cz: z, ux, uz, vx: -uz, vz: ux, y }, origin));
  const half = p.length / 2, NA = p.kind === 'ship' ? 28 : 16, NU = p.kind === 'ship' ? 9 : 6;
  const ts = Array.from({ length: NA + 1 }, (_, i) => -1 + (2 * i) / NA);
  // The hull's skin, port and starboard, in strips from keel to rail; the strake under the rail painted.
  const P = (t: number, u: number, side: number): number[] => {
    const k = keelAt(p, t), s = sheerAt(p, t);
    return [t * half, k + (s - k) * u, side * halfAtDeck(p, t) * section(u)];
  };
  for (const side of [1, -1]) for (let i = 0; i < NA; i++) for (let j = 0; j < NU; j++) {
    const u0 = j / NU, u1 = (j + 1) / NU;
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
    const q = [[a0, f0, side * w0], [a1, f1, side * w1], [a1, s1, side * w1], [a0, s0, side * w0]];
    o.quad(q, [0, 0, -side], q.map((v) => [v[0], v[1]]), BuildingMat.Oak, p.hull);
    const cap = [[a0, s0 + 0.06, side * (w0 + INNER + 0.04)], [a1, s1 + 0.06, side * (w1 + INNER + 0.04)], [a1, s1 + 0.06, side * (w1 - 0.04)], [a0, s0 + 0.06, side * (w0 - 0.04)]];
    o.quad(cap, [0, 1, 0], cap.map((v) => [v[0], v[2]]), BuildingMat.Oak, DECK_DARK);
  }
  // Decks: the main deck between the castles (round the hatch), the castles' decks over them.
  const deckStrip = (a0: number, a1: number, fy: number, hole?: { a0: number; a1: number; half: number }, down = false) => {
    const n = Math.max(1, Math.ceil((a1 - a0) / 1.2));
    for (let i = 0; i < n; i++) {
      const b0 = a0 + ((a1 - a0) * i) / n, b1 = a0 + ((a1 - a0) * (i + 1)) / n;
      const w0 = Math.max(0, hullHalf(p, b0, fy) - INNER), w1 = Math.max(0, hullHalf(p, b1, fy) - INNER);
      if (w0 + w1 < 0.1) continue;
      const strip = (z0a: number, z0b: number, z1a: number, z1b: number) => {
        const q = [[b0, fy, z0a], [b1, fy, z0b], [b1, fy, z1b], [b0, fy, z1a]];
        o.quad(q, [0, down ? -1 : 1, 0], q.map((v) => [v[0], v[2]]), BuildingMat.Oak, down ? DECK_DARK : DECK);
      };
      if (hole && b1 > hole.a0 && b0 < hole.a1) { strip(-w0, -w1, -hole.half, -hole.half); strip(hole.half, hole.half, w0, w1); }
      else strip(-w0, -w1, w0, w1);
    }
  };
  const mainA0 = p.aft ? p.aft.a1 : -half, mainA1 = p.fore ? p.fore.a0 : half;
  deckStrip(mainA0, mainA1, p.deckY, p.hatch ?? undefined);
  for (const c of [p.aft, p.fore]) if (c) {
    deckStrip(c.a0 + 0.05, c.a1, c.y);
    // Its front to the main deck: a bulkhead with a door (the captain's cabin aft, the crew's forward).
    const face = c === p.aft ? c.a1 : c.a0, dir = c === p.aft ? 1 : -1, w = hullHalf(p, face, c.y) - INNER;
    const door = 0.55, top = c.y;
    const wall = (b0: number, b1: number, y0: number, y1: number) => { const q = [[face, y0, b0], [face, y0, b1], [face, y1, b1], [face, y1, b0]]; o.quad(q, [dir, 0, 0], q.map((v) => [v[2], v[1]]), BuildingMat.Oak, DECK_DARK); };
    wall(-w, -door, p.deckY, top);
    wall(door, w, p.deckY, top);
    wall(-door, door, p.deckY + 1.95, top);
    // The door itself, shut, a little in.
    const dq = [[face - dir * 0.05, p.deckY, -door], [face - dir * 0.05, p.deckY, door], [face - dir * 0.05, p.deckY + 1.95, door], [face - dir * 0.05, p.deckY + 1.95, -door]];
    o.quad(dq, [dir, 0, 0], dq.map((v) => [v[2], v[1]]), BuildingMat.Oak, p.hull);
    // A rail along the castle's front edge, and a ladder up beside the door.
    for (const s of [1, -1]) beam(o, [face, c.y + 0.9, s * (door + 0.9)], [face, c.y + 0.9, s * (w - 0.05)], 0.04, DECK_DARK);
    if (detail) ladder(o, face + dir * 0.45, p.deckY, c.y, door + 0.45, dir);
    // Its underside: the cabin's ceiling below it.
    deckStrip(c.a0 + 0.05, c.a1, c.y - 0.08, undefined, true);
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
  const outs = [o];
  for (const [mi, m] of p.masts.entries()) {
    const R = (p.kind === 'ship' ? 0.24 : 0.08) * (mi === 0 ? 1 : 0.85);
    beam(o, [m.a, m.foot - 0.2, 0], [m.a, m.top, 0], R, DECK_DARK);
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

/** A ladder against a castle's front at `a`, from `y0` up to `y1`, its middle `b` across, leaning away by `dir`. */
function ladder(o: Out, a: number, y0: number, y1: number, b: number, dir: number): void {
  const lean = 0.35;
  for (const s of [-0.25, 0.25]) beam(o, [a + dir * lean, y0, b + s], [a, y1 + 0.6, b + s], 0.035, DECK_DARK);
  const n = Math.max(3, Math.round((y1 - y0) / 0.3));
  for (let k = 1; k < n; k++) {
    const f = k / n, ra = a + dir * lean * (1 - f), ry = y0 + (y1 - y0) * f;
    beam(o, [ra, ry, b - 0.25], [ra, ry, b + 0.25], 0.022, DECK_DARK);
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
