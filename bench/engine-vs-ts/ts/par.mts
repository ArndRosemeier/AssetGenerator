import { Worker, isMainThread, parentPort, workerData } from 'node:worker_threads';
import { Noise } from '../../../packages/core/src/noise.ts';
import { chunk, CHUNKS } from './work.ts';
if (isMainThread) {
  const T = Number(process.argv[2] ?? 4);
  const ws = Array.from({ length: T }, () => new Worker(new URL(import.meta.url), { workerData: {}, execArgv: [] }));
  const runOnce = () => new Promise<number>((res) => {
    let next = 0, done = 0; const t0 = performance.now();
    const feed = (w: Worker) => { if (next < CHUNKS.length) w.postMessage(CHUNKS[next++]); };
    for (const w of ws) { w.removeAllListeners('message'); w.on('message', () => { if (++done === CHUNKS.length) res(performance.now() - t0); else feed(w); }); feed(w); }
  });
  const times: number[] = [];
  for (let r = 0; r < 8; r++) times.push(await runOnce());
  const t = times.slice(3).sort((a, b) => a - b)[2];
  console.log(`ts workers x${T}: ${t.toFixed(1)} ms wall (64 chunks, noise+mesh, mesh not posted back)`);
  for (const w of ws) w.terminate();
} else {
  const noise = new Noise(1234);
  parentPort!.on('message', (c: [number, number, number]) => { const o = chunk(noise, ...c); parentPort!.postMessage(o.tris); });
}
