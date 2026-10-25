/**
 * A mesher: surfaceNets behind one async call, so the CPU and GPU versions are interchangeable.
 * Pick one at startup (`cpuMesher`, or `await gpuMesher(device)` from `@futuremagic/volume/gpu`) and
 * call `mesh` with the same arguments as `surfaceNets`; both give the same mesh.
 */
import { surfaceNets, type Grid, type MeshData } from './surfaceNets';

export interface Mesher {
  readonly kind: 'cpu' | 'gpu';
  /** Same arguments and result as `surfaceNets`. */
  mesh(grid: Grid, ox: number, oy: number, oz: number, step: number, overlap?: number): Promise<MeshData | null>;
}

/** `surfaceNets` on this thread (or worker). */
export const cpuMesher: Mesher = {
  kind: 'cpu',
  mesh: async (grid, ox, oy, oz, step, overlap = 0) => surfaceNets(grid, ox, oy, oz, step, overlap),
};
