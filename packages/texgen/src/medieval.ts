/**
 * Medieval layers (for MasterWorld's towns and cellars): rubble walls, oak, thatch, wooden shingles,
 * leaded glass, cobbles; for the cellars below: flagstones, old brick, floorboards and limewashed rubble. Same conventions as the facade and roof layers: +v is up (and up-slope on roofs), heights
 * in metres, tileable.
 */
import { TNoise, Tex, clamp01, mix, newCell, rgb, rnd, smooth, worley, wrapd } from './core';
import { randomCourses, runningBond } from './layout';
import { brickWall, stoneBlocks } from './masonry';

type Gen = (t: Tex) => void;

/** Rubble walling: rough field stones of many sizes in roughly level courses, deep lime joints. */
const rubble: Gen = (t) => {
  stoneBlocks(t, {
    seed: 7101, layout: randomCourses(t.W, [0.16, 0.24, 0.14, 0.3, 0.2, 0.18, 0.26, 0.22, 0.12, 0.28], 0.18, 0.55, 7102),
    joint: 0.026, depth: 0.014, bevel: 0.03, ragged: 0.018, bulge: 0.012, rough3d: 0.01,
    base: rgb(150, 142, 128), vary: 0.14, hue: 0.05, grain: 0.12, bedding: 1.5,
    mortar: rgb(196, 188, 170), jointDirt: 0.6, soot: 0.2, streaks: 0.3, rough: 0.92, roughJoint: 0.97, erosion: 0.3,
  });
};

/** Old oak: adzed faces with long grain, open checks and a grey weathered sheen. */
const oak: Gen = (t) => {
  const n1 = new TNoise(7201, t.W), n2 = new TNoise(7202, t.W), n3 = new TNoise(7203, t.W);
  t.each((u, v, _x, _y, idx) => {
    // Grain runs along u.
    const grain = n1.fbm(u, v, 0.6, 4, 0.55, 0.012);
    const ring = Math.abs(Math.sin(v * 220 + n2.fbm(u, v, 0.5, 3) * 9));
    const check = smooth(0.82, 0.96, n3.ridged(u, v, 0.9, 3, 0.5, 0.05)) * smooth(-0.2, 0.4, n2.fbm(u, v, 1.2, 2));
    const adze = n2.fbm(u, v, 0.18, 2, 0.5, 0.1) * 0.0015;
    const k = (1 + grain * 0.25 - (ring < 0.2 ? 0.1 : 0)) * (1 - check * 0.6);
    const grey = smooth(-0.2, 0.5, n3.fbm(u, v, 0.8, 3)) * 0.35;
    const r = mix(0.36, 0.33, grey) * k, g = mix(0.27, 0.31, grey) * k, b = mix(0.2, 0.28, grey) * k;
    t.set(idx, r, g, b, 0.78 + grey * 0.1, adze + grain * 0.0008 - check * 0.004);
  });
};

/** Thatch: straw laid in courses, combed down-slope, darker and mossy where it is old. */
const thatch: Gen = (t) => {
  const n1 = new TNoise(7301, t.W), n2 = new TNoise(7302, t.W), n3 = new TNoise(7303, t.W);
  const course = 0.3;
  t.each((u, v, _x, y, idx) => {
    // Fine stalks along v (down the slope), bunched in courses that overlap downward.
    const stalk = n1.fbm(u, v, 0.012, 3, 0.6, 0.25);
    const bunch = n2.fbm(u, v, 0.09, 3, 0.5, 0.4);
    const ly = (y / course) % 1;
    const butt = smooth(0, 0.12, ly) * (1 - smooth(0.7, 1, ly) * 0.3);
    const h = stalk * 0.006 + bunch * 0.012 + butt * 0.02 + (1 - ly) * 0.01;
    const age = smooth(-0.3, 0.5, n3.fbm(u, v, 0.8, 4));
    const moss = smooth(0.35, 0.7, n3.fbm(u + 0.3, v, 0.5, 3)) * 0.5;
    const k = 1 + stalk * 0.35 + bunch * 0.15 - (1 - butt) * 0.25;
    let r = mix(0.62, 0.42, age) * k, g = mix(0.5, 0.36, age) * k, b = mix(0.3, 0.24, age) * k;
    r = mix(r, 0.26, moss); g = mix(g, 0.3, moss); b = mix(b, 0.16, moss);
    t.set(idx, r, g, b, 0.95, h);
  });
};

/** Split wooden shingles in staggered courses, silvered by the weather. */
const shingle: Gen = (t) => {
  const W = t.W, E = 0.16, NR = Math.round(W / E), Ev = W / NR;
  const n1 = new TNoise(7401, W), n2 = new TNoise(7402, W);
  t.each((u, v, x, y, idx) => {
    const row = Math.floor(y / Ev) % NR, ly = y / Ev - Math.floor(y / Ev);
    const nc = Math.round(W / (0.12 + 0.08 * rnd(7403, row))), sw = W / nc;
    const xx = (x + rnd(7404, row) * W) % W;
    const col = Math.floor(xx / sw) % nc, lx = xx / sw - Math.floor(xx / sw);
    const id = row * 97 + col;
    const ra = rnd(7405, id), rb = rnd(7406, id);
    const gap = smooth(0, 0.06, Math.min(lx, 1 - lx));
    const grain = n1.fbm(u, v, 0.4, 3, 0.5, 0.01);
    const h = (1 - ly) * 0.008 + grain * 0.0005 + (ra - 0.5) * 0.002;
    const silver = clamp01(0.5 + (rb - 0.5) * 0.6 + n2.fbm(u, v, 0.6, 3) * 0.3);
    const k = (0.85 + 0.3 * ra) * (1 + grain * 0.3) * (0.55 + 0.45 * gap) * (0.8 + 0.2 * smooth(0, 0.15, ly));
    const r = mix(0.42, 0.44, silver) * k, g = mix(0.3, 0.42, silver) * k, b = mix(0.2, 0.4, silver) * k;
    t.set(idx, r, g, b, 0.8, mix(-0.002, h, gap));
  });
};

/** Leaded glass: small diamond panes of greenish crown glass in lead cames, dark behind. */
const leaded: Gen = (t) => {
  const W = t.W;
  const n1 = new TNoise(7501, W);
  const cell = newCell();
  const P = 0.11;
  t.each((u, v, x, y, idx) => {
    // Diamond lattice: rotate 45° and take the distance to the grid lines.
    const la = (x + y) / P, lb = (x - y) / P;
    const da = Math.abs(wrapd(la, 1)), db = Math.abs(wrapd(lb, 1));
    const came = Math.min(da, db) * P;
    const lead = smooth(0.006, 0.003, came);
    worley(7502, u * 40, v * 40, 40, 40, 1, cell);
    const ripple = n1.fbm(u, v, 0.05, 2) * 0.3;
    const glassK = 0.12 + ripple * 0.05 + (cell.id & 7) * 0.006;
    const r = mix(glassK * 0.8, 0.16, lead), g = mix(glassK, 0.17, lead), b = mix(glassK * 0.85, 0.18, lead);
    t.set(idx, r, g, b, mix(0.05, 0.55, lead), lead * 0.002 + ripple * 0.0004);
  });
};

/** Cobbles: rounded field stones of mixed sizes, set close in sandy earth, worn smooth on top. */
const cobbles: Gen = (t) => {
  const W = t.W, N = Math.round(W / 0.14), m = W / N;
  const n1 = new TNoise(7601, W), n2 = new TNoise(7602, W);
  const cell = newCell();
  const S = [rgb(126, 120, 112), rgb(108, 106, 104), rgb(94, 96, 100), rgb(134, 120, 106), rgb(142, 136, 124), rgb(116, 110, 100), rgb(100, 92, 84)];
  t.each((u, v, _x, _y, idx) => {
    const wu = u + n1.fbm(u, v, 0.3, 2) * 0.004, wv = v + n1.fbm(u + 0.4, v, 0.3, 2) * 0.004;
    worley(7603, wu * N + 0.5, wv * N + 0.5, N, N, 0.7, cell, true);
    const ra = rnd(7604, cell.id), rb = rnd(7605, cell.id);
    const edge = cell.edge * m;
    const e = edge - 0.005 - ra * 0.004;
    const stone = smooth(-0.002, 0.005, e);
    const dome = Math.pow(clamp01(e / (0.045 + rb * 0.02)), 0.6) * 0.03;
    const grain = n2.fbm(u, v, 0.015, 3) * 0.002;
    const c = S[Math.floor(ra * S.length) % S.length];
    const k = (0.85 + rb * 0.3) * (1 + grain * 40) * (0.75 + 0.25 * Math.sqrt(clamp01(e / 0.04)));
    const dirt = smooth(-0.3, 0.6, n2.fbm(u, v, 0.4, 3)) * 0.25;
    const r = mix(0.2, mix(c[0] * k, 0.3, dirt), stone), g = mix(0.18, mix(c[1] * k, 0.27, dirt), stone), b = mix(0.14, mix(c[2] * k, 0.2, dirt), stone);
    t.set(idx, r, g, b, mix(0.95, 0.7 - dome * 6, stone), stone * (0.004 + dome) + grain);
  });
};


/** Flagstones: worn slabs of many sizes laid in rough rows, gritty earth in the wide joints, edges rounded by feet. */
const flagstone: Gen = (t) => {
  stoneBlocks(t, {
    seed: 7701, layout: randomCourses(t.W, [0.34, 0.58, 0.27, 0.49, 0.38, 0.62, 0.3], 0.26, 1.05, 7702),
    joint: 0.014, depth: 0.008, bevel: 0.03, ragged: 0.03, bulge: 0.003, rough3d: 0.005,
    base: rgb(124, 120, 112), vary: 0.22, hue: 0.05, grain: 0.12, bedding: 1.2,
    mortar: rgb(104, 96, 84), jointDirt: 0.45, soot: 0.25, streaks: 0, rough: 0.78, roughJoint: 0.98, erosion: 0.35,
  });
};

/** Old hand-made brick: dull red-brown, uneven and chipped, soft lime joints with a white salt bloom. */
const brick: Gen = (t) => {
  const C1 = rgb(132, 70, 50), C2 = rgb(104, 56, 44), C3 = rgb(78, 46, 40), C4 = rgb(150, 92, 66);
  brickWall(t, {
    seed: 7801, layout: runningBond(t.W, 24, 8, 7802, 0.008),
    joint: 0.013, depth: 0.008, bevel: 0.006, ragged: 0.0016, chips: 0.6,
    palette: (a, b, _k, o) => {
      const m = (x: number[], y: number[], k: number) => { o[0] = x[0] + (y[0] - x[0]) * k; o[1] = x[1] + (y[1] - x[1]) * k; o[2] = x[2] + (y[2] - x[2]) * k; };
      m(C1, C2, a);
      if (b < 0.15) m(o, C3, 0.7); else if (b > 0.88) m(o, C4, 0.6);
      const v = 0.86 + 0.26 * ((a * 6.13) % 1);
      o[0] *= v; o[1] *= v; o[2] *= v;
    },
    mottle: 0.14, mortar: rgb(168, 160, 144), soot: 0.6, streaks: 0.45, rough: 0.9,
    paint: { color: rgb(214, 210, 198), coverage: 0.12 },
  });
};

/** Floorboards: long planks of uneven width along u, butt joints staggered, nail heads, grime in the gaps. */
const boards: Gen = (t) => {
  const W = t.W, n1 = new TNoise(7901, W), n2 = new TNoise(7902, W), n3 = new TNoise(7903, W);
  // Plank edges across v (sum to W), each row with its own butt joints along u.
  const widths: number[] = [];
  for (let k = 0, sum = 0; sum < W - 0.12; k++) { const w = 0.17 + rnd(7904, k) * 0.09; widths.push(w); sum += w; }
  const scale = W / widths.reduce((a, b) => a + b, 0);
  const edges = [0];
  for (const w of widths) edges.push(edges[edges.length - 1] + w * scale);
  t.each((u, v, x, y, idx) => {
    let row = 0;
    while (row < widths.length - 1 && y >= edges[row + 1]) row++;
    const ly = (y - edges[row]) / (edges[row + 1] - edges[row]);
    const len = W / (1 + Math.floor(rnd(7905, row) * 2));
    const xx = (x + rnd(7906, row) * W) % W;
    const piece = Math.floor(xx / len), lx = (xx % len) / len;
    const id = row * 31 + piece;
    const ra = rnd(7907, id), rb = rnd(7908, id);
    const gapE = Math.min(ly * (edges[row + 1] - edges[row]), (1 - ly) * (edges[row + 1] - edges[row]), lx * len, (1 - lx) * len);
    const gap = smooth(0.002, 0.008, gapE);
    // Grain along u, a few knots, wear in the middle of the room's path (low-frequency).
    const grain = n1.fbm(u + ra, v, 0.5, 4, 0.55, 0.01);
    const ring = Math.abs(Math.sin(v * 260 + ra * 40 + n2.fbm(u, v, 0.4, 3) * 8));
    const knot = smooth(0.08, 0.0, Math.hypot(((xx % len) - len * (0.3 + ra * 0.4)) * 0.6, (ly - 0.5) * (edges[row + 1] - edges[row]))) * (rb > 0.6 ? 1 : 0);
    const nail = (Math.min(lx * len, (1 - lx) * len) < 0.05 && Math.abs(ly - 0.5) < 0.12) ? smooth(0.007, 0.004, Math.hypot(Math.min(lx * len, (1 - lx) * len) - 0.03, (ly - 0.5) * (edges[row + 1] - edges[row]))) : 0;
    const wear = smooth(-0.2, 0.5, n3.fbm(u, v, 0.9, 3));
    const dirt = (1 - smooth(0.004, 0.03, gapE)) * 0.4;
    const k = (0.82 + ra * 0.3) * (1 + grain * 0.22 - (ring < 0.18 ? 0.08 : 0)) * (1 - knot * 0.2) * (1 - dirt);
    let r = mix(0.42, 0.37, wear) * k, g = mix(0.31, 0.3, wear) * k, b = mix(0.21, 0.24, wear) * k;
    r = mix(r, 0.12, nail); g = mix(g, 0.11, nail); b = mix(b, 0.1, nail);
    const h = mix(-0.004, 0.002 * (1 - wear * 0.5) + grain * 0.0006 - knot * 0.0005 + (rb - 0.5) * 0.0015, gap);
    t.set(idx, mix(0.06, r, gap), mix(0.05, g, gap), mix(0.04, b, gap), mix(0.95, 0.72 + wear * 0.12, gap) - nail * 0.3, h);
  });
};

/** Limewashed rubble: the stones' shape shows through coats of whitewash, flaking off in patches, with damp and mould. */
const limewash: Gen = (t) => {
  const W = t.W, n1 = new TNoise(8001, W), n2 = new TNoise(8002, W), n3 = new TNoise(8003, W);
  stoneBlocks(t, {
    seed: 8004, layout: randomCourses(W, [0.14, 0.27, 0.12, 0.33, 0.19, 0.24, 0.3, 0.16, 0.22], 0.14, 0.6, 8005),
    joint: 0.034, depth: 0.008, bevel: 0.05, ragged: 0.04, bulge: 0.014, rough3d: 0.006,
    base: rgb(140, 134, 122), vary: 0.14, hue: 0.05, grain: 0.1, bedding: 1.4,
    mortar: rgb(176, 168, 150), jointDirt: 0.5, soot: 0, streaks: 0, rough: 0.92, roughJoint: 0.96, erosion: 0.2,
    extra: (u, v, mask, _hit, c) => {
      // Whitewash fills the joints a little and covers the stone, except where it has flaked.
      const flake = smooth(0.16, 0.22, n1.fbm(u, v, 0.6, 5, 0.6) * 0.75 + n2.fbm(u, v, 0.06, 3) * 0.25);
      const coat = 1 - flake;
      const tone = 0.9 + n2.fbm(u, v, 0.25, 3) * 0.05 + n3.fbm(u, v, 0.03, 2) * 0.03;
      const mould = smooth(0.1, 0.45, n3.fbm(u + 0.37, v, 0.35, 4)) * 0.5;
      let r = 0.86 * tone, g = 0.84 * tone, b = 0.78 * tone;
      r = mix(r, 0.34, mould * 0.6); g = mix(g, 0.36, mould * 0.6); b = mix(b, 0.28, mould * 0.6);
      c[0] = mix(c[0], r, coat); c[1] = mix(c[1], g, coat); c[2] = mix(c[2], b, coat);
      c[3] = mix(c[3], 0.95, coat);
      c[4] = c[4] * mix(1, 0.6, coat) + (1 - mask) * coat * 0.004 + coat * 0.0012;
    },
  });
};

/** Every medieval layer, in a fixed order (index = layer number). */
export const MEDIEVALS: { name: string; W: number; gen: Gen; normal: number; aoK: number; aoR: [number, number] }[] = [
  { name: 'rubble', W: 2.4, gen: rubble, normal: 1, aoK: 40, aoR: [0.01, 0.05] },
  { name: 'oak', W: 1.6, gen: oak, normal: 1, aoK: 30, aoR: [0.005, 0.02] },
  { name: 'thatch', W: 2.4, gen: thatch, normal: 1, aoK: 60, aoR: [0.006, 0.03] },
  { name: 'shingle', W: 2.0, gen: shingle, normal: 1, aoK: 60, aoR: [0.006, 0.02] },
  { name: 'leaded', W: 0.88, gen: leaded, normal: 0.6, aoK: 10, aoR: [0.003, 0.01] },
  { name: 'cobbles', W: 2.1, gen: cobbles, normal: 1, aoK: 50, aoR: [0.006, 0.025] },
  { name: 'flagstone', W: 2.4, gen: flagstone, normal: 1, aoK: 45, aoR: [0.008, 0.04] },
  { name: 'brick', W: 1.8, gen: brick, normal: 1, aoK: 40, aoR: [0.004, 0.02] },
  { name: 'boards', W: 2.0, gen: boards, normal: 1, aoK: 30, aoR: [0.004, 0.02] },
  { name: 'limewash', W: 2.4, gen: limewash, normal: 1, aoK: 40, aoR: [0.01, 0.05] },
];
