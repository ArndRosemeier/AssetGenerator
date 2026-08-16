# Monster pack viewer

Engine app that reads [`assets/monsters/quaternius/catalog.json`](../../assets/monsters/quaternius/catalog.json)
and plays the Quaternius Ultimate Monsters clips.

Needs a sibling Engine checkout at `../Engine` (override the Cargo path if yours
lives elsewhere) and the fetched pack on disk.

```bat
viewer\monster_pack\MonsterPack.bat
```

```bash
python tools/fetch_quaternius_monsters.py
cargo run -p monster_pack
```

Controls: click a body, Space or E cycles clips, arrow keys add yaw, Esc quits.

The Engine skinned path is still vertex colour only. The shared atlas will not
show until Engine samples albedo on skinned meshes. Load, facing, and clip names
are what this viewer proves today.
