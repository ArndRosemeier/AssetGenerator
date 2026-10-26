/**
 * The post chain: the scene drawn into a pass of its own, then bloom, then the renderer's tone curve.
 * Hand `target` and `draw` to the Stage (StageOptions), so shaders are compiled against the scene pass and
 * the chain's own shaders are built in the warm-up, not on the render path.
 */
import { RenderPipeline, type Camera, type RenderTarget, type Scene, type WebGPURenderer } from 'three/webgpu';
import { pass, uniform } from 'three/tsl';
import { bloom } from 'three/examples/jsm/tsl/display/BloomNode.js';

export interface PostOptions {
  /** Glow around what is brighter than `threshold` (scene light before exposure); off without it. */
  bloom?: { strength: number; radius: number; threshold: number };
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
  const scenePass = pass(scene, camera);
  const color = scenePass.getTextureNode('output');
  let out: { add?: unknown } = color;
  let glow: Post['bloom'] = null;
  if (opts.bloom) {
    const b = bloom(color, uniform(opts.bloom.strength), uniform(opts.bloom.radius), uniform(opts.bloom.threshold));
    glow = { strength: b.strength, radius: b.radius, threshold: b.threshold };
    out = color.add(b);
  }
  const pipeline = new RenderPipeline(renderer, out as typeof color);
  return {
    draw: () => pipeline.render(),
    target: () => scenePass.renderTarget,
    bloom: glow,
  };
}
