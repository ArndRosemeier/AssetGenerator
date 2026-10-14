import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import * as THREE from 'three/webgpu';
import { randomAppearance, setHumanAssetBase } from '../src/index';
import { Humanoid, type Wardrobe } from '../src/three/index';

// The assets come from disk: fetch of file:// URLs, which node's fetch does not do.
const base = new URL('../assets/', import.meta.url);
const realFetch = globalThis.fetch;
globalThis.fetch = (async (u: string | URL) => {
  if (!String(u).startsWith('file:')) return realFetch(u);
  const b = readFileSync(fileURLToPath(String(u)));
  return { ok: true, json: async () => JSON.parse(b.toString()), arrayBuffer: async () => b.buffer.slice(b.byteOffset, b.byteOffset + b.byteLength) };
}) as typeof fetch;
setHumanAssetBase(base.href);

const NAKED: Wardrobe = { resolve: () => null, itemDef: () => undefined, buildItem: () => new THREE.Group(), disposeItem: () => {} };

/** Knee bend (degrees, 0 = straight) and how far the knee sits ahead of the hip–foot line (m; < 0 is folded backwards). */
function knee(h: Humanoid, s: 'L' | 'R', yaw: number): [number, number] {
  const p = (n: string) => h.char.bone(n).getWorldPosition(new THREE.Vector3());
  const a = p(`upperleg01.${s}`), b = p(`lowerleg01.${s}`), c = p(`foot.${s}`);
  const u = a.clone().sub(b).normalize(), v = c.clone().sub(b).normalize();
  const fwd = new THREE.Vector3(-Math.sin(yaw), 0, -Math.cos(yaw));
  return [(Math.PI - Math.acos(Math.max(-1, Math.min(1, u.dot(v))))) * (180 / Math.PI), b.clone().sub(a.clone().add(c).multiplyScalar(0.5)).dot(fwd)];
}

test('standing and turning on uneven ground, the knees never fold backwards or jump', async () => {
  const h = await Humanoid.create(randomAppearance('human', 3), { wardrobe: NAKED });
  for (const [name, ground] of [
    ['bumpy', (x: number, _y: number, z: number) => 0.06 * Math.sin(x * 9) * Math.cos(z * 7)],
    ['slope', (x: number) => x * 0.35],
  ] as const) {
    let prev: number[] | null = null;
    const dt = 1 / 60;
    for (let k = 0; k < 720; k++) {
      const t = k * dt, yaw = Math.sin(t * 0.7) * 1.5;
      h.update({ pos: [0, 0, 0], vel: [0, 0, 0], yaw, anim: { move: 'idle' } }, dt, t, ground);
      h.object.updateMatrixWorld(true);
      const L = knee(h, 'L', yaw), R = knee(h, 'R', yaw);
      assert.ok(L[1] > -0.02 && R[1] > -0.02, `${name} at ${t.toFixed(2)} s: a knee folds backwards (${L[1].toFixed(3)}, ${R[1].toFixed(3)} m)`);
      if (prev && k > 5) assert.ok(Math.abs(L[0] - prev[0]) < 6 && Math.abs(R[0] - prev[1]) < 6, `${name} at ${t.toFixed(2)} s: a knee jumps ${prev[0].toFixed(0)}→${L[0].toFixed(0)}°, ${prev[1].toFixed(0)}→${R[0].toFixed(0)}°`);
      prev = [L[0], R[0]];
    }
  }
});
