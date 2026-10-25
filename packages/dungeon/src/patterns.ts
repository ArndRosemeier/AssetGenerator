/**
 * The cycle library (after Dormans' cyclic generation in *Unexplored*): each pattern grows a loop from a
 * room `s` to a new room `t` it makes. A dungeon is one main cycle (from the entrance to the goal) with
 * two or three more cycles inserted into its passages. Patterns tag what they make, so the game can
 * dress it ('key', 'lock', 'view', 'ledge', 'dug', 'shortcut', ...).
 *
 * The library grows with each new dungeon kind; games pick which patterns fit (a cellar has no chasms).
 */
import type { Rng } from '@futuremagic/core';
import type { GraphBuilder } from './graph';

export interface PatternContext {
  readonly b: GraphBuilder;
  readonly rng: Rng;
  /** The deepest storey allowed. */
  readonly minLevel: number;
}

export interface CyclePattern {
  readonly id: string;
  /** What the player meets, in a line. */
  readonly about: string;
  /** Rooms it adds at most (t included). */
  readonly rooms: number;
  /** Goes one storey below `s`. */
  readonly descends?: boolean;
  /** Builds the loop from `s`; returns the new room `t`. */
  build(c: PatternContext, s: number): number;
}

const lvl = (c: PatternContext, r: number) => c.b.rooms[r].level;

export const PATTERNS: readonly CyclePattern[] = [
  {
    id: 'twin-paths', about: 'two ways to the same place', rooms: 5,
    build(c, s) {
      const { b, rng } = c, t = b.room(lvl(c, s), 'medium');
      b.link(b.chain(s, rng.int(1, 2), 'small'), t, 'door');
      b.link(b.chain(s, rng.int(1, 2), 'small'), t, 'open');
      return t;
    },
  },
  {
    id: 'lock-key', about: 'a locked door; its key lies around a loop that comes out behind it', rooms: 5,
    build(c, s) {
      const { b, rng } = c, L = lvl(c, s), t = b.room(L, 'medium');
      const k = b.room(L, 'small', ['key']);
      b.link(b.chain(s, rng.int(0, 1), 'small'), t, 'locked', ['lock'], k);
      b.link(b.chain(s, rng.int(1, 2), 'small'), k, 'door');
      b.link(t, k, 'oneway', ['shortcut']);
      return t;
    },
  },
  {
    id: 'hidden-shortcut', about: 'the long way round, and a hidden way straight back', rooms: 4,
    build(c, s) {
      const { b, rng } = c, t = b.room(lvl(c, s), 'medium');
      b.link(b.chain(s, rng.int(2, 3), 'small'), t, 'door');
      b.link(t, s, 'secret', ['shortcut']);
      return t;
    },
  },
  {
    id: 'seen-goal', about: 'the goal is seen through bars long before it is reached', rooms: 5,
    build(c, s) {
      const { b, rng } = c, t = b.room(lvl(c, s), 'medium');
      b.link(b.chain(s, rng.int(0, 1), 'small'), t, 'grate', ['view']);
      b.link(b.chain(s, rng.int(2, 3), 'small'), t, 'door');
      return t;
    },
  },
  {
    id: 'drop-in', about: 'a ledge over a tall hall: drop in, then find the way back up', rooms: 4, descends: true,
    build(c, s) {
      const { b, rng } = c, L = lvl(c, s);
      const t = b.room(L - 1, 'large', ['hall'], 2);
      const x = b.chain(s, 1, 'small', ['ledge']);
      b.link(x, t, 'drop', ['ledge', 'view']);
      const u = b.room(L - 1, 'small');
      b.link(t, u, 'open');
      const v = b.chain(u, rng.int(0, 1), 'small');
      if (rng.chance(0.5)) b.link(v, s, 'oneway', ['stairs', 'shortcut']);
      else b.link(v, s, 'open', ['stairs']);
      return t;
    },
  },
  {
    id: 'barred-return', about: 'a door barred on the far side opens the way back', rooms: 4,
    build(c, s) {
      const { b, rng } = c, t = b.room(lvl(c, s), 'medium');
      b.link(b.chain(s, rng.int(1, 2), 'small'), t, 'door');
      b.link(b.chain(t, 1, 'small'), s, 'oneway', ['shortcut']);
      return t;
    },
  },
  {
    id: 'collapsed-way', about: 'the old way fell in; something dug around it', rooms: 3,
    build(c, s) {
      const { b, rng } = c, t = b.room(lvl(c, s), 'medium');
      b.link(s, t, 'blocked', ['collapse']);
      b.link(b.chain(s, rng.int(1, 2), 'nook', ['dug'], 'open'), t, 'open', ['dug']);
      return t;
    },
  },
  {
    id: 'secret-key', about: 'the key to a locked door lies behind a hidden one', rooms: 4,
    build(c, s) {
      const { b, rng } = c, L = lvl(c, s), t = b.room(L, 'medium');
      const k = b.room(L, 'nook', ['key', 'hidden']);
      b.link(b.chain(s, rng.int(0, 1), 'small'), t, 'locked', ['lock'], k);
      b.link(b.chain(s, 1, 'small'), k, 'secret');
      b.link(k, s, 'oneway', ['shortcut']);
      return t;
    },
  },
  {
    id: 'gallery', about: 'a gallery looks down into a hall that is reached by stairs', rooms: 3, descends: true,
    build(c, s) {
      const { b } = c, L = lvl(c, s);
      const t = b.room(L - 1, 'large', ['hall'], 2);
      const g = b.room(L, 'small', ['gallery']);
      b.link(s, g, 'open');
      b.link(g, t, 'grate', ['view']);
      const u = b.room(L - 1, 'small');
      b.link(s, u, 'open', ['stairs']);
      b.link(u, t, 'door');
      return t;
    },
  },
  {
    id: 'side-loop', about: 'a little loop off the way with something for those who look', rooms: 4,
    build(c, s) {
      const { b } = c, L = lvl(c, s), t = b.room(L, 'medium');
      const m = b.chain(s, 1, 'small');
      b.link(m, t, 'door');
      const a = b.room(L, 'small', ['side']), r = b.room(L, 'nook', ['side', 'reward']);
      b.link(m, a, 'open');
      b.link(a, r, 'open');
      b.link(r, m, 'secret');
      return t;
    },
  },
  {
    id: 'guarded-short', about: 'a short way past danger or a long quiet one', rooms: 4,
    build(c, s) {
      const { b } = c, t = b.room(lvl(c, s), 'medium');
      b.link(b.chain(s, 1, 'small', ['guarded']), t, 'open', ['guarded']);
      b.link(b.chain(s, 2, 'small', ['quiet']), t, 'door');
      return t;
    },
  },
  {
    id: 'low-road', about: 'a way beneath: down, along and up again', rooms: 4, descends: true,
    build(c, s) {
      const { b, rng } = c, L = lvl(c, s), t = b.room(L, 'medium');
      b.link(b.chain(s, 1, 'small'), t, 'door');
      const u = b.room(L - 1, 'small', ['low']);
      b.link(s, u, 'open', ['stairs']);
      b.link(b.chain(u, rng.int(0, 1), 'small', ['low']), t, 'open', ['stairs']);
      return t;
    },
  },
  {
    id: 'false-goal', about: 'the way that looks right ends in a fall of rubble; the real way goes round', rooms: 4,
    build(c, s) {
      const { b, rng } = c, L = lvl(c, s), t = b.room(L, 'medium');
      const f = b.room(L, 'small', ['false']);
      b.link(s, f, 'open');
      b.link(f, t, 'blocked', ['collapse', 'false']);
      b.link(b.chain(s, rng.int(1, 2), 'small'), t, 'door');
      return t;
    },
  },
  {
    id: 'seen-key', about: 'the key is seen through bars from the locked door; the way to it goes round', rooms: 5,
    build(c, s) {
      const { b, rng } = c, L = lvl(c, s), t = b.room(L, 'medium');
      const x = b.chain(s, 1, 'small', ['lock']);
      const k = b.room(L, 'small', ['key']);
      b.link(x, t, 'locked', ['lock'], k);
      b.link(x, k, 'grate', ['view']);
      b.link(b.chain(s, rng.int(1, 2), 'small'), k, 'door');
      b.link(k, s, 'oneway', ['shortcut']);
      return t;
    },
  },
  {
    id: 'gambit', about: 'a guarded side room with something worth the risk, and a way on from it', rooms: 4,
    build(c, s) {
      const { b } = c, L = lvl(c, s), t = b.room(L, 'medium');
      const m = b.chain(s, 1, 'small');
      b.link(m, t, 'door');
      const g = b.room(L, 'small', ['guarded']), r = b.room(L, 'nook', ['reward']);
      b.link(m, g, 'open', ['guarded']);
      b.link(g, r, 'door');
      b.link(r, t, 'oneway', ['shortcut']);
      return t;
    },
  },
  {
    id: 'split-descent', about: 'two stairs down into the same lower hall', rooms: 3, descends: true,
    build(c, s) {
      const { b } = c, L = lvl(c, s);
      const t = b.room(L - 1, 'large', ['hall']);
      b.link(b.chain(s, 1, 'small'), t, 'open', ['stairs']);
      b.link(b.chain(s, 1, 'small'), t, 'open', ['stairs']);
      return t;
    },
  },
  {
    id: 'bolt-hole', about: 'the long way in through doors; the dwellers dug a bolt-hole straight back', rooms: 5,
    build(c, s) {
      const { b, rng } = c, L = lvl(c, s), t = b.room(L, 'medium');
      b.link(b.chain(s, rng.int(2, 3), 'small'), t, 'door');
      const n = b.room(L, 'nook', ['dug']);
      b.link(t, n, 'open', ['dug']);
      b.link(n, s, 'oneway', ['dug', 'shortcut']);
      return t;
    },
  },
  {
    id: 'ring-hall', about: 'a hall with rooms opening off it; the way on goes through one, and a barred door leads back', rooms: 4,
    build(c, s) {
      const { b } = c, L = lvl(c, s), t = b.room(L, 'medium');
      const h = b.room(L, 'large', ['hall']);
      b.link(s, h, 'open');
      const a = b.room(L, 'small');
      b.link(h, a, 'door');
      b.link(a, t, 'open');
      b.link(t, h, 'oneway', ['shortcut']);
      const n = b.room(L, 'nook', ['side', 'reward']);
      b.link(h, n, 'door');
      return t;
    },
  },

];

export function patternById(id: string, lib: readonly CyclePattern[] = PATTERNS): CyclePattern {
  const p = lib.find((x) => x.id === id);
  if (!p) throw new Error(`no cycle pattern "${id}"`);
  return p;
}
