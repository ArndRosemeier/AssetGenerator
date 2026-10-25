// @ts-nocheck -- TSL typings; a browser page (tools/gpu-page.mjs).
// In the browser: the GPU path must draw exactly the instances the rules (select.ts) pick (frustum with
// shadow sweep, levels, dither), the same image as the CPU path, and no WebGPU errors; then times the cull.
import { BoxGeometry, ConeGeometry, Matrix4, Mesh, MeshBasicNodeMaterial, PerspectiveCamera, RenderTarget, Scene, Color, Vector3, Frustum, Quaternion, WebGPURenderer, UnsignedByteType } from 'three/webgpu';
import { attribute, mat4, positionLocal, vec4 } from 'three/tsl';
import { Rng } from '../../../core/src/index';
import { CpuInstanceDraws, GpuInstanceDraws, gpuInstancesSupported, kindSphere, inLod, recordSphere, sphereVisible, viewDistance, RECORD, KIND, DITHER } from '../../src/index';

const log = (s: string) => { document.getElementById('out')!.textContent += s + '\n'; console.log(s); };
const W = 320, H = 200;

function material(color: number): MeshBasicNodeMaterial {
  const m = new MeshBasicNodeMaterial({ color });
  m.positionNode = mat4(attribute('iM0', 'vec4'), attribute('iM1', 'vec4'), attribute('iM2', 'vec4'), attribute('iM3', 'vec4')).mul(vec4(positionLocal, 1)).xyz;
  return m;
}

function kinds() {
  const box = new BoxGeometry(2, 6, 2).translate(0, 3, 0), cone = new ConeGeometry(3, 8, 6).translate(0, 4, 0), small = new BoxGeometry(1, 1, 1);
  const red = material(0xff3030), green = material(0x30ff30), blue = material(0x3030ff), grey = material(0x909090);
  return [
    { lods: [{ far: 60, parts: [{ geometry: box, material: red }, { geometry: cone, material: green }] }, { near: 60, far: 900, fade: [600, 900] as const, parts: [{ geometry: cone, material: blue }] }] },
    { lods: [{ far: 60, parts: [{ geometry: small, material: grey }] }] },
    { lods: [{ far: 300, parts: [{ geometry: cone, material: red }] }, { near: 300, far: 2000, parts: [{ geometry: box, material: blue }] }] },
  ];
}

function records(n: number, seed: number): Float32Array {
  const rng = new Rng(seed), d = new Float32Array(n * RECORD), m = new Matrix4(), q = new Quaternion(), up = new Vector3(0, 1, 0), s = new Vector3();
  for (let i = 0; i < n; i++) {
    const x = rng.range(-1200, 1200), z = rng.range(-1200, 1200), k = rng.int(0, 2);
    m.compose(new Vector3(x, rng.range(-2, 2), z), q.setFromAxisAngle(up, rng.range(0, 6.28)), s.setScalar(rng.range(0.7, 1.4)));
    d.set(m.elements, i * RECORD);
    d[i * RECORD + KIND] = k;
    d[i * RECORD + DITHER] = rng.float();
  }
  return d;
}

/** Per part, what the rules draw (the GPU path's job). */
function expected(ks, d: Float32Array, n: number, cam: PerspectiveCamera, sweep: [number, number, number], horizontal: boolean): number[] {
  const f = new Frustum().setFromProjectionMatrix(new Matrix4().multiplyMatrices(cam.projectionMatrix, cam.matrixWorldInverse), cam.coordinateSystem);
  const planes = f.planes.flatMap((p) => [p.normal.x, p.normal.y, p.normal.z, p.constant]);
  const spheres = ks.map((k) => { const s = kindSphere(k); return [s.center.x, s.center.y, s.center.z, s.radius]; });
  const parts = ks.map((k) => k.lods.map((l) => l.parts.length));
  const first = []; let p = 0;
  ks.forEach((k, ki) => { first[ki] = []; k.lods.forEach((l, li) => { first[ki][li] = p; p += l.parts.length; }); });
  const out = new Array(p).fill(0);
  const c = cam.position.toArray();
  for (let i = 0; i < n; i++) {
    const o = i * RECORD, k = d[o + KIND];
    const [x, y, z, r] = recordSphere(d, o, spheres[k]);
    if (!sphereVisible(planes, x, y, z, r, sweep)) continue;
    const dist = viewDistance(c, x, y, z, horizontal);
    ks[k].lods.forEach((l, li) => { if (inLod(l, dist, d[o + DITHER])) for (let q = 0; q < parts[k][li]; q++) out[first[k][li] + q]++; });
  }
  return out;
}

async function pixels(renderer, scene, cam, rt): Promise<Uint8Array> {
  renderer.setRenderTarget(rt);
  renderer.render(scene, cam);
  renderer.setRenderTarget(null);
  return new Uint8Array(await renderer.readRenderTargetPixelsAsync(rt, 0, 0, W, H));
}

async function main() {
  const renderer = new WebGPURenderer({ antialias: false });
  renderer.setSize(W, H);
  document.body.appendChild(renderer.domElement);
  await renderer.init();
  const device = renderer.backend.device;
  const errors: string[] = [];
  device?.addEventListener('uncapturederror', (e) => errors.push(e.error.message));
  if (!gpuInstancesSupported(renderer)) {
    window.__result = { match: false, error: `GPU path not supported (webgpu ${!!renderer.backend.isWebGPUBackend}, indirect-first-instance ${!!device?.features?.has('indirect-first-instance')})` };
    return;
  }
  const ks = kinds(), N = 20000, data = records(N, 7);
  const cam = new PerspectiveCamera(60, W / H, 0.5, 5000);
  cam.position.set(30, 25, -40);
  cam.lookAt(200, 0, 300);
  cam.updateMatrixWorld();
  const dir = new Vector3(0.3, -1, 0.5).normalize(), reach = 40;
  const sweep = dir.clone().multiplyScalar(reach).toArray() as [number, number, number];
  const gpu = new GpuInstanceDraws(renderer, ks, { horizontal: true, shadow: { dir, reach }, capacity: 1024 });
  const rt = new RenderTarget(W, H, { type: UnsignedByteType, depthBuffer: true });
  const scene = new Scene();
  scene.background = new Color(0x000000);
  scene.add(gpu.group);
  // Drawn once with a few instances first, so the buffers grow under live draws (as when flying into new woods).
  gpu.set(data, 500);
  await gpu.ready();
  gpu.update(cam);
  await pixels(renderer, scene, cam, rt);
  gpu.set(data, N); // grows from 1024
  gpu.update(cam);
  const got = await gpu.counts(), want = expected(ks, data, N, cam, sweep, true);
  log(`counts gpu ${got.join(' ')}`);
  log(`counts cpu ${want.join(' ')}`);
  // f32 against f64 at range and plane edges: a few instances either way.
  const countsOk = got.every((g, i) => Math.abs(g - want[i]) <= 2);

  // Same image as the CPU path (which draws every level whole; the view culling must not take anything visible).
  const a = await pixels(renderer, scene, cam, rt);
  scene.remove(gpu.group);
  const cpu = new CpuInstanceDraws(ks, { horizontal: true });
  cpu.set(data, N);
  cpu.update(cam);
  scene.add(cpu.group);
  const b = await pixels(renderer, scene, cam, rt);
  let lit = 0, diff = 0;
  for (let i = 0; i < a.length; i += 4) {
    if (a[i] + a[i + 1] + a[i + 2] > 0) lit++;
    if (Math.abs(a[i] - b[i]) + Math.abs(a[i + 1] - b[i + 1]) + Math.abs(a[i + 2] - b[i + 2]) > 30) diff++;
  }
  log(`image: ${lit} of ${W * H} pixels drawn, ${diff} differ from the CPU path`);
  const imageOk = lit > W * H * 0.05 && diff <= W * H * 0.002;

  // Cull time for 100k instances (the passes only), median of 20.
  const big = records(100000, 9);
  gpu.set(big, 100000);
  gpu.update(cam);
  await device.queue.onSubmittedWorkDone();
  const ts: number[] = [];
  for (let r = 0; r < 20; r++) {
    const t0 = performance.now();
    gpu.update(cam);
    await device.queue.onSubmittedWorkDone();
    ts.push(performance.now() - t0);
  }
  ts.sort((x, y) => x - y);
  log(`cull 100k instances: ${ts[10].toFixed(2)} ms (submit to done, median of 20)`);
  if (errors.length) log(`WebGPU errors: ${errors.slice(0, 3).join(' | ')}`);
  window.__result = { match: countsOk && imageOk && errors.length === 0, counts: { got, want }, lit, diff, cullMs: ts[10], errors };
}

main().catch((e) => { log(String(e?.stack ?? e)); window.__result = { match: false, error: String(e) }; });
