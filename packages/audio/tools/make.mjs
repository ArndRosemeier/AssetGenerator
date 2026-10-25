#!/usr/bin/env node
/**
 * Makes a game's sounds and music from a spec (`sounds.json`): asks OpenRouter for each one that has no raw take yet,
 * then cuts, levels and encodes every take into the game's sound folder and writes its `index.json`, which the
 * player (`@futuremagic/audio/web`, `AudioEngine`) reads. Never part of CI: it needs the key and costs money.
 *
 *   NODE_USE_ENV_PROXY=1 node packages/audio/tools/make.mjs --spec sounds.json --out public/sound
 *       [--raw dir] [--only id,id] [--again id,id] [--dry] [--title Name]
 *
 * The spec: `{ "sounds": [Sound...], "music": [Music...] }`. A sound is `{ id, kind, prompt | from, ... }`:
 *  - `bed`: a long take, trimmed and levelled to −24 dBFS RMS; the player crossfades it into a loop;
 *  - `loop`: the same for a sound with a place, cut to its middle `seconds` (default 8);
 *  - `steps`: a take of separate hits (footsteps, hooves, rungs), cut into its `count` clearest;
 *  - `call`: one sound, trimmed (quieter than `trim` of its loudest moment, 0.03 by default), peak at −3 dBFS.
 * A piece of music is `{ id, prompt, out, model?: "clip", mono? }`, levelled to −16 LUFS (only a take whose `out` is
 * set goes into the game). `from` (a list of files in the raw folder) takes sounds made before (another game's) instead
 * of asking a model: `steps` and `call` cut each file as one take, `bed` and `loop` use the first.
 *
 * Models follow Arnd's preferences, resolved when the script runs (never a hardcoded version): sounds from the newest
 * ByteDance Seed Audio on the speech endpoint (a prompt must start with "The sound of", or it speaks the words), music
 * from the newest Google Lyria Pro (Clip for a 30 s piece), streamed. Audio is read as bytes from start to end; nothing
 * decodes it as text. The key ($OPEN_ROUTER_KEY or $OPENROUTER_API_KEY) is never printed. Raw takes are kept in
 * `--raw`, so cutting again costs nothing. Came from Solarpolis `scripts/sound/make.mjs`.
 */
import { spawnSync } from 'node:child_process';
import { existsSync, mkdirSync, readFileSync, readdirSync, rmSync, statSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';

const API = 'https://openrouter.ai/api/v1';
/** The rate sounds are stored and played at (the engine's AudioContext asks for the same). */
export const RATE = 32000;

const args = process.argv.slice(2);
const opt = (name) => { const i = args.indexOf(name); return i >= 0 ? args[i + 1] : null; };
const list = (name) => (opt(name) ?? '').split(',').filter(Boolean);
const SPEC = resolve(opt('--spec') ?? 'sounds.json');
const OUT = resolve(opt('--out') ?? 'public/sound');
const RAW = resolve(opt('--raw') ?? '.sound-raw');
const TITLE = opt('--title') ?? 'futuremagic';
const ONLY = list('--only');
const AGAIN = new Set(list('--again'));
const DRY = args.includes('--dry');

function key() {
  const k = process.env.OPEN_ROUTER_KEY || process.env.OPENROUTER_API_KEY;
  if (!k) throw new Error('No OpenRouter key: set OPEN_ROUTER_KEY.');
  return k.trim();
}

async function api(path, body, accept) {
  const r = await fetch(API + path, {
    method: body ? 'POST' : 'GET',
    headers: { Authorization: `Bearer ${key()}`, 'Content-Type': 'application/json', 'X-Title': TITLE, ...(accept ? { Accept: accept } : {}) },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!r.ok) throw new Error(`${path}: HTTP ${r.status} ${(await r.text()).slice(0, 500)}`);
  return r;
}

/** Arnd's rule: the newest model of the family (largest `created`, then the highest version in the id), never `:batch`. */
function newest(models) {
  const ver = (id) => (id.match(/\d+/g) ?? []).map(Number);
  const cmp = (a, b) => { const x = ver(a), y = ver(b); for (let i = 0; i < Math.max(x.length, y.length); i++) if ((x[i] ?? 0) !== (y[i] ?? 0)) return (x[i] ?? 0) - (y[i] ?? 0); return 0; };
  return models.filter((m) => !m.id.endsWith(':batch')).sort((a, b) => (b.created ?? 0) - (a.created ?? 0) || cmp(b.id, a.id))[0]?.id ?? null;
}

async function resolveModels() {
  const all = (await (await api('/models?output_modalities=all')).json()).data;
  const outs = (m) => m.architecture?.output_modalities ?? [];
  const seed = newest(all.filter((m) => /^bytedance-seed\/seed-audio/.test(m.id) && outs(m).some((o) => o === 'speech' || o === 'audio')));
  const music = newest(all.filter((m) => /lyria/.test(m.id) && /pro/.test(m.id) && outs(m).includes('audio')));
  const clip = newest(all.filter((m) => /lyria/.test(m.id) && /clip/.test(m.id) && outs(m).includes('audio')));
  if (!seed || !music || !clip) throw new Error(`model family missing (seed ${seed}, lyria pro ${music}, clip ${clip}): ask Arnd, never guess`);
  return { sound: seed, music, clip };
}

/** One Seed Audio take: the speech endpoint, MP3 bytes. */
async function seedTake(model, prompt) {
  if (!/^the sound of/i.test(prompt)) throw new Error(`a sound prompt must start with "The sound of": ${prompt}`);
  return Buffer.from(await (await api('/audio/speech', { model, input: prompt, response_format: 'mp3' })).arrayBuffer());
}

/** One Lyria take: audio only comes streamed; the base64 chunks are joined and decoded once at the end. */
async function lyriaTake(model, prompt) {
  const r = await api('/chat/completions', { model, messages: [{ role: 'user', content: prompt }], stream: true, modalities: ['text', 'audio'] }, 'text/event-stream');
  const dec = new TextDecoder(); // the stream is JSON text; the audio inside it is base64
  let buf = '', b64 = '';
  for await (const chunk of r.body) {
    buf += dec.decode(chunk, { stream: true });
    let nl;
    while ((nl = buf.indexOf('\n')) >= 0) {
      const line = buf.slice(0, nl).trim();
      buf = buf.slice(nl + 1);
      if (!line.startsWith('data:')) continue;
      const data = line.slice(5).trim();
      if (data === '[DONE]') continue;
      let ev;
      try { ev = JSON.parse(data); } catch { continue; }
      if (ev.error) throw new Error(`stream error: ${JSON.stringify(ev.error).slice(0, 300)}`);
      for (const c of ev.choices ?? []) if (c.delta?.audio?.data) b64 += c.delta.audio.data;
    }
  }
  if (!b64) throw new Error('no audio in the stream');
  return Buffer.from(b64, 'base64');
}

function ffmpeg(argv, input) {
  const r = spawnSync('ffmpeg', ['-hide_banner', '-loglevel', 'error', ...argv], { input, maxBuffer: 1 << 30 });
  if (r.status !== 0) throw new Error(`ffmpeg ${argv.join(' ')}: ${r.stderr}`);
  return r.stdout;
}

/** A file decoded to mono float samples at RATE. */
function decode(file) {
  const b = ffmpeg(['-i', file, '-ac', '1', '-ar', String(RATE), '-f', 'f32le', 'pipe:1']);
  return new Float32Array(b.buffer, b.byteOffset, b.byteLength / 4).slice();
}

/** Samples encoded to a mono MP3 at RATE. */
function encode(samples, file, kbps) {
  mkdirSync(dirname(file), { recursive: true });
  ffmpeg(['-y', '-f', 'f32le', '-ar', String(RATE), '-ac', '1', '-i', 'pipe:0', '-c:a', 'libmp3lame', '-b:a', `${kbps}k`, file], Buffer.from(samples.buffer, samples.byteOffset, samples.byteLength));
}

/** RMS per 5 ms frame. */
function envelope(x) {
  const n = Math.round(RATE * 0.005), env = new Float32Array(Math.floor(x.length / n));
  for (let f = 0; f < env.length; f++) { let s = 0; for (let i = f * n; i < (f + 1) * n; i++) s += x[i] * x[i]; env[f] = Math.sqrt(s / n); }
  return { env, frame: n };
}

const peakOf = (x) => x.reduce((m, v) => Math.max(m, Math.abs(v)), 0);
const rmsOf = (x) => Math.sqrt(x.reduce((s, v) => s + v * v, 0) / Math.max(1, x.length));

/** Cut off the quiet before the first and after the last frame above `share` of the loudest frame. */
function trim(x, share) {
  const { env, frame } = envelope(x);
  const top = env.reduce((m, v) => Math.max(m, v), 0), on = top * share;
  let a = 0, b = env.length - 1;
  while (a < b && env[a] < on) a++;
  while (b > a && env[b] < on) b--;
  return x.slice(Math.max(0, (a - 4) * frame), Math.min(x.length, (b + 8) * frame));
}

function fade(x, inS, outS) {
  const i = Math.round(inS * RATE), o = Math.round(outS * RATE);
  for (let k = 0; k < i && k < x.length; k++) x[k] *= k / i;
  for (let k = 0; k < o && k < x.length; k++) x[x.length - 1 - k] *= k / o;
  return x;
}

const scale = (x, g) => { for (let i = 0; i < x.length; i++) x[i] *= g; return x; };
const dB = (d) => 10 ** (d / 20);

/** A bed: trimmed, levelled to −24 dBFS RMS (peaks kept under −1 dBFS), faded at both ends; the player crossfades it. */
function bed(x) {
  const t = trim(x, 0.05);
  const g = Math.min(dB(-24) / Math.max(rmsOf(t), 1e-6), dB(-1) / Math.max(peakOf(t), 1e-6));
  return fade(scale(t, g), 0.05, 0.05);
}

/** A short loop for a sound with a place: the middle `secs` of the trimmed take, levelled as a bed. */
function loop(x, secs) {
  const t = trim(x, 0.05), n = Math.min(t.length, Math.round(secs * RATE)), a = Math.floor((t.length - n) / 2);
  return bed(t.slice(a, a + n));
}

/** A single call: trimmed (below `share` of its loudest 5 ms), peak at −3 dBFS, at most `most` s long (faded out). */
function call(x, most, share = 0.03) {
  let t = trim(x, share);
  if (most && t.length > most * RATE) t = t.slice(0, Math.round(most * RATE));
  return fade(scale(t, dB(-3) / Math.max(peakOf(t), 1e-6)), 0.005, most ? Math.min(0.3, most / 4) : 0.08);
}

/**
 * Hits out of a take (footsteps, hooves, rungs). A take often carries its own ground noise, so a hit is a peak standing
 * out of its surroundings: a frame at least 9 dB over the median of the second round it and the loudest within 200 ms.
 * Each runs from 60 ms before its peak to `tail` ms after (or 40 ms before the next); the `count` that stand out most
 * and do not clip are kept, each with its peak at −3 dBFS.
 */
function steps(x, count, tail = 350) {
  const { env, frame } = envelope(x);
  const ms = (m) => Math.round(m / 5);
  const median = (a, b) => { const v = Array.from(env.subarray(Math.max(0, a), Math.min(env.length, b))).sort((p, q) => p - q); return v[v.length >> 1] ?? 0; };
  const peaks = [];
  for (let f = 0; f < env.length; f++) {
    let top = true;
    for (let g = Math.max(0, f - ms(200)); g < Math.min(env.length, f + ms(200)) && top; g++) if (env[g] > env[f]) top = false;
    const floor = median(f - ms(500), f + ms(500));
    if (top && env[f] > floor * dB(9)) peaks.push({ f, stand: env[f] / Math.max(floor, 1e-9) });
  }
  const cuts = peaks.map((p, i) => {
    const a = Math.max(0, (p.f - ms(60)) * frame);
    const next = i + 1 < peaks.length ? (peaks[i + 1].f - ms(40)) * frame : x.length;
    return { stand: p.stand, x: x.slice(a, Math.min(x.length, (p.f + ms(tail)) * frame, next)) };
  }).filter((c) => c.x.length > 0.12 * RATE && peakOf(c.x) < 0.999);
  cuts.sort((p, q) => q.stand - p.stand);
  return cuts.slice(0, count).map(({ x: c }) => fade(scale(c, dB(-3) / Math.max(peakOf(c), 1e-6)), 0.004, 0.06));
}

/** Music stays at 44.1 kHz (it streams, never decoded whole), levelled to −16 LUFS: stereo, or mono for music played at a place. */
function music(raw, file, mono, kbps) {
  mkdirSync(dirname(file), { recursive: true });
  ffmpeg(['-y', '-i', raw, '-af', 'loudnorm=I=-16:TP=-1.5:LRA=11', '-ar', '44100', '-ac', mono ? '1' : '2', '-c:a', 'libmp3lame', '-b:a', `${kbps ?? (mono ? 64 : 112)}k`, file]);
}

const seconds = (x) => Math.round((x.length / RATE) * 1000) / 1000;

async function pool(items, n, f) {
  const out = [];
  let i = 0;
  await Promise.all(Array.from({ length: n }, async () => { while (i < items.length) { const k = i++; try { out[k] = await f(items[k]); } catch (e) { console.warn(`  ${items[k].id}: ${e.message}`); } } }));
  return out;
}

/** The takes of a sound, cut. */
function cut(s, raw) {
  if (s.from) {
    const xs = s.from.map((f) => decode(join(RAW, f)));
    if (s.kind === 'bed') return [bed(xs[0])];
    if (s.kind === 'loop') return [loop(xs[0], s.seconds ?? 8)];
    return xs.map((x) => call(x, s.most, s.trim));
  }
  const x = decode(raw);
  if (s.kind === 'steps') return steps(x, s.count, s.tail);
  if (s.kind === 'bed') return [bed(x)];
  if (s.kind === 'loop') return [loop(x, s.seconds ?? 8)];
  return [call(x, s.most, s.trim)];
}

async function main() {
  const spec = JSON.parse(readFileSync(SPEC, 'utf8'));
  const music_ = spec.music ?? [];
  const items = [...spec.sounds, ...music_].filter((s) => !ONLY.length || ONLY.includes(s.id));
  const rawOf = (s) => join(RAW, `${s.id}.${s.kind === 'music' ? 'audio' : 'mp3'}`);
  const missing = items.filter((s) => !s.from && (AGAIN.has(s.id) || !existsSync(rawOf(s))));
  if (missing.length) {
    const models = await resolveModels();
    console.log(`models: sounds ${models.sound}, music ${models.music} (short pieces ${models.clip}); ${missing.length} takes to make`);
    if (DRY) return;
    const startUsage = (await (await api('/key')).json()).data.usage;
    await pool(missing, 6, async (s) => {
      const bytes = s.kind === 'music' ? await lyriaTake(s.model === 'clip' ? models.clip : models.music, s.prompt) : await seedTake(models.sound, s.prompt);
      mkdirSync(dirname(rawOf(s)), { recursive: true });
      writeFileSync(rawOf(s), bytes);
      console.log(`  took ${s.id} (${bytes.length} bytes)`);
    });
    const used = (await (await api('/key')).json()).data.usage - startUsage;
    console.log(`cost of this run: $${used.toFixed(3)}`);
  }
  const index = existsSync(join(OUT, 'index.json')) ? JSON.parse(readFileSync(join(OUT, 'index.json'), 'utf8')) : { sounds: {} };
  for (const s of items) {
    const raw = s.kind === 'music' && s.from ? join(RAW, s.from[0]) : rawOf(s);
    if (!existsSync(s.from ? join(RAW, s.from[0]) : raw)) continue;
    const dir = join(OUT, dirname(s.id)), base = s.id.split('/').pop();
    for (const f of existsSync(dir) ? readdirSync(dir) : []) if (f === `${base}.mp3` || new RegExp(`^${base}-\\d+\\.mp3$`).test(f)) rmSync(join(dir, f));
    if (s.kind === 'music') {
      if (!s.out) continue;
      const file = `${s.out}.mp3`;
      music(raw, join(OUT, file), !!s.mono, s.kbps);
      const secs = Number(spawnSync('ffprobe', ['-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', join(OUT, file)]).stdout.toString().trim());
      index.sounds[s.out] = { kind: s.kind, take: s.id, files: [file], seconds: [Math.round(secs * 10) / 10] };
      console.log(`  ${s.id} -> ${file}: ${(statSync(join(OUT, file)).size / 1024).toFixed(0)} KB`);
      continue;
    }
    const takes = cut(s, raw);
    if (s.kind === 'steps' && !s.from && takes.length < s.count) console.warn(`  ${s.id}: only ${takes.length} of ${s.count} steps found`);
    const files = takes.map((t, i) => (takes.length > 1 || s.kind === 'steps' ? `${s.id}-${i + 1}.mp3` : `${s.id}.mp3`));
    takes.forEach((t, i) => encode(t, join(OUT, files[i]), s.kind === 'bed' || s.kind === 'loop' ? 64 : 80));
    index.sounds[s.id] = { kind: s.kind, files, seconds: takes.map(seconds) };
    const bytes = files.reduce((n, f) => n + statSync(join(OUT, f)).size, 0);
    console.log(`  ${s.id}: ${files.length} file(s), ${(bytes / 1024).toFixed(0)} KB`);
  }
  // A sound taken out of the spec leaves the index (its files are removed with it).
  const listed = new Set([...spec.sounds.map((s) => s.id), ...music_.map((s) => s.out).filter(Boolean)]);
  for (const id of Object.keys(index.sounds)) {
    if (listed.has(id)) continue;
    for (const f of index.sounds[id].files) rmSync(join(OUT, f), { force: true });
    delete index.sounds[id];
  }
  index.rate = RATE;
  index.sounds = Object.fromEntries(Object.entries(index.sounds).sort(([a], [b]) => a.localeCompare(b)));
  writeFileSync(join(OUT, 'index.json'), JSON.stringify(index, null, 1) + '\n');
}

main().catch((e) => { console.error(e.message); process.exit(1); });
