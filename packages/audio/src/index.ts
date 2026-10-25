/**
 * The pure half of `@futuremagic/audio` (no DOM, no Web Audio): the sound index the engine loads, seeded choices of
 * takes, the footstep clock and the music picker. The player itself is `@futuremagic/audio/web` (`AudioEngine`).
 */
import { hash3i, hashString, hashToFloat } from '@futuremagic/core';

/** What `tools/make.mjs` writes beside the sounds: every sound's files (takes) and their lengths. */
export interface SoundIndex {
  /** The rate the effects were stored at (the engine's context runs at it). */
  rate: number;
  sounds: Record<string, SoundEntry>;
}

export interface SoundEntry {
  kind: 'bed' | 'loop' | 'steps' | 'call' | 'music' | string;
  files: string[];
  seconds: number[];
}

/** A take of a sound, as played: which file, how fast (pitch) and how loud. */
export interface TakePick {
  file: string;
  pitch: number;
  gain: number;
}

/**
 * The `n`th play of a sound: one of its takes (never `last`, the one played before, when it has more), at a pitch
 * within ±`pitch` and a loudness within ±`gain`, all from the seed, so a replay sounds the same.
 */
export function pickTake(entry: SoundEntry, n: number, seed: number, last: string | null = null, spread = { pitch: 0.08, gain: 0.15 }): TakePick {
  const draw = (k: number): number => hashToFloat(hash3i(seed, n, k, 0x5a17));
  const m = entry.files.length;
  let i = Math.floor(draw(0) * m) % m;
  if (m > 1 && entry.files[i] === last) i = (i + 1) % m;
  return { file: entry.files[i], pitch: 1 + spread.pitch * (2 * draw(1) - 1), gain: 1 + spread.gain * (2 * draw(2) - 1) };
}

/** A seed for a sound's name (so each sound has its own sequence of takes). */
export const soundSeed = (seed: number, id: string): number => hash3i(seed, hashString(id), 0, 0x50d);

/**
 * Footsteps (or hooves, or swimming strokes) by distance: one beat each `stride` metres walked. The first beat after
 * standing still comes early, as a foot lifts at once.
 */
export class Stride {
  private walked = 0;

  /** Moving at `speed` (m/s) for `dt` s with strides of `stride` m: true when a foot comes down. */
  step(speed: number, dt: number, stride: number): boolean {
    if (speed < 0.2) {
      this.walked = Math.min(this.walked, stride * 0.6);
      return false;
    }
    this.walked += speed * dt;
    if (this.walked < stride) return false;
    this.walked -= stride;
    if (this.walked > stride) this.walked = 0;
    return true;
  }

  reset(): void { this.walked = 0; }
}

/** A stride at a speed (m/s): longer when running, as people's are (about 0.7 m walking, 1.1 m running). */
export const strideAt = (speed: number): number => Math.min(1.25, 0.55 + speed * 0.12);

export interface MusicOptions {
  /** A piece plays at least this long before another mood's piece replaces it (s), unless the new mood is urgent. */
  hold: number;
  /** Moods that cut in at once (a fight). */
  urgent: readonly string[];
  /** Silence between two pieces of the same mood, so music does not run without end (s). */
  rest: number;
}

const MUSIC: MusicOptions = { hold: 30, urgent: [], rest: 40 };

/**
 * Which piece to play: a mood (explore by day, town, fight...) has several pieces; the picker holds a piece a while
 * before following a new mood (so music does not flip at every door), lets urgent moods in at once, rests between
 * pieces of the same mood and never repeats the last piece when the mood has more. All choices are seeded.
 */
export class MusicPicker {
  private readonly opts: MusicOptions;
  private now: { mood: string; piece: string; since: number } | null = null;
  private resting: { mood: string; until: number } | null = null;
  private count = 0;
  private readonly last = new Map<string, string>();

  constructor(private readonly moods: Readonly<Record<string, readonly string[]>>, private readonly seed: number, opts: Partial<MusicOptions> = {}) {
    this.opts = { ...MUSIC, ...opts };
  }

  /** What plays (null: silence). */
  get piece(): string | null { return this.now?.piece ?? null; }
  get mood(): string | null { return this.now?.mood ?? null; }

  /**
   * The mood wanted at time `t` (s; null: no music). Returns the piece to play now (a change: crossfade to it), null
   * to fade out, or undefined when nothing changes.
   */
  want(mood: string | null, t: number): string | null | undefined {
    const cur = this.now, urgent = (m: string | null): boolean => !!m && this.opts.urgent.includes(m);
    if (cur && cur.mood === mood) return undefined;
    // A piece is held a while (an urgent one less: the fight's music lingers only briefly after it).
    if (cur && !urgent(mood) && t - cur.since < (urgent(cur.mood) ? Math.min(8, this.opts.hold) : this.opts.hold)) return undefined;
    if (!mood || !this.moods[mood]?.length) {
      if (!cur) return undefined;
      this.now = null;
      return null;
    }
    if (!cur && this.resting?.mood === mood && t < this.resting.until) return undefined;
    this.resting = null;
    const piece = this.choose(mood);
    this.now = { mood, piece, since: t };
    return piece;
  }

  /** The piece that played ended (it is not looped): rest, then another of the mood. */
  ended(t: number): void {
    if (!this.now) return;
    this.resting = { mood: this.now.mood, until: t + this.opts.rest };
    this.now = null;
  }

  private choose(mood: string): string {
    const list = this.moods[mood];
    const draw = hashToFloat(hash3i(this.seed, this.count++, hashString(mood), 0x3c));
    let i = Math.floor(draw * list.length) % list.length;
    if (list.length > 1 && list[i] === this.last.get(mood)) i = (i + 1) % list.length;
    this.last.set(mood, list[i]);
    return list[i];
  }
}

/**
 * A room's echo as an impulse response (one channel), made from its T60 and first delay: seeded noise decaying 60 dB
 * over T60, its highs dying faster than its lows (a one-pole low-pass closing along the tail), after a short silence for
 * the first reflections to come back. From Solarpolis `src/audio/sound.ts`.
 */
export function roomImpulse(rate: number, t60: number, delay: number, channel: number): Float32Array {
  t60 = Math.min(6, Math.max(0.1, t60));
  const n = Math.ceil((delay + t60) * rate), lead = Math.floor(delay * rate), x = new Float32Array(n);
  let seed = 0x9e3779b9 ^ (channel * 0x85ebca6b) ^ Math.round(t60 * 1000), y = 0;
  for (let i = lead; i < n; i++) {
    seed = (Math.imul(seed ^ (seed >>> 15), 0x2c1b3c6d) + 0x6d2b79f5) | 0;
    const white = ((seed >>> 0) / 4294967296) * 2 - 1, t = (i - lead) / rate;
    const cut = 1000 + 7000 * Math.exp((-3 * t) / t60), k = 1 - Math.exp((-2 * Math.PI * cut) / rate);
    y += k * (white - y);
    x[i] = y * Math.exp((-6.91 * t) / t60);
  }
  return x;
}
