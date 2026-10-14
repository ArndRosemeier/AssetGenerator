import { test } from 'node:test';
import assert from 'node:assert/strict';
import { deriveSeed, hash32, Rng, Noise, MinHeap, clamp, smin } from '../src/index';

// Values pinned on 2026-10-14 from Scale's copy: a change here changes every world built from a seed.
test('deriveSeed and hash32 are stable', () => {
  assert.equal(hash32(1), hash32(1));
  assert.equal(deriveSeed(42, 'level', 3), deriveSeed(42, 'level', 3));
  assert.notEqual(deriveSeed(42, 'level', 3), deriveSeed(42, 'level', 4));
  assert.equal(deriveSeed(1, 'a'), PINNED.derive1a);
});

test('Rng streams are deterministic and in range', () => {
  const a = new Rng(7), b = new Rng(7);
  for (let i = 0; i < 1000; i++) {
    const x = a.float();
    assert.equal(x, b.float());
    assert.ok(x >= 0 && x < 1);
  }
  assert.equal(new Rng(7).nextU32(), PINNED.rng7);
});

test('Noise is deterministic and roughly in [-1, 1]', () => {
  const n = new Noise(123), m = new Noise(123);
  let lo = Infinity, hi = -Infinity;
  for (let i = 0; i < 2000; i++) {
    const v = n.n3(i * 0.37, i * 0.11, -i * 0.23);
    assert.equal(v, m.n3(i * 0.37, i * 0.11, -i * 0.23));
    lo = Math.min(lo, v); hi = Math.max(hi, v);
  }
  assert.ok(lo >= -1.01 && hi <= 1.01, `${lo}..${hi}`);
});

test('MinHeap pops in priority order', () => {
  const h = new MinHeap();
  const r = new Rng(1);
  for (let i = 0; i < 200; i++) h.push(r.float(), i);
  let last = -Infinity;
  while (h.size) {
    const p = h.peekPriority();
    assert.ok(p >= last);
    last = p;
    h.pop();
  }
});

test('math helpers', () => {
  assert.equal(clamp(5, 0, 1), 1);
  assert.ok(smin(0, 0, 1) < 0);
});

const PINNED = { derive1a: 2134813601, rng7: 4244348465 };
