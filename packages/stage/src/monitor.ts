/**
 * Shader monitor (see the game's docs/SHADERS.md): records every shader build and how long it blocked the main
 * thread, and checks the policy: under 100 ms each, and after warm-up builds take at most a third of the time, spread
 * evenly: after a build of t ms, the next starts no sooner than 2t ms after it ended (the cap, cap.ts). `window.shaders.report()` in the console; a game shows `stage.hudLine()` in its HUD or debug menu. From Dunfinity src/render/shaders/monitor.ts.
 */
export type Phase = 'warmup' | 'run';
export type BuildKind = 'node-sync' | 'node-async' | 'gpu-module' | 'gpu-pipeline-sync' | 'gpu-pipeline-async' | 'gl-link';

export interface ShaderEvent { t: number; kind: BuildKind; ms: number; what: string; phase: Phase }

/** Which kinds stall the main thread while they run (the async ones yield or run off-thread). */
const BLOCKING: ReadonlySet<BuildKind> = new Set(['node-sync', 'gpu-module', 'gpu-pipeline-sync', 'gl-link']);
/** Which kinds start a new shader (counted against the cap). */
const STARTS: ReadonlySet<BuildKind> = new Set(['node-sync', 'node-async']);

export class ShaderMonitor {
  readonly budgetMs = 100;
  /** The most of any stretch of time that builds may take after warm-up (as the cap's `share`). */
  readonly share = 1 / 3;
  phase: Phase = 'warmup';
  /** Why the render path builds right now, if on purpose (appended to what synchronous builds record), e.g. the Stage's shadow warm-up. */
  note = '';
  readonly events: ShaderEvent[] = [];

  constructor(private readonly now: () => number = () => performance.now()) {}

  record(kind: BuildKind, ms: number, what: string, t = this.now() - ms): void {
    // The note says why the render path builds: it marks synchronous builds only.
    this.events.push({ t, kind, ms, what: this.note && kind === 'node-sync' ? `${what} (${this.note})` : what, phase: this.phase });
  }

  /** Time a synchronous piece of work as one event. */
  time<T>(kind: BuildKind, what: string, fn: () => T): T {
    const t0 = this.now();
    try { return fn(); } finally { this.record(kind, this.now() - t0, what, t0); }
  }

  /** Policy breaches, one line each (empty: the policy holds). */
  violations(): string[] {
    const out: string[] = [];
    for (const e of this.events) {
      if (BLOCKING.has(e.kind) && e.ms > this.budgetMs) out.push(`${e.phase}: ${e.kind} "${e.what}" blocked ${e.ms.toFixed(0)} ms (budget ${this.budgetMs} ms)`);
    }
    const starts = this.events.filter((e) => e.phase === 'run' && STARTS.has(e.kind)).sort((a, b) => a.t - b.t);
    const rest = 1 / this.share - 1;
    for (let i = 1; i < starts.length; i++) {
      const a = starts[i - 1], b = starts[i], earliest = a.t + a.ms + a.ms * rest;
      if (b.t < earliest - 1) out.push(`run: "${b.what}" started ${(b.t - a.t - a.ms).toFixed(0)} ms after a build of ${a.ms.toFixed(0)} ms ended (minimum ${(a.ms * rest).toFixed(0)} ms)`);
    }
    return out;
  }

  summary(): { warmup: number; run: number; worstMs: number; violations: number } {
    const blocking = this.events.filter((e) => BLOCKING.has(e.kind));
    return {
      warmup: this.events.filter((e) => e.phase === 'warmup' && STARTS.has(e.kind)).length,
      run: this.events.filter((e) => e.phase === 'run' && STARTS.has(e.kind)).length,
      worstMs: blocking.reduce((m, e) => Math.max(m, e.ms), 0),
      violations: this.violations().length,
    };
  }

  report(): string {
    const s = this.summary();
    return [`shaders: ${s.warmup} built in warm-up, ${s.run} after, worst block ${s.worstMs.toFixed(0)} ms, ${s.violations} violations`, ...this.violations()].join('\n');
  }
}
