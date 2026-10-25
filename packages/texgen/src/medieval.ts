/**
 * Medieval layers (for MasterWorld's towns): rubble walls, oak, thatch, wooden shingles and leaded
 * glass. Same conventions as the facade and roof layers: +v is up (and up-slope on roofs), heights
 * in metres, tileable.
 */
import { TNoise, Tex, clamp01, mix, newCell, rgb, rnd, smooth, worley, wrapd } from './core';
import { randomCourses } from './layout';
import { stoneBlocks } from './masonry';

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

/** Every medieval layer, in a fixed order (index = layer number). */
export const MEDIEVALS: { name: string; W: number; gen: Gen; normal: number; aoK: number; aoR: [number, number] }[] = [
  { name: 'rubble', W: 2.4, gen: rubble, normal: 1, aoK: 40, aoR: [0.01, 0.05] },
  { name: 'oak', W: 1.6, gen: oak, normal: 1, aoK: 30, aoR: [0.005, 0.02] },
  { name: 'thatch', W: 2.4, gen: thatch, normal: 1, aoK: 60, aoR: [0.006, 0.03] },
  { name: 'shingle', W: 2.0, gen: shingle, normal: 1, aoK: 60, aoR: [0.006, 0.02] },
  { name: 'leaded', W: 0.88, gen: leaded, normal: 0.6, aoK: 10, aoR: [0.003, 0.01] },
];
