// @ts-nocheck -- a browser page (tools/gpu-page.mjs), not part of the package's build.
// Draw-cost benchmark: how much main-thread time three.js spends per frame drawing many static objects, and how
// much each way of drawing them saves. The same field of lit, shadowed objects (a few shapes, a few materials, like
// a town's or a forest's static parts) is drawn as plain meshes, inside a BundleGroup (WebGPU render bundles), as
// InstancedMesh, as BatchedMesh and as merged geometry, on WebGPURenderer's WebGPU and WebGL2 backends and on the
// classic WebGLRenderer. Each row: mean and median CPU ms in `renderer.render` (sun shadow map drawn every frame or
// not), the frame interval, and draw calls. Run on a real GPU:
//   npm run bench:draw -- --headed     (vsync off; with --serve, start Chrome with --disable-gpu-vsync --disable-frame-rate-limit)
// URL options: ?n=1000,4000 (object counts) &backends=webgpu,webgl2,classic &modes=meshes,bundle,... &shadow=1,0
//   &frames=180 (measured per row) &warm=40.
import * as T from 'three/webgpu';
import * as C from 'three';
import { mergeGeometries } from 'three/examples/jsm/utils/BufferGeometryUtils.js';

const q = new URLSearchParams(location.search);
const list = (k: string, d: string) => (q.get(k) ?? d).split(',').filter(Boolean);
const COUNTS = list('n', '1000,4000').map(Number);
const BACKENDS = list('backends', 'webgpu,webgl2,classic');
const MODES = list('modes', 'meshes,bundle,instanced,batched,merged');
const SHADOWS = list('shadow', '1,0').map((s) => s === '1');
const FRAMES = Number(q.get('frames') ?? 180), WARM = Number(q.get('warm') ?? 40);
const W = 1920, H = 1080, FIELD = 400, SHAPES = 8, COLORS = 6;

const out = document.getElementById('out')!;
const log = (s: string) => { out.textContent += s + '\n'; console.log(s); };

/** Deterministic placement: the same field for every row. */
function rng(seed: number) { let s = seed >>> 0; return () => ((s = (s * 1664525 + 1013904223) >>> 0) / 4294967296); }

function shapes(G: typeof C) {
  return [
    new G.BoxGeometry(2, 3, 2), new G.CylinderGeometry(0.8, 1, 4, 12), new G.ConeGeometry(1.5, 4, 10), new G.SphereGeometry(1.2, 16, 10),
    new G.BoxGeometry(4, 1, 1), new G.CylinderGeometry(0.3, 0.3, 5, 8), new G.TorusGeometry(1, 0.3, 8, 16), new G.CapsuleGeometry(0.6, 1.5, 4, 8),
  ].slice(0, SHAPES);
}

interface Placed { shape: number; color: number; matrix: C.Matrix4 }
function field(n: number): Placed[] {
  const r = rng(n * 7 + 1), m: Placed[] = [], q = new C.Quaternion(), up = new C.Vector3(0, 1, 0);
  for (let i = 0; i < n; i++) {
    const p = new C.Vector3((r() - 0.5) * FIELD, 0, (r() - 0.5) * FIELD);
    const matrix = new C.Matrix4().compose(p, q.setFromAxisAngle(up, r() * 6.28), new C.Vector3().setScalar(0.7 + r() * 0.6));
    m.push({ shape: Math.floor(r() * SHAPES), color: Math.floor(r() * COLORS), matrix });
  }
  return m;
}

/** The objects for one row, in `root` (a Group, or a BundleGroup for `bundle`). */
function build(G: any, classic: boolean, mode: string, placed: Placed[], root: any) {
  const geos = shapes(G);
  const mats = Array.from({ length: COLORS }, (_, i) => new (classic ? G.MeshStandardMaterial : G.MeshStandardNodeMaterial)({ color: new G.Color().setHSL(i / COLORS, 0.5, 0.5), roughness: 0.8 }));
  const shadowy = (o: any) => { o.castShadow = o.receiveShadow = true; o.matrixAutoUpdate = false; o.updateMatrix(); o.updateMatrixWorld(true); return o; };
  if (mode === 'meshes' || mode === 'bundle' || mode === 'meshes-auto') {
    for (const p of placed) {
      const m = new G.Mesh(geos[p.shape], mats[p.color]);
      m.matrix.copy(p.matrix); m.matrix.decompose(m.position, m.quaternion, m.scale);
      shadowy(m);
      if (mode === 'meshes-auto') m.matrixAutoUpdate = true; // what an object left at three's default costs each frame
      root.add(m);
    }
  } else if (mode === 'instanced') {
    for (let s = 0; s < SHAPES; s++) for (let c = 0; c < COLORS; c++) {
      const mine = placed.filter((p) => p.shape === s && p.color === c);
      if (!mine.length) continue;
      const im = new G.InstancedMesh(geos[s], mats[c], mine.length);
      mine.forEach((p, i) => im.setMatrixAt(i, p.matrix));
      im.computeBoundingSphere();
      root.add(shadowy(im));
    }
  } else if (mode === 'batched') {
    for (let c = 0; c < COLORS; c++) {
      const mine = placed.filter((p) => p.color === c);
      let verts = 0, idx = 0;
      for (const g of geos) { verts += g.attributes.position.count; idx += g.index ? g.index.count : g.attributes.position.count; }
      const b = new G.BatchedMesh(mine.length, verts, idx, mats[c]);
      const ids = geos.map((g) => b.addGeometry(g));
      for (const p of mine) b.setMatrixAt(b.addInstance(ids[p.shape]), p.matrix);
      root.add(shadowy(b));
    }
  } else if (mode === 'merged') {
    for (let c = 0; c < COLORS; c++) {
      const mine = placed.filter((p) => p.color === c);
      const g = mergeGeometries(mine.map((p) => geos[p.shape].clone().applyMatrix4(p.matrix)));
      root.add(shadowy(new G.Mesh(g, mats[c])));
    }
  } else throw new Error(`unknown mode ${mode}`);
  return () => { for (const g of geos) g.dispose(); for (const m of mats) m.dispose(); root.traverse((o: any) => { if (mode === 'merged' && o.geometry) o.geometry.dispose(); if (o.dispose && o !== root) o.dispose?.(); }); };
}

const median = (a: number[]) => { const s = [...a].sort((x, y) => x - y); return s[Math.floor(s.length / 2)]; };
const frameWait = () => new Promise((r) => requestAnimationFrame(r));

async function row(backend: string, mode: string, n: number, shadow: boolean) {
  const classic = backend === 'classic', G: any = classic ? C : T;
  if (classic && mode === 'bundle') return null; // render bundles are WebGPURenderer's
  const canvas = document.createElement('canvas');
  canvas.width = W; canvas.height = H; canvas.style.cssText = 'width:480px;height:270px;display:block';
  document.body.appendChild(canvas);
  let renderer: any;
  if (classic) renderer = new C.WebGLRenderer({ canvas, antialias: false, powerPreference: 'high-performance' });
  else { renderer = new T.WebGPURenderer({ canvas, antialias: false, forceWebGL: backend === 'webgl2', powerPreference: 'high-performance' }); await renderer.init(); }
  renderer.setPixelRatio(1); renderer.setSize(W, H, false);
  renderer.shadowMap.enabled = true; renderer.shadowMap.type = classic ? C.PCFSoftShadowMap : T.PCFShadowMap; // WebGPURenderer maps PCFSoft to PCF
  const scene = new G.Scene();
  scene.background = new G.Color(0x8fb4d8);
  const camera = new G.PerspectiveCamera(55, W / H, 0.5, 2000);
  camera.position.set(0, 140, 240); camera.lookAt(0, 0, 0);
  const sun = new G.DirectionalLight(0xfff0d8, 4); sun.position.set(120, 200, 80);
  sun.castShadow = true; sun.shadow.mapSize.set(2048, 2048);
  Object.assign(sun.shadow.camera, { left: -FIELD / 2, right: FIELD / 2, top: FIELD / 2, bottom: -FIELD / 2, near: 1, far: 600 });
  sun.shadow.camera.updateProjectionMatrix();
  sun.shadow.autoUpdate = shadow;
  scene.add(sun, sun.target, new G.HemisphereLight(0xbcd6f0, 0x5a5040, 1.4));
  const ground = new G.Mesh(new G.PlaneGeometry(FIELD * 1.2, FIELD * 1.2).rotateX(-Math.PI / 2), new (classic ? G.MeshStandardMaterial : G.MeshStandardNodeMaterial)({ color: 0x6b7a4a }));
  ground.receiveShadow = true; scene.add(ground);
  const root = mode === 'bundle' ? new T.BundleGroup() : new G.Group();
  const dispose = build(G, classic, mode, field(n), root);
  scene.add(root);
  if (!shadow) { sun.shadow.needsUpdate = true; } // drawn once, then kept
  const cpu: number[] = [], gaps: number[] = [];
  let calls = 0, last = 0;
  for (let i = 0; i < WARM + FRAMES; i++) {
    await frameWait();
    const t0 = performance.now();
    renderer.render(scene, camera);
    const t1 = performance.now();
    if (i >= WARM) { cpu.push(t1 - t0); if (last) gaps.push(t0 - last); calls = renderer.info.render.drawCalls ?? renderer.info.render.calls; }
    last = t0;
  }
  // WebGPU work is queued: wait for it so the next row starts clean.
  if (!classic && renderer.backend?.device) await renderer.backend.device.queue.onSubmittedWorkDone();
  dispose(); ground.geometry.dispose(); ground.material.dispose(); renderer.dispose(); canvas.remove();
  const mean = cpu.reduce((a, b) => a + b, 0) / cpu.length;
  return { backend, mode, n, shadow, cpuMean: +mean.toFixed(2), cpuMedian: +median(cpu).toFixed(2), frameMedian: +median(gaps).toFixed(2), calls };
}

async function main() {
  log(`three r${T.REVISION} · ${navigator.userAgent.match(/Chrome\/[\d.]+/)?.[0] ?? navigator.userAgent} · ${W}x${H} · ${FRAMES} frames per row (after ${WARM})`);
  if (!('gpu' in navigator)) log('no navigator.gpu: the webgpu rows fall back to WebGL2 inside three');
  log('backend  mode         n     shadow  cpu mean  cpu median  frame  calls');
  const rows = [];
  for (const n of COUNTS) for (const backend of BACKENDS) for (const shadow of SHADOWS) for (const mode of MODES) {
    const r = await row(backend, mode, n, shadow);
    if (!r) continue;
    rows.push(r);
    log(`${backend.padEnd(8)} ${mode.padEnd(12)} ${String(n).padEnd(5)} ${(shadow ? 'every' : 'kept').padEnd(7)} ${r.cpuMean.toFixed(2).padStart(8)}  ${r.cpuMedian.toFixed(2).padStart(10)}  ${r.frameMedian.toFixed(1).padStart(5)}  ${String(r.calls).padStart(5)}`);
  }
  (window as any).__result = { match: true, rows };
}

main().catch((e) => { log(String(e?.stack ?? e)); (window as any).__result = { match: false, error: String(e) }; });
