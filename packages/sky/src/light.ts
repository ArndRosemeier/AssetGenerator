/**
 * The light rig for physical albedos, as numbers (no three.js): how strong the sun, the sky's fill and the ground's
 * bounce are once `skyLight` has said what the sky gives, and how the eye adapts. `./rig` (SkyRig) puts them on a
 * scene's lights; tests and workers can read them here. Tuned in MasterWorld (src/render/sky.ts), shared with Nauta.
 */
import type { SkyLight, Vec3 } from './path';

/**
 * The gain on the light rig: `skyLight` is Scale's rig, tuned for its bright city materials; physical albedos
 * (earth, wood, stone at 0.1 to 0.4) are darker, so the lights are stronger, while the exposure (and so the
 * sky) stays Scale's.
 */
export const RIG_GAIN = 3.4;
/** The environment (sky) light on everything lit, and in reflections, on top of `skyLight`'s envIntensity. */
export const ENV_GAIN = 2.4;
/**
 * The env map below the horizon, as a share of the horizon: the ground gives back about a fifth of the sky (the
 * rest of its bounce is the hemisphere light). At 1 everything was lit from below as from the sky, and under
 * clouds a head or a hood showed no shaded side at all.
 */
export const ENV_GROUND = 0.25;
/**
 * The sky's light in the shade is its environment map; Preetham's clear sky is too saturated a blue for that, so
 * the env copy is drawn with this much of its colour. Whatever shows the env map as a picture (a mirror, the
 * fog's colour) puts it back (`fullSky` in `./rig`).
 */
export const ENV_SATURATION = 0.6;
/** Exposure on top of the sky's own (the tone curve's gain times this; a game multiplies its own on top). */
export const RIG_EXPOSURE = 1.15;
/** How much of the low sun's dimming by the air the eye adapts away (0 none, 1 all), and the most it lifts it. */
export const SUN_ADAPT = 0.6;
export const SUN_ADAPT_MAX = 2.5;
/** The dimmest the sun's light counts as for that (luminance), so a sun at the horizon is not lifted without end. */
const SUN_ADAPT_FLOOR = 0.05;
/** How fast the eye adapts to a change of light, per second (about a second from a cave out into the day). */
export const EYE_ADAPT = 3;
/** Luminance of linear Rec. 709 red, green and blue. */
const LUMA: Vec3 = [0.2126, 0.7152, 0.0722];

/**
 * The sky's light falls with the sun about as fast as the sun's own (Preetham), so a low sun would leave the shade
 * nearly black; real skies keep more (the share of diffuse light rises as the sun sinks). The env map's strength
 * is raised by the square root of how much its irradiance fell from midday, at most 3x. Irradiance of the sky
 * (luminance, up-facing) by sun height, integrated from the sky shader offline.
 */
const SKY_E: readonly (readonly [number, number])[] = [[0, 0.079], [0.03, 0.221], [0.06, 0.428], [0.1, 0.78], [0.15, 1.287], [0.2, 1.797], [0.3, 2.643], [0.4, 3.239], [0.5, 3.757], [0.6, 4.374], [0.7, 5.175]];
/** The most the low sun's sky is raised. */
const LOW_SUN_MAX = 3;

/** How much brighter the sky's fill is under a sun `sunUp` high (sin of its elevation) than its own fall would leave it. */
export function lowSunSky(sunUp: number): number {
  const top = SKY_E[SKY_E.length - 1]!;
  const up = Math.min(Math.max(sunUp, 0), top[0]);
  let i = 1;
  while (i < SKY_E.length - 1 && SKY_E[i]![0] < up) i++;
  const [a, ea] = SKY_E[i - 1]!, [b, eb] = SKY_E[i]!;
  const e = ea + ((eb - ea) * (up - a)) / (b - a);
  return Math.min(LOW_SUN_MAX, Math.sqrt(top[1] / e));
}

/** The sun's (or moon's) light strength: the air dims the low sun a lot; the eye adapts, so only part of that shows (the colour stays). */
export function adaptedSun(L: SkyLight, gain = RIG_GAIN): number {
  const c = L.lightColor, lum = Math.max(SUN_ADAPT_FLOOR, LUMA[0] * c[0] + LUMA[1] * c[1] + LUMA[2] * c[2]);
  return L.lightIntensity * gain * Math.min(lum ** -SUN_ADAPT, SUN_ADAPT_MAX);
}

/** Lightning's light from the whole sky at full flash, and its colour (r, g, b). */
const FLASH_FILL = 0.84;
const FLASH_COLOR: Vec3 = [0.75, 0.8, 1];
/** The dim sky's own fill from dusk on (r, g, b; without it the shade under the moon is black), and how much an overcast takes of it. */
const DUSK_FILL: Vec3 = [0.05, 0.06, 0.09];
const DUSK_OVERCAST = 0.5;

/**
 * The hemisphere light's sky colour. The hemisphere light is mostly the light thrown back by the sunlit ground
 * (from below, `L.bounce`); the sky's own light comes from the environment map. Only from dusk on, when the dim sky
 * is most of the light, and while lightning lights the land from the whole sky (`flash` 0..1), does it add some.
 */
export function skyFill(L: SkyLight, flash: number, out: Vec3 = [0, 0, 0]): Vec3 {
  const f = flash * FLASH_FILL, dusk = (1 - L.day) * (1 - DUSK_OVERCAST * L.overcast);
  for (let i = 0; i < 3; i++) out[i] = FLASH_COLOR[i]! * f + DUSK_FILL[i]! * dusk;
  return out;
}

/** The eye's exposure `seen` a step `dt` (seconds) on toward `want`; at once on the first frame (`seen` < 0) or with no time passed. */
export function eyeAdapt(seen: number, want: number, dt: number): number {
  return seen < 0 || dt === 0 ? want : seen + (want - seen) * Math.min(1, dt * EYE_ADAPT);
}
