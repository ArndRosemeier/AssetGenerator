# @futuremagic/dungeon

Dungeons built from cycles, not trees (after Dormans' cyclic generation in *Unexplored*). Pure, runs in
workers and tests. The game brings the meaning (history, inhabitants, dressing); this package brings
the shape.

| Step | Call | What you get |
| --- | --- | --- |
| Graph | `cyclicGraph(spec, seed)` | rooms and links: one main cycle from the entrance to the goal, 0–n more cycles inserted into its passages, a shortcut back out and a refuge added if the cycles made none |
| Pacing | `pace(graph)` | the intended walk in (keys fetched on the way), per-room tension (0 calm .. 1 climax) and beats: entrance, foreshadow, build, safe, reveal, climax, exit, side; the way out and whether it is a shortcut |
| Layout | `layoutDungeon(graph, seed, opts)` | rooms as cell rectangles on storeys (tall rooms span two), passages routed by A* with stairs, doors at both ends; `LayoutGrid` answers which room or passage owns a cell |

## Link kinds

`open`, `door`, `locked` (key in room `key`), `secret` (never on the intended route), `oneway`
(barred on the far side: a shortcut), `drop` (down over a ledge into a tall room), `grate` (see
through, no way through), `blocked` (rubble: a trace of history).

## The cycle library (`PATTERNS`)

| id | the player meets |
| --- | --- |
| `twin-paths` | two ways to the same place |
| `lock-key` | a locked door; its key lies around a loop that comes out behind it |
| `hidden-shortcut` | the long way round, and a hidden way straight back |
| `seen-goal` | the goal seen through bars long before it is reached |
| `drop-in` | a ledge over a tall hall: drop in, then find the way back up |
| `barred-return` | a door barred on the far side opens the way back |
| `collapsed-way` | the old way fell in; something dug around it |
| `secret-key` | the key to a locked door lies behind a hidden one |
| `gallery` | a gallery looks down into a hall that is reached by stairs |
| `side-loop` | a little loop off the way with something for those who look |
| `guarded-short` | a short way past danger or a long quiet one |
| `low-road` | a way beneath: down, along and up again |

Games choose which patterns suit a kind of place (`GraphSpec.main`, `.inserts`) and can weight them
(`GraphSpec.weight`, e.g. down-weight what the player saw lately). Patterns tag what they make
(`key`, `lock`, `view`, `ledge`, `hall`, `gallery`, `dug`, `collapse`, `guarded`, `quiet`, `low`,
`side`, `reward`, `shortcut`, `stairs`), so dressing can follow. The library is meant to grow to
15–20 patterns as more dungeon kinds need them.

## Units

Cells and storeys. MasterWorld uses 2 m cells and 2.8 m storeys with two cells of stairs per storey.
