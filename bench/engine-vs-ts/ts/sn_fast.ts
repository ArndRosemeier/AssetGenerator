// Same algorithm as packages/volume surfaceNets, written allocation-light: growable typed arrays, no closures/tuple-destructuring in hot loops.
const PAD = 3;
const EA = new Int8Array([0,2,4,6,0,1,4,5,0,1,2,3]), EB = new Int8Array([1,3,5,7,2,3,6,7,4,5,6,7]);
let P = new Float32Array(1 << 16), Nn = new Float32Array(1 << 16), I = new Uint32Array(1 << 17);
export function surfaceNetsFast(n: number, d: Float32Array, ox: number, oy: number, oz: number, step: number) {
  const cells = n - 1, nn = n * n;
  const vert = new Int32Array(cells * cells * cells).fill(-1);
  const c = new Float64Array(8);
  let pv = 0;
  for (let k = 0; k < cells; k++) for (let j = 0; j < cells; j++) for (let i = 0; i < cells; i++) {
    const base = i + n * j + nn * k;
    let mask = 0;
    for (let q = 0; q < 8; q++) { const v = d[base + (q & 1) + n * ((q >> 1) & 1) + nn * ((q >> 2) & 1)]; c[q] = v; if (v < 0) mask |= 1 << q; }
    if (mask === 0 || mask === 255) continue;
    let sx = 0, sy = 0, sz = 0, count = 0;
    for (let e = 0; e < 12; e++) {
      const a = EA[e], b = EB[e], va = c[a], vb = c[b];
      if ((va < 0) === (vb < 0)) continue;
      const t = va / (va - vb);
      sx += (a & 1) + t * ((b & 1) - (a & 1)); sy += ((a >> 1) & 1) + t * (((b >> 1) & 1) - ((a >> 1) & 1)); sz += ((a >> 2) & 1) + t * (((b >> 2) & 1) - ((a >> 2) & 1)); count++;
    }
    if (pv * 3 + 3 > P.length) { const np = new Float32Array(P.length * 2); np.set(P); P = np; const nq = new Float32Array(Nn.length * 2); nq.set(Nn); Nn = nq; }
    vert[i + cells * (j + cells * k)] = pv;
    const fx = sx / count, fy = sy / count, fz = sz / count;
    P[pv * 3] = ox + (i - PAD + fx) * step; P[pv * 3 + 1] = oy + (j - PAD + fy) * step; P[pv * 3 + 2] = oz + (k - PAD + fz) * step;
    let gx = 0, gy = 0, gz = 0;
    for (let q = 0; q < 8; q++) {
      const a = i + (q & 1), b = j + ((q >> 1) & 1), e = k + ((q >> 2) & 1);
      const wq = ((q & 1) ? fx : 1 - fx) * (((q >> 1) & 1) ? fy : 1 - fy) * (((q >> 2) & 1) ? fz : 1 - fz);
      const o = a + n * b + nn * e;
      gx += wq * (d[o + (a < n - 1 ? 1 : 0)] - d[o - (a > 0 ? 1 : 0)]);
      gy += wq * (d[o + (b < n - 1 ? n : 0)] - d[o - (b > 0 ? n : 0)]);
      gz += wq * (d[o + (e < n - 1 ? nn : 0)] - d[o - (e > 0 ? nn : 0)]);
    }
    const len = Math.sqrt(gx * gx + gy * gy + gz * gz) || 1;
    Nn[pv * 3] = gx / len; Nn[pv * 3 + 1] = gy / len; Nn[pv * 3 + 2] = gz / len;
    pv++;
  }
  if (!pv) return null;
  const N = n - 2 * PAD - 1, cc = cells * cells;
  let ic = 0;
  const lo = PAD, hi = PAD + N - 1;
  for (let k = lo; k <= hi; k++) for (let j = lo; j <= hi; j++) for (let i = lo; i <= hi; i++) {
    const s = i + n * j + nn * k, s0 = d[s], vb = i + cells * j + cc * k;
    if (ic + 18 > I.length) { const ni = new Uint32Array(I.length * 2); ni.set(I); I = ni; }
    for (let ax = 0; ax < 3; ax++) {
      const s1 = d[s + (ax === 0 ? 1 : ax === 1 ? n : nn)];
      if ((s0 < 0) === (s1 < 0)) continue;
      let v0 = vert[vb], v1, v2, v3;
      if (ax === 0) { v1 = vert[vb - cells]; v2 = vert[vb - cells - cc]; v3 = vert[vb - cc]; }
      else if (ax === 1) { v1 = vert[vb - cc]; v2 = vert[vb - 1 - cc]; v3 = vert[vb - 1]; }
      else { v1 = vert[vb - 1]; v2 = vert[vb - 1 - cells]; v3 = vert[vb - cells]; }
      if (v0 < 0 || v1 < 0 || v2 < 0 || v3 < 0) continue;
      if (s0 < 0) { I[ic++] = v0; I[ic++] = v1; I[ic++] = v2; I[ic++] = v0; I[ic++] = v2; I[ic++] = v3; }
      else { I[ic++] = v0; I[ic++] = v2; I[ic++] = v1; I[ic++] = v0; I[ic++] = v3; I[ic++] = v2; }
    }
  }
  if (!ic) return null;
  return { positions: P.slice(0, pv * 3), normals: Nn.slice(0, pv * 3), indices: I.slice(0, ic) };
}
