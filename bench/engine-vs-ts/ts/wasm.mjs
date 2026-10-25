import { readFileSync } from 'node:fs';
const { instance } = await WebAssembly.instantiate(readFileSync(process.argv[2]));
const e = instance.exports;
const med = (f) => { f(); f(); const t = []; for (let r = 0; r < 7; r++) { const t0 = performance.now(); f(); t.push(performance.now() - t0); } return t.sort((a,b)=>a-b)[3]; };
const nz = med(() => e.wasm_noise_all());
e.wasm_prepare();
const ms = med(() => e.wasm_mesh_all());
console.log(`wasm single: noise ${nz.toFixed(1)} ms, mesh ${ms.toFixed(1)} ms, tris=${e.wasm_mesh_all()}`);
