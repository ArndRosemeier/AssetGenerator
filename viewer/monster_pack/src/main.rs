//! Browse the Quaternius Ultimate Monsters catalog and play clips.
//!
//! Space / E cycles clips on the current body. Esc quits.
//!
//! The Engine skinned path is vertex colour only; the pack's atlas will not
//! show until Engine samples albedo on skinned meshes.

use engine::egui;
use engine::prelude::*;
use serde::Deserialize;
use std::collections::BTreeMap;
use std::fs;
use std::path::{Path, PathBuf};

const PACK_REL: &str = "assets/monsters/quaternius";
const FETCH_HINT: &str = "python tools/fetch_quaternius_monsters.py";

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct Catalog {
    pack: String,
    title: String,
    source: String,
    license: String,
    atlas: String,
    families: BTreeMap<String, Family>,
    bodies: Vec<Body>,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct Family {
    rig: String,
    clips: BTreeMap<String, String>,
}

#[derive(Debug, Clone, Deserialize)]
#[serde(deny_unknown_fields)]
struct Body {
    id: String,
    family: String,
    file: String,
    measured_height_m: f32,
    offset: [f32; 3],
    notes: String,
}

struct Loaded {
    body: Body,
    clips: Vec<String>,
    clip_i: usize,
    entity: EntityId,
}

fn repo_root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../..")
        .canonicalize()
        .unwrap_or_else(|e| panic!("cannot resolve repo root: {e}"))
}

fn load_catalog(pack_dir: &Path) -> Catalog {
    let path = pack_dir.join("catalog.json");
    let text = fs::read_to_string(&path).unwrap_or_else(|e| {
        panic!(
            "missing catalog at {} ({e}). Run: {FETCH_HINT}",
            path.display()
        )
    });
    let catalog: Catalog =
        serde_json::from_str(&text).unwrap_or_else(|e| panic!("catalog.json is invalid: {e}"));
    if catalog.bodies.is_empty() {
        panic!("catalog.json has no bodies");
    }
    for body in &catalog.bodies {
        if !catalog.families.contains_key(&body.family) {
            panic!("body '{}' names unknown family '{}'", body.id, body.family);
        }
        if body.measured_height_m <= 0.0 || !body.measured_height_m.is_finite() {
            panic!(
                "body '{}' has invalid measured_height_m {}",
                body.id, body.measured_height_m
            );
        }
        if body.offset.iter().any(|v| !v.is_finite()) {
            panic!("body '{}' has a non-finite offset", body.id);
        }
    }
    catalog
}

fn require_pack_files(pack_dir: &Path, catalog: &Catalog) {
    let atlas = pack_dir.join(&catalog.atlas);
    if !atlas.is_file() {
        panic!("missing atlas {} . Run: {FETCH_HINT}", atlas.display());
    }
    let mut missing: Vec<String> = Vec::new();
    for body in &catalog.bodies {
        let path = pack_dir.join(&body.file);
        if !path.is_file() {
            missing.push(body.file.clone());
        }
    }
    if !missing.is_empty() {
        panic!(
            "missing {} pack file(s), first: {}. Run: {FETCH_HINT}",
            missing.len(),
            missing[0]
        );
    }
}

fn load_body(pack_dir: &Path, body: &Body) -> AnimatedModel {
    let path = pack_dir.join(&body.file);
    AnimatedModel::load_with(&path, pack_dir, &EngineLimits::default())
        .unwrap_or_else(|e| panic!("failed to load {}: {e}", body.id))
}

fn spawn_body(world: &mut World, pack_dir: &Path, body: &Body) -> Loaded {
    let model = load_body(pack_dir, body);
    let clips: Vec<String> = model.clip_names().map(str::to_string).collect();
    if clips.is_empty() {
        panic!("{} has no animation clips", body.id);
    }
    let [ox, oy, oz] = body.offset;
    let place = Place::at(ox, oy, oz)
        .unwrap_or_else(|e| panic!("{} offset is not a valid Place: {e}", body.id));
    let entity = world
        .spawn_animated(model, place)
        .unwrap_or_else(|e| panic!("spawn {}: {e}", body.id));
    let first = clips[0].as_str();
    if let Err(e) = world.play_animation(entity, first) {
        eprintln!("play {} / {first}: {e}", body.id);
    }
    Loaded {
        body: body.clone(),
        clips,
        clip_i: 0,
        entity,
    }
}

fn play_clip(world: &mut World, loaded: &mut Loaded, index: usize) {
    loaded.clip_i = index % loaded.clips.len();
    let name = loaded.clips[loaded.clip_i].as_str();
    if let Err(e) = world.play_animation(loaded.entity, name) {
        eprintln!("play {} / {name}: {e}", loaded.body.id);
    } else {
        eprintln!("clip -> {name}");
    }
}

fn main() {
    let root = repo_root();
    let pack_dir = root.join(PACK_REL);
    if !pack_dir.is_dir() {
        panic!(
            "missing pack directory {} . Run: {FETCH_HINT}",
            pack_dir.display()
        );
    }
    let catalog = load_catalog(&pack_dir);
    require_pack_files(&pack_dir, &catalog);
    eprintln!(
        "loaded {} ({} bodies). controls: click a body, Space/E cycle clips",
        catalog.title,
        catalog.bodies.len()
    );

    let mut loaded: Option<Loaded> = None;
    let mut pending: Option<String> = Some(catalog.bodies[0].id.clone());
    let mut yaw = 0.0f32;

    Engine::run("monster_pack", move |world, frame| {
        if frame.first {
            world.clear_color = Color::rgb(140, 190, 230);
            world.spawn(
                Shape::box_at((0.0, -0.05, 0.0), (24.0, 0.1, 24.0), rgb(90, 140, 70))
                    .expect("ground plane"),
            );
            world.set_sun(Vec3::new(0.45, 1.0, 0.25), 0.24);
        }

        if let Some(id) = pending.take() {
            let body = catalog
                .bodies
                .iter()
                .find(|b| b.id == id)
                .unwrap_or_else(|| panic!("catalog has no body '{id}'"))
                .clone();
            if let Some(prev) = loaded.take() {
                world.despawn(prev.entity);
            }
            loaded = Some(spawn_body(world, &pack_dir, &body));
        }

        if frame.input.pressed(Key::Space) || frame.input.pressed(Key::E) {
            if let Some(cur) = loaded.as_mut() {
                let next = cur.clip_i + 1;
                play_clip(world, cur, next);
            }
        }

        yaw += frame.input.axis(Key::Left, Key::Right) * 70.0 * frame.dt;
        yaw += frame.dt * 12.0;

        let height = loaded
            .as_ref()
            .map(|l| l.body.measured_height_m)
            .unwrap_or(3.0);
        world.look_orbit(
            Vec3::new(0.0, height * 0.45, 0.0),
            (height * 2.4).max(4.0),
            yaw,
            22.0,
        );

        let family_clips = loaded.as_ref().map(|l| {
            catalog
                .families
                .get(&l.body.family)
                .map(|f| f.clips.clone())
                .unwrap_or_default()
        });

        egui::Window::new("Monsters")
            .anchor(egui::Align2::LEFT_TOP, [12.0, 12.0])
            .resizable(true)
            .default_width(280.0)
            .show(frame.ui.ctx(), |ui| {
                ui.label(format!("{}  ({})", catalog.title, catalog.pack));
                ui.label(format!("{}  {}", catalog.license, catalog.source));
                let mut clicked_clip: Option<usize> = None;
                if let Some(cur) = loaded.as_ref() {
                    ui.label(format!("body  {}", cur.body.id));
                    ui.label(format!(
                        "height  {:.3} m   clip  {}",
                        cur.body.measured_height_m, cur.clips[cur.clip_i]
                    ));
                    if let Some(expected) = family_clips.as_ref() {
                        ui.label(format!("rig  {}", catalog.families[&cur.body.family].rig));
                        for (action, name) in expected {
                            let present = cur.clips.iter().any(|c| c == name);
                            ui.label(format!(
                                "  {action}: {name}{}",
                                if present { "" } else { "  MISSING" }
                            ));
                        }
                    }
                    if !cur.body.notes.is_empty() {
                        ui.label(format!("note  {}", cur.body.notes));
                    }
                    ui.separator();
                    ui.label("clips on this file");
                    for (i, name) in cur.clips.iter().enumerate() {
                        if ui
                            .selectable_label(i == cur.clip_i, name.as_str())
                            .clicked()
                        {
                            clicked_clip = Some(i);
                        }
                    }
                }
                if let Some(i) = clicked_clip {
                    if let Some(cur) = loaded.as_mut() {
                        play_clip(world, cur, i);
                    }
                }
                ui.separator();
                ui.label("Space / E cycle clips. Arrows yaw. Esc quits.");
                ui.label("Skinned albedo is not sampled yet — colours are vertex factors.");
                ui.separator();
                for family_name in catalog.families.keys() {
                    egui::CollapsingHeader::new(family_name)
                        .default_open(*family_name == "big")
                        .show(ui, |ui| {
                            for body in catalog.bodies.iter().filter(|b| b.family == *family_name) {
                                let selected =
                                    loaded.as_ref().is_some_and(|l| l.body.id == body.id);
                                if ui.selectable_label(selected, body.id.as_str()).clicked()
                                    && !selected
                                {
                                    pending = Some(body.id.clone());
                                }
                            }
                        });
                }
            });
    });
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn catalog_and_orc_load() {
        let root = repo_root();
        let pack_dir = root.join(PACK_REL);
        let catalog = load_catalog(&pack_dir);
        require_pack_files(&pack_dir, &catalog);
        assert_eq!(catalog.bodies.len(), 50);
        let orc = catalog
            .bodies
            .iter()
            .find(|b| b.id == "big/Orc")
            .expect("catalog must list big/Orc");
        let model = load_body(&pack_dir, orc);
        assert!(model.find_clip("Idle").is_some(), "big/Orc must ship Idle");
        assert!(model.find_clip("Walk").is_some(), "big/Orc must ship Walk");
    }
}
