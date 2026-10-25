import { test } from 'node:test';
import assert from 'node:assert/strict';
import { CLEAR, moonAt, moonPhase, skyLight, skyPath, starField, sunTransmittance } from '../src/path';

const len = (v: number[]) => Math.hypot(v[0], v[1], v[2]);

test('sky path: unit vectors, up by day, down at night, highest near noon', () => {
  for (let h = 0; h < 24; h += 0.5) assert.ok(Math.abs(len(skyPath(h)) - 1) < 1e-9);
  assert.ok(skyPath(12)[1] > 0.5);
  assert.ok(skyPath(0)[1] < -0.5);
  assert.ok(skyPath(12)[1] > skyPath(9)[1] && skyPath(12)[1] > skyPath(15)[1]);
});

test('moon: phase wraps 0..1, full moon is lit, new moon dark', () => {
  for (let t = -1000; t < 1000; t += 37) { const p = moonPhase(t); assert.ok(p >= 0 && p < 1); }
  const sun = skyPath(12);
  const m = moonAt(12, 0, sun);
  assert.ok(Math.abs(len(m.dir) - 1) < 1e-9 && Math.abs(len(m.sunSide) - 1) < 1e-6);
  assert.ok(m.lit >= 0 && m.lit <= 1);
});

test('sky light: bright day, dark night, golden hour in between', () => {
  const noon = skyPath(12), dusk = skyPath(17.6), night = skyPath(0);
  const d = skyLight(noon, moonAt(12, 12, noon)), g = skyLight(dusk, moonAt(17.6, 17.6, dusk)), n = skyLight(night, moonAt(0, 24, night));
  assert.ok(d.day > 0.99 && n.night > 0.99);
  assert.ok(d.lightIntensity > n.lightIntensity * 5);
  assert.ok(g.golden > d.golden);
  assert.ok(n.stars > 0.5 && d.stars === 0);
  const storm = skyLight(noon, moonAt(12, 12, noon), { ...CLEAR, cover: 1, dark: 1, sun: 0.2 });
  assert.ok(storm.lightIntensity < d.lightIntensity && storm.overcast > 0.8);
});

test('star field: seeded and on the upper dome', () => {
  const a = starField(5, 100), b = starField(5, 100), c = starField(6, 100);
  assert.deepEqual(a.position, b.position);
  assert.notDeepEqual(a.position, c.position);
  for (let i = 0; i < 100; i++) assert.ok(a.position[i * 3 + 1] >= 0);
});

test('sun light: about white at noon, warmer and dimmer towards the horizon, and the ground throws some back', () => {
  const noon = skyLight(skyPath(12), moonAt(12, 12, skyPath(12)));
  const late = skyLight(skyPath(17.4), moonAt(17.4, 17.4, skyPath(17.4)));
  const c = noon.lightColor, w = late.lightColor;
  assert.ok(c[2] / c[0] > 0.8, 'noon is not far from white');
  assert.ok(w[2] / w[0] < c[2] / c[0] && w[1] / w[0] < c[1] / c[0], 'evening light is warmer');
  assert.ok(w[0] + w[1] + w[2] < c[0] + c[1] + c[2], 'and dimmer');
  assert.deepEqual(sunTransmittance(1).map((v) => +v.toFixed(6)), [1, 1, 1]);
  assert.ok(noon.bounce[1] > late.bounce[1] && noon.bounce[1] > 0);
});
