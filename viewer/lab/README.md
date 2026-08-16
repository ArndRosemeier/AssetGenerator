# Asset Lab viewer

One Engine window for everything this repo hosts. Tabs are filled by scanning
directories — there is no asset registry.

| Tab | Scans |
| --- | --- |
| Humans | `assets/humans/*.glb` (base + dressed outfits) |
| Monsters | `assets/monsters/**/*.glb` |
| Assets | `assets/out/*.glb` (generated specs: trees, rocks, kit cells, …) |

Empty tabs stay empty and print the command that produces the files. Character
Studio morph sliders are not here.

```bat
viewer\lab\Lab.bat
```

```bash
cargo run -p lab
```

Needs a sibling Engine checkout at `../Engine`. Controls: click an item, Space
or E cycles clips on a skinned body, arrow keys add yaw, Esc quits, Rescan
re-reads the folders.
