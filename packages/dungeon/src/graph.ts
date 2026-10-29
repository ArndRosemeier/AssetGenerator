/**
 * The dungeon as a graph of rooms and links, before it has a shape. Games tag rooms and links with what
 * they mean (a kitchen, a key, a collapse); the generator only cares about the link kinds below.
 */

/**
 * How a link can be passed.
 * - `open`: an archway or a passage.
 * - `door`: a plain door.
 * - `locked`: a door that needs the key lying in room `key`.
 * - `secret`: a hidden way; passable once found, never on the intended route.
 * - `oneway`: barred on one side: passable from `a` to `b` only, until opened from `a` (then both ways).
 *   This is how shortcuts back out work.
 * - `drop`: from `a` down into the taller room `b` over a ledge; never back up.
 * - `grate`: bars or a gap: you see through, you cannot pass.
 * - `blocked`: rubble or bricks: neither seen nor passed (a trace of what happened there).
 */
export type LinkKind = 'open' | 'door' | 'locked' | 'secret' | 'oneway' | 'drop' | 'grate' | 'blocked';

export const LINK_KINDS: readonly LinkKind[] = ['open', 'door', 'locked', 'secret', 'oneway', 'drop', 'grate', 'blocked'];

/** A room's size class; the game maps each to cells (`LayoutOptions.size`). */
export type RoomSize = 'nook' | 'small' | 'medium' | 'large';

export interface Room {
  readonly id: number;
  /** What the room is for, in the game's words, plus the generator's own ('entrance', 'goal', 'key', ...). */
  readonly tags: string[];
  /** Storey: 0 the entrance's, -1 one below, ... */
  level: number;
  /**
   * Storeys the room spans upwards from `level` (2: a tall hall, entered from above over a ledge; more: a
   * cavern, which the game may make by raising a room after the graph is built).
   */
  height: number;
  size: RoomSize;
}

export interface Link {
  readonly id: number;
  readonly a: number;
  readonly b: number;
  kind: LinkKind;
  /** `locked`: the room the key lies in. */
  key?: number;
  readonly tags: string[];
}

export interface DungeonGraph {
  readonly rooms: Room[];
  /** Removed links are left out; ids stay stable (`links[i].id` need not be `i`). */
  readonly links: Link[];
  readonly entrance: number;
  readonly goal: number;
  /** The cycle patterns it was built from, main cycle first. */
  readonly patterns: string[];
}

/** Grows a graph room by room; the cycle patterns use it. */
export class GraphBuilder {
  readonly rooms: Room[] = [];
  readonly links: Link[] = [];
  private nextLink = 0;

  room(level: number, size: RoomSize, tags: string[] = [], height = 1): number {
    const id = this.rooms.length;
    this.rooms.push({ id, tags: [...tags], level, height, size });
    return id;
  }

  link(a: number, b: number, kind: LinkKind = 'open', tags: string[] = [], key?: number): Link {
    const l: Link = { id: this.nextLink++, a, b, kind, tags: [...tags], ...(key !== undefined ? { key } : {}) };
    this.links.push(l);
    return l;
  }

  remove(l: Link): void {
    const i = this.links.indexOf(l);
    if (i >= 0) this.links.splice(i, 1);
  }

  /** `n` new rooms in a row after `from` (same level, plain passages); returns the last (or `from` when n = 0). */
  chain(from: number, n: number, size: RoomSize, tags: string[] = [], kind: LinkKind = 'open'): number {
    let at = from;
    for (let i = 0; i < n; i++) {
      const r = this.room(this.rooms[from].level, size, tags);
      this.link(at, r, kind);
      at = r;
    }
    return at;
  }

  tag(room: number, ...tags: string[]): void {
    for (const t of tags) if (!this.rooms[room].tags.includes(t)) this.rooms[room].tags.push(t);
  }
}

/** Links touching a room. */
export function linksOf(g: { links: readonly Link[] }, room: number): Link[] {
  return g.links.filter((l) => l.a === room || l.b === room);
}

/** The room at the other end of a link. */
export function across(l: Link, room: number): number {
  return l.a === room ? l.b : l.a;
}
