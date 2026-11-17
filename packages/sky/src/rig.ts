/**
 * The light rig: one sky lighting a scene of physical albedos through the day, shared by the games (MasterWorld,
 * Nauta). It owns the dome and the stars, the sky's environment map (the sky as the fill light in the shade), and
 * the sun (or moon) and hemisphere lights a game made: the sun's colour and strength with the eye's adaptation to a
 * low sun, the clouds' shadows on everything it lights, the brighter sky under a low sun, the ground's bounce, the
 * exposure and its easing as the light changes, and the colour grade over the day. The numbers are in `./light`.
 *
 * What a game adds of its own (rooms, caves, windows, fog, shadows) goes in a subclass's `local`, which runs once
 * the open sky's light is set and before the eye adapts. Everything that changes a shader's key (the environment
 * map, the sun's colour node) is set up in the constructor: make the rig before the Stage's warm-up, and call
 * `update` once before it too.
 */
import { BoxGeometry, Color, Mesh, PMREMGenerator, Scene, Vector3, type DirectionalLight, type HemisphereLight, type Material, type Node, type PerspectiveCamera, type RenderTarget, type Sprite, type WebGPURenderer } from 'three/webgpu';
import { dot, mix, positionWorld, renderGroup, uniform, vec3 } from 'three/tsl';
import { GRADE, gradeAt, type GradeKey } from '@futuremagic/stage';
import { CLEAR, moonAt, skyLight, skyPath, starField, type SkyLight, type SkyWeather, type Vec3 } from './path';
import { ENV_GAIN, ENV_GROUND, ENV_SATURATION, RIG_EXPOSURE, RIG_GAIN, adaptedSun, eyeAdapt, lowSunSky, skyFill } from './light';
import { MOON_RADIUS, cloudShadow, makeSkyNode, makeStarsNode } from './node';

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export type SkyUniforms = Record<string, { value: any }>;
/** The uniforms of a sky made by `makeSkyNode` (`uniforms.<name>.value`, as on three's GLSL `Sky`). */
export const skyUniforms = (m: Material): SkyUniforms => (m as unknown as { uniforms: SkyUniforms }).uniforms;

/** A colour read from the sky's environment map with its full colour back (see ENV_SATURATION): for a mirror or the fog. */
export const fullSky = (c: Node): Node => {
  const luma = dot(c as never, vec3(0.2126, 0.7152, 0.0722));
  return mix(vec3(luma), c as never, 1 / ENV_SATURATION).max(0) as unknown as Node;
};

/** Hours in a day, and seconds in a minute (the clock). */
const HOURS = 24;
const MINUTE = 60;
/** The dome's size, metres: beyond everything drawn, inside the camera's far plane. */
const DOME_SIZE = 100000;
/** Drawn first, the stars right after: behind everything else. */
const DOME_ORDER = -1000;
/** A star's size on screen, pixels; stars this much wider than the moon's disc around it are hidden by its glare. */
const STAR_SIZE = 2;
const MOON_HIDES = 1.15;
/** The env copy of the sky: its box's size and the cube camera's near and far planes (metres). */
const ENV_BOX = 1000;
const ENV_NEAR = 1;
const ENV_FAR = 2000;
/** The environment map is drawn again when the sun moved this far (unit vector), or the weather by one step of 1/ENV_WEATHER_STEPS. */
const ENV_SUN_MOVE = 0.02;
const ENV_WEATHER_STEPS = 25;
/** Lightning's direction: how much of it is across the sky and how much up. */
const FLASH_ACROSS = 0.8;
const FLASH_UP = 0.5;

export interface SkyRigOptions {
  /** The dome's material, made from the game's own material kind (so the game's warm-up compiles it). */
  readonly dome: Material;
  /** Hours 0..24 at the start, and real minutes a game day takes (0 stops the clock). */
  readonly hour: number;
  readonly dayMinutes: number;
  /** The star field's seed (the same stars every night). */
  readonly starSeed: number;
  /** Metres up to the clouds: they pass overhead as the camera travels, and their shadows fall where they are (0: fixed to the view). */
  readonly cloudHeight?: number;
  /** The game's exposure on top of the rig's (its tone curve's need: AgX wants more than ACES for the same mid-grey). */
  readonly exposure?: number;
  /** The env map below the horizon as a share of the horizon (default ENV_GROUND). */
  readonly envGround?: number;
  /** Where a lit point is in the world, for the clouds' shadows (a floating origin's world position; default `positionWorld`). */
  readonly world?: Node;
  /** A further shade on the sun's light (MasterWorld: the hills' shadows beyond the shadow map). */
  readonly shade?: Node;
}

export class SkyRig {
  /** Hours 0..24, and whole days since the start. */
  hour: number;
  day = 0;
  /** Real minutes per game day; 0 stops the clock. */
  dayMinutes: number;
  /** How many times faster than its day length the clock runs now (time compressed). */
  pace = 1;
  weather: SkyWeather = { ...CLEAR };
  /** Toward the sun. */
  readonly sunDir: Vec3 = [0, 1, 0];
  /** The light of the last update (water and weather read it). */
  light!: SkyLight;
  /** The multiplier the scene's lights carry on `skyLight`'s rig (RIG_GAIN). */
  readonly gain = RIG_GAIN;
  /** Lightning 0..1 and the bearing it lights the clouds from (radians). */
  flash = 0;
  flashBearing = 0;
  /** The setting's colour key over the day (empty: the grade stays as the game set it). */
  look: readonly GradeKey[] = [];
  /** How far the eye is in a lamp-lit room, 0..1: the grade moves to the day's key there (the lamp, not the night outside, sets the colour). */
  inside = 0;
  /** The dome; it goes in with `stage.add` after the warm-up has compiled its kind (drawing it before would build it on the spot). */
  readonly dome: Mesh;
  /** The star field (its opacity follows the night and the cloud cover). */
  protected readonly stars: Sprite;
  protected readonly U: SkyUniforms;
  protected readonly envU: SkyUniforms;
  /** Exposure on top of the sky's own (the rig's times the game's). */
  protected readonly exposure: number;
  /** The sun's (or moon's) colour times its strength, and where it comes from: the sun's colour node reads them. */
  protected readonly sunLight = uniform(new Color()).setGroup(renderGroup);
  private readonly lightDir = uniform(new Vector3(0, 1, 0)).setGroup(renderGroup);
  private readonly envScene = new Scene();
  private readonly pmrem: PMREMGenerator;
  private readonly envRT: RenderTarget;
  private readonly lastEnvSun: Vec3 = [0, -2, 0];
  /** The weather the environment map was last drawn with. */
  private lastEnvWx = '';
  private time = 0;
  /** The eye's exposure, eased (from a dark place out into the day and back, the eye adapts over a moment). */
  private seen = -1;
  private readonly fill: Vec3 = [0, 0, 0];

  constructor(
    protected readonly renderer: WebGPURenderer,
    protected readonly scene: Scene,
    protected readonly sun: DirectionalLight,
    protected readonly hemi: HemisphereLight,
    o: SkyRigOptions,
  ) {
    this.exposure = RIG_EXPOSURE * (o.exposure ?? 1);
    this.hour = o.hour;
    this.dayMinutes = o.dayMinutes;
    this.dome = new Mesh(new BoxGeometry(1, 1, 1), o.dome);
    this.dome.name = 'sky';
    this.dome.scale.setScalar(DOME_SIZE);
    this.dome.renderOrder = DOME_ORDER;
    this.dome.frustumCulled = false;
    this.U = skyUniforms(o.dome);
    this.U.cloudHeight.value = o.cloudHeight ?? 0;
    scene.background = null;
    // The stars: a seeded field on a dome inside the sky box, faded in at night (and hidden behind the moon).
    const field = starField(o.starSeed);
    this.stars = makeStarsNode(field.position, field.color, STAR_SIZE, this.U.moonDir, Math.cos(MOON_RADIUS * MOON_HIDES));
    this.stars.name = 'stars';
    this.stars.renderOrder = DOME_ORDER + 1;
    this.stars.frustumCulled = false;
    scene.add(this.stars);

    const envSky = makeSkyNode({ reversed: false, env: true });
    envSky.name = 'env sky';
    envSky.scale.setScalar(ENV_BOX);
    this.envU = skyUniforms(envSky.material as Material);
    this.envU.envSaturation.value = ENV_SATURATION;
    // The hemisphere light throws the ground's bounce up: the env map below the horizon is only a little of it.
    this.envU.envGround.value = o.envGround ?? ENV_GROUND;
    this.envScene.add(envSky);
    this.pmrem = new PMREMGenerator(renderer);
    // An environment map from the start: it is part of every lit shader's key. Later refreshes (the first in
    // `update`, once the sky's uniforms are set) render into the same target, so no shader is built again.
    // It is the only light from the sky: shade facing the bright horizon or the sun's side of the sky is lighter.
    this.envRT = this.pmrem.fromScene(this.envScene, 0, ENV_NEAR, ENV_FAR);
    scene.environment = this.envRT.texture;
    // The clouds' shadows on everything the sun lights (three takes a light's colorNode in place of its colour).
    const lit = this.sunLight.mul(cloudShadow(this.U, o.world ?? positionWorld, this.lightDir));
    (sun as unknown as { colorNode: unknown }).colorNode = o.shade ? lit.mul(o.shade as never) : lit;
  }

  /** The sky's environment map (reflections, the fog's colour). */
  get envTexture() { return this.envRT.texture; }
  /** Toward the sun (or the moon at night), as lit last frame. */
  get lightDirection(): Vector3 { return this.lightDir.value; }
  /** The sun's light as it falls outside: its colour times its strength (the moon's at night: check `sunDir` for that). */
  get sunColor(): Color { return this.sunLight.value; }

  /** Once per frame. `camera` null: only the light (before the warm-up). */
  update(dt: number, camera: PerspectiveCamera | null): void {
    if (this.dayMinutes > 0) {
      this.hour += (dt / MINUTE / this.dayMinutes) * HOURS * this.pace;
      if (this.hour >= HOURS) { this.hour -= HOURS; this.day++; }
    }
    this.time += dt;
    const sun = skyPath(this.hour, this.sunDir);
    const moon = moonAt(this.hour, this.day * HOURS + this.hour, sun);
    const L = skyLight(sun, moon, this.weather), wx = this.weather;
    this.light = L;
    for (const U of [this.U, this.envU]) {
      U.sunPosition.value.set(sun[0], sun[1], sun[2]);
      U.cloudCoverage.value = wx.cover; U.cloudDensity.value = wx.density; U.cloudDark.value = wx.dark;
      U.overcast.value = L.overcast; U.skyFog.value = L.skyFog;
      U.fogCol.value.setRGB(...L.fogColor);
    }
    this.U.moonDir.value.set(...moon.dir);
    this.U.moonSun.value.set(...moon.sunSide);
    this.U.moonBright.value = L.moonBright;
    this.envU.moonDir.value.set(...moon.dir);
    (this.stars.material as { opacity: number }).opacity = L.stars;
    this.U.time.value = this.time;
    this.U.flash.value = this.flash;
    this.U.flashDir.value.set(Math.cos(this.flashBearing) * FLASH_ACROSS, FLASH_UP, Math.sin(this.flashBearing) * FLASH_ACROSS);

    this.sun.color.setRGB(...L.lightColor);
    this.sun.intensity = adaptedSun(L, this.gain);
    this.hemi.color.setRGB(...skyFill(L, this.flash, this.fill));
    this.hemi.groundColor.setRGB(...L.bounce);
    this.hemi.intensity = this.gain;
    this.scene.environmentIntensity = L.envIntensity * ENV_GAIN * lowSunSky(sun[1]);
    this.renderer.toneMappingExposure = L.exposure * this.exposure;
    if (this.look.length) {
      const g = gradeAt(this.look, this.inside >= 1 ? 1 : sun[1] + (1 - sun[1]) * this.inside);
      GRADE.slope.value.set(...g.slope);
      GRADE.saturation.value = g.saturation;
    }
    this.sunLight.value.copy(this.sun.color).multiplyScalar(this.sun.intensity);
    this.local(dt, L);
    // The eye adapts over a moment when the light changes much (out of a cave into the day); at once on the first frame.
    this.seen = eyeAdapt(this.seen, this.renderer.toneMappingExposure, dt);
    this.renderer.toneMappingExposure = this.seen;
    this.lightDir.value.set(...L.lightDir);
    if (camera) { this.dome.position.copy(camera.position); this.stars.position.copy(camera.position); }

    // The environment map when the sun moved or the weather changed noticeably.
    const l = this.lastEnvSun;
    const wxKey = [wx.cover, wx.dark, wx.fog, wx.sun].map((v) => Math.round(v * ENV_WEATHER_STEPS)).join();
    if (Math.hypot(l[0] - sun[0], l[1] - sun[1], l[2] - sun[2]) > ENV_SUN_MOVE || wxKey !== this.lastEnvWx) {
      l[0] = sun[0]; l[1] = sun[1]; l[2] = sun[2];
      this.lastEnvWx = wxKey;
      this.pmrem.fromScene(this.envScene, 0, ENV_NEAR, ENV_FAR, { renderTarget: this.envRT } as never);
    }
  }

  /**
   * The game's own light, after the open sky's is set and before the eye adapts: below ground, in a room, under
   * water. It may change the lights, the environment's strength and `renderer.toneMappingExposure` (what the eye
   * adapts to). Nothing by default.
   */
  protected local(_dt: number, _light: SkyLight): void {}
}
