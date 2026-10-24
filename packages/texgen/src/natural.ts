/**
 * Natural ground layers for open country (wild grass, forest floor, rock, cliff strata, scree, snow, sand,
 * mud): the terrain of fantasy and wilderness games. Same conventions as the other layers (index.ts): one
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
    const k = 0.75 + nS.fbm(u, v, 0.08, 3) * 0.3 + (rnd(5104, idx) - 0.5) * 0.25;
    t.set(idx, 0.17 * k, 0.14 * k, 0.08 * k, 0.95, nS.fbm(u, v, 0.15, 3) * 0.004);
  });
  const rng = new Rng(5105);
  // Tufts: blades fanning out from a root, so the grass reads as clumps, not as fur.
  const tufts = Math.round((W * W) / 0.0012);
  for (let k = 0; k < tufts; k++) {
    const x = rng.float() * W, y = rng.float() * W, u = x / W, v = y / W;
    if (rng.float() > 0.8 + 0.4 * nC.fbm(u, v, 0.4, 3)) continue;
    const dry = smooth(0.1, 0.6, nD.fbm(u, v, 1.5, 4) + nD.fbm(u, v, 0.2, 2) * 0.3);
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
    t.set(idx, 0.16 * k, 0.11 * k, 0.07 * k, 0.9, nS.fbm(u, v, 0.4, 3) * 0.01);
  });
  const rng = new Rng(5204);
  const leafColours: RGB[] = [rgb(120, 70, 30), rgb(150, 95, 40), rgb(95, 60, 32), rgb(170, 120, 55), rgb(80, 55, 35)];
  const leaves = Math.round((W * W) / 0.0016);
  for (let k = 0; k < leaves; k++) {
    const cx = rng.float() * W, cy = rng.float() * W;
    const a = rng.range(0.012, 0.028), b = a * rng.range(0.4, 0.6), th = rng.float() * Math.PI;
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
    const m = smooth(0.25, 0.45, nM.fbm(u, v, 0.6, 4));
    if (m <= 0) return;
    const k = 0.8 + nM.fbm(u, v, 0.01, 2) * 0.3;
    t.r[idx] = mix(t.r[idx], 0.16 * k, m); t.g[idx] = mix(t.g[idx], 0.27 * k, m); t.b[idx] = mix(t.b[idx], 0.07 * k, m);
    t.rough[idx] = mix(t.rough[idx], 0.95, m);
    t.h[idx] = Math.max(t.h[idx], 0.012 + m * 0.01 + nM.fbm(u, v, 0.008, 2) * 0.002);
  });
};

interface RockOpts { seed: number; base: RGB; warm: RGB; lichen: number; strata: number; }

/** Weathered rock: fractured plates, ridged relief, warm stains, lichen; `strata` adds horizontal bands. */
function rock(t: Tex, o: RockOpts): void {
  const W = t.W;
  const n1 = new TNoise(o.seed + 1, W), n2 = new TNoise(o.seed + 2, W), n3 = new TNoise(o.seed + 3, W);
  const cell = newCell(), f = Math.max(2, Math.round(W / 0.9));
  t.each((u, v, _x, _y, idx) => {
    worley(o.seed + 4, u * f + n1.fbm(u, v, 1.2, 3) * 0.6, v * f + n1.fbm(u + 0.5, v, 1.2, 3) * 0.6, f, f, 1, cell, true);
    const crack = (1 - smooth(0.0, 0.025, cell.edge)) * 0.6;
    const plate = ((cell.id & 255) / 255 - 0.5) * 0.05;
    const band = o.strata > 0 ? Math.sin(v * Math.PI * 2 * Math.round(W / 0.45) + n2.fbm(u, v, 1.2, 3) * 3) * 0.5 + 0.5 : 0;
    let h = n2.ridged(u, v, 1.6, 5) * 0.12 + n3.fbm(u, v, 0.15, 3) * 0.015 + plate - crack * 0.04 + band * o.strata * 0.05;
    const tone = 1 + n1.fbm(u, v, 0.7, 4) * 0.18 + plate * 2 + (rnd(o.seed + 5, idx) - 0.5) * 0.12 + band * o.strata * 0.18;
    const warm = smooth(0.0, 0.6, n3.fbm(u, v, 1.5, 3));
    let r = mix(o.base[0], o.warm[0], warm) * tone, g = mix(o.base[1], o.warm[1], warm) * tone, b = mix(o.base[2], o.warm[2], warm) * tone;
    r *= 1 - crack * 0.5; g *= 1 - crack * 0.5; b *= 1 - crack * 0.5;
    // Lichen: pale grey-green and orange crusts on the exposed tops.
    const li = smooth(0.35, 0.55, n2.fbm(u + 0.3, v, 0.35, 4)) * o.lichen * smooth(0.03, 0.08, h);
    if (li > 0) {
      const orange = rnd(o.seed + 6, cell.id) < 0.3;
      r = mix(r, orange ? 0.62 : 0.55, li); g = mix(g, orange ? 0.40 : 0.58, li); b = mix(b, orange ? 0.15 : 0.45, li);
      h += li * 0.002;
    }
    t.set(idx, r, g, b, 0.82 - crack * 0.1, h);
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
];

