import { test } from 'node:test';
import assert from 'node:assert/strict';
import { BoxGeometry, Matrix4, MeshBasicNodeMaterial, PerspectiveCamera, Vector3 } from 'three/webgpu';
import { CpuInstanceDraws, RECORD, KIND, DITHER, FRAME, frameAt, inLod, listLayout, listsInUse, recordSphere, sphereVisible, worldMatrix } from '../src/index';

test('a level holds from near up to far, and dithers out over its fade', () => {
  const l = { near: 10, far: 100, fade: [60, 100] as const };
  assert.equal(inLod(l, 5, 0.5), false);
  assert.equal(inLod(l, 10, 0), true);
  assert.equal(inLod(l, 50, 0), true);
  assert.equal(inLod(l, 80, 0.9), true);
  assert.equal(inLod(l, 80, 0.1), false);
  assert.equal(inLod(l, 100, 0.99), false);
  assert.equal(inLod({ far: 20 }, 19.9, 0), true);
});

test('lists get room for every instance of their kind', () => {
  assert.deepEqual(listLayout([3, 0, 5], [2, 1, 1]), { base: [0, 3, 6, 6], cap: [3, 3, 0, 5], total: 11 });
});

test('spheres against the frustum, and shadow casters behind it', () => {
  // One plane facing +z through the origin, the rest far away.
  const planes = [0, 0, 1, 0, ...Array(20).fill(0).map((_, i) => (i % 4 === 3 ? 1e6 : 0))];
  assert.equal(sphereVisible(planes, 0, 0, 5, 1), true);
  assert.equal(sphereVisible(planes, 0, 0, -0.5, 1), true);
  assert.equal(sphereVisible(planes, 0, 0, -5, 1), false);
  // Light shining towards +z: a caster behind the plane throws its shadow into the view.
  assert.equal(sphereVisible(planes, 0, 0, -5, 1, [0, 0, 10]), true);
  assert.equal(sphereVisible(planes, 0, 0, -5, 1, [0, 0, -10]), false);
});

test('a record sphere follows its matrix (scale and offset)', () => {
  const m = new Matrix4().makeScale(2, 2, 2).setPosition(10, 0, 0);
  const rec = new Float32Array(RECORD);
  rec.set(m.elements);
  assert.deepEqual(recordSphere(rec, 0, [0, 1, 0, 3]), [10, 2, 0, 6]);
});

test('the CPU path puts each instance into the parts of its levels', async () => {
  const geo = new BoxGeometry(), mat = new MeshBasicNodeMaterial();
  const kinds = [
    { lods: [{ far: 50, parts: [{ geometry: geo, material: mat }, { geometry: geo, material: mat }] }, { near: 50, far: 500, parts: [{ geometry: geo, material: mat }] }] },
    { lods: [{ far: 50, parts: [{ geometry: geo, material: mat }] }] },
  ];
  const draws = new CpuInstanceDraws(kinds, { horizontal: true });
  const xs = [[0, 10, 0], [0, 100, 0], [1, 10, 0], [1, 100, 0], [0, 600, 0]];
  const data = new Float32Array(xs.length * RECORD);
  xs.forEach(([k, x, h], i) => {
    data.set(new Matrix4().setPosition(x, 50, 0).elements, i * RECORD);
    data[i * RECORD + KIND] = k;
    data[i * RECORD + DITHER] = h;
  });
  draws.set(data, xs.length);
  const cam = new PerspectiveCamera();
  draws.update(cam);
  assert.deepEqual(await draws.counts(), [1, 1, 1, 1]);
  assert.equal(draws.group.children.length, 4);
});

test('the CPU path keeps its counts when frames run while shaders build', async () => {
  const geo = new BoxGeometry(), mat = new MeshBasicNodeMaterial();
  const draws = new CpuInstanceDraws([{ lods: [{ far: 50, parts: [{ geometry: geo, material: mat }] }] }, { lods: [{ far: 50, parts: [{ geometry: geo, material: mat }] }] }]);
  const data = new Float32Array(RECORD);
  data.set(new Matrix4().elements);
  draws.set(data, 1);
  const cam = new PerspectiveCamera();
  const counts = () => draws.group.children.map((m) => (m as unknown as { geometry: { instanceCount: number } }).geometry.instanceCount);
  await draws.prepare(async () => {
    draws.update(cam); // the game loop runs meanwhile
    assert.deepEqual(counts(), [1, 1]);
  });
  assert.deepEqual(counts(), [1, 0]);
  draws.update(cam);
  assert.deepEqual(counts(), [1, 0]);
});

test('the CPU path draws relative to a floating origin, and writes again when it steps', () => {
  const geo = new BoxGeometry(), mat = new MeshBasicNodeMaterial();
  const origin = new Vector3(299520, 0, -299520);
  const draws = new CpuInstanceDraws([{ lods: [{ far: 50, parts: [{ geometry: geo, material: mat }] }] }], { horizontal: true, origin });
  const data = new Float32Array(RECORD);
  data.set(new Matrix4().setPosition(299530.5, 20, -299510.25).elements);
  draws.set(data, 1);
  const cam = new PerspectiveCamera();
  cam.position.set(299525, 22, -299515);
  const drawn = () => {
    const a = (draws.group.children[0] as unknown as { geometry: { getAttribute(n: string): { data: { array: Float32Array } } } }).geometry.getAttribute('iM3').data.array;
    return [a[12], a[13], a[14]];
  };
  draws.update(cam);
  assert.deepEqual(drawn(), [10.5, 20, 9.75], 'distance chosen in world space, drawn relative to the origin');
  origin.set(298240, 0, -299520);
  draws.update(cam);
  assert.deepEqual(drawn(), [1290.5, 20, 9.75], 'the origin stepped: written again without the camera moving');
});

test('a level list is in use only while an instance of its kind is within its range (give or take the slack)', () => {
  // Kind 0: levels [0, 50) and [50, 500); kind 1: one level [0, 500); kind 2: none placed.
  const ranges = [{ far: 50 }, { near: 50, far: 500 }, { far: 500 }, { far: 500 }];
  const local: [number, number, number, number][] = [[0, 0, 0, 1], [0, 0, 0, 1], [0, 0, 0, 1]];
  const rec = new Float32Array(RECORD * 2);
  const put = (i: number, x: number, kind: number) => { rec.set(new Matrix4().setPosition(x, 0, 0).elements, i * RECORD); rec[i * RECORD + KIND] = kind; };
  put(0, 100, 0); put(1, 30, 1);
  assert.deepEqual(listsInUse(rec, 2, local, ranges, [2, 1, 1], [0, 0, 0], true, 8), [false, true, true, false]);
  // Within the slack of the near level's edge: in use.
  put(0, 55, 0);
  assert.deepEqual(listsInUse(rec, 2, local, ranges, [2, 1, 1], [0, 0, 0], true, 8), [true, true, true, false]);
  // Only `count` records count.
  assert.deepEqual(listsInUse(rec, 1, local, ranges, [2, 1, 1], [0, 0, 0], true, 8), [true, true, false, false]);
});

test('a record in a moving frame is in the world where its frame carries it; frame 0 is the world', () => {
  const ship = new Matrix4().makeRotationY(Math.PI / 2).setPosition(1000, 2, 500);
  const frames = new Float64Array(ship.elements);
  const rec = new Float32Array(RECORD * 2);
  rec.set(new Matrix4().setPosition(3, 1, 0).elements, 0);
  rec[FRAME] = 1;
  rec.set(new Matrix4().setPosition(3, 1, 0).elements, RECORD);
  assert.equal(frameAt(rec, 0, frames), 0);
  assert.equal(frameAt(rec, RECORD, frames), -1, 'frame 0: the world');
  assert.equal(frameAt(rec, 0, undefined), -1, 'no frames given: the world');
  const m = new Float64Array(16);
  worldMatrix(rec, 0, frames, m);
  // Turned a quarter round y, 3 m along her x is 3 m along the world's -z.
  assert.deepEqual([...m.slice(12, 15)].map((v) => Math.round(v * 1e6) / 1e6), [1000, 3, 497]);
  assert.deepEqual(recordSphere(rec, 0, [0, 0, 0, 1], frames).map((v) => Math.round(v * 1e6) / 1e6), [1000, 3, 497, 1]);
  assert.deepEqual(recordSphere(rec, RECORD, [0, 0, 0, 1], frames), [3, 1, 0, 1]);
  // The lists in use measure from where the frame has carried it.
  assert.deepEqual(listsInUse(rec, 1, [[0, 0, 0, 1]], [{ far: 50 }, { near: 50, far: 5000 }], [2], [1000, 0, 500], true, 1, frames), [true, false]);
});

test('the CPU path carries framed instances with their frame each update, without set, and chooses levels where they are', () => {
  const geo = new BoxGeometry(), mat = new MeshBasicNodeMaterial();
  const ship = new Matrix4().setPosition(5000, 0, 0);
  const origin = new Vector3(4096, 0, 0);
  const draws = new CpuInstanceDraws([{ lods: [{ far: 50, parts: [{ geometry: geo, material: mat }] }, { near: 50, far: 900, parts: [{ geometry: geo, material: mat }] }] }], { horizontal: true, frames: [ship], origin });
  const data = new Float32Array(RECORD * 2);
  data.set(new Matrix4().setPosition(2, 1, 0).elements, 0);
  data[FRAME] = 1;
  data.set(new Matrix4().setPosition(4100, 0, 0).elements, RECORD); // a world record beside her
  draws.set(data, 2);
  const cam = new PerspectiveCamera();
  cam.position.set(4990, 3, 0);
  const near = (i: number) => (draws.group.children[i] as unknown as { geometry: { instanceCount: number; getAttribute(n: string): { data: { array: Float32Array } } } }).geometry;
  draws.update(cam);
  assert.equal(near(0).instanceCount, 1, 'her fitting: near level (12 m off)');
  assert.equal(near(1).instanceCount, 1, 'the world record: far level (890 m off)');
  assert.deepEqual([...near(0).getAttribute('iM3').data.array.slice(12, 15)], [906, 1, 0], 'drawn relative to the origin');
  // She heels 0.2 rad round her length (x) and moves 1 m: the fitting follows, no set needed.
  ship.makeRotationX(0.2).setPosition(5001, 0, 0);
  draws.update(cam);
  const a = near(0).getAttribute('iM3').data.array;
  assert.deepEqual([a[12], a[13], a[14]].map((v) => Math.round(v * 1e4) / 1e4), [907, Math.round(Math.cos(0.2) * 1e4) / 1e4, Math.round(Math.sin(0.2) * 1e4) / 1e4]);
  assert.equal(Math.round(a[5] * 1e4) / 1e4, Math.round(Math.cos(0.2) * 1e4) / 1e4, 'turned with her');
  // She sails off: once she is 50 m away her fitting takes the far level, the camera never having moved.
  ship.identity().setPosition(5100, 0, 0);
  draws.update(cam);
  assert.equal(near(0).instanceCount, 0);
  assert.equal(near(1).instanceCount, 2);
});
