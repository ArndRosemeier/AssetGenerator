/**
 * Prototype: packages/volume surfaceNets as WebGPU compute shaders, for a batch of same-size chunks at once.
 *
 * Same output as the TS mesher: vertices in cell scan order (x fastest), indices chunk-local and in the
 * same order, so a chunk's mesh is identical up to f32 rounding of positions and normals.
 *
 * Passes (one command encoder, no CPU round trip in between):
 *   1. classify    one thread per cell: 1 if the cell has a sign change (it gets a vertex)
 *   2. scan        exclusive prefix sum of those flags = each vertex's index (keeps the scan order)
 *   3. vertices    one thread per active cell: position + gradient normal, written at its index
 *   4. countQuads  one thread per owned sample: how many of its 3 edges make a quad (0..3)
 *   5. scan        prefix sum = where each sample's quads go in the index buffer
 *   6. chunkInfo   per chunk: first vertex and first quad (to make indices chunk-local), and the totals
 *   7. writeQuads  one thread per owned sample: write its 6 indices per quad
 */

export const PAD = 3;
export const OVERLAP = 2;

export interface ChunkParams { ox: number; oy: number; oz: number; step: number; overlap?: number }
export interface MeshData { positions: Float32Array; normals: Float32Array; indices: Uint32Array }

const WG = 256;
const BLOCK = WG * 4; // elements per scan workgroup (4 per thread)

const COMMON = /* wgsl */ `
struct P { n: u32, cells: u32, cells3: u32, chunks: u32, dom: u32, dom3: u32, nsamp3: u32, N: u32 }
struct Chunk { ox: f32, oy: f32, oz: f32, step: f32, overlap: u32, a: u32, b: u32, c: u32 }
@group(0) @binding(0) var<uniform> p: P;
@group(0) @binding(1) var<storage, read> d: array<f32>;
@group(0) @binding(2) var<storage, read> chunk: array<Chunk>;
const PAD = ${PAD}u;
const OVERLAP = ${OVERLAP}u;
fn at(base: u32, i: u32, j: u32, k: u32) -> f32 { return d[base + i + p.n * (j + p.n * k)]; }
fn cellId(i: u32, j: u32, k: u32) -> u32 { return i + p.cells * (j + p.cells * k); }
fn linear(g: vec3<u32>, nw: vec3<u32>) -> u32 { return g.x + g.y * nw.x * ${WG}u; }
`;

const CLASSIFY = COMMON + /* wgsl */ `
@group(0) @binding(3) var<storage, read_write> vflag: array<u32>;
@compute @workgroup_size(${WG}) fn main(@builtin(global_invocation_id) g: vec3<u32>, @builtin(num_workgroups) nw: vec3<u32>) {
  let id = linear(g, nw);
  if (id >= p.cells3 * p.chunks) { return; }
  let c = id / p.cells3; let r = id % p.cells3;
  let i = r % p.cells; let j = (r / p.cells) % p.cells; let k = r / (p.cells * p.cells);
  let base = c * p.nsamp3;
  var mask = 0u;
  for (var q = 0u; q < 8u; q++) {
    if (at(base, i + (q & 1u), j + ((q >> 1u) & 1u), k + ((q >> 2u) & 1u)) < 0.0) { mask |= 1u << q; }
  }
  vflag[id] = select(0u, 1u, mask != 0u && mask != 255u);
}`;

const VERTICES = COMMON + /* wgsl */ `
@group(0) @binding(3) var<storage, read> vflag: array<u32>;
@group(0) @binding(4) var<storage, read> vscan: array<u32>;
@group(0) @binding(5) var<storage, read_write> pos: array<f32>;
@group(0) @binding(6) var<storage, read_write> nor: array<f32>;
const EA = array<u32, 12>(0u, 2u, 4u, 6u, 0u, 1u, 4u, 5u, 0u, 1u, 2u, 3u);
const EB = array<u32, 12>(1u, 3u, 5u, 7u, 2u, 3u, 6u, 7u, 4u, 5u, 6u, 7u);
@compute @workgroup_size(${WG}) fn main(@builtin(global_invocation_id) g: vec3<u32>, @builtin(num_workgroups) nw: vec3<u32>) {
  let id = linear(g, nw);
  if (id >= p.cells3 * p.chunks) { return; }
  if (vflag[id] == 0u) { return; }
  let c = id / p.cells3; let r = id % p.cells3;
  let i = r % p.cells; let j = (r / p.cells) % p.cells; let k = r / (p.cells * p.cells);
  let base = c * p.nsamp3;
  var cv: array<f32, 8>;
  for (var q = 0u; q < 8u; q++) { cv[q] = at(base, i + (q & 1u), j + ((q >> 1u) & 1u), k + ((q >> 2u) & 1u)); }
  var s = vec3<f32>(0.0); var count = 0.0;
  for (var e = 0u; e < 12u; e++) {
    let a = EA[e]; let b = EB[e]; let va = cv[a]; let vb = cv[b];
    if ((va < 0.0) == (vb < 0.0)) { continue; }
    let t = va / (va - vb);
    let pa = vec3<f32>(f32(a & 1u), f32((a >> 1u) & 1u), f32((a >> 2u) & 1u));
    let pb = vec3<f32>(f32(b & 1u), f32((b >> 1u) & 1u), f32((b >> 2u) & 1u));
    s += pa + t * (pb - pa);
    count += 1.0;
  }
  let f = s / count;
  let ch = chunk[c];
  let v = vscan[id];
  if (v * 3u + 2u >= arrayLength(&pos)) { return; }
  let ijk = vec3<f32>(f32(i), f32(j), f32(k)) - f32(PAD) + f;
  pos[v * 3u] = ch.ox + ijk.x * ch.step;
  pos[v * 3u + 1u] = ch.oy + ijk.y * ch.step;
  pos[v * 3u + 2u] = ch.oz + ijk.z * ch.step;
  // Field gradient (central differences at the corners), trilinear at the vertex.
  var gr = vec3<f32>(0.0);
  let m = p.n - 1u;
  for (var q = 0u; q < 8u; q++) {
    let a = i + (q & 1u); let b = j + ((q >> 1u) & 1u); let e = k + ((q >> 2u) & 1u);
    let w = select(1.0 - f.x, f.x, (q & 1u) != 0u) * select(1.0 - f.y, f.y, ((q >> 1u) & 1u) != 0u) * select(1.0 - f.z, f.z, ((q >> 2u) & 1u) != 0u);
    gr.x += w * (at(base, min(a + 1u, m), b, e) - at(base, select(a - 1u, 0u, a == 0u), b, e));
    gr.y += w * (at(base, a, min(b + 1u, m), e) - at(base, a, select(b - 1u, 0u, b == 0u), e));
    gr.z += w * (at(base, a, b, min(e + 1u, m)) - at(base, a, b, select(e - 1u, 0u, e == 0u)));
  }
  var len = length(gr);
  if (len == 0.0) { len = 1.0; }
  nor[v * 3u] = gr.x / len; nor[v * 3u + 1u] = gr.y / len; nor[v * 3u + 2u] = gr.z / len;
}`;

// Shared by countQuads and writeQuads: the quads of one owned sample.
const QUADS = COMMON + /* wgsl */ `
@group(0) @binding(3) var<storage, read> vflag: array<u32>;
struct Q { ok: bool, rock: bool, c0: u32, c1: u32, c2: u32, c3: u32 }
fn quad(base: u32, cb: u32, i: u32, j: u32, k: u32, axis: u32) -> Q {
  var q: Q;
  let s0 = at(base, i, j, k);
  var s1: f32;
  if (axis == 0u) { s1 = at(base, i + 1u, j, k); q.c0 = cellId(i, j, k); q.c1 = cellId(i, j - 1u, k); q.c2 = cellId(i, j - 1u, k - 1u); q.c3 = cellId(i, j, k - 1u); }
  else if (axis == 1u) { s1 = at(base, i, j + 1u, k); q.c0 = cellId(i, j, k); q.c1 = cellId(i, j, k - 1u); q.c2 = cellId(i - 1u, j, k - 1u); q.c3 = cellId(i - 1u, j, k); }
  else { s1 = at(base, i, j, k + 1u); q.c0 = cellId(i, j, k); q.c1 = cellId(i - 1u, j, k); q.c2 = cellId(i - 1u, j - 1u, k); q.c3 = cellId(i, j - 1u, k); }
  q.rock = s0 < 0.0;
  q.ok = (s0 < 0.0) != (s1 < 0.0) && vflag[cb + q.c0] != 0u && vflag[cb + q.c1] != 0u && vflag[cb + q.c2] != 0u && vflag[cb + q.c3] != 0u;
  return q;
}
// Sample (i, j, k) of thread r in chunk c, and whether the chunk owns it (with its overlap sides).
fn owned(c: u32, r: u32, ijk: ptr<function, vec3<u32>>) -> bool {
  let lo = PAD - OVERLAP;
  let v = vec3<u32>(r % p.dom + lo, (r / p.dom) % p.dom + lo, r / (p.dom * p.dom) + lo);
  *ijk = v;
  let ov = chunk[c].overlap;
  for (var a = 0u; a < 3u; a++) {
    let l = PAD - OVERLAP * ((ov >> (2u * a)) & 1u);
    let h = PAD + p.N - 1u + OVERLAP * ((ov >> (2u * a + 1u)) & 1u);
    if (v[a] < l || v[a] > h) { return false; }
  }
  return true;
}
`;

const COUNT_QUADS = QUADS + /* wgsl */ `
@group(0) @binding(4) var<storage, read_write> qcount: array<u32>;
@compute @workgroup_size(${WG}) fn main(@builtin(global_invocation_id) g: vec3<u32>, @builtin(num_workgroups) nw: vec3<u32>) {
  let id = linear(g, nw);
  if (id >= p.dom3 * p.chunks) { return; }
  let c = id / p.dom3;
  var ijk: vec3<u32>;
  var n = 0u;
  if (owned(c, id % p.dom3, &ijk)) {
    for (var a = 0u; a < 3u; a++) { if (quad(c * p.nsamp3, c * p.cells3, ijk.x, ijk.y, ijk.z, a).ok) { n++; } }
  }
  qcount[id] = n;
}`;

const WRITE_QUADS = QUADS + /* wgsl */ `
@group(0) @binding(4) var<storage, read> qscan: array<u32>;
@group(0) @binding(5) var<storage, read> vscan: array<u32>;
@group(0) @binding(6) var<storage, read> info: array<u32>;
@group(0) @binding(7) var<storage, read_write> idx: array<u32>;
@compute @workgroup_size(${WG}) fn main(@builtin(global_invocation_id) g: vec3<u32>, @builtin(num_workgroups) nw: vec3<u32>) {
  let id = linear(g, nw);
  if (id >= p.dom3 * p.chunks) { return; }
  let c = id / p.dom3;
  var ijk: vec3<u32>;
  if (!owned(c, id % p.dom3, &ijk)) { return; }
  let cb = c * p.cells3; let vb = info[c];
  var o = qscan[id] * 6u;
  for (var a = 0u; a < 3u; a++) {
    let q = quad(c * p.nsamp3, cb, ijk.x, ijk.y, ijk.z, a);
    if (!q.ok) { continue; }
    if (o + 5u >= arrayLength(&idx)) { return; }
    let v0 = vscan[cb + q.c0] - vb; let v1 = vscan[cb + q.c1] - vb; let v2 = vscan[cb + q.c2] - vb; let v3 = vscan[cb + q.c3] - vb;
    // Rock at the sample: the air is towards +axis, keep the order; otherwise flip.
    if (q.rock) { idx[o] = v0; idx[o + 1u] = v1; idx[o + 2u] = v2; idx[o + 3u] = v0; idx[o + 4u] = v2; idx[o + 5u] = v3; }
    else { idx[o] = v0; idx[o + 1u] = v2; idx[o + 2u] = v1; idx[o + 3u] = v0; idx[o + 4u] = v3; idx[o + 5u] = v2; }
    o += 6u;
  }
}`;

// info layout: [0..C] first vertex of each chunk (C = total), [C+1..2C+1] first quad of each chunk (2C+1 = total).
const CHUNK_INFO = /* wgsl */ `
struct P { n: u32, cells: u32, cells3: u32, chunks: u32, dom: u32, dom3: u32, nsamp3: u32, N: u32 }
@group(0) @binding(0) var<uniform> p: P;
@group(0) @binding(1) var<storage, read> vflag: array<u32>;
@group(0) @binding(2) var<storage, read> vscan: array<u32>;
@group(0) @binding(3) var<storage, read> qcount: array<u32>;
@group(0) @binding(4) var<storage, read> qscan: array<u32>;
@group(0) @binding(5) var<storage, read_write> info: array<u32>;
@compute @workgroup_size(64) fn main(@builtin(global_invocation_id) g: vec3<u32>) {
  let c = g.x;
  if (c > p.chunks) { return; }
  if (c < p.chunks) { info[c] = vscan[c * p.cells3]; info[p.chunks + 1u + c] = qscan[c * p.dom3]; return; }
  let lv = p.cells3 * p.chunks - 1u; let lq = p.dom3 * p.chunks - 1u;
  info[c] = vscan[lv] + vflag[lv];
  info[2u * p.chunks + 1u] = qscan[lq] + qcount[lq];
}`;

const SCAN_BLOCK = /* wgsl */ `
@group(0) @binding(0) var<uniform> len: vec4<u32>;
@group(0) @binding(1) var<storage, read> src: array<u32>;
@group(0) @binding(2) var<storage, read_write> dst: array<u32>;
@group(0) @binding(3) var<storage, read_write> sums: array<u32>;
var<workgroup> sh: array<u32, ${WG}>;
@compute @workgroup_size(${WG}) fn main(@builtin(local_invocation_id) l: vec3<u32>, @builtin(workgroup_id) w: vec3<u32>, @builtin(num_workgroups) nw: vec3<u32>) {
  let blk = w.x + w.y * nw.x;
  let base = blk * ${BLOCK}u + l.x * 4u;
  var v: array<u32, 4>; var s = 0u;
  for (var e = 0u; e < 4u; e++) { v[e] = s; if (base + e < len.x) { s += src[base + e]; } }
  sh[l.x] = s;
  workgroupBarrier();
  for (var off = 1u; off < ${WG}u; off *= 2u) {
    var t = 0u;
    if (l.x >= off) { t = sh[l.x - off]; }
    workgroupBarrier();
    sh[l.x] += t;
    workgroupBarrier();
  }
  let ex = sh[l.x] - s;
  for (var e = 0u; e < 4u; e++) { if (base + e < len.x) { dst[base + e] = ex + v[e]; } }
  if (l.x == ${WG - 1}u) { sums[blk] = sh[l.x]; }
}`;

const SCAN_ADD = /* wgsl */ `
@group(0) @binding(0) var<uniform> len: vec4<u32>;
@group(0) @binding(1) var<storage, read_write> dst: array<u32>;
@group(0) @binding(2) var<storage, read> sums: array<u32>;
@compute @workgroup_size(${WG}) fn main(@builtin(local_invocation_id) l: vec3<u32>, @builtin(workgroup_id) w: vec3<u32>, @builtin(num_workgroups) nw: vec3<u32>) {
  let blk = w.x + w.y * nw.x;
  let add = sums[blk];
  let base = blk * ${BLOCK}u + l.x * 4u;
  for (var e = 0u; e < 4u; e++) { if (base + e < len.x) { dst[base + e] += add; } }
}`;

type Pass = { pipeline: GPUComputePipeline; bind: GPUBindGroup; wg: [number, number] };

/** Workgroup counts for `n` workgroups, split over y past the 65535 limit. */
function grid(n: number): [number, number] {
  if (n <= 65535) return [Math.max(n, 1), 1];
  const y = Math.ceil(n / 65535);
  return [Math.ceil(n / y), y];
}

export class GpuSurfaceNets {
  readonly n: number; readonly cells: number; readonly cells3: number; readonly dom: number; readonly dom3: number;
  readonly chunks: number;
  readonly density: GPUBuffer; readonly positions: GPUBuffer; readonly normals: GPUBuffer; indices!: GPUBuffer;
  readonly info: GPUBuffer;
  private chunkBuf: GPUBuffer; private uniform: GPUBuffer;
  private vflag: GPUBuffer; private vscan: GPUBuffer; private qcount: GPUBuffer; private qscan: GPUBuffer;
  private passes: Pass[] = [];
  private quadCap: number;
  private mods = new Map<string, GPUComputePipeline>();

  /** `n` samples per axis (N + 2·PAD + 1), `chunks` chunks per batch. */
  constructor(readonly device: GPUDevice, n: number, chunks: number, quadCapacity = 1 << 18) {
    this.n = n; this.cells = n - 1; this.cells3 = this.cells ** 3; this.chunks = chunks;
    const N = n - 2 * PAD - 1;
    this.dom = N + 2 * OVERLAP; this.dom3 = this.dom ** 3;
    const S = GPUBufferUsage.STORAGE, D = GPUBufferUsage.COPY_DST, C = GPUBufferUsage.COPY_SRC;
    const buf = (size: number, usage: number) => device.createBuffer({ size: Math.max(16, Math.ceil(size / 4) * 4), usage });
    this.uniform = buf(32, GPUBufferUsage.UNIFORM | D);
    device.queue.writeBuffer(this.uniform, 0, new Uint32Array([n, this.cells, this.cells3, chunks, this.dom, this.dom3, n ** 3, N]));
    this.density = buf(chunks * n ** 3 * 4, S | D);
    this.chunkBuf = buf(chunks * 32, S | D);
    const L = chunks * this.cells3, Q = chunks * this.dom3;
    this.vflag = buf(L * 4, S); this.vscan = buf(L * 4, S);
    this.qcount = buf(Q * 4, S); this.qscan = buf(Q * 4, S);
    // Every cell could hold a vertex, so positions and normals take the worst case; indices grow on demand.
    this.positions = buf(L * 12, S | C); this.normals = buf(L * 12, S | C);
    this.info = buf((2 * chunks + 2) * 4, S | C);
    this.quadCap = quadCapacity;
    this.build();
  }

  private pipe(code: string): GPUComputePipeline {
    let p = this.mods.get(code);
    if (!p) {
      p = this.device.createComputePipeline({ layout: 'auto', compute: { module: this.device.createShaderModule({ code }), entryPoint: 'main' } });
      this.mods.set(code, p);
    }
    return p;
  }

  /** `buffers[i]` goes to binding i; null skips a binding the shader does not use ('auto' layouts drop those). */
  private pass(code: string, buffers: (GPUBuffer | null)[], workgroups: number): Pass {
    const pipeline = this.pipe(code);
    const entries = buffers.flatMap((buffer, binding) => buffer ? [{ binding, resource: { buffer } }] : []);
    const bind = this.device.createBindGroup({ layout: pipeline.getBindGroupLayout(0), entries });
    return { pipeline, bind, wg: grid(workgroups) };
  }

  /** Prefix-scan passes: dst = exclusive scan of src (length len). */
  private scan(src: GPUBuffer, dst: GPUBuffer, len: number): Pass[] {
    const S = GPUBufferUsage.STORAGE;
    const blocks = Math.ceil(len / BLOCK);
    const u = this.device.createBuffer({ size: 16, usage: GPUBufferUsage.UNIFORM | GPUBufferUsage.COPY_DST });
    this.device.queue.writeBuffer(u, 0, new Uint32Array([len, 0, 0, 0]));
    const sums = this.device.createBuffer({ size: Math.max(16, blocks * 4), usage: S });
    const out = [this.pass(SCAN_BLOCK, [u, src, dst, sums], blocks)];
    if (blocks > 1) {
      const scanned = this.device.createBuffer({ size: Math.max(16, blocks * 4), usage: S });
      out.push(...this.scan(sums, scanned, blocks));
      out.push(this.pass(SCAN_ADD, [u, dst, scanned], blocks));
    }
    return out;
  }

  private build(): void {
    const { uniform: u, density: d, chunkBuf: ch, chunks } = this;
    const L = chunks * this.cells3, Q = chunks * this.dom3;
    this.indices?.destroy();
    this.indices = this.device.createBuffer({ size: this.quadCap * 24, usage: GPUBufferUsage.STORAGE | GPUBufferUsage.COPY_SRC });
    this.passes = [
      this.pass(CLASSIFY, [u, d, null, this.vflag], Math.ceil(L / WG)),
      ...this.scan(this.vflag, this.vscan, L),
      this.pass(VERTICES, [u, d, ch, this.vflag, this.vscan, this.positions, this.normals], Math.ceil(L / WG)),
      this.pass(COUNT_QUADS, [u, d, ch, this.vflag, this.qcount], Math.ceil(Q / WG)),
      ...this.scan(this.qcount, this.qscan, Q),
      this.pass(CHUNK_INFO, [u, this.vflag, this.vscan, this.qcount, this.qscan, this.info], Math.ceil((chunks + 1) / 64)),
      this.pass(WRITE_QUADS, [u, d, ch, this.vflag, this.qscan, this.vscan, this.info, this.indices], Math.ceil(Q / WG)),
    ];
  }

  get passCount(): number { return this.passes.length; }

  /** Upload all chunks' densities (chunk c at c·n³) and their origins/steps/overlap masks. */
  upload(densities: Float32Array<ArrayBuffer>, params: ChunkParams[]): void {
    this.device.queue.writeBuffer(this.density, 0, densities);
    const a = new ArrayBuffer(this.chunks * 32), f = new Float32Array(a), u = new Uint32Array(a);
    params.forEach((c, q) => { f.set([c.ox, c.oy, c.oz, c.step], q * 8); u[q * 8 + 4] = c.overlap ?? 0; });
    this.device.queue.writeBuffer(this.chunkBuf, 0, a);
  }

  /** Record the meshing passes. The mesh stays on the GPU (positions, normals, indices, info). */
  encode(enc: GPUCommandEncoder, timestamps?: GPUComputePassTimestampWrites): void {
    const pass = enc.beginComputePass(timestamps ? { timestampWrites: timestamps } : undefined);
    for (const p of this.passes) { pass.setPipeline(p.pipeline); pass.setBindGroup(0, p.bind); pass.dispatchWorkgroups(p.wg[0], p.wg[1]); }
    pass.end();
  }

  /** Mesh the uploaded chunks and read them back, one MeshData (or null) per chunk like surfaceNets(). */
  async run(): Promise<(MeshData | null)[]> {
    const dev = this.device;
    let enc = dev.createCommandEncoder();
    this.encode(enc);
    const infoRead = dev.createBuffer({ size: this.info.size, usage: GPUBufferUsage.MAP_READ | GPUBufferUsage.COPY_DST });
    enc.copyBufferToBuffer(this.info, 0, infoRead, 0, this.info.size);
    dev.queue.submit([enc.finish()]);
    await infoRead.mapAsync(GPUMapMode.READ);
    const info = new Uint32Array(infoRead.getMappedRange().slice(0));
    infoRead.destroy();
    const C = this.chunks, nv = info[C], nq = info[2 * C + 1];
    if (nq > this.quadCap) { // Index buffer too small: grow and mesh again.
      this.quadCap = Math.ceil(nq * 1.5);
      this.build();
      return this.run();
    }
    const read = async (src: GPUBuffer, bytes: number) => {
      const b = dev.createBuffer({ size: Math.max(16, bytes), usage: GPUBufferUsage.MAP_READ | GPUBufferUsage.COPY_DST });
      return { b, src, bytes };
    };
    const parts = await Promise.all([read(this.positions, nv * 12), read(this.normals, nv * 12), read(this.indices, nq * 24)]);
    enc = dev.createCommandEncoder();
    for (const r of parts) if (r.bytes) enc.copyBufferToBuffer(r.src, 0, r.b, 0, r.bytes);
    dev.queue.submit([enc.finish()]);
    await Promise.all(parts.map((r) => r.b.mapAsync(GPUMapMode.READ)));
    const [P, Nn] = parts.slice(0, 2).map((r) => new Float32Array(r.b.getMappedRange().slice(0, r.bytes)));
    const I = new Uint32Array(parts[2].b.getMappedRange().slice(0, parts[2].bytes));
    parts.forEach((r) => r.b.destroy());
    const out: (MeshData | null)[] = [];
    for (let c = 0; c < C; c++) {
      const v0 = info[c], v1 = info[c + 1], q0 = info[C + 1 + c], q1 = info[C + 2 + c];
      // Like surfaceNets(): null when the chunk has no vertices or no faces.
      if (v1 === v0 || q1 === q0) { out.push(null); continue; }
      out.push({ positions: P.subarray(v0 * 3, v1 * 3), normals: Nn.subarray(v0 * 3, v1 * 3), indices: I.subarray(q0 * 6, q1 * 6) });
    }
    return out;
  }
}
