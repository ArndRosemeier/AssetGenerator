//! Directory scans. The viewer list is whatever `.glb` files are on disk.

use std::fs;
use std::path::{Path, PathBuf};

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Tab {
    Humans,
    Monsters,
    Assets,
}

impl Tab {
    pub const ALL: [Tab; 3] = [Tab::Humans, Tab::Monsters, Tab::Assets];

    pub fn label(self) -> &'static str {
        match self {
            Tab::Humans => "Humans",
            Tab::Monsters => "Monsters",
            Tab::Assets => "Assets",
        }
    }

    pub fn empty_hint(self) -> &'static str {
        match self {
            Tab::Humans => "No human GLBs. Run: python tools/sync_character_studio_assets.py",
            Tab::Monsters => "No monster GLBs. Run: python tools/fetch_quaternius_monsters.py",
            Tab::Assets => "No generated GLBs. Run: python tools/ag.py generate crate_small",
        }
    }
}

#[derive(Clone, Debug)]
pub struct Entry {
    pub tab: Tab,
    pub id: String,
    pub group: String,
    pub label: String,
    pub path: PathBuf,
}

pub fn scan_all(root: &Path) -> Vec<Entry> {
    let mut out = Vec::new();
    out.extend(scan_humans(root));
    out.extend(scan_monsters(root));
    out.extend(scan_assets(root));
    out
}

fn scan_humans(root: &Path) -> Vec<Entry> {
    let dir = root.join("assets/humans");
    let mut out = Vec::new();
    let Ok(entries) = fs::read_dir(&dir) else {
        return out;
    };
    for item in entries {
        let Ok(item) = item else {
            continue;
        };
        let path = item.path();
        if !is_glb(&path) {
            continue;
        }
        let stem = file_stem(&path);
        let (group, label) = human_group_label(&stem);
        out.push(Entry {
            tab: Tab::Humans,
            id: format!("humans/{stem}"),
            group,
            label,
            path,
        });
    }
    out.sort_by(|a, b| (&a.group, &a.label).cmp(&(&b.group, &b.label)));
    out
}

fn human_group_label(stem: &str) -> (String, String) {
    for sex in ["male", "female"] {
        let base = format!("{sex}_base");
        if stem == base {
            return (sex.to_string(), "base".to_string());
        }
        let prefix = format!("{sex}_dressed_");
        if let Some(rest) = stem.strip_prefix(&prefix) {
            return (sex.to_string(), rest.to_string());
        }
    }
    ("other".to_string(), stem.to_string())
}

fn scan_monsters(root: &Path) -> Vec<Entry> {
    let dir = root.join("assets/monsters");
    let mut out = Vec::new();
    collect_glbs(&dir, &dir, &mut out);
    let mut entries: Vec<Entry> = out
        .into_iter()
        .map(|path| {
            let rel = path.strip_prefix(&dir).unwrap_or(&path).with_extension("");
            let rel = rel.to_string_lossy().replace('\\', "/");
            let group = rel
                .rsplit_once('/')
                .map(|(parent, _)| parent.to_string())
                .unwrap_or_else(|| "monsters".to_string());
            let label = rel
                .rsplit_once('/')
                .map(|(_, name)| name.to_string())
                .unwrap_or_else(|| rel.clone());
            Entry {
                tab: Tab::Monsters,
                id: format!("monsters/{rel}"),
                group,
                label,
                path,
            }
        })
        .collect();
    entries.sort_by(|a, b| (&a.group, &a.label).cmp(&(&b.group, &b.label)));
    entries
}

fn scan_assets(root: &Path) -> Vec<Entry> {
    let dir = root.join("assets/out");
    let mut out = Vec::new();
    let Ok(entries) = fs::read_dir(&dir) else {
        return out;
    };
    for item in entries {
        let Ok(item) = item else {
            continue;
        };
        let path = item.path();
        if !is_glb(&path) {
            continue;
        }
        let stem = file_stem(&path);
        let group = asset_group(&stem);
        out.push(Entry {
            tab: Tab::Assets,
            id: format!("assets/{stem}"),
            group,
            label: stem,
            path,
        });
    }
    out.sort_by(|a, b| (&a.group, &a.label).cmp(&(&b.group, &b.label)));
    out
}

fn asset_group(stem: &str) -> String {
    stem.split_once('_')
        .map(|(prefix, _)| prefix.to_string())
        .unwrap_or_else(|| stem.to_string())
}

fn collect_glbs(root: &Path, dir: &Path, out: &mut Vec<PathBuf>) {
    let Ok(entries) = fs::read_dir(dir) else {
        return;
    };
    for item in entries {
        let Ok(item) = item else {
            continue;
        };
        let path = item.path();
        if path.is_dir() {
            collect_glbs(root, &path, out);
        } else if is_glb(&path) {
            out.push(path);
        }
    }
}

fn is_glb(path: &Path) -> bool {
    path.extension()
        .is_some_and(|e| e.eq_ignore_ascii_case("glb"))
}

fn file_stem(path: &Path) -> String {
    path.file_stem()
        .map(|s| s.to_string_lossy().into_owned())
        .unwrap_or_default()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn human_labels_split_sex_and_outfit() {
        assert_eq!(
            human_group_label("male_base"),
            ("male".to_string(), "base".to_string())
        );
        assert_eq!(
            human_group_label("female_dressed_viking"),
            ("female".to_string(), "viking".to_string())
        );
    }

    #[test]
    fn asset_groups_use_first_token() {
        assert_eq!(asset_group("pine_alpine_short"), "pine");
        assert_eq!(asset_group("crate_small"), "crate");
        assert_eq!(asset_group("crawler_spider_wolf"), "crawler");
    }

    #[test]
    fn scan_does_not_require_files() {
        let tmp = std::env::temp_dir().join("asset_lab_scan_empty");
        let _ = fs::create_dir_all(&tmp);
        let entries = scan_all(&tmp);
        assert!(entries.is_empty());
    }
}
