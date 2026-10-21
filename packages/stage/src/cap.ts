/**
 * The shader cap (see the game's docs/SHADERS.md): after the loading screen, new shaders start at most
 * `maxPerSecond` per second and at least `1000 / maxPerSecond` ms apart, one per frame. With each
 * compile under 100 ms, at most half of any stretch of time goes to shaders, so the game never
 * freezes. During warm-up (`active = false`) everything compiles at full speed.
 *
 * Ported from Scale (src/render/shaderCap.ts) via Dunfinity, with the clock injectable for tests.
 */
export class ShaderCap {
  maxPerSecond = 5;
  /** Off during warm-up. */
  active = false;
  /** Builds waiting for room right now. */
  waiting = 0;
  private spent: number[] = [];
  private lastAt = -1e9;
  private frameTaken = false;

  constructor(private readonly now: () => number = () => performance.now(), private readonly nextFrame: (fn: () => void) => void = (fn) => requestAnimationFrame(fn)) {}

  /** Once per frame, before anything starts a build. */
  newFrame(): void { this.frameTaken = false; }

  private lastSecond(t: number): number {
    while (this.spent.length && this.spent[0] <= t - 1000) this.spent.shift();
    return this.spent.length;
  }

  room(): boolean {
    if (!this.active || this.maxPerSecond <= 0) return true;
    const t = this.now();
    return !this.frameTaken && t - this.lastAt >= 1000 / this.maxPerSecond && this.lastSecond(t) < this.maxPerSecond;
  }

  /** Book one new shader starting now. */
  take(): void {
    const t = this.now();
    this.frameTaken = true;
    this.lastAt = t;
    this.spent.push(t);
  }

  /** Resolves on a frame with room, and takes it. */
  slot(): Promise<void> {
    if (this.room()) { this.take(); return Promise.resolve(); }
    this.waiting++;
    return new Promise((res) => {
      const again = (): void => {
        if (!this.room()) { this.nextFrame(again); return; }
        this.waiting--;
        this.take();
        res();
      };
      this.nextFrame(again);
    });
  }
}
