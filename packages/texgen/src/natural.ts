/**
 * Natural ground layers for open country (wild grass, forest floor, rock, cliff strata, scree, snow, sand,
 * mud, and the kinds of country's: heather, clay, limestone pavement, chalk turf, gravel): the terrain of fantasy and wilderness games. Same conventions as the other layers (index.ts): one
 * tile is W metres square, wraps seamlessly, row 0 = v = 0, +v is "up" (on a cliff: up the face).
 */
import { Rng } from '@futuremagic/core';
import { RGB, TNoise, Tex, mix, newCell, rgb, rnd, smooth, worley } from './core';
import { pebbles, splat, stroke } from './paint';

type Gen = (t: Tex) => void;

/** Long meadow grass: tufts of blades over soil, dry and fresh patches, a few flowers. */
const wildGrass: Gen = (t) => {
  const W = t.W;
  const nD = new TNoise(5101, W), nC = new TNoise(5102, W), nS = new TNoise(5103, W);
  t.each((u, v, _x, _y, idx) => {
    // Thatch: old, flattened grass under the living blades, so gaps read as grass, not as bare soil.
    const k = 0.8 + nS.fbm(u, v, 0.08, 3) * 0.25 + (rnd(5104, idx) - 0.5) * 0.3;
    t.set(idx, 0.25 * k, 0.26 * k, 0.12 * k, 0.95, nS.fbm(u, v, 0.15, 3) * 0.004);
  });
  const rng = new Rng(5105);
  for (let k = 0; k < Math.round((W * W) / 0.0004); k++) {
    const x = rng.float() * W, y = rng.float() * W, a = rng.float() * Math.PI * 2, len = rng.range(0.015, 0.04), vk = rng.range(0.6, 1.1);
    const dry = rng.float();
    stroke(t, x, y, a, len, (_s, idx) => {
      const z = 0.004 + rng.float() * 0.002;
      if (z <= t.h[idx]) return;
      t.set(idx, mix(0.20, 0.40, dry) * vk, mix(0.27, 0.36, dry) * vk, mix(0.09, 0.18, dry) * vk, 0.9, z);
    });
  }
  // Tufts: blades fanning out from a root, so the grass reads as clumps, not as fur.
  const tufts = Math.round((W * W) / 0.0012);
  for (let k = 0; k < tufts; k++) {
    const x = rng.float() * W, y = rng.float() * W, u = x / W, v = y / W;
    if (rng.float() > 0.8 + 0.4 * nC.fbm(u, v, 0.4, 3)) continue;
    const dry = smooth(0.15, 0.7, nD.fbm(u, v, 1.5, 4) + nD.fbm(u, v, 0.2, 2) * 0.3) * 0.7;
    const blades = rng.int(5, 11), lean = rng.float() * Math.PI * 2;
    for (let b = 0; b < blades; b++) {
      const a = lean + rng.range(-1.1, 1.1), len = rng.range(0.03, 0.09), hue = rng.float(), vk = rng.range(0.65, 1.25);
      const dk = dry * rng.range(0.4, 1);
      const cr = mix(mix(0.16, 0.27, hue), 0.58, dk), cg = mix(mix(0.30, 0.40, hue), 0.50, dk), cb = mix(mix(0.07, 0.11, hue), 0.27, dk);
      stroke(t, x, y, a, len, (s, idx) => {
        const z = 0.01 + s * len * 0.8;
        if (z <= t.h[idx]) return;
        const sh = vk * (0.45 + 0.55 * s);
        t.set(idx, cr * sh, cg * sh, cb * sh, 0.72 + dk * 0.2, z);
      });
    }
  }
  // Flowers: small bright heads above the blades, in loose drifts.
  const colours: RGB[] = [rgb(238, 232, 210), rgb(236, 196, 60), rgb(150, 110, 200), rgb(205, 70, 60)];
  const flowers = Math.round(W * W * 30);
  for (let k = 0; k < flowers; k++) {
    const x = rng.float() * W, y = rng.float() * W;
    if (rng.float() > smooth(0.1, 0.5, nC.fbm(x / W + 0.3, y / W, 0.7, 3))) continue;
    const c = colours[rng.int(0, colours.length - 1)], R = rng.range(0.004, 0.008), z = rng.range(0.06, 0.1);
    splat(t, x, y, R, (dx, dy, idx) => {
      const q = 1 - Math.hypot(dx, dy) / R;
      if (z <= t.h[idx]) return;
      t.set(idx, c[0] * (0.8 + 0.2 * q), c[1] * (0.8 + 0.2 * q), c[2] * (0.8 + 0.2 * q), 0.6, z + q * 0.002);
    });
  }
};

/** Forest floor: dark soil, fallen leaves, needles, twigs and moss cushions. */
const forestFloor: Gen = (t) => {
  const W = t.W;
  const nS = new TNoise(5201, W), nM = new TNoise(5202, W);
  t.each((u, v, _x, _y, idx) => {
    const k = 0.8 + nS.fbm(u, v, 0.1, 3) * 0.25 + (rnd(5203, idx) - 0.5) * 0.2;
    t.set(idx, 0.27 * k, 0.20 * k, 0.13 * k, 0.9, nS.fbm(u, v, 0.4, 3) * 0.01);
  });
  const rng = new Rng(5204);
  const leafColours: RGB[] = [rgb(120, 70, 30), rgb(150, 95, 40), rgb(95, 60, 32), rgb(170, 120, 55), rgb(80, 55, 35)];
  const leaves = Math.round((W * W) / 0.0012);
  for (let k = 0; k < leaves; k++) {
    const cx = rng.float() * W, cy = rng.float() * W;
    const a = rng.range(0.025, 0.055), b = a * rng.range(0.4, 0.6), th = rng.float() * Math.PI;
    const ct = Math.cos(th), st = Math.sin(th), z0 = rng.range(0, 0.012), col = leafColours[rng.int(0, leafColours.length - 1)], vk = rng.range(0.7, 1.15);
    splat(t, cx, cy, a, (dx, dy, idx) => {
      const px = dx * ct + dy * st, py = -dx * st + dy * ct;
      const q = (px / a) ** 2 + (py / b) ** 2;
      if (q >= 1) return;
      const z = z0 + (1 - q) * 0.0015 + Math.abs(py / b) * 0.001;
      if (z <= t.h[idx]) return;
      const vein = Math.abs(py) < b * 0.08 ? 0.8 : 1;
      t.set(idx, col[0] * vk * vein, col[1] * vk * vein, col[2] * vk * vein, 0.75, z);
    });
  }
  // Twigs and needles.
  for (let k = 0; k < Math.round(W * W * 260); k++) {
    const x = rng.float() * W, y = rng.float() * W, a = rng.float() * Math.PI * 2, len = rng.range(0.02, 0.12), z0 = rng.range(0.004, 0.016), vk = rng.range(0.6, 1);
    stroke(t, x, y, a, len, (_s, idx) => {
      if (z0 <= t.h[idx]) return;
      t.set(idx, 0.24 * vk, 0.17 * vk, 0.11 * vk, 0.85, z0);
    });
  }
  // Moss cushions on top.
  t.each((u, v, _x, _y, idx) => {
    const m = smooth(0.1, 0.35, nM.fbm(u, v, 0.6, 4));
    if (m <= 0) return;
    const k = 0.8 + nM.fbm(u, v, 0.01, 2) * 0.3;
    t.r[idx] = mix(t.r[idx], 0.24 * k, m); t.g[idx] = mix(t.g[idx], 0.36 * k, m); t.b[idx] = mix(t.b[idx], 0.10 * k, m);
    t.rough[idx] = mix(t.rough[idx], 0.95, m);
    t.h[idx] = Math.max(t.h[idx], 0.012 + m * 0.01 + nM.fbm(u, v, 0.008, 2) * 0.002);
  });
};

interface RockOpts { seed: number; base: RGB; warm: RGB; lichen: number; strata: number; }

/**
 * Weathered rock in place. The face is broken into slabs, wider than they are tall (beds; `strata` makes them thin
 * and banded in colour), each a facet of its own tilt, so where two meet the face steps or folds instead of being
 * drawn round with a dark line (dried mud has plates with gaps; rock has facets with edges). A few fissures wander
 * across it, open in places and shut in others. Every facet is chipped and grainy and a little lighter or darker
 * than the next; rain has run dark streaks down it, iron stains it warm here and there, and lichen crusts the facets
 * that face up. +v is up the face (index.ts); everything wraps with the tile.
 */
function rock(t: Tex, o: RockOpts): void {
  const W = t.W;
  const n1 = new TNoise(o.seed + 1, W), n2 = new TNoise(o.seed + 2, W), n3 = new TNoise(o.seed + 3, W), n4 = new TNoise(o.seed + 7, W);
  const cell = newCell();
  // Slabs about 1.6 m across and 0.7 m high (0.35 m when banded).
  const fx = Math.max(2, Math.round(W / (o.strata > 0 ? 1.6 : 1.3))), fy = Math.max(2, Math.round(W / (o.strata > 0 ? 0.35 : 0.85)));
  t.each((u, v, _x, _y, idx) => {
    const wu = u + n1.fbm(u, v, 1.4, 3) * (0.35 / fx), wv = v + n1.fbm(u + 0.5, v, 1.4, 3) * (0.25 / fy);
    worley(o.seed + 4, wu * fx, wv * fy, fx, fy, 0.9, cell, true);
    const id = cell.id;
    // The facet's own tilt (metres of height per metre across and up), and how far it stands out.
    const ax = (rnd(o.seed + 17, id) - 0.5) * 0.5, ay = (rnd(o.seed + 18, id) - 0.35) * 0.4;
    const dx = (wu * fx - cell.px) * (W / fx), dy = (wv * fy - cell.py) * (W / fy);
    const facet = ax * dx + ay * dy + (rnd(o.seed + 11, id) - 0.5) * 0.06;
    // Edges: a narrow worn bevel where facets meet (the step itself comes from their different tilts).
    const edgeM = cell.edge * Math.min(W / fx, W / fy);
    const worn = smooth(0.0, 0.05, edgeM);
    // Fissures: the wavering zero lines of a noise, open only in stretches.
    const fis = n2.fbm(u, v, 2.2, 3);
    const fissure = (1 - smooth(0.003, 0.014, Math.abs(fis))) * smooth(0.0, 0.35, n3.fbm(u + 0.2, v, 1.7, 2));
    const band = o.strata > 0 ? Math.sin(v * Math.PI * 2 * Math.round(W / 0.8) + n3.fbm(u, v, 2, 2) * 2) * 0.5 + 0.5 : 0;
    const chip = n2.ridged(u + rnd(o.seed + 12, id), v, 0.5, 4) * 0.04 + n3.fbm(u, v, 0.14, 3) * 0.01;
    const bulge = n4.fbm(u + 0.7, v, 2.5, 3) * 0.06;
    const grain = (rnd(o.seed + 5, idx) - 0.5) * 0.004;
    let h = facet + bulge + chip + grain - fissure * 0.02 - (1 - worn) * 0.006 + band * o.strata * 0.008;
    // Tone: facet to facet, broad patches, grain, the beds' bands; dark streaks run down from where water stood.
    const streak = smooth(0.2, 0.65, n4.fbm(u, v, 0.3, 3, 0.5, 3)) * 0.2;
    const lit = ay * 0.5; // facets tilted up catch more dust and light
    const tone = (1 + (rnd(o.seed + 13, id) - 0.5) * 0.14 + lit + n1.fbm(u, v, 1.6, 3) * 0.16 + (rnd(o.seed + 19, idx) - 0.5) * 0.16 + (band - 0.5) * o.strata * 0.22) * (1 - streak);
    const warm = smooth(0.05, 0.65, n3.fbm(u + 0.4, v, 1.8, 3)) * (0.6 + 0.4 * rnd(o.seed + 14, id));
    let r = mix(o.base[0], o.warm[0], warm) * tone, g = mix(o.base[1], o.warm[1], warm) * tone, b = mix(o.base[2], o.warm[2], warm) * tone;
    const dark = 1 - fissure * 0.4 - (1 - worn) * 0.06;
    r *= dark; g *= dark; b *= dark;
    // Lichen: grey-green and orange crusts on facets that face up, never in the fissures.
    const li = smooth(0.3, 0.55, n2.fbm(u + 0.3, v, 0.45, 4)) * o.lichen * smooth(-0.02, 0.12, ay) * (1 - fissure);
    if (li > 0) {
      const orange = rnd(o.seed + 6, id) < 0.3;
      r = mix(r, orange ? 0.62 : 0.55, li); g = mix(g, orange ? 0.40 : 0.58, li); b = mix(b, orange ? 0.15 : 0.45, li);
      h += li * 0.002;
    }
    t.set(idx, r, g, b, 0.86 - fissure * 0.08 - li * 0.05, h);
  });
}

const rockFace: Gen = (t) => rock(t, { seed: 5301, base: rgb(112, 108, 102), warm: rgb(138, 118, 96), lichen: 0.6, strata: 0 });
const cliffStrata: Gen = (t) => rock(t, { seed: 5401, base: rgb(150, 128, 104), warm: rgb(176, 140, 102), lichen: 0.25, strata: 1 });

/** Scree: angular stones of all sizes over grit. */
const scree: Gen = (t) => {
  pebbles(t, 5501, {
    count: 1.6, rMin: 0.02, rMax: 0.11, height: 0.45,
    palette: [rgb(120, 116, 110), rgb(98, 95, 90), rgb(140, 132, 120), rgb(110, 100, 88)],
    fines: rgb(92, 86, 78), finesH: 0, dust: 0.25,
  });
};

/** Snow: wind ripples (sastrugi), soft drifts, a cold blue in the hollows. */
const snow: Gen = (t) => {
  const W = t.W;
  const n1 = new TNoise(5601, W), n2 = new TNoise(5602, W);
  t.each((u, v, _x, _y, idx) => {
    const ripple = n1.ridged(u + n2.fbm(u, v, 1.5, 2) * 0.05, v, 0.9, 3, 0.5, 0.25);
    const h = n2.fbm(u, v, 1.6, 4) * 0.05 + ripple * 0.012 + n1.fbm(u, v, 0.02, 2) * 0.0008;
    const hollow = smooth(0.02, -0.03, h);
    const k = 0.94 + (rnd(5603, idx) - 0.5) * 0.04;
    t.set(idx, mix(0.95, 0.86, hollow) * k, mix(0.96, 0.9, hollow) * k, mix(0.98, 0.97, hollow) * k, 0.55 + (rnd(5604, idx) < 0.02 ? -0.3 : 0), h);
  });
};

/** Sand: wind ripples and fine grain, darker and smoother where damp. */
const sand: Gen = (t) => {
  const W = t.W;
  const n1 = new TNoise(5701, W), n2 = new TNoise(5702, W);
  t.each((u, v, _x, _y, idx) => {
    const warp = n2.fbm(u, v, 0.8, 3) * 0.25;
    const ripple = Math.sin((v + warp) * Math.PI * 2 * Math.round(W / 0.09)) * 0.5 + 0.5;
    const damp = smooth(0.1, 0.5, n1.fbm(u, v, 1.4, 3)) * 0.5;
    const h = ripple * 0.004 * (1 - damp) + n1.fbm(u, v, 0.5, 3) * 0.01;
    const k = (1 + (rnd(5703, idx) - 0.5) * 0.18 + ripple * 0.04) * (1 - damp * 0.35);
    t.set(idx, 0.76 * k, 0.66 * k, 0.48 * k, 0.9 - damp * 0.3, h);
  });
};

/** Mud: wet dark earth, puddles and footprints of rain. */
const mud: Gen = (t) => {
  const W = t.W;
  const n1 = new TNoise(5801, W), n2 = new TNoise(5802, W);
  t.each((u, v, _x, _y, idx) => {
    const h0 = n1.fbm(u, v, 0.5, 4) * 0.02 + n2.fbm(u, v, 0.05, 3) * 0.004 + n2.ridged(u, v, 0.3, 3) * 0.006;
    const wet = smooth(-0.005, -0.015, h0);
    const k = 1 + (rnd(5803, idx) - 0.5) * 0.1;
    const tone = 1 + n2.fbm(u, v, 0.4, 3) * 0.3;
    const r = mix(0.30, 0.13, wet) * k * tone, g = mix(0.23, 0.10, wet) * k * tone, b = mix(0.15, 0.08, wet) * k * tone;
    t.set(idx, r, g, b, mix(0.75, 0.08, wet), Math.max(h0, -0.012));
  });
};

/** Short tufts: `n` per square metre, blades `len` long in `colours`, standing `z0` over the bed (shared by the turf-like layers). */
function tufts(t: Tex, seed: number, n: number, len: [number, number], colours: RGB[], z0: number, where: (u: number, v: number) => number = () => 1): void {
  const W = t.W, rng = new Rng(seed);
  for (let k = 0; k < Math.round(W * W * n); k++) {
    const x = rng.float() * W, y = rng.float() * W;
    if (rng.float() > where(x / W, y / W)) continue;
    const c = colours[rng.int(0, colours.length - 1)], lean = rng.float() * Math.PI * 2;
    for (let b = rng.int(3, 7); b > 0; b--) {
      const a = lean + rng.range(-1.2, 1.2), l = rng.range(len[0], len[1]), vk = rng.range(0.7, 1.2);
      stroke(t, x, y, a, l, (s, idx) => {
        const z = z0 + s * l * 0.6;
        if (z <= t.h[idx]) return;
        const sh = vk * (0.55 + 0.45 * s);
        t.set(idx, c[0] * sh, c[1] * sh, c[2] * sh, 0.85, z);
      });
    }
  }
}

/** Moor: heather in low dark clumps over black peat, purple where it flowers, wiry grass and moss between. */
const heather: Gen = (t) => {
  const W = t.W;
  const nP = new TNoise(5901, W), nC = new TNoise(5902, W);
  t.each((u, v, _x, _y, idx) => {
    const wet = smooth(0.15, 0.4, nP.fbm(u, v, 0.9, 3));
    const k = 0.85 + nP.fbm(u, v, 0.05, 3) * 0.3 + (rnd(5903, idx) - 0.5) * 0.2;
    t.set(idx, mix(0.16, 0.08, wet) * k, mix(0.12, 0.07, wet) * k, mix(0.08, 0.05, wet) * k, mix(0.92, 0.4, wet), nP.fbm(u, v, 0.3, 3) * 0.006 - wet * 0.006);
  });
  // Moss and wiry grass on the peat.
  tufts(t, 5904, 60, [0.02, 0.06], [rgb(110, 112, 60), rgb(140, 128, 70), rgb(80, 96, 44)], 0.002);
  // The heather: clumps of woody sprigs, each a dome of short strokes, flowering in drifts.
  const rng = new Rng(5905);
  for (let k = 0; k < Math.round(W * W * 40); k++) {
    const cx = rng.float() * W, cy = rng.float() * W, u = cx / W, v = cy / W;
    if (rng.float() > smooth(-0.3, 0.3, nC.fbm(u, v, 0.8, 3)) + 0.5) continue;
    const R = rng.range(0.1, 0.25), bloom = smooth(0.0, 0.35, nC.fbm(u + 0.5, v, 1.2, 3)) * rng.range(0.4, 1);
    for (let s = Math.round(R * R * 14000); s > 0; s--) {
      const a = rng.float() * Math.PI * 2, d = Math.sqrt(rng.float()) * R;
      const x = cx + Math.cos(a) * d, y = cy + Math.sin(a) * d, dome = Math.sqrt(1 - (d / R) ** 2);
      const flower = rng.float() < bloom * 0.7, vk = rng.range(0.6, 1.2);
      const c: RGB = flower ? [0.5 * vk, 0.24 * vk, 0.46 * vk] : rng.float() < 0.6 ? [0.22 * vk, 0.24 * vk, 0.12 * vk] : [0.3 * vk, 0.2 * vk, 0.13 * vk];
      stroke(t, x, y, rng.float() * Math.PI * 2, rng.range(0.01, 0.025), (_q, idx) => {
        const z = 0.01 + dome * R * 0.5 + (flower ? 0.003 : 0);
        if (z <= t.h[idx]) return;
        t.set(idx, c[0], c[1], c[2], 0.9, z);
      });
    }
  }
};

/**
 * Badlands: bare clay crusted by the sun, cracked into polygons and crazed into small lumps, a few stones washed
 * out on top. Pale and nearly grey: the land's bands of colour are laid over it by height (the terrain shader).
 */
const clay: Gen = (t) => {
  const W = t.W;
  const n1 = new TNoise(6001, W), n2 = new TNoise(6002, W), n3 = new TNoise(6003, W);
  const big = newCell(), small = newCell();
  // Weathered mudstone dries into a crust: polygons about 0.8 m across with open cracks between them, each crazed
  // into small swollen lumps ("popcorn") a few centimetres across. No direction to it: it lies on any slope.
  const bf = Math.max(2, Math.round(W / 0.8)), sf = Math.max(2, Math.round(W / 0.07));
  t.each((u, v, _x, _y, idx) => {
    const wu = u + n1.fbm(u, v, 1.2, 3) * (0.3 / bf), wv = v + n1.fbm(u + 0.5, v, 1.2, 3) * (0.3 / bf);
    worley(6007, wu * bf, wv * bf, bf, bf, 0.9, big);
    worley(6008, u * sf, v * sf, sf, sf, 0.9, small);
    const crack = 1 - smooth(0.0, 0.04, (big.f2 - big.f1) * (W / bf));
    const seam = 1 - smooth(0.0, 0.2, small.f2 - small.f1);
    const lump = Math.sqrt(Math.max(0, 1 - small.f1 * small.f1 * 1.6));
    const deep = smooth(-0.2, 0.4, n3.fbm(u, v, 0.8, 3));
    const h = lump * 0.006 - seam * 0.002 - crack * 0.02 + n2.fbm(u, v, 0.15, 3) * 0.006 + (rnd(6004, idx) - 0.5) * 0.001;
    const k = (0.92 + n1.fbm(u, v, 0.6, 3) * 0.16 + (rnd(6009, big.id) - 0.5) * 0.1 + (rnd(6005, idx) - 0.5) * 0.06) * (1 - crack * 0.45 - seam * 0.06) * (0.94 + 0.06 * deep);
    t.set(idx, 0.70 * k, 0.62 * k, 0.54 * k, 0.93, h);
  });
  pebbles(t, 6006, { count: 0.06, rMin: 0.01, rMax: 0.04, height: 0.5, palette: [rgb(150, 136, 118), rgb(110, 100, 90), rgb(170, 150, 120)], fines: rgb(0, 0, 0), finesH: 0, bed: false });
};

/**
 * Karst: limestone pavement. Pale grey blocks (clints) between deep joints (grikes) that run in two sets, nearly
 * straight, with moss and ferns down in them; the blocks' tops fluted and pitted by rain.
 */
const limestone: Gen = (t) => {
  const W = t.W;
  const n1 = new TNoise(6101, W), n2 = new TNoise(6102, W), n3 = new TNoise(6103, W);
  const a = Math.round(W / 1.3), b = Math.round(W / 0.9);
  t.each((u, v, _x, _y, idx) => {
    const j1 = Math.abs(Math.sin((u + n1.fbm(u, v, 0.6, 2) * 0.03) * Math.PI * a));
    const j2 = Math.abs(Math.sin((v + u * 0.25 + n2.fbm(u, v, 0.6, 2) * 0.03) * Math.PI * b));
    // The second set breaks off here and there; the first runs through.
    const open2 = smooth(-0.15, 0.15, n3.fbm(u, v, 0.9, 2));
    const grike = Math.max(1 - smooth(0.0, 0.07, j1), (1 - smooth(0.0, 0.06, j2)) * open2);
    const pit = n2.ridged(u, v, 0.08, 3) * 0.004 + n1.fbm(u, v, 0.35, 3) * 0.008;
    const tone = 0.92 + n3.fbm(u, v, 0.5, 3) * 0.14 + (rnd(6104, idx) - 0.5) * 0.1;
    const moss = grike * smooth(-0.1, 0.3, n1.fbm(u + 0.4, v, 0.7, 3));
    let r = 0.66 * tone, g = 0.65 * tone, bl = 0.61 * tone;
    r = mix(r, 0.08, grike * 0.85); g = mix(g, 0.08, grike * 0.85); bl = mix(bl, 0.07, grike * 0.85);
    r = mix(r, 0.16, moss * 0.6); g = mix(g, 0.24, moss * 0.6); bl = mix(bl, 0.08, moss * 0.6);
    t.set(idx, r, g, bl, 0.8 + grike * 0.15, pit - grike * 0.05);
  });
  tufts(t, 6105, 40, [0.03, 0.08], [rgb(80, 110, 50), rgb(110, 120, 60)], -0.03, (u) => smooth(0.4, 0.9, 1 - Math.abs(Math.sin(u * Math.PI * a))));
};

/** Downs: turf grazed short and dense, fine and even, with the white chalk showing through where it is worn, and flints. */
const chalkTurf: Gen = (t) => {
  const W = t.W;
  const n1 = new TNoise(6201, W), n2 = new TNoise(6202, W);
  t.each((u, v, _x, _y, idx) => {
    const k = 0.85 + n1.fbm(u, v, 0.1, 3) * 0.25 + (rnd(6203, idx) - 0.5) * 0.25;
    t.set(idx, 0.18 * k, 0.24 * k, 0.09 * k, 0.92, n1.fbm(u, v, 0.2, 3) * 0.002);
  });
  const worn = (u: number, v: number) => smooth(0.1, 0.36, n2.fbm(u, v, 1.6, 4));
  tufts(t, 6204, 700, [0.008, 0.022], [rgb(70, 100, 36), rgb(92, 118, 44), rgb(110, 120, 56), rgb(60, 88, 34)], 0.002, (u, v) => 1 - worn(u, v) * 0.9);
  t.each((u, v, _x, _y, idx) => {
    const c = worn(u, v);
    if (c <= 0) return;
    const k = 0.92 + (rnd(6205, idx) - 0.5) * 0.12;
    t.r[idx] = mix(t.r[idx], 0.82 * k, c); t.g[idx] = mix(t.g[idx], 0.80 * k, c); t.b[idx] = mix(t.b[idx], 0.74 * k, c);
    t.h[idx] = mix(t.h[idx], -0.002, c);
  });
  pebbles(t, 6206, { count: 0.04, rMin: 0.012, rMax: 0.035, height: 0.4, palette: [rgb(70, 66, 64), rgb(120, 110, 100), rgb(210, 205, 196)], fines: rgb(0, 0, 0), finesH: 0, bed: false, mask: (u, v) => 0.2 + worn(u, v) });
};

/** A river valley's floor: rounded pebbles and grit washed down, grass grown over in drifts between them. */
const gravel: Gen = (t) => {
  const W = t.W;
  const n1 = new TNoise(6301, W);
  pebbles(t, 6302, {
    count: 1.1, rMin: 0.015, rMax: 0.06, height: 0.5,
    palette: [rgb(150, 144, 132), rgb(118, 112, 104), rgb(170, 160, 140), rgb(130, 118, 100), rgb(96, 92, 88)],
    fines: rgb(120, 110, 94), finesH: 0, dust: 0.15,
  });
  tufts(t, 6303, 260, [0.03, 0.08], [rgb(70, 98, 36), rgb(96, 112, 46), rgb(120, 118, 60)], 0.02, (u, v) => smooth(-0.1, 0.35, n1.fbm(u, v, 0.8, 3)));
};

/** Every natural layer, in a fixed order (index = layer number). */
export const NATURALS: { name: string; W: number; gen: Gen; normal: number; aoK: number; aoR: [number, number] }[] = [
  { name: 'wildGrass', W: 3, gen: wildGrass, normal: 0.4, aoK: 25, aoR: [0.01, 0.05] },
  { name: 'forestFloor', W: 3, gen: forestFloor, normal: 0.8, aoK: 40, aoR: [0.01, 0.05] },
  { name: 'rockFace', W: 4, gen: rockFace, normal: 1, aoK: 20, aoR: [0.02, 0.1] },
  { name: 'cliffStrata', W: 6, gen: cliffStrata, normal: 1, aoK: 20, aoR: [0.02, 0.12] },
  { name: 'scree', W: 2, gen: scree, normal: 1, aoK: 50, aoR: [0.01, 0.04] },
  { name: 'snow', W: 4, gen: snow, normal: 0.6, aoK: 10, aoR: [0.03, 0.12] },
  { name: 'sand', W: 3, gen: sand, normal: 0.7, aoK: 20, aoR: [0.01, 0.05] },
  { name: 'mud', W: 3, gen: mud, normal: 0.8, aoK: 30, aoR: [0.01, 0.05] },
  // The kinds of country's own grounds (MasterWorld D55): moor, badlands, karst, downs, a valley's floor.
  { name: 'heather', W: 3, gen: heather, normal: 0.8, aoK: 40, aoR: [0.01, 0.05] },
  { name: 'clay', W: 3, gen: clay, normal: 0.8, aoK: 20, aoR: [0.01, 0.05] },
  { name: 'limestone', W: 4, gen: limestone, normal: 1, aoK: 30, aoR: [0.02, 0.08] },
  { name: 'chalkTurf', W: 2, gen: chalkTurf, normal: 0.5, aoK: 25, aoR: [0.01, 0.04] },
  { name: 'gravel', W: 2, gen: gravel, normal: 1, aoK: 50, aoR: [0.01, 0.04] },
];

