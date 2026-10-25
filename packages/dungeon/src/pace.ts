/**
 * The tension curve (plan "pacing"): the intended walk from the entrance to the goal (fetching keys on
 * the way), and along it a quiet entrance with foreshadowing, rising danger, one safe spot, a reveal,
 * the climax, and a shortcut back out.
 */
import { across, type DungeonGraph, type Link } from './graph';

export type Beat = 'entrance' | 'foreshadow' | 'build' | 'safe' | 'reveal' | 'climax' | 'exit' | 'side';

export interface Pace {
  /** The walk in, room by room (rooms may repeat when a key is fetched); empty if the goal can't be reached. */
  readonly route: number[];
  /** Per room: 0 calm .. 1 the climax. */
  readonly tension: number[];
  readonly beat: Beat[];
  /** The safe spot (-1 if none could be found). */
  readonly safe: number;
  /** Where the goal is first seen or sensed. */
  readonly reveal: number;
  /** The way back out from the goal, room by room, once the route is done. */
  readonly exit: number[];
  /** The way out is clearly shorter than the way in, or uses a shortcut (a barred door, a hidden way). */
  readonly shortcut: boolean;
  /** The goal could only be reached through a secret way. */
  readonly needsSecret: boolean;
}

/** Can `l` be walked from `from`, holding the keys in `held`? */
function passable(l: Link, from: number, held: (key: number) => boolean, secrets: boolean, opened?: Set<number>): boolean {
  switch (l.kind) {
    case 'open': case 'door': return true;
    case 'locked': return l.key === undefined || held(l.key);
    case 'secret': return secrets;
    case 'oneway': return from === l.a || !!opened?.has(l.id);
    case 'drop': return from === l.a;
    default: return false;
  }
}

/** Shortest walk entrance → goal; state = room + keys picked up. */
function walk(g: DungeonGraph, secrets: boolean): number[] {
  const keys = [...new Set(g.links.filter((l) => l.kind === 'locked' && l.key !== undefined).map((l) => l.key!))];
  const bit = (room: number) => { const i = keys.indexOf(room); return i < 0 ? 0 : 1 << i; };
  const n = g.rooms.length, start = g.entrance * 64 + bit(g.entrance);
  const prev = new Map<number, number>([[start, -1]]);
  const q = [start];
  let end = -1;
  for (let h = 0; h < q.length && end < 0; h++) {
    const s = q[h], room = Math.floor(s / 64), mask = s % 64;
    if (room === g.goal) { end = s; break; }
    for (const l of g.links) {
      if (l.a !== room && l.b !== room) continue;
      if (!passable(l, room, (k) => (mask & bit(k)) !== 0, secrets)) continue;
      const to = across(l, room), ns = to * 64 + (mask | bit(to));
      if (!prev.has(ns)) { prev.set(ns, s); q.push(ns); }
    }
  }
  if (end < 0 || n === 0) return [];
  const out: number[] = [];
  for (let s = end; s >= 0; s = prev.get(s)!) out.push(Math.floor(s / 64));
  return out.reverse();
}

/** Plain BFS over links that pass `ok`; returns the path from `from` to the first room in `to`. */
function bfs(g: DungeonGraph, from: number, isGoal: (r: number) => boolean, ok: (l: Link, from: number) => boolean): number[] {
  const prev = new Map<number, number>([[from, -1]]);
  const q = [from];
  for (let h = 0; h < q.length; h++) {
    const r = q[h];
    if (isGoal(r)) {
      const out: number[] = [];
      for (let x = r; x >= 0; x = prev.get(x)!) out.push(x);
      return out.reverse();
    }
    for (const l of g.links) {
      if ((l.a !== r && l.b !== r) || !ok(l, r)) continue;
      const to = across(l, r);
      if (!prev.has(to)) { prev.set(to, r); q.push(to); }
    }
  }
  return [];
}

export function pace(g: DungeonGraph): Pace {
  const n = g.rooms.length;
  let route = walk(g, false), needsSecret = false;
  if (!route.length) { route = walk(g, true); needsSecret = route.length > 0; }
  const tension = new Array<number>(n).fill(0), beat = new Array<Beat>(n).fill('side');
  if (!route.length) return { route, tension, beat, safe: -1, reveal: -1, exit: [], shortcut: false, needsSecret };

  // Along the route: first visits rise towards the climax.
  const firsts: number[] = [];
  for (const r of route) if (!firsts.includes(r)) firsts.push(r);
  const pos = new Array<number>(n).fill(-1);
  firsts.forEach((r, i) => { pos[r] = firsts.length > 1 ? i / (firsts.length - 1) : 1; });
  for (const r of firsts) { tension[r] = 0.08 + 0.92 * Math.pow(pos[r], 1.25); beat[r] = 'build'; }

  // Rooms off the route take a little less than the route room they hang off.
  const anyWay = (l: Link) => l.kind !== 'grate' && l.kind !== 'blocked';
  for (let r = 0; r < n; r++) {
    if (pos[r] >= 0) continue;
    const p = bfs(g, r, (x) => pos[x] >= 0, anyWay);
    const at = p.length ? p[p.length - 1] : g.entrance;
    tension[r] = tension[at] * 0.85;
  }

  // Exit: everything opened on the way in; secrets known.
  const opened = new Set<number>();
  for (let i = 1; i < route.length; i++) {
    const a = route[i - 1], b = route[i];
    for (const l of g.links) if (l.kind === 'oneway' && l.a === a && l.b === b) opened.add(l.id);
  }
  const exit = bfs(g, g.goal, (r) => r === g.entrance, (l, from) => passable(l, from, () => true, true, opened));
  const usesShortcut = exit.some((r, i) => i > 0 && g.links.some((l) => (l.kind === 'oneway' || l.kind === 'secret' || l.tags.includes('shortcut')) && ((l.a === exit[i - 1] && l.b === r) || (l.b === exit[i - 1] && l.a === r))));
  const shortcut = exit.length > 0 && (usesShortcut || exit.length - 1 < (route.length - 1) * 0.75);
  for (const r of exit) if (pos[r] < 0) { beat[r] = 'exit'; tension[r] = 0.2; }

  // Beats.
  beat[g.entrance] = 'entrance'; tension[g.entrance] = 0.05;
  if (firsts.length > 2) beat[firsts[1]] = 'foreshadow';
  beat[g.goal] = 'climax'; tension[g.goal] = 1;
  let reveal = -1;
  for (const r of firsts) {
    if (r === g.goal) break;
    if (g.links.some((l) => (l.kind === 'grate' || l.kind === 'drop') && ((l.a === r && l.b === g.goal) || (l.b === r && l.a === g.goal)))) { reveal = r; break; }
  }
  if (reveal < 0 && firsts.length > 2) reveal = firsts[firsts.length - 2];
  if (reveal >= 0 && reveal !== g.entrance) { beat[reveal] = 'reveal'; tension[reveal] = Math.max(tension[reveal], 0.8); }

  // Safe spot: a dead end off the route around the middle; else a route room there.
  const degree = (r: number) => g.links.filter((l) => (l.a === r || l.b === r) && anyWay(l)).length;
  let safe = -1, best = Infinity;
  for (let r = 0; r < n; r++) {
    if (pos[r] >= 0 || beat[r] !== 'side' || degree(r) !== 1) continue;
    const p = bfs(g, r, (x) => pos[x] >= 0, anyWay);
    const at = p.length ? pos[p[p.length - 1]] : 0;
    if (at < 0.25 || at > 0.85) continue;
    const d = Math.abs(at - 0.6);
    if (d < best) { best = d; safe = r; }
  }
  if (safe < 0) for (const r of firsts) {
    if (beat[r] !== 'build' && beat[r] !== 'foreshadow') continue;
    const d = Math.abs(pos[r] - 0.55);
    if (pos[r] >= 0.3 && pos[r] <= 0.8 && d < best) { best = d; safe = r; }
  }
  if (safe >= 0) { beat[safe] = 'safe'; tension[safe] = 0.12; }
  return { route, tension, beat, safe, reveal, exit, shortcut, needsSecret };
}
