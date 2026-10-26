import { test } from 'node:test';
import assert from 'node:assert/strict';
import { Group, Matrix4, PerspectiveCamera, Scene, Vector3 } from 'three/webgpu';
import { FloatingOrigin } from '../src/origin';

test('FloatingOrigin: moves in whole grains, only once the camera strays past reach', () => {
  const o = new FloatingOrigin({ grain: 1280 });
  assert.equal(o.moveTo(-32010, 31990), true);
  assert.deepEqual(o.at.toArray(), [-32000, 0, 32000]);
  assert.equal(o.follow(-32000 + 1279, 32000 - 1280), false, 'within reach on both axes');
  assert.equal(o.steps, 1);
  assert.equal(o.follow(-32000 + 1281, 32000), true);
  assert.deepEqual(o.at.toArray(), [-30720, 0, 32000], 'snapped to the nearest grain point');
  assert.equal(o.moveTo(-30700, 32010), false, 'the same grain point: no step');
});

test('FloatingOrigin: the scene root stands at minus the origin, pinned objects at the identity', () => {
  const o = new FloatingOrigin({ grain: 1024 });
  const scene = new Scene(), placed = new Group(), gpu = new Group();
  placed.position.set(300123.5, 12, -299876.25);
  scene.add(placed, gpu);
  o.attach(scene);
  o.pin(gpu);
  const moves: number[][] = [];
  o.onMove((dx, dz) => moves.push([dx, dz]));
  o.moveTo(300000, -300000);
  scene.updateMatrixWorld(true);
  const p = new Vector3().setFromMatrixPosition(placed.matrixWorld);
  assert.deepEqual(p.toArray(), [300123.5 - 300032, 12, -299876.25 + 300032], 'relative to the origin (300032 = 293 grains)');
  assert.ok(gpu.matrixWorld.equals(new Matrix4()), 'a pinned object draws at the identity');
  assert.deepEqual(moves, [[300032, -300032]]);
  assert.deepEqual(o.toWorld(p.clone()).toArray(), placed.position.toArray());
});

test('FloatingOrigin.view: the drawn camera keeps the lens and turn, placed relative to the origin', () => {
  const o = new FloatingOrigin();
  o.moveTo(-32768, 32768);
  const cam = new PerspectiveCamera(55, 1.5, 0.2, 1000);
  cam.position.set(-32700.25, 80, 32800.5);
  cam.lookAt(-32600, 70, 32900);
  const drawn = o.view(cam, new PerspectiveCamera());
  assert.deepEqual(drawn.position.toArray(), [67.75, 80, 32.5]);
  assert.ok(drawn.quaternion.equals(cam.quaternion));
  assert.equal(drawn.fov, 55);
  assert.ok(drawn.projectionMatrix.equals(cam.projectionMatrix));
});

/** float32 rounding, as the GPU stores and adds. */
const f = Math.fround;

/**
 * What the shader does with a vertex near the camera: world position = model matrix translation + local vertex,
 * then minus the camera (the view matrix's translation), all in float32. Returns the error against exact math (m).
 */
function viewError(at: number, origin: number): number {
  let worst = 0;
  for (let i = 0; i < 200; i++) {
    const cam = at + i * 0.0137, obj = at + 3.21 + i * 0.0071, local = 0.4321;
    const exact = obj + local - cam;
    const drawn = f(f(f(obj - origin) + f(local)) - f(cam - origin));
    worst = Math.max(worst, Math.abs(drawn - exact));
  }
  return worst;
}

test('float32 near the camera: centimetres off at 300 km from zero without an origin, far below a millimetre with one', () => {
  for (const at of [30000, 300000]) {
    const without = viewError(at, 0), withOrigin = viewError(at, new FloatingOrigin({ grain: 1280 }).snap(at, 0)[0]);
    assert.ok(withOrigin < 1e-4, `${at} m with the origin: ${withOrigin}`);
    assert.ok(without > withOrigin * 20, `${at} m: ${without} without against ${withOrigin} with`);
  }
  assert.ok(viewError(300000, 0) > 0.005, 'without: millimetres to centimetres at 300 km (this is the shimmer)');
});

test('FloatingOrigin.view: the game camera takes the drawn camera\'s depth set-up, so its projection matches', () => {
  const o = new FloatingOrigin();
  const cam = new PerspectiveCamera(55, 1.5, 0.2, 1000), drawn = new PerspectiveCamera();
  o.view(cam, drawn);
  // What the renderer does to the camera it draws (reversed depth, WebGPU's coordinate system).
  (drawn as unknown as { _reversedDepth: boolean })._reversedDepth = true;
  drawn.coordinateSystem = 2001;
  drawn.updateProjectionMatrix();
  const wanted = drawn.projectionMatrix.clone();
  o.view(cam, drawn);
  assert.equal(cam.reversedDepth, true);
  assert.equal(cam.coordinateSystem, 2001);
  assert.ok(drawn.projectionMatrix.equals(wanted), 'the copy keeps the projection the renderer wants');
});
