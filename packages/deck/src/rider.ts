/**
 * A body carried by the deck it stands on (pure). A game whose walker moves in the world (on land, on a quay, up a
 * gangplank) keeps it on a moving deck so: after each of the walker's steps, `board` notes where on the deck the body
 * stands, in the deck's own frame; when the deck has moved (`carry`, every frame), the body is put back at that spot
 * of the deck in its new place. So it neither slides off nor sinks through as the deck rises, pitches, rolls and
 * sails. A body put somewhere else in the meantime (a teleport, a cut scene) is not carried back.
 */
import { frameToLocal, frameToWorld, type Frame, type Vec3 } from './frame';

/** The body counts as put elsewhere when it moved this far (m, summed over x, y, z) since it was boarded or carried. */
const MOVED = 1e-6;

export class Rider<Id> {
  /** The deck the body stands on, where on it (its frame), and where in the world it was then. */
  private aboard: { readonly id: Id; readonly local: Vec3; readonly world: Vec3 } | null = null;

  /** `body`: the walker's position (written to when the body is carried); null: no body now. */
  constructor(private readonly body: () => Vec3 | null) {}

  /** The deck the body stands on (null: none). */
  get on(): Id | null {
    return this.aboard?.id ?? null;
  }

  /** Where on its deck the body stood when last boarded or carried, in the deck's frame (null: not aboard). */
  get spot(): Readonly<Vec3> | null {
    return this.aboard?.local ?? null;
  }

  /** Deck `id` is now at `frame`: a body standing on it, not put elsewhere since, goes with it. */
  carry(id: Id, frame: Frame): void {
    const r = this.body(), was = this.aboard;
    if (!r || !was || was.id !== id) return;
    const w = was.world;
    if (Math.abs(r.x - w.x) + Math.abs(r.y - w.y) + Math.abs(r.z - w.z) >= MOVED) return;
    frameToWorld(frame, was.local.x, was.local.y, was.local.z, w);
    r.x = w.x; r.y = w.y; r.z = w.z;
  }

  /** After the walker's step: the body stands on deck `id` at `frame` (its spot there is noted for the next carry). */
  board(id: Id, frame: Frame): void {
    const r = this.body();
    if (!r) { this.aboard = null; return; }
    this.aboard = { id, local: frameToLocal(frame, r.x, r.y, r.z), world: { x: r.x, y: r.y, z: r.z } };
  }

  /** The body is on no deck (on the quay, in the water, over the side). */
  leave(): void {
    this.aboard = null;
  }

  /** Deck `id` is gone (out of reach): a body on it is on none. */
  drop(id: Id): void {
    if (this.aboard?.id === id) this.aboard = null;
  }
}
