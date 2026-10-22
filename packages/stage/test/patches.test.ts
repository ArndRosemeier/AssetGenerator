import { test } from 'node:test';
import assert from 'node:assert/strict';
import type { WebGPURenderer } from 'three/webgpu';
import { rebindSwitchedTextures } from '../src/patches';

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
