/**
 * The CPU path (WebGL 2, or a WebGPU device without indirect-first-instance): every part is a batch whose
 * matrices are written on the CPU, with the levels chosen again whenever the camera has moved `step` metres.
 * No view culling: the batches are drawn whole (not frustum-culled, they cover the camera all round).
 */
import { Group, Mesh, type Camera, type InstancedBufferGeometry, type InstancedInterleavedBuffer } from 'three/webgpu';
import { batchCap, instancedGeometry } from './geometry';
import { DITHER, KIND, RECORD, inLod, viewDistance } from './select';
import type { DrawKind, DrawOptions, DrawPart, InstanceDraws } from './types';

interface Batch { part: DrawPart; mesh: Mesh<InstancedBufferGeometry>; matrices: Float32Array; buffer: InstancedInterleavedBuffer; cap: number; n: number }

export class CpuInstanceDraws implements InstanceDraws {
  readonly group = new Group();
  readonly path = 'cpu' as const;
  /** Per kind, per level: its batches. */
  private readonly batches: Batch[][][];
  private data = new Float32Array(0);
  private count = 0;
  private readonly at: [number, number, number] = [Infinity, 0, 0];
  private dirty = true;

  constructor(private readonly kinds: DrawKind[], private readonly opts: DrawOptions = {}) {
    const cap = batchCap(opts.capacity ?? 0);
    this.batches = kinds.map((k) => k.lods.map((l) => l.parts.map((part) => this.batch(part, cap))));
  }

  private batch(part: DrawPart, cap: number): Batch {
    const { geometry, matrices, buffer } = instancedGeometry(part.geometry, cap);
    const mesh = new Mesh(geometry, part.material);
    mesh.frustumCulled = false;
    mesh.castShadow = part.castShadow ?? false;
    mesh.receiveShadow = part.receiveShadow ?? false;
    if (part.name) mesh.name = part.name;
    this.group.add(mesh);
    return { part, mesh, matrices, buffer, cap, n: 0 };
  }

  set(data: Float32Array, count: number): void {
    if (this.data.length < count * RECORD) this.data = new Float32Array(count * RECORD);
    this.data.set(data.subarray(0, count * RECORD));
    this.count = count;
    this.dirty = true;
  }

  update(camera: Camera): void {
    const p = camera.position;
    const step = this.opts.step ?? 8;
    if (!this.dirty && Math.hypot(p.x - this.at[0], p.y - this.at[1], p.z - this.at[2]) <= step) return;
    this.dirty = false;
    this.at[0] = p.x; this.at[1] = p.y; this.at[2] = p.z;
    for (const k of this.batches) for (const l of k) for (const b of l) b.n = 0;
    const d = this.data, horizontal = !!this.opts.horizontal;
    for (let i = 0; i < this.count; i++) {
      const o = i * RECORD, kind = d[o + KIND];
      const lods = this.kinds[kind]?.lods;
      if (!lods) continue;
      const dist = viewDistance(this.at, d[o + 12], d[o + 13], d[o + 14], horizontal);
      lods.forEach((l, li) => {
        if (!inLod(l, dist, d[o + DITHER])) return;
        for (const b of this.batches[kind][li]) {
          if (b.n >= b.cap) this.grow(b);
          b.matrices.set(d.subarray(o, o + 16), b.n++ * 16);
        }
      });
    }
    for (const k of this.batches) for (const l of k) for (const b of l) {
      b.mesh.geometry.instanceCount = b.n;
      b.buffer.needsUpdate = true;
    }
  }

  /** A full batch: a bigger geometry, same material (same shaders, nothing to build). */
  private grow(b: Batch): void {
    const cap = batchCap(b.cap + 1);
    const { geometry, matrices, buffer } = instancedGeometry(b.part.geometry, cap);
    matrices.set(b.matrices);
    b.mesh.geometry.dispose();
    b.mesh.geometry = geometry;
    Object.assign(b, { matrices, buffer, cap });
  }

  async ready(): Promise<void> {}

  async counts(): Promise<number[]> {
    return this.batches.flat(2).map((b) => b.n);
  }

  dispose(): void {
    for (const b of this.batches.flat(2)) b.mesh.geometry.dispose();
    this.group.clear();
  }
}
