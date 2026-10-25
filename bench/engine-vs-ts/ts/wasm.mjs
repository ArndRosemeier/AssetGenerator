import { readFileSync } from 'node:fs';
const { instance } = await WebAssembly.instantiate(readFileSync(process.argv[2]));
const e = instance.exports;
const med = (f) => { f(); f(); const t = []; for (let r = 0; r < 5; r++) { const t0 = performance.now(); f(); t.push(performance.now() - t0); } return t.sort((a,b)=>a-b)[2]; };
const nz = med(() => e.wasm_noise_all());
const all = med(() => e.wasm_chunks_all());
console.log(`wasm single: noise ${nz.toFixed(1)} ms, mesh ${(all - nz).toFixed(1)} ms, tris=${e.wasm_chunks_all()}`);
