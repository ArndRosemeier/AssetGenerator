import { test } from 'node:test';
import assert from 'node:assert/strict';
import { MusicPicker, Stride, pickTake, roomImpulse, strideAt } from '../src/index';

test('takes: seeded, never the same twice running, pitch and gain within their spread', () => {
  const entry = { kind: 'steps', files: ['a', 'b', 'c', 'd'], seconds: [0.4, 0.4, 0.4, 0.4] };
  const run = (seed: number) => {
    let last: string | null = null;
    return Array.from({ length: 40 }, (_, n) => { const t = pickTake(entry, n, seed, last); last = t.file; return t; });
  };
  const a = run(7);
  assert.deepEqual(a, run(7));
  assert.notDeepEqual(a.map((t) => t.file), run(8).map((t) => t.file));
  for (let i = 1; i < a.length; i++) assert.notEqual(a[i].file, a[i - 1].file);
  assert.equal(new Set(a.map((t) => t.file)).size, 4);
  for (const t of a) {
    assert.ok(t.pitch >= 0.92 && t.pitch <= 1.08);
    assert.ok(t.gain >= 0.85 && t.gain <= 1.15);
  }
  assert.equal(pickTake({ kind: 'call', files: ['x'], seconds: [1] }, 3, 1).file, 'x');
});

test('stride: one beat per stride walked, an early first one, none standing', () => {
  const s = new Stride();
  let beats = 0;
  for (let i = 0; i < 100; i++) if (s.step(1.5, 0.1, 0.75)) beats++;
  assert.equal(beats, 20);
  for (let i = 0; i < 10; i++) assert.equal(s.step(0, 0.1, 0.75), false);
  // After standing, the first step comes within less than a stride.
  let t = 0;
  while (!s.step(1.5, 0.05, 0.75)) t += 0.05;
  assert.ok(t < 0.5);
  assert.ok(strideAt(5) > strideAt(1.5));
});

test('music: held a while, urgent moods cut in, no repeat, rest after a piece ends', () => {
  const m = new MusicPicker({ day: ['d1', 'd2', 'd3'], town: ['t1'], fight: ['f1', 'f2'] }, 3, { hold: 30, urgent: ['fight'], rest: 40 });
  const first = m.want('day', 0);
  assert.ok(first && first.startsWith('d'));
  assert.equal(m.want('day', 5), undefined);
  // Into town too soon: held.
  assert.equal(m.want('town', 10), undefined);
  assert.equal(m.want('town', 31), 't1');
  // A fight cuts in at once, and lingers only briefly after.
  assert.ok(m.want('fight', 32)?.startsWith('f'));
  assert.equal(m.want('town', 35), undefined);
  assert.equal(m.want('town', 41), 't1');
  // A piece that ends leaves a rest before the next of its mood; never the same day piece twice running.
  m.ended(100);
  assert.equal(m.want('town', 110), undefined);
  assert.equal(m.want('town', 141), 't1');
  const days: string[] = [];
  for (let i = 0; i < 6; i++) { m.ended(200 + i * 100); days.push(m.want('day', 250 + i * 100) as string); }
  for (let i = 1; i < days.length; i++) assert.notEqual(days[i], days[i - 1]);
  // No mood: fade out.
  assert.equal(m.want(null, 1000), null);
  assert.equal(m.piece, null);
});

test('room echo: silent lead, decays by its T60', () => {
  const rate = 8000, x = roomImpulse(rate, 1, 0.02, 0);
  assert.equal(x.length, Math.ceil(1.02 * rate));
  assert.equal(x[10], 0);
  const rms = (a: number, b: number) => Math.sqrt(x.slice(a, b).reduce((s, v) => s + v * v, 0) / (b - a));
  assert.ok(rms(200, 1000) > 30 * rms(7000, 8000));
  assert.deepEqual(roomImpulse(rate, 1, 0.02, 1), roomImpulse(rate, 1, 0.02, 1));
});
