/**
 * The CPU path (WebGL 2, or a WebGPU device without indirect-first-instance): every part is a batch whose
 * matrices are written on the CPU, with the levels chosen again whenever the camera has moved `step` metres.
 * No view culling: the batches are drawn whole (not frustum-culled, they cover the camera all round).
 */
import { Group, Mesh, Vector3, type Camera, type InstancedBufferGeometry, type InstancedInterleavedBuffer } from 'three/webgpu';
import { batchCap, instancedGeometry } from './geometry';
import { DITHER, KIND, RECORD, frameAt, inLod, viewDistance, worldMatrix } from './select';
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
  /** The origin the batches were last written relative to (opts.origin). */
  private readonly drawnAt: [number, number, number] = [0, 0, 0];
  private readonly cam = new Vector3();
  private dirty = true;
  /** While shaders build, every batch draws at least one instance. */
  private preparing = false;
  /** The frames (opts.frames) as read on this update, and as the batches were last written with. */
  private readonly frames: Float64Array;
  private readonly framesDrawn: Float64Array;
  /** The frames as they were when the levels were last chosen (a frame that moves `step` away chooses again). */
  private readonly framesChosen: Float64Array;
  /** Batch slots holding an instance in a moving frame (rewritten when only the frames moved): batch, slot, record. */
  private framed: { b: Batch[]; at: number[]; rec: number[] } = { b: [], at: [], rec: [] };

  constructor(private readonly kinds: DrawKind[], private readonly opts: DrawOptions = {}) {
    const cap = batchCap(opts.capacity ?? 0);
    const nf = (opts.frames?.length ?? 0) * 16;
    this.frames = new Float64Array(nf);
    this.framesDrawn = new Float64Array(nf).fill(NaN);
    this.framesChosen = new Float64Array(nf).fill(NaN);
    this.batches = kinds.map((k) => k.lods.map((l) => l.parts.map((part) => this.batch(part, cap))));
  }

  private batch(part: DrawPart, cap: number): Batch {
    const { geometry, matrices, buffer } = instancedGeometry(part.geometry, cap);
    const mesh = new Mesh(geometry, part.material);
    mesh.frustumCulled = false;
    mesh.castShadow = part.castShadow ?? false;
    mesh.receiveShadow = part.receiveShadow ?? false;
    mesh.renderOrder = part.renderOrder ?? 0;
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
    const p = camera.getWorldPosition(this.cam);
    const step = this.opts.step ?? 8, org = this.opts.origin, ox = org?.x ?? 0, oy = org?.y ?? 0, oz = org?.z ?? 0;
    // A step of the origin moves every instance's drawn position.
    if (ox !== this.drawnAt[0] || oy !== this.drawnAt[1] || oz !== this.drawnAt[2]) this.dirty = true;
    const F = this.frames;
    this.opts.frames?.forEach((m, k) => F.set(m.elements, k * 16));
    // A frame that has gone `step` from where the levels were chosen chooses them again.
    for (let f = 0; f < F.length && !this.dirty; f += 16) {
      if (!(Math.hypot(F[f + 12] - this.framesChosen[f + 12], F[f + 13] - this.framesChosen[f + 13], F[f + 14] - this.framesChosen[f + 14]) <= step)) this.dirty = true;
    }
    if (!this.dirty && Math.hypot(p.x - this.at[0], p.y - this.at[1], p.z - this.at[2]) <= step) {
      if (!sameFrames(F, this.framesDrawn)) this.moveFramed(ox, oy, oz);
      return;
    }
    this.dirty = false;
    this.drawnAt[0] = ox; this.drawnAt[1] = oy; this.drawnAt[2] = oz;
    this.at[0] = p.x; this.at[1] = p.y; this.at[2] = p.z;
    this.framesChosen.set(F);
    this.framesDrawn.set(F);
    for (const k of this.batches) for (const l of k) for (const b of l) b.n = 0;
    const framed: CpuInstanceDraws['framed'] = { b: [], at: [], rec: [] };
    const d = this.data, horizontal = !!this.opts.horizontal, nf = F.length ? F : undefined;
    for (let i = 0; i < this.count; i++) {
      const o = i * RECORD, kind = d[o + KIND];
      const lods = this.kinds[kind]?.lods;
      if (!lods) continue;
      const f = frameAt(d, o, nf);
      const dist = f < 0
        ? viewDistance(this.at, d[o + 12], d[o + 13], d[o + 14], horizontal)
        : viewDistance(this.at, ...framePoint(F, f, d[o + 12], d[o + 13], d[o + 14]), horizontal);
      lods.forEach((l, li) => {
        if (!inLod(l, dist, d[o + DITHER])) return;
        for (const b of this.batches[kind][li]) {
          if (b.n >= b.cap) this.grow(b);
          const at = b.n++ * 16;
          this.write(b, at, o, nf, ox, oy, oz);
          if (f >= 0) { framed.b.push(b); framed.at.push(at); framed.rec.push(o); }
        }
      });
    }
    this.framed = framed;
    for (const k of this.batches) for (const l of k) for (const b of l) {
      b.mesh.geometry.instanceCount = this.preparing ? Math.max(1, b.n) : b.n;
      b.buffer.needsUpdate = true;
    }
  }

  /** Record `o` into batch `b` at float `at`: in the world (its frame's matrix times its own), relative to the origin. */
  private write(b: Batch, at: number, o: number, frames: Float64Array | undefined, ox: number, oy: number, oz: number): void {
    // Through a frame in doubles, so a far ship's fittings lose nothing before the origin is taken off.
    worldMatrix(this.data, o, frames, _m);
    _m[12] -= ox; _m[13] -= oy; _m[14] -= oz;
    b.matrices.set(_m, at);
  }

  /** Only the frames moved: their instances written again where they are (the levels stay as chosen). */
  private moveFramed(ox: number, oy: number, oz: number): void {
    const { b, at, rec } = this.framed;
    for (let i = 0; i < b.length; i++) this.write(b[i], at[i], rec[i], this.frames, ox, oy, oz);
    for (const x of new Set(b)) x.buffer.needsUpdate = true;
    this.framesDrawn.set(this.frames);
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

  async prepare(compile: (group: Group) => Promise<void>): Promise<void> {
    this.preparing = true;
    for (const b of this.batches.flat(2)) b.mesh.geometry.instanceCount = Math.max(1, b.n);
    try {
      await compile(this.group);
    } finally {
      this.preparing = false;
      for (const b of this.batches.flat(2)) b.mesh.geometry.instanceCount = b.n;
    }
  }

  async counts(): Promise<number[]> {
    return this.batches.flat(2).map((b) => b.n);
  }

  dispose(): void {
    for (const b of this.batches.flat(2)) b.mesh.geometry.dispose();
    this.group.clear();
  }
}

const _m = new Float64Array(16);

/** Whether two sets of frames are the same (NaN, not drawn yet, never is). */
function sameFrames(a: Float64Array, b: Float64Array): boolean {
  for (let i = 0; i < a.length; i++) if (a[i] !== b[i]) return false;
  return true;
}

/** Point (x, y, z) of the frame at `f` in the world. */
function framePoint(F: Float64Array, f: number, x: number, y: number, z: number): [number, number, number] {
  return [F[f] * x + F[f + 4] * y + F[f + 8] * z + F[f + 12], F[f + 1] * x + F[f + 5] * y + F[f + 9] * z + F[f + 13], F[f + 2] * x + F[f + 6] * y + F[f + 10] * z + F[f + 14]];
}
