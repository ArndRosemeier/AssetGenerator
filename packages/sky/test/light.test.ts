import { test } from 'node:test';
import assert from 'node:assert/strict';
import { CLEAR, moonAt, skyLight, skyPath } from '../src/path';
import { EYE_ADAPT, RIG_GAIN, SUN_ADAPT_MAX, adaptedSun, eyeAdapt, lowSunSky, skyFill } from '../src/light';

const lightAt = (hour: number, wx = CLEAR) => { const sun = skyPath(hour); return skyLight(sun, moonAt(hour, hour, sun), wx); };

test('the low sun keeps the sky bright: 1 at the top of the table, more as it sinks, at most 3x', () => {
  assert.equal(lowSunSky(0.7), 1);
  assert.equal(lowSunSky(0.9), 1);
  let last = 1;
  for (let up = 0.7; up >= 0; up -= 0.05) { const k = lowSunSky(up); assert.ok(k >= last - 1e-12); last = k; }
  assert.equal(lowSunSky(-0.3), 3);
});

test('the eye lifts the dimmed low sun, never more than SUN_ADAPT_MAX', () => {
  const noon = lightAt(12), low = lightAt(6.4);
  assert.ok(adaptedSun(noon) > 0);
  assert.ok(adaptedSun(low) / (low.lightIntensity * RIG_GAIN) > adaptedSun(noon) / (noon.lightIntensity * RIG_GAIN));
  for (let h = 0; h < 24; h += 0.25) { const L = lightAt(h); assert.ok(adaptedSun(L) <= L.lightIntensity * RIG_GAIN * SUN_ADAPT_MAX + 1e-12); }
});

test('the sky fill is dark by day, a little blue at night, and lightning lights it', () => {
  assert.ok(skyFill(lightAt(12), 0).every((c) => c < 1e-3));
  const night = skyFill(lightAt(0), 0);
  assert.ok(night[2] > night[0] && night[0] > 0);
  assert.ok(skyFill(lightAt(0), 1)[2] > night[2] + 0.5);
});

test('the eye adapts over about a second, and at once on the first frame', () => {
  assert.equal(eyeAdapt(-1, 2, 0.016), 2);
  assert.equal(eyeAdapt(1, 2, 0), 2);
  const step = eyeAdapt(1, 2, 0.1);
  assert.ok(Math.abs(step - (1 + 0.1 * EYE_ADAPT)) < 1e-12);
  assert.equal(eyeAdapt(1, 2, 1), 2);
});
