import { test } from 'node:test';
import assert from 'node:assert/strict';
import { ShaderCap } from '../src/cap';

/** A fake clock with 60 fps frames: every requested frame callback runs 16.7 ms later. */
function sim() {
  let t = 0;
  const frames: (() => void)[] = [];
  const cap = new ShaderCap(() => t, (fn) => frames.push(fn));
  const step = () => { t += 1000 / 60; cap.newFrame(); const f = frames.splice(0); for (const fn of f) fn(); };
  return { cap, step, now: () => t };
}

test('warm-up: no cap while inactive', async () => {
  const { cap } = sim();
  for (let i = 0; i < 20; i++) await cap.slot();
});

test('active: at most 5 per second, at least 200 ms apart, one per frame', async () => {
  const { cap, step, now } = sim();
  cap.active = true;
  const starts: number[] = [];
  let pending = 0;
  for (let i = 0; i < 20; i++) { pending++; void cap.slot().then(() => { starts.push(now()); pending--; }); }
  for (let f = 0; f < 60 * 6 && pending; f++) { step(); await Promise.resolve(); }
  assert.equal(starts.length, 20);
  for (let i = 1; i < starts.length; i++) assert.ok(starts[i] - starts[i - 1] >= 200 - 1e-6, `gap ${starts[i] - starts[i - 1]}`);
  for (const s of starts) assert.ok(starts.filter((x) => x > s - 1000 && x <= s).length <= 5);
});
