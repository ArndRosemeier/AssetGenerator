import { test } from 'node:test';
import assert from 'node:assert/strict';
import type { Material } from 'three/webgpu';
import { Kinds } from '../src/kinds';

const fake = (): Material => ({}) as Material;

test('a kind builds its one material on first use, named after it', () => {
  const kinds = new Kinds<'position' | 'normal'>();
  let built = 0;
  const k = kinds.define('wood', ['position', 'normal'], () => { built++; return fake(); });
  assert.equal(built, 0);
  const m = k.make();
  assert.equal(k.make(), m);
  assert.equal(built, 1);
  assert.equal((m as unknown as { name: string }).name, 'wood');
  assert.deepEqual(k.shadow, { cast: true, receive: true });
});

test('a name is defined once; late kinds stay out of the warm-up', () => {
  const kinds = new Kinds();
  kinds.define('a', ['position'], fake);
  kinds.define('b', ['position'], fake, { cast: false, receive: false }, true);
  assert.throws(() => kinds.define('a', ['position'], fake), /defined twice/);
  assert.deepEqual(kinds.all().map((k) => k.name), ['a', 'b']);
  assert.deepEqual(kinds.warm().map((k) => k.name), ['a']);
});
