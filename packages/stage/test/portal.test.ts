import { test } from 'node:test';
import assert from 'node:assert/strict';
import { Matrix4, PerspectiveCamera, type CoordinateSystem, Quaternion, Vector3, Vector4, WebGLCoordinateSystem, WebGPUCoordinateSystem } from 'three/webgpu';
import { clipNear, openingPlane, portalStep, screenRect, throughPortal } from '../src/portal';

/** A frame at (x, y, z), turned by `yaw` round the up axis. */
const frame = (x: number, y: number, z: number, yaw: number) => new Matrix4().compose(new Vector3(x, y, z), new Quaternion().setFromAxisAngle(new Vector3(0, 1, 0), yaw), new Vector3(1, 1, 1));

const camera = (system: CoordinateSystem, reversed: boolean) => {
  const c = new PerspectiveCamera(55, 16 / 9, 0.2, 120000);
  (c as unknown as { _reversedDepth: boolean })._reversedDepth = reversed;
  c.coordinateSystem = system;
  c.updateProjectionMatrix();
  return c;
};

test('portal: a point behind the near opening is seen at the same spot behind the far one', () => {
  const from = frame(10, 2, 5, 0.3), to = frame(-400, -380, 90, 2.1);
  const local = new Vector3(0.4, 1.2, -2);
  const p = local.clone().applyMatrix4(from).applyMatrix4(portalStep(from, to));
  const q = local.clone().applyMatrix4(to);
  assert.ok(p.distanceTo(q) < 1e-9);
});

test('portal: the camera through it keeps its place relative to the opening', () => {
  const from = frame(0, 0, 0, 0), to = frame(100, -400, 50, Math.PI / 2);
  const cam = camera(WebGPUCoordinateSystem, true);
  cam.position.set(1, 1.7, 4);
  cam.lookAt(0, 1, -1);
  const out = throughPortal(cam, from, to, new PerspectiveCamera());
  const seen = new Vector3(1, 1.7, 4).applyMatrix4(to);
  assert.ok(out.position.distanceTo(seen) < 1e-9);
  assert.ok(out.projectionMatrix.equals(cam.projectionMatrix));
  assert.equal(out.coordinateSystem, cam.coordinateSystem);
  // A point on the far side shows where its twin behind the near opening would.
  const near = new Vector3(0.2, 1, -3), far = near.clone().applyMatrix4(portalStep(from, to));
  const a = near.clone().project(cam), b = far.clone().project(out);
  assert.ok(Math.abs(a.x - b.x) < 1e-9 && Math.abs(a.y - b.y) < 1e-9);
});

for (const [name, system, reversed] of [['reversed depth', WebGPUCoordinateSystem, true], ['WebGPU', WebGPUCoordinateSystem, false], ['WebGL', WebGLCoordinateSystem, false]] as const) {
  test(`portal: the near plane lies on the opening (${name})`, () => {
    const cam = camera(system, reversed);
    cam.position.set(0, 1.5, 6);
    cam.lookAt(0.5, 1, 0);
    const opening = frame(0, 0, 0, 0.2);
    assert.equal(clipNear(cam, openingPlane(opening)), true);
    const e = cam.projectionMatrix.elements;
    const clip = (p: Vector3) => new Vector4(p.x, p.y, p.z, 1).applyMatrix4(cam.matrixWorldInverse).applyMatrix4(cam.projectionMatrix);
    const lo = system === WebGLCoordinateSystem && !reversed ? -1 : 0;
    const inside = (p: Vector3) => { const c = clip(p); const d = c.z / c.w; return d >= lo - 1e-9 && d <= 1 + 1e-9; };
    // In front of the opening (towards the camera): clipped; just behind it and far behind it: kept.
    assert.equal(inside(new Vector3(0, 1, 2).applyMatrix4(opening)), false);
    assert.equal(inside(new Vector3(0, 1, -0.5).applyMatrix4(opening)), true);
    assert.equal(inside(new Vector3(0, 1, -5000).applyMatrix4(opening)), true);
    // On the opening the depth is the near plane's.
    const on = clip(new Vector3(0.3, 1, 0).applyMatrix4(opening));
    assert.ok(Math.abs(on.z / on.w - (reversed ? 1 : lo)) < 1e-6);
    assert.ok(Number.isFinite(e[10]));
  });
}

test('portal: nothing beyond an opening that faces away is in view', () => {
  const cam = camera(WebGPUCoordinateSystem, true);
  cam.position.set(0, 1.5, 6);
  cam.lookAt(0, 1.5, 20);
  const before = cam.projectionMatrix.clone();
  assert.equal(clipNear(cam, openingPlane(frame(0, 0, 0, 0))), false);
  assert.ok(cam.projectionMatrix.equals(before));
});

test('portal: the opening\'s rectangle on the screen', () => {
  const cam = camera(WebGPUCoordinateSystem, true);
  cam.position.set(0, 1, 5);
  cam.lookAt(0, 1, 0);
  const corners = [new Vector3(-1, 0, 0), new Vector3(1, 0, 0), new Vector3(1, 2, 0), new Vector3(-1, 2, 0)];
  const r = screenRect(corners, cam, 1600, 900)!;
  assert.ok(r.x > 600 && r.x + r.w < 1000 && r.y > 200 && r.y + r.h < 700, JSON.stringify(r));
  assert.equal(screenRect(corners.map((c) => c.clone().add(new Vector3(0, 0, 20))), cam, 1600, 900), null, 'behind the camera');
  assert.deepEqual(screenRect([...corners, new Vector3(0, 1, 30)], cam, 1600, 900), { x: 0, y: 0, w: 1600, h: 900 }, 'wrapping round the eye');
  assert.equal(screenRect(corners.map((c) => c.clone().add(new Vector3(40, 0, 0))), cam, 1600, 900), null, 'off to the side');
});
