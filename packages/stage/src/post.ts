/**
 * The post chain: the scene drawn into a render target of its own, then bloom, then the renderer's
 * tone curve, then FXAA. Hand `target` and `draw` to the Stage (StageOptions), so shaders are compiled
 * against that target and the chain's own shaders are built in the warm-up, not on the render path.
 *
 * The scene is drawn by `draw` itself, at the top level, not by a `pass()` node inside the pipeline:
 * three keys a render context by call depth too, and a pass draws one level down (inside the
 * pipeline's own quad), so everything the Stage compiled ahead at the top level was built again in
 * play, shadows included.
 */
import { DepthTexture, FloatType, HalfFloatType, RenderPipeline, RenderTarget, Vector2, type Camera, type Scene, type WebGPURenderer } from 'three/webgpu';
import { renderOutput, texture, uniform } from 'three/tsl';
import { bloom } from 'three/examples/jsm/tsl/display/BloomNode.js';
import { fxaa } from 'three/examples/jsm/tsl/display/FXAANode.js';

export interface PostOptions {
  /** Glow around what is brighter than `threshold` (scene light before exposure); off without it. */
  bloom?: { strength: number; radius: number; threshold: number };
  /**
   * Multisampling of the scene target (default 0). On WebGL2 resolving a multisampled float depth
   * buffer fails (glBlitFramebuffer) and the frame comes out black, so smoothing is FXAA by default.
   */
  samples?: number;
  /** FXAA after the tone curve (default true). */
  fxaa?: boolean;
  /** A float depth buffer for the scene target (a reversed depth buffer needs one; default true). */
  floatDepth?: boolean;
}

export interface Post {
  /** Draws one frame through the chain. */
  draw(): void;
  /** Where the scene itself is drawn (compile against it). */
  target(): RenderTarget;
  /** Bloom's knobs, live (uniforms); null without bloom. */
  readonly bloom: { strength: { value: number }; radius: { value: number }; threshold: { value: number } } | null;
}

export function createPost(renderer: WebGPURenderer, scene: Scene, camera: Camera, opts: PostOptions = {}): Post {
  const depth = new DepthTexture(1, 1);
  if (opts.floatDepth ?? true) depth.type = FloatType;
  const rt = new RenderTarget(1, 1, { type: HalfFloatType, depthTexture: depth, samples: opts.samples ?? 0 });
  const color = texture(rt.texture);
  let out = color as unknown as ReturnType<typeof renderOutput>;
  let glow: Post['bloom'] = null;
  if (opts.bloom) {
    const b = bloom(color, uniform(opts.bloom.strength), uniform(opts.bloom.radius), uniform(opts.bloom.threshold));
    glow = { strength: b.strength, radius: b.radius, threshold: b.threshold };
    out = color.add(b) as unknown as typeof out;
  }
  const pipeline = new RenderPipeline(renderer, out);
  if (opts.fxaa ?? true) {
    pipeline.outputNode = fxaa(renderOutput(out)) as unknown as typeof out;
    pipeline.outputColorTransform = false;
  }
  const size = new Vector2();
  return {
    draw: () => {
      renderer.getDrawingBufferSize(size);
      if (rt.width !== size.x || rt.height !== size.y) rt.setSize(size.x, size.y);
      const prev = renderer.getRenderTarget();
      renderer.setRenderTarget(rt);
      renderer.render(scene, camera);
      renderer.setRenderTarget(prev);
      pipeline.render();
    },
    target: () => rt,
    bloom: glow,
  };
}
