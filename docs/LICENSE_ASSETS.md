# Third-party assets

## Quaternius Ultimate Monsters

| Path | Source | License |
| --- | --- | --- |
| `assets/monsters/quaternius/**` | [Quaternius Ultimate Monsters](https://quaternius.com/packs/ultimatemonsters.html), the author's own Google Drive folder `18m4KpzpEzhC9wl7jzr6dUc0N8Jozr79C` | **CC0** |

`assets/monsters/quaternius/License.txt` is the licence file bundled with the
download, written by the fetch script next to the `.glb` files. It is the
author's boilerplate and names a different pack of his ("Ultimate Platformer
Pack") while stating CC0 1.0 Universal; the pack page states the same terms.
**Sketchfab and scraper mirrors of Ultimate Monsters sometimes claim CC-BY.**
They are not the source this repository used and not the terms it relies on.

Fetch and conversion: `python tools/fetch_quaternius_monsters.py`. The pack
ships self-contained `.gltf` with the 9 KB `Atlas_Monsters.png` base64'd into
every one of the fifty files; the script rewrites each as `.glb` pointing at a
single shared copy of the atlas. Geometry, rigs and animation clips are
untouched.

The `.glb` files and atlas are gitignored. `catalog.json` and `CREDITS.txt`
are the committed source. This is not part of `python tools/ag.py regenerate`.
