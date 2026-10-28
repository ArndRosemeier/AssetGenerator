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
  the same town. `size` picks one of `SETTLEMENT_SIZES` (default `town`): a `hamlet` (a few cottages and
  farmsteads round a green with its well; no lanes, temple or inn), a `village` (temple, inn, smithy, a
  couple of crafts, a few stalls), a `town`, and a `capital` (about 250 m across, five or six roads out,
  a taller core; planned in under a second). A capital also has a wall (`plan.wall`, `walls.ts`
  `townWall`: a ring a little outside its edge, a gate where each road goes through, towers along it;
  its fields begin outside it), a seat of rule (a great three-storey stone hall, trade `ruler`, in its
  own grounds `plan.seatGrounds` near the market), quarters (`plan.quarters`: each stretch between two
  roads, `seat`, `temple`, `crafts` or `common`; the crafts go to the crafts quarter first), three inns,
  smithies and bakeries spread over it, and sixteen crafts. Smaller sizes plan exactly as before.
* `building`: `houseShape(b)`, a building's storeys (jettied out over the street), every window and door
  and the chimney, rolled once from its seed; `buildingMesh(b, origin, detail, { open })` draws it from
  outside (`open`: its door stands open, for drawing it hollow). A seat of rule has a tower at each front
  corner, banners by its door and a broad landing before it. `wallMesh` / `wallBlocks` draw a capital's
  wall and let walkers through its gates only.
* `fixtures`: `fixtureMesh(fixtures, height, origin, detail, pick)` draws a town's fixtures out of doors
  (stalls with awnings, the well, benches with their seat at `BENCH_SEAT`, tables, barrels, anvils, ovens,
  workbenches, troughs, woodpiles, gardens, washing lines, hen coops, graves, the offering stone) on the
  ground; `fixtureBlocks` says which a walker runs into.
* `interior`: `planInterior(b)` furnishes every storey of that same shape (stairs up, the hearth under the
  chimney, furniture and the spots people use), `interiorMesh` draws the inside faces with the windows open
  through them and a daylight level per vertex (`INSIDE_LIGHT`), `interiorSolids` gives the boxes a walker
  is walled in by and `interiorBlocked` the furniture in its way. Merged with the open building it is a
  hollow building one walks into where it stands.

* `route`: roads between places over open land (`routeRoad`): the cheapest way over a grid, where cost
  grows with the grade, water is crossed only at a ford and the caller may forbid ground; straightened
  and rounded, points evenly spaced. `roadProfile` lays the height a road runs at (eased over rises,
  meeting the ground at both ends), so the land can be cut and filled to it.

Came from Scale (`src/core/geom2.ts`, `src/core/clip.ts`, `src/plan/cell.ts`, v1.0); the town planner
is new, for MasterWorld.
