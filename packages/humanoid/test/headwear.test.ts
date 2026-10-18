import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import * as THREE from 'three/webgpu';
import { bandPlane, bandY, buildBody, loadHumanAssets, planeToModel, randomAppearance, setHumanAssetBase, skullAt, toSocket } from '../src/index';
import { sharedGraph } from '../src/three/nodes/sharedGraph';

const base = new URL('../assets/', import.meta.url);
const realFetch = globalThis.fetch;
globalThis.fetch = (async (u: string | URL) => {
  if (!String(u).startsWith('file:')) return realFetch(u);
  const b = readFileSync(fileURLToPath(String(u)));
  return { ok: true, json: async () => JSON.parse(b.toString()), arrayBuffer: async () => b.buffer.slice(b.byteOffset, b.byteOffset + b.byteLength) };
}) as typeof fetch;
setHumanAssetBase(base.href);

test('the head map reaches every skull vertex, on a child and an adult; a band plane is level and maps to model space', async () => {
  const as = await loadHumanAssets();
  for (const app of [randomAppearance('human', 1, { gender: 0.9, age: 0.5 }), randomAppearance('human', 2, { gender: 0.1, age: 0.1 })]) {
    const b = buildBody(as, app), h = b.fit.head!;
    const head = as.boneByName.get('head')!, BODY = as.manifest.groups.tongue[0];
    let n = 0;
    for (let v = 0; v < BODY; v++) {
      if (as.skinIdx[v * 4] !== head || as.skinW[v * 4] < 200) continue;
      const p = toSocket(b.sockets.head, b.pos, v * 3);
      if (p[1] < h.brow) continue;
      const d = [p[0] - h.c[0], p[1] - h.c[1], p[2] - h.c[2]], r = Math.hypot(d[0], d[1], d[2]);
      const az = Math.atan2(d[0], d[2]), el = Math.asin(d[1] / r);
      assert.ok(skullAt(h, az, el) >= r - 1e-6, `vertex ${v} is ${((r - skullAt(h, az, el)) * 1000).toFixed(1)} mm outside the map`);
      n++;
    }
    assert.ok(n > 100);
    assert.ok(h.brow > 0 && h.top > h.brow + 0.04, 'the brow under the top of the head');
    const pl = bandPlane(h, { front: 0.2, back: 0 });
    assert.equal(pl[0], 0, 'level from side to side');
    assert.ok(bandY(pl, 0, h.c[2] + h.radius) >= h.brow, 'at or over the brow');
    // A point on the band in socket space is on the model-space plane too.
    const s = b.sockets.head, q = [0.03, bandY(pl, 0.03, 0.02), 0.02];
    const B = s.basis, m = [0, 1, 2].map((i) => s.pos[i] + B[i] * q[0] + B[3 + i] * q[1] + B[6 + i] * q[2]);
    const pm = planeToModel(s, pl);
    assert.ok(Math.abs(pm[0] * m[0] + pm[1] * m[1] + pm[2] * m[2] - pm[3]) < 1e-9);
  }
});

test('shared graph materials keep their alpha test (hair strands are cut out, not solid cards)', () => {
  const { material } = sharedGraph('alpha test check', { u: { value: 1 } }, {}, () => new THREE.MeshPhysicalNodeMaterial({ alphaTest: 0.38 }));
  assert.equal(material.alphaTest, 0.38);
});
