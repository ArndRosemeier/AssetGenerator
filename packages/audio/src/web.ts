/**
 * The sound player of `@futuremagic/audio`, on Web Audio. A game says what is heard; the engine plays it:
 *
 *  - beds: long takes (wind, rain, a river, a tavern's murmur) played as overlapping segments that crossfade, in two
 *    chains offset by half a take and panned apart, so a mono take sounds wide and its loop never shows. A game sets
 *    each bed's level every tick (`bed`); a bed not set fades out, and stops once quiet a while. A bed can stand at a
 *    place (`at`): one chain through an HRTF panner, so a waterfall or a smithy is heard from where it is;
 *  - one-shots (`play`): a seeded take of a sound (never the same twice running), at a seeded pitch, in the head or
 *    from a place in the world;
 *  - music (`music`): streamed through two media elements (never decoded whole) that crossfade, ducked under dialogs
 *    (`duck`);
 *  - the world's sound goes through a low-pass (`muffle`: under water, behind walls) and a room's echo (`echo`).
 *
 * Buses: `world` (beds and placed sounds), `body` (steps, the hero's own sounds), `ui`, `music`, each with its own
 * volume under the master. Decoded audio is 32-bit float, so takes are stored at `index.rate` (32 kHz mono) and the
 * context runs at that rate; past `budget` bytes the least recently heard takes go.
 *
 * Browsers start sound only after the person's first click or key: `unlock` (called from such an event, or by the
 * engine's own listener) opens the context; what was asked before (music, beds) starts then.
 * From Solarpolis `src/audio/sound.ts`.
 */
import { hashString, hashToFloat } from '@futuremagic/core';
import { pickTake, roomImpulse, soundSeed, type SoundIndex, type SoundEntry } from './index';

export type Bus = 'world' | 'body' | 'ui' | 'music';
export type Vec3 = readonly [number, number, number];

export interface EngineOptions {
  /** The folder with `index.json` and the sounds (a URL ending in `/`). */
  base: string;
  /** Seed for the takes' choices and pitches. */
  seed?: number;
  /** Most decoded audio kept (bytes), 24 MB by default. */
  budget?: number;
  /** Listen for the first press on this target to unlock (default: the window); null: the game calls `unlock`. */
  unlockOn?: EventTarget | null;
}

export interface PlayOptions {
  bus?: Bus;
  /** Loudness, 1 = as made. */
  gain?: number;
  /** Playback rate on top of the take's seeded one. */
  pitch?: number;
  /** From a place in the world (else in the head). */
  at?: Vec3;
  /** Half as loud at twice this distance (m), 4 by default. */
  ref?: number;
  /** Seconds from now. */
  delay?: number;
}

export interface BedOptions {
  bus?: Bus;
  /** Standing at a place (moved each time the bed is set). */
  at?: Vec3;
  ref?: number;
  /** How fast its level follows (time constant, s), 1.2 by default. */
  glide?: number;
  /** Playback rate. */
  rate?: number;
}

interface Take { buffer: AudioBuffer; bytes: number; used: number }

/** One chain of a loop's crossfading segments. */
interface Chain { out: AudioNode; rate: number; skip: number; next: number; playing: AudioBufferSourceNode[]; first: boolean }

interface BedVoice { gain: GainNode; panner: PannerNode | null; chains: Chain[]; file: string; set: boolean; heard: number }

interface Deck { media: HTMLAudioElement; node: MediaElementAudioSourceNode; gain: GainNode; piece: string | null }

const MB = 1024 * 1024;
/** Segments overlap by this much (s) and are laid this far ahead (s). */
const XFADE = 1.5, LAY_AHEAD = 2;
/** A bed quiet this long (s) stops; its take stays until memory needs it. */
const QUIET_STOP = 12;
/** Most one-shots at once. */
const MOST_SHOTS = 24;

export class AudioEngine {
  private ctx: AudioContext | null = null;
  private index: SoundIndex | null = null;
  private master!: GainNode;
  private readonly buses = new Map<Bus, GainNode>();
  private muffler!: BiquadFilterNode;
  private echoIn!: GainNode;
  private echoes: { conv: ConvolverNode; gain: GainNode; t60: number }[] = [];
  private readonly takes = new Map<string, Take>();
  private readonly loading = new Map<string, Promise<Take | null>>();
  private readonly beds = new Map<string, BedVoice>();
  private decks: Deck[] = [];
  private wantMusic: { piece: string | null; fade: number } | null = null;
  private duckLevel = 1;
  private readonly plays = new Map<string, { n: number; last: string }>();
  private shots = 0;
  private readonly seed: number;
  private readonly budget: number;
  private readonly levels: Record<Bus | 'master', number> = { master: 1, world: 1, body: 1, ui: 1, music: 1 };
  /** Called when a piece of music plays to its end (pieces are not looped). */
  onMusicEnded: (() => void) | null = null;
  /** The index is loaded (or failed: null). */
  readonly ready: Promise<SoundIndex | null>;

  constructor(private readonly opts: EngineOptions) {
    this.seed = opts.seed ?? 0x5eed;
    this.budget = opts.budget ?? 24 * MB;
    this.ready = fetch(`${opts.base}index.json`).then((r) => (r.ok ? r.json() : null)).then((i: SoundIndex | null) => (this.index = i)).catch(() => (this.index = null));
    const target = opts.unlockOn === undefined ? (typeof window === 'undefined' ? null : window) : opts.unlockOn;
    if (target) {
      const unlock = (): void => {
        target.removeEventListener('pointerdown', unlock, true);
        target.removeEventListener('keydown', unlock, true);
        this.unlock();
      };
      target.addEventListener('pointerdown', unlock, true);
      target.addEventListener('keydown', unlock, true);
    }
  }

  /** Whether sound can play (after the first press). */
  get open(): boolean { return this.ctx !== null; }

  /** Whether the index names this sound. */
  has(id: string): boolean { return !!this.index?.sounds[id]; }

  /** Volume of the whole (0..1) or of a bus. */
  setVolume(bus: Bus | 'master', v: number): void {
    this.levels[bus] = v;
    if (!this.ctx) return;
    const node = bus === 'master' ? this.master : this.buses.get(bus)!;
    node.gain.setTargetAtTime(bus === 'music' ? v * this.duckLevel : v, this.ctx.currentTime, 0.05);
  }

  volume(bus: Bus | 'master'): number { return this.levels[bus]; }

  /** Open the context (from a press). */
  unlock(): void {
    if (this.ctx) return;
    let ctx: AudioContext;
    try { ctx = new AudioContext({ sampleRate: this.index?.rate ?? 32000 }); } catch { ctx = new AudioContext(); }
    this.ctx = ctx;
    this.master = ctx.createGain();
    this.master.gain.value = this.levels.master;
    this.master.connect(ctx.destination);
    this.muffler = ctx.createBiquadFilter();
    this.muffler.type = 'lowpass';
    this.muffler.frequency.value = ctx.sampleRate / 2;
    this.muffler.connect(this.master);
    this.echoIn = ctx.createGain();
    this.echoes = [0, 1].map(() => {
      const conv = ctx.createConvolver(), gain = ctx.createGain();
      gain.gain.value = 0;
      this.echoIn.connect(conv).connect(gain).connect(this.master);
      return { conv, gain, t60: 0 };
    });
    for (const b of ['world', 'body', 'ui', 'music'] as Bus[]) {
      const g = ctx.createGain();
      g.gain.value = this.levels[b];
      if (b === 'world') g.connect(this.muffler); else g.connect(this.master);
      if (b === 'world' || b === 'body') g.connect(this.echoIn);
      this.buses.set(b, g);
    }
    void ctx.resume();
    if (this.wantMusic) this.music(this.wantMusic.piece, this.wantMusic.fade);
  }

  /** The listener's ears: where they are, which way they look and which way is up. */
  listen(eye: Vec3, look: Vec3, up: Vec3 = [0, 1, 0]): void {
    const l = this.ctx?.listener;
    if (!l) return;
    if (l.positionX) {
      const t = this.ctx!.currentTime;
      l.positionX.setValueAtTime(eye[0], t); l.positionY.setValueAtTime(eye[1], t); l.positionZ.setValueAtTime(eye[2], t);
      l.forwardX.setValueAtTime(look[0], t); l.forwardY.setValueAtTime(look[1], t); l.forwardZ.setValueAtTime(look[2], t);
      l.upX.setValueAtTime(up[0], t); l.upY.setValueAtTime(up[1], t); l.upZ.setValueAtTime(up[2], t);
    } else {
      l.setPosition(...eye);
      l.setOrientation(...look, ...up);
    }
  }

  /** Fetch and decode these sounds' takes ahead of need (once sound is open). */
  preload(ids: readonly string[]): void {
    if (!this.ctx) return;
    for (const id of ids) for (const f of this.index?.sounds[id]?.files ?? []) if (!this.takes.has(f)) void this.decode(f);
  }

  /** Play a sound once (a seeded take of it). False if it is not ready yet (its takes start loading). */
  play(id: string, o: PlayOptions = {}): boolean {
    const ctx = this.ctx, entry = this.index?.sounds[id];
    if (!ctx || !entry || this.shots >= MOST_SHOTS) return false;
    const was = this.plays.get(id), n = was?.n ?? 0;
    const pick = pickTake(entry, n, soundSeed(this.seed, id), was?.last ?? null);
    this.plays.set(id, { n: n + 1, last: pick.file });
    const take = this.takes.get(pick.file);
    if (!take) { this.loadAll(entry); return false; }
    take.used = ctx.currentTime;
    const src = ctx.createBufferSource(), g = ctx.createGain();
    src.buffer = take.buffer;
    src.playbackRate.value = pick.pitch * (o.pitch ?? 1);
    g.gain.value = pick.gain * (o.gain ?? 1);
    const panner = o.at ? spot(ctx, o.at, o.ref ?? 4) : null;
    src.connect(g);
    (panner ? g.connect(panner) : g).connect(this.buses.get(o.bus ?? (o.at ? 'world' : 'body'))!);
    this.shots++;
    src.onended = () => { this.shots--; g.disconnect(); panner?.disconnect(); };
    src.start(ctx.currentTime + (o.delay ?? 0));
    return true;
  }

  /**
   * A bed at `level` (0..1) under `key` (the sound's id by default): call it every tick while it should be heard; one
   * not set since the last `settle` fades out.
   */
  bed(id: string, level: number, o: BedOptions = {}, key = id): void {
    const ctx = this.ctx;
    if (!ctx) return;
    let v = this.beds.get(key);
    if (v && level <= 0.002 && !v.set) return;
    if (!v) {
      if (level <= 0.002) return;
      v = this.startBed(id, key, o) ?? undefined;
      if (!v) return;
    }
    v.set = true;
    v.heard = ctx.currentTime;
    v.gain.gain.setTargetAtTime(level, ctx.currentTime, o.glide ?? 1.2);
    if (v.panner && o.at) {
      const p = v.panner, t = ctx.currentTime;
      p.positionX.setTargetAtTime(o.at[0], t, 0.1); p.positionY.setTargetAtTime(o.at[1], t, 0.1); p.positionZ.setTargetAtTime(o.at[2], t, 0.1);
    }
  }

  /** After a tick's `bed` calls: beds not set fade out. */
  settle(glide = 1.5): void {
    const ctx = this.ctx;
    if (!ctx) return;
    for (const v of this.beds.values()) {
      if (!v.set) v.gain.gain.setTargetAtTime(0, ctx.currentTime, glide);
      v.set = false;
    }
  }

  /** Crossfade to a piece of music (an id in the index), or fade out (null), over `fade` s. */
  music(piece: string | null, fade = 4): void {
    this.wantMusic = { piece, fade };
    const ctx = this.ctx;
    if (!ctx) return;
    if (this.decks.length === 0) this.decks = [0, 1].map(() => this.deck(ctx));
    const [a, b] = this.decks, now = ctx.currentTime;
    if (a.piece === piece) return;
    // The playing deck fades out; the other takes the new piece and fades in.
    fadeTo(a.gain, 0, now, fade);
    const out = a;
    setTimeout(() => { if (out.piece === null) out.media.pause(); }, fade * 1000 + 200);
    this.decks = [b, a];
    a.piece = null;
    if (!piece) return;
    const file = this.index?.sounds[piece]?.files[0];
    if (!file) return;
    b.piece = piece;
    b.media.src = this.opts.base + file;
    b.media.currentTime = 0;
    void b.media.play().catch(() => undefined);
    fadeTo(b.gain, 1, now, fade);
  }

  /** The music now playing (null: none). */
  get piece(): string | null { return this.decks[0]?.piece ?? this.wantMusic?.piece ?? null; }

  /** Lower the music (a dialog open, a moment to hear), 1 = back to full. */
  duck(level: number, seconds = 0.6): void {
    this.duckLevel = level;
    const g = this.buses.get('music');
    if (g && this.ctx) g.gain.setTargetAtTime(this.levels.music * level, this.ctx.currentTime, seconds / 3);
  }

  /** The world's sound through a low-pass at `hz` (under water, behind walls); null opens it again. */
  muffle(hz: number | null, glide = 0.3): void {
    const ctx = this.ctx;
    if (!ctx) return;
    this.muffler.frequency.setTargetAtTime(hz ?? ctx.sampleRate / 2, ctx.currentTime, glide);
  }

  /** The room's echo: its T60 (s) and how much of it (0: outdoors). A new room's echo crossfades in. */
  echo(t60: number, wet: number, glide = 0.5): void {
    const ctx = this.ctx;
    if (!ctx) return;
    const [a, b] = this.echoes, now = ctx.currentTime;
    if (wet > 0.01 && Math.abs(t60 - a.t60) > 0.2 * Math.max(a.t60, 0.1)) {
      const buf = ctx.createBuffer(2, roomImpulse(ctx.sampleRate, t60, 0.02, 0).length, ctx.sampleRate);
      for (let ch = 0; ch < 2; ch++) buf.copyToChannel(roomImpulse(ctx.sampleRate, t60, 0.02, ch) as Float32Array<ArrayBuffer>, ch);
      b.conv.buffer = buf;
      b.t60 = t60;
      a.gain.gain.setTargetAtTime(0, now, glide);
      this.echoes = [b, a];
    }
    this.echoes[0].gain.gain.setTargetAtTime(wet, now, glide);
  }

  /** Every frame: keep the beds' segments laid ahead, stop the beds quiet for long. */
  update(): void {
    const ctx = this.ctx;
    if (!ctx) return;
    const now = ctx.currentTime;
    for (const [key, v] of this.beds) {
      const take = this.takes.get(v.file);
      if (!take || now - v.heard > QUIET_STOP) { this.stopBed(key, v); continue; }
      take.used = now;
      for (const c of v.chains) this.layChain(c, take.buffer, now);
    }
  }

  /** Bytes of decoded audio held. */
  decodedBytes(): number {
    let n = 0;
    for (const t of this.takes.values()) n += t.bytes;
    return n;
  }

  /** A line for a debug HUD. */
  summary(): string {
    if (!this.ctx) return 'sound: waiting for a click';
    const beds = [...this.beds].filter(([, v]) => v.gain.gain.value > 0.01).map(([k, v]) => `${k} ${v.gain.gain.value.toFixed(2)}`).join(', ');
    return `sound: ${(this.decodedBytes() / MB).toFixed(1)} MB, ${this.shots} shots · ${beds || 'no beds'} · music ${this.piece ?? '-'}`;
  }

  private deck(ctx: AudioContext): Deck {
    const media = new Audio();
    media.crossOrigin = 'anonymous';
    media.preload = 'auto';
    const node = ctx.createMediaElementSource(media), gain = ctx.createGain();
    gain.gain.value = 0;
    node.connect(gain).connect(this.buses.get('music')!);
    const d: Deck = { media, node, gain, piece: null };
    media.onended = () => { if (this.decks[0] === d && d.piece) { d.piece = null; this.onMusicEnded?.(); } };
    return d;
  }

  private startBed(id: string, key: string, o: BedOptions): BedVoice | null {
    const entry = this.index?.sounds[id], file = entry?.files[0];
    if (!entry || !file) return null;
    if (!this.takes.has(file)) { void this.decode(file); return null; }
    const ctx = this.ctx!, now = ctx.currentTime, gain = ctx.createGain();
    gain.gain.value = 0;
    const panner = o.at ? spot(ctx, o.at, o.ref ?? 8) : null;
    (panner ? gain.connect(panner) : gain).connect(this.buses.get(o.bus ?? 'world')!);
    const rate = o.rate ?? 1;
    // Placed: one chain (from one point). Else two, the second half a take in and a little slower, panned apart.
    const chains = (panner ? [0] : [-0.45, 0.45]).map((p, k) => {
      let out: AudioNode = gain;
      if (!panner) {
        const pan = ctx.createStereoPanner();
        pan.pan.value = p;
        pan.connect(gain);
        out = pan;
      }
      return { out, rate: k ? rate * 0.97 : rate, skip: k ? 0.5 : hashToFloat(hashString(key)), next: now + 0.05, playing: [], first: true } as Chain;
    });
    const v: BedVoice = { gain, panner, chains, file, set: false, heard: now };
    this.beds.set(key, v);
    return v;
  }

  private layChain(c: Chain, buffer: AudioBuffer, now: number): void {
    const ctx = this.ctx!, dur = buffer.duration;
    while (c.next < now + LAY_AHEAD) {
      const offset = c.first ? c.skip * dur : 0, length = dur - offset;
      c.first = false;
      const src = ctx.createBufferSource(), g = ctx.createGain();
      src.buffer = buffer;
      src.playbackRate.value = c.rate;
      const span = length / c.rate, fade = Math.min(XFADE, span / 3), at = Math.max(c.next, now);
      g.gain.setValueAtTime(0, at);
      g.gain.linearRampToValueAtTime(1, at + fade);
      g.gain.setValueAtTime(1, at + span - fade);
      g.gain.linearRampToValueAtTime(0, at + span);
      src.connect(g).connect(c.out);
      src.start(at, offset);
      src.stop(at + span + 0.05);
      c.playing.push(src);
      src.onended = () => { c.playing = c.playing.filter((x) => x !== src); g.disconnect(); };
      c.next = at + span - fade;
    }
  }

  private stopBed(key: string, v: BedVoice): void {
    for (const c of v.chains) for (const s of c.playing) { try { s.stop(); } catch { /* already stopped */ } }
    v.gain.disconnect();
    v.panner?.disconnect();
    this.beds.delete(key);
  }

  private loadAll(entry: SoundEntry): void {
    for (const f of entry.files) if (!this.takes.has(f)) void this.decode(f);
  }

  private decode(file: string): Promise<Take | null> {
    let p = this.loading.get(file);
    if (p) return p;
    const ctx = this.ctx!;
    p = fetch(this.opts.base + file)
      .then((r) => (r.ok ? r.arrayBuffer() : Promise.reject(new Error(`${file}: ${r.status}`))))
      .then((b) => ctx.decodeAudioData(b))
      .then((buffer) => {
        const take = { buffer, bytes: buffer.length * buffer.numberOfChannels * 4, used: ctx.currentTime };
        this.takes.set(file, take);
        this.fit();
        return take;
      })
      .catch(() => null)
      .finally(() => { this.loading.delete(file); });
    this.loading.set(file, p);
    return p;
  }

  /** Past the budget, drop the takes heard longest ago that no bed is playing. */
  private fit(): void {
    if (this.decodedBytes() <= this.budget) return;
    const playing = new Set([...this.beds.values()].map((v) => v.file));
    const old = [...this.takes].filter(([f]) => !playing.has(f)).sort((a, b) => a[1].used - b[1].used);
    for (const [f] of old) {
      if (this.decodedBytes() <= this.budget) break;
      this.takes.delete(f);
    }
  }
}

/** A gain gliding linearly to `to` over `seconds` from now. */
function fadeTo(g: GainNode, to: number, now: number, seconds: number): void {
  g.gain.cancelScheduledValues(now);
  g.gain.setValueAtTime(g.gain.value, now);
  g.gain.linearRampToValueAtTime(to, now + Math.max(0.01, seconds));
}

/** A panner at a point in the world (HRTF), half as loud at twice `ref` m. */
function spot(ctx: AudioContext, at: Vec3, ref: number): PannerNode {
  return new PannerNode(ctx, {
    panningModel: 'HRTF', distanceModel: 'inverse', refDistance: ref, rolloffFactor: 1, maxDistance: 2000,
    positionX: at[0], positionY: at[1], positionZ: at[2],
  });
}
