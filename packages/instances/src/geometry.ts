/**
 * Instances as geometry attributes: the instance matrix is iM0..iM3 (its four columns, vec4 each) of one
 * interleaved buffer. Materials read those names (see @futuremagic/vegetation), so batches of any size and
 * number share their shaders, unlike InstancedMesh (one shader per mesh).
 */
import { InstancedBufferGeometry, InstancedInterleavedBuffer, InterleavedBufferAttribute, DynamicDrawUsage, type BufferGeometry } from 'three/webgpu';

/** The source's attributes and index on a new instanced geometry (shared, not copied). */
export function instancedFrom(source: BufferGeometry): InstancedBufferGeometry {
  const g = new InstancedBufferGeometry();
  for (const [name, a] of Object.entries(source.attributes)) g.setAttribute(name, a);
  g.setIndex(source.index);
  return g;
}

/** iM0..iM3 on `g`, read from `buffer` (16 floats per instance). */
export function setInstanceMatrices(g: BufferGeometry, buffer: InstancedInterleavedBuffer): InterleavedBufferAttribute[] {
  const cols: InterleavedBufferAttribute[] = [];
  for (let c = 0; c < 4; c++) {
    const a = new InterleavedBufferAttribute(buffer, 4, c * 4);
    g.setAttribute(`iM${c}`, a);
    cols.push(a);
  }
  return cols;
}

/**
 * A batch of `capacity` instances of `source` (its attributes and index shared) as an instanced geometry:
 * the instance matrices are the attributes iM0..iM3 of one interleaved buffer (`matrices`, 16 floats per
 * instance, column-major like Matrix4.elements). Draw it with a plain Mesh (not frustum-culled) and set
 * `instanceCount`.
 */
export function instancedGeometry(source: BufferGeometry, capacity: number): { geometry: InstancedBufferGeometry; matrices: Float32Array; buffer: InstancedInterleavedBuffer } {
  const g = instancedFrom(source);
  const matrices = new Float32Array(capacity * 16);
  const buffer = new InstancedInterleavedBuffer(matrices, 16, 1);
  buffer.setUsage(DynamicDrawUsage);
  setInstanceMatrices(g, buffer);
  g.instanceCount = 0;
  return { geometry: g, matrices, buffer };
}

/**
 * Room for `n` instances with headroom, in few big steps (a batch that grows gets a new buffer; the
 * shaders stay the same).
 */
export function batchCap(n: number): number {
  let c = 512;
  while (c < n * 1.25) c *= 4;
  return c;
}
