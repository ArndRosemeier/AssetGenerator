// @ts-nocheck -- three's TSL typings infer swizzles and vector widths poorly; checked on the GPU (test/gpu).
/**
 * The GPU path: culling and packing in compute passes, drawn with indirect draws, nothing read back.
 *
 * Every frame, three passes (one compute submit, before the frame's render):
 *   1. reset   one thread per list: its counter to 0
 *   2. cull    one thread per instance: its sphere against the view frustum (swept along the light, so
 *              casters of shadows into the view stay), then for each of its kind's levels whose distance
 *              range (and dither) it is in, an atomic slot in that level's list and its matrix copied there
 *   3. finish  one thread per draw: the indirect draw arguments (index count, instances = the list's count,
 *              first instance = the list's first slot)
 * The lists share one output buffer, and every part's geometry reads its matrices from it as iM0..iM3 (the
 * vertex attributes materials already use), starting at its list's first slot. So materials need no change.
 *
 * A list gets room for every instance of its kind, so it never overflows; the layout is made on `set`.
 * Needs WebGPU with 'indirect-first-instance' (each draw starts at its list's slot).
 */
import {
  Frustum, Group, MathUtils, Matrix4, Mesh, Sphere, StorageBufferAttribute, StorageInstancedBufferAttribute, IndirectStorageBufferAttribute,
  InterleavedBufferAttribute, Vector3, Vector4, type Camera, type InstancedBufferGeometry, type WebGPURenderer,
} from 'three/webgpu';
import { Fn, If, Loop, atomicAdd, atomicLoad, atomicStore, dot, instanceIndex, length, max, min, smoothstep, storage, uint, uniform, uniformArray, vec3, vec4 } from 'three/tsl';
import { instancedFrom } from './geometry';
import { KIND, RECORD, listLayout, listsInUse, type LodRange } from './select';
import type { DrawKind, DrawOptions, InstanceDraws } from './types';

/** vec4s per record. */
const R4 = RECORD / 4;
/** The lists in use are found again once the camera has moved this far (m); a list counts within twice this of its range. */
const RECHECK = 4;
/** Fade bounds that never fade (smoothstep needs start < end). */
const NO_FADE = [1e30, 2e30];

/**
 * The output: a storage buffer that is also an instanced interleaved buffer (16 floats per instance), so
 * compute writes it and the vertex stage reads it as iM0..iM3. three keys GPU buffers by this object, so both
 * uses get the same buffer; the attributes are flagged storage so it is made with STORAGE | VERTEX usage
 * whichever use comes first.
 */
class MatrixBuffer extends StorageInstancedBufferAttribute {
  /** three tells interleaved buffers apart by uuid (RenderObject.needsGeometryUpdate): without one a new buffer goes unnoticed. */
  readonly uuid = MathUtils.generateUUID();
  readonly stride = 16;
  readonly isInterleavedBuffer = true;
  readonly isInstancedInterleavedBuffer = true;
  meshPerAttribute = 1;
  constructor(count: number) { super(new Float32Array(Math.max(1, count) * 16), 16); }
}

/** Whether `renderer` can take the GPU path. */
export function gpuInstancesSupported(renderer: WebGPURenderer): boolean {
  const b = (renderer as any).backend;
  return !!b?.isWebGPUBackend && !!b.device?.features?.has('indirect-first-instance');
}

interface Draw { geometry: InstancedBufferGeometry; list: number; mesh: Mesh }

export class GpuInstanceDraws implements InstanceDraws {
  readonly group = new Group();
  readonly path = 'gpu' as const;
  private readonly draws: Draw[] = [];
  /** Per kind: its local bounding sphere, first list and number of lists. */
  private readonly kindTable: StorageBufferAttribute;
  private readonly listTable: StorageBufferAttribute;
  private readonly drawTable: StorageBufferAttribute;
  private readonly counters: StorageBufferAttribute;
  private readonly indirect: IndirectStorageBufferAttribute;
  private input!: StorageBufferAttribute;
  private out!: MatrixBuffer;
  private passes!: { reset: any; cull: any; finish: any };
  private readonly planes = Array.from({ length: 6 }, () => new Vector4());
  private readonly uPlanes = uniformArray(this.planes);
  private readonly uCam = uniform(new Vector3());
  private readonly uSweep = uniform(new Vector3());
  /** The floating origin (opts.origin): instances are culled and drawn relative to it. */
  private readonly uOrigin = uniform(new Vector3());
  private readonly frustum = new Frustum();
  private readonly pv = new Matrix4();
  private readonly listsOfKind: number[];
  private readonly nLists: number;
  /** Per kind its local sphere, per list its levels (for `listsInUse`). */
  private readonly spheres: [number, number, number, number][];
  private readonly ranges: LodRange[] = [];
  /** Where the lists in use were last found (NaN: find them on the next update). */
  private readonly checkedAt = new Vector3(NaN, NaN, NaN);
  private readonly eye = new Vector3();

  constructor(private readonly renderer: WebGPURenderer, private readonly kinds: DrawKind[], private readonly opts: DrawOptions = {}) {
    this.listsOfKind = kinds.map((k) => k.lods.length);
    this.nLists = this.listsOfKind.reduce((a, b) => a + b, 0);
    const kt = new Float32Array(kinds.length * 8);
    const lt = new Float32Array(Math.max(1, this.nLists) * 8);
    let list = 0;
    this.spheres = [];
    kinds.forEach((k, ki) => {
      const s = kindSphere(k);
      this.spheres.push([s.center.x, s.center.y, s.center.z, s.radius]);
      kt.set([s.center.x, s.center.y, s.center.z, s.radius, list, k.lods.length, 0, 0], ki * 8);
      for (const l of k.lods) {
        this.ranges.push(l);
        const fade = l.fade ?? NO_FADE;
        lt.set([l.near ?? 0, l.far, fade[0], fade[1], 0, 0, 0, 0], list * 8);
        for (const part of l.parts) {
          const geometry = instancedFrom(part.geometry);
          geometry.instanceCount = 1; // drawn indirectly; three skips a draw of 0 instances
          const mesh = new Mesh(geometry, part.material);
          mesh.frustumCulled = false;
          mesh.castShadow = part.castShadow ?? false;
          mesh.receiveShadow = part.receiveShadow ?? false;
          mesh.renderOrder = part.renderOrder ?? 0;
    if (part.name) mesh.name = part.name;
          this.group.add(mesh);
          this.draws.push({ geometry, list, mesh });
        }
        list++;
      }
    });
    this.kindTable = new StorageBufferAttribute(kt, 4);
    this.listTable = new StorageBufferAttribute(lt, 4);
    // Per draw: list, index (or vertex) count, first index, indexed (1) or not.
    const dt = new Uint32Array(Math.max(1, this.draws.length) * 4);
    this.draws.forEach((d, i) => {
      const g = d.geometry, idx = g.index;
      dt.set([d.list, idx ? idx.count : g.attributes.position.count, 0, idx ? 1 : 0], i * 4);
    });
    this.drawTable = new StorageBufferAttribute(dt, 4);
    this.counters = new StorageBufferAttribute(new Uint32Array(Math.max(1, this.nLists)), 1);
    this.indirect = new IndirectStorageBufferAttribute(new Uint32Array(Math.max(1, this.draws.length) * 5), 5);
    this.draws.forEach((d, i) => d.geometry.setIndirect(this.indirect, i * 20));
    this.allocate(opts.capacity ?? 4096, 0);
  }

  /** Input room for `records` instances and output room for `slots`; new buffers mean new passes (same code: cache hits). */
  private allocate(records: number, slots: number): void {
    let grown = false;
    if (!this.input || this.input.count < records * R4) {
      // Headroom, so streaming in more instances rarely grows the buffers again.
      this.input = new StorageBufferAttribute(new Float32Array(Math.max(1, Math.ceil(records * 1.5)) * RECORD), 4);
      grown = true;
    }
    if (!this.out || this.out.count < slots) {
      this.out = new MatrixBuffer(Math.max(Math.ceil(slots * 1.5), this.out ? this.out.count * 2 : 0));
      for (const d of this.draws) {
        for (let c = 0; c < 4; c++) {
          const a = new InterleavedBufferAttribute(this.out as any, 4, c * 4);
          a.isStorageInstancedBufferAttribute = true;
          d.geometry.setAttribute(`iM${c}`, a);
        }
      }
      grown = true;
    }
    // New buffers need passes bound to them (same code: cache hits).
    if (grown) this.passes = undefined;
  }

  private build(): { reset: any; cull: any; finish: any } {
    const nLists = this.nLists, nDraws = this.draws.length, nKinds = this.kinds.length;
    const input = storage(this.input, 'vec4', this.input.count).toReadOnly();
    const out = storage(this.out, 'vec4', this.out.count * 4);
    const kinds = storage(this.kindTable, 'vec4', this.kindTable.count).toReadOnly();
    const lists = storage(this.listTable, 'vec4', this.listTable.count).toReadOnly();
    const draws = storage(this.drawTable, 'uvec4', this.drawTable.count).toReadOnly();
    const counters = storage(this.counters, 'uint', this.counters.count).toAtomic();
    const ind = storage(this.indirect, 'uint', this.indirect.count * 5);
    const horizontal = !!this.opts.horizontal;
    const planes = this.uPlanes, cam = this.uCam, sweep = this.uSweep, origin = this.uOrigin;

    const reset = Fn(() => { atomicStore(counters.element(instanceIndex), uint(0)); })().compute(nLists);

    const cull = Fn(() => {
      const b = instanceIndex.mul(R4);
      const c0 = input.element(b).toVar(), c1 = input.element(b.add(1)).toVar(), c2 = input.element(b.add(2)).toVar();
      // Relative to the origin before anything else (both near it: an exact float32 difference).
      const c3 = vec4(input.element(b.add(3)).xyz.sub(origin), 1).toVar();
      const ex = input.element(b.add(KIND / 4)).toVar();
      const kind = uint(ex.x).toVar();
      const ks = kinds.element(kind.mul(2)).toVar(), kl = kinds.element(kind.mul(2).add(1)).toVar();
      const center = c0.xyz.mul(ks.x).add(c1.xyz.mul(ks.y)).add(c2.xyz.mul(ks.z)).add(c3.xyz).toVar();
      const r = ks.w.mul(max(length(c0.xyz), max(length(c1.xyz), length(c2.xyz)))).toVar();
      const seen = uint(1).toVar();
      Loop(6, ({ i }) => {
        const p = planes.element(i);
        const d = dot(p.xyz, center).add(p.w).add(max(dot(p.xyz, sweep), 0));
        If(d.lessThan(r.negate()), () => { seen.assign(uint(0)); });
      });
      // Unknown kinds are skipped (no list has room for them).
      If(seen.equal(uint(1)).and(kind.lessThan(uint(nKinds))), () => {
        const v = center.sub(cam);
        const dist = (horizontal ? length(vec3(v.x, 0, v.z)) : length(v)).toVar();
        const first = uint(kl.x).toVar();
        Loop({ start: first, end: first.add(uint(kl.y)), type: 'uint', condition: '<' }, ({ i: l }) => {
          const a = lists.element(l.mul(2));
          const at = lists.element(l.mul(2).add(1));
          const t = smoothstep(a.z, a.w, dist);
          const drop = t.greaterThan(0).and(ex.y.lessThan(t));
          If(dist.greaterThanEqual(a.x).and(dist.lessThan(a.y)).and(drop.not()), () => {
            const slot = atomicAdd(counters.element(l), uint(1)).toVar();
            If(slot.lessThan(uint(at.y)), () => {
              const o = uint(at.x).add(slot).mul(4);
              out.element(o).assign(c0);
              out.element(o.add(1)).assign(c1);
              out.element(o.add(2)).assign(c2);
              out.element(o.add(3)).assign(c3);
            });
          });
        });
      });
    })().compute(0);

    const finish = Fn(() => {
      const d = draws.element(instanceIndex).toVar();
      const at = lists.element(d.x.mul(2).add(1));
      const n = min(atomicLoad(counters.element(d.x)), uint(at.y));
      const o = instanceIndex.mul(5);
      ind.element(o).assign(d.y);
      ind.element(o.add(1)).assign(n);
      // drawIndexedIndirect: count, instances, first index, base vertex, first instance; drawIndirect: count, instances, first vertex, first instance.
      ind.element(o.add(2)).assign(d.z);
      If(d.w.equal(uint(1)), () => {
        ind.element(o.add(3)).assign(uint(0));
        ind.element(o.add(4)).assign(uint(at.x));
      }).Else(() => {
        ind.element(o.add(3)).assign(uint(at.x));
        ind.element(o.add(4)).assign(uint(0));
      });
    })().compute(nDraws);
    return { reset, cull, finish };
  }

  private count = 0;

  set(data: Float32Array, count: number): void {
    const n = this.kinds.map(() => 0);
    for (let i = 0; i < count; i++) {
      const k = data[i * RECORD + KIND];
      if (k >= 0 && k < n.length) n[k]++;
    }
    const lay = listLayout(n, this.listsOfKind);
    this.allocate(count, lay.total);
    const lt = this.listTable.array as Float32Array;
    lay.base.forEach((b, l) => { lt[l * 8 + 4] = b; lt[l * 8 + 5] = lay.cap[l]; });
    this.listTable.needsUpdate = true;
    (this.input.array as Float32Array).set(data.subarray(0, count * RECORD));
    this.input.clearUpdateRanges();
    this.input.addUpdateRange(0, Math.max(1, count * RECORD));
    this.input.needsUpdate = true;
    this.count = count;
    this.checkedAt.set(NaN, NaN, NaN);
  }

  /**
   * Hides the parts of the level lists no instance can be in near `eye` (world space), shows the others: an
   * empty indirect draw still costs a draw call on the CPU, in the view and in every shadow map.
   */
  private skipEmpty(eye: Vector3): void {
    const c = this.checkedAt, horizontal = !!this.opts.horizontal;
    const moved = horizontal ? Math.hypot(eye.x - c.x, eye.z - c.z) : eye.distanceTo(c);
    if (moved < RECHECK) return; // NaN (not checked yet) is never below
    c.copy(eye);
    const used = listsInUse(this.input.array as Float32Array, this.count, this.spheres, this.ranges, this.listsOfKind, [eye.x, eye.y, eye.z], horizontal, RECHECK * 2);
    for (const d of this.draws) d.mesh.visible = used[d.list];
  }

  update(camera: Camera): void {
    // The frame's own view (the renderer updates matrices only when it renders, after this).
    camera.updateMatrixWorld();
    this.pv.multiplyMatrices(camera.projectionMatrix, camera.matrixWorldInverse);
    this.frustum.setFromProjectionMatrix(this.pv, (camera as any).coordinateSystem);
    this.frustum.planes.forEach((p, i) => this.planes[i].set(p.normal.x, p.normal.y, p.normal.z, p.constant));
    // World space, then relative to the origin (in doubles: a plane moves by its normal along the origin).
    const o = this.opts.origin;
    if (o) this.uOrigin.value.copy(o);
    if (o) for (const p of this.planes) p.w += p.x * o.x + p.y * o.y + p.z * o.z;
    camera.getWorldPosition(this.uCam.value);
    this.skipEmpty(this.eye.copy(this.uCam.value));
    if (o) this.uCam.value.sub(o);
    const sh = this.opts.shadow;
    if (sh) this.uSweep.value.copy(sh.dir).multiplyScalar(sh.reach);
    else this.uSweep.value.set(0, 0, 0);
    this.dispatch();
  }

  private dispatch(): void {
    if (!this.passes) this.passes = this.build();
    this.passes.cull.count = this.count;
    this.renderer.compute([this.passes.reset, this.passes.cull, this.passes.finish]);
  }

  async ready(): Promise<void> {
    if (!this.passes) this.passes = this.build();
    this.passes.cull.count = this.count;
    await this.renderer.computeAsync([this.passes.reset, this.passes.cull, this.passes.finish]);
  }

  async prepare(compile: (group: Group) => Promise<void>): Promise<void> {
    await this.ready();
    // Drawn indirectly with instanceCount 1 throughout, so every part already builds (shown meanwhile: one
    // hidden as empty must have its shaders when instances come near).
    for (const d of this.draws) d.mesh.visible = true;
    this.checkedAt.set(NaN, NaN, NaN);
    await compile(this.group);
  }

  async counts(): Promise<number[]> {
    const buf = new Uint32Array(await this.renderer.getArrayBufferAsync(this.indirect));
    return this.draws.map((_, i) => buf[i * 5 + 1]);
  }

  dispose(): void {
    for (const d of this.draws) d.geometry.dispose();
    this.group.clear();
  }
}

/** A kind's local bounding sphere: around every part of every level. */
export function kindSphere(k: DrawKind): Sphere {
  const s = new Sphere();
  let first = true;
  for (const l of k.lods) for (const p of l.parts) {
    if (!p.geometry.boundingSphere) p.geometry.computeBoundingSphere();
    const b = p.geometry.boundingSphere!;
    if (first) { s.copy(b); first = false; } else s.union(b);
  }
  return s;
}
