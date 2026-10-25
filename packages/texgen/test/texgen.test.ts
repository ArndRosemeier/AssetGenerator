import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  GROUND_LAYER_COUNT, MEDIEVAL_LAYER_COUNT, MEDIEVAL_NAMES, NATURAL_LAYER_COUNT, NATURAL_NAMES, NATURAL_TILE_METERS,
  generateGroundLayer, generateMedievalLayer, generateNaturalLayer,
} from '../src/index';

const N = 64;

/** Mean albedo difference across the wrap seam vs between neighbouring interior rows/columns. */
function seam(a: Uint8Array, n: number): { wrap: number; inner: number } {
  let wrap = 0, inner = 0;
  for (let i = 0; i < n; i++) {
    for (let c = 0; c < 3; c++) {
      wrap += Math.abs(a[(i * n + n - 1) * 4 + c] - a[(i * n) * 4 + c]);
      wrap += Math.abs(a[((n - 1) * n + i) * 4 + c] - a[i * 4 + c]);
      inner += Math.abs(a[(i * n + n / 2) * 4 + c] - a[(i * n + n / 2 - 1) * 4 + c]);
      inner += Math.abs(a[((n / 2) * n + i) * 4 + c] - a[((n / 2 - 1) * n + i) * 4 + c]);
    }
  }
  return { wrap, inner };
}

test('natural layers: names, tile sizes and count agree', () => {
  assert.equal(NATURAL_NAMES.length, NATURAL_LAYER_COUNT);
  assert.equal(NATURAL_TILE_METERS.length, NATURAL_LAYER_COUNT);
  assert.ok(NATURAL_LAYER_COUNT >= 8);
  assert.ok(NATURAL_TILE_METERS.every((m) => m > 0));
});

for (let i = 0; i < NATURAL_LAYER_COUNT; i++) {
  test(`natural layer ${NATURAL_NAMES[i]}: size, determinism, seamless wrap, not flat`, () => {
    const a = generateNaturalLayer(i, N), b = generateNaturalLayer(i, N);
    assert.equal(a.albedo.length, N * N * 4);
    assert.equal(a.normal.length, N * N * 4);
    assert.deepEqual(a.albedo, b.albedo);
    assert.deepEqual(a.normal, b.normal);
    const s = seam(a.albedo, N);
    assert.ok(s.wrap < s.inner * 2.5 + N, `seam ${s.wrap} vs interior ${s.inner}`);
    let min = 255, max = 0;
    for (let p = 0; p < N * N; p++) { const v = a.albedo[p * 4 + 1]; min = Math.min(min, v); max = Math.max(max, v); }
    assert.ok(max - min > 10, 'layer has visible variation');
  });
}

for (let i = 0; i < MEDIEVAL_LAYER_COUNT; i++) {
  test(`medieval layer ${MEDIEVAL_NAMES[i]}: size, determinism, seamless wrap, not flat`, () => {
    const a = generateMedievalLayer(i, N), b = generateMedievalLayer(i, N);
    assert.equal(a.albedo.length, N * N * 4);
    assert.deepEqual(a.albedo, b.albedo);
    const s = seam(a.albedo, N);
    assert.ok(s.wrap < s.inner * 2.5 + N, `seam ${s.wrap} vs interior ${s.inner}`);
    let min = 255, max = 0;
    for (let p = 0; p < N * N; p++) { const v = a.albedo[p * 4 + 1]; min = Math.min(min, v); max = Math.max(max, v); }
    assert.ok(max - min > 10, 'layer has visible variation');
  });
}

test('out of range layer throws', () => {
  assert.throws(() => generateNaturalLayer(NATURAL_LAYER_COUNT, N));
  assert.throws(() => generateGroundLayer(GROUND_LAYER_COUNT, N));
});
