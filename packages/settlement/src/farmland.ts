/**
 * The land that feeds a town (planTown calls this last): farmsteads on the roads out, each a farmhouse,
 * a barn and a stable round a yard with a fenced paddock beside it; open fields of long strips in
 * furlongs, out to a distance that grows with the town's people (a hamlet tills a ring of a hundred
 * metres, a big town several hundred); tracks between the furlongs that lead out to them; meadows with
 * haystacks at the far edge and on slopes, kitchen crops (cabbages, beans, flax) next to the houses.
 *
 * Which animals graze a paddock is not decided here: a paddock only says how many (the game picks the
 * kind). Pure, runs in workers and tests.
 */
import { Noise, type Rng, deriveSeed } from '@futuremagic/core';
import { difference, intersection, offset, shapeArea, shapesToPolys, strokePolylines } from './clip';
import { closestOnPolyline, ensureCCW, minAreaRect, pointInPoly, polyBounds, polyCentroid, type Poly } from './geom2';
import { organicCuts } from './streets';
import { makeBuilding, rect, type FixtureKind, type TownBuilding, type TownSite, type TownStreet } from './town';

/** What grows on a field. */
export type CropKind = 'wheat' | 'rye' | 'barley' | 'oats' | 'beans' | 'flax' | 'cabbage' | 'ploughed' | 'fallow' | 'meadow' | 'pasture';

/** Every crop, in a fixed order (games index textures and colours by it). */
export const CROPS: readonly CropKind[] = ['wheat', 'rye', 'barley', 'oats', 'beans', 'flax', 'cabbage', 'ploughed', 'fallow', 'meadow', 'pasture'];

export interface Field {
  id: number;
  /** The strip's outline (counter-clockwise). */
  poly: Poly;
  crop: CropKind;
  /** Which way the furrows and rows run (radians, atan2(z, x)). */
  rows: number;
  /** The farm (index into farms) that works it, -1 none. */
  farm: number;
  /** A paddock's own pasture: the paddock's index, else -1. */
  paddock: number;
}

export interface Paddock {
  id: number;
  /** The fence line (counter-clockwise). */
  poly: Poly;
  farm: number;
  /** How many animals graze in it (the game decides which: horses until there are cattle). */
  animals: number;
  /** The gate: its middle, and the yaw facing into the paddock. */
  gate: [number, number, number];
}

export interface Farm {
  id: number;
  /** The farmhouse (its building id is the farm's: people live and work there), the barn and the stable. */
  house: number;
  barn: number;
  stable: number;
  /** The yard between them. */
  yard: Poly;
  paddock: number;
  /** Its fields, nearest first. */
  fields: number[];
}

/** Things standing in the fields that are not buildings: fences round the paddocks, haystacks. */
export type TownProp =
  /** Posts along the ground (x, ground y, z per post), rails between neighbours; open at the gate. */
  | { kind: 'fence'; posts: number[]; seed: number }
  /** A stack of hay, its foot on the ground at (x, y, z). */
  | { kind: 'haystack'; x: number; y: number; z: number; r: number; h: number; seed: number };

export interface Farmland {
  /** The outer edge of the farmland (fields stop short of it). */
  edge: Poly;
  /** Furlongs: the blocks of land between the tracks the strips were cut from (open ground, no trees). */
  furlongs: Poly[];
  fields: Field[];
  paddocks: Paddock[];
  farms: Farm[];
  props: TownProp[];
}

/** What planTown hands over: the site, the town as planned so far, and a way to add fixtures. */
export interface FarmlandInput {
  site: TownSite;
  rng: Rng;
  cx: number;
  cz: number;
  /** The town's outline and its roads out (centre lines, already long enough to reach the fields' edge). */
  outline: Poly;
  roads: number[][];
  /** The town's typical outline radius (m): the farmland's reach follows it. */
  radius: number;
  /** Everyone living in the town (farmers excluded). */
  people: number;
  /** The town's buildings and streets: the farms' are added to them. */
  buildings: TownBuilding[];
  streets: TownStreet[];
  /** Adds a fixture (it refuses water and buildings, so call it after the buildings are in). */
  fix: (kind: FixtureKind, x: number, z: number, yaw: number, building: number) => void;
  wet: (x: number, z: number) => boolean;
  roadWidth: number;
}

/** Farmland reaches about this far (m) beyond the outline of a town of outline radius `radius`. */
export function farmlandReach(radius: number): number {
  return Math.min(420, Math.max(110, 90 + 2.2 * radius));
}

/** How many farmsteads a town of `people` has round it. */
export function farmCount(people: number): number {
  return Math.min(12, Math.max(2, Math.round(1 + people / 45)));
}

const PATH_W = 3;
/** Next to the houses: kitchen crops. */
const KITCHEN: readonly CropKind[] = ['cabbage', 'beans', 'flax', 'cabbage'];
/** Far out: hay and grazing. */
const OUTFIELD: readonly CropKind[] = ['meadow', 'meadow', 'pasture', 'fallow'];
/** The three fields in turn: winter corn, spring corn, resting. */
const ROTATION: readonly (readonly CropKind[])[] = [['wheat', 'wheat', 'rye'], ['barley', 'oats', 'beans'], ['fallow', 'ploughed']];
/** The odd strip that differs from its furlong. */
const ODD: readonly CropKind[] = ['wheat', 'barley', 'oats', 'fallow', 'ploughed', 'rye'];
/** Grass between two strips (m). */
const BALK = 1.4;

export function planFarmland(input: FarmlandInput): Farmland {
  const { site, rng, cx, cz, outline, roads, wet, streets } = input;
  const W = farmlandReach(input.radius);
  const props: TownProp[] = [];
  const farms: Farm[] = [];
  const paddocks: Paddock[] = [];
  const fields: Field[] = [];

  // 1. The edge: round the outline, W out (give or take), stopping short of water.
  const edge = farmEdge(new Noise(deriveSeed(input.site.seed, 'farmland')), cx, cz, outline, W, wet);
  const inEdge = (x: number, z: number) => pointInPoly(edge, x, z);
  const town = shapesToPolys(offset([outline], 5, 'round'));
  const inTown = (x: number, z: number) => town.some((p) => pointInPoly(p, x, z));

  // 2. Farmsteads along the roads out, spread over the roads and kept apart.
  const fr = rng.fork('farmsteads');
  const want = farmCount(input.people);
  const sites: FarmSite[] = [];
  for (const [ri, road] of roads.entries()) {
    const start = leaveIndex(road, inTown);
    if (start < 0) continue;
    for (let k = start, s = 0; k + 3 < road.length; k += 2) {
      s += Math.hypot(road[k + 2] - road[k], road[k + 3] - road[k + 1]);
      if (s < 30 || s > W * 0.8) continue;
      for (const side of [-1, 1]) sites.push({ road: ri, k, s, side, score: fr.float() * 0.6 + s / W });
    }
  }
  sites.sort((a, b) => a.score - b.score);
  const taken: { x: number; z: number; road: number }[] = [];
  const footprints: Poly[] = [];
  for (let pass = 0; pass < 2 && farms.length < want; pass++) {
    for (const st of sites) {
      if (farms.length >= want) break;
      // First pass: one farm per road before a second on any.
      if (pass === 0 && taken.some((t) => t.road === st.road)) continue;
      const lay = layFarm(st, roads[st.road], input, fr.fork('farm', farms.length));
      if (!lay) continue;
      const [fx, fz] = polyCentroid(lay.footprint);
      if (taken.some((t) => Math.hypot(t.x - fx, t.z - fz) < 75)) continue;
      if (!farmFits(lay, input, inTown, inEdge, footprints, roads)) continue;
      taken.push({ x: fx, z: fz, road: st.road });
      footprints.push(lay.footprint);
      addFarm(lay, input, farms, paddocks, props, fields, fr);
    }
  }

  // 3. The fields: the ring between the town and the edge, less roads and farmsteads, cut into furlongs
  // by tracks and the furlongs into strips.
  const blocked = [
    ...town,
    ...pieceStrokes(roads, input.roadWidth / 2 + 1.5),
    ...shapesToPolys(offset(footprints, 4, 'miter')),
  ];
  const ring = difference([edge], blocked);
  const lr = rng.fork('furlongs');
  const tracks: number[][] = [];
  const furlongs: Poly[] = [];
  for (const piece of ring) {
    if (shapeArea(piece) < 1500) continue;
    const cuts = organicCuts(piece.outer, [80, 150], lr, 30);
    for (const ch of cuts.cuts) {
      // A track along the cut, reaching on to the road or the town's edge track at either end.
      const [ax, az, bx, bz] = ch, L = Math.hypot(bx - ax, bz - az), ux = (bx - ax) / L, uz = (bz - az) / L;
      // (The pieces' holes, farmsteads standing in the fields, are not seen by the cuts: no track through them.)
      if (footprints.length && intersection(shapesToPolys(strokePolylines([[ax - ux * 4, az - uz * 4, bx + ux * 4, bz + uz * 4]], PATH_W)), shapesToPolys(offset(footprints, 1))).length) continue;
      tracks.push([ax - ux * 4, az - uz * 4, (ax + bx) / 2 + lr.range(-2, 2) * uz, (az + bz) / 2 - lr.range(-2, 2) * ux, bx + ux * 4, bz + uz * 4]);
    }
    furlongs.push(...cuts.pieces);
  }
  for (const pts of tracks) streets.push({ kind: 'path', pts, width: PATH_W });
  const cut = [...blocked, ...pieceStrokes(tracks, PATH_W / 2 + 0.6)];
  const cutBounds = cut.map(polyBounds);
  const cr = rng.fork('crops');
  const outFurlongs: Poly[] = [];
  for (const fl of furlongs) {
    // The furlong's own crop (three fields: winter corn, spring corn, fallow), its strips' run and width.
    const o = minAreaRect(fl);
    const along = (o.hu >= o.hv ? o.angle : o.angle + Math.PI / 2) + cr.range(-0.08, 0.08);
    const [fcx, fcz] = polyCentroid(fl);
    const out = distOut(outline, edge, cx, cz, fcx, fcz);
    const garden = out < 0.18;
    const sw = garden ? cr.range(6, 9) : cr.range(11, 19);
    const mainCrop: CropKind = cr.pick(garden ? KITCHEN : out > 0.82 ? OUTFIELD : ROTATION[cr.int(0, 2)]);
    const pieces = difference([fl], near(cut, cutBounds, polyBounds(fl)));
    for (const piece of pieces) {
      if (shapeArea(piece) < 300) continue;
      outFurlongs.push(piece.outer);
      // Strips: long rectangles along the run, side by side across it, grass between.
      const ux = Math.cos(along), uz = Math.sin(along), vx = -uz, vz = ux;
      const [x0, z0, x1, z1] = polyBounds(piece.outer);
      const span = Math.hypot(x1 - x0, z1 - z0);
      const [pcx, pcz] = polyCentroid(piece.outer);
      for (let v = -span / 2, w = 0; v < span / 2; v += w + BALK) {
        w = sw * cr.range(0.8, 1.2);
        const strip = rect(pcx - ux * span - vx * -v, pcz - uz * span - vz * -v, ux, uz, vx, vz, span * 2, w);
        for (const s of intersection([ensureCCW(strip)], shapesToPolys([piece]))) {
          if (s.holes.length || shapeArea(s) < 250 || polyWet(s.outer, wet)) continue;
          let crop: CropKind = cr.chance(0.8) ? mainCrop : cr.pick(garden ? KITCHEN : ODD);
          // Steep strips and those by the water are left to grass: hay meadows.
          if (steep(s.outer, site.height) || waterNear(s.outer, wet, 30)) crop = 'meadow';
          fields.push({ id: fields.length, poly: s.outer, crop, rows: along, farm: -1, paddock: -1 });
        }
      }
    }
  }

  // 4. Each field belongs to the nearest farm; a farm's nearest fields and its paddock get work spots.
  for (const f of fields) {
    if (f.paddock >= 0) continue;
    const [x, z] = polyCentroid(f.poly);
    let best = -1, bd = Infinity;
    for (const fm of farms) {
      const [yx, yz] = polyCentroid(fm.yard), d = Math.hypot(yx - x, yz - z);
      if (d < bd) { bd = d; best = fm.id; }
    }
    f.farm = best;
  }
  const hr = rng.fork('field work');
  for (const fm of farms) {
    const [yx, yz] = polyCentroid(fm.yard);
    const dist = (f: Field) => { const [x, z] = polyCentroid(f.poly); return Math.hypot(x - yx, z - yz); };
    fm.fields = fields.filter((f) => f.farm === fm.id && f.paddock < 0).sort((a, b) => dist(a) - dist(b)).map((f) => f.id);
    let n = 0;
    for (const id of fm.fields) {
      const f = fields[id];
      if (n >= 5 || dist(f) > 260) break;
      if (f.crop === 'meadow' || f.crop === 'pasture') continue;
      for (let k = 0; k < 2; k++) {
        const p = insidePoint(f.poly, hr, 2.5);
        if (p) input.fix('field', p[0], p[1], f.rows + (hr.chance(0.5) ? 0 : Math.PI), fm.house);
      }
      n++;
    }
  }
  // Haystacks on the meadows.
  for (const f of fields) {
    if (f.crop !== 'meadow' || !hr.chance(0.45)) continue;
    for (let k = hr.int(1, 3); k > 0; k--) {
      const p = insidePoint(f.poly, hr, 3);
      if (p) props.push(haystack(p[0], p[1], site, hr));
    }
  }
  return { edge, furlongs: outFurlongs, fields, paddocks, farms, props };
}

// ---------------------------------------------------------------- the edge

/** The farmland's edge: rays from the middle, W beyond the outline with noise, cut short before water. */
function farmEdge(n: Noise, cx: number, cz: number, outline: Poly, W: number, wet: (x: number, z: number) => boolean): Poly {
  const N = 72, r0s: number[] = [], rs: number[] = [];
  for (let i = 0; i < N; i++) {
    const a = (i / N) * Math.PI * 2;
    r0s.push(rayOut(outline, cx, cz, Math.cos(a), Math.sin(a)));
  }
  // Round the town's own spikes (it reaches out along its roads), so the fields end in a soft line.
  const soft = smoothRing(smoothRing(smoothRing(r0s)));
  for (let i = 0; i < N; i++) {
    const a = (i / N) * Math.PI * 2, dx = Math.cos(a), dz = Math.sin(a);
    rs.push(Math.max(r0s[i] + 30, soft[i] + W * (0.8 + 0.4 * n.fbm2(dx * 1.1 + 7.3, dz * 1.1 - 2.1, 2))));
  }
  const out: Poly = [];
  smoothRing(rs).forEach((r, i) => {
    const a = (i / N) * Math.PI * 2, dx = Math.cos(a), dz = Math.sin(a);
    let rr = r;
    for (let t = r0s[i] + 6; t < rr; t += 5) if (wet(cx + dx * t, cz + dz * t)) { rr = Math.max(r0s[i] + 4, t - 6); break; }
    out.push(cx + dx * rr, cz + dz * rr);
  });
  return ensureCCW(out);
}

/** Each value of a ring averaged with its neighbours. */
function smoothRing(v: number[]): number[] {
  const n = v.length;
  return v.map((x, i) => (v[(i + n - 1) % n] + 2 * x + v[(i + 1) % n]) / 4);
}

/** How far a ray from (cx, cz) runs before it leaves the polygon (its farthest crossing). */
function rayOut(p: Poly, cx: number, cz: number, dx: number, dz: number): number {
  const n = p.length >> 1;
  let best = 0;
  for (let i = 0; i < n; i++) {
    const ax = p[i * 2] - cx, az = p[i * 2 + 1] - cz, bx = p[((i + 1) % n) * 2] - cx, bz = p[((i + 1) % n) * 2 + 1] - cz;
    const ex = bx - ax, ez = bz - az, den = dx * ez - dz * ex;
    if (Math.abs(den) < 1e-9) continue;
    const t = (ax * ez - az * ex) / den, s = (ax * dz - az * dx) / den;
    if (t > 0 && s >= 0 && s <= 1) best = Math.max(best, t);
  }
  return best;
}

/** How far out a point lies: 0 at the outline, 1 at the edge (along its ray from the middle). */
function distOut(outline: Poly, edge: Poly, cx: number, cz: number, x: number, z: number): number {
  const d = Math.hypot(x - cx, z - cz) || 1, dx = (x - cx) / d, dz = (z - cz) / d;
  const r0 = rayOut(outline, cx, cz, dx, dz), r1 = rayOut(edge, cx, cz, dx, dz);
  return Math.max(0, Math.min(1, (d - r0) / Math.max(1, r1 - r0)));
}

/** The index (into the flat array) of the first road point outside the town, -1 if none. */
function leaveIndex(road: number[], inTown: (x: number, z: number) => boolean): number {
  for (let k = 0; k + 1 < road.length; k += 2) if (!inTown(road[k], road[k + 1])) return k;
  return -1;
}

// ---------------------------------------------------------------- farmsteads

interface FarmSite { road: number; k: number; s: number; side: number; score: number }

/** A farmstead laid out beside a road: everything as rectangles in the farm's frame, ready to check. */
interface FarmLay {
  /** The farm's frame: origin on the road's edge, u along the road, v away from it. */
  ox: number; oz: number; ux: number; uz: number; vx: number; vz: number;
  /** Where on the road it joins (x, z). */
  rx: number; rz: number;
  house: Box; barn: Box; stable: Box;
  yard: Box;
  paddock: Box;
  footprint: Poly;
}

/** A rectangle in the farm's frame: middle (u, v), half sizes, and its door side (unit, in u/v). */
interface Box { u: number; v: number; hu: number; hv: number; du: number; dv: number }

function layFarm(st: FarmSite, road: number[], input: FarmlandInput, r: Rng): FarmLay | null {
  const k = st.k;
  const tx = road[k + 2] - road[k], tz = road[k + 3] - road[k + 1], tl = Math.hypot(tx, tz);
  if (tl < 1e-6) return null;
  const ux = (tx / tl) * st.side, uz = (tz / tl) * st.side;
  // v: away from the road (to the road's left for side 1, right for -1, with u turned to match).
  const vx = -uz, vz = ux;
  const off = input.roadWidth / 2 + r.range(4, 9);
  const ox = road[k] + vx * off, oz = road[k + 1] + vz * off;
  const flip = r.chance(0.5) ? 1 : -1;
  const hhu = r.range(4.6, 6), hhv = r.range(3.4, 4.4);
  const bhu = r.range(6.5, 8.5), bhv = r.range(4.2, 5.4);
  const shu = r.range(3.6, 4.6), shv = r.range(2.8, 3.4);
  // The yard is wide enough that the track up its middle passes the house.
  const yw = 2 * hhu + r.range(3, 5), yd = r.range(15, 19);
  // The house at the front facing the road, the barn across the back facing the yard, the stable at the side.
  const house: Box = { u: -flip * (yw - hhu), v: hhv + 1, hu: hhu, hv: hhv, du: 0, dv: -1 };
  const barn: Box = { u: flip * r.range(-1.5, 1.5), v: yd + bhv, hu: bhu, hv: bhv, du: 0, dv: -1 };
  // The stable's door faces into the yard (towards -flip in u): its depth runs along u.
  const stable: Box = { u: flip * (yw - shv), v: shu + 3, hu: shv, hv: shu, du: -flip, dv: 0 };
  const yard: Box = { u: 0, v: yd / 2 + 0.5, hu: yw, hv: yd / 2 + 0.5, du: 0, dv: -1 };
  const pw = r.range(13, 19), pd = r.range(12, 17);
  const paddock: Box = { u: flip * (yw + 2 + pw), v: pd + 1, hu: pw, hv: pd, du: -flip, dv: 0 };
  const lay: FarmLay = { ox, oz, ux, uz, vx, vz, rx: road[k], rz: road[k + 1], house, barn, stable, yard, paddock, footprint: [] };
  const u0 = Math.min(-yw - 1, paddock.u - pw) - 1, u1 = Math.max(yw + 1, paddock.u + pw) + 1;
  const v1 = Math.max(barn.v + bhv, paddock.v + pd) + 7; // room behind the barn for the stacks
  lay.footprint = ensureCCW(boxPoly(lay, { u: (u0 + u1) / 2, v: v1 / 2, hu: (u1 - u0) / 2, hv: v1 / 2, du: 0, dv: -1 }));
  return lay;
}

/** A box's corners in world x, z. */
function boxPoly(l: FarmLay, b: Box): Poly {
  const p = (u: number, v: number) => [l.ox + l.ux * u + l.vx * v, l.oz + l.uz * u + l.vz * v];
  return [...p(b.u - b.hu, b.v - b.hv), ...p(b.u + b.hu, b.v - b.hv), ...p(b.u + b.hu, b.v + b.hv), ...p(b.u - b.hu, b.v + b.hv)];
}

const at = (l: FarmLay, u: number, v: number): [number, number] => [l.ox + l.ux * u + l.vx * v, l.oz + l.uz * u + l.vz * v];

/** Dry, gentle, outside the town and inside the farmland, clear of other farms and other roads. */
function farmFits(l: FarmLay, input: FarmlandInput, inTown: (x: number, z: number) => boolean, inEdge: (x: number, z: number) => boolean, others: Poly[], roads: number[][]): boolean {
  const f = l.footprint;
  const [x0, z0, x1, z1] = polyBounds(f);
  let lo = Infinity, hi = -Infinity;
  for (let i = 0; i <= 6; i++) for (let j = 0; j <= 6; j++) {
    const x = x0 + ((x1 - x0) * i) / 6, z = z0 + ((z1 - z0) * j) / 6;
    if (!pointInPoly(f, x, z)) continue;
    if (input.wet(x, z) || inTown(x, z) || !inEdge(x, z)) return false;
    const h = input.site.height(x, z);
    lo = Math.min(lo, h); hi = Math.max(hi, h);
  }
  if (hi - lo > Math.max(3, 0.12 * Math.hypot(x1 - x0, z1 - z0))) return false;
  for (const p of others) if (intersection([f], [p]).length) return false;
  // No road through the farm (its own road runs along the front).
  for (const r of roads) for (let k = 0; k + 1 < r.length; k += 2) if (pointInPoly(f, r[k], r[k + 1])) return false;
  return true;
}

function addFarm(l: FarmLay, input: FarmlandInput, farms: Farm[], paddocks: Paddock[], props: TownProp[], fields: Field[], r: Rng): void {
  const id = farms.length, site = input.site, buildings = input.buildings;
  const make = (b: Box, k: number) => {
    // makeBuilding's u runs along the front, v away from the door.
    const dvx = l.ux * b.du + l.vx * b.dv, dvz = l.uz * b.du + l.vz * b.dv; // door side
    const bvx = -dvx, bvz = -dvz, bux = -bvz, buz = bvx;
    const across = b.du !== 0;
    const [x, z] = at(l, b.u, b.v);
    const bb = makeBuilding(buildings.length, 'cottage', x, z, bux, buz, bvx, bvz, across ? b.hv : b.hu, across ? b.hu : b.hv, false, false, true, -1, site, r);
    bb.seed = deriveSeed(site.seed, 'farm', id, k);
    buildings.push(bb);
    return bb;
  };
  const house = make(l.house, 0);
  house.kind = 'farmhouse';
  house.trade = 'farmer';
  house.household = r.int(3, 6);
  house.floors = r.chance(0.3) ? 2 : 1;
  const barn = make(l.barn, 1);
  barn.kind = 'barn';
  barn.household = 0;
  barn.floors = 1;
  barn.floorH = r.range(4.2, 5);
  barn.ridgeAlongU = true;
  barn.roof = 'gable';
  barn.wall = r.chance(0.6) ? 'timber' : 'stone';
  barn.cover = r.chance(0.7) ? 'thatch' : 'shingle';
  barn.pitch = barn.cover === 'thatch' ? r.range(1.05, 1.25) : r.range(0.8, 1);
  const stable = make(l.stable, 2);
  stable.kind = 'stable';
  stable.household = 0;
  stable.floors = 1;
  stable.floorH = r.range(2.7, 3.1);
  stable.wall = r.chance(0.5) ? 'timber' : 'plaster';
  stable.ridgeAlongU = true;
  // The paddock, its fence (posts every 2.5 m round it, a gate gap on the yard side) and its pasture.
  const pPoly = ensureCCW(boxPoly(l, l.paddock));
  const gv = Math.min(l.paddock.v - l.paddock.hv + 4, l.stable.v);
  const gateU = l.paddock.u + l.paddock.du * l.paddock.hu; // its side towards the yard
  const [gx, gz] = at(l, gateU, gv);
  const into = Math.atan2(-(l.uz * l.paddock.du), -(l.ux * l.paddock.du));
  const pid = paddocks.length;
  paddocks.push({ id: pid, poly: pPoly, farm: id, animals: r.int(2, 4), gate: [gx, gz, into] });
  props.push({ kind: 'fence', posts: fencePosts(pPoly, gx, gz, 1.6, site.height), seed: deriveSeed(site.seed, 'fence', id) });
  fields.push({ id: fields.length, poly: pPoly, crop: 'pasture', rows: Math.atan2(l.uz, l.ux), farm: id, paddock: pid });
  // The yard's things: a trough by the gate, the paddock's gate, hay for the stable, a well, wood, hens, a garden.
  const step = (u: number, v: number): [number, number] => at(l, u, v);
  const hb = house.id;
  const gIn = step(gateU - l.paddock.du * 1.2, gv + 3);
  input.fix('paddock', ...step(gateU - l.paddock.du * 1.6, gv), into, hb);
  input.fix('trough', gIn[0], gIn[1], into + Math.PI / 2, hb);
  input.fix('hayrack', ...step(l.stable.u + l.stable.du * (l.stable.hu + 1), l.stable.v + l.stable.hv * 0.6), Math.atan2(-l.uz * l.stable.du, -l.ux * l.stable.du), hb);
  input.fix('well', ...step(r.range(-3, 3), l.yard.v + r.range(-2, 2)), r.range(-Math.PI, Math.PI), hb);
  input.fix('woodpile', ...step(l.house.u, l.house.v + l.house.hv + 1.2), Math.atan2(-l.vz, -l.vx), hb);
  input.fix('chopblock', ...step(l.house.u + 2.5, l.house.v + l.house.hv + 2.4), Math.atan2(-l.vz, -l.vx), hb);
  input.fix('chickens', ...step(l.house.u * 0.4, l.yard.v + 3), r.range(-Math.PI, Math.PI), hb);
  const sideU = l.house.u + Math.sign(l.house.u || 1) * (l.house.hu + 4);
  input.fix('garden', ...step(sideU, l.house.v), Math.atan2(l.uz, l.ux), hb);
  if (r.chance(0.6)) input.fix('washline', ...step(sideU, l.house.v + 4), Math.atan2(l.uz, l.ux), hb);
  // Haystacks behind the barn.
  for (let k = r.int(1, 3); k > 0; k--) {
    const [x, z] = step(l.barn.u + r.range(-l.barn.hu, l.barn.hu), l.barn.v + l.barn.hv + r.range(2.5, 4.5));
    props.push(haystack(x, z, site, r));
  }
  // A track from the road into the yard.
  const [ex, ez] = step(0, l.yard.v);
  input.streets.push({ kind: 'path', pts: [l.rx, l.rz, ...step(0, -1), ex, ez], width: PATH_W });
  farms.push({ id, house: house.id, barn: barn.id, stable: stable.id, yard: ensureCCW(boxPoly(l, l.yard)), paddock: pid, fields: [] });
}

/** Fence posts round a closed polygon, about `gap` m apart, leaving a gate of `gate` m at (gx, gz). */
function fencePosts(poly: Poly, gx: number, gz: number, gate: number, height: (x: number, z: number) => number): number[] {
  const n = poly.length >> 1;
  const pts: number[] = [];
  for (let i = 0; i < n; i++) {
    const ax = poly[i * 2], az = poly[i * 2 + 1], bx = poly[((i + 1) % n) * 2], bz = poly[((i + 1) % n) * 2 + 1];
    const L = Math.hypot(bx - ax, bz - az), m = Math.max(1, Math.round(L / 2.5));
    for (let k = 0; k < m; k++) pts.push(ax + ((bx - ax) * k) / m, az + ((bz - az) * k) / m);
  }
  pts.push(pts[0], pts[1]);
  // Open the ring at the post nearest the gate: the posts run from one side of the gate round to the other.
  const c = closestOnPolyline(pts, gx, gz);
  const m = pts.length >> 1;
  const out: number[] = [];
  const start = c.seg + 1;
  for (let k = 0; k < m - 1; k++) {
    const i = (start + k) % (m - 1);
    const x = pts[i * 2], z = pts[i * 2 + 1];
    if (Math.hypot(x - gx, z - gz) < gate) continue;
    out.push(x, height(x, z), z);
  }
  return out;
}

function haystack(x: number, z: number, site: TownSite, r: Rng): TownProp {
  return { kind: 'haystack', x, y: site.height(x, z), z, r: r.range(1.5, 2.1), h: r.range(2.4, 3.2), seed: Math.floor(r.float() * 2 ** 31) };
}

// ---------------------------------------------------------------- helpers

/** Polylines stroked in short pieces (each its own polygon, so `near` can pass over most of them). */
function pieceStrokes(lines: number[][], half: number): Poly[] {
  const out: Poly[] = [];
  for (const l of lines) for (let k = 0; k + 3 < l.length; k += 16) out.push(...shapesToPolys(strokePolylines([l.slice(k, k + 18)], half, 'round', 'round')));
  return out;
}

/** The polygons whose bounds overlap `b` (clipping against all of them is slow). */
function near(polys: Poly[], bounds: [number, number, number, number][], b: [number, number, number, number]): Poly[] {
  return polys.filter((_, i) => bounds[i][0] <= b[2] && bounds[i][2] >= b[0] && bounds[i][1] <= b[3] && bounds[i][3] >= b[1]);
}

/** Water within `reach` m of the polygon's middle. */
function waterNear(p: Poly, wet: (x: number, z: number) => boolean, reach: number): boolean {
  const [x, z] = polyCentroid(p);
  for (let a = 0; a < 6; a++) if (wet(x + Math.cos(a * Math.PI / 3) * reach, z + Math.sin(a * Math.PI / 3) * reach)) return true;
  return false;
}

function polyWet(p: Poly, wet: (x: number, z: number) => boolean): boolean {
  for (let i = 0; i < p.length; i += 2) if (wet(p[i], p[i + 1])) return true;
  const [x, z] = polyCentroid(p);
  return wet(x, z);
}

/** Too steep to plough (it is left as meadow): the ground rises more than 1 in 5 across the strip. */
function steep(p: Poly, height: (x: number, z: number) => number): boolean {
  const [cx, cz] = polyCentroid(p), hc = height(cx, cz);
  for (let i = 0; i < p.length; i += 2) {
    const d = Math.hypot(p[i] - cx, p[i + 1] - cz);
    if (d > 1 && Math.abs(height(p[i], p[i + 1]) - hc) / d > 0.2) return true;
  }
  return false;
}

/** A seeded point inside the polygon, at least `margin` m from its edge (null if none found). */
function insidePoint(p: Poly, r: Rng, margin: number): [number, number] | null {
  const [x0, z0, x1, z1] = polyBounds(p);
  for (let k = 0; k < 24; k++) {
    const x = r.range(x0, x1), z = r.range(z0, z1);
    if (!pointInPoly(p, x, z)) continue;
    let ok = true;
    const n = p.length >> 1;
    for (let i = 0; i < n && ok; i++) {
      const ax = p[i * 2], az = p[i * 2 + 1], bx = p[((i + 1) % n) * 2], bz = p[((i + 1) % n) * 2 + 1];
      const dx = bx - ax, dz = bz - az, L2 = dx * dx + dz * dz || 1;
      const t = Math.max(0, Math.min(1, ((x - ax) * dx + (z - az) * dz) / L2));
      if (Math.hypot(ax + dx * t - x, az + dz * t - z) < margin) ok = false;
    }
    if (ok) return [x, z];
  }
  return null;
}
