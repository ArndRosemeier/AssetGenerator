// A package's GPU check in the browser: builds <dir>/page.ts, serves it on localhost and runs it in Chromium via
// Playwright; the page sets window.__result ({ match, error? }). Exit 1 when it does not match. Usage (repo root,
// after `npm install`):
//   npm i --no-save playwright && npx playwright install chromium     (once)
//   node tools/gpu-page.mjs packages/volume/test/gpu                   headless (SwiftShader where there is no real GPU)
//   ... --headed                       a visible window
//   ... --serve                        only serve; open the printed URL in Chrome yourself
import { execSync } from 'node:child_process';
import { createServer } from 'node:http';
import { readFileSync, mkdirSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createRequire } from 'node:module';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const args = process.argv.slice(2);
const here = join(root, args.find((a) => !a.startsWith('-') && !a.startsWith('?')) ?? 'packages/volume/test/gpu'), out = join(here, 'out');
const esb = join(root, 'node_modules', '.bin', process.platform === 'win32' ? 'esbuild.cmd' : 'esbuild');
mkdirSync(out, { recursive: true });
execSync(`"${esb}" page.ts --bundle --format=esm --target=es2022 --outfile=out/page.js --log-level=warning`, { cwd: here, stdio: 'inherit' });
writeFileSync(join(out, 'index.html'), '<!doctype html><meta charset="utf-8"><title>GPU check</title><pre id="out"></pre><script type="module" src="page.js"></script>');

const server = createServer((req, res) => {
  const f = new URL(req.url, 'http://x').pathname === '/' ? 'index.html' : 'page.js';
  res.writeHead(200, { 'content-type': f.endsWith('.js') ? 'text/javascript' : 'text/html' });
  res.end(readFileSync(join(out, f)));
}).listen(0, '127.0.0.1');
await new Promise((r) => server.on('listening', r));
const url = `http://127.0.0.1:${server.address().port}/`;
if (args.includes('--serve')) { console.log(`open ${url} in Chrome (Ctrl+C to stop)`); }
else {
  let pw;
  try { pw = await import('playwright'); } catch { try { pw = createRequire(import.meta.url)('playwright'); } catch {} }
  if (!pw) { console.log(`playwright not installed (npm i --no-save playwright). Open ${url} in Chrome instead.`); }
  if (pw) {
    const flags = ['--enable-unsafe-webgpu', '--enable-gpu', '--ignore-gpu-blocklist'];
    if (process.platform === 'linux') flags.push('--enable-features=Vulkan');
    const opts = { headless: !args.includes('--headed'), args: flags, ...(process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : {}) };
    let browser;
    // Full Chromium first: Playwright's default headless shell lacks dxcompiler.dll, so WebGPU fails on Windows.
    for (const channel of ['chromium', undefined, 'chrome']) {
      try { browser = await pw.chromium.launch({ ...opts, ...(channel ? { channel } : {}) }); break; } catch (e) { if (channel === 'chrome') throw e; }
    }
    const page = await browser.newPage();
    page.on('console', (m) => { if (!m.text().startsWith('{')) console.log('[page] ' + m.text()); });
    await page.goto(url + (args.find((a) => a.startsWith('?')) ?? ''));
    const res = await page.waitForFunction(() => window.__result, null, { timeout: 0, polling: 500 }).then((h) => h.jsonValue());
    console.log(JSON.stringify(res, null, 2));
    await browser.close(); server.close();
    process.exit(res.error || !res.match ? 1 : 0);
  }
}
