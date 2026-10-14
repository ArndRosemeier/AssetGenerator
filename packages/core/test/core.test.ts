import { test } from 'node:test';
import assert from 'node:assert/strict';
import { deriveSeed, hash32, Rng, Noise, MinHeap, clamp, smin, cellular2, cellular3, cellBorder } from '../src/index';

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

test('cellular results name the second nearest cell, and cellBorder is the exact Voronoi border distance', () => {
  for (let i = 0; i < 500; i++) {
    const x = i * 0.173 - 20, y = i * 0.291 - 30;
    const r = cellular2(9, x, y, 0.85);
    assert.notEqual(r.id2, r.id);
    assert.ok(Math.abs(Math.hypot(r.px2 - x, r.py2 - y) - r.f2) < 1e-9);
    // Walking b towards the second feature reaches the bisector: both features equally far.
    const b = cellBorder(r);
    assert.ok(b >= (r.f2 - r.f1) / 2 - 1e-9);
    const dx = r.px2 - r.px, dy = r.py2 - r.py, len = Math.hypot(dx, dy);
    const qx = x + (dx / len) * b, qy = y + (dy / len) * b;
    assert.ok(Math.abs(Math.hypot(qx - r.px, qy - r.py) - Math.hypot(qx - r.px2, qy - r.py2)) < 1e-9);
  }
  const r3 = cellular3(4, 1.3, 2.7, -0.4);
  assert.ok(Math.abs(Math.hypot(r3.px2 - 1.3, r3.py2 - 2.7, r3.pz2 + 0.4) - r3.f2) < 1e-9);
});
