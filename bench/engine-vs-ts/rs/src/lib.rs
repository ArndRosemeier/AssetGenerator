//! Faithful Rust port of @futuremagic/core Noise (fbm3) + Rng and @futuremagic/volume surfaceNets.
const F3: f64 = 1.0 / 3.0;
const G3: f64 = 1.0 / 6.0;
const GRAD3: [f32; 36] = [1.,1.,0.,-1.,1.,0.,1.,-1.,0.,-1.,-1.,0., 1.,0.,1.,-1.,0.,1.,1.,0.,-1.,-1.,0.,-1., 0.,1.,1.,0.,-1.,1.,0.,1.,-1.,0.,-1.,-1.];

struct Rng { a: u32, b: u32, c: u32, d: u32 }
impl Rng {
    fn new(seed: u32) -> Self { let mut r = Rng { a: 0x9e3779b9, b: 0x243f6a88, c: 0xb7e15162, d: seed }; for _ in 0..12 { r.next(); } r }
    fn next(&mut self) -> u32 {
        let t = self.a.wrapping_add(self.b).wrapping_add(self.d);
        self.d = self.d.wrapping_add(1);
        self.a = self.b ^ (self.b >> 9);
        self.b = self.c.wrapping_add(self.c << 3);
        self.c = (self.c << 21) | (self.c >> 11);
        self.c = self.c.wrapping_add(t);
        t
    }
    fn float(&mut self) -> f64 { self.next() as f64 / 4294967296.0 }
}

pub struct Noise { perm: [u8; 512], perm12: [u8; 512] }
impl Noise {
    pub fn new(seed: u32) -> Self {
        let mut rng = Rng::new(seed);
        let mut p = [0u8; 256];
        for i in 0..256 { p[i] = i as u8; }
        for i in (1..256).rev() { let j = (rng.float() * (i as f64 + 1.0)).floor() as usize; p.swap(i, j); }
        let mut perm = [0u8; 512]; let mut perm12 = [0u8; 512];
        for i in 0..512 { perm[i] = p[i & 255]; perm12[i] = perm[i] % 12; }
        Noise { perm, perm12 }
    }
    #[inline(always)]
    pub fn n3(&self, xin: f64, yin: f64, zin: f64) -> f64 {
        let perm = &self.perm; let p12 = &self.perm12;
        let s = (xin + yin + zin) * F3;
        let i = (xin + s).floor(); let j = (yin + s).floor(); let k = (zin + s).floor();
        let t = (i + j + k) * G3;
        let x0 = xin - (i - t); let y0 = yin - (j - t); let z0 = zin - (k - t);
        let (i1, j1, k1, i2, j2, k2) = if x0 >= y0 {
            if y0 >= z0 { (1,0,0,1,1,0) } else if x0 >= z0 { (1,0,0,1,0,1) } else { (0,0,1,1,0,1) }
        } else if y0 < z0 { (0,0,1,0,1,1) } else if x0 < z0 { (0,1,0,0,1,1) } else { (0,1,0,1,1,0) };
        let x1 = x0 - i1 as f64 + G3; let y1 = y0 - j1 as f64 + G3; let z1 = z0 - k1 as f64 + G3;
        let x2 = x0 - i2 as f64 + 2.0*G3; let y2 = y0 - j2 as f64 + 2.0*G3; let z2 = z0 - k2 as f64 + 2.0*G3;
        let x3 = x0 - 1.0 + 3.0*G3; let y3 = y0 - 1.0 + 3.0*G3; let z3 = z0 - 1.0 + 3.0*G3;
        let ii = (i as i64 & 255) as usize; let jj = (j as i64 & 255) as usize; let kk = (k as i64 & 255) as usize;
        let g = |idx: usize| p12[idx] as usize * 3;
        let corner = |t: f64, gi: usize, x: f64, y: f64, z: f64| -> f64 {
            if t > 0.0 { let t2 = t * t; t2 * t2 * (GRAD3[gi] as f64 * x + GRAD3[gi+1] as f64 * y + GRAD3[gi+2] as f64 * z) } else { 0.0 }
        };
        let n0 = corner(0.6 - x0*x0 - y0*y0 - z0*z0, g(ii + perm[jj + perm[kk] as usize] as usize), x0, y0, z0);
        let n1 = corner(0.6 - x1*x1 - y1*y1 - z1*z1, g(ii + i1 + perm[jj + j1 + perm[kk + k1] as usize] as usize), x1, y1, z1);
        let n2 = corner(0.6 - x2*x2 - y2*y2 - z2*z2, g(ii + i2 + perm[jj + j2 + perm[kk + k2] as usize] as usize), x2, y2, z2);
        let n3 = corner(0.6 - x3*x3 - y3*y3 - z3*z3, g(ii + 1 + perm[jj + 1 + perm[kk + 1] as usize] as usize), x3, y3, z3);
        32.0 * (n0 + n1 + n2 + n3)
    }
    pub fn fbm3(&self, x: f64, y: f64, z: f64, octaves: u32) -> f64 {
        let (mut sum, mut amp, mut norm, mut f) = (0.0, 1.0, 0.0, 1.0);
        for o in 0..octaves { let o = o as f64;
            sum += amp * self.n3(x * f + o * 17.31, y * f - o * 9.17, z * f + o * 5.71);
            norm += amp; amp *= 0.5; f *= 2.0; }
        sum / norm
    }
}

pub const PAD: i32 = 3; const OVERLAP: i32 = 2;
pub const N: i32 = 32; pub const NS: usize = (N + 2 * PAD + 1) as usize;
const EDGES: [(usize, usize); 12] = [(0,1),(2,3),(4,5),(6,7),(0,2),(1,3),(4,6),(5,7),(0,4),(1,5),(2,6),(3,7)];

pub struct MeshData { pub positions: Vec<f32>, pub normals: Vec<f32>, pub indices: Vec<u32> }

pub fn surface_nets(n: usize, d: &[f32], ox: f64, oy: f64, oz: f64, step: f64, overlap: u32) -> Option<MeshData> {
    let cells = n - 1;
    let at = |i: usize, j: usize, k: usize| d[i + n * (j + n * k)] as f64;
    let mut vert = vec![-1i32; cells * cells * cells];
    let mut pos: Vec<f32> = Vec::new(); let mut nor: Vec<f32> = Vec::new();
    let mut c = [0f64; 8];
    for k in 0..cells { for j in 0..cells { for i in 0..cells {
        let mut mask = 0u32;
        for q in 0..8 { let v = at(i + (q & 1), j + ((q >> 1) & 1), k + ((q >> 2) & 1)); c[q] = v; if v < 0.0 { mask |= 1 << q; } }
        if mask == 0 || mask == 255 { continue; }
        let (mut sx, mut sy, mut sz, mut count) = (0.0, 0.0, 0.0, 0.0);
        for &(a, b) in EDGES.iter() {
            let (va, vb) = (c[a], c[b]);
            if (va < 0.0) == (vb < 0.0) { continue; }
            let t = va / (va - vb);
            let (ax, ay, az) = ((a & 1) as f64, ((a >> 1) & 1) as f64, ((a >> 2) & 1) as f64);
            let (bx, by, bz) = ((b & 1) as f64, ((b >> 1) & 1) as f64, ((b >> 2) & 1) as f64);
            sx += ax + t * (bx - ax); sy += ay + t * (by - ay); sz += az + t * (bz - az); count += 1.0;
        }
        vert[i + cells * (j + cells * k)] = (pos.len() / 3) as i32;
        let (fx, fy, fz) = (sx / count, sy / count, sz / count);
        pos.push((ox + (i as f64 - PAD as f64 + fx) * step) as f32);
        pos.push((oy + (j as f64 - PAD as f64 + fy) * step) as f32);
        pos.push((oz + (k as f64 - PAD as f64 + fz) * step) as f32);
        let (mut gx, mut gy, mut gz) = (0.0, 0.0, 0.0);
        for q in 0..8 {
            let (a, b, e) = (i + (q & 1), j + ((q >> 1) & 1), k + ((q >> 2) & 1));
            let wq = (if q & 1 != 0 { fx } else { 1.0 - fx }) * (if (q >> 1) & 1 != 0 { fy } else { 1.0 - fy }) * (if (q >> 2) & 1 != 0 { fz } else { 1.0 - fz });
            gx += wq * (at((a + 1).min(n - 1), b, e) - at(a.saturating_sub(1), b, e));
            gy += wq * (at(a, (b + 1).min(n - 1), e) - at(a, b.saturating_sub(1), e));
            gz += wq * (at(a, b, (e + 1).min(n - 1)) - at(a, b, e.saturating_sub(1)));
        }
        let mut len = (gx * gx + gy * gy + gz * gz).sqrt(); if len == 0.0 { len = 1.0; }
        nor.push((gx / len) as f32); nor.push((gy / len) as f32); nor.push((gz / len) as f32);
    }}}
    if pos.is_empty() { return None; }
    let mut idx: Vec<u32> = Vec::new();
    let nn = n as i32 - 2 * PAD - 1;
    let lo = |axis: u32| PAD - OVERLAP * ((overlap >> (2 * axis)) & 1) as i32;
    let hi = |axis: u32| PAD + nn - 1 + OVERLAP * ((overlap >> (2 * axis + 1)) & 1) as i32;
    let v = |i: i32, j: i32, k: i32| vert[(i + cells as i32 * (j + cells as i32 * k)) as usize];
    let mut quad = |a: f64, b: f64, v0: i32, v1: i32, v2: i32, v3: i32| {
        if (a < 0.0) == (b < 0.0) { return; }
        if v0 < 0 || v1 < 0 || v2 < 0 || v3 < 0 { return; }
        let (v0, v1, v2, v3) = (v0 as u32, v1 as u32, v2 as u32, v3 as u32);
        if a < 0.0 { idx.extend_from_slice(&[v0, v1, v2, v0, v2, v3]); } else { idx.extend_from_slice(&[v0, v2, v1, v0, v3, v2]); }
    };
    for k in lo(2)..=hi(2) { for j in lo(1)..=hi(1) { for i in lo(0)..=hi(0) {
        let (iu, ju, ku) = (i as usize, j as usize, k as usize);
        let s0 = at(iu, ju, ku);
        quad(s0, at(iu + 1, ju, ku), v(i, j, k), v(i, j - 1, k), v(i, j - 1, k - 1), v(i, j, k - 1));
        quad(s0, at(iu, ju + 1, ku), v(i, j, k), v(i, j, k - 1), v(i - 1, j, k - 1), v(i - 1, j, k));
        quad(s0, at(iu, ju, ku + 1), v(i, j, k), v(i - 1, j, k), v(i - 1, j - 1, k), v(i, j - 1, k));
    }}}
    if idx.is_empty() { return None; }
    Some(MeshData { positions: pos, normals: nor, indices: idx })
}

pub fn density(noise: &Noise, cx: i32, cy: i32, cz: i32) -> Vec<f32> {
    let mut d = vec![0f32; NS * NS * NS];
    let (ox, oy, oz) = ((cx * N) as f64, (cy * N) as f64, (cz * N) as f64);
    let mut p = 0;
    for k in 0..NS { for j in 0..NS { for i in 0..NS {
        let x = ox + (i as f64 - PAD as f64); let y = oy + (j as f64 - PAD as f64); let z = oz + (k as f64 - PAD as f64);
        d[p] = (noise.fbm3(x * 0.02, y * 0.02, z * 0.02, 5) * 20.0 + (y - 64.0) * 0.5) as f32; p += 1;
    }}}
    d
}

/// Returns (tris, verts, checksum) and splits time via the callback-free API below.
pub fn chunk(noise: &Noise, cx: i32, cy: i32, cz: i32) -> (Vec<f32>, Option<MeshData>) {
    let d = density(noise, cx, cy, cz);
    let m = surface_nets(NS, &d, (cx * N) as f64, (cy * N) as f64, (cz * N) as f64, 1.0, 0);
    (d, m)
}

// ---- wasm entry: run all 64 chunks single-threaded, return noise ms*1000 packed... keep it simple
#[no_mangle]
pub extern "C" fn wasm_noise_all() -> f64 { let n = Noise::new(1234); let mut s = 0.0;
    for z in 0..4 { for y in 0..4 { for x in 0..4 { let d = density(&n, x, y, z); s += d[0] as f64; } } } s }
#[no_mangle]
pub extern "C" fn wasm_chunks_all() -> u32 { let n = Noise::new(1234); let mut tris = 0;
    for z in 0..4 { for y in 0..4 { for x in 0..4 { let (_, m) = chunk(&n, x, y, z); if let Some(m) = m { tris += m.indices.len() as u32 / 3; } } } } tris }
