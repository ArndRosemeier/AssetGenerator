//! Browse every GLB this repo hosts: humans, monsters, and generated assets.
//!
//! Lists come from directory scans. Empty tabs say how to produce the files.
//! Space / E cycles clips on a skinned body. Esc quits.

mod scan;

use engine::egui;
use engine::prelude::*;
use scan::{scan_all, Entry, Tab};
use std::path::{Path, PathBuf};

enum Kind {
    Animated { clips: Vec<String>, clip_i: usize },
    Static,
}

struct Loaded {
    id: String,
    entity: EntityId,
    kind: Kind,
    look_at: Vec3,
    distance: f32,
}

struct App {
    root: PathBuf,
    entries: Vec<Entry>,
    tab: Tab,
    filter: String,
    pending: Option<String>,
    loaded: Option<Loaded>,
    error: Option<String>,
    yaw: f32,
}

fn repo_root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../..")
        .canonicalize()
        .unwrap_or_else(|e| panic!("cannot resolve repo root: {e}"))
}

fn aabb_to_camera(min: Vec3, max: Vec3) -> (Vec3, f32) {
    if !min.is_finite() || !max.is_finite() || min.x > max.x {
        return (Vec3::new(0.0, 1.0, 0.0), 6.0);
    }
    let center = (min + max) * 0.5;
    let extent = (max - min).max_element().max(0.4);
    (center, (extent * 2.2).max(2.5))
}

fn animated_bounds(model: &AnimatedModel) -> (Vec3, f32) {
    let mut min = Vec3::splat(f32::MAX);
    let mut max = Vec3::splat(f32::MIN);
    for mesh in &model.meshes {
        for p in &mesh.positions {
            min = min.min(*p);
            max = max.max(*p);
        }
    }
    aabb_to_camera(min, max)
}

fn static_bounds(mesh: &Mesh) -> (Vec3, f32) {
    let built = mesh.build();
    let mut min = Vec3::splat(f32::MAX);
    let mut max = Vec3::splat(f32::MIN);
    for p in &built.positions {
        min = min.min(*p);
        max = max.max(*p);
    }
    aabb_to_camera(min, max)
}

fn spawn_entry(world: &mut World, root: &Path, entry: &Entry) -> Result<Loaded, String> {
    match AnimatedModel::load_with(&entry.path, root, &EngineLimits::default()) {
        Ok(model) => {
            let clips: Vec<String> = model.clip_names().map(str::to_string).collect();
            let (look_at, distance) = animated_bounds(&model);
            let entity = world
                .spawn_animated(model, Place::default())
                .map_err(|e| format!("spawn {}: {e}", entry.id))?;
            let mut clip_i = 0usize;
            if !clips.is_empty() {
                if let Err(e) = world.play_animation(entity, &clips[0]) {
                    eprintln!("play {} / {}: {e}", entry.id, clips[0]);
                }
            } else {
                clip_i = 0;
            }
            Ok(Loaded {
                id: entry.id.clone(),
                entity,
                kind: Kind::Animated { clips, clip_i },
                look_at,
                distance,
            })
        }
        Err(anim_err) => {
            let mesh = Model::load_with(&entry.path, root, &EngineLimits::default()).map_err(
                |static_err| format!("{}: animated ({anim_err}); static ({static_err})", entry.id),
            )?;
            let (look_at, distance) = static_bounds(&mesh);
            let entity = world
                .place(mesh, Place::default())
                .map_err(|e| format!("spawn {}: {e}", entry.id))?;
            Ok(Loaded {
                id: entry.id.clone(),
                entity,
                kind: Kind::Static,
                look_at,
                distance,
            })
        }
    }
}

fn play_clip(world: &mut World, loaded: &mut Loaded, index: usize) {
    let Kind::Animated { clips, clip_i } = &mut loaded.kind else {
        return;
    };
    if clips.is_empty() {
        return;
    }
    *clip_i = index % clips.len();
    let name = clips[*clip_i].as_str();
    if let Err(e) = world.play_animation(loaded.entity, name) {
        eprintln!("play {} / {name}: {e}", loaded.id);
    }
}

fn main() {
    let root = repo_root();
    let entries = scan_all(&root);
    eprintln!(
        "lab viewer: {} humans, {} monsters, {} assets",
        entries.iter().filter(|e| e.tab == Tab::Humans).count(),
        entries.iter().filter(|e| e.tab == Tab::Monsters).count(),
        entries.iter().filter(|e| e.tab == Tab::Assets).count()
    );

    let first = entries
        .iter()
        .find(|e| e.tab == Tab::Assets && e.id == "assets/crate_small")
        .or_else(|| entries.iter().find(|e| e.tab == Tab::Monsters))
        .or_else(|| entries.first())
        .map(|e| e.id.clone());

    let mut app = App {
        root,
        entries,
        tab: if first
            .as_deref()
            .is_some_and(|id| id.starts_with("monsters/"))
        {
            Tab::Monsters
        } else if first.as_deref().is_some_and(|id| id.starts_with("humans/")) {
            Tab::Humans
        } else {
            Tab::Assets
        },
        filter: String::new(),
        pending: first,
        loaded: None,
        error: None,
        yaw: 0.0,
    };

    Engine::run("Asset Lab", move |world, frame| {
        if frame.first {
            world.clear_color = Color::rgb(140, 190, 230);
            world.spawn(
                Shape::box_at((0.0, -0.05, 0.0), (40.0, 0.1, 40.0), rgb(90, 140, 70))
                    .expect("ground plane"),
            );
            world.set_sun(Vec3::new(0.45, 1.0, 0.25), 0.24);
        }

        if let Some(id) = app.pending.take() {
            let Some(entry) = app.entries.iter().find(|e| e.id == id).cloned() else {
                app.error = Some(format!("scan no longer contains '{id}'"));
                return;
            };
            if let Some(prev) = app.loaded.take() {
                world.despawn(prev.entity);
            }
            match spawn_entry(world, &app.root, &entry) {
                Ok(loaded) => {
                    app.error = None;
                    app.loaded = Some(loaded);
                }
                Err(err) => {
                    eprintln!("{err}");
                    app.error = Some(err);
                }
            }
        }

        if frame.input.pressed(Key::Space) || frame.input.pressed(Key::E) {
            if let Some(cur) = app.loaded.as_mut() {
                let next = match &cur.kind {
                    Kind::Animated { clip_i, .. } => Some(clip_i + 1),
                    Kind::Static => None,
                };
                if let Some(next) = next {
                    play_clip(world, cur, next);
                }
            }
        }

        app.yaw += frame.input.axis(Key::Left, Key::Right) * 70.0 * frame.dt;
        app.yaw += frame.dt * 10.0;
        let (look_at, distance) = app
            .loaded
            .as_ref()
            .map(|l| (l.look_at, l.distance))
            .unwrap_or((Vec3::new(0.0, 1.0, 0.0), 8.0));
        world.look_orbit(look_at, distance, app.yaw, 22.0);

        draw_ui(world, frame, &mut app);
    });
}

fn draw_ui(world: &mut World, frame: &Frame, app: &mut App) {
    let mut clicked_clip: Option<usize> = None;
    let mut clicked_id: Option<String> = None;
    let mut rescan = false;

    egui::Window::new("Library")
        .anchor(egui::Align2::LEFT_TOP, [12.0, 12.0])
        .resizable(true)
        .default_width(300.0)
        .show(frame.ui.ctx(), |ui| {
            ui.horizontal(|ui| {
                for tab in Tab::ALL {
                    if ui.selectable_label(app.tab == tab, tab.label()).clicked() {
                        app.tab = tab;
                    }
                }
                if ui.button("Rescan").clicked() {
                    rescan = true;
                }
            });
            ui.text_edit_singleline(&mut app.filter);
            if let Some(err) = &app.error {
                ui.colored_label(egui::Color32::from_rgb(180, 40, 40), err);
            }
            if let Some(cur) = app.loaded.as_ref() {
                ui.label(format!("showing  {}", cur.id));
                match &cur.kind {
                    Kind::Animated { clips, clip_i } if !clips.is_empty() => {
                        ui.label(format!("clip  {}", clips[*clip_i]));
                        ui.separator();
                        ui.label("clips");
                        for (i, name) in clips.iter().enumerate() {
                            if ui.selectable_label(i == *clip_i, name.as_str()).clicked() {
                                clicked_clip = Some(i);
                            }
                        }
                    }
                    Kind::Animated { .. } => {
                        ui.label("skinned, no clips");
                    }
                    Kind::Static => {
                        ui.label("static mesh");
                    }
                }
            }
            ui.separator();
            ui.label("Space / E cycle clips. Arrows yaw. Esc quits.");
            ui.label("Skinned albedo is vertex colour until Engine samples maps.");
            ui.separator();

            let filter = app.filter.to_ascii_lowercase();
            let tab_entries: Vec<&Entry> = app
                .entries
                .iter()
                .filter(|e| e.tab == app.tab)
                .filter(|e| {
                    filter.is_empty()
                        || e.id.to_ascii_lowercase().contains(&filter)
                        || e.label.to_ascii_lowercase().contains(&filter)
                        || e.group.to_ascii_lowercase().contains(&filter)
                })
                .collect();
            if tab_entries.is_empty() {
                ui.label(app.tab.empty_hint());
                return;
            }
            let mut groups: Vec<String> = Vec::new();
            for entry in &tab_entries {
                if !groups.iter().any(|g| g == &entry.group) {
                    groups.push(entry.group.clone());
                }
            }
            let selected = app.loaded.as_ref().map(|l| l.id.as_str());
            for group in groups {
                egui::CollapsingHeader::new(&group)
                    .default_open(true)
                    .show(ui, |ui| {
                        for entry in tab_entries.iter().filter(|e| e.group == group) {
                            let is_sel = selected == Some(entry.id.as_str());
                            if ui.selectable_label(is_sel, entry.label.as_str()).clicked()
                                && !is_sel
                            {
                                clicked_id = Some(entry.id.clone());
                            }
                        }
                    });
            }
        });

    if let Some(i) = clicked_clip {
        if let Some(cur) = app.loaded.as_mut() {
            play_clip(world, cur, i);
        }
    }
    if let Some(id) = clicked_id {
        app.pending = Some(id);
    }
    if rescan {
        app.entries = scan_all(&app.root);
        eprintln!(
            "rescanned: {} humans, {} monsters, {} assets",
            app.entries.iter().filter(|e| e.tab == Tab::Humans).count(),
            app.entries
                .iter()
                .filter(|e| e.tab == Tab::Monsters)
                .count(),
            app.entries.iter().filter(|e| e.tab == Tab::Assets).count()
        );
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn scan_repo_roots() {
        let root = repo_root();
        let entries = scan_all(&root);
        let monsters = entries.iter().filter(|e| e.tab == Tab::Monsters).count();
        let assets = entries.iter().filter(|e| e.tab == Tab::Assets).count();
        if root
            .join("assets/monsters/quaternius/big/Orc.glb")
            .is_file()
        {
            assert!(
                entries
                    .iter()
                    .any(|e| e.id == "monsters/quaternius/big/Orc"),
                "scan missed fetched Orc"
            );
            assert!(
                monsters >= 50,
                "expected the full Quaternius set, got {monsters}"
            );
        }
        if root.join("assets/humans/male_base.glb").is_file() {
            assert!(
                entries.iter().any(|e| e.id == "humans/male_base"),
                "scan missed male_base"
            );
            let human = root.join("assets/humans/male_base.glb");
            let model = AnimatedModel::load_with(&human, &root, &EngineLimits::default())
                .expect("male_base must load as a skinned model");
            assert!(
                model.meshes.iter().all(|m| m.uvs.len() == m.positions.len()),
                "male_base mesh is missing UVs"
            );
            assert!(
                model.meshes.iter().any(|m| m.albedo.is_some()),
                "male_base must ship a baseColorTexture"
            );
        }
        let dressed = root.join("assets/humans/male_dressed_male_casualsuit01.glb");
        if dressed.is_file() {
            let model = AnimatedModel::load_with(&dressed, &root, &EngineLimits::default())
                .expect("dressed casualsuit01 must load as a skinned model");
            let textured = model.meshes.iter().filter(|m| m.albedo.is_some()).count();
            assert!(
                model.meshes.len() >= 3,
                "dressed body must include skin, eyes, and clothes, got {} meshes",
                model.meshes.len()
            );
            assert!(
                textured >= 3,
                "dressed body must ship clothes albedo, got {textured} textured meshes"
            );
        }
        if root.join("assets/out/crate_small.glb").is_file() {
            assert!(
                entries.iter().any(|e| e.id == "assets/crate_small"),
                "scan missed crate_small"
            );
            assert!(assets > 1, "expected many generated assets, got {assets}");
            let crate_path = root.join("assets/out/crate_small.glb");
            assert!(
                AnimatedModel::load_with(&crate_path, &root, &EngineLimits::default()).is_err(),
                "crate_small must not be a skinned model"
            );
            Model::load_with(&crate_path, &root, &EngineLimits::default())
                .expect("crate_small must load as a static mesh");
        }
        let orc = root.join("assets/monsters/quaternius/big/Orc.glb");
        if orc.is_file() {
            let model = AnimatedModel::load_with(&orc, &root, &EngineLimits::default())
                .expect("Orc must load as a skinned model");
            assert!(model.find_clip("Idle").is_some());
            assert!(
                model.meshes.iter().all(|m| m.uvs.len() == m.positions.len()),
                "Orc mesh is missing UVs"
            );
            assert!(
                model.meshes.iter().any(|m| m.albedo.is_some()),
                "Orc must sample Atlas_Monsters.png"
            );
        }
    }
}
