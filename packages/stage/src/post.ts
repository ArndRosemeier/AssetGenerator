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
import { DepthTexture, FloatType, HalfFloatType, Matrix4, RenderPipeline, RenderTarget, Vector2, WebGLCoordinateSystem, type Camera, type Node, type Scene, type WebGPURenderer } from 'three/webgpu';
import { convertToTexture, float, mix, renderOutput, texture, uniform, vec2, vec4 } from 'three/tsl';
import { bloom } from 'three/examples/jsm/tsl/display/BloomNode.js';
import { ao as gtao } from 'three/examples/jsm/tsl/display/GTAONode.js';
import { depthAwareBlur } from 'three/examples/jsm/tsl/display/depthAwareBlur.js';
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
  /**
   * Ambient occlusion (GTAO, half resolution, blurred along surfaces): contact shade in corners and
   * under things. `radius` in world units; `strength` 0..1 how dark full occlusion gets.
   */
  ao?: { radius: number; strength: number; samples?: number };
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
  /** Ambient occlusion's knobs, live (uniforms); null without it. */
  readonly ao: { strength: { value: number }; radius: { value: number } } | null;
}

export function createPost(renderer: WebGPURenderer, scene: Scene, camera: Camera, opts: PostOptions = {}): Post {
  const depth = new DepthTexture(1, 1);
  if (opts.floatDepth ?? true) depth.type = FloatType;
  const rt = new RenderTarget(1, 1, { type: HalfFloatType, depthTexture: depth, samples: opts.samples ?? 0 });
  let color: Node<'vec4'> = vec4(texture(rt.texture));
  const size = new Vector2();
  const texel = uniform(new Vector2(1, 1));
  let shade: Post['ao'] = null;
  let fixProjection = (): void => {};
  if (opts.ao) {
    const depthNode = texture(depth);
    const a = gtao(depthNode, null as unknown as typeof depthNode, camera); // no normals: from depth
    a.resolutionScale = 0.5;
    a.samples.value = opts.ao.samples ?? 8;
    a.radius.value = opts.ao.radius;
    fixProjection = webglReversedFix(renderer, camera, a as unknown as GtaoMatrices);
    const raw = a.getTextureNode();
    const across = convertToTexture(vec4(depthAwareBlur(raw, depthNode, vec2(texel.x, 0), camera, 2, opts.ao.radius)));
    const blurred = depthAwareBlur(across, depthNode, vec2(0, texel.y), camera, 2, opts.ao.radius);
    const strength = uniform(opts.ao.strength);
    // The sky (cleared depth) gets none.
    const d = depthNode.r;
    const sky = renderer.reversedDepthBuffer ? d.lessThanEqual(0) : d.greaterThanEqual(1);
    const factor = sky.select(float(1), mix(float(1), blurred, strength));
    color = color.mul(vec4(factor, factor, factor, 1));
    shade = { strength, radius: a.radius };
  }
  let out = color;
  let glow: Post['bloom'] = null;
  if (opts.bloom) {
    const b = bloom(color, uniform(opts.bloom.strength), uniform(opts.bloom.radius), uniform(opts.bloom.threshold));
    glow = { strength: b.strength, radius: b.radius, threshold: b.threshold };
    out = color.add(b);
  }
  const pipeline = new RenderPipeline(renderer, out);
  if (opts.fxaa ?? true) {
    pipeline.outputNode = fxaa(renderOutput(out)) as unknown as typeof out;
    pipeline.outputColorTransform = false;
  }
  return {
    draw: () => {
      renderer.getDrawingBufferSize(size);
      if (rt.width !== size.x || rt.height !== size.y) rt.setSize(size.x, size.y);
      texel.value.set(1 / size.x, 1 / size.y);
      fixProjection();
      const prev = renderer.getRenderTarget();
      renderer.setRenderTarget(rt);
      renderer.render(scene, camera);
      renderer.setRenderTarget(prev);
      pipeline.render();
    },
    target: () => rt,
    bloom: glow,
    ao: shade,
  };
}

/** GTAONode's camera matrices (uniforms it keeps). */
interface GtaoMatrices { _cameraProjectionMatrix: { value: Matrix4 }; _cameraProjectionMatrixInverse: { value: Matrix4 } }

/**
 * GTAO turns depth back into positions the WebGL way (clip z = 2·depth - 1), but a reversed depth
 * buffer on WebGL (clip control) keeps clip z in 0..1. So on that backend it gets the camera's
 * projection followed by that same remap (z' = 2z - w), which its inverse undoes. Elsewhere: no-op.
 */
function webglReversedFix(renderer: WebGPURenderer, camera: Camera, a: GtaoMatrices): () => void {
  if (!renderer.reversedDepthBuffer || renderer.coordinateSystem !== WebGLCoordinateSystem) return () => {};
  const remap = new Matrix4().set(1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 2, -1, 0, 0, 0, 1);
  const proj = new Matrix4(), inv = new Matrix4();
  a._cameraProjectionMatrix.value = proj;
  a._cameraProjectionMatrixInverse.value = inv;
  return () => {
    proj.multiplyMatrices(remap, camera.projectionMatrix);
    inv.copy(proj).invert();
  };
}
