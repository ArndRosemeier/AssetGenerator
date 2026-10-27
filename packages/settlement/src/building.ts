/**
 * Medieval buildings as meshes, from a planned TownBuilding: a rubble plinth, walls per storey (lime
 * plaster, rubble or dressed stone, or timber framing with real posts, rails and braces), upper storeys
 * jettied over the street, windows with reveals, frames, sills, leaded glass and painted shutters, a
 * plank door, gable or hip roofs with overhanging eaves and verges (thatch, tile, slate, shingle), gable
 * framing, chimneys, and the temple: a low stone hall with a porch, a round drum rising from its middle under a dome.
 *
 * Pure geometry (no three.js): positions relative to a given origin, normals, uv in metres (the game
 * divides by its texture's tile size), a material per vertex (BuildingMat) and a tint. `detail` false
 * gives the far version: the same shape without frames, beams, shutters and reveals.
 */
import { Rng } from '@futuremagic/core';
import type { TownBuilding } from './town';

/** Surface materials. The game maps each to a texture layer. */
export const BuildingMat = {
  Plaster: 0,
  Rubble: 1,
  Ashlar: 2,
  Oak: 3,
  Thatch: 4,
  Tile: 5,
  Slate: 6,
  Shingle: 7,
  Glass: 8,
} as const;
export type BuildingMat = (typeof BuildingMat)[keyof typeof BuildingMat];
export const BUILDING_MAT_COUNT = 9;

export interface BuildingMesh {
  position: Float32Array;
  normal: Float32Array;
  /** Texture coordinates in metres. */
  uv: Float32Array;
  /** BuildingMat per vertex. */
  mat: Uint8Array;
  /** Tint per vertex, rgb 0..255 (multiplies the texture). */
  tint: Uint8Array;
  index: Uint32Array;
}

export type RGB = [number, number, number];
const WHITE: RGB = [255, 255, 255];

/** Lime washes, ochres and pale earth colours for plaster. */
const WASHES: RGB[] = [[244, 238, 224], [238, 228, 204], [232, 214, 178], [226, 206, 170], [236, 222, 212], [214, 222, 214], [240, 232, 214], [222, 196, 160]];
/** Old oak, from weathered silver-brown to almost black. */
const TIMBERS: RGB[] = [[150, 120, 96], [110, 82, 62], [86, 62, 48], [66, 48, 38], [128, 104, 86]];
/** Painted shutters and doors. */
const PAINTS: RGB[] = [[120, 150, 110], [150, 70, 54], [80, 104, 130], [176, 140, 74], [116, 92, 70], [96, 120, 96]];
const STONES: RGB[] = [[236, 228, 214], [222, 214, 200], [210, 204, 196], [232, 220, 196]];

/** Collects triangles; `world` turns local (a, y, b) into positions relative to the origin. */
export class Out {
  pos: number[] = [];
  nrm: number[] = [];
  uv: number[] = [];
  mat: number[] = [];
  tint: number[] = [];
  idx: number[] = [];
  constructor(private readonly t: Frame) {}

  /** A quad from four local corners (any winding: it is turned to face `n`), uv from (s, t) metres. */
  quad(p: number[][], n: number[], uv: number[][], m: BuildingMat, c: RGB): void {
    const w = p.map((q) => this.t.point(q[0], q[1], q[2]));
    const wn = this.t.dir(n[0], n[1], n[2]);
    const base = this.pos.length / 3;
    for (let i = 0; i < 4; i++) {
      this.pos.push(w[i][0], w[i][1], w[i][2]);
      this.nrm.push(wn[0], wn[1], wn[2]);
      this.uv.push(uv[i][0], uv[i][1]);
      this.mat.push(m);
      this.tint.push(c[0], c[1], c[2]);
    }
    const e1 = [w[1][0] - w[0][0], w[1][1] - w[0][1], w[1][2] - w[0][2]], e2 = [w[2][0] - w[0][0], w[2][1] - w[0][1], w[2][2] - w[0][2]];
    const cx = e1[1] * e2[2] - e1[2] * e2[1], cy = e1[2] * e2[0] - e1[0] * e2[2], cz = e1[0] * e2[1] - e1[1] * e2[0];
    if (cx * wn[0] + cy * wn[1] + cz * wn[2] >= 0) this.idx.push(base, base + 1, base + 2, base, base + 2, base + 3);
    else this.idx.push(base, base + 2, base + 1, base, base + 3, base + 2);
  }

  /** A triangle (as a degenerate quad would waste a vertex: emitted directly). */
  tri(p: number[][], n: number[], uv: number[][], m: BuildingMat, c: RGB): void {
    const w = p.map((q) => this.t.point(q[0], q[1], q[2]));
    const wn = this.t.dir(n[0], n[1], n[2]);
    const base = this.pos.length / 3;
    for (let i = 0; i < 3; i++) {
      this.pos.push(w[i][0], w[i][1], w[i][2]);
      this.nrm.push(wn[0], wn[1], wn[2]);
      this.uv.push(uv[i][0], uv[i][1]);
      this.mat.push(m);
      this.tint.push(c[0], c[1], c[2]);
    }
    const e1 = [w[1][0] - w[0][0], w[1][1] - w[0][1], w[1][2] - w[0][2]], e2 = [w[2][0] - w[0][0], w[2][1] - w[0][1], w[2][2] - w[0][2]];
    const cx = e1[1] * e2[2] - e1[2] * e2[1], cy = e1[2] * e2[0] - e1[0] * e2[2], cz = e1[0] * e2[1] - e1[1] * e2[0];
    if (cx * wn[0] + cy * wn[1] + cz * wn[2] >= 0) this.idx.push(base, base + 1, base + 2);
    else this.idx.push(base, base + 2, base + 1);
  }

  /** An axis-aligned box in local space (a0..a1, y0..y1, b0..b1); `bottom` false leaves the underside out. */
  box(a0: number, a1: number, y0: number, y1: number, b0: number, b1: number, m: BuildingMat, c: RGB, bottom = false): void {
    const faces: [number[][], number[]][] = [
      [[[a0, y0, b0], [a1, y0, b0], [a1, y1, b0], [a0, y1, b0]], [0, 0, -1]],
      [[[a1, y0, b1], [a0, y0, b1], [a0, y1, b1], [a1, y1, b1]], [0, 0, 1]],
      [[[a0, y0, b1], [a0, y0, b0], [a0, y1, b0], [a0, y1, b1]], [-1, 0, 0]],
      [[[a1, y0, b0], [a1, y0, b1], [a1, y1, b1], [a1, y1, b0]], [1, 0, 0]],
      [[[a0, y1, b0], [a1, y1, b0], [a1, y1, b1], [a0, y1, b1]], [0, 1, 0]],
    ];
    if (bottom) faces.push([[[a0, y0, b1], [a1, y0, b1], [a1, y0, b0], [a0, y0, b0]], [0, -1, 0]]);
    for (const [p, n] of faces) this.quad(p, n, p.map((q) => planeUV(q, n)), m, c);
  }
}

/**
 * A round shield (a hall's sign, one on a weapon rack): a painted disc `r` across facing `n` (along a or b,
 * in the frame), its back at `c`, with an iron rim and boss.
 */
export function roundShield(o: Out, c: [number, number, number], n: [number, number], r: number, face: RGB, rim: RGB = [72, 72, 76], rimMat: BuildingMat = BuildingMat.Slate): void {
  const SEG = 12, th = 0.04;
  const ta = Math.abs(n[0]) > 0.5 ? 0 : 1, tb = 1 - ta, nn = [n[0], 0, n[1]];
  const at = (k: number, rr: number, d: number) => {
    const t = (k / SEG) * 2 * Math.PI, x = Math.cos(t) * rr, y = Math.sin(t) * rr;
    return [c[0] + ta * x + n[0] * d, c[1] + y, c[2] + tb * x + n[1] * d];
  };
  const mid = [c[0] + n[0] * th, c[1], c[2] + n[1] * th], uv = [[0.5, 0.5], [1, 0.5], [0.5, 1]];
  for (let k = 0; k < SEG; k++) {
    // Paint on a smooth ground (plaster), not on the dark oak: the colour reads in shade.
    o.tri([mid, at(k, r * 0.86, th), at(k + 1, r * 0.86, th)], nn, uv, BuildingMat.Plaster, face);
    o.quad([at(k, r * 0.86, th), at(k + 1, r * 0.86, th), at(k + 1, r, th), at(k, r, th)], nn, [[0, 0], [1, 0], [1, 1], [0, 1]], rimMat, rim);
    const t = ((k + 0.5) / SEG) * 2 * Math.PI, rn = [ta * Math.cos(t), Math.sin(t), tb * Math.cos(t)];
    o.quad([at(k, r, 0), at(k + 1, r, 0), at(k + 1, r, th), at(k, r, th)], rn, [[0, 0], [1, 0], [1, 1], [0, 1]], rimMat, rim);
  }
  const b = 0.06;
  o.box(mid[0] - b + n[0] * b, mid[0] + b + n[0] * b, c[1] - b, c[1] + b, mid[2] - b + n[1] * b, mid[2] + b + n[1] * b, rimMat, rim);
}

/** UV in metres for a planar face with normal n: the two axes in its plane. */
function planeUV(q: number[], n: number[]): number[] {
  if (Math.abs(n[1]) > 0.5) return [q[0], q[2]];
  if (Math.abs(n[0]) > 0.5) return [q[2], q[1]];
  return [q[0], q[1]];
}

/** The building's frame: local a along u, b along v, y up from the floor, to positions relative to the origin. */
export class Frame {
  constructor(private readonly b: { cx: number; cz: number; ux: number; uz: number; vx: number; vz: number; y: number }, private readonly o: [number, number, number]) {}
  point(a: number, y: number, bb: number): [number, number, number] {
    const f = this.b;
    return [f.cx + f.ux * a + f.vx * bb - this.o[0], f.y + y - this.o[1], f.cz + f.uz * a + f.vz * bb - this.o[2]];
  }
  dir(a: number, y: number, bb: number): [number, number, number] {
    const f = this.b;
    const x = f.ux * a + f.vx * bb, z = f.uz * a + f.vz * bb;
    const l = Math.hypot(x, y, z) || 1;
    return [x / l, y / l, z / l];
  }
}

/** A hole in a wall: from s0 to s1 along it (m from its first corner), t0 to t1 up from the storey's floor. */
export interface WallOpening { s0: number; s1: number; t0: number; t1: number; door?: boolean }
type Opening = WallOpening;

/** The look of one building, rolled from its seed. */
export interface Look {
  wash: RGB;
  timber: RGB;
  paint: RGB;
  stone: RGB;
  shutters: number;
  jetty: number;
  bay: number;
  /** The front door's outside: painted or bare wood (its own roll, so a door drawn apart matches: `doorLeaves`). */
  door: RGB;
}

/** One wall of a storey: from (a0, b0) to (a1, b1) in the building's frame, counter-clockwise seen from above. */
export interface HouseWall {
  /** 0 front (the street, with the door), 1 right (+a), 2 back, 3 left (-a). */
  id: 0 | 1 | 2 | 3;
  a0: number; b0: number; a1: number; b1: number;
  opens: WallOpening[];
}

/** One storey: its floor and the walls' top over the building's floor (m), and its front and back (b). */
export interface HouseStorey {
  y0: number; y1: number;
  front: number; back: number;
  mat: BuildingMat;
  /** The wall's colour (plaster's wash or the stone's). */
  tint: RGB;
  /** Plaster between timber framing. */
  timbered: boolean;
  walls: HouseWall[];
}

/** Where the chimney's stack stands (its middle in the building's frame) and the wall the hearth is built against. */
export interface HouseChimney { a: number; b: number; wall: 'left' | 'right' | 'back' }

/**
 * A building's shape as the outside shows it and the inside must match: its storeys (jettied out over the
 * street), every window and the door on every wall, and the chimney. `buildingMesh` draws it from outside,
 * `planInterior` and `interiorMesh` furnish and draw it from within; both read this, so they agree.
 */
export interface HouseShape {
  look: Look;
  storeys: HouseStorey[];
  /** The walls' top, where the roof sits, and the top storey's front and back (b). */
  top: number; front: number; back: number;
  chimney: HouseChimney | null;
}

/** Inner wall thickness (m): the inside faces stand this far in from the outside ones. */
export const WALL_THICK = 0.28;

/** The shape of `b` (see HouseShape). Pure and seeded: the same building gives the same shape. */
export function houseShape(b: TownBuilding): HouseShape {
  const r = new Rng(b.seed);
  const look: Look = {
    wash: r.pick(WASHES), timber: r.pick(TIMBERS), paint: r.pick(PAINTS), stone: r.pick(STONES),
    shutters: r.range(0.2, 0.8),
    jetty: b.kind !== 'temple' && b.floors > 1 && b.wall !== 'stone' && r.chance(b.attached ? 0.7 : 0.4) ? r.range(0.3, 0.5) : 0,
    bay: r.range(2.4, 3.1),
    door: [0, 0, 0],
  };
  look.door = new Rng(b.seed ^ 0xd00e).chance(0.5) ? look.paint : look.timber;
  const { hu, hv } = b;
  if (b.kind === 'temple') {
    // The hall: a low square of stone, small windows high up, a wide door at the front.
    const H = b.floorH, walls: HouseWall[] = [];
    const sides: [number, number, number, number, 0 | 1 | 2 | 3][] = [[hu, -hv, hu, hv, 1], [hu, hv, -hu, hv, 2], [-hu, hv, -hu, -hv, 3], [-hu, -hv, hu, -hv, 0]];
    for (const [a0, b0, a1, b1, id] of sides) {
      const len = Math.hypot(a1 - a0, b1 - b0), opens: Opening[] = [];
      if (id !== 0) for (let s = 1.8; s < len - 1.2; s += 2.6) opens.push({ s0: s - 0.35, s1: s + 0.35, t0: H - 2.1, t1: H - 1.3 });
      else opens.push({ s0: len / 2 - 1.1, s1: len / 2 + 1.1, t0: 0, t1: 3.2, door: true });
      walls.push({ id, a0, b0, a1, b1, opens });
    }
    return { look, storeys: [{ y0: 0, y1: H, front: -hv, back: hv, mat: BuildingMat.Ashlar, tint: look.stone, timbered: false, walls }], top: H, front: -hv, back: hv, chimney: null };
  }
  const wallMat = b.wall === 'stone' ? (r.chance(0.6) ? BuildingMat.Rubble : BuildingMat.Ashlar) : BuildingMat.Plaster;
  const tint = b.wall === 'stone' ? look.stone : look.wash;
  const storeys: HouseStorey[] = [];
  // The chimney first: no window where its breast stands against the wall inside.
  const chim = chimneyOf(b, r);
  const breast = chim ? (b.kind === 'smithy' || b.kind === 'bakery' ? 1.2 : 0.9) : 0;
  let y = 0, front = -hv, back = hv;
  for (let f = 0; f < b.floors; f++) {
    const h = b.floorH;
    // A jetty: each upper storey stands out over the street (and on free-standing houses over the back too).
    if (f > 0 && look.jetty > 0) {
      front -= look.jetty;
      if (!b.attached) back += look.jetty * 0.6;
    }
    const ground = f === 0;
    // A stone ground floor under plastered or timbered upper floors, now and then.
    const mat = ground && b.wall !== 'stone' && b.floors > 1 && r.chance(0.3) ? BuildingMat.Rubble : wallMat;
    const sides: [number, number, number, number, 0 | 1 | 2 | 3][] = [
      [-hu, front, hu, front, 0], [hu, front, hu, back, 1], [hu, back, -hu, back, 2], [-hu, back, -hu, front, 3],
    ];
    const walls = sides.map(([a0, b0, a1, b1, id]): HouseWall => {
      const len = Math.hypot(a1 - a0, b1 - b0);
      const blind = b.attached && (id === 1 || id === 3);
      // Where the breast is along this wall (s from its first corner).
      const at = !chim ? null : chim.wall === 'back' && id === 2 ? hu - chim.a : chim.wall === 'right' && id === 1 ? chim.b - front : chim.wall === 'left' && id === 3 ? back - chim.b : null;
      const opens = blind ? [] : openings(len, h, look.bay, ground && id === 0 ? doorAt(a0, a1, len) : null, ground, b.kind, r);
      return { id, a0, b0, a1, b1, opens: at === null ? opens : opens.filter((q) => q.s1 < at - breast || q.s0 > at + breast) };
    });
    storeys.push({ y0: y, y1: y + h, front, back, mat, tint: mat === BuildingMat.Plaster ? tint : look.stone, timbered: b.wall === 'timber' && mat === BuildingMat.Plaster, walls });
    y += h;
  }
  return { look, storeys, top: y, front, back, chimney: chim };
}

/**
 * Where the hearth and its chimney go: over the forge or the oven at the back of a smithy or bakery, else
 * against a gable wall (a side wall when the ridge runs along the street, the back wall when it runs into
 * the plot); the inn's hearth is always on its left wall, clear of the counter across the back.
 */
function chimneyOf(b: TownBuilding, r: Rng): HouseChimney | null {
  if (b.kind === 'stable' || b.kind === 'barn' || b.kind === 'temple') return null;
  const ha = Math.max(1.6, b.hu - WALL_THICK), hb = Math.max(1.6, b.hv - WALL_THICK);
  if (b.kind === 'smithy') return { a: (r.chance(0.5) ? -1 : 1) * Math.min(ha - 1.0, 1.2), b: hb - 0.6, wall: 'back' };
  if (b.kind === 'bakery') return { a: 0, b: hb - 0.7, wall: 'back' };
  // On a gable wall, where the stack rises through the roof near its ridge.
  if (b.kind === 'inn') return b.ridgeAlongU ? { a: -(ha - 0.45), b: r.range(-0.5, 0.5), wall: 'left' } : { a: r.range(-0.5, 0.5), b: hb - 0.45, wall: 'back' };
  const side = r.chance(0.5) ? -1 : 1;
  if (b.ridgeAlongU || hb < 2.2) return { a: side * (ha - 0.45), b: r.range(-0.3, 0.3), wall: side < 0 ? 'left' : 'right' };
  return { a: side * r.range(0.25, 0.5) * ha, b: hb - 0.45, wall: 'back' };
}

/** `open`: the door stands open (the inside is drawn too, by `interiorMesh`): no door leaf in the doorway. */
/** `open`: drawn to be walked into (interior.ts). `sign`: a round shield of this colour over the door (a game's guild hall). */
export function buildingMesh(b: TownBuilding, origin: [number, number, number], detail = true, opts: { open?: boolean; sign?: RGB } = {}): BuildingMesh {
  const S = houseShape(b);
  // The small things (shutters, paint, braces) from a stream of their own: the near and far versions draw
  // different ones, and the shape must not move with them.
  const r = new Rng(b.seed ^ 0x5eed);
  const ux = Math.cos(b.angle), uz = Math.sin(b.angle);
  const frame = new Frame({ cx: b.cx, cz: b.cz, ux, uz, vx: b.vx, vz: b.vz, y: b.floorY }, origin);
  const out = new Out(frame);
  const open = !!opts.open;
  if (b.kind === 'temple') temple(out, b, S, r, detail, open);
  else house(out, b, S, r, detail, open);
  if (opts.sign) doorSign(out, b, S, opts.sign);
  return {
    position: Float32Array.from(out.pos), normal: Float32Array.from(out.nrm), uv: Float32Array.from(out.uv),
    mat: Uint8Array.from(out.mat), tint: Uint8Array.from(out.tint), index: Uint32Array.from(out.idx),
  };
}

// ---------------------------------------------------------------- what one walks on

/** A box in a building's frame (u across, v from the front at -hv to the back), its top over the floor (m). */
export interface EntranceBox {
  u0: number; u1: number; v0: number; v1: number;
  /** Top, metres above the building's floor (floorY); the box goes down into the ground. */
  top: number;
  mat: BuildingMat;
}

/** What stands in front of a building's door: platforms and steps to walk on, and posts in the way. */
export interface Entrance {
  /** Walked on (the hero stands on the highest one under them). */
  floors: EntranceBox[];
  /** Solid from the ground up (the temple porch's columns). */
  posts: EntranceBox[];
}

/** Steps from the ground up to `top`, in front of `front` (v), `half` wide each side of the middle. */
function stepsUp(b: TownBuilding, front: number, top: number, half: number): EntranceBox[] {
  const rise = top + b.floorY - b.groundY;
  if (rise <= 0.3) return [];
  const n = Math.min(5, Math.ceil(rise / 0.2)), h = rise / (n + 1), out: EntranceBox[] = [];
  // The lowest and outermost first; each one 0.32 m deep and a step higher.
  for (let i = 0; i < n; i++) out.push({ u0: -half, u1: half, v0: front - 0.32 * (n - i), v1: front, top: top - h * (n - i), mat: BuildingMat.Ashlar });
  return out;
}

/** The porch, steps and columns before a building's door (the mesh draws them; the game walks on them). */
export function buildingEntrance(b: TownBuilding): Entrance {
  if (b.kind === 'temple') {
    const { w, f0, f1, top, cols } = porch(b);
    const floor: EntranceBox = { u0: -w - 0.4, u1: w + 0.4, v0: f0 - 0.5, v1: f1, top: 0.25, mat: BuildingMat.Rubble };
    const posts = cols.map((a) => ({ u0: a - 0.25, u1: a + 0.25, v0: f0 + 0.1, v1: f0 + 0.6, top, mat: BuildingMat.Ashlar }));
    return { floors: [floor, ...stepsUp(b, f0 - 0.5, 0.25, Math.min(w, 1.6))], posts };
  }
  return { floors: stepsUp(b, -b.hv - 0.06, 0, 0.7), posts: [] };
}

/** The temple porch's measures: half width, front and back (v), the columns' top and where they stand (u). */
function porch(b: TownBuilding, detail = true): { w: number; f0: number; f1: number; top: number; cols: number[] } {
  const w = Math.min(b.hu - 0.4, 3.6), d = 2.2, n = detail ? 4 : 2;
  return { w, f0: -b.hv - d, f1: -b.hv, top: b.floorH - 0.6, cols: Array.from({ length: n }, (_, i) => -w + 0.3 + ((2 * w - 0.6) * i) / (n - 1)) };
}

/** Draws the entrance's boxes down to below the lowest ground. */
function drawEntrance(o: Out, b: TownBuilding, L: Look): void {
  const down = b.floorY - b.groundY + 0.3;
  for (const f of buildingEntrance(b).floors) o.box(f.u0, f.u1, -down, f.top, f.v0, f.v1, f.mat, L.stone);
}

// ---------------------------------------------------------------- houses

/**
 * A plastered wall seen from afar (no frames, windows or shutters drawn): its tint carries them on
 * average, so far houses are not paler than near ones.
 */
function farWall(c: RGB, L: Look, timbered: boolean): RGB {
  const k = timbered ? 0.3 : 0, dim = 0.86;
  return [0, 1, 2].map((i) => Math.round((c[i] * (1 - k) + L.timber[i] * k) * dim)) as RGB;
}

function house(o: Out, b: TownBuilding, S: HouseShape, r: Rng, detail: boolean, open: boolean): void {
  const { hu, hv } = b, L = S.look;
  const plinthDown = b.floorY - b.groundY + 0.3;
  // The plinth: rubble from below the lowest ground to the floor. Opened, its top drops under the
  // room's floor boards (interior.ts FLOOR), or the two fight for the same depth.
  o.box(-hu - 0.06, hu + 0.06, -plinthDown, open ? 0 : 0.05, -hv - 0.06, hv + 0.06, BuildingMat.Rubble, L.stone);
  // Steps up to the door.
  if (detail) drawEntrance(o, b, L);
  S.storeys.forEach((st, f) => {
    const y = st.y0;
    if (f > 0 && st.front < S.storeys[f - 1].front) {
      const f0 = S.storeys[f - 1].front, front = st.front;
      if (detail) for (let a = -hu + 0.3; a < hu - 0.1; a += 0.62) o.box(a - 0.08, a + 0.08, y - 0.18, y, front, f0 + 0.05, BuildingMat.Oak, L.timber, true);
      // The jetty's underside.
      o.quad([[-hu, y - 0.18, front], [hu, y - 0.18, front], [hu, y - 0.18, f0], [-hu, y - 0.18, f0]], [0, -1, 0], [[-hu, front], [hu, front], [hu, f0], [-hu, f0]], BuildingMat.Oak, L.timber);
    }
    const tn = st.mat === BuildingMat.Plaster && !detail ? farWall(st.tint, L, st.timbered) : st.tint;
    for (const w of st.walls) wall(o, w.a0, w.b0, w.a1, w.b1, st.y0, st.y1, w.opens, st.mat, tn, detail, L, st.timbered, r, open);
  });
  roof(o, b, -hu, hu, S.front, S.back, S.top, L, detail);
  chimney(o, b, S, detail);
}

/** Where a building's door sign goes (building frame): flat on the front wall, or hung from a bracket where no wall is free. */
export interface SignPlace {
  readonly a: number; readonly y: number; readonly b: number;
  readonly r: number;
  /** Flat on the wall facing the street; else hung from a bracket, painted both sides. */
  readonly flat: boolean;
}

/**
 * Where the sign of `b` goes, the same rule for every house: a round shield flat on the front wall beside
 * the door, clear of the door, the windows and their shutters, under the roof's underside (a low thatch
 * comes down to the ground floor's top) or the storey's top beam; smaller if need be (down to 0.22 m); where the front has
 * no such place, hung from a short bracket beside the door, under the eave. Null without a front door.
 */
export function signPlace(b: TownBuilding, S: HouseShape): SignPlace | null {
  const st = S.storeys[0], w = st.walls.find((x) => x.id === 0), q = w?.opens.find((x) => x.door);
  if (!w || !q) return null;
  const len = Math.hypot(w.a1 - w.a0, w.b1 - w.b0), da = (w.a1 - w.a0) / len, db = (w.b1 - w.b0) / len;
  const at = (s: number) => [w.a0 + da * s, w.b0 + db * s] as const;
  // The free wall's top: under the roof where it comes down onto this storey's front, else under the beam.
  const eaves = S.storeys.length === 1 && b.ridgeAlongU;
  const thick = b.cover === 'thatch' ? 0.38 : 0.14;
  // Where the roof comes down over the front, under its edge out past the wall (seen from the street the
  // eave hides what is above that), not just under it at the wall.
  const top = eaves ? Math.min(st.y1, S.top) - eaveOf(b) * b.pitch - thick - 0.05 : st.y1 - 0.12;
  // Windows widened by their shutters (each half the window's width) and a hand's breadth.
  const keep = w.opens.filter((o) => !o.door).map((o) => ({ s0: o.s0 - (o.s1 - o.s0) / 2 - 0.08, s1: o.s1 + (o.s1 - o.s0) / 2 + 0.08, t0: o.t0 - 0.08, t1: o.t1 + 0.08 }));
  for (const r of [0.36, 0.3, 0.25, 0.22]) {
    // At about head height beside the door (higher only shows its rim under a low eave).
    const y = Math.min(top - r, st.y0 + 1.75);
    if (y - r < st.y0 + 0.8) continue;
    for (let d = 0; d < 2.0; d += 0.1) {
      for (const s of [q.s1 + 0.12 + r + d, q.s0 - 0.12 - r - d]) {
        if (s - r < 0.25 || s + r > len - 0.25) continue;
        if (keep.some((o) => s + r > o.s0 && s - r < o.s1 && y + r > st.y0 + o.t0 && y - r < st.y0 + o.t1)) continue;
        const [pa, pb] = at(s);
        return { a: pa, y, b: pb, r, flat: true };
      }
    }
  }
  // No free wall: a short bracket beside the door, its arm under the eave where the eave comes down.
  const right = len - q.s1 >= q.s0, s = right ? Math.min(len - 0.3, q.s1 + 0.45) : Math.max(0.3, q.s0 - 0.45);
  const [pa, pb] = at(s), r = 0.28;
  return { a: pa, y: Math.max(st.y0 + 1.3, Math.min(st.y0 + 2.1, top - 0.1 - (eaves ? 0.6 * b.pitch : 0))) - r - 0.08, b: pb, r, flat: false };
}

/** A guild's sign on the front wall (`signPlace`), with a brass rim that catches the light in shade. */
function doorSign(o: Out, b: TownBuilding, S: HouseShape, face: RGB): void {
  const p = signPlace(b, S);
  if (!p) return;
  // Brass: a pale gold on the plaster ground (on slate it went olive in shade).
  const iron: RGB = [52, 50, 48], brass: RGB = [214, 178, 98];
  if (p.flat) {
    // A peg in the wall, the shield on it facing the street.
    roundShield(o, [p.a, p.y, p.b - 0.06], [0, -1], p.r, face, brass, BuildingMat.Plaster);
    return;
  }
  // No free wall: an arm out from the wall, the shield on its end, still facing the street.
  const out = 0.55, armY = p.y + p.r + 0.08;
  o.box(p.a - 0.03, p.a + 0.03, armY, armY + 0.05, p.b - out, p.b, BuildingMat.Slate, iron, true);
  o.box(p.a - 0.025, p.a + 0.025, armY - 0.4, armY + 0.05, p.b - 0.05, p.b, BuildingMat.Slate, iron, true);
  o.box(p.a - 0.015, p.a + 0.015, p.y + p.r - 0.02, armY, p.b - out - 0.015, p.b - out + 0.015, BuildingMat.Slate, iron);
  roundShield(o, [p.a, p.y, p.b - out - 0.02], [0, -1], p.r, face, brass, BuildingMat.Plaster);
  roundShield(o, [p.a, p.y, p.b - out + 0.02], [0, 1], p.r, face, brass, BuildingMat.Plaster);
}

/** Where the door goes along the front wall (s from a0): the middle, where the plan put it. */
function doorAt(a0: number, a1: number, len: number): number {
  return a1 > a0 ? -a0 : len + a0;
}

/** Windows (and the door) on a wall `len` long and `h` high. */
function openings(len: number, h: number, bay: number, door: number | null, ground: boolean, kind: TownBuilding['kind'], r: Rng): Opening[] {
  const out: Opening[] = [];
  const shop = ground && (kind === 'workshop' || kind === 'bakery' || kind === 'smithy' || kind === 'inn');
  if (door !== null) {
    // A barn's doors take a loaded wagon.
    const w = kind === 'barn' ? 3.4 : kind === 'stable' || kind === 'smithy' || kind === 'mill' ? 1.9 : kind === 'inn' ? 1.3 : 1.05;
    out.push({ s0: door - w / 2, s1: door + w / 2, t0: 0, t1: Math.min(h - 0.35, kind === 'barn' ? 3.4 : kind === 'stable' ? 2.5 : 2.05), door: true });
  }
  // Barns are dark inside: a few small vents high up, no windows.
  if (kind === 'barn') {
    for (const c of [len * 0.2, len * 0.8]) if (door === null || Math.abs(c - door) > 2.6) out.push({ s0: c - 0.3, s1: c + 0.3, t0: h - 1.2, t1: h - 0.7 });
    return out;
  }
  const n = Math.max(1, Math.round(len / bay));
  for (let i = 0; i < n; i++) {
    const c = (i + 0.5) * (len / n);
    const w = shop ? 1.4 : ground ? 0.75 : 0.85, hh = shop ? 1.2 : ground ? 0.95 : 1.1;
    const t0 = shop ? 0.75 : ground ? 1.0 : 0.85;
    if (c - w / 2 < 0.45 || c + w / 2 > len - 0.45) continue;
    if (out.some((q) => q.door && c + w / 2 > q.s0 - 0.5 && c - w / 2 < q.s1 + 0.5)) continue;
    if (!shop && r.chance(0.12)) continue; // a blank bay now and then
    out.push({ s0: c - w / 2, s1: c + w / 2, t0, t1: Math.min(h - 0.3, t0 + hh) });
  }
  return out;
}

/**
 * One storey of one wall: the face with holes for its openings, their reveals, glass, frames, sills and
 * shutters, the door leaf, and timber framing.
 */
function wall(o: Out, a0: number, b0: number, a1: number, b1: number, y0: number, y1: number, opens: Opening[], m: BuildingMat, c: RGB, detail: boolean, L: Look, timbered: boolean, r: Rng, open = false): void {
  const len = Math.hypot(a1 - a0, b1 - b0);
  const da = (a1 - a0) / len, db = (b1 - b0) / len;
  // Outward normal: the wall runs counter-clockwise seen from above in (a, b), so outward is (db, -da).
  const na = db, nb = -da;
  const P = (s: number, t: number, d = 0): number[] => [a0 + da * s + na * d, t, b0 + db * s + nb * d];
  const N = [na, 0, nb];
  // The face, split on a grid at the openings' edges.
  const ss = [0, len], ts = [y0, y1];
  for (const q of opens) { ss.push(q.s0, q.s1); ts.push(y0 + q.t0, y0 + q.t1); }
  const S = [...new Set(ss)].sort((x, y) => x - y), T = [...new Set(ts)].sort((x, y) => x - y);
  for (let i = 0; i + 1 < S.length; i++) for (let j = 0; j + 1 < T.length; j++) {
    const sm = (S[i] + S[i + 1]) / 2, tm = (T[j] + T[j + 1]) / 2 - y0;
    if (opens.some((q) => sm > q.s0 && sm < q.s1 && tm > q.t0 && tm < q.t1)) continue;
    o.quad([P(S[i], T[j]), P(S[i + 1], T[j]), P(S[i + 1], T[j + 1]), P(S[i], T[j + 1])], N, [[S[i], T[j]], [S[i + 1], T[j]], [S[i + 1], T[j + 1]], [S[i], T[j + 1]]], m, c);
  }
  const frameMat = m === BuildingMat.Plaster ? BuildingMat.Oak : BuildingMat.Ashlar;
  const frameTint = m === BuildingMat.Plaster ? L.timber : L.stone;
  for (const q of opens) {
    const t0 = y0 + q.t0, t1 = y0 + q.t1;
    const back = q.door ? 0.12 : 0.16;
    if (detail) {
      // Reveals.
      o.quad([P(q.s0, t0), P(q.s0, t1), P(q.s0, t1, -back), P(q.s0, t0, -back)], [da, 0, db], [[0, t0], [0, t1], [back, t1], [back, t0]], m, c);
      o.quad([P(q.s1, t0), P(q.s1, t1), P(q.s1, t1, -back), P(q.s1, t0, -back)], [-da, 0, -db], [[0, t0], [0, t1], [back, t1], [back, t0]], m, c);
      o.quad([P(q.s0, t1), P(q.s1, t1), P(q.s1, t1, -back), P(q.s0, t1, -back)], [0, -1, 0], [[q.s0, 0], [q.s1, 0], [q.s1, back], [q.s0, back]], m, c);
      if (!q.door) o.quad([P(q.s0, t0), P(q.s1, t0), P(q.s1, t0, -back), P(q.s0, t0, -back)], [0, 1, 0], [[q.s0, 0], [q.s1, 0], [q.s1, back], [q.s0, back]], m, c);
    }
    const d = detail ? -back : -0.02;
    if (q.door) {
      // A plank door, painted or bare (the paint rolled either way, so an open door keeps the rest).
      // (The roll is kept so the rest of the walls roll as before.)
      r.chance(0.5);
      const paint = L.door;
      if (!open) o.quad([P(q.s0, t0, d), P(q.s1, t0, d), P(q.s1, t1, d), P(q.s0, t1, d)], N, [[q.s0, t0], [q.s1, t0], [q.s1, t1], [q.s0, t1]], BuildingMat.Oak, paint);
    } else {
      o.quad([P(q.s0, t0, d), P(q.s1, t0, d), P(q.s1, t1, d), P(q.s0, t1, d)], N, [[q.s0, t0], [q.s1, t0], [q.s1, t1], [q.s0, t1]], BuildingMat.Glass, WHITE);
    }
    if (!detail) continue;
    // Frame, and a sill under windows.
    const fw = 0.09, fo = 0.035;
    const fb = (s0: number, s1: number, u0: number, u1: number, thick?: number) => frameBox(o, P, da, db, na, nb, s0, s1, u0, u1, fo, frameMat, frameTint, thick);
    fb(q.s0 - fw, q.s0, t0, t1 + fw);
    fb(q.s1, q.s1 + fw, t0, t1 + fw);
    fb(q.s0, q.s1, t1, t1 + fw);
    if (!q.door) {
      fb(q.s0 - fw - 0.04, q.s1 + fw + 0.04, t0 - 0.07, t0);
      // Shutters, folded back against the wall.
      if (r.float() < L.shutters) {
        const w = (q.s1 - q.s0) / 2;
        fb(q.s0 - fw - w, q.s0 - fw - 0.01, t0, t1, 0.03);
        fb(q.s1 + fw + 0.01, q.s1 + fw + w, t0, t1, 0.03);
      }
    }
  }
  if (detail && timbered) frameWall(o, P, da, db, na, nb, len, y0, y1, opens, L, r);
}

/** A box lying on the wall face from (s0, t0) to (s1, t1), `d` thick (outwards). */
function frameBox(o: Out, P: (s: number, t: number, d?: number) => number[], da: number, db: number, na: number, nb: number, s0: number, s1: number, t0: number, t1: number, d: number, m: BuildingMat, c: RGB, thick?: number): void {
  const dd = thick ?? d;
  const N = [na, 0, nb];
  o.quad([P(s0, t0, dd), P(s1, t0, dd), P(s1, t1, dd), P(s0, t1, dd)], N, [[s0, t0], [s1, t0], [s1, t1], [s0, t1]], m, c);
  o.quad([P(s0, t1, 0), P(s1, t1, 0), P(s1, t1, dd), P(s0, t1, dd)], [0, 1, 0], [[s0, 0], [s1, 0], [s1, dd], [s0, dd]], m, c);
  o.quad([P(s0, t0, 0), P(s1, t0, 0), P(s1, t0, dd), P(s0, t0, dd)], [0, -1, 0], [[s0, 0], [s1, 0], [s1, dd], [s0, dd]], m, c);
  o.quad([P(s0, t0, 0), P(s0, t1, 0), P(s0, t1, dd), P(s0, t0, dd)], [-da, 0, -db], [[t0, 0], [t1, 0], [t1, dd], [t0, dd]], m, c);
  o.quad([P(s1, t0, 0), P(s1, t1, 0), P(s1, t1, dd), P(s1, t0, dd)], [da, 0, db], [[t0, 0], [t1, 0], [t1, dd], [t0, dd]], m, c);
}

/** Timber framing over a plastered storey: corner posts, sill and head rails, posts at the openings, braces. */
function frameWall(o: Out, P: (s: number, t: number, d?: number) => number[], da: number, db: number, na: number, nb: number, len: number, y0: number, y1: number, opens: Opening[], L: Look, r: Rng): void {
  const w = 0.2, d = 0.045, c = L.timber;
  const box = (s0: number, s1: number, t0: number, t1: number) => frameBox(o, P, da, db, na, nb, s0, s1, t0, t1, d, BuildingMat.Oak, c);
  box(0, len, y0, y0 + w);
  box(0, len, y1 - w, y1);
  box(0, w, y0 + w, y1 - w);
  box(len - w, len, y0 + w, y1 - w);
  // Posts beside the openings, and between them where the gap is wide.
  const posts: number[] = [];
  for (const q of opens) posts.push(q.s0 - 0.09 - w / 2, q.s1 + 0.09 + w / 2);
  const all = [w / 2, ...posts.sort((a, b) => a - b), len - w / 2];
  const keep: number[] = [];
  for (const p of all) {
    // Long blank stretches get posts of their own, at most 1.5 m apart.
    const last = keep.length ? keep[keep.length - 1] : null;
    if (last !== null && p - last > 1.7) { const k = Math.ceil((p - last) / 1.5); for (let i = 1; i < k; i++) keep.push(last + ((p - last) * i) / k); }
    if (last === null || p - keep[keep.length - 1] > 0.5) keep.push(p);
  }
  for (const p of keep.slice(1, -1)) if (!opens.some((q) => p > q.s0 - 0.05 && p < q.s1 + 0.05)) box(p - w / 2, p + w / 2, y0 + w, y1 - w);
  // A rail at window-sill height, and braces in the blank panels.
  for (let i = 0; i + 1 < keep.length; i++) {
    const s0 = keep[i] + w / 2, s1 = keep[i + 1] - w / 2;
    if (s1 - s0 < 0.6) continue;
    if (opens.some((q) => (s0 + s1) / 2 > q.s0 && (s0 + s1) / 2 < q.s1)) continue;
    const mid = y0 + (y1 - y0) * 0.42;
    box(s0, s1, mid - 0.08, mid + 0.08);
    if (s1 - s0 > 1.1 && r.chance(0.8)) {
      // A brace: from a bottom corner of the panel up to the far post (a "man" figure's leg, simplified).
      const left = r.chance(0.5);
      braceOn(o, P, na, nb, left ? s0 : s1, y0 + w, left ? s1 : s0, mid - 0.08, 0.17, d, c);
      braceOn(o, P, na, nb, left ? s1 : s0, mid + 0.08, left ? s0 : s1, y1 - w, 0.17, d, c);
    }
  }
}

/** A diagonal timber on the wall face from (s0, t0) to (s1, t1). */
function braceOn(o: Out, P: (s: number, t: number, d?: number) => number[], na: number, nb: number, s0: number, t0: number, s1: number, t1: number, w: number, d: number, c: RGB): void {
  const ds = s1 - s0, dt = t1 - t0, L = Math.hypot(ds, dt) || 1;
  const os = (-dt / L) * (w / 2), ot = (ds / L) * (w / 2);
  // Ends cut to the rails (horizontal), so the brace meets them flush.
  const q = [[s0 - os, t0 - ot], [s1 - os, t1 - ot], [s1 + os, t1 + ot], [s0 + os, t0 + ot]].map(([s, t]) => [s, Math.min(Math.max(t, Math.min(t0, t1)), Math.max(t0, t1))]);
  o.quad(q.map(([s, t]) => P(s, t, d)), [na, 0, nb], q.map(([s, t]) => [(s - s0) * ds / L + (t - t0) * dt / L, -(s - s0) * dt / L + (t - t0) * ds / L]), BuildingMat.Oak, c);
  for (let i = 0; i < 4; i++) {
    const [s, t] = q[i], [s2, t2] = q[(i + 1) % 4];
    const el = Math.hypot(s2 - s, t2 - t);
    if (el < 1e-4) continue;
    // Side faces: their normal lies in the wall plane; the quad helper turns it to face outwards from the brace.
    const ms = (s + s2) / 2 - (s0 + s1) / 2, mt = (t + t2) / 2 - (t0 + t1) / 2;
    const P0 = P(0, 0), Ps = P(1, 0), Pt = P(0, 1);
    const nx = (Ps[0] - P0[0]) * ms + (Pt[0] - P0[0]) * mt, ny = (Ps[1] - P0[1]) * ms + (Pt[1] - P0[1]) * mt, nz = (Ps[2] - P0[2]) * ms + (Pt[2] - P0[2]) * mt;
    o.quad([P(s, t, 0), P(s2, t2, 0), P(s2, t2, d), P(s, t, d)], [nx, ny, nz], [[0, 0], [el, 0], [el, d], [0, d]], BuildingMat.Oak, c);
  }
}

// ---------------------------------------------------------------- roofs

const COVER_MAT: Record<TownBuilding['cover'], BuildingMat> = { thatch: BuildingMat.Thatch, tile: BuildingMat.Tile, slate: BuildingMat.Slate, shingle: BuildingMat.Shingle };

/** The roof over the rectangle a0..a1 × b0..b1 whose walls end at `y`. */
function roof(o: Out, b: TownBuilding, a0: number, a1: number, b0: number, b1: number, y: number, L: Look, detail: boolean): void {
  const m = COVER_MAT[b.cover];
  const thick = b.cover === 'thatch' ? 0.38 : 0.14;
  const eave = eaveOf(b);
  const tint: RGB = b.cover === 'thatch' ? [255, 246, 228] : b.cover === 'tile' ? [255, 236, 226] : WHITE;
  // Work in a frame where the ridge runs along `p` (from -P to P) and the slopes fall along `q` (-Q to Q).
  const alongU = b.ridgeAlongU;
  const P = alongU ? (a1 - a0) / 2 : (b1 - b0) / 2, Q = alongU ? (b1 - b0) / 2 : (a1 - a0) / 2;
  const ca = (a0 + a1) / 2, cb = (b0 + b1) / 2;
  const toLocal = (p: number, h: number, q: number): number[] => (alongU ? [ca + p, h, cb + q] : [ca + q, h, cb + p]);
  const rise = Q * b.pitch;
  const verge = b.attached && alongU ? 0.02 : 0.3;
  const hip = b.roof === 'hip' && P > Q * 0.6;
  const eaveY = y - eave * b.pitch;
  if (!hip) {
    for (const side of [-1, 1]) {
      // One slope: from the eave (q = side * (Q + eave)) up to the ridge (q = 0).
      const n = normalise([0, Q, side * rise]);
      const nl = alongU ? [0, n[1], n[2]] : [n[2], n[1], 0];
      const qe = side * (Q + eave), slope = Math.hypot(Q + eave, rise + eave * b.pitch);
      const top = [toLocal(-P - verge, eaveY, qe), toLocal(P + verge, eaveY, qe), toLocal(P + verge, y + rise, 0), toLocal(-P - verge, y + rise, 0)];
      const uv = [[-P - verge, 0], [P + verge, 0], [P + verge, slope], [-P - verge, slope]];
      o.quad(top, nl, uv, m, tint);
      const under = top.map((v) => [v[0], v[1] - thick, v[2]]);
      o.quad(under, [-nl[0], -nl[1], -nl[2]], uv, BuildingMat.Oak, L.timber);
      // The eave's edge and the verges.
      o.quad([top[0], top[1], under[1], under[0]], alongU ? [0, 0, side] : [side, 0, 0], [[-P, 0], [P, 0], [P, thick], [-P, thick]], m, tint);
      for (const e of [0, 1]) {
        const i = e === 0 ? 0 : 1, j = e === 0 ? 3 : 2;
        o.quad([top[i], top[j], under[j], under[i]], alongU ? [e === 0 ? -1 : 1, 0, 0] : [0, 0, e === 0 ? -1 : 1], [[0, 0], [slope, 0], [slope, thick], [0, thick]], m, tint);
      }
    }
    // The gables: wall triangles at both ends, framed on timber houses.
    for (const e of [-1, 1]) {
      const p = e * P;
      const gm = b.wall === 'stone' ? BuildingMat.Rubble : BuildingMat.Plaster;
      const gc = b.wall === 'stone' ? L.stone : detail ? L.wash : farWall(L.wash, L, b.wall === 'timber');
      const n = alongU ? [e, 0, 0] : [0, 0, e];
      o.tri([toLocal(p, y, -Q), toLocal(p, y, Q), toLocal(p, y + rise - 0.05, 0)], n, [[-Q, y], [Q, y], [0, y + rise]], gm, gc);
      if (detail && b.wall === 'timber') {
        const off = e * 0.04;
        const post = (q0: number, q1: number, h0: number, h1: number) => {
          const pts = [toLocal(p + off, h0, q0), toLocal(p + off, h0, q1), toLocal(p + off, h1, q1), toLocal(p + off, h1, q0)];
          o.quad(pts, n, [[q0, h0], [q1, h0], [q1, h1], [q0, h1]], BuildingMat.Oak, L.timber);
        };
        const strut = (q0: number, h0: number, q1: number, h1: number) => {
          const dq = q1 - q0, dh = h1 - h0, l = Math.hypot(dq, dh) || 1, wq = (-dh / l) * 0.08, wh = (dq / l) * 0.08;
          const pts = [toLocal(p + off, h0 - wh, q0 - wq), toLocal(p + off, h1 - wh, q1 - wq), toLocal(p + off, h1 + wh, q1 + wq), toLocal(p + off, h0 + wh, q0 + wq)];
          o.quad(pts, n, [[0, 0], [l, 0], [l, 0.16], [0, 0.16]], BuildingMat.Oak, L.timber);
        };
        // A collar and two struts leaning in under it: the gable's frame (no upright in the middle).
        const collar = y + rise * 0.45, half = Q * 0.55;
        post(-half, half, collar - 0.09, collar + 0.09);
        strut(-Q * 0.8, y + 0.1, -half * 0.45, collar - 0.09);
        strut(Q * 0.8, y + 0.1, half * 0.45, collar - 0.09);
        post(-Q, Q, y - 0.1, y + 0.1);
      }
      // A small window high in the gable that faces the street.
      if (detail && rise > 2.2) {
        const off = e * 0.03, h0 = y + rise * 0.3, h1 = h0 + 0.7;
        o.quad([toLocal(p + off, h0, -0.3), toLocal(p + off, h0, 0.3), toLocal(p + off, h1, 0.3), toLocal(p + off, h1, -0.3)], n, [[-0.3, h0], [0.3, h0], [0.3, h1], [-0.3, h1]], BuildingMat.Glass, WHITE);
      }
    }
    // The ridge.
    const rc = [toLocal(-P - verge, y + rise + 0.06, -0.14), toLocal(P + verge, y + rise + 0.06, -0.14), toLocal(P + verge, y + rise + 0.06, 0.14), toLocal(-P - verge, y + rise + 0.06, 0.14)];
    o.quad(rc, [0, 1, 0], [[-P, 0], [P, 0], [P, 0.28], [-P, 0.28]], m, tint);
  } else {
    // A hip roof: two trapezoids along the ridge and two triangles at the ends, all at one pitch.
    const ex = Q + eave, ridge = Math.max(0, P - Q);
    const tops: [number[][], number[]][] = [];
    for (const side of [-1, 1]) {
      const n = normalise([0, Q, side * rise]);
      tops.push([[toLocal(-P - eave, eaveY, side * ex), toLocal(P + eave, eaveY, side * ex), toLocal(ridge, y + rise, 0), toLocal(-ridge, y + rise, 0)], alongU ? [0, n[1], n[2]] : [n[2], n[1], 0]]);
    }
    for (const side of [-1, 1]) {
      const n = normalise([side * rise, Q, 0]);
      const nl = alongU ? [n[0], n[1], 0] : [0, n[1], n[0]];
      const apex = toLocal(side * ridge, y + rise, 0);
      const a = toLocal(side * (P + eave), eaveY, -ex), c = toLocal(side * (P + eave), eaveY, ex);
      o.tri([a, c, apex], nl, [[-ex, 0], [ex, 0], [0, Math.hypot(Q + eave, rise)]], m, tint);
      o.tri([a, c, apex].map((v) => [v[0], v[1] - thick, v[2]]), nl.map((v) => -v), [[-ex, 0], [ex, 0], [0, 1]], BuildingMat.Oak, L.timber);
    }
    for (const [p, n] of tops) {
      const slope = Math.hypot(Q + eave, rise);
      o.quad(p, n, [[-P, 0], [P, 0], [ridge, slope], [-ridge, slope]], m, tint);
      o.quad(p.map((v) => [v[0], v[1] - thick, v[2]]), n.map((v) => -v), [[-P, 0], [P, 0], [ridge, 1], [-ridge, 1]], BuildingMat.Oak, L.timber);
      o.quad([p[0], p[1], [p[1][0], p[1][1] - thick, p[1][2]], [p[0][0], p[0][1] - thick, p[0][2]]], [n[0], 0, n[2]], [[-P, 0], [P, 0], [P, thick], [-P, thick]], m, tint);
    }
  }
}

/** The roof's rise over the walls' top (m) for the rectangle front..back. */
function roofRise(b: TownBuilding, front: number, back: number): number {
  return (b.ridgeAlongU ? (back - front) / 2 : b.hu) * b.pitch;
}

/** The roof's top surface over (a, b) of a house (m over its floor), as `roof` draws it. */
export function roofAt(b: TownBuilding, S: HouseShape, a: number, bb: number): number {
  const alongU = b.ridgeAlongU;
  const P = alongU ? b.hu : (S.back - S.front) / 2, Q = alongU ? (S.back - S.front) / 2 : b.hu;
  const p = alongU ? a : bb - (S.front + S.back) / 2, q = alongU ? bb - (S.front + S.back) / 2 : a;
  const rise = Q * b.pitch;
  let h = rise - Math.abs(q) * b.pitch;
  if (b.roof === 'hip' && P > Q * 0.6) {
    // The hip ends fall from the ridge's ends to the eaves (steeper when the roof is about square).
    const ridge = Math.max(0, P - Q), e = eaveOf(b);
    h = Math.min(h, rise - Math.max(0, Math.abs(p) - ridge) * (rise + e * b.pitch) / (P + e - ridge));
  }
  return S.top + h;
}

/** How far the roof reaches out past the walls (m). */
function eaveOf(b: TownBuilding): number {
  return b.cover === 'thatch' ? 0.6 : 0.42;
}

/** A house's chimney stack: its middle, half width, and from where it comes out of the roof to its top. */
export function chimneyStack(b: TownBuilding, S: HouseShape = houseShape(b)): { a: number; b: number; half: number; y0: number; y1: number } | null {
  const c = S.chimney;
  if (!c) return null;
  const r = new Rng(b.seed ^ 0xc41e), half = 0.32;
  const y1 = S.top + roofRise(b, S.front, S.back) + r.range(0.7, 1.2);
  // From a little under the roof at the stack's lowest corner.
  let y0 = Infinity;
  for (const da of [-half, half]) for (const db of [-half, half]) y0 = Math.min(y0, roofAt(b, S, c.a + da, c.b + db));
  return { a: c.a, b: c.b, half, y0: y0 - 0.25, y1 };
}

/** The chimney's stack: from inside the roof up past the ridge, capped. */
function chimney(o: Out, b: TownBuilding, S: HouseShape, detail: boolean): void {
  const k = chimneyStack(b, S);
  if (!k) return;
  o.box(k.a - k.half, k.a + k.half, k.y0, k.y1, k.b - k.half, k.b + k.half, BuildingMat.Rubble, S.look.stone);
  if (detail) o.box(k.a - 0.4, k.a + 0.4, k.y1, k.y1 + 0.1, k.b - 0.4, k.b + 0.4, BuildingMat.Ashlar, S.look.stone, true);
}

function normalise(v: number[]): number[] {
  const l = Math.hypot(v[0], v[1], v[2]) || 1;
  return [v[0] / l, v[1] / l, v[2] / l];
}

// ---------------------------------------------------------------- the temple

function temple(o: Out, b: TownBuilding, S: HouseShape, r: Rng, detail: boolean, open: boolean): void {
  const { hu, hv } = b, L = S.look;
  const plinthDown = b.floorY - b.groundY + 0.3;
  const stone = BuildingMat.Ashlar;
  o.box(-hu - 0.15, hu + 0.15, -plinthDown, open ? 0 : 0.25, -hv - 0.15, hv + 0.15, BuildingMat.Rubble, L.stone);
  const H = b.floorH;
  for (const w of S.storeys[0].walls) wall(o, w.a0, w.b0, w.a1, w.b1, 0, H, w.opens, stone, L.stone, detail, L, false, r, open);
  roof(o, { ...b, ridgeAlongU: false, attached: false, roof: 'hip', kind: 'temple' } as TownBuilding, -hu, hu, -hv, hv, H, L, detail);
  portico(o, b, L, detail);
  // The sanctuary: a round drum rising out of the hall's middle, a ring of windows, a dome and a lantern.
  const s = b.sanctuary!;
  const n = 16, R = s.r;
  const ring = (rad: number, k: number): [number, number] => [Math.cos((k / n) * Math.PI * 2) * rad, Math.sin((k / n) * Math.PI * 2) * rad];
  for (let k = 0; k < n; k++) {
    const [a0, b0] = ring(R, k), [a1, b1] = ring(R, k + 1);
    const len = Math.hypot(a1 - a0, b1 - b0);
    const y0 = H - 0.6, opens: Opening[] = k % 2 === 0 ? [{ s0: len / 2 - 0.3, s1: len / 2 + 0.3, t0: s.h - y0 - 2.3, t1: s.h - y0 - 0.9 }] : [];
    wall(o, a0, b0, a1, b1, y0, s.h, opens, stone, L.stone, detail, L, false, r);
  }
  // A cornice ring, then the dome in bands (its rise is 0.9 of its radius).
  const cR = R + 0.25;
  if (detail) for (let k = 0; k < n; k++) {
    const [a0, b0] = ring(R, k), [a1, b1] = ring(R, k + 1), [c0, d0] = ring(cR, k), [c1, d1] = ring(cR, k + 1);
    const ma = (a0 + a1) / 2, mb = (b0 + b1) / 2, ml = Math.hypot(ma, mb) || 1;
    const seg = Math.hypot(c1 - c0, d1 - d0);
    o.quad([[c0, s.h, d0], [c1, s.h, d1], [c1, s.h + 0.3, d1], [c0, s.h + 0.3, d0]], [ma / ml, 0, mb / ml], [[0, 0], [seg, 0], [seg, 0.3], [0, 0.3]], stone, L.stone);
    o.quad([[a0, s.h + 0.3, b0], [a1, s.h + 0.3, b1], [c1, s.h + 0.3, d1], [c0, s.h + 0.3, d0]], [0, 1, 0], [[0, 0], [seg, 0], [seg, 0.25], [0, 0.25]], stone, L.stone);
  }
  const bands = detail ? 5 : 3, rise = R * 0.9, y0 = s.h + 0.3, lr = Math.max(0.7, R * 0.2);
  const dome = BuildingMat.Slate;
  const at = (i: number): [number, number] => {
    // From the base to the lantern's foot: a quarter ellipse.
    const t = (i / bands) * Math.acos(lr / R);
    return [Math.cos(t) * R, y0 + Math.sin(t) * rise];
  };
  for (let i = 0; i < bands; i++) {
    const [r0, h0] = at(i), [r1, h1] = at(i + 1);
    const sl = Math.hypot(r0 - r1, h1 - h0);
    for (let k = 0; k < n; k++) {
      const [a0, b0] = ring(1, k), [a1, b1] = ring(1, k + 1);
      const ma = (a0 + a1) / 2, mb = (b0 + b1) / 2, ml = Math.hypot(ma, mb);
      const nrm = normalise([(ma / ml) * (h1 - h0), r0 - r1, (mb / ml) * (h1 - h0)]);
      const w0 = Math.hypot(a1 - a0, b1 - b0) * r0, w1 = Math.hypot(a1 - a0, b1 - b0) * r1;
      o.quad([[a0 * r0, h0, b0 * r0], [a1 * r0, h0, b1 * r0], [a1 * r1, h1, b1 * r1], [a0 * r1, h1, b0 * r1]], nrm, [[0, i * sl], [w0, i * sl], [(w0 + w1) / 2, (i + 1) * sl], [(w0 - w1) / 2, (i + 1) * sl]], dome, DOME);
    }
  }
  // The lantern: a small open drum of posts with a cap and a finial.
  const [, ly] = at(bands);
  const lh = 1.1 + R * 0.08;
  if (detail) for (let k = 0; k < 6; k++) {
    const t = (k / 6) * Math.PI * 2, px = Math.cos(t) * (lr - 0.12), pz = Math.sin(t) * (lr - 0.12);
    o.box(px - 0.1, px + 0.1, ly, ly + lh, pz - 0.1, pz + 0.1, stone, L.stone);
  } else o.box(-lr * 0.8, lr * 0.8, ly, ly + lh, -lr * 0.8, lr * 0.8, stone, L.stone);
  o.box(-lr - 0.1, lr + 0.1, ly + lh, ly + lh + 0.25, -lr - 0.1, lr + 0.1, stone, L.stone, true);
  o.box(-lr * 0.55, lr * 0.55, ly + lh + 0.25, ly + lh + 0.65, -lr * 0.55, lr * 0.55, dome, DOME);
  o.box(-0.12, 0.12, ly + lh + 0.65, ly + lh + 1.4, -0.12, 0.12, stone, L.stone);
}

/** The dome's tint over slate: weathered copper green. */
const DOME: RGB = [150, 200, 178];

/** The temple's porch: columns before the door under a low pediment. */
function portico(o: Out, b: TownBuilding, L: Look, detail: boolean): void {
  const stone = BuildingMat.Ashlar, { w, f0, f1, top, cols } = porch(b, detail), d = f1 - f0;
  // The porch floor and its steps (also far off: they carry the columns).
  drawEntrance(o, b, L);
  for (const a of cols) o.box(a - 0.25, a + 0.25, 0.25, top, f0 + 0.1, f0 + 0.6, stone, L.stone);
  // The beam, then the pediment: a front triangle and two slopes back to the hall.
  o.box(-w - 0.2, w + 0.2, top, top + 0.55, f0, f1, stone, L.stone, true);
  const y = top + 0.55, rise = (w + 0.2) * 0.38, e = w + 0.3;
  o.tri([[-e, y, f0 - 0.05], [e, y, f0 - 0.05], [0, y + rise, f0 - 0.05]], [0, 0, -1], [[-e, 0], [e, 0], [0, rise]], stone, L.stone);
  const sl = Math.hypot(e, rise), m = b.cover === 'tile' ? BuildingMat.Tile : BuildingMat.Slate;
  for (const side of [-1, 1]) {
    o.quad([[side * e, y, f0 - 0.1], [0, y + rise, f0 - 0.1], [0, y + rise, f1 + 0.5], [side * e, y, f1 + 0.5]], normalise([side * rise, e, 0]), [[0, 0], [sl, 0], [sl, d + 0.6], [0, d + 0.6]], m, WHITE);
  }
}
