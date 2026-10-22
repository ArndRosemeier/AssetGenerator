import { test } from 'node:test';
import assert from 'node:assert/strict';
import { ShaderCap } from '../src/cap';

/** A fake clock with 60 fps frames: every requested frame callback runs 16.7 ms later; `spend` is time a build blocks. */
function sim() {
  let t = 0;
  const frames: (() => void)[] = [];
  const cap = new ShaderCap(() => t, (fn) => frames.push(fn));
  const step = () => { t += 1000 / 60; cap.newFrame(); const f = frames.splice(0); for (const fn of f) fn(); };
  return { cap, step, now: () => t, spend: (ms: number) => { t += ms; } };
}

test('warm-up: no cap while inactive', async () => {
  const { cap } = sim();
  for (let i = 0; i < 20; i++) (await cap.slot())();
});

test('active: builds take at most a third of the time, evenly spaced, one per frame', async () => {
  const { cap, step, now, spend } = sim();
  cap.active = true;
  const cost = [2, 2, 30, 2, 2, 2, 60, 2, 1, 1];
  const runs: { start: number; end: number }[] = [];
  let pending = 0;
  for (const ms of cost) {
    pending++;
    void cap.slot().then((release) => {
      const start = now();
      spend(ms);
      runs.push({ start, end: now() });
      release();
      pending--;
    });
  }
  await new Promise((r) => setImmediate(r)); // the first starts at once
  for (let f = 0; f < 600 && pending; f++) { step(); await new Promise((r) => setImmediate(r)); }
  assert.equal(runs.length, cost.length);
  for (let i = 1; i < runs.length; i++) {
    const a = runs[i - 1], b = runs[i];
    assert.ok(b.start - a.end >= 2 * (a.end - a.start) - 1e-6, `${b.start - a.end} ms after a build of ${a.end - a.start} ms`);
  }
  // Quick builds follow each other a frame apart; a slow one keeps the next waiting twice as long as it took.
  assert.ok(runs[1].start - runs[0].start < 20, `${runs[1].start - runs[0].start} ms`);
  assert.ok(runs[7].start - runs[6].end >= 120, `${runs[7].start - runs[6].end} ms`);
});

test('active: one build per frame, however quick', async () => {
  const { cap, step } = sim();
  cap.active = true;
  let started = 0;
  for (let i = 0; i < 5; i++) void cap.slot().then((release) => { started++; release(); });
  await Promise.resolve();
  assert.equal(started, 1);
  step();
  await Promise.resolve();
  assert.equal(started, 2);
});

test('a slot never given back holds the cap for a second at most', async () => {
  const { cap, step, now } = sim();
  cap.active = true;
  await cap.slot(); // never given back
  let at = -1;
  void cap.slot().then((release) => { at = now(); release(); });
  for (let f = 0; f < 200 && at < 0; f++) { step(); await new Promise((r) => setImmediate(r)); }
  assert.ok(at >= 1000 && at < 1100, `${at}`);
});
