/**
 * A town's fixtures out of doors as meshes, in the building format (BuildingMesh, drawn with the buildings'
 * shader): the market's stalls and well, benches, tables and barrels, the smith's forge, anvil and quench tub,
 * the baker's oven, workbenches, troughs, woodpiles and chopping blocks, gardens, washing lines, hen coops,
 * graves and the offering stone. Each stands where the plan put it (its x, z), turned to its yaw (where its
 * user looks), on the ground `height` gives. `detail` false gives the far version (fewer sides, no small
 * things on top). `fixtureBlocks` says what a walker runs into. Pure.
 */
import { Rng, seat } from '@futuremagic/core';
import { BuildingMat, Frame, Out, type BuildingMesh, type RGB } from './building';
import type { Poly } from './geom2';
import type { Fixture, FixtureKind } from './town';

/** A bench's seat, metres above the ground (a sitter's hips go there). */
export const BENCH_SEAT = 0.45;

const TIMBER: RGB = [128, 100, 78];
const DARK: RGB = [84, 62, 48];
const LIGHT_WOOD: RGB = [196, 166, 126];
const STONE: RGB = [206, 198, 184];
const RUBBLE: RGB = [170, 160, 146];
const SOOT: RGB = [92, 84, 78];
const IRON: RGB = [70, 72, 78];
const WATER: RGB = [52, 74, 84];
const EARTH: RGB = [110, 86, 62];
const LEAVES: RGB = [96, 138, 72];
const LINEN: RGB = [236, 230, 214];
/** Awnings and washing: dyed cloth. */
const CLOTHS: RGB[] = [[196, 72, 58], [64, 104, 156], [214, 172, 72], [92, 140, 92], [176, 112, 64], [146, 82, 132], [230, 222, 204]];
/** Wares on a stall's counter: apples, cabbages, cheese, loaves, cloth, pots. */
/** The catch on a fish stall: silver, blue-grey, a pink one. */
const FISH: RGB[] = [[190, 196, 202], [128, 146, 160], [170, 180, 168], [206, 150, 140]];
const WARES: RGB[] = [[196, 60, 44], [120, 168, 84], [236, 206, 120], [190, 136, 76], [126, 120, 170], [178, 104, 72]];

/** How far round its middle a fixture stops a walker (m, a box: along its yaw, across it). None: walked through or over. */
/** How deep below the lowest ground under its foot a fixture is set (m): little, so a bench's seat stays where a sitter's hips go. */
const SINK = 0.02;
/**
 * Set at its middle's height, not seated: what lies on the ground as the ground lies (dug beds, a field's work
 * spot), and a bench, whose seat must stay BENCH_SEAT over its middle (where a sitter's hips go): its legs run
 * down into the ground instead (LEG_DOWN), so on a slope none of them floats.
 */
const LIES: ReadonlySet<FixtureKind> = new Set(['garden', 'field', 'paddock', 'bench']);
/** How far a bench's legs reach below its middle's ground (m): enough for a slope of one in two. */
const LEG_DOWN = 0.45;

const SOLID: Partial<Record<FixtureKind, readonly [number, number]>> = {
  well: [0.85, 0.85], stall: [0.5, 1.25], table: [0.42, 0.82], barrel: [0.32, 0.32], forge: [0.6, 0.65], anvil: [0.3, 0.2],
  quench: [0.28, 0.48], oven: [0.65, 0.65], workbench: [0.32, 0.92], trough: [0.28, 0.92], woodpile: [0.35, 0.85],
  chickens: [0.45, 0.55], offering: [0.35, 0.35], hayrack: [0.4, 0.9], washline: [0.08, 0.08],
  crane: [0.9, 0.9], cargo: [1.1, 1.45], nets: [0.12, 1.7], fishstall: [0.5, 1.25],
};

/** Does a body of radius `r` at (x, z) run into this fixture? */
export function fixtureBlocks(f: Fixture, x: number, z: number, r: number): boolean {
  const s = SOLID[f.kind];
  if (!s) return false;
  const dx = x - f.x, dz = z - f.z;
  if (Math.abs(dx) > 2 + r || Math.abs(dz) > 2 + r) return false;
  const c = Math.cos(f.yaw), n = Math.sin(f.yaw);
  if (f.kind === 'washline') return [-1.5, 1.5].some((b) => Math.hypot(dx + n * b, dz - c * b) < 0.08 + r);
  return Math.abs(dx * c + dz * n) < s[0] + r && Math.abs(-dx * n + dz * c) < s[1] + r;
}

/**
 * What of a fixture stands in the way of the eye, as boxes in its frame (a0, a1 along the way its user looks, y0, y1
 * up from its ground, b0, b1 across): a stall's counter and its awning, a well's wall and roof, a forge's hood, a hen
 * coop, a woodpile under its lean-to, an oven, a hayrack. A camera keeps out of them and sees past them (a talk's
 * view from over a stall ended up on its awning: the walker's boxes stop at the counter). Fixtures the eye sees over
 * have none.
 */
const SIGHT: Partial<Record<FixtureKind, readonly (readonly [number, number, number, number, number, number])[]>> = {
  stall: [[-0.4, 0.4, 0, 0.92, -1.2, 1.2], [-1.7, 0.75, 1.85, 2.35, -1.4, 1.4]],
  fishstall: [[-0.4, 0.4, 0, 0.92, -1.2, 1.2], [-1.5, 0.6, 1.75, 2.2, -1.3, 1.3]],
  crane: [[-0.9, 0.9, 0, 1.0, -0.9, 0.9], [0.3, 0.9, 0, 6.6, -0.3, 0.3]],
  cargo: [[-1.1, 1.1, 0, 1.7, -1.45, 1.45]],
  nets: [[-0.12, 0.12, 0, 2.3, -1.7, 1.7]],
  well: [[-0.78, 0.78, 0, 0.75, -0.78, 0.78], [-0.65, 0.65, 2.1, 2.6, -0.95, 0.95]],
  forge: [[-0.55, 0.55, 0, 0.8, -0.6, 0.6], [0.15, 0.55, 0.8, 2.7, -0.45, 0.45]],
  chickens: [[-0.5, 0.5, 0, 1.25, -0.6, 0.6]],
  woodpile: [[-0.4, 0.45, 0, 1.25, -0.9, 0.9]],
  oven: [[-0.6, 0.6, 0, 1.15, -0.6, 0.6]],
  hayrack: [[-0.35, 0.35, 0, 1.45, -0.85, 0.85]],
};

/**
 * How far (x, y, z) is from what of fixture `f` blocks the eye (SIGHT), its ground at `ground` (the height the mesh
 * stands on at its middle); below 0 inside. Infinity for a fixture the eye sees over.
 */
export function fixtureSight(f: Fixture, ground: number, x: number, y: number, z: number): number {
  const boxes = SIGHT[f.kind];
  if (!boxes) return Infinity;
  const c = Math.cos(f.yaw), n = Math.sin(f.yaw), dx = x - f.x, dz = z - f.z;
  const a = dx * c + dz * n, b = -dx * n + dz * c, h = y - ground;
  let d = Infinity;
  for (const [a0, a1, y0, y1, b0, b1] of boxes) {
    const qa = Math.max(a0 - a, a - a1), qy = Math.max(y0 - h, h - y1), qb = Math.max(b0 - b, b - b1);
    const out = Math.hypot(Math.max(qa, 0), Math.max(qy, 0), Math.max(qb, 0)), inside = Math.min(Math.max(qa, qy, qb), 0);
    d = Math.min(d, out + inside);
  }
  return d;
}

/** Where a fixture's user stands (x, z) and the way they face: a step before it, facing it (a stall's buyer in front, facing the seller); on a bench, on it. */
export function fixtureStand(f: Fixture): [number, number, number] {
  const stall = f.kind === 'stall' || f.kind === 'fishstall';
  const dir = stall ? f.yaw + Math.PI : f.yaw;
  const back = stall ? 1.4 : f.kind === 'bench' ? 0 : f.kind === 'crane' ? 1.2 : f.kind === 'cargo' ? 1.6 : 0.9;
  return [f.x - Math.cos(dir) * back, f.z - Math.sin(dir) * back, dir];
}

/** A body's room round where a fixture's user stands (m), and how far to each side a second or third user stands (side by side). */
const STAND_R = 0.45;
const SIDE = 0.75;
const SIDE_R = 0.35;
/** A fixture's own clearance off a wall (m). */
const WALL_GAP = 0.15;

/**
 * Whether a fixture and the people using it stay out of every footprint in `polys` (the town's buildings): its
 * solid box with a little gap, where its user stands with room for a body, and the places beside that for a
 * second and third user. `inside(poly, x, z)` and `dist(poly, x, z)`: the geometry (the town planner's).
 */
export function fixtureClear(f: Fixture, polys: readonly Poly[], inside: (p: Poly, x: number, z: number) => boolean, dist: (p: Poly, x: number, z: number) => number): boolean {
  const c = Math.cos(f.yaw), n = Math.sin(f.yaw), s = SOLID[f.kind];
  const pts: [number, number, number][] = [];
  if (s) for (const i of [-1, 0, 1]) for (const j of [-1, 0, 1]) pts.push([f.x + c * s[0] * i - n * s[1] * j, f.z + n * s[0] * i + c * s[1] * j, WALL_GAP]);
  else pts.push([f.x, f.z, WALL_GAP]);
  const [sx, sz, dir] = fixtureStand(f), ac = -Math.sin(dir), an = Math.cos(dir);
  pts.push([sx, sz, STAND_R]);
  for (const k of [-SIDE, -SIDE / 2, SIDE / 2, SIDE]) pts.push([sx + ac * k, sz + an * k, SIDE_R]);
  return polys.every((p) => pts.every(([x, z, r]) => !inside(p, x, z) && dist(p, x, z) >= r));
}

/**
 * The fixtures among `list` that `pick` takes (by their x, z; default all) as one mesh, positions relative to
 * `origin`, each set on the ground `height` gives: lowered to the lowest ground under its foot (core `seat`), so
 * on a slope no edge floats.
 */
export function fixtureMesh(list: readonly Fixture[], height: (x: number, z: number) => number, origin: [number, number, number], detail = true, pick: (x: number, z: number) => boolean = () => true): BuildingMesh {
  const all = { pos: [] as number[], nrm: [] as number[], uv: [] as number[], mat: [] as number[], tint: [] as number[], idx: [] as number[] };
  for (const f of list) {
    if (!pick(f.x, f.z)) continue;
    const c = Math.cos(f.yaw), s = Math.sin(f.yaw);
    // a along the way its user looks, b across (to the left of it), y up from the ground.
    const o = new Out(new Frame({ cx: f.x, cz: f.z, ux: c, uz: s, vx: -s, vz: c, y: height(f.x, f.z) }, origin));
    draw(o, f, new Rng(f.id * 7919 + 17), detail);
    if (!LIES.has(f.kind)) seat((x, z) => height(x + origin[0], z + origin[2]) - origin[1], o.pos, 0, o.pos.length, SINK);
    const base = all.pos.length / 3;
    all.pos.push(...o.pos); all.nrm.push(...o.nrm); all.uv.push(...o.uv); all.mat.push(...o.mat); all.tint.push(...o.tint);
    for (const i of o.idx) all.idx.push(i + base);
  }
  return {
    position: Float32Array.from(all.pos), normal: Float32Array.from(all.nrm), uv: Float32Array.from(all.uv),
    mat: Uint8Array.from(all.mat), tint: Uint8Array.from(all.tint), index: Uint32Array.from(all.idx),
  };
}

function draw(o: Out, f: Fixture, r: Rng, detail: boolean): void {
  const sides = detail ? 10 : 6;
  switch (f.kind) {
    case 'bench':
      // The sitters sit on it facing its yaw, side by side across it.
      slab(o, -0.17, 0.17, BENCH_SEAT - 0.06, BENCH_SEAT, -0.9, 0.9, TIMBER);
      for (const b of [-0.75, 0.75]) o.box(-0.13, 0.13, -LEG_DOWN, BENCH_SEAT - 0.06, b - 0.04, b + 0.04, BuildingMat.Oak, DARK);
      break;
    case 'table':
      slab(o, -0.4, 0.4, 0.72, 0.78, -0.8, 0.8, TIMBER);
      legs(o, -0.4, 0.4, -0.8, 0.8, 0.72, 0.05, DARK);
      if (detail) { o.box(-0.1, 0, 0.78, 0.92, 0.2, 0.3, BuildingMat.Oak, LIGHT_WOOD); o.box(0.05, 0.15, 0.78, 0.9, -0.35, -0.25, BuildingMat.Slate, IRON); }
      break;
    case 'barrel':
      prism(o, 0, 0, 0.3, 0, 0.9, sides, BuildingMat.Oak, TIMBER);
      if (detail) for (const y of [0.15, 0.72]) prism(o, 0, 0, 0.315, y, y + 0.05, sides, BuildingMat.Slate, IRON, false);
      break;
    case 'stall': {
      // The seller stands behind (−a), the buyers in front (+a): a counter, four posts, a sloping awning.
      const cloth = r.pick(CLOTHS);
      o.box(-0.4, 0.4, 0, 0.92, -1.2, 1.2, BuildingMat.Oak, TIMBER);
      for (const [a, b, h] of [[-1.55, -1.3, 2.25], [-1.55, 1.3, 2.25], [0.45, -1.3, 1.95], [0.45, 1.3, 1.95]] as const) o.box(a - 0.05, a + 0.05, 0, h, b - 0.05, b + 0.05, BuildingMat.Oak, DARK);
      const p = [[-1.7, 2.3, -1.4], [0.75, 1.9, -1.4], [0.75, 1.9, 1.4], [-1.7, 2.3, 1.4]];
      const n = [0.16, 0.99, 0];
      o.quad(p, n, p.map((q) => [q[0], q[2]]), BuildingMat.Plaster, cloth);
      o.quad(p, [-n[0], -n[1], 0], p.map((q) => [q[0], q[2]]), BuildingMat.Plaster, cloth.map((v) => Math.round(v * 0.75)) as RGB);
      if (detail) {
        // A valance hanging at the front, and wares on the counter.
        o.quad([[0.75, 1.9, -1.4], [0.75, 1.9, 1.4], [0.75, 1.62, 1.4], [0.75, 1.62, -1.4]], [1, 0, 0], [[-1.4, 1.9], [1.4, 1.9], [1.4, 1.62], [-1.4, 1.62]], BuildingMat.Plaster, cloth);
        for (let i = 0; i < 4; i++) {
          const b = -0.9 + i * 0.6 + r.range(-0.1, 0.1), w = r.range(0.14, 0.24);
          o.box(-0.25, 0.25, 0.92, 0.92 + r.range(0.1, 0.22), b - w, b + w, BuildingMat.Plaster, r.pick(WARES));
        }
      }
      break;
    }
    case 'well':
      // A round stone wall, dark water inside, two posts with a beam and a little roof over it.
      prism(o, 0, 0, 0.78, 0, 0.75, detail ? 14 : 8, BuildingMat.Ashlar, STONE);
      o.quad([[-0.6, 0.76, -0.6], [0.6, 0.76, -0.6], [0.6, 0.76, 0.6], [-0.6, 0.76, 0.6]], [0, 1, 0], [[0, 0], [1, 0], [1, 1], [0, 1]], BuildingMat.Slate, WATER);
      for (const b of [-0.72, 0.72]) o.box(-0.07, 0.07, 0.7, 2.2, b - 0.07, b + 0.07, BuildingMat.Oak, DARK);
      o.box(-0.05, 0.05, 1.6, 1.7, -0.78, 0.78, BuildingMat.Oak, TIMBER);
      gable(o, -0.65, 0.65, 2.15, 2.6, -0.95, 0.95, BuildingMat.Shingle, TIMBER);
      if (detail) o.box(-0.12, 0.12, 1.15, 1.4, -0.12, 0.12, BuildingMat.Oak, TIMBER); // the bucket
      break;
    case 'forge':
      // A stone hearth with coals, its hood and a short flue.
      o.box(-0.55, 0.55, 0, 0.8, -0.6, 0.6, BuildingMat.Rubble, RUBBLE);
      o.quad([[-0.4, 0.81, -0.45], [0.4, 0.81, -0.45], [0.4, 0.81, 0.45], [-0.4, 0.81, 0.45]], [0, 1, 0], [[0, 0], [1, 0], [1, 1], [0, 1]], BuildingMat.Slate, [150, 64, 34]);
      o.box(0.15, 0.55, 0.8, 1.9, -0.45, 0.45, BuildingMat.Rubble, SOOT);
      o.box(0.2, 0.5, 1.9, 2.7, -0.2, 0.2, BuildingMat.Rubble, SOOT);
      break;
    case 'anvil':
      o.box(-0.2, 0.2, 0, 0.5, -0.2, 0.2, BuildingMat.Oak, DARK);
      o.box(-0.14, 0.14, 0.5, 0.78, -0.32, 0.32, BuildingMat.Slate, IRON);
      if (detail) o.box(-0.06, 0.06, 0.6, 0.75, 0.32, 0.46, BuildingMat.Slate, IRON); // the horn
      break;
    case 'quench':
      o.box(-0.25, 0.25, 0, 0.55, -0.45, 0.45, BuildingMat.Oak, DARK);
      o.quad([[-0.2, 0.5, -0.4], [0.2, 0.5, -0.4], [0.2, 0.5, 0.4], [-0.2, 0.5, 0.4]], [0, 1, 0], [[0, 0], [1, 0], [1, 1], [0, 1]], BuildingMat.Slate, WATER);
      break;
    case 'oven': {
      // A domed bread oven of clay and stone on a plinth; its dark mouth faces the baker (−a).
      o.box(-0.6, 0.6, 0, 0.6, -0.6, 0.6, BuildingMat.Rubble, RUBBLE);
      dome(o, 0, 0, 0.55, 0.6, 0.6, sides, BuildingMat.Rubble, [196, 160, 128]);
      o.quad([[-0.56, 0.62, -0.2], [-0.56, 0.62, 0.2], [-0.5, 0.92, 0.2], [-0.5, 0.92, -0.2]], [-1, 0, 0], [[0, 0], [1, 0], [1, 1], [0, 1]], BuildingMat.Slate, [34, 26, 22]);
      break;
    }
    case 'workbench':
      slab(o, -0.3, 0.3, 0.8, 0.88, -0.9, 0.9, LIGHT_WOOD);
      legs(o, -0.3, 0.3, -0.9, 0.9, 0.8, 0.05, DARK);
      if (detail) { o.box(-0.15, 0.15, 0.88, 0.98, 0.3, 0.7, BuildingMat.Oak, TIMBER); o.box(-0.05, 0.05, 0.88, 0.93, -0.6, -0.2, BuildingMat.Slate, IRON); }
      break;
    case 'trough':
      o.box(-0.25, 0.25, 0, 0.5, -0.9, 0.9, BuildingMat.Oak, DARK);
      o.quad([[-0.2, 0.45, -0.85], [0.2, 0.45, -0.85], [0.2, 0.45, 0.85], [-0.2, 0.45, 0.85]], [0, 1, 0], [[0, 0], [1, 0], [1, 1], [0, 1]], BuildingMat.Slate, WATER);
      break;
    case 'woodpile':
      // Split logs stacked under a lean-to of shingles.
      o.box(-0.3, 0.3, 0, 0.9, -0.8, 0.8, BuildingMat.Oak, LIGHT_WOOD);
      if (detail) for (let i = 0; i < 3; i++) o.box(0.3, 0.32, 0.1 + i * 0.28, 0.32 + i * 0.28, -0.75, 0.75, BuildingMat.Oak, [176, 146, 108]);
      lean(o, -0.4, 0.45, 1.25, 1.0, -0.9, 0.9, BuildingMat.Shingle, TIMBER);
      break;
    case 'chopblock':
      prism(o, 0, 0, 0.28, 0, 0.45, sides, BuildingMat.Oak, TIMBER);
      if (detail) { o.box(-0.03, 0.03, 0.45, 0.62, -0.02, 0.02, BuildingMat.Oak, LIGHT_WOOD); o.box(-0.06, 0.06, 0.6, 0.66, -0.02, 0.1, BuildingMat.Slate, IRON); }
      break;
    case 'garden':
      // Two beds of dug earth with rows of greens.
      for (const b of [-0.6, 0.6]) {
        o.box(-1, 1, 0, 0.14, b - 0.42, b + 0.42, BuildingMat.Rubble, EARTH);
        if (detail) for (let i = 0; i < 5; i++) { const a = -0.8 + i * 0.4; o.box(a - 0.12, a + 0.12, 0.14, 0.3 + r.range(0, 0.1), b - 0.12, b + 0.12, BuildingMat.Thatch, LEAVES); }
      }
      break;
    case 'washline': {
      // Two posts across the way one faces, a line between, washing on it.
      for (const b of [-1.5, 1.5]) o.box(-0.05, 0.05, 0, 1.85, b - 0.05, b + 0.05, BuildingMat.Oak, DARK);
      o.box(-0.01, 0.01, 1.76, 1.78, -1.5, 1.5, BuildingMat.Oak, LINEN);
      for (let i = 0; i < (detail ? 4 : 2); i++) {
        const b = -1.1 + i * 0.7 + r.range(-0.1, 0.1), w = r.range(0.2, 0.32), h = r.range(0.45, 0.8), c = r.pick(CLOTHS);
        const p = [[0, 1.76, b - w], [0, 1.76, b + w], [0, 1.76 - h, b + w], [0, 1.76 - h, b - w]];
        o.quad(p, [1, 0, 0], p.map((q) => [q[2], q[1]]), BuildingMat.Plaster, c);
        o.quad(p, [-1, 0, 0], p.map((q) => [q[2], q[1]]), BuildingMat.Plaster, c);
      }
      break;
    }
    case 'chickens':
      // The hens' coop: a little shed on stilts with a ramp.
      for (const [a, b] of [[-0.35, -0.45], [0.35, -0.45], [-0.35, 0.45], [0.35, 0.45]]) o.box(a - 0.04, a + 0.04, 0, 0.35, b - 0.04, b + 0.04, BuildingMat.Oak, DARK);
      o.box(-0.4, 0.4, 0.35, 0.95, -0.5, 0.5, BuildingMat.Oak, TIMBER);
      gable(o, -0.5, 0.5, 0.95, 1.25, -0.6, 0.6, BuildingMat.Shingle, DARK);
      if (detail) o.quad([[-0.12, 0.4, 0.52], [0.12, 0.4, 0.52], [0.12, 0, 1.0], [-0.12, 0, 1.0]], [0, 0.77, 0.64], [[0, 0], [1, 0], [1, 1], [0, 1]], BuildingMat.Oak, LIGHT_WOOD);
      break;
    case 'grave':
      // A low mound and a headstone at its head (beyond it, as the mourner looks).
      o.box(-0.45, 0.95, -0.02, 0.18, -0.38, 0.38, BuildingMat.Rubble, EARTH);
      o.box(1.0, 1.13, 0, 0.75, -0.28, 0.28, BuildingMat.Ashlar, r.pick([STONE, RUBBLE, [186, 182, 172] as RGB]));
      break;
    case 'offering':
      o.box(-0.32, 0.32, 0, 0.85, -0.32, 0.32, BuildingMat.Ashlar, STONE);
      o.box(-0.38, 0.38, 0.85, 0.95, -0.38, 0.38, BuildingMat.Ashlar, STONE);
      if (detail) prism(o, 0, 0, 0.16, 0.95, 1.03, 8, BuildingMat.Slate, [150, 120, 80]);
      break;
    case 'hayrack':
      o.box(-0.35, 0.35, 0, 1.3, -0.85, 0.85, BuildingMat.Oak, DARK);
      o.box(-0.3, 0.3, 0.6, 1.45, -0.8, 0.8, BuildingMat.Thatch, [236, 214, 150]);
      break;
    case 'crane': {
      // A harbour crane of timber: a stout post on a cross of sills, a jib reaching out over the water (+a) with its
      // brace, the rope and a bundle on the hook, and the winch at its foot where the hand works it (−a).
      for (const [a0, a1, b0, b1] of [[-0.9, 0.9, -0.14, 0.14], [-0.14, 0.14, -0.9, 0.9]]) o.box(a0, a1, 0, 0.22, b0, b1, BuildingMat.Oak, DARK);
      o.box(-0.18, 0.18, 0.22, 6.5, -0.18, 0.18, BuildingMat.Oak, TIMBER);
      beam(o, [-0.6, 6.3, 0], [4.6, 6.75, 0], 0.13, DARK);
      beam(o, [0.1, 3.6, 0], [2.8, 6.55, 0], 0.09, TIMBER);
      beam(o, [0, 0.22, 0.7], [0, 2.2, 0.12], 0.07, TIMBER);
      beam(o, [0, 0.22, -0.7], [0, 2.2, -0.12], 0.07, TIMBER);
      o.box(4.42, 4.46, 2.4, 6.7, -0.02, 0.02, BuildingMat.Oak, LINEN);
      // The load on the hook, seen from afar too (a bare rope reads as a gallows).
      o.box(3.9, 5.0, 1.3, 2.4, -0.55, 0.55, BuildingMat.Oak, LIGHT_WOOD);
      if (detail) {
        prism(o, -0.55, 0, 0.32, 0.7, 1.15, sides, BuildingMat.Oak, TIMBER);
        o.box(-0.62, -0.48, 0.55, 1.3, 0.36, 0.42, BuildingMat.Oak, DARK);
        o.box(-0.62, -0.48, 0.55, 1.3, -0.42, -0.36, BuildingMat.Oak, DARK);
        o.box(-0.95, -0.85, 0.85, 1.0, 0.36, 0.6, BuildingMat.Slate, IRON);
      }
      break;
    }
    case 'cargo': {
      // Cargo waiting on the quay: crates in two rows, stacked two high, a barrel or two, sacks.
      const n = detail ? 9 : 6;
      for (let i = 0; i < n; i++) {
        const row = i % 2, a = (row ? 0.5 : -0.5) + r.range(-0.1, 0.1), b = -0.9 + (Math.floor(i / 2) % 3) * 0.9 + r.range(-0.08, 0.08), w = r.range(0.32, 0.44), h = r.range(0.5, 0.8);
        const y = i >= 6 ? 0.82 : 0;
        o.box(a - w, a + w, y, y + h, b - w, b + w, BuildingMat.Oak, r.pick([LIGHT_WOOD, TIMBER, [168, 138, 98] as RGB]));
      }
      if (detail) {
        prism(o, 0.7, 1.0, 0.28, 0, 0.82, sides, BuildingMat.Oak, TIMBER);
        o.box(-0.85, -0.45, 0, 0.32, 0.75, 1.15, BuildingMat.Thatch, [190, 170, 130]);
      }
      break;
    }
    case 'nets': {
      // Fishing nets hung to dry between two posts, floats along the top line.
      for (const b of [-1.6, 1.6]) o.box(-0.06, 0.06, 0, 2.3, b - 0.06, b + 0.06, BuildingMat.Oak, DARK);
      o.box(-0.03, 0.03, 2.08, 2.14, -1.6, 1.6, BuildingMat.Oak, DARK);
      const net: RGB = r.pick([[92, 98, 76], [118, 96, 70], [70, 86, 90]]);
      const p = [[0, 2.08, -1.5], [0, 2.08, 1.5], [0, 0.35, 1.3], [0, 0.45, -1.35]];
      o.quad(p, [1, 0, 0], p.map((q) => [q[2], q[1]]), BuildingMat.Thatch, net);
      o.quad(p, [-1, 0, 0], p.map((q) => [q[2], q[1]]), BuildingMat.Thatch, net);
      if (detail) for (let i = 0; i < 6; i++) { const b = -1.3 + i * 0.52; o.box(-0.06, 0.06, 1.96, 2.06, b - 0.06, b + 0.06, BuildingMat.Plaster, [206, 150, 70]); }
      break;
    }
    case 'fishstall': {
      // A fishmonger's counter: the catch laid out on it in a row of trays, a tub below, a plain canvas over it.
      o.box(-0.4, 0.4, 0, 0.92, -1.2, 1.2, BuildingMat.Oak, TIMBER);
      for (const [a, b, h] of [[-1.35, -1.2, 2.15], [-1.35, 1.2, 2.15], [0.45, -1.2, 1.85], [0.45, 1.2, 1.85]] as const) o.box(a - 0.05, a + 0.05, 0, h, b - 0.05, b + 0.05, BuildingMat.Oak, DARK);
      const p = [[-1.5, 2.2, -1.3], [0.6, 1.8, -1.3], [0.6, 1.8, 1.3], [-1.5, 2.2, 1.3]], n = [0.19, 0.98, 0];
      o.quad(p, n, p.map((q) => [q[0], q[2]]), BuildingMat.Plaster, LINEN);
      o.quad(p, [-n[0], -n[1], 0], p.map((q) => [q[0], q[2]]), BuildingMat.Plaster, [200, 194, 178]);
      if (detail) {
        for (let i = 0; i < 4; i++) {
          const b = -0.9 + i * 0.6;
          o.box(-0.32, 0.32, 0.92, 0.98, b - 0.26, b + 0.26, BuildingMat.Oak, DARK);
          for (let k = 0; k < 3; k++) o.box(-0.24 + k * 0.17, -0.14 + k * 0.17, 0.98, 1.04, b - 0.2, b + 0.2, BuildingMat.Slate, r.pick(FISH));
        }
        prism(o, 0.75, -0.7, 0.3, 0, 0.5, sides, BuildingMat.Oak, TIMBER);
      }
      break;
    }
    case 'field': case 'paddock':
      break;
  }
}

/** A square beam `t` half thick from p0 to p1 (a, y, b), its sides turned along it. */
function beam(o: Out, p0: number[], p1: number[], t: number, c: RGB): void {
  const d = [p1[0] - p0[0], p1[1] - p0[1], p1[2] - p0[2]], L = Math.hypot(d[0], d[1], d[2]);
  const u = d.map((v) => v / L);
  // Two directions across it: one level where it can be, the other square to both.
  let s = [-u[2], 0, u[0]];
  const sl = Math.hypot(s[0], s[2]);
  s = sl > 1e-3 ? s.map((v) => v / sl) : [1, 0, 0];
  const w = [u[1] * s[2] - u[2] * s[1], u[2] * s[0] - u[0] * s[2], u[0] * s[1] - u[1] * s[0]];
  const P = (e: number[], i: number, j: number) => [e[0] + (s[0] * i + w[0] * j) * t, e[1] + (s[1] * i + w[1] * j) * t, e[2] + (s[2] * i + w[2] * j) * t];
  const corners = [[1, 1], [-1, 1], [-1, -1], [1, -1]];
  for (let k = 0; k < 4; k++) {
    const [i0, j0] = corners[k], [i1, j1] = corners[(k + 1) % 4];
    const m = [s[0] * (i0 + i1) + w[0] * (j0 + j1), s[1] * (i0 + i1) + w[1] * (j0 + j1), s[2] * (i0 + i1) + w[2] * (j0 + j1)], ml = Math.hypot(m[0], m[1], m[2]);
    const nrm = m.map((v) => v / ml);
    o.quad([P(p0, i0, j0), P(p0, i1, j1), P(p1, i1, j1), P(p1, i0, j0)], nrm, [[0, 0], [t * 2, 0], [t * 2, L], [0, L]], BuildingMat.Oak, c);
  }
}

/** A flat top (a0..a1 along, b0..b1 across) from y0 to y1, with its underside. */
function slab(o: Out, a0: number, a1: number, y0: number, y1: number, b0: number, b1: number, c: RGB): void {
  o.box(a0, a1, y0, y1, b0, b1, BuildingMat.Oak, c, true);
}

/** Four legs under a top's corners, `t` thick. */
function legs(o: Out, a0: number, a1: number, b0: number, b1: number, top: number, t: number, c: RGB): void {
  for (const [a, b] of [[a0 + t, b0 + t], [a1 - t, b0 + t], [a0 + t, b1 - t], [a1 - t, b1 - t]]) o.box(a - t, a + t, 0, top, b - t, b + t, BuildingMat.Oak, c);
}

/** An upright prism round (a, b), `n` sides of radius `r`, from y0 to y1 (and its top). */
function prism(o: Out, a: number, b: number, r: number, y0: number, y1: number, n: number, m: BuildingMat, c: RGB, top = true): void {
  const P = (k: number, y: number) => [a + Math.cos((k / n) * Math.PI * 2) * r, y, b + Math.sin((k / n) * Math.PI * 2) * r];
  for (let k = 0; k < n; k++) {
    const t = ((k + 0.5) / n) * Math.PI * 2, s0 = (k / n) * Math.PI * 2 * r, s1 = ((k + 1) / n) * Math.PI * 2 * r;
    o.quad([P(k, y0), P(k + 1, y0), P(k + 1, y1), P(k, y1)], [Math.cos(t), 0, Math.sin(t)], [[s0, y0], [s1, y0], [s1, y1], [s0, y1]], m, c);
    if (top) o.tri([P(k, y1), P(k + 1, y1), [a, y1, b]], [0, 1, 0], [[P(k, y1)[0], P(k, y1)[2]], [P(k + 1, y1)[0], P(k + 1, y1)[2]], [a, b]], m, c);
  }
}

/** A dome of radius `r` and height `h` on y0 round (a, b). */
function dome(o: Out, a: number, b: number, r: number, y0: number, h: number, n: number, m: BuildingMat, c: RGB): void {
  const bands = 4, P = (k: number, i: number) => {
    const t = (i / bands) * (Math.PI / 2), q = (k / n) * Math.PI * 2;
    return [a + Math.cos(q) * r * Math.cos(t), y0 + h * Math.sin(t), b + Math.sin(q) * r * Math.cos(t)];
  };
  for (let k = 0; k < n; k++) for (let i = 0; i < bands; i++) {
    const q = ((k + 0.5) / n) * Math.PI * 2, t = ((i + 0.5) / bands) * (Math.PI / 2);
    const nrm = [Math.cos(q) * Math.cos(t) * h, Math.sin(t) * r, Math.sin(q) * Math.cos(t) * h];
    const p = [P(k, i), P(k + 1, i), P(k + 1, i + 1), P(k, i + 1)];
    if (i === bands - 1) o.tri([p[0], p[1], p[2]], nrm, [[0, 0], [1, 0], [0.5, 1]], m, c);
    else o.quad(p, nrm, [[0, 0], [1, 0], [1, 1], [0, 1]], m, c);
  }
}

/** A little gable roof over a0..a1 (its ridge along b at y1, eaves at y0), b0..b1. */
function gable(o: Out, a0: number, a1: number, y0: number, y1: number, b0: number, b1: number, m: BuildingMat, c: RGB): void {
  const am = (a0 + a1) / 2, rise = y1 - y0, run = am - a0;
  for (const [ae, s] of [[a0, -1], [a1, 1]] as const) {
    const p = [[ae, y0, b0], [am, y1, b0], [am, y1, b1], [ae, y0, b1]];
    o.quad(p, [s * rise, run, 0], p.map((q) => [q[2], Math.hypot(q[0] - ae, q[1] - y0)]), m, c);
    o.quad(p, [-s * rise, -run, 0], p.map((q) => [q[2], Math.hypot(q[0] - ae, q[1] - y0)]), m, c);
  }
  for (const b of [b0, b1]) o.tri([[a0, y0, b], [a1, y0, b], [am, y1, b]], [0, 0, b === b0 ? -1 : 1], [[a0, y0], [a1, y0], [am, y1]], m, c);
}

/** A lean-to roof from a0 (high, y0) to a1 (low, y1), b0..b1, seen from above and below. */
function lean(o: Out, a0: number, a1: number, y0: number, y1: number, b0: number, b1: number, m: BuildingMat, c: RGB): void {
  const p = [[a0, y0, b0], [a1, y1, b0], [a1, y1, b1], [a0, y0, b1]], n = [y0 - y1, a1 - a0, 0];
  o.quad(p, n, p.map((q) => [q[2], q[0]]), m, c);
  o.quad(p, [-n[0], -n[1], 0], p.map((q) => [q[2], q[0]]), m, c);
}
