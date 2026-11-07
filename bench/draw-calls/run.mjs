// Draw-call benchmark: Engine (native wgpu) vs three.js WebGPURenderer in Chromium, same scenes.
// Usage from the AssetGenerator root, with Engine checked out next to it (..\Engine):
//   npm install && npm i --no-save playwright && npx playwright install chromium
//   node bench/draw-calls/run.mjs [--runs 3] [--only engine|three] [--warm 300] [--frames 600] [--size 1920x1080]
import { createServer } from 'node:http';
import { readFile, writeFile } from 'node:fs/promises';
import { execSync, spawnSync } from 'node:child_process';
import { dirname, join, extname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createRequire } from 'node:module';

const here = dirname(fileURLToPath(import.meta.url)), root = join(here, '..', '..');
const arg = (k, d) => { const i = process.argv.indexOf(`--${k}`); return i > 0 ? process.argv[i + 1] : d; };
const RUNS = +arg('runs', 3), ONLY = arg('only', ''), WARM = arg('warm', '300'), FRAMES = arg('frames', '600');
const [W, H] = arg('size', '1920x1080').split('x').map(Number);
const SCENES = (arg('scenes', 'unique,moving,instanced')).split(',');
const results = [];

if (ONLY !== 'three') {
  const dir = join(here, 'engine');
  console.log('building engine bench (release)...');
  execSync('cargo build --release', { cwd: dir, stdio: 'inherit' });
  const exe = join(dir, 'target', 'release', process.platform === 'win32' ? 'drawbench.exe' : 'drawbench');
  for (let r = 0; r < RUNS; r++) for (const scene of SCENES) {
    const env = { ...process.env, DRAWBENCH_SCENE: scene, DRAWBENCH_WARM: WARM, DRAWBENCH_FRAMES: FRAMES, ENGINE_PRESENT_MODE: 'immediate', ENGINE_WIDTH: String(W), ENGINE_HEIGHT: String(H) };
    const p = spawnSync(exe, [], { env, encoding: 'utf8', timeout: 15 * 60e3 });
    const line = (p.stdout || '').split('\n').find((l) => l.startsWith('{"stack"'));
    if (!line) { console.error(`engine ${scene} failed:\n${p.stderr?.slice(-2000)}`); continue; }
    const o = { ...JSON.parse(line), run: r }; results.push(o); console.log(JSON.stringify(o));
  }
}

if (ONLY !== 'engine') {
  const req = createRequire(join(root, 'package.json'));
  let pw; try { pw = req('playwright'); } catch { pw = createRequire(import.meta.url)('playwright'); }
  const types = { '.html': 'text/html', '.js': 'text/javascript' };
  const server = createServer(async (rq, rs) => {
    const u = new URL(rq.url, 'http://x');
    const file = u.pathname.startsWith('/three/') ? join(root, 'node_modules', 'three', 'build', u.pathname.slice(7)) : join(here, 'web', u.pathname === '/' ? 'index.html' : u.pathname);
    let body; try { body = await readFile(file); } catch { rs.writeHead(404); rs.end(); return; }
    rs.writeHead(200, { 'content-type': types[extname(file)] ?? 'application/octet-stream' }); rs.end(body);
  }).listen(0);
  const port = server.address().port;
  // Headed Chromium (Windows: the headless shell lacks dxcompiler.dll), vsync and frame cap off so rAF runs uncapped.
  const browser = await pw.chromium.launch({
    channel: process.env.DRAWBENCH_CHANNEL || 'chromium', headless: !!process.env.DRAWBENCH_HEADLESS,
    args: ['--enable-unsafe-webgpu', '--disable-gpu-vsync', '--disable-frame-rate-limit', '--disable-renderer-backgrounding', '--disable-background-timer-throttling', `--window-size=${W},${H + 120}`, ...(process.env.DRAWBENCH_ARGS ? process.env.DRAWBENCH_ARGS.split(' ') : [])],
  });
  for (let r = 0; r < RUNS; r++) for (const scene of SCENES) {
    const page = await browser.newPage({ viewport: { width: W, height: H } });
    page.on('console', (m) => { if (m.type() === 'error') console.error('page:', m.text()); });
    page.on('pageerror', (e) => console.error('page error:', e.message));
    await page.goto(`http://127.0.0.1:${port}/?scene=${scene}&warm=${WARM}&frames=${FRAMES}`);
    try {
      await page.waitForFunction(() => window.__result, null, { timeout: 15 * 60e3, polling: 500 });
      const o = { ...(await page.evaluate(() => window.__result)), run: r }; results.push(o); console.log(JSON.stringify(o));
      if (r === 0) await page.screenshot({ path: join(here, `three_${scene}.png`) });
    } catch (e) { console.error(`three ${scene} failed: ${e.message}`); }
    await page.close();
  }
  await browser.close(); server.close();
}

// Summary: median over runs of each run's median frame time.
const med = (a) => { const x = [...a].sort((p, q) => p - q); return x[x.length >> 1]; };
console.log('\nscene       engine ms   three ms   three/engine');
for (const scene of SCENES) {
  const e = results.filter((o) => o.stack === 'engine' && o.scene === scene).map((o) => o.median_ms);
  const t = results.filter((o) => o.stack === 'three' && o.scene === scene).map((o) => o.median_ms);
  const em = e.length ? med(e) : NaN, tm = t.length ? med(t) : NaN;
  console.log(`${scene.padEnd(11)} ${em.toFixed(2).padStart(9)}  ${tm.toFixed(2).padStart(9)}   ${(tm / em).toFixed(2)}x`);
}
await writeFile(join(here, 'results.json'), JSON.stringify(results, null, 2));
console.log(`\nwrote ${join(here, 'results.json')}`);
