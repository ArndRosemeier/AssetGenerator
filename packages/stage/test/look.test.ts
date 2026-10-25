import { test } from 'node:test';
import assert from 'node:assert/strict';
import { gradeAt, type GradeKey } from '../src/look';

const keys: GradeKey[] = [
  { at: -0.2, slope: [0.9, 0.95, 1.1], saturation: 0.9 },
  { at: 0.1, slope: [1.1, 1, 0.9], saturation: 1.3 },
  { at: 0.6, slope: [1, 1, 1], saturation: 1.2 },
];

test('gradeAt holds the end keys and hits each key exactly', () => {
  assert.deepEqual(gradeAt(keys, -1), { slope: [0.9, 0.95, 1.1], saturation: 0.9 });
  assert.deepEqual(gradeAt(keys, 1), { slope: [1, 1, 1], saturation: 1.2 });
  assert.equal(gradeAt(keys, 0.1).saturation, 1.3);
  assert.deepEqual(gradeAt([], 0), { slope: [1, 1, 1], saturation: 1 });
});

test('gradeAt blends smoothly between keys', () => {
  const mid = gradeAt(keys, 0.35);
  assert.ok(Math.abs(mid.saturation - 1.25) < 1e-9);
  assert.ok(gradeAt(keys, 0.12).saturation > 1.29);
});
