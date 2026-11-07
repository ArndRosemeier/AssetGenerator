//! Draw-call benchmark, Engine side. Same scenes as ../web/index.html.
//! DRAWBENCH_SCENE = unique | moving | instanced. Prints one JSON line and exits.
use engine::prelude::*;

const SIDE: usize = 100; // 100 x 100 = 10,000 boxes
const INST_SIDE: usize = 448; // 448 x 448 = 200,704 instances
fn env_usize(k: &str, d: usize) -> usize { std::env::var(k).ok().and_then(|v| v.parse().ok()).unwrap_or(d) }

fn color(i: usize) -> Color {
    rgb((60 + (i * 37) % 180) as u8, (60 + (i * 91) % 180) as u8, (60 + (i * 53) % 180) as u8)
}

fn unit_box(c: Color) -> Mesh {
    let mut m = Mesh::new();
    m.add_box((0.0, 0.0, 0.0), (0.8, 0.8, 0.8), c).expect("box");
    m
}

fn grid_pos(i: usize, side: usize, spacing: f32) -> Vec3 {
    let half = side as f32 * spacing * 0.5;
    Vec3::new((i % side) as f32 * spacing - half, 0.0, (i / side) as f32 * spacing - half)
}

fn main() {
    let scene = std::env::var("DRAWBENCH_SCENE").unwrap_or_else(|_| "unique".into());
    let mut ids: Vec<EntityId> = Vec::new();
    let mut dts: Vec<f32> = Vec::new();
    let mut frame_no = 0usize;
    // frame.dt is clamped for gameplay, so time the callbacks with our own clock.
    let mut last: Option<std::time::Instant> = None;
    let warm = env_usize("DRAWBENCH_WARM", 300);
    let measure = env_usize("DRAWBENCH_FRAMES", 600);
    let scene2 = scene.clone();
    Engine::run_with("drawbench", EngineLimits::permissive(), move |world, frame| {
        if frame.first {
            world.set_vsync(false);
            world.set_shadows(None);
            world.set_ambient_occlusion(None);
            world.set_global_illumination(None);
            world.set_bloom(BloomSettings::disabled());
            world.set_sun(Vec3::new(0.4, 1.0, 0.2), 0.3);
            match scene2.as_str() {
                "unique" | "moving" => {
                    for i in 0..SIDE * SIDE {
                        let p = Place { position: grid_pos(i, SIDE, 1.2), ..Place::default() };
                        ids.push(world.place(unit_box(color(i)), p)?);
                    }
                }
                "instanced" => {
                    let places: Vec<Place> = (0..INST_SIDE * INST_SIDE)
                        .map(|i| Place { position: grid_pos(i, INST_SIDE, 0.27), scale: 0.25, tint: color(i), ..Place::default() })
                        .collect();
                    world.spawn_many(unit_box(rgb(255, 255, 255)), places)?;
                }
                other => panic!("DRAWBENCH_SCENE must be unique, moving or instanced, got {other}"),
            }
            // Fixed camera that sees the whole 120 m grid.
            world.look_orbit(Vec3::ZERO, 105.0, 30.0, 45.0);
        }
        if scene2 == "moving" {
            let t = frame.time;
            for (i, id) in ids.iter().enumerate() {
                let mut p = grid_pos(i, SIDE, 1.2);
                p.y = (t * 2.0 + i as f32 * 0.1).sin() * 0.5;
                world.set_place(*id, Place { position: p, yaw_degrees: t * 40.0 + i as f32, ..Place::default() })?;
            }
        }
        frame_no += 1;
        let now = std::time::Instant::now();
        if let Some(prev) = last {
            if frame_no > warm {
                dts.push((now - prev).as_secs_f32() * 1000.0);
            }
        }
        last = Some(now);
        if dts.len() == measure {
            let mut s = dts.clone();
            s.sort_by(|a, b| a.partial_cmp(b).unwrap());
            let mean = s.iter().sum::<f32>() / s.len() as f32;
            println!(
                "{{\"stack\":\"engine\",\"scene\":\"{}\",\"frames\":{},\"median_ms\":{:.3},\"p95_ms\":{:.3},\"mean_ms\":{:.3},\"fps\":{:.1},\"size\":\"{}x{}\"}}",
                scene2, s.len(), s[s.len() / 2], s[s.len() * 95 / 100], mean, 1000.0 / mean, frame.width, frame.height
            );
            world.request_exit();
        }
        Ok(())
    })
    .expect("engine run");
}
