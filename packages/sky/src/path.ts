/**
 * Where the sun and moon stand, and what light they give: pure numbers, no three.js, so games and tests
 * share them. From Scale's SkySystem.
 */
import { clamp, lerp, smoothstep, Rng } from '@futuremagic/core';

export type Vec3 = [number, number, number];

/** Days from one new moon to the next. */
export const SYNODIC = 29.53;

/**
 * Unit direction to the sun at `hour` (0..24) on a path like ~45°N around the equinox: up at 6, highest at
 * noon in the south (+z), down at 18. The moon uses it too, shifted by its phase.
 */
export function skyPath(hour: number, out: Vec3 = [0, 0, 0]): Vec3 {
  const t = ((hour - 6) / 24) * Math.PI * 2;
  const elev = Math.sin(t) * 0.8;
  const az = t + 0.4;
  const x = Math.cos(az) * Math.cos(elev), y = Math.sin(elev), z = Math.sin(az) * Math.cos(elev) * 0.6 + 0.35;
  const l = Math.hypot(x, y, z);
  out[0] = x / l; out[1] = y / l; out[2] = z / l;
  return out;
}

/** Lunar phase 0..1 (0 new, 0.5 full) at an absolute time in hours; `offset` shifts the cycle. */
export function moonPhase(hoursAbs: number, offset = 0.3): number {
  const p = (hoursAbs / 24 / SYNODIC + offset) % 1;
  return p < 0 ? p + 1 : p;
}

export interface Moon {
  dir: Vec3;
  /** Direction the sunlight falls on the moon from (sets the phase the disc shows). */
  sunSide: Vec3;
  /** Lit fraction of the disc, 0 new .. 1 full. */
  lit: number;
}

/** The moon at `hour` of a day `hoursAbs` into the game: it runs the sun's path, lagging by its phase. */
export function moonAt(hour: number, hoursAbs: number, sun: Vec3): Moon {
  const phase = moonPhase(hoursAbs);
  const dir = skyPath(hour - phase * 24);
  const pa = phase * Math.PI * 2;
  const d = sun[0] * dir[0] + sun[1] * dir[1] + sun[2] * dir[2];
  let px = sun[0] - dir[0] * d, py = sun[1] - dir[1] * d, pz = sun[2] - dir[2] * d;
  if (px * px + py * py + pz * pz < 1e-6) { px = -dir[0] * dir[1]; py = 1 - dir[1] * dir[1]; pz = -dir[2] * dir[1]; }
  const pl = Math.hypot(px, py, pz) || 1;
  const c = Math.cos(pa), s = Math.sin(pa) * (pa > Math.PI ? -1 : 1);
  return {
    dir,
    sunSide: [dir[0] * c + (px / pl) * s, dir[1] * c + (py / pl) * s, dir[2] * c + (pz / pl) * s],
    lit: (1 - Math.cos(pa)) / 2,
  };
}

/** Weather as the sky sees it. */
export interface SkyWeather {
  /** Cloud cover 0..1. */
  cover: number;
  /** Cloud opacity. */
  density: number;
  /** Storm darkness 0..1. */
  dark: number;
  /** Direct sun left, 0..1. */
  sun: number;
  /** Fog 0..1. */
  fog: number;
  /** Rain 0..1. */
  rain: number;
}

export const CLEAR: SkyWeather = { cover: 0.35, density: 0.45, dark: 0, sun: 1, fog: 0, rain: 0 };

/** The lighting a sky gives at one moment (Scale's light rig, as numbers). */
export interface SkyLight {
  /** 0 night .. 1 day, 0..1 golden hour, 0..1 night. */
  day: number;
  golden: number;
  night: number;
  /** Direction the key light comes from (sun by day, moon or high sky glow by night). */
  lightDir: Vec3;
  lightColor: Vec3;
  lightIntensity: number;
  skyColor: Vec3;
  groundColor: Vec3;
  hemiIntensity: number;
  /** Fog colour (the horizon) and exponential fog density per metre. */
  fogColor: Vec3;
  fogDensity: number;
  /** Tone mapping exposure. */
  exposure: number;
  /** scene.environmentIntensity for the sky's environment map. */
  envIntensity: number;
  /** Sky shader weather uniforms. */
  overcast: number;
  skyFog: number;
  /** Star opacity. */
  stars: number;
  /** Moon disc brightness. */
  moonBright: number;
}

export function skyLight(sun: Vec3, moon: Moon, wx: SkyWeather = CLEAR): SkyLight {
  const sunUp = sun[1];
  const day = smoothstep(-0.12, 0.15, sunUp);
  const night = 1 - smoothstep(-0.2, 0.02, sunUp);
  const golden = smoothstep(0.35, 0.02, sunUp) * day;
  const overcast = smoothstep(0.55, 1, wx.cover) * 0.9;
  const skyFog = clamp(wx.fog * 1.1 + wx.rain * 0.25, 0, 1);
  const moonUp = smoothstep(-0.03, 0.2, moon.dir[1]);
  let lightDir: Vec3, lightColor: Vec3, lightIntensity: number;
  if (sunUp > -0.05) {
    lightDir = [sun[0], sun[1], sun[2]];
    lightColor = [1, lerp(0.95, 0.62, golden), lerp(0.9, 0.42, golden)];
    lightIntensity = 3.2 * smoothstep(-0.05, 0.12, sunUp) * wx.sun;
  } else {
    // At night: the moon while it is up, else a faint glow from high overhead.
    const nx = moon.dir[0] * 0.5, nz = moon.dir[2] * 0.5, nl = Math.hypot(nx, 1, nz);
    const d: Vec3 = [lerp(nx / nl, moon.dir[0], moonUp), lerp(1 / nl, moon.dir[1], moonUp), lerp(nz / nl, moon.dir[2], moonUp)];
    const l = Math.hypot(d[0], d[1], d[2]) || 1;
    lightDir = [d[0] / l, d[1] / l, d[2] / l];
    lightColor = [0.55, 0.65, 0.9];
    lightIntensity = 0.25 * night * wx.sun * (0.45 + 0.75 * moon.lit * moonUp);
  }
  const dull = 1 - wx.sun;
  const hemiIntensity = lerp(0.06, 0.75, day) * (1 + 0.35 * dull) * (1 - 0.4 * wx.dark);
  let sky: Vec3 = [lerp(0.25, 0.75, day), lerp(0.3, 0.84, day), lerp(0.5, 1.0, day)];
  const grey = (sky[0] + sky[1] + sky[2]) / 3;
  sky = sky.map((c) => lerp(c, grey, dull * 0.75)) as Vec3;
  const ground: Vec3 = [lerp(0.06, 0.38, day), lerp(0.06, 0.34, day), lerp(0.08, 0.28, day)];
  let fog: Vec3 = [lerp(0.03, 0.72, day) + golden * 0.15, lerp(0.04, 0.8, day) + golden * 0.05, lerp(0.07, 0.9, day) - golden * 0.1];
  const g = lerp(0.035, 0.66 * (1 - 0.6 * wx.dark), day);
  const gw = Math.max(overcast, Math.min(1, wx.fog * 1.3));
  fog = [lerp(fog[0], g * 0.96, gw), lerp(fog[1], g, gw), lerp(fog[2], g * 1.03, gw)];
  return {
    day, golden, night, lightDir, lightColor, lightIntensity,
    skyColor: sky, groundColor: ground, hemiIntensity,
    fogColor: fog,
    fogDensity: 0.00012 + 0.0062 * Math.pow(wx.fog, 2.2) + 0.0011 * wx.rain,
    exposure: lerp(1.6, 0.55, day) * (1 + 0.45 * dull * day) * (1 - 0.45 * wx.dark * day),
    envIntensity: lerp(0.05, 0.22, day) * (1 - 0.3 * wx.dark),
    overcast, skyFog,
    stars: night * (1 - smoothstep(0.4, 0.85, wx.cover)) * (1 - skyFog),
    moonBright: lerp(1.5, 0.3, day),
  };
}

/** Star positions (on a dome of `radius`, upper half) and colours, from a seed. */
export function starField(seed: number, n = 4000, radius = 40000): { position: Float32Array; color: Float32Array } {
  const rng = new Rng(seed);
  const position = new Float32Array(n * 3), color = new Float32Array(n * 3);
  for (let i = 0; i < n; i++) {
    const u = rng.float() * 2 - 1, a = rng.float() * Math.PI * 2, r = Math.sqrt(1 - u * u);
    position.set([Math.cos(a) * r * radius, Math.abs(u) * radius, Math.sin(a) * r * radius], i * 3);
    const b = 0.4 + rng.float() * 0.6;
    color.set([b, b * (0.9 + rng.float() * 0.1), b * (0.85 + rng.float() * 0.2)], i * 3);
  }
  return { position, color };
}
