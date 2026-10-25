use bench::*;
use rayon::prelude::*;
use std::time::Instant;
fn main() {
    let noise = Noise::new(1234);
    let chunks: Vec<(i32,i32,i32)> = (0..4).flat_map(|z| (0..4).flat_map(move |y| (0..4).map(move |x| (x,y,z)))).collect();
    // checksum, same as TS
    let (mut tris, mut verts, mut sum) = (0usize, 0usize, 0f64);
    for &(x,y,z) in &chunks { let (d, m) = chunk(&noise, x,y,z); let mut q = 0; while q < d.len() { sum += d[q] as f64; q += 97; }
        if let Some(m) = m { tris += m.indices.len()/3; verts += m.positions.len()/3; } }
    println!("check tris={tris} verts={verts} sum={sum:.3}");
    let mut runs = vec![];
    for _ in 0..5 {
        let (mut nz, mut ms) = (0.0, 0.0);
        for &(x,y,z) in &chunks {
            let t0 = Instant::now(); let d = density(&noise, x,y,z); let t1 = Instant::now();
            let m = surface_nets(NS, &d, (x*N) as f64, (y*N) as f64, (z*N) as f64, 1.0, 0); let t2 = Instant::now();
            std::hint::black_box(m);
            nz += (t1-t0).as_secs_f64()*1e3; ms += (t2-t1).as_secs_f64()*1e3;
        }
        runs.push((nz, ms));
    }
    runs.sort_by(|a,b| (a.0+a.1).partial_cmp(&(b.0+b.1)).unwrap());
    println!("rust single: noise {:.1} ms, mesh {:.1} ms (64 chunks, median of 5)", runs[2].0, runs[2].1);
    for t in [4usize] {
        let pool = rayon::ThreadPoolBuilder::new().num_threads(t).build().unwrap();
        let mut ts = vec![];
        for _ in 0..8 { let t0 = Instant::now();
            pool.install(|| { let r: usize = chunks.par_iter().map(|&(x,y,z)| chunk(&noise,x,y,z).1.map(|m| m.indices.len()).unwrap_or(0)).sum(); std::hint::black_box(r); });
            ts.push(t0.elapsed().as_secs_f64()*1e3); }
        let mut tail = ts[3..].to_vec(); tail.sort_by(|a,b| a.partial_cmp(b).unwrap());
        println!("rust rayon x{t}: {:.1} ms wall", tail[2]);
    }
}
