// Runs the CPU benchmark set: TS (original + rewritten mesher), TS workers, Rust native, Rust rayon, Rust->WASM.
// Usage (from repo root, after `npm install`): node bench/engine-vs-ts/run.mjs
import { execSync } from 'node:child_process';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
const here = dirname(fileURLToPath(import.meta.url)), root = join(here, '..', '..'), out = join(here, 'out');
const esb = join(root, 'node_modules', '.bin', process.platform === 'win32' ? 'esbuild.cmd' : 'esbuild');
const sh = (c, cwd = here) => { console.log(`$ ${c}`); execSync(c, { cwd, stdio: 'inherit' }); };
for (const f of ['single.ts', 'par.mts', 'fastbench.ts']) sh(`"${esb}" ts/${f} --bundle --platform=node --format=esm --outfile=out/${f.replace(/\.m?ts$/, '.mjs')} --log-level=warning`);
sh('node out/single.mjs'); sh('node out/fastbench.mjs'); sh('node out/par.mjs 1'); sh('node out/par.mjs 4'); sh('node out/par.mjs 8');
sh('cargo build --release -q', join(here, 'rs')); sh(join('rs', 'target', 'release', 'bench'));
sh('rustup target add wasm32-unknown-unknown'); sh('cargo build --release -q --lib --target wasm32-unknown-unknown', join(here, 'rs'));
sh(`node ts/wasm.mjs ${join('rs', 'target', 'wasm32-unknown-unknown', 'release', 'bench.wasm')}`);
