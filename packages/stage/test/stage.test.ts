import { test } from 'node:test';
import assert from 'node:assert/strict';
import { Float32BufferAttribute, MeshBasicNodeMaterial } from 'three/webgpu';
import { DrawnCasters, standIn, type StageKind } from '../src/stage';

const kind = (attributes: string[], cast = false): StageKind => ({ name: 'test', attributes, make: () => new MeshBasicNodeMaterial(), shadow: { cast, receive: true } });

test('standIn: an indexed triangle with exactly the kind\'s attributes and shadow flags', () => {
  const m = standIn(kind(['position', 'normal', 'uv'], true));
  assert.deepEqual(Object.keys(m.geometry.attributes).sort(), ['normal', 'position', 'uv']);
  assert.ok(m.geometry.index, 'indexed: the index is part of the cache key');
  assert.equal(m.castShadow, true);
  assert.equal(m.receiveShadow, true);
});

test('standIn: a game attribute comes from the hook, and an unknown one fails loudly', () => {
  assert.throws(() => standIn(kind(['position', 'surface'])), /surface/);
  const m = standIn(kind(['position', 'surface']), (g, name) => {
    if (name !== 'surface') return false;
    g.setAttribute('surface', new Float32BufferAttribute(new Float32Array(3 * 4), 4));
    return true;
  });
  assert.equal(m.geometry.getAttribute('surface').itemSize, 4);
});

test('DrawnCasters: a caster counts as drawn until its geometry or material changes', () => {
  const d = new DrawnCasters();
  const g1 = {}, g2 = {}, mat = {};
  const m = { geometry: g1, material: mat };
  assert.equal(d.fresh(m), true);
  d.mark(m);
  assert.equal(d.fresh(m), false, 'drawn as it is: skipped');
  m.geometry = g2;
  assert.equal(d.fresh(m), true, 'a new detail level: drawn again');
  assert.equal(d.fresh({ geometry: g2, material: mat }), true, 'another mesh with the same parts: its own objects');
});
