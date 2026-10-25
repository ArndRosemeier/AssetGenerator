/**
 * Instances drawn by distance and view, for any repeated mesh (trees, rocks, buildings, crowds): see README.
 * `createInstanceDraws` picks the GPU path (compute culling, indirect draws) where WebGPU allows it, else the CPU path.
 */
import type { WebGPURenderer } from 'three/webgpu';
import { CpuInstanceDraws } from './cpu';
import { GpuInstanceDraws, gpuInstancesSupported } from './gpu';
import type { DrawKind, DrawOptions, InstanceDraws } from './types';

export * from './select';
export * from './geometry';
export * from './types';
export { CpuInstanceDraws } from './cpu';
export { GpuInstanceDraws, gpuInstancesSupported, kindSphere } from './gpu';

/** The GPU path when the renderer can take it (WebGPU with indirect-first-instance) and `opts.cpu` is not set, else the CPU path. */
export function createInstanceDraws(renderer: WebGPURenderer, kinds: DrawKind[], opts: DrawOptions = {}): InstanceDraws {
  return !opts.cpu && gpuInstancesSupported(renderer) ? new GpuInstanceDraws(renderer, kinds, opts) : new CpuInstanceDraws(kinds, opts);
}
