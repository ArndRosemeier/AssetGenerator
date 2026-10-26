import { test } from 'node:test';
import assert from 'node:assert/strict';
import { roadProfile, routeRoad, type RouteSite } from '../src/index';

/** A ridge across x = 0 with a saddle at z = 300, and a river along x = 400 with a ford at z = -200. */
const land = (seed: number): RouteSite => ({
  seed,
  height: (x, z) => 20 + 60 * Math.exp(-(x * x) / (2 * 80 * 80)) * (1 - 0.8 * Math.exp(-((z - 300) ** 2) / (2 * 90 * 90))),
  water: (x, z) => (Math.abs(x - 400) < 10 ? (Math.abs(z + 200) < 30 ? 0.4 : 2) : 0),
});

test('route: the same land gives the same road, another seed another one', () => {
  const a = routeRoad(land(1), [-500, 0], [300, 0]);
  assert.ok(a);
  assert.deepEqual(a, routeRoad(land(1), [-500, 0], [300, 0]));
  assert.notDeepEqual(a.pts, routeRoad(land(2), [-500, 0], [300, 0])!.pts);
});

test('route: over a ridge the road goes by the saddle, ends exact, points evenly spaced', () => {
  const r = routeRoad(land(3), [-500, 0], [300, 0])!;
  assert.deepEqual(r.pts.slice(0, 2), [-500, 0]);
  assert.deepEqual(r.pts.slice(-2), [300, 0]);
  // Where it crosses the ridge line (x = 0) it is near the saddle.
  let crossZ = NaN;
  for (let k = 2; k < r.pts.length; k += 2) if (r.pts[k - 2] < 0 && r.pts[k] >= 0) crossZ = r.pts[k + 1];
  assert.ok(Math.abs(crossZ - 300) < 120, `crosses at z ${crossZ.toFixed(0)}`);
  for (let k = 2; k < r.pts.length; k += 2) assert.ok(Math.abs(Math.hypot(r.pts[k] - r.pts[k - 2], r.pts[k + 1] - r.pts[k - 1]) - 6) < 0.6);
});

test('route: a river is crossed at its ford; blocked ground and deep water stop it', () => {
  const r = routeRoad(land(4), [300, 0], [500, 0])!;
  assert.ok(r.fords > 0);
  let crossZ = NaN;
  for (let k = 2; k < r.pts.length; k += 2) if (r.pts[k - 2] < 400 && r.pts[k] >= 400) crossZ = r.pts[k + 1];
  assert.ok(Math.abs(crossZ + 200) < 40, `fords at z ${crossZ.toFixed(0)}`);
  const deep: RouteSite = { ...land(4), water: (x) => (Math.abs(x - 400) < 10 ? 2 : 0) };
  assert.equal(routeRoad(deep, [300, 0], [500, 0], { margin: 200 }), null);
  const walled: RouteSite = { ...land(4), water: () => 0, blocked: (x, z) => Math.abs(x - 400) < 10 && z > -150 };
  const w = routeRoad(walled, [300, 0], [500, 0], { margin: 300 })!;
  for (let k = 0; k < w.pts.length; k += 2) assert.ok(!(Math.abs(w.pts[k] - 400) < 6 && w.pts[k + 1] > -140));
});

test('route: the profile eases over bumps and meets the ground at both ends', () => {
  const pts: number[] = [];
  for (let x = 0; x <= 300; x += 6) pts.push(x, 0);
  const h = (x: number) => 10 + (Math.abs(x - 150) < 6 ? 3 : 0);
  const ys = roadProfile(pts, h);
  assert.equal(ys[0], 10);
  assert.equal(ys[ys.length - 1], 10);
  const top = ys[25];
  assert.ok(top > 10 && top < 11.5, `bump flattened to ${top}`);
});

test('route: a 3 km road is found quickly', () => {
  const t0 = performance.now();
  const r = routeRoad(land(5), [-1500, -1000], [1500, 800]);
  assert.ok(r);
  assert.ok(performance.now() - t0 < 2000, `${(performance.now() - t0).toFixed(0)} ms`);
});
