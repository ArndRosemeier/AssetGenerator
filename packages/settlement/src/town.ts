/**
 * A medieval settlement, planned from a seed and the ground it stands on: a market place, the roads
 * that leave it (they follow the land), an organic outline that grows along the roads, crooked lanes
 * between, plots that face the streets, houses by trade and zone (tall timber-framed houses round the
 * market, cottages with gardens at the edge), a temple with its burial ground, a moot hall and an inn on the market, a
 * smithy on a road out, and the fixtures people use (well, stalls, anvil, woodpiles, gardens). One planner makes
 * every size, from a hamlet of a few cottages round a green to a capital and past it (`sizeRules`: any size on one
 * scale, the named sizes whole numbers on it).
 *
 * Pure: no three.js, runs in workers and tests. The same site gives the same town.
 */
import { Noise, Rng, angleDiff, deriveSeed } from '@futuremagic/core';
import { difference, intersection, shapeArea, shapesToPolys, strokePolylines, union, type Shape } from './clip';
import { chaikin, distSqPointSeg, ensureCCW, minAreaRect, pointInPoly, polyArea, polyBounds, polyCentroid, type Poly } from './geom2';
import { perimeterLots, type Lot, type LotRules } from './lots';
import { organicCuts } from './streets';
import { townWall, type TownWall, type WallRules } from './walls';
import { fixtureClear } from './fixtures';
import { planHarbour, type HarbourPlan, type HarbourSite } from './harbour';
import { edgeWet, polyWet, wetNear } from './wet';
import { farmlandReach, planFarmland, type Farm, type Field, type Paddock, type TownProp } from './farmland';

/** How big a settlement is: an inn and a stable by the road (a waystation), a few farms round a green, a village with its temple and inn, a market town, a capital. */
export type SettlementSize = 'waystation' | 'hamlet' | 'village' | 'town' | 'capital';

/** What a size of settlement has. */
export interface SizeRules {
  /** Typical outline radius, m (rolled between the two). */
  readonly radius: readonly [number, number];
  /** How many roads leave it (one or the other, by seed). */
  readonly roads: readonly [number, number];
  /** The market place's size against a town's (a hamlet's is its green). */
  readonly market: number;
  /** Stalls on the market. */
  readonly stalls: boolean;
  /** Lanes between the roads: the spacing of the cuts, m (none: the houses face the roads and the green). */
  readonly lanes: readonly [number, number] | null;
  /** The zones: houses are planned as if this far out at least (0.78: all cottages, 0.42: no tall core)... */
  readonly inner: number;
  /** ...and their distance from the middle counts this much (below 1: the tall core reaches farther out). */
  readonly spread: number;
  readonly temple: boolean;
  /** Graves in the burial ground, at most. */
  readonly graves: number;
  /** The trades it has: inn, moot hall, bakery, smithy, stable (a carter), and how many crafts. */
  readonly inn: boolean;
  readonly hall: boolean;
  readonly bakery: boolean;
  readonly smithy: boolean;
  readonly stable: boolean;
  readonly crafts: number;
  /** No plots: its few buildings stand by the road through it, facing each other (a waystation). */
  readonly byRoad?: boolean;
  /** A wall round it, a gate for each road (walls.ts); its fields begin outside the wall. */
  readonly wall?: WallRules;
  /** A seat of rule: a great stone hall in its own walled grounds near the market (the ruler's). */
  readonly seat?: boolean;
  /** More than one inn, smithy or bakery (default one each, as the rules above say). */
  readonly inns?: number;
  readonly smithies?: number;
  readonly bakeries?: number;
  /** Quarters: each stretch between two roads is one, named by what stands in it (`TownPlan.quarters`). */
  readonly quarters?: boolean;
  /**
   * Taller and closer (a capital's): storeys of the houses round the market and of those between it and the
   * edge (default 2-3 and 1-2), and the width of a house round the market, m (default 11; narrower: more to a street).
   */
  readonly tall?: { readonly core: readonly [number, number]; readonly mid: readonly [number, number]; readonly front: number };
}

/**
 * How big the houses are against real ones, and with them their plots, the lanes between and a settlement's
 * radius (1: true to life). A game's rooms want more floor than real ones (a body passes the tables, the camera
 * fits), so their footprints are drawn this much bigger; change this one number to resize every settlement.
 * Storeys keep their real height (the stairs fit in a room's length), and furniture its real size.
 */
export const HOUSE_SCALE = 1.2;
const K = HOUSE_SCALE;

export const SETTLEMENT_SIZES: Readonly<Record<SettlementSize, SizeRules>> = {
  waystation: { radius: [20, 26], roads: [2, 2], market: 0.3, stalls: false, lanes: null, inner: 0.78, spread: 1, temple: false, graves: 0, inn: true, hall: false, bakery: false, smithy: false, stable: true, crafts: 0, byRoad: true },
  hamlet: { radius: [38, 52], roads: [1, 2], market: 0.55, stalls: false, lanes: null, inner: 0.78, spread: 1, temple: false, graves: 0, inn: false, hall: false, bakery: false, smithy: false, stable: false, crafts: 0 },
  village: { radius: [62, 85], roads: [2, 3], market: 0.75, stalls: true, lanes: [70, 120], inner: 0.42, spread: 1, temple: true, graves: 10, inn: true, hall: false, bakery: false, smithy: true, stable: false, crafts: 2 },
  town: { radius: [115, 160], roads: [3, 4], market: 1, stalls: true, lanes: [48, 90], inner: 0, spread: 1, temple: true, graves: 18, inn: true, hall: true, bakery: true, smithy: true, stable: true, crafts: 8 },
  capital: {
    radius: [240, 300], roads: [5, 6], market: 1.5, stalls: true, lanes: [44, 80], inner: 0, spread: 0.65, temple: true, graves: 30, inn: true, hall: true, bakery: true, smithy: true, stable: true, crafts: 16,
    wall: { out: 10, height: 8, every: 55 }, seat: true, inns: 3, smithies: 3, bakeries: 3, quarters: true,
    // A city's core: houses of four and five storeys shoulder to shoulder round the market and out along the roads.
    tall: { core: [4, 5], mid: [2, 4], front: 7.5 },
  },
};

/** The named sizes in order: each is a whole number on the size scale (`sizeRules`). */
export const SIZE_SCALE: readonly SettlementSize[] = ['waystation', 'hamlet', 'village', 'town', 'capital'];

/** A size on the scale (a name or a number), as a number. */
export const sizeScale = (size: SettlementSize | number | undefined): number => (typeof size === 'number' ? Math.max(0, size) : SIZE_SCALE.indexOf(size ?? 'town'));

const TALL_DEFAULT = { core: [2, 3] as const, mid: [1, 2] as const, front: 11 };
const rules = new Map<number, SizeRules>();

/**
 * What a settlement of any size has. At a whole number it is that named size's rules (SETTLEMENT_SIZES) exactly;
 * between two, each rule is blended: amounts and ranges in between, what one has and the other lacks (a temple, a
 * wall) from the nearer. Past a capital it grows on: wider, more roads out, more inns, smithies and bakeries, taller
 * houses round the market. One planner for every size.
 */
export function sizeRules(size: SettlementSize | number | undefined): SizeRules {
  const x = sizeScale(size);
  let r = rules.get(x);
  if (r) return r;
  const top = SIZE_SCALE.length - 1, lo = Math.min(top, Math.floor(x)), t = Math.min(1, x - lo);
  const A = SETTLEMENT_SIZES[SIZE_SCALE[lo]];
  if (x > top) r = beyond(SETTLEMENT_SIZES.capital, x - top);
  else if (t === 0) r = A;
  else r = blend(A, SETTLEMENT_SIZES[SIZE_SCALE[lo + 1]], t);
  rules.set(x, r);
  return r;
}

const mix = (a: number, b: number, t: number) => a + (b - a) * t;
const pair = (a: readonly [number, number], b: readonly [number, number], t: number, whole = false): [number, number] => {
  const f = (k: 0 | 1) => (whole ? Math.round(mix(a[k], b[k], t)) : mix(a[k], b[k], t));
  return [f(0), f(1)];
};

function blend(A: SizeRules, B: SizeRules, t: number): SizeRules {
  const near = <T>(a: T, b: T): T => (t < 0.5 ? a : b);
  const ta = A.tall ?? TALL_DEFAULT, tb = B.tall ?? TALL_DEFAULT;
  return {
    radius: pair(A.radius, B.radius, t), roads: pair(A.roads, B.roads, t, true), market: mix(A.market, B.market, t),
    stalls: near(A.stalls, B.stalls), lanes: A.lanes && B.lanes ? pair(A.lanes, B.lanes, t) : near(A.lanes, B.lanes),
    inner: mix(A.inner, B.inner, t), spread: mix(A.spread, B.spread, t), temple: near(A.temple, B.temple),
    graves: Math.round(mix(A.graves, B.graves, t)), inn: near(A.inn, B.inn), hall: near(A.hall, B.hall), bakery: near(A.bakery, B.bakery),
    smithy: near(A.smithy, B.smithy), stable: near(A.stable, B.stable), crafts: Math.round(mix(A.crafts, B.crafts, t)),
    byRoad: near(A.byRoad, B.byRoad), wall: near(A.wall, B.wall), seat: near(A.seat, B.seat), quarters: near(A.quarters, B.quarters),
    inns: Math.round(mix(A.inns ?? 1, B.inns ?? 1, t)), smithies: Math.round(mix(A.smithies ?? 1, B.smithies ?? 1, t)), bakeries: Math.round(mix(A.bakeries ?? 1, B.bakeries ?? 1, t)),
    ...(A.tall || B.tall ? { tall: { core: pair(ta.core, tb.core, t, true), mid: pair(ta.mid, tb.mid, t, true), front: mix(ta.front, tb.front, t) } } : {}),
  };
}

/** A capital grown `e` steps on (e > 0): wider, more of everything, taller round the market (at most six storeys). */
function beyond(C: SizeRules, e: number): SizeRules {
  const grow = 1 + 0.5 * e, tall = C.tall ?? TALL_DEFAULT, up = Math.round(e);
  return {
    ...C,
    radius: [C.radius[0] * grow, C.radius[1] * grow], roads: [C.roads[0] + up, C.roads[1] + up], market: C.market * (1 + 0.35 * e),
    graves: Math.round(C.graves * grow), inns: Math.round((C.inns ?? 1) * grow), smithies: Math.round((C.smithies ?? 1) * grow), bakeries: Math.round((C.bakeries ?? 1) * grow),
    tall: { core: [Math.min(5, tall.core[0] + up), Math.min(6, tall.core[1] + up)], mid: [Math.min(4, tall.mid[0] + up), Math.min(5, tall.mid[1] + up)], front: Math.max(6.5, tall.front - e) },
  };
}

/** Where a town goes and what the land there is like. */
export interface TownSite {
  seed: number;
  /** The market place's middle, world metres. */
  x: number;
  z: number;
  /**
   * How big (default: a small town): one of the named sizes, or any size on their scale (`sizeRules`: waystation
   * 0, hamlet 1, village 2, town 3, capital 4; 3.5 is between a town and a capital, 5 bigger than a capital).
   */
  size?: SettlementSize | number;
  /** Typical outline radius, m (default: rolled for the size; a small town 115-160). */
  radius?: number;
  /** Ground height. */
  height: (x: number, z: number) => number;
  /** Water depth (> 0: water). Streets and plots keep out of it. */
  water?: (x: number, z: number) => number;
  /** Directions (radians, atan2(z, x)) the roads leave in, e.g. towards the neighbours. Default: 3-4 by seed. */
  roads?: number[];
  /** Plan the fields, farmsteads and paddocks round the town (farmland.ts). Default true. */
  farmland?: boolean;
  /** A town by the sea: the shore near it (harbour.ts). It gets a quay, piers and the harbour's trades. */
  harbour?: HarbourSite;
}

/** 'track': the town's edge; 'path': a farm track out in the fields. */
export type StreetKind = 'road' | 'lane' | 'track' | 'path';

export interface TownStreet {
  kind: StreetKind;
  /** Centre line (x, z, ...). */
  pts: number[];
  /** Width, m. */
  width: number;
  /** A closed loop (the edge track). */
  closed?: boolean;
}

export type BuildingKind = 'house' | 'cottage' | 'inn' | 'smithy' | 'bakery' | 'workshop' | 'temple' | 'hall' | 'stable' | 'mill' | 'farmhouse' | 'barn';
export type WallKind = 'timber' | 'stone' | 'plaster';
export type RoofCover = 'thatch' | 'tile' | 'shingle' | 'slate';

export interface TownBuilding {
  id: number;
  kind: BuildingKind;
  /** Trade practised here (a workshop's craft, 'smith', 'baker', ...); '' for a plain home. */
  trade: string;
  /** Footprint: a rectangle. u runs along the street front, v from the street into the plot. */
  cx: number;
  cz: number;
  /** Half width along u, half depth along v, m. */
  hu: number;
  hv: number;
  /** Direction of u (radians, atan2). */
  angle: number;
  /** v's direction (unit), pointing away from the street. */
  vx: number;
  vz: number;
  /** The four corners, counter-clockwise. */
  poly: Poly;
  floors: number;
  /** Storey height, m. */
  floorH: number;
  wall: WallKind;
  roof: 'gable' | 'hip';
  /** The ridge runs along u (eaves to the street) or along v (gable to the street). */
  ridgeAlongU: boolean;
  cover: RoofCover;
  /** Roof pitch, rise per run. */
  pitch: number;
  /** Ground floor level (above the highest corner of the ground under it). */
  floorY: number;
  /** Lowest ground under the footprint (the plinth goes down to it). */
  groundY: number;
  /** Shares a side wall with a neighbour. */
  attached: boolean;
  /** Where one stands outside the door: x, z, and the yaw facing out of the house. */
  door: [number, number, number];
  /** People living here (0: nobody, e.g. the temple). */
  household: number;
  /**
   * A temple's sanctuary: a round drum in the middle of its hall (centre, radius, wall height). The faith
   * is not built in: what is worshipped there is the setting's to say.
   */
  sanctuary?: { cx: number; cz: number; r: number; h: number };
  seed: number;
}

/** Things in the town that offer people something to do (the citizen simulator's smart objects). */
export type FixtureKind =
  | 'well' | 'stall' | 'bench' | 'table' | 'barrel'
  | 'forge' | 'anvil' | 'quench' | 'oven' | 'workbench' | 'trough'
  | 'woodpile' | 'chopblock' | 'garden' | 'washline' | 'chickens'
  | 'grave' | 'offering'
  /** Farm work: a place in a field to plough, sow, hoe or reap; a paddock's gate; hay for the stable. */
  | 'field' | 'paddock' | 'hayrack'
  /** The harbour: a crane on the quay, stacked cargo, nets drying on their racks, a fish stall. */
  | 'crane' | 'cargo' | 'nets' | 'fishstall';

export interface Fixture {
  id: number;
  kind: FixtureKind;
  x: number;
  z: number;
  /** Facing (radians): where someone using it looks. */
  yaw: number;
  /** The building it belongs to, -1 for the town's (well, stalls, graves). */
  building: number;
}

/** What a quarter of a town is (a capital's): round the seat of rule, the temple, the crafts, or just homes. */
export type QuarterKind = 'seat' | 'temple' | 'crafts' | 'common';

/** A quarter: one stretch of the town between two roads out. */
export interface Quarter {
  kind: QuarterKind;
  outline: Poly;
}

export interface TownPlan {
  seed: number;
  centre: [number, number];
  radius: number;
  market: Poly;
  /** The outline (fields begin beyond it). */
  outline: Poly;
  streets: TownStreet[];
  /** Ground between the streets. */
  blocks: Shape[];
  lots: Lot[];
  /** Back yards and gardens. */
  yards: Shape[];
  /** The temple's grounds and burial ground, if any. */
  templeGrounds: Shape | null;
  /** The seat of rule's walled grounds (a capital's), if any. */
  seatGrounds?: Shape | null;
  /** Its wall, gates and towers (a capital's), if any. */
  wall?: TownWall;
  /** Its quarters (a capital's), if any. */
  quarters?: Quarter[];
  buildings: TownBuilding[];
  fixtures: Fixture[];
  /** The farmland's outer edge (farmland.ts; the outline itself when there is none). */
  farmEdge: Poly;
  /** The blocks of open farm ground between the tracks (no trees grow there). */
  furlongs: Poly[];
  fields: Field[];
  paddocks: Paddock[];
  farms: Farm[];
  /** Fences and haystacks. */
  props: TownProp[];
  /** Its harbour (a town by the sea): quay, piers and berths. */
  harbour?: HarbourPlan;
}

const ROAD_W = 6;
const LANE_W = 4;
const TRACK_W = 3;

/** How far a fixture may be moved off a wall (m), in steps of; first straight away from the nearest wall, then aslant, then along it. */
const NUDGE_MAX = 2.5;
const NUDGE_STEP = 0.25;
const NUDGE_TURNS = [0, Math.PI / 4, -Math.PI / 4, Math.PI / 2, -Math.PI / 2];

export function planTown(site: TownSite): TownPlan {
  const seed = deriveSeed(site.seed, 'town');
  const rng = new Rng(seed);
  const S = sizeRules(site.size);
  // Callers that give a radius scale it themselves (by HOUSE_SCALE).
  const R = site.radius ?? rng.range(S.radius[0], S.radius[1]) * K;
  const cx = site.x, cz = site.z;
  const water = site.water ?? (() => 0);
  const wet = (x: number, z: number) => water(x, z) > 0;

  // 1. The market place: an irregular triangle or quadrangle.
  const market = marketPlace(rng.fork('market'), cx, cz, S.market);

  // 2. The roads out, following the land.
  const dirs = site.roads ?? (S.byRoad ? throughRoad(rng.fork('roads')) : roadDirections(rng.fork('roads'), S.roads));
  // Out through the town and on through the fields.
  const farmland = site.farmland ?? true;
  const roadLength = R * 1.5 + (farmland ? farmlandReach(R) * 1.25 + 20 : 0);
  const roads = dirs.map((d, i) => traceRoad(site, rng.fork('road', i), cx, cz, d, roadLength));

  // 3. The outline: round, but grown along the roads, and stopping short of water.
  let outline = townOutline(new Noise(deriveSeed(seed, 'outline')), cx, cz, R, dirs, wet, site.height);
  // A capital's wall, a little outside its edge, a gate on each road. Edge, wall, towers and gates stand dry: where a
  // brook between two rays still crosses them, the town draws back from it (it is built on one bank).
  // A town by the sea: its quay along the waterline, piers out over the water, and a way down from the market to it.
  const harbour = site.harbour ? planHarbour(site.harbour, cx, cz, R, site.height, water) ?? undefined : undefined;
  const rules = S.wall;
  const wall = keepDry(outline, cx, cz, wet, rules ? (o) => townWall(o, roads, rules, ROAD_W, site.height) : null, rules?.out) ?? undefined;
  // The town comes down to its quay (the outline keeps short of the water, the quay runs along it).
  if (harbour) outline = ensureCCW(union([outline, harbour.quay]).reduce((a, b) => (shapeArea(b) > shapeArea(a) ? b : a)).outer);

  // 4. The ground between: the outline less roads, market and edge track, split by lanes.
  const streets: TownStreet[] = roads.map((pts) => ({ kind: 'road' as const, pts, width: ROAD_W }));
  streets.push({ kind: 'track', pts: outline, width: TRACK_W, closed: true });
  if (harbour) streets.push({ kind: 'lane', pts: harbourWay(market, harbour), width: ROAD_W });
  const open = union([...shapesToPolys(strokePolylines(roads, ROAD_W / 2, 'round', 'round')), market, ...(harbour ? [harbour.quay, ...shapesToPolys(strokePolylines([harbourWay(market, harbour)], ROAD_W / 2, 'round', 'round'))] : [])]);
  const sectors = difference([outline], shapesToPolys(open));
  const lanes: number[][] = [];
  const lr = rng.fork('lanes');
  if (S.lanes) for (const s of sectors) {
    if (shapeArea(s) < 400 * K * K) continue;
    for (const ch of organicCuts(s.outer, [S.lanes[0] * K, S.lanes[1] * K], lr, 14 * K).cuts) lanes.push(crooked(ch, lr));
  }
  for (const pts of lanes) streets.push({ kind: 'lane', pts, width: LANE_W });
  const ring = [...outline, outline[0], outline[1]];
  const cut = union([
    ...shapesToPolys(strokePolylines(lanes, LANE_W / 2, 'round', 'round')),
    ...shapesToPolys(strokePolylines([ring], TRACK_W / 2, 'round', 'butt')),
  ]);
  const blocks: Shape[] = [];
  for (const s of sectors) for (const b of difference([s.outer], shapesToPolys(cut))) if (shapeArea(b) > 150 * K * K) blocks.push(b);

  // 5. The temple takes a walled plot near the market; the rest is cut into plots.
  const lots: Lot[] = [];
  const yards: Shape[] = [];
  const buildings: TownBuilding[] = [];
  const fixtures: Fixture[] = [];
  // In the water, unless on the quay (the water under its paving is no matter).
  const fixWet = (x: number, z: number) => wetNear(wet, x, z, FIXTURE_REACH) && !(harbour && pointInPoly(harbour.quay, x, z));
  const fix = (kind: FixtureKind, x: number, z: number, yaw: number, building = -1) => {
    if (fixWet(x, z)) return;
    for (const b of buildings) if (pointInPoly(b.poly, x, z)) return;
    // It and its users keep off the walls (a drinker at the inn's table stood in its front wall): moved off the
    // nearest wall as little as will do, else left out.
    const polys = buildings.filter((b) => Math.hypot(b.cx - x, b.cz - z) < Math.hypot(b.hu, b.hv) + 6).map((b) => b.poly);
    const f: Fixture = { id: fixtures.length, kind, x, z, yaw, building };
    const near = polys.reduce<{ p: Poly | null; d: number }>((m, p) => { const d = distToPoly(p, x, z); return d < m.d ? { p, d } : m; }, { p: null, d: Infinity });
    let ox = 1, oz = 0;
    if (near.p) {
      const e = 0.05, gx = distToPoly(near.p, x + e, z) - distToPoly(near.p, x - e, z), gz = distToPoly(near.p, x, z + e) - distToPoly(near.p, x, z - e), g = Math.hypot(gx, gz);
      if (g > 1e-6) { ox = gx / g; oz = gz / g; }
    }
    for (let d = 0; d <= NUDGE_MAX + 1e-6; d += NUDGE_STEP) {
      for (const turn of d ? NUDGE_TURNS : [0]) {
        const c = Math.cos(turn), s = Math.sin(turn);
        f.x = x + (ox * c - oz * s) * d;
        f.z = z + (ox * s + oz * c) * d;
        if (fixWet(f.x, f.z) || !fixtureClear(f, polys, pointInPoly, distToPoly)) continue;
        fixtures.push(f);
        return;
      }
    }
  };
  const dist = (x: number, z: number) => Math.max(S.inner, (Math.hypot(x - cx, z - cz) / R) * S.spread);
  let templeGrounds: Shape | null = null;
  const plots: Shape[] = S.byRoad ? [] : [...blocks];
  const near = (b: Shape) => { let m = Infinity; for (let i = 0; i < b.outer.length; i += 2) m = Math.min(m, dist(b.outer[i], b.outer[i + 1])); return m; };
  const crr = rng.fork('temple');
  for (const blk of blocks.filter((b) => S.temple && near(b) < Math.max(0.4, S.inner + 0.15) && shapeArea(b) > 900 * K * K).sort((a, b) => near(a) - near(b))) {
    const yard = groundsIn(blk, cx, cz, crr, K);
    const b = yard && templeOn(yard, buildings.length, site, crr);
    if (!yard || !b) continue;
    buildings.push(b);
    templeGrounds = yard;
    plots.splice(plots.indexOf(blk), 1, ...difference([blk.outer], [yard.outer]).filter((s) => shapeArea(s) > 150 * K * K));
    break;
  }
  // A capital's seat of rule takes walled grounds of its own near the market too (not the temple's block).
  let seatGrounds: Shape | null = null;
  const srr = rng.fork('seat');
  for (const blk of S.seat ? plots.filter((b) => near(b) < 0.45 && shapeArea(b) > 1600 * K * K).sort((a, b) => near(a) - near(b)) : []) {
    const yard = groundsIn(blk, cx, cz, srr, 1.3 * K);
    const b = yard && seatOn(yard, buildings.length, site, srr);
    if (!yard || !b) continue;
    buildings.push(b);
    seatGrounds = yard;
    plots.splice(plots.indexOf(blk), 1, ...difference([blk.outer], [yard.outer]).filter((s) => shapeArea(s) > 150 * K * K));
    break;
  }
  const zone = (d: number): LotRules => d < 0.42 ? { width: [6, 10], depth: [12, 17] } : d < 0.78 ? { width: [8, 13], depth: [13, 19] } : { width: [12, 19], depth: [16, 25] };
  const zoneRules = (d: number): LotRules => { const z = zone(d); return { width: [z.width[0] * K, z.width[1] * K], depth: [z.depth[0] * K, z.depth[1] * K] }; };
  const lotRng = rng.fork('lots');
  for (const blk of plots) {
    const { lots: ls, yards: ys } = perimeterLots(blk, zoneRules(dist(...polyCentroid(blk.outer))), lotRng);
    for (const l of ls) if (!polyWet(l.poly, wet)) lots.push(l);
    yards.push(...ys);
  }

  // 6. A house on every plot that holds one (by the road: one on each side of it, facing it).
  const br = rng.fork('houses');
  lots.forEach((lot, li) => {
    const b = houseOn(lot, li, buildings.length, dist, site, br, buildings);
    if (b) buildings.push(b);
  });
  if (S.byRoad) buildings.push(...byTheRoad(roads[0], buildings.length, site, br));

  // 7. Trades: the inn on the market, a bakery near it, a smithy and a stable on the roads out,
  // a mill by the water, crafts along the roads.
  const tr = rng.fork('trades');
  const nearMarket = (b: TownBuilding) => distToPoly(market, b.door[0], b.door[1]);
  const onRoad = (b: TownBuilding) => Math.min(...roads.map((r) => distToLine(r, b.door[0], b.door[1])));
  const homes = () => buildings.filter((b) => b.kind === 'house' || b.kind === 'cottage');
  const take = (b: TownBuilding | undefined, kind: BuildingKind, trade: string) => { if (b) { b.kind = kind; b.trade = trade; } return b; };
  // By the sea the inn is the sailors' tavern on the quay, the harbour master keeps a hall there and cargo waits in warehouses.
  const onQuay = (b: TownBuilding) => (harbour ? distToPoly(harbour.quay, b.door[0], b.door[1]) : Infinity);
  // The houses fronting the quay, biggest first; where too few front it, the nearest to it after them.
  const quayFront = () => {
    const front = homes().filter((b) => onQuay(b) < QUAY_FRONT).sort((a, b) => b.hu * b.hv - a.hu * a.hv);
    return front.length ? front : homes().filter((b) => onQuay(b) < QUAY_NEAR).sort((a, b) => onQuay(a) - onQuay(b));
  };
  const tavern = harbour && S.inn ? take(quayFront()[0], 'inn', 'innkeeper') : undefined;
  if (tavern) { tavern.floors = Math.max(tavern.floors, 2); tavern.household = 4; }
  const master = harbour ? take(quayFront()[0], 'hall', 'harbourmaster') : undefined;
  if (master) { master.floors = Math.max(master.floors, 2); master.wall = 'stone'; master.household = 2; }
  if (harbour) for (let i = 0; i < Math.min(3, harbour.piers.length + 1); i++) take(quayFront()[0], 'workshop', 'warehouse');
  // Fisherfolk mend their nets on the quay and keep their gear in a loft by it.
  if (harbour) for (let i = 0; i < 2; i++) take(quayFront()[0], 'workshop', 'fisher');
  const inn = tavern || S.inn && take(homes().filter((b) => nearMarket(b) < 8).sort((a, b) => b.hu * b.hv - a.hu * a.hv)[0] ?? homes().sort((a, b) => dist(a.cx, a.cz) - dist(b.cx, b.cz))[0], 'inn', 'innkeeper');
  if (inn) { inn.floors = Math.max(inn.floors, 2) + (tr.chance(0.4) ? 1 : 0); inn.household = 4; }
  const hall = S.hall && take(homes().filter((b) => nearMarket(b) < 8).sort((a, b) => b.hu * b.hv - a.hu * a.hv)[0] ?? homes().sort((a, b) => nearMarket(a) - nearMarket(b))[0], 'hall', 'reeve');
  if (hall) { hall.floors = 2; hall.wall = 'timber'; hall.household = 2; }
  if (S.bakery) take(homes().filter((b) => dist(b.cx, b.cz) < 0.5).sort((a, b) => nearMarket(a) - nearMarket(b))[1], 'bakery', 'baker');
  if (S.smithy) take(homes().filter((b) => onRoad(b) < 6 && dist(b.cx, b.cz) > 0.45).sort((a, b) => dist(b.cx, b.cz) - dist(a.cx, a.cz))[0], 'smithy', 'smith');
  // A capital has more of each, spread over the town: the next, apart from those there are.
  const apart = (kind: BuildingKind, m: number) => (b: TownBuilding) => buildings.every((o) => o.kind !== kind || Math.hypot(o.cx - b.cx, o.cz - b.cz) >= m);
  for (let i = 1; i < (S.inns ?? 1); i++) {
    const b = take(homes().filter((b) => onRoad(b) < 6 && dist(b.cx, b.cz) < 0.8 && apart('inn', 90)(b)).sort((a, b) => b.hu * b.hv - a.hu * a.hv)[0], 'inn', 'innkeeper');
    if (b) { b.floors = Math.max(b.floors, 2); b.household = 4; }
  }
  for (let i = 1; i < (S.bakeries ?? 1); i++) take(homes().filter((b) => dist(b.cx, b.cz) < 0.7 && apart('bakery', 80)(b)).sort((a, b) => nearMarket(a) - nearMarket(b))[0], 'bakery', 'baker');
  for (let i = 1; i < (S.smithies ?? 1); i++) take(homes().filter((b) => onRoad(b) < 6 && dist(b.cx, b.cz) > 0.45 && apart('smithy', 120)(b)).sort((a, b) => dist(b.cx, b.cz) - dist(a.cx, a.cz))[0], 'smithy', 'smith');
  if (S.stable) take(homes().filter((b) => onRoad(b) < 6 && dist(b.cx, b.cz) > 0.6).sort((a, b) => b.hu * b.hv - a.hu * a.hv)[0], 'stable', 'carter');
  const mill = homes().filter((b) => waterNear(b, wet, 22)).sort((a, b) => dist(b.cx, b.cz) - dist(a.cx, a.cz))[0];
  if (mill) take(mill, 'mill', 'miller');
  const crafts = ['weaver', 'cobbler', 'carpenter', 'cooper', 'potter', 'tailor', 'chandler', 'butcher', 'tanner', 'dyer', 'glazier', 'fletcher', 'bowyer', 'armourer', 'jeweller', 'bookbinder'].slice(0, S.crafts);
  // Quarters (a capital's): the crafts take the crafts quarter first.
  const quarters = S.quarters ? quartersOf(sectors, buildings) : undefined;
  const craftsQ = quarters?.find((q) => q.kind === 'crafts');
  const inCrafts = (b: TownBuilding) => !!craftsQ && pointInPoly(craftsQ.outline, b.cx, b.cz);
  const shops = tr.shuffle(homes().filter((b) => onRoad(b) < 6 || nearMarket(b) < 8 || inCrafts(b)));
  if (craftsQ) shops.sort((a, b) => Number(inCrafts(b)) - Number(inCrafts(a)));
  if (crafts.length) for (const b of shops) {
    if (!crafts.length || !tr.chance(0.55)) continue;
    take(b, 'workshop', crafts.shift()!);
  }

  // 8. The fixtures.
  const fr = rng.fork('fixtures');
  if (harbour) harbourFixtures(harbour, fix, fr, buildings);
  const [mx, mz] = polyCentroid(market);
  fix('well', mx + fr.range(-3, 3), mz + fr.range(-3, 3), fr.range(-Math.PI, Math.PI));
  const mn = market.length >> 1;
  for (let i = 0; S.stalls && i < mn; i++) {
    const ax = market[i * 2], az = market[i * 2 + 1], bx = market[((i + 1) % mn) * 2], bz = market[((i + 1) % mn) * 2 + 1];
    const L = Math.hypot(bx - ax, bz - az), ux = (bx - ax) / L, uz = (bz - az) / L;
    const inX = -uz, inZ = ux; // the market is counter-clockwise: inward is to the left
    const n = Math.floor(L / 7);
    for (let k = 0; k < n; k++) {
      if (!fr.chance(0.6)) continue;
      const t = (k + 0.5) * (L / n);
      // A stall faces the middle; the seller stands behind it, the buyer in front.
      fix('stall', ax + ux * t + inX * 3.2, az + uz * t + inZ * 3.2, Math.atan2(inZ, inX));
    }
  }
  fix('bench', mx + fr.range(-6, 6), mz + fr.range(-6, 6), fr.range(-Math.PI, Math.PI));
  for (const b of buildings) {
    const [dx, dz, yaw] = b.door;
    const ux = Math.cos(b.angle), uz = Math.sin(b.angle);
    const side = fr.chance(0.5) ? 1 : -1;
    const backX = b.cx + b.vx * (b.hv + 1.2), backZ = b.cz + b.vz * (b.hv + 1.2);
    switch (b.kind) {
      case 'temple':
        break;
      case 'smithy':
        fix('anvil', dx + ux * 1.6 * side, dz + uz * 1.6 * side, yaw + Math.PI, b.id);
        fix('forge', b.cx - b.vx * (b.hv - 0.8) + ux * (b.hu - 1.2) * side, b.cz - b.vz * (b.hv - 0.8) + uz * (b.hu - 1.2) * side, yaw + Math.PI, b.id);
        fix('quench', dx + ux * 2.8 * side, dz + uz * 2.8 * side, yaw + Math.PI, b.id);
        fix('woodpile', backX, backZ, yaw, b.id);
        break;
      case 'inn':
        fix('table', dx + ux * 2.2, dz + uz * 2.2, yaw, b.id);
        fix('table', dx - ux * 2.2, dz - uz * 2.2, yaw, b.id);
        fix('barrel', dx + ux * (b.hu - 0.6), dz + uz * (b.hu - 0.6), yaw, b.id);
        fix('woodpile', backX, backZ, yaw, b.id);
        break;
      case 'bakery':
        fix('oven', backX, backZ, yaw, b.id);
        fix('woodpile', backX + ux * 2, backZ + uz * 2, yaw, b.id);
        break;
      case 'hall':
        fix('bench', dx + ux * 2, dz + uz * 2, yaw, b.id);
        break;
      case 'stable':
        fix('trough', dx + ux * 2 * side, dz + uz * 2 * side, yaw + Math.PI / 2, b.id);
        break;
      case 'workshop':
        fix('workbench', dx + ux * 1.8 * side, dz + uz * 1.8 * side, yaw + Math.PI, b.id);
        break;
      default:
        if (fr.chance(0.35)) fix('bench', dx + ux * 1.5 * side, dz + uz * 1.5 * side, yaw, b.id);
    }
    if (b.kind === 'temple' || b.household === 0) continue;
    // The back: a woodpile against the wall, and where there is room a garden, a washing line, hens.
    if (b.kind !== 'smithy' && b.kind !== 'bakery' && b.kind !== 'inn') fix('woodpile', backX - ux * (b.hu - 1) * side, backZ - uz * (b.hu - 1) * side, yaw, b.id);
    const gx = b.cx + b.vx * (b.hv + 4), gz = b.cz + b.vz * (b.hv + 4);
    if (inYard(yards, lots, gx, gz)) {
      fix('garden', gx, gz, yaw + Math.PI, b.id);
      if (fr.chance(0.4)) fix('washline', gx + ux * 3 * side, gz + uz * 3 * side, b.angle, b.id);
      if (b.kind === 'cottage' && fr.chance(0.5)) fix('chickens', gx - ux * 3 * side, gz - uz * 3 * side, yaw, b.id);
      if (fr.chance(0.3)) fix('chopblock', backX + ux * 1.5 * side, backZ + uz * 1.5 * side, yaw, b.id);
    }
  }
  if (templeGrounds) {
    const ch = buildings.find((b) => b.kind === 'temple')!;
    const cr = rng.fork('graves');
    const [x0, z0, x1, z1] = polyBounds(templeGrounds.outer);
    for (let k = 0; k < 140 && fixtures.filter((f) => f.kind === 'grave').length < S.graves; k++) {
      const x = cr.range(x0, x1), z = cr.range(z0, z1);
      if (!pointInPoly(templeGrounds.outer, x, z) || distToPoly(templeGrounds.outer, x, z) < 2.5) continue;
      if (fixtures.some((f) => f.kind === 'grave' && Math.hypot(f.x - x, f.z - z) < 2.4)) continue;
      fix('grave', x, z, ch.angle + Math.PI / 2, ch.id);
    }
    fix('offering', ch.door[0] + Math.cos(ch.door[2]) * 3, ch.door[1] + Math.sin(ch.door[2]) * 3, ch.door[2] + Math.PI, ch.id);
  }

  // 9. The fields, farmsteads and paddocks round it.
  const people = buildings.reduce((n, b) => n + b.household, 0);
  const land = farmland
    ? planFarmland({ site, rng: rng.fork('farmland'), cx, cz, outline: wall?.ring ?? outline, roads, radius: R, people, buildings, streets, fix: (k, x, z, yaw, b) => fix(k, x, z, yaw, b), wet, roadWidth: ROAD_W })
    : { edge: outline, furlongs: [], fields: [], paddocks: [], farms: [], props: [] };
  // The roads end a little beyond the fields (the world's road network takes over from there).
  if (farmland) for (const st of streets) {
    if (st.kind !== 'road') continue;
    let k = 2;
    while (k < st.pts.length && pointInPoly(land.edge, st.pts[k], st.pts[k + 1])) k += 2;
    st.pts = st.pts.slice(0, Math.min(st.pts.length, k + 12));
  }

  return {
    seed, centre: [cx, cz], radius: R, market, outline, streets, blocks, lots, yards, templeGrounds, buildings, fixtures,
    ...(S.seat ? { seatGrounds } : {}), ...(wall ? { wall } : {}), ...(quarters ? { quarters } : {}),
    ...(harbour ? { harbour } : {}),
    farmEdge: land.edge, furlongs: land.furlongs, fields: land.fields, paddocks: land.paddocks, farms: land.farms, props: land.props,
  };
}

// ---------------------------------------------------------------- the layout

function marketPlace(r: Rng, cx: number, cz: number, scale: number): Poly {
  const n = r.chance(0.35) ? 3 : 4;
  const R = r.range(15, 21) * (n === 3 ? 1.3 : 1) * scale;
  const rot = r.range(0, Math.PI * 2);
  const out: Poly = [];
  for (let i = 0; i < n; i++) {
    const a = rot + (i / n) * Math.PI * 2 + r.range(-0.22, 0.22);
    const rr = R * r.range(0.85, 1.15);
    out.push(cx + Math.cos(a) * rr, cz + Math.sin(a) * rr);
  }
  return ensureCCW(out);
}

/** One road through: out both ways, nearly straight. */
function throughRoad(r: Rng): number[] {
  const d = r.range(0, Math.PI * 2);
  return [d, d + Math.PI + r.range(-0.2, 0.2)];
}

/**
 * Buildings by the road through a waystation: a big one on one side (the inn, two storeys) and a long low
 * one across from it a little along (the stable), each its front to the road.
 */
function byTheRoad(road: number[], id: number, site: TownSite, r: Rng): TownBuilding[] {
  const [ax, az] = [road[0], road[1]];
  const k = Math.min(road.length - 2, 4);
  const L = Math.hypot(road[k] - ax, road[k + 1] - az) || 1;
  const ux = (road[k] - ax) / L, uz = (road[k + 1] - az) / L;
  const out: TownBuilding[] = [];
  const sides = r.chance(0.5) ? [1, -1] : [-1, 1];
  const sizes: [number, number, number][] = [[r.range(6, 7.5) * K, r.range(4.5, 5.5) * K, r.range(-2, 2) * K], [r.range(6.5, 8) * K, r.range(3.5, 4.2) * K, r.range(4, 8) * K]];
  sizes.forEach(([hu, hv, along], i) => {
    // v away from the road: the side's normal.
    const vx = -uz * sides[i], vz = ux * sides[i];
    const off = ROAD_W / 2 + r.range(1.5, 2.5) + hv;
    const cx = ax + ux * along + vx * off, cz = az + uz * along + vz * off;
    const b = makeBuilding(id + i, 'house', cx, cz, ux, uz, vx, vz, hu, hv, false, false, false, i, site, r);
    b.floors = i === 0 ? 2 : 1;
    out.push(b);
  });
  return out;
}

function roadDirections(r: Rng, [few, more]: readonly [number, number]): number[] {
  const n = r.chance(0.5) ? few : more;
  const rot = r.range(0, Math.PI * 2);
  const out: number[] = [];
  for (let i = 0; i < n; i++) out.push(rot + (i / n) * Math.PI * 2 + r.range(-0.3, 0.3));
  return out;
}

/** A road from the middle outwards: each 6 m step turns towards the gentlest, driest way that keeps the heading. */
function traceRoad(site: TownSite, r: Rng, cx: number, cz: number, dir: number, length: number): number[] {
  const step = 6;
  const water = site.water ?? (() => 0);
  const pts = [cx, cz];
  let x = cx, z = cz, h = dir;
  const wiggle = r.range(0.4, 0.9);
  for (let s = 0; s * step < length; s++) {
    let best = h, bestCost = Infinity;
    for (const turn of [-0.32, -0.16, 0, 0.16, 0.32]) {
      const a = h + turn;
      const nx = x + Math.cos(a) * step, nz = z + Math.sin(a) * step;
      const slope = Math.abs(site.height(nx, nz) - site.height(x, z)) / step;
      const cost = slope * 30 + Math.abs(angleDiff(a, dir)) * 1.2 + (water(nx, nz) > 0 ? 6 : 0) + Math.abs(turn) * wiggle + r.range(0, 0.15);
      if (cost < bestCost) { bestCost = cost; best = a; }
    }
    h = best;
    x += Math.cos(h) * step;
    z += Math.sin(h) * step;
    pts.push(x, z);
  }
  return chaikin(pts, 2);
}

/**
 * Ground steeper than this (rise per metre, over CLIFF_RUN m) ends the town: the foot of a cliff, a scarp or a
 * steep hillside (a town keeps to the valley floor and does not climb the wall of a mesa).
 */
const CLIFF = 0.45;
const CLIFF_RUN = 8;

/** Is the ground this steep here, whichever way it falls (a ray crossing a slope aslant must still stop)? */
function steepAt(height: (x: number, z: number) => number, x: number, z: number): boolean {
  const h = CLIFF_RUN / 2;
  const gx = height(x + h, z) - height(x - h, z), gz = height(x, z + h) - height(x, z - h);
  return Math.hypot(gx, gz) > CLIFF * CLIFF_RUN;
}

/** The town's outline: 64 rays, round with noise, longer along the roads, cut short before water and steep ground. */
function townOutline(n: Noise, cx: number, cz: number, R: number, dirs: number[], wet: (x: number, z: number) => boolean, height: (x: number, z: number) => number): Poly {
  const out: Poly = [];
  for (let i = 0; i < 64; i++) {
    const a = (i / 64) * Math.PI * 2;
    let along = 0;
    for (const d of dirs) along = Math.max(along, Math.pow(Math.max(0, Math.cos(angleDiff(a, d))), 10));
    let rr = R * (0.82 + 0.22 * n.fbm2(Math.cos(a) * 1.4, Math.sin(a) * 1.4, 3)) + R * 0.45 * along;
    const ca = Math.cos(a), sa = Math.sin(a);
    for (let t = 20; t < rr; t += 4) {
      const x = cx + ca * t, z = cz + sa * t;
      if (wet(x, z) || steepAt(height, x + ca * CLIFF_RUN, z + sa * CLIFF_RUN)) { rr = Math.max(20, t - 8); break; }
    }
    out.push(cx + Math.cos(a) * rr, cz + Math.sin(a) * rr);
  }
  return ensureCCW(out);
}

/** A lane: the straight cut bent a little, and reaching past both ends so it meets the streets. */
function crooked(ch: number[], r: Rng): number[] {
  const [ax, az, bx, bz] = ch;
  const L = Math.hypot(bx - ax, bz - az), ux = (bx - ax) / L, uz = (bz - az) / L;
  const pts: number[] = [ax - ux * 2, az - uz * 2];
  const k = Math.max(1, Math.round(L / 16));
  for (let i = 1; i < k; i++) {
    const t = (i / k) * L, off = r.range(-1, 1) * Math.min(4, L * 0.06);
    pts.push(ax + ux * t - uz * off, az + uz * t + ux * off);
  }
  pts.push(bx + ux * 2, bz + uz * 2);
  return k > 1 ? chaikin(pts, 1) : pts;
}

// ---------------------------------------------------------------- buildings

function houseOn(lot: Lot, li: number, id: number, dist: (x: number, z: number) => number, site: TownSite, r: Rng, placed: readonly TownBuilding[]): TownBuilding | null {
  const [ax, az, bx, bz] = lot.front;
  const L = Math.hypot(bx - ax, bz - az);
  if (L < 4.5 * K) return null;
  const ux = (bx - ax) / L, uz = (bz - az) / L;
  // v: into the plot (towards its middle).
  const [lcx, lcz] = polyCentroid(lot.poly);
  let vx = -uz, vz = ux;
  if ((lcx - ax) * vx + (lcz - az) * vz < 0) { vx = -vx; vz = -vz; }
  const d = dist((ax + bx) / 2, (az + bz) / 2);
  const core = d < 0.42, edge = d >= 0.78;
  const attached = core ? r.chance(0.85) : !edge && r.chance(0.4);
  const gap = attached ? 0.05 : edge ? r.range(1.5, 3.5) : r.range(0.8, 1.8);
  const setback = core ? 0.3 : edge ? r.range(1.5, 4) : r.range(0.4, 1.5);
  const tall = sizeRules(site.size).tall;
  let w = Math.min(L - 2 * gap, K * (edge ? r.range(8, 12) : core ? tall?.front ?? 11 : r.range(8, 12)));
  let dep = K * (edge ? r.range(6, 8) : core ? r.range(9, 12) : r.range(7.5, 10));
  const lotArea = Math.abs(polyArea(lot.poly));
  for (let tries = 0; tries < 5; tries++) {
    if (w < 4.5 * K || dep < 5 * K) return null;
    const t0 = (L - w) / 2;
    const poly = rect(ax + ux * t0 + vx * setback, az + uz * t0 + vz * setback, ux, uz, vx, vz, w, dep);
    const inside = intersection([poly], [lot.poly]).reduce((s, x) => s + shapeArea(x), 0);
    const clash = placed.some((o) => Math.abs(o.cx - poly[0]) < 30 && Math.abs(o.cz - poly[1]) < 30 && intersection([poly], [o.poly]).some((x) => shapeArea(x) > 0.02));
    if (inside >= w * dep * 0.99 && w * dep < lotArea * 0.9 && !clash) {
      // A hillside or a cliff foot under it: the plot stays empty (a smaller house would not stand better).
      if (tooSteep(poly, site.height)) return null;
      const ccx = ax + ux * (t0 + w / 2) + vx * (setback + dep / 2), ccz = az + uz * (t0 + w / 2) + vz * (setback + dep / 2);
      return makeBuilding(id, edge ? 'cottage' : 'house', ccx, ccz, ux, uz, vx, vz, w / 2, dep / 2, attached, core, edge, li, site, r);
    }
    if (tries % 2 === 0) dep *= 0.85; else w *= 0.88;
  }
  return null;
}

/** A building on a rectangle (u along its front, v away from the door), its look rolled from `r`. */
export function makeBuilding(id: number, kind: BuildingKind, cx: number, cz: number, ux: number, uz: number, vx: number, vz: number, hu: number, hv: number, attached: boolean, core: boolean, edge: boolean, li: number, site: TownSite, r: Rng): TownBuilding {
  const poly = ensureCCW(rect(cx - ux * hu - vx * hv, cz - uz * hu - vz * hv, ux, uz, vx, vz, hu * 2, hv * 2));
  const { lo, hi } = groundUnder(poly, site.height);
  const wall: WallKind = edge ? r.weighted(['plaster', 'stone', 'timber'] as const, (k) => ({ plaster: 3, stone: 1.5, timber: 1 })[k]) : r.weighted(['timber', 'plaster', 'stone'] as const, (k) => ({ timber: core ? 4 : 2.5, plaster: 1.5, stone: core ? 1 : 0.6 })[k]);
  const cover: RoofCover = edge ? (r.chance(0.8) ? 'thatch' : 'shingle') : core ? r.weighted(['tile', 'shingle', 'slate'] as const, (k) => ({ tile: 3, shingle: 1.5, slate: 1 })[k]) : r.weighted(['shingle', 'thatch', 'tile'] as const, (k) => ({ shingle: 2, thatch: 1.5, tile: 1.5 })[k]);
  const tall = sizeRules(site.size).tall;
  const floors = edge ? 1 : core ? r.int(...(tall?.core ?? [2, 3])) : r.int(...(tall?.mid ?? [1, 2]));
  return {
    id, kind, trade: '', cx, cz, hu, hv, angle: Math.atan2(uz, ux), vx, vz, poly,
    floors, floorH: r.range(2.6, 2.9), wall,
    roof: edge && r.chance(0.5) ? 'hip' : 'gable',
    // Round the market the gables face the street; in the rest of the town the eaves often do.
    ridgeAlongU: core ? r.chance(0.25) : r.chance(0.6),
    cover, pitch: cover === 'thatch' ? r.range(1.1, 1.4) : r.range(0.8, 1.15),
    floorY: hi + 0.15, groundY: lo, attached,
    door: [cx - vx * (hv + 0.9), cz - vz * (hv + 0.9), Math.atan2(-vz, -vx)],
    household: edge ? r.int(2, 5) : r.int(2, 6),
    seed: deriveSeed(site.seed, 'building', li),
  };
}

/** The temple grounds: a walled plot of about 40 × 28 m (times `scale`) in the block's corner nearest the market. */
function groundsIn(blk: Shape, cx: number, cz: number, r: Rng, scale = 1): Shape | null {
  let ax = 0, az = 0, best = Infinity;
  for (let i = 0; i < blk.outer.length; i += 2) {
    const d = Math.hypot(blk.outer[i] - cx, blk.outer[i + 1] - cz);
    if (d < best) { best = d; ax = blk.outer[i]; az = blk.outer[i + 1]; }
  }
  const [bx, bz] = polyCentroid(blk.outer);
  const L = Math.hypot(bx - ax, bz - az) || 1;
  const o = minAreaRect(blk.outer);
  const long = r.range(36, 44) * scale, short = r.range(26, 30) * scale;
  const px = ax + ((bx - ax) / L) * Math.min(L, long * 0.55), pz = az + ((bz - az) / L) * Math.min(L, long * 0.55);
  const ux = o.ux, uz = o.uz, vx = -uz, vz = ux;
  const [hu, hv] = o.hu >= o.hv ? [long / 2, short / 2] : [short / 2, long / 2];
  const sq = rect(px - ux * hu - vx * hv, pz - uz * hu - vz * hv, ux, uz, vx, vz, hu * 2, hv * 2);
  const pieces = intersection([ensureCCW(sq)], [blk.outer]).sort((a, b) => shapeArea(b) - shapeArea(a));
  return pieces.length && shapeArea(pieces[0]) > 600 * scale * scale ? pieces[0] : null;
}

/**
 * The seat of rule (a capital's): a great hall of stone in the middle of its grounds, three storeys under a
 * slate roof, its door to the grounds' gate side; the ruler's household lives there.
 */
function seatOn(blk: Shape, id: number, site: TownSite, r: Rng): TownBuilding | null {
  const o = minAreaRect(blk.outer);
  const longU = o.hu >= o.hv;
  const lx = longU ? o.ux : -o.uz, lz = longU ? o.uz : o.ux;
  const halfLong = Math.max(o.hu, o.hv), halfShort = Math.min(o.hu, o.hv);
  // Long side across the grounds: u along the long axis, the door on a long side.
  const hu = Math.min(11 * K, halfLong * 0.55), hv = Math.min(7.5 * K, halfShort * 0.5);
  if (hv < 5 * K || hu < 7 * K) return null;
  const ux = lx, uz = lz, vx = -uz, vz = ux;
  const b = makeBuilding(id, 'hall', o.cx, o.cz, ux, uz, vx, vz, hu, hv, false, true, false, -1, site, r);
  const area = intersection([b.poly], [blk.outer]).reduce((s, x) => s + shapeArea(x), 0);
  if (area < hu * hv * 4 * 0.95) return null;
  if (tooSteep(b.poly, site.height)) return null;
  b.trade = 'ruler';
  b.floors = 3;
  b.floorH = r.range(3.4, 3.8);
  b.wall = 'stone';
  b.cover = 'slate';
  b.roof = 'hip';
  b.ridgeAlongU = true;
  b.pitch = r.range(0.7, 0.85);
  b.household = 6;
  b.seed = deriveSeed(site.seed, 'seat');
  return b;
}

/**
 * The quarters (a capital's): each stretch between two roads out is one: the one with the seat of rule in
 * it is the seat's, the temple's is the temple's, the biggest of the others the crafts', the rest homes.
 */
function quartersOf(sectors: readonly Shape[], buildings: readonly TownBuilding[]): Quarter[] {
  const holds = (s: Shape, kind: BuildingKind, trade?: string) => buildings.some((b) => b.kind === kind && (!trade || b.trade === trade) && pointInPoly(s.outer, b.cx, b.cz));
  const out = sectors.filter((s) => shapeArea(s) > 2000).map((s): Quarter & { area: number } => ({
    kind: holds(s, 'hall', 'ruler') ? 'seat' : holds(s, 'temple') ? 'temple' : 'common', outline: s.outer, area: shapeArea(s),
  }));
  const crafts = out.filter((q) => q.kind === 'common').sort((a, b) => b.area - a.area)[0];
  if (crafts) crafts.kind = 'crafts';
  return out.map(({ kind, outline }) => ({ kind, outline }));
}

/**
 * The temple: a low stone hall with a porch at the front and a round, domed sanctuary rising from its
 * middle; the rest of the grounds is the burial ground.
 */
function templeOn(blk: Shape, id: number, site: TownSite, r: Rng): TownBuilding | null {
  const o = minAreaRect(blk.outer);
  const longU = o.hu >= o.hv;
  const lx = longU ? o.ux : -o.uz, lz = longU ? o.uz : o.ux;
  const halfLong = Math.max(o.hu, o.hv), halfShort = Math.min(o.hu, o.hv);
  // A square-ish hall; the porch takes about 2.5 m in front of it.
  const hu = Math.min(6 * K, halfShort * 0.42), hv = Math.min(hu * 1.15, halfLong * 0.5 - 1.5 * K);
  if (hv < 4 * K || hu < 4 * K) return null;
  // u runs across the hall, v along it; the door is at the -v end, the sanctuary in the middle.
  const vx = lx, vz = lz, ux = vz, uz = -vx;
  const ccx = o.cx + vx * 1.2 * K, ccz = o.cz + vz * 1.2 * K;
  const b = makeBuilding(id, 'temple', ccx, ccz, ux, uz, vx, vz, hu, hv, false, false, false, -1, site, r);
  const area = intersection([b.poly], [blk.outer]).reduce((s, x) => s + shapeArea(x), 0);
  if (area < hu * hv * 4 * 0.95) return null;
  if (tooSteep(b.poly, site.height)) return null;
  b.trade = 'keeper';
  b.floors = 1;
  b.floorH = r.range(5.5, 6.5);
  b.wall = 'stone';
  b.cover = r.chance(0.6) ? 'slate' : 'tile';
  b.roof = 'hip';
  b.ridgeAlongU = false;
  b.pitch = r.range(0.45, 0.55);
  b.household = 0;
  const sr = hu * 0.72;
  b.sanctuary = { cx: ccx, cz: ccz, r: sr, h: b.floorH + hu * b.pitch + r.range(3.6, 4.6) };
  b.door = [ccx - vx * (hv + 3), ccz - vz * (hv + 3), Math.atan2(-vz, -vx)];
  b.seed = deriveSeed(site.seed, 'temple');
  return b;
}

// ---------------------------------------------------------------- helpers

/** A rectangle from corner (ax, az), `w` along u and `d` along v. */
export function rect(ax: number, az: number, ux: number, uz: number, vx: number, vz: number, w: number, d: number): Poly {
  return [ax, az, ax + ux * w, az + uz * w, ax + ux * w + vx * d, az + uz * w + vz * d, ax + vx * d, az + vz * d];
}

/**
 * How much the ground rises under a footprint (m): its corners, the middles of its sides, its centre and the
 * points halfway from the centre to each corner and side, so a cliff foot that passes between the corners
 * shows too.
 */
export function riseUnder(poly: Poly, height: (x: number, z: number) => number): number {
  const [cx, cz] = polyCentroid(poly);
  const n = poly.length >> 1;
  let lo = height(cx, cz), hi = lo;
  const at = (x: number, z: number) => { const h = height(x, z); if (h < lo) lo = h; if (h > hi) hi = h; };
  for (let i = 0; i < n; i++) {
    const x = poly[i * 2], z = poly[i * 2 + 1], j = (i + 1) % n;
    const mx = (x + poly[j * 2]) / 2, mz = (z + poly[j * 2 + 1]) / 2;
    at(x, z); at(mx, mz); at((x + cx) / 2, (z + cz) / 2); at((mx + cx) / 2, (mz + cz) / 2);
  }
  return hi - lo;
}

/**
 * The most the ground may rise under a building (m): a plinth takes up a slope, a cliff foot or a hillside
 * it may not. A metre in five across the building, never less than 2.5 m (a small house on a gentle slope).
 */
export function steepFor(poly: Poly): number {
  let d = 0;
  const n = poly.length >> 1;
  for (let i = 0; i < n; i++) for (let j = i + 1; j < n; j++) d = Math.max(d, Math.hypot(poly[i * 2] - poly[j * 2], poly[i * 2 + 1] - poly[j * 2 + 1]));
  return Math.max(2.5, d * 0.2);
}

/** Too steep to build on: the ground under the footprint rises more than a plinth takes up. */
export function tooSteep(poly: Poly, height: (x: number, z: number) => number): boolean {
  return riseUnder(poly, height) > steepFor(poly);
}

function groundUnder(poly: Poly, height: (x: number, z: number) => number): { lo: number; hi: number } {
  let lo = Infinity, hi = -Infinity;
  const [cx, cz] = polyCentroid(poly);
  for (let i = 0; i <= poly.length; i += 2) {
    const x = i < poly.length ? poly[i] : cx, z = i < poly.length ? poly[i + 1] : cz;
    const h = height(x, z);
    lo = Math.min(lo, h); hi = Math.max(hi, h);
  }
  return { lo, hi };
}

/** A fixture keeps this far from water (m): a stall's legs and awning, a bench's seat. */
const FIXTURE_REACH = 1.8;

/** A house this near the quay (its door, m) fronts it: the harbour's trades take such houses. */
const QUAY_FRONT = 6;
/** Where none fronts it, the harbour's trades take the nearest houses within this of the quay (m). */
const QUAY_NEAR = 30;

/** The way from the market down to the quay: from the market's middle to the quay's middle, a little bent. */
function harbourWay(market: Poly, h: HarbourPlan): number[] {
  const [mx, mz] = polyCentroid(market), n = h.edge.length >> 1, i = n >> 1;
  // To the quay's back edge, then a few metres onto it, so the way meets the paving.
  const qx = h.back[i * 2] + h.out[i * 2] * 4, qz = h.back[i * 2 + 1] + h.out[i * 2 + 1] * 4;
  const L = Math.hypot(qx - mx, qz - mz), k = Math.max(2, Math.round(L / 14)), pts: number[] = [];
  for (let j = 0; j <= k; j++) {
    const t = j / k, bend = Math.sin(t * Math.PI) * Math.min(6, L * 0.05);
    pts.push(mx + (qx - mx) * t - ((qz - mz) / L) * bend, mz + (qz - mz) * t + ((qx - mx) / L) * bend);
  }
  return pts;
}

/**
 * The harbour's fixtures on the quay: a crane by each pier's root, cargo stacked by it, nets drying along the quay and
 * a few fish stalls in a row, all a little in from the water's edge.
 */
function harbourFixtures(h: HarbourPlan, fix: (kind: FixtureKind, x: number, z: number, yaw: number, building?: number) => void, r: Rng, buildings: readonly TownBuilding[]): void {
  const n = h.edge.length >> 1;
  // Cranes and cargo are the warehouses' work, nets the fisherfolk's: each the nearest of its trade's houses.
  // (Where a small harbour has no house of that trade, the harbour master's people see to it.)
  const nearestOf = (trade: string, x: number, z: number) => buildings.filter((b) => b.trade === trade).reduce<TownBuilding | null>((a, b) => (!a || Math.hypot(b.cx - x, b.cz - z) < Math.hypot(a.cx - x, a.cz - z) ? b : a), null);
  const owner = (trade: string, x: number, z: number) => (nearestOf(trade, x, z) ?? nearestOf('harbourmaster', x, z))?.id ?? -1;
  const at = (i: number, inland: number, along: number): [number, number, number] => {
    const k = Math.min(n - 1, Math.max(0, i)), ox = h.out[k * 2], oz = h.out[k * 2 + 1];
    return [h.edge[k * 2] - ox * inland - oz * along, h.edge[k * 2 + 1] - oz * inland + ox * along, Math.atan2(oz, ox)];
  };
  const nearest = (x: number, z: number) => { let b = 0, d = Infinity; for (let i = 0; i < n; i++) { const e = Math.hypot(h.edge[i * 2] - x, h.edge[i * 2 + 1] - z); if (e < d) { d = e; b = i; } } return b; };
  const used: number[] = [];
  for (const p of h.piers) {
    const i = nearest(p.x0, p.z0);
    used.push(i);
    const side = r.chance(0.5) ? 1 : -1;
    // The crane faces the water (its jib swings out over the pier's side); the cargo waits behind it.
    const [x, z, yaw] = at(i, 3.2, side * (p.half + 3.5));
    fix('crane', x, z, yaw, owner('warehouse', x, z));
    const [cx, cz] = at(i, 7.5, side * (p.half + 4.5));
    fix('cargo', cx, cz, yaw + r.range(-0.3, 0.3), owner('warehouse', cx, cz));
    const [dx, dz] = at(i, 7.5, -side * (p.half + 5));
    fix('cargo', dx, dz, yaw + r.range(-0.3, 0.3), owner('warehouse', dx, dz));
  }
  // Along the rest of the quay: nets and fish stalls, clear of the piers' roots.
  const free = (i: number) => used.every((u) => Math.abs(u - i) * 4 > 14);
  let stalls = 0;
  for (let i = 2; i < n - 2; i += 3) {
    if (!free(i)) continue;
    const roll = r.float();
    if (roll < 0.3 && stalls < 4) { const [x, z, yaw] = at(i, 6, 0); fix('fishstall', x, z, yaw); stalls++; }
    else if (roll < 0.55) { const [x, z, yaw] = at(i, 4.5, 0); fix('nets', x, z, yaw, owner('fisher', x, z)); }
  }
}

/** How far (m) the edge draws back from water it crosses, and a wall beyond it (its `out` added) from water under it. */
const DRY_BACK = 8;
/** Rounds of drawing back before the town is taken as it stands. */
const DRY_ROUNDS = 16;

/**
 * Keeps a town's edge, and its wall if it has one (`build` makes it from the edge), off the water: the outline's rays
 * stop at the first water they meet, but a brook can still run between two rays' ends across the edge, or under the
 * wall that stands outside it. Wherever one does, the points of the outline round that way are drawn back short of the
 * water, and the wall (`out` m outside the edge) built anew, until both are dry. Changes `outline` in place (each point moved towards the middle,
 * so it stays counter-clockwise); returns the wall (null without one).
 */
function keepDry<W extends TownWall>(outline: Poly, cx: number, cz: number, wet: (x: number, z: number) => boolean, build: ((o: Poly) => W) | null, out = 0): W | null {
  let wall = build ? build(outline) : null;
  for (let round = 0; round < DRY_ROUNDS; round++) {
    const spots: { x: number; z: number; back: number }[] = [];
    const e = edgeWet(outline, wet);
    if (e) spots.push({ x: e[0], z: e[1], back: DRY_BACK });
    if (wall) {
      const R = wall.ring;
      for (let i = 0; i < R.length; i += 2) if (wetNear(wet, R[i], R[i + 1], wall.thick / 2 + 1)) { spots.push({ x: R[i], z: R[i + 1], back: out + DRY_BACK }); break; }
      for (const t of wall.towers) if (wetNear(wet, t.x, t.z, wall.towerHalf * 1.5)) { spots.push({ x: t.x, z: t.z, back: out + wall.towerHalf + DRY_BACK }); break; }
      for (const g of wall.gates) if (wetNear(wet, g.x, g.z, g.half)) { spots.push({ x: g.x, z: g.z, back: out + DRY_BACK }); break; }
    }
    if (!spots.length) break;
    for (const s of spots) drawBack(outline, cx, cz, s.x, s.z, s.back);
    if (build) wall = build(outline);
  }
  return wall;
}

/** Draws the outline's points round the way of (x, z) back to `back` m short of it (no nearer the middle than 20 m). */
function drawBack(outline: Poly, cx: number, cz: number, x: number, z: number, back: number): void {
  const d = Math.hypot(x - cx, z - cz), a = Math.atan2(z - cz, x - cx);
  // The rays within a stretch about 30 m either side of the spot, and at least the spot's two neighbours.
  const width = Math.max((2 * Math.PI) / 32, Math.atan2(30, Math.max(d, 1)));
  const to = Math.max(20, d - back);
  for (let i = 0; i < outline.length; i += 2) {
    const px = outline[i] - cx, pz = outline[i + 1] - cz, r = Math.hypot(px, pz);
    if (r <= to || Math.abs(angleDiff(Math.atan2(pz, px), a)) > width) continue;
    outline[i] = cx + (px / r) * to;
    outline[i + 1] = cz + (pz / r) * to;
  }
}

function waterNear(b: TownBuilding, wet: (x: number, z: number) => boolean, reach: number): boolean {
  for (let a = 0; a < 8; a++) if (wet(b.cx + Math.cos(a * Math.PI / 4) * reach, b.cz + Math.sin(a * Math.PI / 4) * reach)) return true;
  return false;
}

function inYard(yards: Shape[], lots: Lot[], x: number, z: number): boolean {
  for (const l of lots) if (pointInPoly(l.poly, x, z)) return true;
  for (const y of yards) if (pointInPoly(y.outer, x, z)) return true;
  return false;
}

/** Distance from a point to a polygon's outline. */
export function distToPoly(p: Poly, x: number, z: number): number {
  const n = p.length >> 1;
  let best = Infinity;
  for (let i = 0; i < n; i++) {
    const j = (i + 1) % n;
    best = Math.min(best, distSqPointSeg(x, z, p[i * 2], p[i * 2 + 1], p[j * 2], p[j * 2 + 1]));
  }
  return Math.sqrt(best);
}

/** Distance from a point to a polyline. */
export function distToLine(pts: number[], x: number, z: number): number {
  let best = Infinity;
  for (let i = 0; i + 3 < pts.length; i += 2) best = Math.min(best, distSqPointSeg(x, z, pts[i], pts[i + 1], pts[i + 2], pts[i + 3]));
  return Math.sqrt(best);
}

