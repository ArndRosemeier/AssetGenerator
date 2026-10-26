import { test } from 'node:test';
import assert from 'node:assert/strict';
import type { WebGPURenderer } from 'three/webgpu';
import { NodeUpdateType, Texture } from 'three/webgpu';
import { texture, uv } from 'three/tsl';
import { keepTextureUpdates, rebindSwitchedTextures } from '../src/patches';

test('rebind: a texture node switched to another texture forgets its generation, so its bind group is rebuilt', () => {
  const white = { version: 1 }, eye = { version: 1 }, seen: unknown[] = [];
  const node = { value: white as unknown };
  const binding = { isSampledTexture: true, textureNode: node, texture: white as unknown, generation: 1 as number | null };
  const other = { isUniformBuffer: true, generation: 7 };
  const renderer = { _bindings: { _update(group: { bindings: unknown[] }) { seen.push(binding.generation); return group; } } };
  assert.ok(rebindSwitchedTextures(renderer as unknown as WebGPURenderer));
  const group = { bindings: [binding, other] };
  renderer._bindings._update(group);
  assert.equal(seen.pop(), 1, 'unchanged texture: generation kept');
  node.value = eye; // the next object's own texture, same version as the fallback
  renderer._bindings._update(group);
  assert.equal(seen.pop(), null, 'switched: generation forgotten, so three rebuilds the group');
  assert.equal(other.generation, 7);
  assert.equal(rebindSwitchedTextures({} as WebGPURenderer), false, 'no hook without three internals');
});

test('texture node: an update of its own (onObjectUpdate) survives the build, a plain texture keeps three\'s choice', () => {
  assert.ok(keepTextureUpdates());
  const own = texture(new Texture(), uv()).onObjectUpdate(() => undefined) as unknown as { setup(b: unknown): unknown; updateType: string };
  const plain = texture(new Texture(), uv()) as unknown as { setup(b: unknown): unknown; updateType: string };
  const builder = { context: {}, getNodeProperties: () => ({}) } as unknown;
  for (const n of [own, plain]) {
    n.setup(builder);
    n.updateType = NodeUpdateType.NONE; // what three's uv setup does while building
  }
  assert.equal(own.updateType, NodeUpdateType.OBJECT);
  assert.equal(plain.updateType, NodeUpdateType.NONE);
  own.updateType = NodeUpdateType.FRAME;
  assert.equal(own.updateType, NodeUpdateType.FRAME, 'another update type can still be set');
});

test('shadow nodes: materials that lend the same nodes share one set (so one shadow shader), others get their own', async () => {
  const { shareShadowNodes, shadowKindOf } = await import('../src/patches');
  const { MeshStandardNodeMaterial } = await import('three/webgpu');
  const { color, float } = await import('three/tsl');
  const own = (m: unknown) => ({ colorNode: null, depthNode: null, positionNode: null, from: m });
  const renderer = { shadowMap: { transmitted: false }, _getShadowNodes: own } as unknown as { _getShadowNodes(m: unknown): { colorNode: unknown }; shadowMap: unknown };
  assert.ok(shareShadowNodes(renderer as unknown as WebGPURenderer));
  assert.ok(shareShadowNodes(renderer as unknown as WebGPURenderer), 'a second install keeps the first');
  const tint = color(0.5, 0.4, 0.3), other = color(0.1, 0.1, 0.1);
  const a = new MeshStandardNodeMaterial(), b = new MeshStandardNodeMaterial(), c = new MeshStandardNodeMaterial(), plain = new MeshStandardNodeMaterial();
  a.colorNode = tint; b.colorNode = tint; c.colorNode = other;
  a.map = new Texture(); b.map = new Texture(); // each its own picture, read from the mesh drawn
  c.maskNode = float(1).greaterThan(0);
  assert.equal(shadowKindOf(a), shadowKindOf(b));
  assert.notEqual(shadowKindOf(a), shadowKindOf(c));
  const na = renderer._getShadowNodes(a), nb = renderer._getShadowNodes(b), nc = renderer._getShadowNodes(c);
  assert.equal(na, nb, 'alike: the very same nodes');
  assert.notEqual(na, nc);
  assert.ok(na.colorNode && nc.colorNode);
  assert.equal(renderer._getShadowNodes(plain).colorNode, null, 'nothing to lend: no colour node, as in three');
});

test('late builds: after warm-up a draw without its shader builds only in a frame with room under the cap, else waits', async () => {
  const { deferLateBuilds } = await import('../src/patches');
  const { ShaderCap } = await import('../src/cap');
  const { ShaderMonitor } = await import('../src/monitor');
  let now = 0, frames: (() => void)[] = [];
  const cap = new ShaderCap(() => now, (fn) => frames.push(fn)), monitor = new ShaderMonitor(() => now);
  const ro = { object: { name: 'beard', type: 'Mesh' }, material: { type: 'ShadowMaterial' } };
  let built = new Set<unknown>();
  const drawn: unknown[] = [];
  const renderer = {
    _currentRenderContext: {},
    _objects: { get: (o: unknown) => ({ ...ro, object: o }) },
    _nodes: { getForRenderCacheKey: () => 7 },
    _renderObjectDirect(object: unknown) { drawn.push(object); built.add(object); now += 2; }, // a 2 ms build while drawn
  };
  assert.ok(deferLateBuilds(renderer as unknown as WebGPURenderer, cap, monitor, (r: { object: unknown }) => !built.has(r.object), () => 'beard shadow'));
  const a = { name: 'a' }, b = { name: 'b' };
  renderer._renderObjectDirect(a); // warm-up: drawn (and built) at once
  assert.equal(drawn.length, 1);
  built = new Set();
  cap.active = true;
  renderer._renderObjectDirect(a); // room: built in this frame's slot, while drawn
  renderer._renderObjectDirect(b); // same frame: no room, skipped
  assert.deepEqual(drawn.slice(1), [a]);
  assert.equal(monitor.summary().late, 1);
  cap.newFrame(); now += 1;
  renderer._renderObjectDirect(b); // 2 ms build needs 4 ms after it: still waits
  assert.equal(drawn.length, 2);
  cap.newFrame(); now += 5;
  renderer._renderObjectDirect(a); renderer._renderObjectDirect(b);
  assert.deepEqual(drawn.slice(2), [a, b], 'a built already draws; b now has its slot');
  assert.equal(monitor.summary().late, 1, 'noted once per shader');
  frames = [];
  monitor.note = 'shadow warm-up';
  built = new Set();
  renderer._renderObjectDirect(a); renderer._renderObjectDirect(b);
  assert.equal(drawn.length, 6, 'the Stage\'s own warm-up draws at once');
  assert.equal(deferLateBuilds({} as WebGPURenderer, cap, monitor, () => true, () => ''), false);
});
