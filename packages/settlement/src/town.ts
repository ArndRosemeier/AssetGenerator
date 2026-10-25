/**
 * A medieval small town, planned from a seed and the ground it stands on: a market place, the roads
 * that leave it (they follow the land), an organic outline that grows along the roads, crooked lanes
 * between, plots that face the streets, houses by trade and zone (tall timber-framed houses round the
 * market, cottages with gardens at the edge), a temple with its burial ground, a moot hall and an inn on the market, a
 * smithy on a road out, and the fixtures people use (well, stalls, anvil, woodpiles, gardens).
 *
 * Pure: no three.js, runs in workers and tests. The same site gives the same town.
 */
import { Noise, Rng, angleDiff, deriveSeed } from '@futuremagic/core';
import { difference, intersection, shapeArea, shapesToPolys, strokePolylines, union, type Shape } from './clip';
import { chaikin, distSqPointSeg, ensureCCW, minAreaRect, pointInPoly, polyArea, polyBounds, polyCentroid, type Poly } from './geom2';
import { perimeterLots, type Lot, type LotRules } from './lots';
import { organicCuts } from './streets';

/** Where a town goes and what the land there is like. */
export interface TownSite {
  seed: number;
  /** The market place's middle, world metres. */
  x: number;
  z: number;
  /** Typical outline radius, m (a small town: 110-170). */
  radius?: number;
  /** Ground height. */
  height: (x: number, z: number) => number;
  /** Water depth (> 0: water). Streets and plots keep out of it. */
  water?: (x: number, z: number) => number;
  /** Directions (radians, atan2(z, x)) the roads leave in, e.g. towards the neighbours. Default: 3-4 by seed. */
  roads?: number[];
}

export type StreetKind = 'road' | 'lane' | 'track';

export interface TownStreet {
  kind: StreetKind;
  /** Centre line (x, z, ...). */
  pts: number[];
  /** Width, m. */
  width: number;
  /** A closed loop (the edge track). */
  closed?: boolean;
}

export type BuildingKind = 'house' | 'cottage' | 'inn' | 'smithy' | 'bakery' | 'workshop' | 'temple' | 'hall' | 'stable' | 'mill';
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
  | 'grave' | 'offering';

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
  buildings: TownBuilding[];
  fixtures: Fixture[];
}

const ROAD_W = 6;
const LANE_W = 4;
const TRACK_W = 3;

export function planTown(site: TownSite): TownPlan {
  const seed = deriveSeed(site.seed, 'town');
  const rng = new Rng(seed);
  const R = site.radius ?? rng.range(115, 160);
  const cx = site.x, cz = site.z;
  const water = site.water ?? (() => 0);
  const wet = (x: number, z: number) => water(x, z) > 0;

  // 1. The market place: an irregular triangle or quadrangle.
  const market = marketPlace(rng.fork('market'), cx, cz);

  // 2. The roads out, following the land.
  const dirs = site.roads ?? roadDirections(rng.fork('roads'));
  const roads = dirs.map((d, i) => traceRoad(site, rng.fork('road', i), cx, cz, d, R * 1.5));

  // 3. The outline: round, but grown along the roads, and stopping short of water.
  const outline = townOutline(new Noise(deriveSeed(seed, 'outline')), cx, cz, R, dirs, wet);

  // 4. The ground between: the outline less roads, market and edge track, split by lanes.
  const streets: TownStreet[] = roads.map((pts) => ({ kind: 'road' as const, pts, width: ROAD_W }));
  streets.push({ kind: 'track', pts: outline, width: TRACK_W, closed: true });
  const open = union([...shapesToPolys(strokePolylines(roads, ROAD_W / 2, 'round', 'round')), market]);
  const sectors = difference([outline], shapesToPolys(open));
  const lanes: number[][] = [];
  const lr = rng.fork('lanes');
  for (const s of sectors) {
    if (shapeArea(s) < 400) continue;
    for (const ch of organicCuts(s.outer, [48, 90], lr, 14).cuts) lanes.push(crooked(ch, lr));
  }
  for (const pts of lanes) streets.push({ kind: 'lane', pts, width: LANE_W });
  const ring = [...outline, outline[0], outline[1]];
  const cut = union([
    ...shapesToPolys(strokePolylines(lanes, LANE_W / 2, 'round', 'round')),
    ...shapesToPolys(strokePolylines([ring], TRACK_W / 2, 'round', 'butt')),
  ]);
  const blocks: Shape[] = [];
  for (const s of sectors) for (const b of difference([s.outer], shapesToPolys(cut))) if (shapeArea(b) > 150) blocks.push(b);

  // 5. The temple takes a walled plot near the market; the rest is cut into plots.
  const lots: Lot[] = [];
  const yards: Shape[] = [];
  const buildings: TownBuilding[] = [];
  const fixtures: Fixture[] = [];
  const fix = (kind: FixtureKind, x: number, z: number, yaw: number, building = -1) => {
    if (wet(x, z)) return;
    for (const b of buildings) if (pointInPoly(b.poly, x, z)) return;
    fixtures.push({ id: fixtures.length, kind, x, z, yaw, building });
  };
  const dist = (x: number, z: number) => Math.hypot(x - cx, z - cz) / R;
  let templeGrounds: Shape | null = null;
  const plots: Shape[] = [...blocks];
  const near = (b: Shape) => { let m = Infinity; for (let i = 0; i < b.outer.length; i += 2) m = Math.min(m, dist(b.outer[i], b.outer[i + 1])); return m; };
  const crr = rng.fork('temple');
  for (const blk of blocks.filter((b) => near(b) < 0.4 && shapeArea(b) > 900).sort((a, b) => near(a) - near(b))) {
    const yard = groundsIn(blk, cx, cz, crr);
    const b = yard && templeOn(yard, buildings.length, site, crr);
    if (!yard || !b) continue;
    buildings.push(b);
    templeGrounds = yard;
    plots.splice(plots.indexOf(blk), 1, ...difference([blk.outer], [yard.outer]).filter((s) => shapeArea(s) > 150));
    break;
  }
  const zoneRules = (d: number): LotRules => d < 0.42 ? { width: [6, 10], depth: [12, 17] } : d < 0.78 ? { width: [8, 13], depth: [13, 19] } : { width: [12, 19], depth: [16, 25] };
  const lotRng = rng.fork('lots');
  for (const blk of plots) {
    const { lots: ls, yards: ys } = perimeterLots(blk, zoneRules(dist(...polyCentroid(blk.outer))), lotRng);
    for (const l of ls) if (!lotWet(l.poly, wet)) lots.push(l);
    yards.push(...ys);
  }

  // 6. A house on every plot that holds one.
  const br = rng.fork('houses');
  lots.forEach((lot, li) => {
    const b = houseOn(lot, li, buildings.length, dist, site, br, buildings);
    if (b) buildings.push(b);
  });

  // 7. Trades: the inn on the market, a bakery near it, a smithy and a stable on the roads out,
  // a mill by the water, crafts along the roads.
  const tr = rng.fork('trades');
  const nearMarket = (b: TownBuilding) => distToPoly(market, b.door[0], b.door[1]);
  const onRoad = (b: TownBuilding) => Math.min(...roads.map((r) => distToLine(r, b.door[0], b.door[1])));
  const homes = () => buildings.filter((b) => b.kind === 'house' || b.kind === 'cottage');
  const take = (b: TownBuilding | undefined, kind: BuildingKind, trade: string) => { if (b) { b.kind = kind; b.trade = trade; } return b; };
  const inn = take(homes().filter((b) => nearMarket(b) < 8).sort((a, b) => b.hu * b.hv - a.hu * a.hv)[0] ?? homes().sort((a, b) => dist(a.cx, a.cz) - dist(b.cx, b.cz))[0], 'inn', 'innkeeper');
  if (inn) { inn.floors = Math.max(inn.floors, 2) + (tr.chance(0.4) ? 1 : 0); inn.household = 4; }
  const hall = take(homes().filter((b) => nearMarket(b) < 8).sort((a, b) => b.hu * b.hv - a.hu * a.hv)[0] ?? homes().sort((a, b) => nearMarket(a) - nearMarket(b))[0], 'hall', 'reeve');
  if (hall) { hall.floors = 2; hall.wall = 'timber'; hall.household = 2; }
  take(homes().filter((b) => dist(b.cx, b.cz) < 0.5).sort((a, b) => nearMarket(a) - nearMarket(b))[1], 'bakery', 'baker');
  take(homes().filter((b) => onRoad(b) < 6 && dist(b.cx, b.cz) > 0.45).sort((a, b) => dist(b.cx, b.cz) - dist(a.cx, a.cz))[0], 'smithy', 'smith');
  take(homes().filter((b) => onRoad(b) < 6 && dist(b.cx, b.cz) > 0.6).sort((a, b) => b.hu * b.hv - a.hu * a.hv)[0], 'stable', 'carter');
  const mill = homes().filter((b) => waterNear(b, wet, 22)).sort((a, b) => dist(b.cx, b.cz) - dist(a.cx, a.cz))[0];
  if (mill) take(mill, 'mill', 'miller');
  const crafts = ['weaver', 'cobbler', 'carpenter', 'cooper', 'potter', 'tailor', 'chandler', 'butcher'];
  for (const b of tr.shuffle(homes().filter((b) => onRoad(b) < 6 || nearMarket(b) < 8))) {
    if (!crafts.length || !tr.chance(0.55)) continue;
    take(b, 'workshop', crafts.shift()!);
  }

  // 8. The fixtures.
  const fr = rng.fork('fixtures');
  const [mx, mz] = polyCentroid(market);
  fix('well', mx + fr.range(-3, 3), mz + fr.range(-3, 3), fr.range(-Math.PI, Math.PI));
  const mn = market.length >> 1;
  for (let i = 0; i < mn; i++) {
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
    for (let k = 0; k < 140 && fixtures.filter((f) => f.kind === 'grave').length < 18; k++) {
      const x = cr.range(x0, x1), z = cr.range(z0, z1);
      if (!pointInPoly(templeGrounds.outer, x, z) || distToPoly(templeGrounds.outer, x, z) < 2.5) continue;
      if (fixtures.some((f) => f.kind === 'grave' && Math.hypot(f.x - x, f.z - z) < 2.4)) continue;
      fix('grave', x, z, ch.angle + Math.PI / 2, ch.id);
    }
    fix('offering', ch.door[0] + Math.cos(ch.door[2]) * 3, ch.door[1] + Math.sin(ch.door[2]) * 3, ch.door[2] + Math.PI, ch.id);
  }

  return { seed, centre: [cx, cz], radius: R, market, outline, streets, blocks, lots, yards, templeGrounds, buildings, fixtures };
}

// ---------------------------------------------------------------- the layout

function marketPlace(r: Rng, cx: number, cz: number): Poly {
  const n = r.chance(0.35) ? 3 : 4;
  const R = r.range(15, 21) * (n === 3 ? 1.3 : 1);
  const rot = r.range(0, Math.PI * 2);
  const out: Poly = [];
  for (let i = 0; i < n; i++) {
    const a = rot + (i / n) * Math.PI * 2 + r.range(-0.22, 0.22);
    const rr = R * r.range(0.85, 1.15);
    out.push(cx + Math.cos(a) * rr, cz + Math.sin(a) * rr);
  }
  return ensureCCW(out);
}

function roadDirections(r: Rng): number[] {
  const n = r.chance(0.5) ? 3 : 4;
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

/** The town's outline: 64 rays, round with noise, longer along the roads, cut short before water. */
function townOutline(n: Noise, cx: number, cz: number, R: number, dirs: number[], wet: (x: number, z: number) => boolean): Poly {
  const out: Poly = [];
  for (let i = 0; i < 64; i++) {
    const a = (i / 64) * Math.PI * 2;
    let along = 0;
    for (const d of dirs) along = Math.max(along, Math.pow(Math.max(0, Math.cos(angleDiff(a, d))), 10));
    let rr = R * (0.82 + 0.22 * n.fbm2(Math.cos(a) * 1.4, Math.sin(a) * 1.4, 3)) + R * 0.45 * along;
    for (let t = 20; t < rr; t += 4) if (wet(cx + Math.cos(a) * t, cz + Math.sin(a) * t)) { rr = Math.max(20, t - 8); break; }
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
  if (L < 4.5) return null;
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
  let w = Math.min(L - 2 * gap, edge ? r.range(8, 12) : core ? 11 : r.range(8, 12));
  let dep = edge ? r.range(6, 8) : core ? r.range(9, 12) : r.range(7.5, 10);
  const lotArea = Math.abs(polyArea(lot.poly));
  for (let tries = 0; tries < 5; tries++) {
    if (w < 4.5 || dep < 5) return null;
    const t0 = (L - w) / 2;
    const poly = rect(ax + ux * t0 + vx * setback, az + uz * t0 + vz * setback, ux, uz, vx, vz, w, dep);
    const inside = intersection([poly], [lot.poly]).reduce((s, x) => s + shapeArea(x), 0);
    const clash = placed.some((o) => Math.abs(o.cx - poly[0]) < 30 && Math.abs(o.cz - poly[1]) < 30 && intersection([poly], [o.poly]).some((x) => shapeArea(x) > 0.02));
    if (inside >= w * dep * 0.99 && w * dep < lotArea * 0.9 && !clash) {
      const ccx = ax + ux * (t0 + w / 2) + vx * (setback + dep / 2), ccz = az + uz * (t0 + w / 2) + vz * (setback + dep / 2);
      return makeBuilding(id, edge ? 'cottage' : 'house', ccx, ccz, ux, uz, vx, vz, w / 2, dep / 2, attached, core, edge, li, site, r);
    }
    if (tries % 2 === 0) dep *= 0.85; else w *= 0.88;
  }
  return null;
}

function makeBuilding(id: number, kind: BuildingKind, cx: number, cz: number, ux: number, uz: number, vx: number, vz: number, hu: number, hv: number, attached: boolean, core: boolean, edge: boolean, li: number, site: TownSite, r: Rng): TownBuilding {
  const poly = ensureCCW(rect(cx - ux * hu - vx * hv, cz - uz * hu - vz * hv, ux, uz, vx, vz, hu * 2, hv * 2));
  const { lo, hi } = groundUnder(poly, site.height);
  const wall: WallKind = edge ? r.weighted(['plaster', 'stone', 'timber'] as const, (k) => ({ plaster: 3, stone: 1.5, timber: 1 })[k]) : r.weighted(['timber', 'plaster', 'stone'] as const, (k) => ({ timber: core ? 4 : 2.5, plaster: 1.5, stone: core ? 1 : 0.6 })[k]);
  const cover: RoofCover = edge ? (r.chance(0.8) ? 'thatch' : 'shingle') : core ? r.weighted(['tile', 'shingle', 'slate'] as const, (k) => ({ tile: 3, shingle: 1.5, slate: 1 })[k]) : r.weighted(['shingle', 'thatch', 'tile'] as const, (k) => ({ shingle: 2, thatch: 1.5, tile: 1.5 })[k]);
  const floors = edge ? 1 : core ? r.int(2, 3) : r.int(1, 2);
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

/** The temple grounds: a walled plot of about 40 × 28 m in the block's corner nearest the market. */
function groundsIn(blk: Shape, cx: number, cz: number, r: Rng): Shape | null {
  let ax = 0, az = 0, best = Infinity;
  for (let i = 0; i < blk.outer.length; i += 2) {
    const d = Math.hypot(blk.outer[i] - cx, blk.outer[i + 1] - cz);
    if (d < best) { best = d; ax = blk.outer[i]; az = blk.outer[i + 1]; }
  }
  const [bx, bz] = polyCentroid(blk.outer);
  const L = Math.hypot(bx - ax, bz - az) || 1;
  const o = minAreaRect(blk.outer);
  const long = r.range(36, 44), short = r.range(26, 30);
  const px = ax + ((bx - ax) / L) * Math.min(L, long * 0.55), pz = az + ((bz - az) / L) * Math.min(L, long * 0.55);
  const ux = o.ux, uz = o.uz, vx = -uz, vz = ux;
  const [hu, hv] = o.hu >= o.hv ? [long / 2, short / 2] : [short / 2, long / 2];
  const sq = rect(px - ux * hu - vx * hv, pz - uz * hu - vz * hv, ux, uz, vx, vz, hu * 2, hv * 2);
  const pieces = intersection([ensureCCW(sq)], [blk.outer]).sort((a, b) => shapeArea(b) - shapeArea(a));
  return pieces.length && shapeArea(pieces[0]) > 600 ? pieces[0] : null;
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
  const hu = Math.min(6, halfShort * 0.42), hv = Math.min(hu * 1.15, halfLong * 0.5 - 1.5);
  if (hv < 4 || hu < 4) return null;
  // u runs across the hall, v along it; the door is at the -v end, the sanctuary in the middle.
  const vx = lx, vz = lz, ux = vz, uz = -vx;
  const ccx = o.cx + vx * 1.2, ccz = o.cz + vz * 1.2;
  const b = makeBuilding(id, 'temple', ccx, ccz, ux, uz, vx, vz, hu, hv, false, false, false, -1, site, r);
  const area = intersection([b.poly], [blk.outer]).reduce((s, x) => s + shapeArea(x), 0);
  if (area < hu * hv * 4 * 0.95) return null;
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

function rect(ax: number, az: number, ux: number, uz: number, vx: number, vz: number, w: number, d: number): Poly {
  return [ax, az, ax + ux * w, az + uz * w, ax + ux * w + vx * d, az + uz * w + vz * d, ax + vx * d, az + vz * d];
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

function lotWet(p: Poly, wet: (x: number, z: number) => boolean): boolean {
  for (let i = 0; i < p.length; i += 2) if (wet(p[i], p[i + 1])) return true;
  const [x, z] = polyCentroid(p);
  return wet(x, z);
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

