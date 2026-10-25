/**
 * The graph laid out in space: rooms as rectangles of grid cells on storeys, links as passages of cells
 * found by A* (with stairs between storeys), tall rooms entered from above over a ledge. Units are
 * cells; the game chooses how many metres a cell and a storey are.
 *
 * Rooms are placed one by one next to a room they link to (breadth first from the entrance); the links
 * that close the cycles are routed afterwards. A layout that cannot close every cycle is thrown away
 * and tried again with the next random numbers.
 */
import { MinHeap, Rng } from '@futuremagic/core';
import type { DungeonGraph, Link, Room } from './graph';

/** +x, +z, -x, -z. */
export const DIRS: readonly (readonly [number, number])[] = [[1, 0], [0, 1], [-1, 0], [0, -1]];

export interface PlacedRoom {
  readonly id: number;
  readonly x: number;
  readonly z: number;
  readonly w: number;
  readonly d: number;
  readonly level: number;
  readonly height: 1 | 2;
}

export interface PathCell {
  readonly x: number;
  readonly z: number;
  /** For stairs: the upper storey. */
  readonly level: number;
  /** Stairs: the floor falls by one storey over `run` cells along `dir`; this is step `step` (0 = top). */
  readonly stair?: { readonly dir: number; readonly step: number; readonly run: number };
}

/** A door: in the wall on side `dir` of the cell (x, z, level) that belongs to `room`. */
export interface Door {
  readonly room: number;
  readonly x: number;
  readonly z: number;
  readonly level: number;
  readonly dir: number;
}

export interface PlacedLink {
  readonly link: Link;
  /** Cells between the rooms (empty when the rooms share a wall). */
  readonly path: PathCell[];
  /** The opening into `a` and the one into `b` (the same door when the path is empty). */
  readonly doors: readonly [Door, Door];
}

export interface DungeonLayout {
  readonly rooms: PlacedRoom[];
  readonly links: PlacedLink[];
  /** Storeys used, lowest and highest. */
  readonly levels: readonly [number, number];
  /** Tries it took. */
  readonly tries: number;
}

export interface LayoutOptions {
  /** Cells per room, width and depth (default by size class: nook 2, small 2–3, medium 3–4, large 4–6). */
  readonly size?: (room: Room, rng: Rng) => readonly [number, number];
  /** The entrance's rectangle in cells (e.g. the house above); default centred on 0, 0. */
  readonly entrance?: { readonly x: number; readonly z: number; readonly w: number; readonly d: number };
  /** Half extent of the grid around 0, 0, cells (default 24). */
  readonly radius?: number;
  /** Cells of stairs per storey (default 2). */
  readonly stairRun?: number;
  /** Longest passage between a room and the one it was placed next to, cells (default 8). */
  readonly maxPath?: number;
  /** Whole layouts tried before giving up (default 30). */
  readonly attempts?: number;
}

const SIZES: Record<Room['size'], readonly [number, number]> = { nook: [2, 2], small: [2, 3], medium: [3, 4], large: [4, 6] };

export function defaultRoomSize(room: Room, rng: Rng): [number, number] {
  const [lo, hi] = SIZES[room.size];
  return [rng.int(lo, hi), rng.int(lo, hi)];
}

/** Lays out a graph; null if no layout closed every cycle within the attempts. */
export function layoutDungeon(g: DungeonGraph, seed: number, opts: LayoutOptions = {}): DungeonLayout | null {
  const rng = new Rng(seed);
  const attempts = opts.attempts ?? 30;
  for (let i = 0; i < attempts; i++) {
    const out = tryLayout(g, rng, opts);
    if (out) return { ...out, tries: i + 1 };
  }
  return null;
}

const key = (x: number, z: number, l: number) => `${x},${z},${l}`;

/** Which room or passage each cell belongs to. */
export class LayoutGrid {
  /** >= 0: a room id; < 0: -1 - index into layout.links. */
  readonly cells = new Map<string, number>();
  /** Stair cells, by the key of their upper cell and of the one below. */
  readonly stairs = new Map<string, PathCell>();

  constructor(layout?: DungeonLayout) {
    if (!layout) return;
    for (const r of layout.rooms) this.addRoom(r);
    layout.links.forEach((pl, i) => this.addPath(pl.path, i));
  }

  owner(x: number, z: number, l: number): number | undefined {
    return this.cells.get(key(x, z, l));
  }

  free(x: number, z: number, l: number): boolean {
    return !this.cells.has(key(x, z, l));
  }

  addRoom(r: PlacedRoom): void {
    for (let l = r.level; l < r.level + r.height; l++)
      for (let z = r.z; z < r.z + r.d; z++) for (let x = r.x; x < r.x + r.w; x++) this.cells.set(key(x, z, l), r.id);
  }

  addPath(path: readonly PathCell[], index: number): void {
    for (const c of path) {
      this.cells.set(key(c.x, c.z, c.level), -1 - index);
      if (c.stair) {
        this.cells.set(key(c.x, c.z, c.level - 1), -1 - index);
        this.stairs.set(key(c.x, c.z, c.level), c);
        this.stairs.set(key(c.x, c.z, c.level - 1), c);
      }
    }
  }
}

/** Storeys a link may open into a room on: a drop enters a tall room over its ledge, a grate may look in from above. */
function doorLevels(room: PlacedRoom, link: Link, end: 'a' | 'b'): number[] {
  if (link.kind === 'drop' && end === 'b') return room.height === 2 ? [room.level + 1] : [];
  if (link.kind === 'grate' && room.height === 2) return [room.level, room.level + 1];
  return [room.level];
}

function tryLayout(g: DungeonGraph, rng: Rng, opts: LayoutOptions): Omit<DungeonLayout, 'tries'> | null {
  const R = opts.radius ?? 24, run = opts.stairRun ?? 2, maxPath = opts.maxPath ?? 8;
  const sizeOf = opts.size ?? defaultRoomSize;
  const grid = new LayoutGrid();
  const placed: (PlacedRoom | undefined)[] = new Array(g.rooms.length);
  const links: PlacedLink[] = [];
  const done = new Set<number>();
  let lo = 0, hi = 0;
  for (const r of g.rooms) { lo = Math.min(lo, r.level); hi = Math.max(hi, r.level + r.height - 1); }

  const inBounds = (x: number, z: number) => x >= -R && x < R && z >= -R && z < R;

  const place = (room: Room, x: number, z: number, w: number, d: number) => {
    const p: PlacedRoom = { id: room.id, x, z, w, d, level: room.level, height: room.height };
    placed[room.id] = p;
    grid.addRoom(p);
  };

  /** Room fits: its cells free and in bounds, and no other room touching it (except `beside`). */
  const fits = (room: Room, x: number, z: number, w: number, d: number, beside: number) => {
    for (let l = room.level; l < room.level + room.height; l++)
      for (let zz = z - 1; zz <= z + d; zz++) for (let xx = x - 1; xx <= x + w; xx++) {
        const inside = xx >= x && xx < x + w && zz >= z && zz < z + d;
        if (inside && !inBounds(xx, zz)) return false;
        const o = grid.owner(xx, zz, l);
        if (o === undefined) continue;
        if (inside) return false;
        if (o >= 0 && o !== beside) return false;
      }
    return true;
  };

  const connect = (link: Link, limit: number): boolean => {
    const A = placed[link.a]!, B = placed[link.b]!;
    const la = doorLevels(A, link, 'a'), lb = doorLevels(B, link, 'b');
    // Sharing a wall: a door straight through.
    const direct: Door[] = [];
    for (const l of la) {
      if (!lb.includes(l)) continue;
      for (let z = A.z; z < A.z + A.d; z++) for (let x = A.x; x < A.x + A.w; x++) for (let k = 0; k < 4; k++) {
        const nx = x + DIRS[k][0], nz = z + DIRS[k][1];
        if (grid.owner(nx, nz, l) === B.id && !(nx >= A.x && nx < A.x + A.w && nz >= A.z && nz < A.z + A.d)) direct.push({ room: A.id, x, z, level: l, dir: k });
      }
    }
    if (direct.length) {
      const da = direct[Math.floor(direct.length / 2)];
      const db: Door = { room: B.id, x: da.x + DIRS[da.dir][0], z: da.z + DIRS[da.dir][1], level: da.level, dir: (da.dir + 2) % 4 };
      links.push({ link, path: [], doors: [da, db] });
      return true;
    }
    const found = route(grid, A, la, B, lb, run, inBounds, limit, rng, lo, hi);
    if (!found) return false;
    links.push({ link, path: found.path, doors: [found.from, found.to] });
    grid.addPath(found.path, links.length - 1);
    return true;
  };

  // The entrance first.
  const E = g.rooms[g.entrance];
  if (opts.entrance) place(E, opts.entrance.x, opts.entrance.z, opts.entrance.w, opts.entrance.d);
  else { const [w, d] = sizeOf(E, rng); place(E, -(w >> 1), -(d >> 1), w, d); }

  // Depth first along the loops, so a loop's far side is placed coming back towards where it started;
  // each room beside a placed room it links to, as near as fits to its other placed neighbours.
  const pref: Link['kind'][] = ['open', 'door', 'locked', 'oneway', 'drop', 'secret', 'grate', 'blocked'];
  const order: number[] = [];
  const visit = (r: number) => {
    order.push(r);
    const next = g.links.filter((l) => l.a === r || l.b === r).sort((p, q) => pref.indexOf(p.kind) - pref.indexOf(q.kind));
    for (const l of next) { const o = l.a === r ? l.b : l.a; if (!order.includes(o)) visit(o); }
  };
  visit(g.entrance);
  if (order.length < g.rooms.length) return null;
  const gapTo = (a: { x: number; z: number; w: number; d: number }, b: PlacedRoom) =>
    Math.max(0, b.x - (a.x + a.w), a.x - (b.x + b.w)) + Math.max(0, b.z - (a.z + a.d), a.z - (b.z + b.d));
  for (const id of order.slice(1)) {
    const room = g.rooms[id];
    const cand = g.links.filter((l) => (l.a === id && placed[l.b]) || (l.b === id && placed[l.a]));
    cand.sort((p, q) => pref.indexOf(p.kind) - pref.indexOf(q.kind));
    const link = cand[0];
    const parent = placed[link.a === id ? link.b : link.a]!;
    const others = cand.slice(1).map((l) => placed[l.a === id ? l.b : l.a]!);
    const [w, d] = sizeOf(room, rng);
    const levelGap = Math.abs(room.level - parent.level) - (link.kind === 'drop' || link.kind === 'grate' ? 1 : 0);
    const minGap = levelGap > 0 ? run + 2 : 0;
    const spots: { x: number; z: number; gap: number; score: number }[] = [];
    for (let t = 0; t < 60 && spots.length < 8; t++) {
      const side = rng.int(0, 3), gap = minGap + rng.int(0, t < 20 ? 1 : 3);
      let x: number, z: number;
      if (side === 0) { x = parent.x + parent.w + gap; z = parent.z + rng.int(-(d - 1), parent.d - 1); }
      else if (side === 2) { x = parent.x - gap - w; z = parent.z + rng.int(-(d - 1), parent.d - 1); }
      else if (side === 1) { z = parent.z + parent.d + gap; x = parent.x + rng.int(-(w - 1), parent.w - 1); }
      else { z = parent.z - gap - d; x = parent.x + rng.int(-(w - 1), parent.w - 1); }
      if (!fits(room, x, z, w, d, gap === 0 ? parent.id : -1)) continue;
      const near = others.reduce((sum, o) => sum + gapTo({ x, z, w, d }, o), 0);
      spots.push({ x, z, gap, score: near + gap * 0.5 + rng.float() * 2 });
    }
    spots.sort((p, q) => p.score - q.score);
    let ok = false;
    for (const sp of spots) {
      place(room, sp.x, sp.z, w, d);
      if (connect(link, maxPath)) { done.add(link.id); ok = true; break; }
      unplace(grid, placed, room);
    }
    if (!ok) return null;
  }

  // Close the cycles.
  for (const l of g.links) if (!done.has(l.id) && !connect(l, maxPath * 2)) return null;
  return { rooms: placed as PlacedRoom[], links, levels: [lo, hi] };
}

function unplace(grid: LayoutGrid, placed: (PlacedRoom | undefined)[], room: Room): void {
  const p = placed[room.id]!;
  for (let l = p.level; l < p.level + p.height; l++)
    for (let z = p.z; z < p.z + p.d; z++) for (let x = p.x; x < p.x + p.w; x++) grid.cells.delete(key(x, z, l));
  placed[room.id] = undefined;
}

/**
 * A* over free cells from beside room A to beside room B. State: cell and heading (turns cost a little,
 * so passages run straight like built ones). Stairs: `run` cells free on both storeys, then a landing.
 */
function route(grid: LayoutGrid, A: PlacedRoom, la: number[], B: PlacedRoom, lb: number[], run: number,
  inBounds: (x: number, z: number) => boolean, limit: number, rng: Rng, lo: number, hi: number): { path: PathCell[]; from: Door; to: Door } | null {
  type Node = { x: number; z: number; l: number; dir: number; g: number; prev: number; stair?: number; door?: Door };
  const nodes: Node[] = [];
  const best = new Map<string, number>();
  const heap = new MinHeap();
  const bx = B.x + B.w / 2, bz = B.z + B.d / 2, bl = lb[0];
  const h = (x: number, z: number, l: number) => Math.max(0, Math.abs(x - bx) - B.w / 2) + Math.max(0, Math.abs(z - bz) - B.d / 2) + Math.abs(l - bl) * run;
  const jitter = rng.float() * 0.01;
  const push = (n: Node) => {
    const k = `${n.x},${n.z},${n.l},${n.dir}`;
    const old = best.get(k);
    if (old !== undefined && nodes[old].g <= n.g) return;
    nodes.push(n);
    best.set(k, nodes.length - 1);
    heap.push(n.g + h(n.x, n.z, n.l) * (1 + jitter), nodes.length - 1);
  };
  const free = (x: number, z: number, l: number) => inBounds(x, z) && grid.free(x, z, l);
  // Sources: free cells outside A's walls (not at its corners).
  for (const l of la) for (let z = A.z; z < A.z + A.d; z++) for (let x = A.x; x < A.x + A.w; x++) for (let k = 0; k < 4; k++) {
    const nx = x + DIRS[k][0], nz = z + DIRS[k][1];
    if (nx >= A.x && nx < A.x + A.w && nz >= A.z && nz < A.z + A.d) continue;
    if (!free(nx, nz, l)) continue;
    push({ x: nx, z: nz, l, dir: k, g: 0, prev: -1, door: { room: A.id, x, z, level: l, dir: k } });
  }
  const intoB = (x: number, z: number, l: number): Door | null => {
    if (!lb.includes(l)) return null;
    for (let k = 0; k < 4; k++) {
      const nx = x + DIRS[k][0], nz = z + DIRS[k][1];
      if (grid.owner(nx, nz, l) === B.id && (l === B.level || l === B.level + 1)) return { room: B.id, x: nx, z: nz, level: l, dir: (k + 2) % 4 };
    }
    return null;
  };
  while (heap.size) {
    const i = heap.pop();
    const n = nodes[i];
    if (best.get(`${n.x},${n.z},${n.l},${n.dir}`) !== i) continue;
    if (n.g > limit + run * 3) continue;
    const to = intoB(n.x, n.z, n.l);
    if (to) {
      const path: PathCell[] = [];
      let from: Door | undefined;
      for (let j = i; j >= 0; j = nodes[j].prev) {
        const m = nodes[j];
        if (m.stair !== undefined) {
          // A stair move: the steps between the previous cell and this landing.
          const p = nodes[m.prev], up = m.l > p.l, top = up ? m.l : p.l;
          const steps: PathCell[] = [];
          for (let s = 1; s <= run; s++) steps.push({ x: p.x + DIRS[m.dir][0] * s, z: p.z + DIRS[m.dir][1] * s, level: top, stair: { dir: up ? (m.dir + 2) % 4 : m.dir, step: up ? run - s : s - 1, run } });
          path.push({ x: m.x, z: m.z, level: m.l }, ...steps.reverse());
        } else path.push({ x: m.x, z: m.z, level: m.l });
        if (m.door) from = m.door;
      }
      path.reverse();
      return path.length <= limit + run * 2 ? { path, from: from!, to } : null;
    }
    for (let k = 0; k < 4; k++) {
      if (k === (n.dir + 2) % 4) continue;
      const turn = k === n.dir ? 0 : 0.6;
      const nx = n.x + DIRS[k][0], nz = n.z + DIRS[k][1];
      if (free(nx, nz, n.l)) push({ x: nx, z: nz, l: n.l, dir: k, g: n.g + 1 + turn, prev: i });
      // Stairs down or up: run cells free on both storeys, then a landing on the other.
      for (const dl of [-1, 1]) {
        const l2 = n.l + dl;
        if (l2 > hi || l2 < lo) continue;
        let clear = true;
        for (let s = 1; s <= run && clear; s++) {
          const sx = n.x + DIRS[k][0] * s, sz = n.z + DIRS[k][1] * s;
          clear = free(sx, sz, n.l) && free(sx, sz, l2);
        }
        const lx = n.x + DIRS[k][0] * (run + 1), lz = n.z + DIRS[k][1] * (run + 1);
        if (clear && free(lx, lz, l2)) push({ x: lx, z: lz, l: l2, dir: k, g: n.g + run * 2 + 1 + turn, prev: i, stair: dl });
      }
    }
  }
  return null;
}
