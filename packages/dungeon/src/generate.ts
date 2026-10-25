/**
 * A dungeon graph from cycles: one main cycle from the entrance to the goal, then a few more cycles
 * inserted into its passages, then a shortcut back out if none of them made one.
 */
import { Rng } from '@futuremagic/core';
import { GraphBuilder, type DungeonGraph, type RoomSize } from './graph';
import { pace } from './pace';
import { PATTERNS, patternById, type CyclePattern, type PatternContext } from './patterns';

export interface GraphSpec {
  /** Patterns allowed for the main cycle (ids). */
  readonly main: readonly string[];
  /** Patterns allowed for the inserted cycles (ids). */
  readonly inserts: readonly string[];
  /** How many cycles to insert, at least and at most. */
  readonly insertCount: readonly [number, number];
  /** Most rooms in all. */
  readonly maxRooms: number;
  /** Deepest storey (0: one storey only). */
  readonly minLevel: number;
  /** The entrance room's size. */
  readonly entranceSize?: RoomSize;
  /** The library to draw from (default: PATTERNS). */
  readonly library?: readonly CyclePattern[];
  /** Weight per pattern id (default 1), e.g. to prefer patterns not used lately. */
  readonly weight?: (id: string) => number;
}

export function cyclicGraph(spec: GraphSpec, seed: number): DungeonGraph {
  const rng = new Rng(seed);
  const lib = spec.library ?? PATTERNS;
  const b = new GraphBuilder();
  const c: PatternContext = { b, rng, minLevel: spec.minLevel };
  const used: string[] = [];
  const fits = (p: CyclePattern, s: number) => (!p.descends || b.rooms[s].level - 1 >= spec.minLevel) && b.rooms.length + p.rooms <= spec.maxRooms;
  const choose = (ids: readonly string[], s: number): CyclePattern | null => {
    const ok = ids.map((id) => patternById(id, lib)).filter((p) => fits(p, s));
    if (!ok.length) return null;
    return rng.weighted(ok, (p) => (spec.weight?.(p.id) ?? 1) * (used.includes(p.id) ? 0.15 : 1));
  };

  const entrance = b.room(0, spec.entranceSize ?? 'medium', ['entrance']);
  const main = choose(spec.main, entrance);
  if (!main) throw new Error('no main cycle pattern fits the spec');
  const goal = main.build(c, entrance);
  b.tag(goal, 'goal');
  used.push(main.id);

  const inserts = rng.int(spec.insertCount[0], spec.insertCount[1]);
  for (let i = 0; i < inserts; i++) {
    const spots = b.links.filter((l) => (l.kind === 'open' || l.kind === 'door') && !l.tags.includes('stairs') && l.b !== goal);
    if (!spots.length) break;
    const at = rng.pick(spots);
    const p = choose(spec.inserts, at.a);
    if (!p) break;
    b.remove(at);
    const t = p.build(c, at.a);
    b.link(t, at.b, at.kind, at.tags);
    used.push(p.id);
  }

  let g: DungeonGraph = { rooms: b.rooms, links: b.links, entrance, goal, patterns: used };
  if (!pace(g).shortcut) {
    // A door near the entrance, barred from the inside, that the goal's side can open.
    const route = pace(g).route;
    const near = route.find((r) => r !== entrance && b.rooms[r].level === b.rooms[goal].level && r !== goal) ?? entrance;
    b.link(goal, near, 'oneway', ['shortcut']);
    g = { ...g, patterns: [...g.patterns, 'shortcut'] };
  }
  const p = pace(g);
  if (p.safe < 0) {
    // A quiet nook off the way, about halfway.
    const firsts = [...new Set(p.route)];
    const at = firsts[Math.max(1, Math.round(firsts.length * 0.55) - 1)] ?? entrance;
    const nook = b.room(b.rooms[at].level, 'nook', ['refuge']);
    b.link(at, nook, 'door');
    g = { ...g, patterns: [...g.patterns, 'refuge'] };
  }
  return g;
}
