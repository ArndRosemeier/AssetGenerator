# @futuremagic/settlement

Planning settlements on the ground plane (x, z), pure TypeScript: runs in workers and tests.

* `geom2`: flat polygons `[x0, z0, x1, z1, ...]` (area, centroid, splits, bounding boxes, smoothing).
* `clip`: Clipper booleans and offsets (`union`, `difference`, `intersection`, `offset`, `strokePolylines`).
* `lots`: a street block cut into plots facing the street (`perimeterLots`), the yards left behind.
* `streets`: organic street cuts (`organicCuts`).
* `town`: `planTown(site)`, a medieval small town: market place, roads that follow the land, an outline
  grown along the roads, crooked lanes, plots, houses by zone (timber-framed round the market, cottages
  at the edge), a temple of no particular faith and its burial ground, a moot hall, inn, bakery, smithy, stable, a mill by water, crafts, and the
  fixtures people use (well, stalls, anvil, forge, woodpiles, gardens, graves, an offering stone). The same site gives
  the same town.

Came from Scale (`src/core/geom2.ts`, `src/core/clip.ts`, `src/plan/cell.ts`, v1.0); the town planner
is new, for MasterWorld.
