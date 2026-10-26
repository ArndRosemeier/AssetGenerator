import { test } from 'node:test';
import assert from 'node:assert/strict';
import { decodePack } from '../src/index';

/** A pack written the way blender/entrypoints/pack.py writes it. */
function encode(version: 1 | 2, models: { name: string; slots: string[]; pos: number[][]; col: number[][]; slot: number[]; idx: number[] }[]): Uint8Array {
  const out: number[] = [];
  const u8 = (v: number) => out.push(v & 255);
  const u16 = (v: number) => { u8(v); u8(v >> 8); };
  const u32 = (v: number) => { u16(v & 0xffff); u16(v >>> 16); };
  const f32 = (v: number) => { const b = new Uint8Array(new Float32Array([v]).buffer); out.push(...b); };
  const pad = () => { while (out.length % 4) out.push(0); };
  const str = (s: string) => { const b = new TextEncoder().encode(s); u16(b.length); out.push(...b); };
  out.push(...new TextEncoder().encode('FMPK')); u32(version); u32(models.length);
  for (const m of models) {
    str(m.name); pad();
    if (version === 2) { u16(m.slots.length); for (const s of m.slots) str(s); pad(); }
    const all = m.pos.flat(), scale = Math.max(...all.map(Math.abs)) / 32767;
    f32(scale); for (let k = 0; k < 3; k++) f32(Math.min(...m.pos.map((p) => p[k]))); for (let k = 0; k < 3; k++) f32(Math.max(...m.pos.map((p) => p[k])));
    u32(m.pos.length); u32(m.idx.length);
    for (const v of all) u16(Math.round(v / scale) & 0xffff);
    pad();
    for (let i = 0; i < m.pos.length; i++) { u8(0); u8(127); u8(0); }
    for (const c of m.col) for (const v of c) u8(v);
    if (version === 2) for (const s of m.slot) u8(s);
    pad();
    for (const i of m.idx) u16(i);
    pad();
  }
  return Uint8Array.from(out);
}

const tri = { pos: [[0, 0, 0], [1, 0, 0], [0, 2, -0.5]], col: [[255, 0, 0], [0, 255, 0], [0, 0, 128]], idx: [0, 1, 2] };

for (const version of [1, 2] as const) {
  test(`FMPK v${version}: two models decode with positions, normals, colours and slots`, () => {
    const bytes = encode(version, [
      { name: 'one', slots: ['wood', 'iron'], slot: [0, 1, 1], ...tri },
      { name: 'second_model', slots: ['bone'], slot: [0, 0, 0], ...tri },
    ]);
    const pack = decodePack(bytes);
    assert.deepEqual([...pack.keys()], ['one', 'second_model']);
    const m = pack.get('one')!;
    assert.ok(Math.abs(m.positions[7] - 2) < 1e-3 && Math.abs(m.positions[8] + 0.5) < 1e-3);
    assert.equal(m.normals[1], 1);
    assert.equal(m.colors[0], 1);
    assert.ok(Math.abs(m.colors[8] - (128 / 255) ** 2) < 1e-6);
    assert.deepEqual([...m.indices], [0, 1, 2]);
    assert.deepEqual(m.max, [1, 2, 0]);
    if (version === 2) {
      assert.deepEqual(m.slotNames, ['wood', 'iron']);
      assert.deepEqual([...m.slots], [0, 1, 1]);
      assert.deepEqual(pack.get('second_model')!.slotNames, ['bone']);
    } else assert.deepEqual([...m.slots], [0, 0, 0]);
  });
}

test('not a pack throws', () => {
  assert.throws(() => decodePack(new TextEncoder().encode('GLTF000000000000')));
});
