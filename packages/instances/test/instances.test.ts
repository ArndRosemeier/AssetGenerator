import { test } from 'node:test';
import assert from 'node:assert/strict';
import { BoxGeometry, Matrix4, MeshBasicNodeMaterial, PerspectiveCamera, Vector3 } from 'three/webgpu';
import { CpuInstanceDraws, RECORD, KIND, DITHER, inLod, listLayout, recordSphere, sphereVisible } from '../src/index';

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
