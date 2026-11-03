import { test } from 'node:test';
import assert from 'node:assert/strict';
import { BoxGeometry, Mesh, MeshBasicNodeMaterial } from 'three/webgpu';
import { StaticBundle } from '../src/bundle';

const mesh = () => new Mesh(new BoxGeometry(), new MeshBasicNodeMaterial());

test('StaticBundle records again only when its visible children change', () => {
  const b = new StaticBundle('town'), a = mesh(), c = mesh();
  b.add(a, c);
  assert.equal(b.recordIfChanged(), true);
  const v = b.version;
  assert.equal(b.recordIfChanged(), false);
  assert.equal(b.version, v);
  c.visible = false;
  assert.equal(b.recordIfChanged(), true);
  assert.equal(b.version, v + 1);
  c.visible = true;
  b.remove(a);
  assert.equal(b.recordIfChanged(), true);
  b.changed();
  assert.equal(b.version, v + 3);
});

test('StaticBundle draws its children without per-object culling', () => {
  const b = new StaticBundle(), a = mesh();
  b.add(a);
  b.recordIfChanged();
  assert.equal(a.frustumCulled, false);
});
