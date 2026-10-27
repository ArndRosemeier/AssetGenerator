/**
 * The inside of a town building, every storey of it: rooms the size of each storey's walls (jettied ones
 * wider), the stairs up, the hearth under the chimney, the fixtures (tables and benches, a counter, a
 * forge and anvil, beds, chests ...) by the building's kind, and the places people use them (spots, like
 * the town's fixtures). It reads the same `houseShape` as the outside, so the storeys, windows and chimney
 * match what is seen from the street. Pure; `interiorMesh` draws it with the building's materials, to be
 * merged with the open building (`buildingMesh(b, origin, true, { open: true })`) in its place.
 *
 * Coordinates: the building's own frame, metres. a runs along the street front (u), b from the street
 * into the plot (v), y up from the building's floor (`floorY`); (0, 0) is the footprint's middle, the door
 * in the front wall (b = -hb) at a = 0.
 */
import { Rng } from '@futuremagic/core';
import { BuildingMat, Frame, houseShape, Out, planeUV, roundShield, WALL_THICK, type BuildingMesh, type HouseShape, type RGB } from './building';
import type { TownBuilding } from './town';

export type InteriorFixtureKind =
  | 'table' | 'bench' | 'counter' | 'barrel' | 'hearth' | 'bed' | 'chest' | 'shelf'
  | 'forge' | 'anvil' | 'tub' | 'workbench' | 'woodpile' | 'oven' | 'basin'
  /** A hall's weapon rack against a wall (blades, spears, a shield); a practice post (pell) on the floor. */
  | 'rack' | 'pell'
  /** A trapdoor in the floor (to a cellar): walked over, not round. */
  | 'hatch'
  /** A flight of stairs up to the next storey (walked on); the hole it comes up through (open floor). */
  | 'stair' | 'well'
  /** The rail round a stair's hole; the chimney breast on the storeys above the hearth; the open door. */
  | 'rail' | 'flue' | 'door';

/** A fixture: an axis-aligned block (in the building's frame) from its storey's floor up. */
export interface InteriorFixture {
  readonly kind: InteriorFixtureKind;
  /** The storey it stands on (0: the ground floor). */
  readonly storey: number;
  /** Middle, metres. */
  readonly a: number;
  readonly b: number;
  /** Extent along a and b, height. */
  readonly w: number;
  readonly d: number;
  readonly h: number;
}

/** `drill`: a hall's master at the practice post (work, like the smith's). */
export type InteriorSpotKind = 'sit' | 'drink' | 'serve' | 'smith' | 'stoke' | 'quench' | 'craft' | 'bake' | 'sleep' | 'pray' | 'tend' | 'warm' | 'drill';

/** Where someone stands or sits to do something, and which way they face (yaw in the frame: atan2(b, a)). */
export interface InteriorSpot {
  readonly kind: InteriorSpotKind;
  readonly storey: number;
  readonly a: number;
  readonly b: number;
  readonly yaw: number;
}

/** One storey inside: its floor over the building's floor, its clear height, and its walls' inner faces. */
export interface InteriorStorey {
  readonly y: number;
  readonly height: number;
  readonly a0: number; readonly a1: number;
  readonly b0: number; readonly b1: number;
  /** Where one first stands on it: inside the door, or off the top of the stairs. */
  readonly entry: readonly [number, number];
}

/** A flight of stairs from `storey` to the one above: its foot (the first step's front edge, in the middle) and the way up. */
export interface InteriorStair {
  readonly storey: number;
  readonly a: number; readonly b: number;
  /** Unit direction up the flight, along a or b. */
  readonly da: number; readonly db: number;
  readonly w: number;
  readonly steps: number;
  /** Each step's depth and rise. */
  readonly tread: number;
  readonly riser: number;
}

export interface InteriorPlan {
  readonly building: number;
  /** The ground floor's inner half width (along a) and half depth (along b), and its height. */
  readonly ha: number;
  readonly hb: number;
  readonly height: number;
  /** The door's half width (in the front wall, at a = 0) and height. */
  readonly doorW: number;
  readonly doorH: number;
  /** Stone floor (flags) or boards. */
  readonly stoneFloor: boolean;
  readonly storeys: readonly InteriorStorey[];
  readonly stairs: readonly InteriorStair[];
  readonly fixtures: readonly InteriorFixture[];
  readonly spots: readonly InteriorSpot[];
}

/** Wall thickness inside the footprint, metres. */
const WALL = WALL_THICK;
/** A storey's floor stands this far over its walls' foot (boards on joists), its ceiling this far under their top. */
const FLOOR = 0.05;
const CEILING = 0.17;
/** Stairs: width, and a step's depth; the rise is the storey's height over a whole number of steps of about RISER. */
const STAIR_W = 0.9;
const TREAD = 0.22;
const RISER = 0.21;
/** The stair's hole starts this share of the flight up. 0: over the whole flight, since storeys are low
 *  (2.4 m) and a tall body coming down meets the hole's edge with its head a step above where it climbed. */
const WELL_FROM = 0;
/** Facing: towards +a, +b, -a, -b (atan2(b, a)). */
const FACE_A = 0, FACE_B = Math.PI / 2, FACE_NA = Math.PI, FACE_NB = -Math.PI / 2;

/** `hatch`: a trapdoor down to a cellar, on free floor one can walk to. */
/**
 * `hatch`: a trapdoor down to a cellar. `hall`: a house whose ground floor is a hall where fighting is taught
 * (a game's guild house): weapon racks on the walls, a practice post with its master's place, a bench for
 * those who watch; no family table or bed down there (the household lives upstairs).
 */
export function planInterior(b: TownBuilding, opts: { hatch?: boolean; hall?: boolean } = {}): InteriorPlan {
  const S = houseShape(b);
  const ha = Math.max(1.6, b.hu - WALL);
  const door = S.storeys[0].walls.find((w) => w.id === 0)!.opens.find((q) => q.door);
  const doorW = door ? (door.s1 - door.s0) / 2 : 0.55, doorH = door ? door.t1 - FLOOR : 2.05;
  const storeys: InteriorStorey[] = [], stairs: InteriorStair[] = [], fixtures: InteriorFixture[] = [], spots: InteriorSpot[] = [];
  S.storeys.forEach((st, k) => {
    const hb = Math.max(1.6, (st.back - st.front) / 2 - WALL), cb = (st.front + st.back) / 2;
    const y = st.y0 + FLOOR, height = Math.max(2.3, st.y1 - CEILING - y);
    // Off the top of the stairs, or just inside the door.
    const up = stairs.find((s) => s.storey === k - 1);
    const entry: [number, number] = up ? [up.a + up.da * (up.steps * up.tread + 0.5), up.b + up.db * (up.steps * up.tread + 0.5) - cb] : [0, -hb + 0.5];
    const next = S.storeys[k + 1];
    const plan = (stairFirst: boolean): { P: Planner; stair: Omit<InteriorStair, 'storey'> | null } => {
      // Each storey rolls from its own stream (so a second try is the same as a first would be).
      const r = new Rng((b.seed ^ 0x1e7e) + k * 7919);
      const P = new Planner(ha, hb, k === 0, entry);
      P.seeWindows(st, cb, st.y0 - y);
      // The door stands open against the wall inside (two leaves in a wide doorway).
      if (k === 0 && door) {
        const leaves = doorW > 0.8 ? [-1, 1] : [-1], lw = (2 * doorW) / leaves.length;
        for (const s of leaves) P.fixtures.push({ kind: 'door', a: s * (doorW - 0.03), b: -hb + lw / 2, w: 0.06, d: lw, h: doorH });
      }
      if (up) P.well(up, cb);
      if (S.chimney) P.chimney(S, b, k, cb);
      let stair: Omit<InteriorStair, 'storey'> | null = null;
      const climb = () => {
        if (!next) return;
        const nb = (next.back - next.front) / 2 - WALL, ncb = (next.front + next.back) / 2, c = S.chimney;
        // Off the top: on the floor above, clear of the chimney breast there.
        stair = P.stair(r, next.y0 - st.y0, (ta, tb) => Math.abs(tb + cb - ncb) <= nb - 0.3 && !(c && Math.abs(ta - c.a) < 1.0 && Math.abs(tb + cb - c.b) < 1.1));
      };
      if (stairFirst) climb();
      if (k === 0) {
        switch (b.kind) {
          case 'inn': tavern(P, r); break;
          case 'smithy': smithy(P, S.chimney?.a ?? 1.2); break;
          case 'bakery': bakery(P, r); break;
          case 'temple': temple(P, r); break;
          case 'barn': case 'stable': break;
          default: if (opts.hall) hall(P); else home(P, r, b.kind === 'workshop' || b.kind === 'mill' || b.trade !== '');
        }
        if (opts.hatch) P.hatch();
      } else bedroom(P, r, b.kind === 'inn');
      if (!stairFirst) climb();
      return { P, stair };
    };
    // The stairs first, so there is room for them; but the inn's tables first, where the stairs still fit after.
    let tried = plan(!(k === 0 && b.kind === 'inn'));
    if (next && !tried.stair) tried = plan(true);
    const { P, stair } = tried;
    if (stair) stairs.push({ ...(stair as Omit<InteriorStair, 'storey'>), storey: k, b: (stair as InteriorStair).b + cb });
    storeys.push({ y, height, a0: -ha, a1: ha, b0: cb - hb, b1: cb + hb, entry: [entry[0], entry[1] + cb] });
    const reach = P.reach();
    fixtures.push(...P.fixtures.filter((f) => f.kind !== 'keep').map((f) => ({ ...f, kind: f.kind as InteriorFixtureKind, storey: k, b: f.b + cb })));
    // Only the spots one can get to (a table may have shut a hearth's off).
    spots.push(...P.spots.filter((s) => SPOT_RING.some(([da, db]) => reach(s.a + da, s.b + db))).map((s) => ({ ...s, storey: k, b: s.b + cb })));
  });
  const g = storeys[0];
  return {
    building: b.id, ha, hb: g.b1, height: g.height, doorW, doorH,
    stoneFloor: b.kind === 'smithy' || b.kind === 'temple' || b.kind === 'bakery' || b.kind === 'stable' || b.kind === 'barn',
    storeys, stairs, fixtures, spots,
  };
}

/** Where someone could step from to use a spot: on it, or beside it within a metre. */
const SPOT_RING: readonly (readonly [number, number])[] = [[0, 0], ...[0.4, 0.7, 1.0].flatMap((d) => Array.from({ length: 16 }, (_, k) => [d * Math.cos((k * Math.PI) / 8), d * Math.sin((k * Math.PI) / 8)] as const))];

/** The storey a body with its feet at `y` (over the building's floor) is on. */
export function storeyAt(p: InteriorPlan, y: number): number {
  let k = 0;
  for (let i = 1; i < p.storeys.length; i++) if (y >= p.storeys[i].y - 0.3) k = i;
  return k;
}

/** The floor of a storey a person (radius 0.3) can walk to from its entry, on a 0.2 m grid. */
export function reachable(p: InteriorPlan, storey = 0): (a: number, b: number) => boolean {
  const st = p.storeys[storey];
  return reachGrid(st.a0, st.a1, st.b0, st.b1, st.entry, (a, b, r) => interiorBlocked(p, a, b, r, storey, true));
}

/**
 * A person's way (radius `r`) across a storey from `from` to `to`, round the fixtures: a breadth-first search on a
 * 0.2 m grid, pulled straight wherever the floor between two turns is clear. Either end may be where one cannot
 * stand (a seat on a bench, out through the doorway): the way then leaves it for the nearest free floor, and comes to
 * it from the free floor nearest it, within `reach` metres. Flat a, b pairs from `from` to `to` (the ends exact);
 * null when no free floor joins them.
 */
export function roomPath(p: InteriorPlan, from: readonly [number, number], to: readonly [number, number], storey = 0, r = 0.3, reach = 1.2): number[] | null {
  const st = p.storeys[storey], s = 0.2;
  // A little room out past the doorway on the ground floor (one walks in and out through it).
  const a0 = st.a0, b0 = st.b0 - (storey === 0 ? 0.6 : 0);
  const na = Math.ceil((st.a1 - a0) / s), nb = Math.ceil((st.b1 - b0) / s);
  const at = (i: number, j: number): [number, number] => [a0 + (i + 0.5) * s, b0 + (j + 0.5) * s];
  const known = new Int8Array(na * nb);
  const free = (i: number, j: number): boolean => {
    const k = j * na + i;
    if (!known[k]) { const [a, b] = at(i, j); known[k] = interiorBlocked(p, a, b, r, storey, true) ? -1 : 1; }
    return known[k] > 0;
  };
  const cellOf = (a: number, b: number): [number, number] => [Math.floor((a - a0) / s), Math.floor((b - b0) / s)];
  // The start: the free cell nearest `from` (or the next nearest, when that one is shut in, between a bench and the wall).
  const [fi, fj] = cellOf(from[0], from[1]), span = Math.ceil(reach / s);
  const starts: [number, number][] = [];
  for (let j = Math.max(0, fj - span); j <= Math.min(nb - 1, fj + span); j++) {
    for (let i = Math.max(0, fi - span); i <= Math.min(na - 1, fi + span); i++) {
      const [a, b] = at(i, j), d = Math.hypot(a - from[0], b - from[1]);
      if (d <= reach && free(i, j)) starts.push([d, j * na + i]);
    }
  }
  starts.sort((x, y) => x[0] - y[0]);
  const parent = new Int32Array(na * nb).fill(-1);
  let start = -1, end = -1, best = Infinity;
  for (const [, c0] of starts) {
    if (parent[c0] >= 0) continue;
    start = c0;
    parent[c0] = c0;
    const q = [c0];
    best = Infinity;
    for (let h = 0; h < q.length; h++) {
      const c = q[h], i = c % na, j = (c - i) / na;
      const [a, b] = at(i, j), d = Math.hypot(a - to[0], b - to[1]);
      if (d < best) { best = d; end = c; }
      if (d < s * 0.75) break;
      for (const [di, dj] of NEIGHBOURS) {
        const ii = i + di, jj = j + dj;
        if (ii < 0 || jj < 0 || ii >= na || jj >= nb || parent[jj * na + ii] >= 0 || !free(ii, jj)) continue;
        // Diagonally only past two free cells (no cutting a corner).
        if (di && dj && (!free(i + di, j) || !free(i, j + dj))) continue;
        parent[jj * na + ii] = c;
        q.push(jj * na + ii);
      }
    }
    if (best <= reach) break;
  }
  if (best > reach) return null;
  const cells: [number, number][] = [];
  for (let c = end; ; c = parent[c]) {
    const i = c % na;
    cells.push(at(i, (c - i) / na));
    if (c === start) break;
  }
  cells.reverse();
  // Pulled straight: from each turn on to the farthest one in clear sight.
  const clear = (u: readonly [number, number], v: readonly [number, number]): boolean => {
    const n = Math.ceil(Math.hypot(v[0] - u[0], v[1] - u[1]) / 0.04);
    for (let k = 1; k < n; k++) if (interiorBlocked(p, u[0] + ((v[0] - u[0]) * k) / n, u[1] + ((v[1] - u[1]) * k) / n, r, storey, true)) return false;
    return true;
  };
  const out = [from[0], from[1], cells[0][0], cells[0][1]];
  for (let i = 0; i < cells.length - 1;) {
    let k = cells.length - 1;
    while (k > i + 1 && !clear(cells[i], cells[k])) k--;
    out.push(cells[k][0], cells[k][1]);
    if (k === cells.length - 1) break;
    i = k;
  }
  out.push(to[0], to[1]);
  return out;
}

const NEIGHBOURS = [[1, 0], [-1, 0], [0, 1], [0, -1], [1, 1], [1, -1], [-1, 1], [-1, -1]] as const;

function reachGrid(a0: number, a1: number, b0: number, b1: number, entry: readonly [number, number], blocked: (a: number, b: number, r: number) => boolean): (a: number, b: number) => boolean {
  const s = 0.2, r = 0.3, na = Math.ceil((a1 - a0) / s), nb = Math.ceil((b1 - b0) / s);
  const seen = new Uint8Array(na * nb), q: number[] = [];
  const i0 = Math.min(na - 1, Math.max(0, Math.floor((entry[0] - a0) / s))), j0 = Math.min(nb - 1, Math.max(0, Math.floor((entry[1] - b0) / s)));
  seen[j0 * na + i0] = 1;
  q.push(i0, j0);
  while (q.length) {
    const j = q.pop()!, i = q.pop()!;
    for (const [di, dj] of [[1, 0], [-1, 0], [0, 1], [0, -1]]) {
      const ii = i + di, jj = j + dj;
      if (ii < 0 || jj < 0 || ii >= na || jj >= nb || seen[jj * na + ii]) continue;
      if (blocked(a0 + (ii + 0.5) * s, b0 + (jj + 0.5) * s, r)) continue;
      seen[jj * na + ii] = 1;
      q.push(ii, jj);
    }
  }
  return (a, b) => {
    const i = Math.floor((a - a0) / s), j = Math.floor((b - b0) / s);
    return i >= 0 && j >= 0 && i < na && j < nb && seen[j * na + i] === 1;
  };
}

/** A planner's block: a fixture, or free floor kept clear (`keep`: before a stair's foot, its top). */
interface Block { kind: InteriorFixtureKind | 'keep'; a: number; b: number; w: number; d: number; h: number }

/**
 * Places fixtures on one storey where they fit: inside the walls, clear of each other and of the way in.
 * Works in the storey's own frame (centred on it); `planInterior` moves them into the building's.
 */
class Planner {
  readonly fixtures: Block[] = [];
  readonly spots: { kind: InteriorSpotKind; a: number; b: number; yaw: number }[] = [];
  /** Places that must stay reachable besides the spots: a stair's foot. */
  private readonly musts: [number, number][] = [];
  /** While a table and its benches go in together (checked as a whole). */
  private batch = false;
  /** The floor in front of each window (half a metre deep) and its sill's height: nothing taller stands there. */
  windows: (Rect & { sill: number })[] = [];
  /** Set while a stair may stand before a window after all (no other place for it). */
  private anyWindow = false;
  constructor(readonly ha: number, readonly hb: number, readonly ground: boolean, readonly entry: readonly [number, number]) {}

  /** The windows of this storey (the shape's walls; `cb` the storey's middle along b, `y0` its walls' foot under the floor). */
  seeWindows(st: HouseShape['storeys'][number], cb: number, y0: number): void {
    for (const w of st.walls) {
      const len = Math.hypot(w.a1 - w.a0, w.b1 - w.b0), da = (w.a1 - w.a0) / len, db = (w.b1 - w.b0) / len;
      for (const q of w.opens) {
        if (q.door) continue;
        // Along the wall from s0 to s1, from its inner face 0.5 m into the room (inwards is (-db, da)).
        const pts = [q.s0, q.s1].flatMap((t) => [0, 0.5].map((e) => [w.a0 + da * t - db * (WALL + e), w.b0 + db * t + da * (WALL + e) - cb]));
        this.windows.push({ a0: Math.min(...pts.map((p) => p[0])), a1: Math.max(...pts.map((p) => p[0])), b0: Math.min(...pts.map((p) => p[1])), b1: Math.max(...pts.map((p) => p[1])), sill: q.t0 + y0 });
      }
    }
  }

  /** Whether a block (with `gap` around it) fits: inside, clear of the others and of the way in. */
  fits(a: number, b: number, w: number, d: number, gap = 0.5, h = 0): boolean {
    if (Math.abs(a) + w / 2 > this.ha + 1e-6 || Math.abs(b) + d / 2 > this.hb + 1e-6) return false;
    if (!this.anyWindow && this.windows.some((q) => h > q.sill - 0.05 && a + w / 2 > q.a0 && a - w / 2 < q.a1 && b + d / 2 > q.b0 && b - d / 2 < q.b1)) return false;
    // The way in: 1.6 m wide, 1.8 m deep from the door; or a metre round the top of the stairs.
    if (this.ground && Math.abs(a) < 0.8 + w / 2 && b - d / 2 < -this.hb + 1.8) return false;
    if (!this.ground && Math.abs(a - this.entry[0]) < 0.5 + w / 2 && Math.abs(b - this.entry[1]) < 0.5 + d / 2) return false;
    return this.fixtures.every((f) => Math.abs(f.a - a) >= (f.w + w) / 2 + gap || Math.abs(f.b - b) >= (f.d + d) / 2 + gap);
  }

  add(kind: Block['kind'], a: number, b: number, w: number, d: number, h: number, gap = 0.5): boolean {
    // The fires stand under the chimney, where the walls have no windows.
    if (!this.fits(a, b, w, d, gap, kind === 'hearth' || kind === 'forge' || kind === 'oven' ? 0 : h)) return false;
    this.fixtures.push({ kind, a, b, w, d, h });
    // Nothing may shut off a spot placed before it (the keeper behind the counter, the hearth, a bench).
    if (this.batch || this.allReachable()) return true;
    this.fixtures.pop();
    return false;
  }

  spot(kind: InteriorSpotKind, a: number, b: number, yaw: number): void {
    this.spots.push({ kind, a, b, yaw });
  }

  /** The floor one can walk to from the entry. */
  reach(): (a: number, b: number) => boolean {
    const { ha, hb } = this;
    return reachGrid(-ha, ha, -hb, hb, this.entry, (a, b, r) => {
      const inDoor = this.ground && Math.abs(a) < 0.5 && b < -hb + r;
      if (!inDoor && (Math.abs(a) > ha - r || Math.abs(b) > hb - r)) return true;
      return this.fixtures.some((f) => f.kind !== 'hatch' && f.kind !== 'keep' && Math.abs(a - f.a) < f.w / 2 + r && Math.abs(b - f.b) < f.d / 2 + r);
    });
  }

  /** Whether every spot so far (and the stair's foot) can be got to. */
  private allReachable(): boolean {
    const reach = this.reach();
    return this.spots.every((s) => SPOT_RING.some(([da, db]) => reach(s.a + da, s.b + db))) && this.musts.every(([a, b]) => reach(a, b));
  }

  /** A trapdoor on free floor, as far back from the door as it fits (looser gaps if need be). */
  hatch(): void {
    for (const gap of [0.4, 0.2, 0]) {
      for (let b = this.hb - 0.6; b > -this.hb + 1.9; b -= 0.2) {
        for (const a of [this.ha - 0.6, -(this.ha - 0.6), 0, this.ha / 2, -this.ha / 2]) {
          if (!this.fits(a, b, 0.9, 0.9, gap)) continue;
          this.fixtures.push({ kind: 'hatch', a, b, w: 0.9, d: 0.9, h: 0.04 });
          if (this.reach()(a, b) && this.allReachable()) return;
          this.fixtures.pop();
        }
      }
    }
    // Nothing free: at the door's way in (always open).
    this.fixtures.push({ kind: 'hatch', a: 0, b: -this.hb + 1.4, w: 0.9, d: 0.9, h: 0.04 });
  }

  /**
   * The hearth (or the smith's forge, the baker's oven: the kinds place those) under the chimney, and on
   * the storeys above it the chimney breast. Built first: the chimney is where the outside has it.
   */
  chimney(S: HouseShape, b: TownBuilding, storey: number, cb: number): void {
    const c = S.chimney!, ca = c.a, cbb = c.b - cb;
    const toWall = c.wall === 'back' ? this.hb - cbb : this.ha - Math.abs(ca);
    if (storey > 0) {
      // The breast: from the stack's far side to the wall.
      if (c.wall === 'back') { const d = Math.max(0.7, toWall + 0.35); this.fixtures.push({ kind: 'flue', a: ca, b: this.hb - d / 2, w: 0.75, d, h: 9 }); }
      else { const w = Math.max(0.7, toWall + 0.35), s = Math.sign(ca); this.fixtures.push({ kind: 'flue', a: s * (this.ha - w / 2), b: cbb, w, d: 0.75, h: 9 }); }
      return;
    }
    if (b.kind === 'smithy') { if (this.add('forge', ca, this.hb - 0.7, 1.4, 1.2, 0.9, 0.2)) this.spot('stoke', ca, this.hb - 1.7, FACE_B); return; }
    if (b.kind === 'bakery') { if (this.add('oven', ca, this.hb - 0.8, 2.0, 1.4, 1.5, 0.2)) this.spot('bake', ca, this.hb - 2.0, FACE_B); return; }
    if (c.wall === 'back') { if (this.add('hearth', ca, this.hb - 0.45, 1.5, 0.9, 1.3, 0.3)) this.spot('warm', ca, this.hb - 1.55, FACE_B); }
    else {
      const side = Math.sign(ca), a = side * (this.ha - 0.45);
      if (this.add('hearth', a, cbb, 0.9, 1.5, 1.3, 0.3)) this.spot('warm', a - side * 1.1, cbb, side > 0 ? FACE_A : FACE_NA);
    }
  }

  /**
   * Stairs up `rise` metres, along a wall, clear of what stands and with free floor at the foot and the top.
   * `topOk`: whether the top (b, this storey's frame) lies on the floor above. Null when none fits.
   */
  stair(r: Rng, rise: number, topOk: (a: number, b: number) => boolean): Omit<InteriorStair, 'storey'> | null {
    const side = r.chance(0.5) ? -1 : 1;
    // Steeper where a narrow storey leaves no room (an upper flight in a tall thin house).
    // Clear of the windows if it can be, else past one.
    for (const any of [false, true]) {
      this.anyWindow = any;
      for (const tread of [TREAD, 0.18]) {
        const s = this.flight(side, rise, tread, topOk);
        if (s) { this.anyWindow = false; return s; }
      }
    }
    this.anyWindow = false;
    return null;
  }

  private flight(side: number, rise: number, tread: number, topOk: (a: number, b: number) => boolean): Omit<InteriorStair, 'storey'> | null {
    const steps = Math.max(8, Math.round(rise / RISER)), riser = rise / steps, run = steps * tread, w = STAIR_W;
    const tries: [number, number, number, number][] = [];
    // Along a side wall, going back or forward; then along the back wall, either way.
    for (const s of [side, -side]) for (const db of [1, -1]) for (let b = -this.hb; b <= this.hb; b += 0.2) tries.push([s * (this.ha - w / 2), b, 0, db]);
    for (const da of [side, -side]) for (let a = -this.ha; a <= this.ha; a += 0.2) tries.push([a, this.hb - w / 2, da, 0]);
    // Upstairs, along the front wall too (no door there).
    if (!this.ground) for (const da of [side, -side]) for (let a = -this.ha; a <= this.ha; a += 0.2) tries.push([a, -this.hb + w / 2, da, 0]);
    for (const [a, b, da, db] of tries) {
      const ma = a + da * run / 2, mb = b + db * run / 2, sw = da ? run : w, sd = db ? run : w;
      // The foot's free floor (a metre before the first step) and the top's (on the floor above).
      const fa = a - da * 0.45, fb = b - db * 0.45, ta = a + da * (run + 0.5), tb = b + db * (run + 0.5);
      if (!this.fits(ma, mb, sw, sd, 0.05, rise) || !this.fits(fa, fb, da ? 0.8 : w, db ? 0.8 : w, 0.1)) continue;
      if (Math.abs(ta) > this.ha - 0.3 || Math.abs(tb) > this.hb + 2 || !topOk(ta, tb)) continue;
      const f0 = this.fixtures.length;
      this.fixtures.push({ kind: 'stair', a: ma, b: mb, w: sw, d: sd, h: rise }, { kind: 'keep', a: fa, b: fb, w: da ? 0.8 : w, d: db ? 0.8 : w, h: 0 });
      this.musts.push([fa - da * 0.2, fb - db * 0.2]);
      if (this.allReachable()) return { a, b, da, db, w, steps, tread, riser };
      this.fixtures.length = f0;
      this.musts.pop();
    }
    return null;
  }

  /** The hole a stair from below comes up through, the rail round its open sides, and room at its top. */
  well(s: InteriorStair, cb: number): void {
    const run = s.steps * s.tread, from = run * WELL_FROM;
    const a0 = s.a + s.da * from, b0 = s.b - cb + s.db * from, a1 = s.a + s.da * run, b1 = s.b - cb + s.db * run;
    const ma = (a0 + a1) / 2, mb = (b0 + b1) / 2, len = run - from;
    const ww = s.da ? len : s.w, dd = s.db ? len : s.w;
    this.fixtures.push({ kind: 'well', a: ma, b: mb, w: ww, d: dd, h: 0 });
    // Rails: across its low end, and along its side away from the wall.
    const t = 0.08;
    if (s.da) {
      this.fixtures.push({ kind: 'rail', a: a0 - s.da * t / 2, b: mb, w: t, d: dd, h: 0.95 });
      const out = -Math.sign(mb) || 1;
      this.fixtures.push({ kind: 'rail', a: ma, b: mb + out * (dd / 2 + t / 2), w: ww, d: t, h: 0.95 });
    } else {
      this.fixtures.push({ kind: 'rail', a: ma, b: b0 - s.db * t / 2, w: ww, d: t, h: 0.95 });
      const out = -Math.sign(ma) || 1;
      this.fixtures.push({ kind: 'rail', a: ma + out * (ww / 2 + t / 2), b: mb, w: t, d: dd, h: 0.95 });
    }
  }

  /** A table (`len` long) with a bench on each long side; people sit facing it. Returns whether it fitted. */
  table(a: number, b: number, alongA: boolean, sit: InteriorSpotKind, len = 1.6, gap = 0.6): boolean {
    const tw = alongA ? len : 0.8, td = alongA ? 0.8 : len;
    if (!this.fits(a, b, alongA ? tw : tw + 1.4, alongA ? td + 1.4 : td, gap)) return false;
    const f0 = this.fixtures.length, s0 = this.spots.length;
    this.batch = true;
    this.add('table', a, b, tw, td, 0.76, 0);
    for (const s of [-1, 1]) {
      const ba = alongA ? a : a + s * 0.68, bb = alongA ? b + s * 0.68 : b;
      this.add('bench', ba, bb, alongA ? len : 0.3, alongA ? 0.3 : len, 0.45, 0);
      for (const k of len > 1.3 ? [-0.45, 0.45] : [0]) {
        const sa = alongA ? ba + k : ba, sb = alongA ? bb : bb + k;
        this.spot(sit, sa, sb, alongA ? (s < 0 ? FACE_B : FACE_NB) : (s < 0 ? FACE_A : FACE_NA));
      }
    }
    this.batch = false;
    if (this.allReachable()) return true;
    this.fixtures.length = f0;
    this.spots.length = s0;
    return false;
  }

  /**
   * Up to `max` tables wherever they fit, tried on a fine grid from the room's middle outwards, both
   * ways round. Returns how many fitted.
   */
  tables(sit: InteriorSpotKind, max: number, len = 1.6, gap = 0.5): number {
    const at: [number, number, boolean][] = [];
    for (let b = -this.hb + 0.6; b < this.hb - 0.6; b += 0.3) {
      for (let a = -this.ha + 0.6; a < this.ha - 0.6; a += 0.3) at.push([a, b, true], [a, b, false]);
    }
    at.sort((x, y) => Math.abs(x[0]) + Math.abs(x[1]) - Math.abs(y[0]) - Math.abs(y[1]));
    let n = 0;
    for (const [a, b, along] of at) if (n < max && this.table(a, b, along, sit, len, gap)) n++;
    return n;
  }
}

function tavern(P: Planner, r: Rng): void {
  // The counter across the back, the keeper behind it, barrels against the back wall.
  // The keeper gets in at the counter's end by the side wall.
  const cw = Math.min(P.ha, 3.8), ca = P.ha - cw / 2 - 0.9;
  P.add('counter', ca, P.hb - 1.8, cw, 0.6, 1.05, 0);
  P.spot('serve', ca, P.hb - 1.1, FACE_NB);
  for (let a = ca - cw / 2 + 0.4; a < ca + cw / 2; a += 0.75) P.add('barrel', a, P.hb - 0.3, 0.6, 0.6, 0.9, 0.05);
  P.spot('drink', ca - cw / 4, P.hb - 2.55, FACE_B);
  P.spot('drink', ca + cw / 4, P.hb - 2.55, FACE_B);
  void r;
  // As many tables as fit; in a narrow taproom smaller ones, closer together.
  if (!P.tables('drink', 6) && !P.tables('drink', 3, 1.2, 0.3)) P.tables('drink', 2, 0.8, 0.2);
}

function smithy(P: Planner, fa: number): void {
  const side = fa < 0 ? -1 : 1;
  // The forge is in (against the back wall under the chimney): the anvil in front of it, the quench tub beside the anvil.
  P.add('anvil', fa, P.hb - 2.6, 0.4, 0.8, 0.8, 0.2);
  P.spot('smith', fa - side * 0.75, P.hb - 2.6, side > 0 ? FACE_A : FACE_NA);
  if (P.add('tub', fa + side * 1.2, P.hb - 2.6, 0.8, 0.8, 0.6, 0.3)) P.spot('quench', fa + side * 1.2, P.hb - 3.4, FACE_B);
  if (P.add('workbench', -side * (P.ha - 0.35), 0, 0.6, 2.0, 0.9, 0.3)) P.spot('craft', -side * (P.ha - 1.1), 0, side > 0 ? FACE_NA : FACE_A);
  P.add('woodpile', side * (P.ha - 0.4), -P.hb + 2.2, 0.7, 1.4, 0.8, 0.2);
}

function bakery(P: Planner, r: Rng): void {
  // The oven is in, against the back wall under the chimney.
  const side = r.chance(0.5) ? -1 : 1;
  if (P.add('workbench', side * (P.ha - 0.4), 0, 0.7, 2.2, 0.9, 0.3)) P.spot('bake', side * (P.ha - 1.2), 0, side > 0 ? FACE_A : FACE_NA);
  P.add('shelf', -side * (P.ha - 0.25), 0.4, 0.4, 2.0, 1.8, 0.2);
  P.add('barrel', -side * (P.ha - 0.5), -P.hb + 2.3, 0.6, 0.6, 0.9, 0.1);
}

/** An upper storey: beds against the walls (the inn's guest beds in a row), a chest at the foot of each. */
function bedroom(P: Planner, r: Rng, inn: boolean): void {
  const n = inn ? 4 : r.chance(0.5) ? 2 : 1;
  let put = 0;
  for (const b of [P.hb - 1.05, -P.hb + 1.05, 0]) {
    for (const a of [P.ha - 0.55, -(P.ha - 0.55), P.ha - 1.75, -(P.ha - 1.75)]) {
      if (put >= n) break;
      if (!P.add('bed', a, b, 1.0, 2.0, 0.55, 0.25)) continue;
      put++;
      P.spot('sleep', a, b, FACE_NB);
      P.add('chest', a, b - Math.sign(b || 1) * 1.3, 0.9, 0.5, 0.5, 0.1);
    }
  }
  if (!inn) P.add('shelf', r.chance(0.5) ? P.ha - 0.22 : -(P.ha - 0.22), 0, 0.35, 1.2, 1.7, 0.2);
}

function temple(P: Planner, _r: Rng): void {
  // A basin on a plinth in the middle (the faith is the setting's to say), benches in rows facing it.
  P.add('basin', 0, 0.6, 1.0, 1.0, 0.95, 0.4);
  P.spot('tend', 0, -0.4, FACE_B);
  for (const side of [-1, 1]) {
    for (let b = -P.hb + 2.0; b <= P.hb - 1.0; b += 1.3) {
      const a = side * Math.min(P.ha - 0.9, 2.4);
      // Kneeling at the bench's aisle end, facing the basin.
      if (P.add('bench', a, b, 1.5, 0.35, 0.45, 0.1)) P.spot('pray', a - side * 0.5, b, Math.atan2(0.6 - b, side * 0.5 - a));
    }
  }
}

function home(P: Planner, r: Rng, work: boolean): void {
  // The hearth is in (under the chimney): the bed goes to the other side.
  const h = P.fixtures.find((f) => f.kind === 'hearth');
  const side = h ? (h.a < -0.3 ? -1 : h.a > 0.3 ? 1 : r.chance(0.5) ? -1 : 1) : r.chance(0.5) ? -1 : 1;
  // The bed in a back corner on the other side, a chest at its foot.
  const ba = -side * (P.ha - 0.5);
  if (P.add('bed', ba, P.hb - 1.05, 1.0, 2.0, 0.55, 0.1)) {
    P.spot('sleep', ba, P.hb - 1.05, FACE_NB);
    P.add('chest', ba, P.hb - 2.5, 0.9, 0.5, 0.5, 0.1);
  }
  // The family's table where it fits, from the middle of the room outwards.
  if (!P.tables('sit', 1, 1.2, 0.35)) P.tables('sit', 1, 0.8, 0.25);
  if (work && P.add('workbench', side * (P.ha - 0.35), -P.hb + 2.4, 0.6, 1.6, 0.9, 0.3)) P.spot('craft', side * (P.ha - 1.05), -P.hb + 2.4, side > 0 ? FACE_A : FACE_NA);
  P.add('shelf', -side * (P.ha - 0.22), -P.hb + 2.0, 0.35, 1.2, 1.7, 0.1);
}

/**
 * A hall: the practice post nearest the room's middle with its master's place beside it (towards the door),
 * up to three weapon racks on free stretches of the side and back walls, a bench by the front wall.
 */
function hall(P: Planner): void {
  const floor: [number, number][] = [];
  for (let b = -P.hb + 1.4; b < P.hb - 0.6; b += 0.3) for (let a = -P.ha + 0.6; a < P.ha - 0.5; a += 0.3) floor.push([a, b]);
  // Nearest a point a little behind the middle: a few steps in from the door, not at one's elbow.
  floor.sort((x, y) => Math.hypot(x[0], x[1] - P.hb * 0.15) - Math.hypot(y[0], y[1] - P.hb * 0.15));
  floor.find(([a, b]) => {
    if (!P.add('pell', a, b, 0.5, 0.5, 1.75, 0.7)) return false;
    // One must be able to step up to it and strike; its master stands behind it and to one side (away from the
    // door, off the line from the door through the post), facing the door: one coming in sees post and master.
    const reach = P.reach(), side = a > 0 ? -1 : 1;
    const at = [[side * 0.9, 0.5], [-side * 0.9, 0.5], [side * 0.9, -0.2], [-side * 0.9, -0.2], [0, 0.8]].find(([da, db]) => reach(a + da, b + db));
    if (at) { P.spot('drill', a + at[0], b + at[1], FACE_NB); return true; }
    P.fixtures.pop();
    return false;
  });
  const walls: [number, number, number, number][] = [];
  for (let t = P.hb - 1.0; t >= -P.hb + 2.0; t -= 0.3) for (const s of [-1, 1]) walls.push([s * (P.ha - 0.2), t, 0.3, 1.5]);
  for (let t = -P.ha + 1.0; t <= P.ha - 1.0; t += 0.3) walls.push([t, P.hb - 0.2, 1.5, 0.3]);
  let racks = 0;
  for (const [a, b, w, d] of walls) if (racks < 3 && P.add('rack', a, b, w, d, 1.8, 0.6)) racks++;
  // Windows all round: a low rack under a sill (blades only).
  if (!racks) walls.find(([a, b, w, d]) => P.add('rack', a, b, w, d, 0.85, 0.4));
  // Those who come to watch (or wait their turn) sit by the front wall, beside the way in.
  for (const s of [-1, 1]) {
    const a = s * (P.ha - 0.95);
    if (P.add('bench', a, -P.hb + 0.25, 1.4, 0.4, 0.45, 0.2)) { P.spot('sit', a - 0.35, -P.hb + 0.25, FACE_B); P.spot('sit', a + 0.35, -P.hb + 0.25, FACE_B); break; }
  }
}

/** Inside colours. */
const LIME: RGB = [236, 228, 210];
const SOOT: RGB = [150, 140, 128];
/**
 * Interior wood, on BuildingMat.Oak, whose texture is already dark oak (about 6.6 % reflectance): the tints
 * sit on its own colour. TIMBER (boards, benches, table tops) about 6 %, DARK (beams, legs, stairs, the
 * counter, doors) about 2.6 %, LIGHT_WOOD (fresh logs, the hatch's planks) a shade over TIMBER.
 */
const TIMBER: RGB = [255, 240, 225];
const DARK: RGB = [180, 160, 145];
const LIGHT_WOOD: RGB = [255, 250, 245];
const IRON: RGB = [70, 70, 74];
const STEEL: RGB = [150, 152, 158];
/** A painted round shield (madder red) on a hall's rack. */
const SHIELD: RGB = [150, 50, 36];
const LINEN: RGB = [214, 204, 180];
const STONE: RGB = [196, 188, 176];

/**
 * Inside faces carry how much daylight reaches them in their material: `mat` = material + INSIDE_LIGHT ×
 * level, level 1 (dark) .. INSIDE_LEVELS (as out of doors), with room below INSIDE_LIGHT for a game's own
 * texture layers past BuildingMat's, the square root of the share of the open sky's light (the
 * windows' and the door's, by distance and angle, and a little thrown back by the room). Outside faces
 * have level 0. A game dims the sky's light on them by it (the sun's comes in through the openings by itself).
 */
export const INSIDE_LIGHT = 32;
export const INSIDE_LEVELS = 7;

/** An axis-aligned box in the building's frame (y over its floor): what the inside walls a body in with. */
export interface InteriorBox { a0: number; a1: number; y0: number; y1: number; b0: number; b1: number }

interface Rect { a0: number; a1: number; b0: number; b1: number }

/** A rectangle less some holes in it, as rectangles. */
function rectMinus(r: Rect, holes: readonly Rect[]): Rect[] {
  let out = [r];
  for (const h of holes) {
    const next: Rect[] = [];
    for (const q of out) {
      if (h.a1 <= q.a0 || h.a0 >= q.a1 || h.b1 <= q.b0 || h.b0 >= q.b1) { next.push(q); continue; }
      const b0 = Math.max(q.b0, h.b0), b1 = Math.min(q.b1, h.b1);
      if (b0 > q.b0) next.push({ ...q, b1: b0 });
      if (b1 < q.b1) next.push({ ...q, b0: b1 });
      if (h.a0 > q.a0) next.push({ a0: q.a0, a1: Math.max(q.a0, h.a0), b0, b1 });
      if (h.a1 < q.a1) next.push({ a0: Math.min(q.a1, h.a1), a1: q.a1, b0, b1 });
    }
    out = next;
  }
  return out.filter((q) => q.a1 - q.a0 > 1e-3 && q.b1 - q.b0 > 1e-3);
}

const wellRects = (plan: InteriorPlan, storey: number): Rect[] => plan.fixtures.filter((f) => f.kind === 'well' && f.storey === storey).map((f) => ({ a0: f.a - f.w / 2, a1: f.a + f.w / 2, b0: f.b - f.d / 2, b1: f.b + f.d / 2 }));

/** Splits a..b at about `step` metres (and at `cuts` inside it). */
function splits(a: number, b: number, step: number, cuts: number[] = []): number[] {
  const n = Math.max(1, Math.round((b - a) / step)), out = [a, b, ...cuts.filter((c) => c > a + 1e-3 && c < b - 1e-3)];
  for (let i = 1; i < n; i++) out.push(a + ((b - a) * i) / n);
  return [...new Set(out.map((v) => Math.round(v * 1e4) / 1e4))].sort((x, y) => x - y);
}

/**
 * Every storey's inside as a mesh (positions relative to `origin`, in the building's place): floors and
 * ceilings with the stairs' holes, the walls' inner faces with the windows and the door open through
 * them, the stairs and their rails, the chimney breast, the furniture, and the door standing open. Inner
 * faces only: merged with `buildingMesh(b, origin, true, { open: true })` the building is hollow.
 */
/**
 * `lid: false`: a hatch's lid is left out (the game draws it apart, `hatchLidMesh`, to swing it open): the floor
 * has a hole there, a shaft under it with a ladder down one side (`hatchSides`), dark below. `doors: false`: the
 * door's leaves standing open inside are left out (the game draws them apart, `doorLeaves`, to swing them).
 */
export function interiorMesh(plan: InteriorPlan, b: TownBuilding, origin: [number, number, number], opts: { lid?: boolean; doors?: boolean } = {}): BuildingMesh {
  const lid = opts.lid !== false, doors = opts.doors !== false;
  const S = houseShape(b);
  const ux = Math.cos(b.angle), uz = Math.sin(b.angle);
  const rr = new Rng(b.seed ^ 0x51de);
  const lime: RGB = rr.chance(0.3) ? SOOT : LIME;
  const wallMat = b.wall === 'stone' || b.kind === 'temple' ? BuildingMat.Rubble : BuildingMat.Plaster;
  const wallTint = b.wall === 'stone' || b.kind === 'temple' ? STONE : lime;
  const parts: BuildingMesh[] = [];
  plan.storeys.forEach((st, k) => {
    const o = new Out(new Frame({ cx: b.cx, cz: b.cz, ux, uz, vx: b.vx, vz: b.vz, y: b.floorY + st.y }, origin));
    const H = st.height, top = k + 1 < plan.storeys.length ? plan.storeys[k + 1].y - st.y : H + CEILING;
    const room: Rect = { a0: st.a0, a1: st.a1, b0: st.b0, b1: st.b1 };
    // The floor, less the hole the stairs from below come up through; flags or boards.
    const stone = k === 0 && plan.stoneFloor;
    for (const q of rectMinus(room, [...wellRects(plan, k), ...(lid ? [] : hatchRects(plan, k))])) gridQuad(o, q, 0, [0, 1, 0], stone ? BuildingMat.Ashlar : BuildingMat.Oak, stone ? STONE : TIMBER);
    // The ceiling and its joists, less the hole up; the hole's sides through the floor between.
    const up = wellRects(plan, k + 1);
    for (const q of rectMinus(room, up)) gridQuad(o, q, H, [0, -1, 0], BuildingMat.Oak, TIMBER);
    for (let a = st.a0 + 0.6; a < st.a1 - 0.3; a += 1.1) {
      for (const q of rectMinus({ a0: a - 0.09, a1: a + 0.09, b0: st.b0, b1: st.b1 }, up)) o.box(q.a0, q.a1, H - 0.2, H, q.b0, q.b1, BuildingMat.Oak, DARK, true);
    }
    for (const w of up) {
      o.quad([[w.a0, H, w.b0], [w.a1, H, w.b0], [w.a1, top, w.b0], [w.a0, top, w.b0]], [0, 0, 1], [[w.a0, 0], [w.a1, 0], [w.a1, 1], [w.a0, 1]], BuildingMat.Oak, DARK);
      o.quad([[w.a0, H, w.b1], [w.a1, H, w.b1], [w.a1, top, w.b1], [w.a0, top, w.b1]], [0, 0, -1], [[w.a0, 0], [w.a1, 0], [w.a1, 1], [w.a0, 1]], BuildingMat.Oak, DARK);
      o.quad([[w.a0, H, w.b0], [w.a0, H, w.b1], [w.a0, top, w.b1], [w.a0, top, w.b0]], [1, 0, 0], [[w.b0, 0], [w.b1, 0], [w.b1, 1], [w.b0, 1]], BuildingMat.Oak, DARK);
      o.quad([[w.a1, H, w.b0], [w.a1, H, w.b1], [w.a1, top, w.b1], [w.a1, top, w.b0]], [-1, 0, 0], [[w.b0, 0], [w.b1, 0], [w.b1, 1], [w.b0, 1]], BuildingMat.Oak, DARK);
    }
    // The walls' inner faces, open where the outside has its windows and door.
    const sh = S.storeys[k];
    for (const w of sh.walls) innerWall(o, w.a0, w.b0, w.a1, w.b1, w.opens, sh.y0 - st.y, H, room, wallMat, wallTint);
    for (const s of plan.stairs) if (s.storey === k) stair(o, s);
    for (const f of plan.fixtures) if (f.storey === k && (doors || f.kind !== 'door')) {
      if (f.kind === 'hatch' && !lid) hatchShaft(o, f, hatchSides(plan, f));
      else fixture(o, f, H);
    }
    const m = toMesh(o);
    daylight(m, b, origin, st, S.storeys[k], k === 0);
    parts.push(m);
  });
  return merge(parts);
}

/** A horizontal rectangle at height y as quads of about a metre (so the daylight can vary over it). */
function gridQuad(o: Out, q: Rect, y: number, n: number[], m: BuildingMat, c: RGB): void {
  const A = splits(q.a0, q.a1, 1.2), B = splits(q.b0, q.b1, 1.2);
  for (let i = 0; i + 1 < A.length; i++) for (let j = 0; j + 1 < B.length; j++) {
    o.quad([[A[i], y, B[j]], [A[i + 1], y, B[j]], [A[i + 1], y, B[j + 1]], [A[i], y, B[j + 1]]], n, [[A[i], B[j]], [A[i + 1], B[j]], [A[i + 1], B[j + 1]], [A[i], B[j + 1]]], m, c);
  }
}

/**
 * One wall's inner face on one storey (the outside wall a0,b0 -> a1,b1, counter-clockwise), between the
 * storey's floor and ceiling (`H`), with holes where its openings are (`y0`: the openings' storey foot
 * under this floor), and their reveals through to the outside ones.
 */
function innerWall(o: Out, a0: number, b0: number, a1: number, b1: number, opens: readonly { s0: number; s1: number; t0: number; t1: number; door?: boolean }[], y0: number, H: number, room: Rect, m: BuildingMat, c: RGB): void {
  const len = Math.hypot(a1 - a0, b1 - b0), da = (a1 - a0) / len, db = (b1 - b0) / len;
  const na = db, nb = -da;
  // The inner face: WALL inside the outer one, from corner to corner of the room.
  const P = (s: number, t: number, d = -WALL): number[] => [a0 + da * s + na * d, t, b0 + db * s + nb * d];
  const N = [-na, 0, -nb];
  const sOf = (a: number, b: number) => (a - a0) * da + (b - b0) * db;
  const ends = [sOf(room.a0, room.b0), sOf(room.a1, room.b0), sOf(room.a1, room.b1), sOf(room.a0, room.b1)];
  const s0 = Math.max(0, Math.min(...ends)), s1 = Math.min(len, Math.max(...ends));
  const holes = opens.map((q) => ({ s0: q.s0, s1: q.s1, t0: Math.max(0, q.t0 + y0), t1: Math.min(H, q.t1 + y0), door: q.door })).filter((q) => q.t1 > q.t0 + 0.05 && q.s1 > s0 && q.s0 < s1);
  const S = splits(s0, s1, 1.2, holes.flatMap((q) => [q.s0, q.s1])), T = splits(0, H, 1.3, holes.flatMap((q) => [q.t0, q.t1]));
  for (let i = 0; i + 1 < S.length; i++) for (let j = 0; j + 1 < T.length; j++) {
    const sm = (S[i] + S[i + 1]) / 2, tm = (T[j] + T[j + 1]) / 2;
    if (holes.some((q) => sm > q.s0 && sm < q.s1 && tm > q.t0 && tm < q.t1)) continue;
    o.quad([P(S[i], T[j]), P(S[i + 1], T[j]), P(S[i + 1], T[j + 1]), P(S[i], T[j + 1])], N, [[S[i], T[j]], [S[i + 1], T[j]], [S[i + 1], T[j + 1]], [S[i], T[j + 1]]], m, c);
  }
  // Reveals from the inner face to the outer one's (16 cm in for windows, 12 for the door).
  for (const q of holes) {
    const back = q.door ? 0.12 : 0.16, d = WALL - back;
    const Q = (s: number, t: number, e: number) => P(s, t, -WALL + e);
    o.quad([Q(q.s0, q.t0, 0), Q(q.s0, q.t1, 0), Q(q.s0, q.t1, d), Q(q.s0, q.t0, d)], [da, 0, db], [[0, q.t0], [0, q.t1], [d, q.t1], [d, q.t0]], m, c);
    o.quad([Q(q.s1, q.t0, 0), Q(q.s1, q.t1, 0), Q(q.s1, q.t1, d), Q(q.s1, q.t0, d)], [-da, 0, -db], [[0, q.t0], [0, q.t1], [d, q.t1], [d, q.t0]], m, c);
    o.quad([Q(q.s0, q.t1, 0), Q(q.s1, q.t1, 0), Q(q.s1, q.t1, d), Q(q.s0, q.t1, d)], [0, -1, 0], [[q.s0, 0], [q.s1, 0], [q.s1, d], [q.s0, d]], m, c);
    // A sill board under a window.
    if (!q.door) o.quad([Q(q.s0, q.t0, 0), Q(q.s1, q.t0, 0), Q(q.s1, q.t0, d), Q(q.s0, q.t0, d)], [0, 1, 0], [[q.s0, 0], [q.s1, 0], [q.s1, d], [q.s0, d]], BuildingMat.Oak, TIMBER);
  }
}

/** A flight of stairs: each step's tread and riser, the sides down to the floor, the back under its top. */
function stair(o: Out, s: InteriorStair): void {
  const pa = -s.db, pb = s.da, hw = s.w / 2;
  const P = (x: number, y: number, side: number): number[] => [s.a + s.da * x + pa * side * hw, y, s.b + s.db * x + pb * side * hw];
  const fwd = [s.da, 0, s.db], back = [-s.da, 0, -s.db];
  for (let i = 0; i < s.steps; i++) {
    const x0 = i * s.tread, x1 = x0 + s.tread, y0 = i * s.riser, y1 = y0 + s.riser;
    o.quad([P(x0, y1, -1), P(x1, y1, -1), P(x1, y1, 1), P(x0, y1, 1)], [0, 1, 0], [[x0, -hw], [x1, -hw], [x1, hw], [x0, hw]], BuildingMat.Oak, TIMBER);
    o.quad([P(x0, y0, -1), P(x0, y0, 1), P(x0, y1, 1), P(x0, y1, -1)], back, [[-hw, y0], [hw, y0], [hw, y1], [-hw, y1]], BuildingMat.Oak, DARK);
    for (const side of [-1, 1]) o.quad([P(x0, 0, side), P(x1, 0, side), P(x1, y1, side), P(x0, y1, side)], [pa * side, 0, pb * side], [[x0, 0], [x1, 0], [x1, y1], [x0, y1]], BuildingMat.Oak, DARK);
  }
  const run = s.steps * s.tread, rise = s.steps * s.riser;
  o.quad([P(run, 0, -1), P(run, 0, 1), P(run, rise, 1), P(run, rise, -1)], fwd, [[-hw, 0], [hw, 0], [hw, rise], [-hw, rise]], BuildingMat.Oak, DARK);
}

/** The mesh an Out collected. */
function toMesh(o: Out): BuildingMesh {
  return { position: Float32Array.from(o.pos), normal: Float32Array.from(o.nrm), uv: Float32Array.from(o.uv), mat: Uint8Array.from(o.mat), tint: Uint8Array.from(o.tint), index: Uint32Array.from(o.idx) };
}

function merge(parts: readonly BuildingMesh[]): BuildingMesh {
  let nv = 0, ni = 0;
  for (const p of parts) { nv += p.position.length / 3; ni += p.index.length; }
  const out: BuildingMesh = { position: new Float32Array(nv * 3), normal: new Float32Array(nv * 3), uv: new Float32Array(nv * 2), mat: new Uint8Array(nv), tint: new Uint8Array(nv * 3), index: new Uint32Array(ni) };
  let v = 0, k = 0;
  for (const p of parts) {
    out.position.set(p.position, v * 3); out.normal.set(p.normal, v * 3); out.uv.set(p.uv, v * 2); out.mat.set(p.mat, v); out.tint.set(p.tint, v * 3);
    for (let i = 0; i < p.index.length; i++) out.index[k + i] = p.index[i] + v;
    v += p.position.length / 3; k += p.index.length;
  }
  return out;
}

/** A door leaf drawn apart (`doorLeaves`): shut in its doorway, its hinge (as the mesh's coordinates) and how it opens. */
export interface DoorLeaf {
  readonly mesh: BuildingMesh;
  /** A point on the hinge's line (it runs straight up). */
  readonly hinge: [number, number, number];
  /** The turn about +y (rad) that swings it wide open, into the house. */
  readonly open: number;
}

/**
 * The front door's leaves, shut in the doorway as the outside draws its door (`buildingMesh`: its paint outside,
 * the planks inside lit as the room), each turning on its hinge at a jamb (`origin` as for `interiorMesh`). A game
 * draws the house with `{ open: true }` and `interiorMesh(..., { doors: false })` and swings these.
 */
export function doorLeaves(plan: InteriorPlan, b: TownBuilding, origin: [number, number, number]): DoorLeaf[] {
  const S = houseShape(b), sh = S.storeys[0], front = sh.walls.find((w) => w.id === 0);
  const q = front?.opens.find((x) => x.door);
  if (!front || !q) return [];
  const ux = Math.cos(b.angle), uz = Math.sin(b.angle);
  const frame = new Frame({ cx: b.cx, cz: b.cz, ux, uz, vx: b.vx, vz: b.vz, y: b.floorY }, origin);
  const w = plan.doorW, leaves = w > 0.8 ? [-1, 1] : [-1], lw = (2 * w) / leaves.length;
  // The leaf's outside where the outside draws its door (12 cm into the doorway), 5 cm of planks behind it.
  const b0 = front.b0 + 0.12, b1 = b0 + 0.05, y0 = sh.y0 + q.t0, y1 = sh.y0 + q.t1 - 0.01;
  const inward = frame.dir(0, 0, 1);
  return leaves.map((s) => {
    const a0 = Math.min(s * w, s * (w - lw)), a1 = Math.max(s * w, s * (w - lw));
    const outside = new Out(frame), inside = new Out(frame);
    outside.quad([[a0, y0, b0], [a1, y0, b0], [a1, y1, b0], [a0, y1, b0]], [0, 0, -1], [[a0, y0], [a1, y0], [a1, y1], [a0, y1]], BuildingMat.Oak, S.look.door);
    inside.quad([[a0, y0, b1], [a1, y0, b1], [a1, y1, b1], [a0, y1, b1]], [0, 0, 1], [[a0, y0], [a1, y0], [a1, y1], [a0, y1]], BuildingMat.Oak, DARK);
    for (const a of [a0, a1]) inside.quad([[a, y0, b0], [a, y0, b1], [a, y1, b1], [a, y1, b0]], [a === a0 ? -1 : 1, 0, 0], [[b0, y0], [b1, y0], [b1, y1], [b0, y1]], BuildingMat.Oak, DARK);
    inside.quad([[a0, y1, b0], [a1, y1, b0], [a1, y1, b1], [a0, y1, b1]], [0, 1, 0], [[a0, b0], [a1, b0], [a1, b1], [a0, b1]], BuildingMat.Oak, DARK);
    const lit = toMesh(inside);
    daylight(lit, b, origin, plan.storeys[0], sh, true);
    const hinge = frame.point(s * w, 0, (b0 + b1) / 2);
    // From the hinge the leaf runs towards the doorway's middle; opened it points into the house.
    const d = frame.dir(-s, 0, 0), turned = [d[2], -d[0]];
    const open = (turned[0] * inward[0] + turned[1] * inward[2] > 0 ? 1 : -1) * (Math.PI / 2);
    return { mesh: merge([toMesh(outside), lit]), hinge, open };
  });
}

/** A hatch's lid: planks a shade lighter than the floor (it lies in a dark corner), two battens and an iron ring. */
function hatchLid(o: Out, f: InteriorFixture): void {
  const a0 = f.a - f.w / 2, a1 = f.a + f.w / 2, b0 = f.b - f.d / 2, b1 = f.b + f.d / 2;
  o.box(a0, a1, 0, f.h, b0, b1, BuildingMat.Oak, LIGHT_WOOD);
  for (const t of [-0.25, 0.25]) o.box(a0 + 0.06, a1 - 0.06, f.h, f.h + 0.025, f.b + t * f.d - 0.05, f.b + t * f.d + 0.05, BuildingMat.Oak, TIMBER);
  o.box(f.a - 0.1, f.a + 0.1, f.h, f.h + 0.03, f.b - 0.1, f.b + 0.1, BuildingMat.Slate, [120, 120, 126]);
}

/** The sides tried for a hatch's ladder, in turn (unit a, b in the room's frame). */
const SIDES: readonly [number, number][] = [[0, -1], [1, 0], [-1, 0], [0, 1]];
/** Room to stand before a hatch's ladder (m out from its edge), and kept clear past its hinge for the open lid leaning back. */
const HATCH_STAND = 0.5, HATCH_LEAN = 0.35;
/** A hatch's shaft under the floor (m deep); its ladder's rungs this far apart, this far inside the hatch's edge. */
export const HATCH_SHAFT = 2.4, HATCH_RUNG = 0.3, HATCH_RUNG_IN = 0.12;
/** A hatch's ladder stands this far up out of the hole (m, whole rungs): what one holds getting on and off it. */
export const HATCH_RAILS_UP = 0.9;
/** The shaft's sides: earth and old boards, dim. */
const SHAFT: RGB = [120, 104, 88], SHAFT_BANDS = 4;

/** A hatch's way down: the side its ladder stands on and the side its lid hinges on (unit a, b in the room's frame). */
export interface HatchSides { readonly ladder: readonly [number, number]; readonly hinge: readonly [number, number] }

/** Half the hatch `f` across, towards side `s`. */
const hatchEdge = (f: InteriorFixture, s: readonly [number, number]): number => Math.abs(s[0]) * f.w / 2 + Math.abs(s[1]) * f.d / 2;

/**
 * The hatch `f`'s ladder side: the first with room to stand before it; its lid's hinge: across from the ladder,
 * else beside it, a side the lid leaning back does not run into (a hearth, a wall).
 */
export function hatchSides(plan: InteriorPlan, f: InteriorFixture): HatchSides {
  const ladder = SIDES.find(([da, db]) => !interiorBlocked(plan, f.a + da * (HATCH_STAND + f.w / 2), f.b + db * (HATCH_STAND + f.d / 2), 0.3, f.storey, true)) ?? SIDES[0];
  const [da, db] = ladder;
  const room = (s: readonly [number, number]) => !interiorBlocked(plan, f.a + s[0] * (hatchEdge(f, s) + HATCH_LEAN), f.b + s[1] * (hatchEdge(f, s) + HATCH_LEAN), 0.12, f.storey, true);
  const hinge = ([[-da, -db], [db, -da], [-db, da]] as [number, number][]).find(room) ?? [-da, -db];
  return { ladder, hinge };
}

/** An open hatch: the shaft under it, its ladder down the ladder's side (rungs from the floor down), dark at the bottom. */
function hatchShaft(o: Out, f: InteriorFixture, sides: HatchSides): void {
  const a0 = f.a - f.w / 2, a1 = f.a + f.w / 2, b0 = f.b - f.d / 2, b1 = f.b + f.d / 2, y0 = -HATCH_SHAFT;
  const uv = (p: number[][], n: number[]) => p.map((q) => planeUV(q, n));
  // The sides in bands, darker the deeper: the room's light hardly reaches the bottom.
  for (let k = 0; k < SHAFT_BANDS; k++) {
    const t0 = -(k / SHAFT_BANDS) * HATCH_SHAFT, t1 = -((k + 1) / SHAFT_BANDS) * HATCH_SHAFT, f = (1 - k / SHAFT_BANDS) ** 2;
    const c: RGB = [Math.round(SHAFT[0] * f), Math.round(SHAFT[1] * f), Math.round(SHAFT[2] * f)];
    const side = (p: number[][], n: number[]) => o.quad(p, n, uv(p, n), BuildingMat.Oak, c);
    side([[a0, t1, b0], [a1, t1, b0], [a1, t0, b0], [a0, t0, b0]], [0, 0, 1]);
    side([[a0, t1, b1], [a1, t1, b1], [a1, t0, b1], [a0, t0, b1]], [0, 0, -1]);
    side([[a0, t1, b0], [a0, t1, b1], [a0, t0, b1], [a0, t0, b0]], [1, 0, 0]);
    side([[a1, t1, b0], [a1, t1, b1], [a1, t0, b1], [a1, t0, b0]], [-1, 0, 0]);
  }
  o.quad([[a0, y0, b0], [a1, y0, b0], [a1, y0, b1], [a0, y0, b1]], [0, 1, 0], [[a0, b0], [a1, b0], [a1, b1], [a0, b1]], BuildingMat.Slate, HOLE);
  // The ladder: the rungs' line HATCH_RUNG_IN inside the edge, two rails and a rung each HATCH_RUNG, from HATCH_RAILS_UP over the floor down.
  const [la, lb] = sides.ladder, out = hatchEdge(f, sides.ladder) - HATCH_RUNG_IN, across = hatchEdge(f, [lb, la]);
  const hw = Math.min(0.3, across - 0.12), ca = f.a + la * out, cb = f.b + lb * out;
  // A box round the rung line: `t0..t1` across it, `d` either side of it, y0..y1.
  const bar = (t0: number, t1: number, d: number, ya: number, yb: number) => la
    ? o.box(ca - d, ca + d, ya, yb, cb + t0, cb + t1, BuildingMat.Oak, DARK, true)
    : o.box(ca + t0, ca + t1, ya, yb, cb - d, cb + d, BuildingMat.Oak, DARK, true);
  for (const t of [-hw - 0.05, hw]) bar(t, t + 0.05, 0.035, y0, HATCH_RAILS_UP + 0.06);
  for (let k = -Math.round(HATCH_RAILS_UP / HATCH_RUNG); k * HATCH_RUNG <= HATCH_SHAFT + 1e-6; k++) bar(-hw, hw, 0.02, -k * HATCH_RUNG - 0.035, -k * HATCH_RUNG);
}

/** The dark under an open hatch (near black: the room's lamp hardly shows on it). */
const HOLE: RGB = [6, 5, 4];

const hatchRects = (plan: InteriorPlan, storey: number): Rect[] => plan.fixtures.filter((f) => f.kind === 'hatch' && f.storey === storey).map((f) => ({ a0: f.a - f.w / 2, a1: f.a + f.w / 2, b0: f.b - f.d / 2, b1: f.b + f.d / 2 }));

/**
 * The lid of the house's hatch alone, closed, where `interiorMesh` would draw it (`origin` as there), lit as the
 * room is; null: no hatch. A game swings it open about one of its edges (the house drawn with `lid: false`).
 */
export function hatchLidMesh(plan: InteriorPlan, b: TownBuilding, origin: [number, number, number]): BuildingMesh | null {
  const f = plan.fixtures.find((x) => x.kind === 'hatch');
  if (!f) return null;
  const st = plan.storeys[f.storey], ux = Math.cos(b.angle), uz = Math.sin(b.angle);
  const o = new Out(new Frame({ cx: b.cx, cz: b.cz, ux, uz, vx: b.vx, vz: b.vz, y: b.floorY + st.y }, origin));
  hatchLid(o, f);
  const m = toMesh(o);
  daylight(m, b, origin, st, houseShape(b).storeys[f.storey], f.storey === 0);
  return m;
}

/** Writes each vertex's daylight level (INSIDE_LIGHT) from the storey's openings. */
function daylight(m: BuildingMesh, b: TownBuilding, origin: [number, number, number], st: InteriorStorey, sh: HouseShape['storeys'][number], doorOpen: boolean): void {
  const ux = Math.cos(b.angle), uz = Math.sin(b.angle);
  // The openings as small area lights: middle, inward normal, area (in the frame, y over the storey floor).
  const lights: { a: number; y: number; b: number; na: number; nb: number; area: number }[] = [];
  for (const w of sh.walls) {
    const len = Math.hypot(w.a1 - w.a0, w.b1 - w.b0), da = (w.a1 - w.a0) / len, db = (w.b1 - w.b0) / len;
    for (const q of w.opens) {
      if (q.door && !doorOpen) continue;
      const s = (q.s0 + q.s1) / 2;
      lights.push({ a: w.a0 + da * s - db * WALL, y: sh.y0 + (q.t0 + q.t1) / 2 - st.y, b: w.b0 + db * s + da * WALL, na: -db, nb: da, area: (q.s1 - q.s0) * (q.t1 - q.t0) * (q.door ? 1 : 0.8) });
    }
  }
  // Light thrown about the room: the openings' share of its surface, half of it reflected.
  const wa = st.a1 - st.a0, wb = st.b1 - st.b0, surface = 2 * (wa * wb + (wa + wb) * st.height);
  const bounce = 0.5 * lights.reduce((t, l) => t + l.area, 0) / surface;
  const n = m.position.length / 3;
  for (let i = 0; i < n; i++) {
    const dx = m.position[i * 3] + origin[0] - b.cx, dz = m.position[i * 3 + 2] + origin[2] - b.cz;
    const a = dx * ux + dz * uz, bb = dx * b.vx + dz * b.vz, y = m.position[i * 3 + 1] + origin[1] - b.floorY - st.y;
    const nx = m.normal[i * 3], ny = m.normal[i * 3 + 1], nz = m.normal[i * 3 + 2];
    const nA = nx * ux + nz * uz, nB = nx * b.vx + nz * b.vz;
    let f = bounce;
    for (const l of lights) {
      const ea = a - l.a, ey = y - l.y, eb = bb - l.b, d2 = Math.max(0.25, ea * ea + ey * ey + eb * eb), d = Math.sqrt(d2);
      const cw = (ea * l.na + eb * l.nb) / d, cv = -(ea * nA + ey * ny + eb * nB) / d;
      if (cw > 0 && cv > 0) f += (l.area * cw * cv) / (Math.PI * d2);
    }
    const level = Math.min(INSIDE_LEVELS, Math.max(1, Math.round(INSIDE_LEVELS * Math.sqrt(Math.min(1, f)))));
    m.mat[i] += INSIDE_LIGHT * level;
  }
}

/**
 * The inside as boxes a body is walled in by (in the building's frame): every storey's floor and the top
 * ceiling (open over the stairs), the walls (open at the door; the windows count as shut), the steps,
 * the rails, the hearth and the chimney breast. A game makes its walls and floors of these.
 */
export function interiorSolids(plan: InteriorPlan): InteriorBox[] {
  const out: InteriorBox[] = [];
  const T = 0.4;
  plan.storeys.forEach((st, k) => {
    const room: Rect = { a0: st.a0, a1: st.a1, b0: st.b0, b1: st.b1 };
    const below = k > 0 ? plan.storeys[k - 1].y + plan.storeys[k - 1].height : st.y - 1;
    for (const q of rectMinus(room, wellRects(plan, k))) out.push({ ...q, y0: below, y1: st.y });
    const y0 = below - 0.05, y1 = st.y + st.height + 0.05;
    out.push({ a0: st.a0 - T, a1: st.a0, y0, y1, b0: st.b0 - T, b1: st.b1 + T }, { a0: st.a1, a1: st.a1 + T, y0, y1, b0: st.b0 - T, b1: st.b1 + T });
    out.push({ a0: st.a0 - T, a1: st.a1 + T, y0, y1, b0: st.b1, b1: st.b1 + T });
    if (k === 0) {
      const w = plan.doorW, h = st.y + plan.doorH;
      out.push({ a0: st.a0 - T, a1: -w, y0, y1, b0: st.b0 - T, b1: st.b0 }, { a0: w, a1: st.a1 + T, y0, y1, b0: st.b0 - T, b1: st.b0 }, { a0: -w, a1: w, y0: h, y1, b0: st.b0 - T, b1: st.b0 });
    } else out.push({ a0: st.a0 - T, a1: st.a1 + T, y0, y1, b0: st.b0 - T, b1: st.b0 });
    if (k + 1 === plan.storeys.length) out.push({ ...room, y0: st.y + st.height, y1: st.y + st.height + T });
    for (const f of plan.fixtures) {
      if (f.storey !== k || !(f.kind === 'rail' || f.kind === 'hearth' || f.kind === 'flue' || f.kind === 'forge' || f.kind === 'oven')) continue;
      out.push({ a0: f.a - f.w / 2, a1: f.a + f.w / 2, y0: st.y, y1: st.y + Math.min(f.h, st.height), b0: f.b - f.d / 2, b1: f.b + f.d / 2 });
    }
    for (const s of plan.stairs) {
      if (s.storey !== k) continue;
      const pa = Math.abs(s.db), pb = Math.abs(s.da);
      for (let i = 0; i < s.steps; i++) {
        const x0 = i * s.tread, x1 = x0 + s.tread;
        const ea = [s.a + s.da * x0, s.a + s.da * x1], eb = [s.b + s.db * x0, s.b + s.db * x1];
        out.push({ a0: Math.min(...ea) - pa * s.w / 2, a1: Math.max(...ea) + pa * s.w / 2, y0: st.y - 0.1, y1: st.y + (i + 1) * s.riser, b0: Math.min(...eb) - pb * s.w / 2, b1: Math.max(...eb) + pb * s.w / 2 });
      }
    }
  });
  return out;
}

function fixture(o: Out, f: InteriorFixture, H: number): void {
  const a0 = f.a - f.w / 2, a1 = f.a + f.w / 2, b0 = f.b - f.d / 2, b1 = f.b + f.d / 2;
  const legs = (top: number, t: number, m: BuildingMat, c: RGB) => {
    for (const [a, b] of [[a0 + t, b0 + t], [a1 - t, b0 + t], [a0 + t, b1 - t], [a1 - t, b1 - t]]) o.box(a - t, a + t, 0, top, b - t, b + t, m, c);
  };
  switch (f.kind) {
    case 'table': case 'bench': case 'workbench':
      o.box(a0, a1, f.h - 0.07, f.h, b0, b1, BuildingMat.Oak, TIMBER, true);
      legs(f.h - 0.07, 0.05, BuildingMat.Oak, DARK);
      break;
    case 'bed':
      o.box(a0, a1, 0, 0.3, b0, b1, BuildingMat.Oak, TIMBER);
      o.box(a0 + 0.05, a1 - 0.05, 0.3, f.h, b0 + 0.05, b1 - 0.05, BuildingMat.Plaster, LINEN);
      break;
    case 'counter': case 'chest': case 'shelf': case 'barrel': case 'tub': case 'woodpile':
      o.box(a0, a1, 0, f.h, b0, b1, BuildingMat.Oak, f.kind === 'woodpile' ? LIGHT_WOOD : f.kind === 'counter' ? DARK : TIMBER);
      break;
    case 'flue':
      o.box(a0, a1, 0, H, b0, b1, BuildingMat.Rubble, SOOT);
      break;
    case 'rail': {
      const along = f.w > f.d, len = along ? f.w : f.d, n = Math.max(2, Math.ceil(len / 1.2) + 1);
      for (let i = 0; i < n; i++) {
        const t = -len / 2 + 0.04 + ((len - 0.08) * i) / (n - 1), pa = along ? f.a + t : f.a, pb = along ? f.b : f.b + t;
        o.box(pa - 0.04, pa + 0.04, 0, f.h - 0.06, pb - 0.04, pb + 0.04, BuildingMat.Oak, DARK);
      }
      o.box(a0, a1, f.h - 0.06, f.h, b0, b1, BuildingMat.Oak, TIMBER, true);
      break;
    }
    case 'door':
      o.box(a0, a1, 0, f.h, b0, b1, BuildingMat.Oak, DARK, true);
      break;
    case 'stair': case 'well':
      break;
    case 'hearth': case 'forge': case 'oven':
      o.box(a0, a1, 0, f.h, b0, b1, BuildingMat.Rubble, SOOT);
      // The breast above it, up to the ceiling (the chimney's stack goes on through the roof).
      {
        const wa = Math.min(f.w / 2, f.w > f.d ? 0.6 : 0.35), wb = Math.min(f.d / 2, f.d > f.w ? 0.6 : 0.35);
        o.box(f.a - wa, f.a + wa, f.h, H, f.b - wb, f.b + wb, BuildingMat.Rubble, SOOT);
      }
      // A dark mouth on the side facing the room.
      if (f.kind !== 'forge') {
        const toward = Math.abs(f.a) > Math.abs(f.b) ? (f.a > 0 ? 'na' : 'a') : (f.b > 0 ? 'nb' : 'b');
        const m = 0.02, y0 = 0.15, y1 = f.h * 0.6;
        if (toward === 'a') o.quad([[a1 + m, y0, f.b - 0.4], [a1 + m, y0, f.b + 0.4], [a1 + m, y1, f.b + 0.4], [a1 + m, y1, f.b - 0.4]], [1, 0, 0], [[0, 0], [1, 0], [1, 1], [0, 1]], BuildingMat.Slate, [30, 24, 20]);
        if (toward === 'na') o.quad([[a0 - m, y0, f.b - 0.4], [a0 - m, y0, f.b + 0.4], [a0 - m, y1, f.b + 0.4], [a0 - m, y1, f.b - 0.4]], [-1, 0, 0], [[0, 0], [1, 0], [1, 1], [0, 1]], BuildingMat.Slate, [30, 24, 20]);
        if (toward === 'nb') o.quad([[f.a - 0.4, y0, b0 - m], [f.a + 0.4, y0, b0 - m], [f.a + 0.4, y1, b0 - m], [f.a - 0.4, y1, b0 - m]], [0, 0, -1], [[0, 0], [1, 0], [1, 1], [0, 1]], BuildingMat.Slate, [30, 24, 20]);
      }
      break;
    case 'anvil':
      o.box(f.a - 0.18, f.a + 0.18, 0, 0.55, f.b - 0.18, f.b + 0.18, BuildingMat.Oak, DARK);
      o.box(a0, a1, 0.55, f.h, b0, b1, BuildingMat.Slate, IRON);
      break;
    case 'hatch':
      // (The lid drawn apart: interiorMesh draws the shaft instead, hatchShaft.)
      hatchLid(o, f);
      break;
    case 'rack': {
      // Two uprights, a bar low and one high; blades and spears leaning in it, a round shield hung at one end.
      const along = f.w > f.d, len = along ? f.w : f.d, at = (t: number): [number, number] => (along ? [f.a + t, f.b] : [f.a, f.b + t]);
      for (const t of [-len / 2 + 0.05, len / 2 - 0.05]) { const [pa, pb] = at(t); o.box(pa - 0.05, pa + 0.05, 0, f.h, pb - 0.05, pb + 0.05, BuildingMat.Oak, DARK); }
      const tall = f.h > 1.5;
      for (const y of [0.3, tall ? 1.15 : f.h - 0.06]) {
        const [p0a, p0b] = at(-len / 2), [p1a, p1b] = at(len / 2);
        o.box(Math.min(p0a, p1a) - (along ? 0 : 0.04), Math.max(p0a, p1a) + (along ? 0 : 0.04), y, y + 0.06, Math.min(p0b, p1b) - (along ? 0.04 : 0), Math.max(p0b, p1b) + (along ? 0.04 : 0), BuildingMat.Oak, TIMBER);
      }
      for (let i = 0; i < 5; i++) {
        const [pa, pb] = at(-len / 2 + 0.25 + i * 0.2), spear = tall && i % 2 === 1, top = spear ? f.h + 0.1 : tall ? 1.05 : f.h + 0.1;
        if (spear) o.box(pa - 0.02, pa + 0.02, 0, top - 0.2, pb - 0.02, pb + 0.02, BuildingMat.Oak, LIGHT_WOOD);
        o.box(pa - 0.025, pa + 0.025, spear ? top - 0.2 : 0.1, top, pb - (spear ? 0.025 : 0.035), pb + (spear ? 0.025 : 0.035), BuildingMat.Slate, STEEL);
        if (!spear) o.box(pa - 0.06, pa + 0.06, top, top + 0.03, pb - 0.06, pb + 0.06, BuildingMat.Slate, IRON);
      }
      // The shield hangs on the upper bar, facing into the room (the wall is behind the rack's back half).
      const [sa, sb] = at(len / 2 - 0.3), inward: [number, number] = along ? [0, f.b > 0 ? -1 : 1] : [f.a > 0 ? -1 : 1, 0];
      roundShield(o, [sa + inward[0] * 0.06, tall ? 1.5 : f.h + 0.2, sb + inward[1] * 0.06], inward, 0.28, SHIELD);
      break;
    }
    case 'pell':
      // A post of rough timber on a block, scarred where it is struck.
      o.box(a0, a1, 0, 0.12, b0, b1, BuildingMat.Oak, DARK);
      o.box(f.a - 0.1, f.a + 0.1, 0.12, f.h, f.b - 0.1, f.b + 0.1, BuildingMat.Oak, LIGHT_WOOD);
      o.box(f.a - 0.12, f.a + 0.12, 1.1, 1.3, f.b - 0.12, f.b + 0.12, BuildingMat.Plaster, LINEN);
      break;
    case 'basin':
      o.box(f.a - 0.3, f.a + 0.3, 0, f.h - 0.2, f.b - 0.3, f.b + 0.3, BuildingMat.Ashlar, STONE);
      o.box(a0, a1, f.h - 0.2, f.h, b0, b1, BuildingMat.Ashlar, STONE);
      break;
  }
}

/**
 * Whether a body of radius `r` at (a, b) on `storey` touches a wall or a fixture (benches and beds too:
 * people sit and lie at their spots, beside them). The doorway is open, so one walks out. The stairs and
 * their hole are walked on and through (their steps and the rails wall one in: `interiorSolids`), unless
 * `stand`: where a person could stand still.
 */
export function interiorBlocked(plan: InteriorPlan, a: number, b: number, r: number, storey = 0, stand = false): boolean {
  const s = plan.storeys[storey];
  const inDoor = storey === 0 && Math.abs(a) < plan.doorW - r * 0.5 && b < s.b0 + r;
  if (!inDoor && (a < s.a0 + r || a > s.a1 - r || b < s.b0 + r)) return true;
  if (b > s.b1 - r) return true;
  for (const f of plan.fixtures) {
    if (f.storey !== storey || f.kind === 'hatch' || (!stand && (f.kind === 'stair' || f.kind === 'well'))) continue;
    if (Math.abs(a - f.a) < f.w / 2 + r && Math.abs(b - f.b) < f.d / 2 + r) return true;
  }
  return false;
}
