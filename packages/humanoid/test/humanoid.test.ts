import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { parseHumanAssets, buildCharacter, randomAppearance, type HumanManifest, type ConformManifest } from '../src/index';

const dir = fileURLToPath(new URL('../assets/human/', import.meta.url));
const buf = (f: string) => { const b = readFileSync(dir + f); return b.buffer.slice(b.byteOffset, b.byteOffset + b.byteLength) as ArrayBuffer; };
const manifest = JSON.parse(readFileSync(dir + 'manifest.json', 'utf8')) as HumanManifest;
const cm = JSON.parse(readFileSync(dir + 'conform.json', 'utf8')) as ConformManifest;
const assets = parseHumanAssets(manifest, buf(manifest.file), { manifest: cm, buf: buf(cm.file) });

test('the assets load with the Woman/Man conform data', () => {
  assert.ok(assets.conform);
  assert.equal(assets.basePos.length, manifest.morphVerts * 3);
  assert.ok(assets.boneByName.has('root'));
});

test('a character builds deterministically from its appearance', () => {
  const a = buildCharacter(assets, randomAppearance('human', 42));
  const b = buildCharacter(assets, randomAppearance('human', 42));
  assert.deepEqual(a.renderPos, b.renderPos);
  assert.deepEqual(a.body.heads, b.body.heads);
  const c = buildCharacter(assets, randomAppearance('human', 43));
  assert.notDeepEqual(a.renderPos, c.renderPos);
});

test('humans stand on y = 0 and are human sized; races differ', () => {
  for (const seed of [1, 2, 3]) {
    const h = buildCharacter(assets, randomAppearance('human', seed)).body;
    assert.ok(h.height > 1.4 && h.height < 2.1, `height ${h.height}`);
    let minY = Infinity;
    for (let i = 1; i < h.pos.length; i += 3) minY = Math.min(minY, h.pos[i]);
    assert.ok(Math.abs(minY) < 0.02, `feet at ${minY}`);
  }
  const dwarf = buildCharacter(assets, randomAppearance('dwarf', 1)).body;
  assert.ok(dwarf.height < 1.5, `dwarf ${dwarf.height}`);
});

test('a skin mesh needs at most 8 vertex buffers (the WebGPU limit)', async () => {
  const { getHumanStatic } = await import('../src/three/staticData');
  const { CharacterGeometry } = await import('../src/three/Character');
  const geo = new CharacterGeometry(getHumanStatic(assets), buildCharacter(assets, randomAppearance('human', 7)));
  for (const g of [...geo.body, geo.lashes, geo.teeth, geo.tongue]) assert.ok(Object.keys(g.attributes).length <= 8, Object.keys(g.attributes).join(' '));
});
