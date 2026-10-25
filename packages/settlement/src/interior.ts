/**
 * The inside of a town building's ground floor: a room the size of the footprint, its fixtures (tables
 * and benches, a counter, a hearth, a forge and anvil, beds, chests ...) by the building's kind, and the
 * places people use them (spots, like the town's fixtures). Pure; `interiorMesh` builds it with the same
 * materials and tints as the building's outside (`buildingMesh`), placed anywhere (`origin`).
 *
 * Coordinates: the building's own frame, metres. a runs along the street front (u), b from the street
 * into the plot (v), y up from the floor; (0, 0) is the footprint's middle, the door in the front wall
 * (b = -hb) at a = 0.
 */
import { Rng } from '@futuremagic/core';
import { BuildingMat, Frame, Out, type BuildingMesh, type RGB } from './building';
import type { TownBuilding } from './town';

export type InteriorFixtureKind =
  | 'table' | 'bench' | 'counter' | 'barrel' | 'hearth' | 'bed' | 'chest' | 'shelf'
  | 'forge' | 'anvil' | 'tub' | 'workbench' | 'woodpile' | 'oven' | 'basin'
  /** A trapdoor in the floor (to a cellar): walked over, not round. */
  | 'hatch';

/** A fixture: an axis-aligned block (in the building's frame) from the floor up. */
export interface InteriorFixture {
  readonly kind: InteriorFixtureKind;
  /** Middle, metres. */
  readonly a: number;
  readonly b: number;
  /** Extent along a and b, height. */
  readonly w: number;
  readonly d: number;
  readonly h: number;
}

export type InteriorSpotKind = 'sit' | 'drink' | 'serve' | 'smith' | 'stoke' | 'quench' | 'craft' | 'bake' | 'sleep' | 'pray' | 'tend' | 'warm';

/** Where someone stands or sits to do something, and which way they face (yaw in the frame: atan2(b, a)). */
export interface InteriorSpot {
  readonly kind: InteriorSpotKind;
  readonly a: number;
  readonly b: number;
  readonly yaw: number;
}

export interface InteriorPlan {
  readonly building: number;
  /** Inner half width (along a) and half depth (along b), and the room's height. */
  readonly ha: number;
  readonly hb: number;
  readonly height: number;
  /** The door's half width (in the front wall, at a = 0) and height. */
  readonly doorW: number;
  readonly doorH: number;
  /** Stone floor (flags) or boards. */
  readonly stoneFloor: boolean;
  readonly fixtures: readonly InteriorFixture[];
  readonly spots: readonly InteriorSpot[];
}

/** Wall thickness inside the footprint, metres. */
const WALL = 0.28;
/** Facing: towards +a, +b, -a, -b (atan2(b, a)). */
const FACE_A = 0, FACE_B = Math.PI / 2, FACE_NA = Math.PI, FACE_NB = -Math.PI / 2;

/** The ground floor of `b`, furnished for what it is. */
/** `hatch`: a trapdoor down to a cellar, on free floor one can walk to. */
export function planInterior(b: TownBuilding, opts: { hatch?: boolean } = {}): InteriorPlan {
  const r = new Rng(b.seed ^ 0x1e7e);
  const ha = Math.max(1.6, b.hu - WALL), hb = Math.max(1.6, b.hv - WALL);
  const P = new Planner(ha, hb);
  switch (b.kind) {
    case 'inn': tavern(P, r); break;
    case 'smithy': smithy(P, r); break;
    case 'bakery': bakery(P, r); break;
    case 'temple': temple(P, r); break;
    default: home(P, r, b.kind === 'workshop' || b.kind === 'mill' || b.trade !== '');
  }
  if (opts.hatch) P.hatch();
  const plan: InteriorPlan = {
    building: b.id, ha, hb, height: Math.max(2.4, b.floorH - 0.25), doorW: 0.55, doorH: 2.05,
    stoneFloor: b.kind === 'smithy' || b.kind === 'temple' || b.kind === 'bakery',
    fixtures: P.fixtures, spots: P.spots,
  };
  // Only the spots one can get to from the door (a table may have shut a hearth's off).
  const reach = reachable(plan);
  return { ...plan, spots: plan.spots.filter((s) => SPOT_RING.some(([da, db]) => reach(s.a + da, s.b + db))) };
}

/** Where someone could step from to use a spot: on it, or beside it within a metre. */
const SPOT_RING: readonly (readonly [number, number])[] = [[0, 0], ...[0.4, 0.7, 1.0].flatMap((d) => Array.from({ length: 16 }, (_, k) => [d * Math.cos((k * Math.PI) / 8), d * Math.sin((k * Math.PI) / 8)] as const))];

/** The floor a person (radius 0.3) can walk to from the door, on a 0.2 m grid. */
export function reachable(p: InteriorPlan): (a: number, b: number) => boolean {
  const s = 0.2, r = 0.3, na = Math.ceil((2 * p.ha) / s), nb = Math.ceil((2 * p.hb) / s);
  const seen = new Uint8Array(na * nb), q: number[] = [];
  const i0 = Math.floor(na / 2), j0 = Math.ceil(r / s) + 1;
  seen[j0 * na + i0] = 1;
  q.push(i0, j0);
  while (q.length) {
    const j = q.pop()!, i = q.pop()!;
    for (const [di, dj] of [[1, 0], [-1, 0], [0, 1], [0, -1]]) {
      const ii = i + di, jj = j + dj;
      if (ii < 0 || jj < 0 || ii >= na || jj >= nb || seen[jj * na + ii]) continue;
      if (interiorBlocked(p, -p.ha + (ii + 0.5) * s, -p.hb + (jj + 0.5) * s, r)) continue;
      seen[jj * na + ii] = 1;
      q.push(ii, jj);
    }
  }
  return (a, b) => {
    const i = Math.floor((a + p.ha) / s), j = Math.floor((b + p.hb) / s);
    return i >= 0 && j >= 0 && i < na && j < nb && seen[j * na + i] === 1;
  };
}

/** Places fixtures where they fit: inside the walls, clear of each other and of the way in. */
class Planner {
  readonly fixtures: InteriorFixture[] = [];
  readonly spots: InteriorSpot[] = [];
  /** While a table and its benches go in together (checked as a whole). */
  private batch = false;
  constructor(readonly ha: number, readonly hb: number) {}

  /** Whether a block (with `gap` around it) fits: inside, clear of the others and of the door's way in. */
  fits(a: number, b: number, w: number, d: number, gap = 0.5): boolean {
    if (Math.abs(a) + w / 2 > this.ha + 1e-6 || Math.abs(b) + d / 2 > this.hb + 1e-6) return false;
    // The way in: 1.6 m wide, 1.8 m deep from the door.
    if (Math.abs(a) < 0.8 + w / 2 && b - d / 2 < -this.hb + 1.8) return false;
    return this.fixtures.every((f) => Math.abs(f.a - a) >= (f.w + w) / 2 + gap || Math.abs(f.b - b) >= (f.d + d) / 2 + gap);
  }

  add(kind: InteriorFixtureKind, a: number, b: number, w: number, d: number, h: number, gap = 0.5): boolean {
    if (!this.fits(a, b, w, d, gap)) return false;
    this.fixtures.push({ kind, a, b, w, d, h });
    // Nothing may shut off a spot placed before it (the keeper behind the counter, the hearth, a bench).
    if (this.batch || this.allReachable()) return true;
    this.fixtures.pop();
    return false;
  }

  spot(kind: InteriorSpotKind, a: number, b: number, yaw: number): void {
    this.spots.push({ kind, a, b, yaw });
  }

  /** A trapdoor on free floor, as far back from the door as it fits (looser gaps if need be). */
  hatch(): void {
    for (const gap of [0.4, 0.2, 0]) {
      for (let b = this.hb - 0.6; b > -this.hb + 1.9; b -= 0.2) {
        for (const a of [this.ha - 0.6, -(this.ha - 0.6), 0, this.ha / 2, -this.ha / 2]) {
          if (!this.fits(a, b, 0.9, 0.9, gap)) continue;
          this.fixtures.push({ kind: 'hatch', a, b, w: 0.9, d: 0.9, h: 0.04 });
          const reach = reachable({ building: -1, ha: this.ha, hb: this.hb, height: 2.4, doorW: 0.55, doorH: 2.05, stoneFloor: false, fixtures: this.fixtures, spots: [] });
          if (reach(a, b)) return;
          this.fixtures.pop();
        }
      }
    }
    // Nothing free: at the door's way in (always open).
    this.fixtures.push({ kind: 'hatch', a: 0, b: -this.hb + 1.4, w: 0.9, d: 0.9, h: 0.04 });
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

  /** Whether every spot so far can be got to from the door. */
  private allReachable(): boolean {
    const reach = reachable({ building: -1, ha: this.ha, hb: this.hb, height: 2.4, doorW: 0.55, doorH: 2.05, stoneFloor: false, fixtures: this.fixtures, spots: [] });
    return this.spots.every((s) => SPOT_RING.some(([da, db]) => reach(s.a + da, s.b + db)));
  }

  /** A hearth against a side wall (left or right), and a place to warm oneself in front of it. */
  hearth(side: -1 | 1, b = 0): void {
    const a = side * (this.ha - 0.45);
    if (this.add('hearth', a, b, 0.9, 1.5, 1.3, 0.3)) this.spot('warm', a - side * 1.1, b, side > 0 ? FACE_A : FACE_NA);
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
  P.hearth(-1, r.range(-0.5, 0.5));
  P.tables('drink', 6);
}

function smithy(P: Planner, r: Rng): void {
  const side = r.chance(0.5) ? -1 : 1;
  // Forge against the back wall, the anvil in front of it, the quench tub beside the anvil.
  const fa = side * Math.min(P.ha - 1.0, 1.2);
  P.add('forge', fa, P.hb - 0.7, 1.4, 1.2, 0.9, 0.2);
  P.spot('stoke', fa, P.hb - 1.7, FACE_B);
  P.add('anvil', fa, P.hb - 2.6, 0.4, 0.8, 0.8, 0.2);
  P.spot('smith', fa - side * 0.75, P.hb - 2.6, side > 0 ? FACE_A : FACE_NA);
  if (P.add('tub', fa + side * 1.2, P.hb - 2.6, 0.8, 0.8, 0.6, 0.3)) P.spot('quench', fa + side * 1.2, P.hb - 3.4, FACE_B);
  if (P.add('workbench', -side * (P.ha - 0.35), 0, 0.6, 2.0, 0.9, 0.3)) P.spot('craft', -side * (P.ha - 1.1), 0, side > 0 ? FACE_NA : FACE_A);
  P.add('woodpile', side * (P.ha - 0.4), -P.hb + 2.2, 0.7, 1.4, 0.8, 0.2);
}

function bakery(P: Planner, r: Rng): void {
  P.add('oven', 0, P.hb - 0.8, 2.0, 1.4, 1.5, 0.2);
  P.spot('bake', 0, P.hb - 2.0, FACE_B);
  const side = r.chance(0.5) ? -1 : 1;
  if (P.add('workbench', side * (P.ha - 0.4), 0, 0.7, 2.2, 0.9, 0.3)) P.spot('bake', side * (P.ha - 1.2), 0, side > 0 ? FACE_A : FACE_NA);
  P.add('shelf', -side * (P.ha - 0.25), 0.4, 0.4, 2.0, 1.8, 0.2);
  P.add('barrel', -side * (P.ha - 0.5), -P.hb + 2.3, 0.6, 0.6, 0.9, 0.1);
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
  const side = r.chance(0.5) ? -1 : 1;
  P.hearth(side as -1 | 1, r.range(-0.3, 0.3));
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

/** Inside colours. */
const LIME: RGB = [236, 228, 210];
const SOOT: RGB = [150, 140, 128];
const TIMBER: RGB = [112, 84, 62];
const DARK: RGB = [74, 56, 44];
const IRON: RGB = [70, 70, 74];
const LINEN: RGB = [214, 204, 180];
const STONE: RGB = [196, 188, 176];

/**
 * The room as a mesh (positions relative to `origin`, placed where `at` puts the building's frame: its
 * middle on the ground, facing as the building does). Inner faces only, so the room is seen from inside.
 */
export function interiorMesh(plan: InteriorPlan, b: TownBuilding, at: { x: number; y: number; z: number }, origin: [number, number, number]): BuildingMesh {
  const ux = Math.cos(b.angle), uz = Math.sin(b.angle);
  const o = new Out(new Frame({ cx: at.x, cz: at.z, ux, uz, vx: b.vx, vz: b.vz, y: at.y }, origin));
  const { ha, hb, height: H, doorW, doorH } = plan;
  const r = new Rng(b.seed ^ 0x51de);
  const lime: RGB = r.chance(0.3) ? SOOT : LIME;
  // Floor: flags or boards.
  o.quad([[-ha, 0, -hb], [ha, 0, -hb], [ha, 0, hb], [-ha, 0, hb]], [0, 1, 0], [[-ha, -hb], [ha, -hb], [ha, hb], [-ha, hb]], plan.stoneFloor ? BuildingMat.Ashlar : BuildingMat.Oak, plan.stoneFloor ? STONE : TIMBER);
  // Walls, facing in; the front one around the door.
  const wallMat = b.wall === 'stone' ? BuildingMat.Rubble : BuildingMat.Plaster;
  const wallTint = b.wall === 'stone' ? STONE : lime;
  const inner = (p: number[][], n: number[]) => o.quad(p, n, p.map((q) => (Math.abs(n[0]) > 0.5 ? [q[2], q[1]] : [q[0], q[1]])), wallMat, wallTint);
  inner([[-ha, 0, hb], [ha, 0, hb], [ha, H, hb], [-ha, H, hb]], [0, 0, -1]);
  inner([[-ha, 0, -hb], [-ha, 0, hb], [-ha, H, hb], [-ha, H, -hb]], [1, 0, 0]);
  inner([[ha, 0, hb], [ha, 0, -hb], [ha, H, -hb], [ha, H, hb]], [-1, 0, 0]);
  inner([[-ha, 0, -hb], [-doorW, 0, -hb], [-doorW, H, -hb], [-ha, H, -hb]], [0, 0, 1]);
  inner([[doorW, 0, -hb], [ha, 0, -hb], [ha, H, -hb], [doorW, H, -hb]], [0, 0, 1]);
  inner([[-doorW, doorH, -hb], [doorW, doorH, -hb], [doorW, H, -hb], [-doorW, H, -hb]], [0, 0, 1]);
  // The door itself (shut behind whoever came in), and its frame.
  o.box(-doorW, doorW, 0, doorH, -hb - 0.12, -hb - 0.04, BuildingMat.Oak, DARK);
  o.box(-doorW - 0.12, -doorW, 0, doorH + 0.12, -hb, -hb + 0.06, BuildingMat.Oak, TIMBER);
  o.box(doorW, doorW + 0.12, 0, doorH + 0.12, -hb, -hb + 0.06, BuildingMat.Oak, TIMBER);
  o.box(-doorW, doorW, doorH, doorH + 0.12, -hb, -hb + 0.06, BuildingMat.Oak, TIMBER);
  // Ceiling boards and the joists under them.
  o.quad([[-ha, H, -hb], [-ha, H, hb], [ha, H, hb], [ha, H, -hb]], [0, -1, 0], [[-ha, -hb], [-ha, hb], [ha, hb], [ha, -hb]], BuildingMat.Oak, TIMBER);
  for (let a = -ha + 0.6; a < ha - 0.3; a += 1.1) o.box(a - 0.09, a + 0.09, H - 0.2, H, -hb, hb, BuildingMat.Oak, DARK, true);
  for (const f of plan.fixtures) fixture(o, f);
  return {
    position: Float32Array.from(o.pos), normal: Float32Array.from(o.nrm), uv: Float32Array.from(o.uv),
    mat: Uint8Array.from(o.mat), tint: Uint8Array.from(o.tint), index: Uint32Array.from(o.idx),
  };
}

function fixture(o: Out, f: InteriorFixture): void {
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
      o.box(a0, a1, 0, f.h, b0, b1, BuildingMat.Oak, f.kind === 'woodpile' ? [150, 118, 84] : f.kind === 'counter' ? DARK : TIMBER);
      break;
    case 'hearth': case 'forge': case 'oven':
      o.box(a0, a1, 0, f.h, b0, b1, BuildingMat.Rubble, SOOT);
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
      // Planks a shade lighter than the floor (it lies in a dark corner), two battens and an iron ring.
      o.box(a0, a1, 0, f.h, b0, b1, BuildingMat.Oak, [150, 116, 84]);
      for (const t of [-0.25, 0.25]) o.box(a0 + 0.06, a1 - 0.06, f.h, f.h + 0.025, f.b + t * f.d - 0.05, f.b + t * f.d + 0.05, BuildingMat.Oak, TIMBER);
      o.box(f.a - 0.1, f.a + 0.1, f.h, f.h + 0.03, f.b - 0.1, f.b + 0.1, BuildingMat.Slate, [120, 120, 126]);
      break;
    case 'basin':
      o.box(f.a - 0.3, f.a + 0.3, 0, f.h - 0.2, f.b - 0.3, f.b + 0.3, BuildingMat.Ashlar, STONE);
      o.box(a0, a1, f.h - 0.2, f.h, b0, b1, BuildingMat.Ashlar, STONE);
      break;
  }
}

/**
 * Whether a body of radius `r` at (a, b) in the room's frame touches a wall or a fixture (benches and
 * beds too: people sit and lie at their spots, beside them). The doorway is open, so one walks out.
 */
export function interiorBlocked(plan: InteriorPlan, a: number, b: number, r: number): boolean {
  const inDoor = Math.abs(a) < plan.doorW - r * 0.5 && b < -plan.hb + r;
  if (!inDoor && (Math.abs(a) > plan.ha - r || b < -plan.hb + r)) return true;
  if (b > plan.hb - r) return true;
  for (const f of plan.fixtures) if (f.kind !== 'hatch' && Math.abs(a - f.a) < f.w / 2 + r && Math.abs(b - f.b) < f.d / 2 + r) return true;
  return false;
}
