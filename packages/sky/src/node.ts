// @ts-nocheck -- three's TSL typings infer swizzles and vector widths poorly; this file is checked by rendering it (see docs/WEBGPU_PLAN.md).
/**
 * The sky for three's WebGPURenderer: three's SkyMesh (TSL port of `Sky`) with Scale's changes: sun disc
 * and glow, a phased moon, clouds, weather, horizon fog, reversed depth.
 *
 * The uniforms are on `material.uniforms.<name>.value`, as on the GLSL `Sky`.
 */
import * as THREE from 'three/webgpu';
import {
  Fn, float, floor, fract, vec2, vec3, vec4, acos, add, mul, clamp, cos, dot, exp, max, min, mix, modelViewProjection,
  normalize, positionWorld, pow, smoothstep, sub, varyingProperty, uniform, cameraPosition, If, Loop, cross, sqrt, log, select,
  instancedBufferAttribute, pmremTexture, length,
} from 'three/tsl';

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type N = any;

export interface SkyOptions {
  /** The renderer uses a reversed depth buffer (the sky is drawn at z = 0 then). */
  reversed: boolean;
  /** The copy rendered into the environment map: real sun size, full glare, no moon. */
  env?: boolean;
  /** Angular radius of the drawn sun and moon discs, radians (default ~3x the real ones, so they read). */
  sunRadius?: number;
  moonRadius?: number;
  /**
   * A floating origin (a vec3 node, @futuremagic/stage FloatingOrigin's `node`) when the scene is drawn relative to
   * one: the clouds overhead are placed by the camera's world position, so they stay put when it steps.
   */
  origin?: N;
}

const gradient = Fn(([i]: N[]) => {
  const p = fract(i.xyx.mul(vec3(0.1031, 0.1030, 0.0973))).toVar();
  p.addAssign(dot(p, p.yzx.add(33.33)));
  return fract(p.xx.add(p.yz).mul(p.zy)).mul(2.0).sub(1.0);
});
const noise = Fn(([p]: N[]) => {
  const i = floor(p);
  const f = fract(p);
  const u = f.mul(f).mul(f).mul(f.mul(f.mul(6.0).sub(15.0)).add(10.0));
  const a = dot(gradient(i), f);
  const b = dot(gradient(i.add(vec2(1.0, 0.0))), f.sub(vec2(1.0, 0.0)));
  const c = dot(gradient(i.add(vec2(0.0, 1.0))), f.sub(vec2(0.0, 1.0)));
  const d = dot(gradient(i.add(vec2(1.0, 1.0))), f.sub(vec2(1.0, 1.0)));
  return mix(mix(a, b, u.x), mix(c, d, u.x), u.y).mul(1.6);
});
const fbmN = (octaves: number) => Fn(([position, drift]: N[]) => {
  const p = vec2(position).toVar();
  const result = float(0.0).toVar();
  const amplitude = float(1.0).toVar();
  Loop(octaves, () => {
    result.addAssign(amplitude.mul(noise(p)));
    amplitude.mulAssign(0.5);
    p.mulAssign(2.0).addAssign(drift);
  });
  return result;
});
const fbm = fbmN(4);
const fbmShadow = fbmN(3);

/** The cloud layer at sky coordinates `uv`: the noise, its threshold (1 - local cover) and the mask. */
function cloudField(U: N, uv: N, f: N) {
  const evolve = U.time.mul(U.cloudSpeed).mul(300.0);
  const cloudNoise = f(uv.mul(1000.0), evolve).mul(0.7).add(0.5).clamp(0.0, 1.0);
  const region = noise(uv.mul(300.0)).mul(0.37).add(0.5);
  const cov = clamp(U.cloudCoverage.add(region.sub(0.5).mul(0.6)), 0.0, 1.0);
  const threshold = sub(1.0, cov);
  return { cloudNoise, threshold };
}

/** Sky coordinates of the cloud seen in `direction` from `origin` (world, m): the layer lies `cloudHeight` m up. */
function cloudUv(U: N, direction: N, origin: N) {
  const elevation = mix(1.0, 0.1, U.cloudElevation);
  const flat = direction.xz.div(direction.y.max(0.02)).add(origin.xz.div(U.cloudHeight.max(1.0)));
  return flat.div(elevation).mul(U.cloudScale).add(U.time.mul(U.cloudSpeed));
}

/**
 * The clouds' shadow on the land, for a light's `colorNode` (a three Light's colour times this lights every
 * lit material): 1 in the open, down to `1 - strength` under a thick cloud. `U` is the sky's uniforms (the
 * shadows fall where the drawn clouds are once `cloudHeight` is set), `sunDir` the light's unit direction.
 * Three octaves of the sky's four: the finest is lost in a soft shadow anyway.
 */
export function cloudShadow(U: N, position: N, sunDir: N, strength = 0.7): N {
  return Fn(() => {
    const s = normalize(sunDir);
    const { cloudNoise, threshold } = cloudField(U, cloudUv(U, s, position), fbmShadow);
    const depth = max(0.0, cloudNoise.sub(threshold));
    const alpha = sub(1.0, exp(depth.mul(U.cloudDensity).mul(-12.0))).mul(smoothstep(0.02, 0.15, s.y));
    return sub(1.0, alpha.mul(strength).mul(sub(1.0, U.overcast)));
  })();
}

/**
 * Aerial perspective: the colour of the sky toward `direction`, from the sky's environment map (a PMREM
 * of the env copy of the sky), blurred by `blur` (roughness 0..1) so clouds and the sun disc smear into
 * a glow. For a fog colour: distant land then fades into the sky behind it, warm towards the sun, blue
 * away from it. Directions below the horizon look at the horizon.
 */
export function skyToward(envMap: THREE.Texture, direction: N, blur = 0.55): N {
  const d = normalize(vec3(direction.x, max(direction.y, 0.02), direction.z));
  return pmremTexture(envMap, d, float(blur)).rgb;
}

/**
 * The sky's glow while the sun is just below the horizon (sun height -0.18..0.05), where Preetham
 * has gone black: a warm band low toward the sun, a blue that deepens to the zenith, and a faint
 * pink above the shadowed horizon opposite. It fades as the sun sinks and as Preetham takes over.
 */
export function twilight(direction: N, sunDirection: N): N {
  const s = sunDirection.y;
  const glow = smoothstep(-0.18, -0.01, s).mul(sub(1.0, smoothstep(-0.01, 0.06, s)).mul(0.85).add(0.15)).mul(sub(1.0, smoothstep(0.03, 0.1, s)));
  const h = max(direction.y, 0.0);
  const flat = vec2(direction.x, direction.z);
  const sunFlat = vec2(sunDirection.x, sunDirection.z);
  // Clamped: rounding takes it a hair past 0 or 1 straight away from or toward the sun, and WGSL's pow of a
  // negative base is NaN (a dark dotted line down the sky on WebGPU, in the sun's vertical plane).
  const toward = dot(flat.div(max(length(flat), 1e-4)), sunFlat.div(max(length(sunFlat), 1e-4))).mul(0.5).add(0.5).clamp(0.0, 1.0);
  const low = pow(sub(1.0, h), 6.0);
  // The band toward the sun sinks and narrows with it.
  const band = vec3(0.9, 0.38, 0.12).mul(low).mul(pow(toward, 3.0).mul(0.85).add(0.15)).mul(smoothstep(-0.18, -0.02, s));
  const blue = mix(vec3(0.05, 0.08, 0.16), vec3(0.012, 0.03, 0.085), pow(h, 0.6)).mul(smoothstep(-0.2, -0.04, s).add(0.3));
  const belt = vec3(0.12, 0.06, 0.09).mul(pow(sub(1.0, h), 3.0)).mul(pow(sub(1.0, toward), 2.0));
  return band.add(blue).add(belt).mul(glow).mul(0.5).mul(smoothstep(-0.12, 0.0, direction.y));
}

/**
 * The night sky once twilight has gone (sun below about -0.1): not black but a deep blue, lighter
 * toward the horizon and brighter while the moon is up, so hills and roofs stand against it.
 */
export function nightSky(direction: N, sunDirection: N, moonDirection: N): N {
  const dark = sub(1.0, smoothstep(-0.2, -0.06, sunDirection.y));
  const h = max(direction.y, 0.0);
  const base = mix(vec3(0.022, 0.03, 0.055), vec3(0.006, 0.011, 0.03), pow(h, 0.5));
  const moonUp = smoothstep(-0.05, 0.25, moonDirection.y);
  // The moon's own halo: a wide, faint glow round it.
  const halo = vec3(0.05, 0.06, 0.08).mul(pow(max(dot(direction, moonDirection), 0.0), 12.0)).mul(moonUp);
  return base.mul(moonUp.mul(1.2).add(0.6)).add(halo).mul(dark).mul(smoothstep(-0.15, 0.0, direction.y));
}

/** A unit box drawn behind everything; scale it large and keep it on the camera. */
export function makeSkyNode(o: SkyOptions): THREE.Mesh {
  const reversed = o.reversed, env = !!o.env, sunR = o.sunRadius ?? SUN_RADIUS, moonR = o.moonRadius ?? MOON_RADIUS;
  const material = new THREE.NodeMaterial();
  const mesh = new THREE.Mesh(new THREE.BoxGeometry(1, 1, 1), material);
  const U = {
    turbidity: uniform(4), rayleigh: uniform(1.4), mieCoefficient: uniform(0.004), mieDirectionalG: uniform(0.8),
    sunPosition: uniform(new THREE.Vector3()),
    cloudScale: uniform(0.0002), cloudSpeed: uniform(0.00002), cloudCoverage: uniform(0.35), cloudDensity: uniform(0.45), cloudElevation: uniform(0.5),
    // Metres up to the cloud layer: the clouds pass overhead as the camera moves (and cloudShadow matches them); 0 keeps them fixed to the view.
    cloudHeight: uniform(0),
    // The env copy only: its colour's saturation. Preetham's clear sky is a very saturated blue; as the light in the shade it reads too blue.
    envSaturation: uniform(1),
    // The env copy only: how bright it is below the horizon, as a share of the horizon (1 = as the horizon).
    // Where the ground's own bounce is lit apart (a hemisphere light), lower it: else everything is lit from
    // below as brightly as from the sky, and under an overcast sky (no sun) nothing shows a shaded side.
    envGround: uniform(1),
    showSunDisc: uniform(1), time: uniform(0),
    cloudDark: uniform(0), overcast: uniform(0), flash: uniform(0), flashDir: uniform(new THREE.Vector3(0, 0.5, 1)),
    skyFog: uniform(0), fogCol: uniform(new THREE.Color()),
    sunCosR: uniform(Math.cos(env ? 0.0093 : sunR)), moonDir: uniform(new THREE.Vector3(0, -1, 0)), moonSun: uniform(new THREE.Vector3(0, 1, 0)), moonBright: uniform(0),
  };
  (material as unknown as { uniforms: typeof U }).uniforms = U;

  const vSunDirection = varyingProperty('vec3') as N;
  const vSunE = varyingProperty('float') as N;
  const vBetaR = varyingProperty('vec3') as N;
  const vBetaM = varyingProperty('vec3') as N;

  const vertexNode = Fn(() => {
    const e = float(2.718281828459045);
    const totalRayleigh = vec3(5.804542996261093e-6, 1.3562911419845635e-5, 3.0265902468824876e-5);
    const MieConst = vec3(1.8399918514433978e14, 2.7798023919660528e14, 4.0790479543861094e14);
    const cutoffAngle = float(1.6110731556870734);
    const steepness = float(1.5);
    const EE = float(1000.0);
    const sunDirection = normalize(U.sunPosition);
    vSunDirection.assign(sunDirection);
    const zenithAngleCos = clamp(sunDirection.y, -1, 1);
    vSunE.assign(EE.mul(max(0.0, float(1.0).sub(pow(e, cutoffAngle.sub(acos(zenithAngleCos)).div(steepness).negate())))));
    const sunfade = float(1.0).sub(clamp(float(1.0).sub(exp(U.sunPosition.y.div(450000.0))), 0, 1));
    const rayleighCoefficient = U.rayleigh.sub(float(1.0).mul(float(1.0).sub(sunfade)));
    vBetaR.assign(totalRayleigh.mul(rayleighCoefficient));
    const c = float(0.2).mul(U.turbidity).mul(10e-18);
    vBetaM.assign(float(0.434).mul(c).mul(MieConst).mul(U.mieCoefficient));
    const position = modelViewProjection as N;
    // Always at the far plane (z = 0 with a reversed depth buffer).
    if (reversed) position.z.assign(0.0);
    else position.z.assign(position.w);
    return position;
  })();

  const colorNode = Fn(() => {
    const pi = float(3.141592653589793);
    const rayleighZenithLength = float(8.4e3);
    const mieZenithLength = float(1.25e3);
    const THREE_OVER_SIXTEENPI = float(0.05968310365946075);
    const ONE_OVER_FOURPI = float(0.07957747154594767);
    const direction = normalize(positionWorld.sub(cameraPosition)).toVar();
    const zenithAngle = acos(max(0.0, direction.y));
    const inverse = float(1.0).div(cos(zenithAngle).add(float(0.15).mul(pow(float(93.885).sub(zenithAngle.mul(180.0).div(pi)), -1.253))));
    const sR = rayleighZenithLength.mul(inverse);
    const sM = mieZenithLength.mul(inverse);
    const Fex = exp(mul(vBetaR, sR).add(mul(vBetaM, sM)).negate()).toVar();
    const cosTheta = dot(direction, vSunDirection).toVar();
    const cc = cosTheta.mul(0.5).add(0.5);
    const rPhase = THREE_OVER_SIXTEENPI.mul(float(1.0).add(pow(cc, 2.0)));
    const betaRTheta = vBetaR.mul(rPhase);
    const g2 = pow(U.mieDirectionalG, 2.0);
    const inv = float(1.0).div(pow(float(1.0).sub(float(2.0).mul(U.mieDirectionalG).mul(cosTheta)).add(g2), 1.5));
    const mPhase = ONE_OVER_FOURPI.mul(float(1.0).sub(g2)).mul(inv);
    const betaMTheta = vBetaM.mul(mPhase);
    const Lin = pow(vSunE.mul(add(betaRTheta, betaMTheta).div(add(vBetaR, vBetaM))).mul(sub(1.0, Fex)), vec3(1.5)).toVar();
    Lin.mulAssign(mix(vec3(1.0), pow(vSunE.mul(add(betaRTheta, betaMTheta).div(add(vBetaR, vBetaM))).mul(Fex), vec3(1.0 / 2.0)), clamp(pow(sub(1.0, vSunDirection.y), 5.0), 0.0, 1.0)));
    const L0 = vec3(0.1).mul(Fex);

    // Sun disc (sharp, our radius); on screen bright but not blown out, so it keeps its colour.
    const sundisc = smoothstep(U.sunCosR.sub(0.00002), U.sunCosR.add(0.00002), cosTheta).mul(U.showSunDisc);
    const sundiscColor = (env
      ? min(vSunE.mul(Fex), 80.0).mul(760.0).mul(sundisc).mul(sub(1.0, U.overcast))
      : Fex.div(max(max(Fex.r, Fex.g), max(Fex.b, 1e-4))).mul(sundisc).mul(sub(1.0, U.overcast))
        .mul(mix(9.0, 30.0, smoothstep(0.0, 0.35, vSunDirection.y))).mul(smoothstep(0.0, 0.05, vSunE.div(1000.0)))).toVar();

    // The glare around a low sun is compressed on screen (above a soft knee).
    const skyC = add(Lin, L0).mul(0.04).toVar();
    if (!env) {
      const skyL = max(max(skyC.r, skyC.g), skyC.b);
      skyC.assign(select(skyL.greaterThan(1.0), skyC.mul(float(1.0).add(log(skyL)).div(skyL)), skyC));
    }
    const texColor = skyC.add(sundiscColor).add(vec3(0.0, 0.0003, 0.00075)).toVar();
    // A soft glow around the sun.
    const cz = max(cosTheta, 0.0);
    texColor.addAssign(min(vSunE.mul(Fex), 80.0).mul(float(0.05).mul(pow(cz, 6000.0)).add(float(0.003).mul(pow(cz, 400.0))))
      .mul(U.showSunDisc).mul(sub(1.0, U.overcast)).mul(smoothstep(-0.05, 0.02, direction.y)));

    // Twilight: Preetham goes black once the sun is 2 degrees down, but the sky glows on until about 10 degrees.
    const twi = twilight(direction, vSunDirection).toVar();
    texColor.addAssign(twi.mul(sub(1.0, U.overcast.mul(0.6))));
    const night = nightSky(direction, vSunDirection, U.moonDir).toVar();
    texColor.addAssign(night.mul(sub(1.0, U.overcast.mul(0.5))));

    // The moon: a sphere lit from the sun's side (its phase), maria, craters, reddened low down.
    if (!env) {
      const cosM = dot(direction, U.moonDir);
      If(U.moonBright.greaterThan(0.0).and(cosM.greaterThan(Math.cos(moonR * 1.05))), () => {
        const mRight = normalize(cross(U.moonDir, vec3(0.0, 1.0, 0.0)));
        const mUp = cross(mRight, U.moonDir);
        const mp = vec2(dot(direction, mRight), dot(direction, mUp)).div(moonR).toVar();
        const mr2 = dot(mp, mp);
        const mDisc = float(1.0).sub(smoothstep(0.92, 1.0, mr2));
        const mN = mp.x.mul(mRight).add(mp.y.mul(mUp)).sub(sqrt(max(0.0, float(1.0).sub(mr2))).mul(U.moonDir));
        const mLit = smoothstep(-0.04, 0.12, dot(mN, U.moonSun));
        const maria = smoothstep(0.05, 0.45, noise(mp.mul(1.7).add(vec2(3.1, 7.4))).mul(0.7).add(noise(mp.mul(3.9).add(vec2(1.3, 2.9))).mul(0.3)));
        const craters = smoothstep(0.35, 0.7, noise(mp.mul(6.0).add(vec2(5.7, 0.4)))).mul(0.14);
        const mAlb = float(1.0).sub(maria.mul(0.38)).mul(float(1.0).sub(craters));
        const mCol = vec3(0.92, 0.9, 0.85).mul(mAlb).mul(mLit.add(0.006))
          .mul(mix(vec3(1.0, 0.62, 0.38), vec3(1.0), smoothstep(0.0, 0.22, direction.y)));
        texColor.addAssign(mCol.mul(mDisc).mul(U.moonBright).mul(sub(1.0, U.overcast)).mul(smoothstep(-0.01, 0.02, direction.y)));
      });
    }

    If(direction.y.greaterThan(0.0).and(U.cloudCoverage.greaterThan(0.0)), () => {
      const origin = select(U.cloudHeight.greaterThan(0.0), o.origin ? cameraPosition.add(o.origin) : cameraPosition, vec3(0.0));
      const cloudUV = cloudUv(U, direction, origin).toVar();
      const field = cloudField(U, cloudUV, fbm);
      const cloudNoise = field.cloudNoise.toVar();
      const threshold = field.threshold.toVar();
      const cloudMask = smoothstep(threshold, threshold.add(0.3), cloudNoise).toVar();
      const horizonFade = smoothstep(0.0, add(0.03, mul(0.06, U.cloudElevation)), direction.y);
      cloudMask.mulAssign(horizonFade);
      const dayFactor = smoothstep(-0.08, 0.3, vSunDirection.y);
      const sunColor = vSunE.mul(Fex).mul(0.22).mul(0.04).toVar();
      const skyAmbient = Lin.mul(0.04).add(vec3(0.0, 0.0003, 0.00075));
      const depth = max(0.0, cloudNoise.sub(threshold)).toVar();
      const beer = exp(depth.mul(-4.0)).toVar();
      const powder = sub(1.0, beer.mul(beer));
      const shade = mix(0.45, 1.0, beer.mul(powder).mul(2.6).clamp(0.0, 1.0));
      const silver = float(0.51).div(pow(sub(1.49, cosTheta.mul(1.4)), 1.5)).clamp(0.0, 3.0);
      const edge = cloudMask.mul(sub(1.0, cloudMask)).mul(4.0);
      const cloudColor = skyAmbient.add(sunColor.mul(shade)).toVar();
      cloudColor.addAssign(sunColor.mul(silver).mul(edge).mul(0.6));
      cloudColor.mulAssign(dayFactor.max(0.03));
      // After sunset the clouds take the glow from below: warm toward the sun, dim elsewhere.
      cloudColor.addAssign(twi.mul(0.6).add(twilight(vec3(direction.x, 0.0, direction.z).normalize(), vSunDirection).mul(0.5)));
      // At night they are grey shapes lit by the night sky (and the moon), darker than the sky round them.
      cloudColor.addAssign(night.mul(0.8));
      // Weather: darker clouds, lightning lighting them.
      cloudColor.mulAssign(sub(1.0, U.cloudDark.mul(0.72)));
      cloudColor.addAssign(vec3(0.75, 0.8, 1.0).mul(U.flash).mul(add(0.25, pow(max(dot(direction, U.flashDir), 0.0), 8.0).mul(2.5))).mul(3.0));
      const alpha = sub(1.0, exp(depth.mul(U.cloudDensity).mul(-12.0))).mul(horizonFade).toVar();
      texColor.subAssign(L0.mul(0.04).mul(alpha));
      const cloudAerial = mix(texColor, cloudColor, Fex);
      texColor.assign(mix(texColor, cloudAerial, alpha));
    });

    // Overcast (grey, no blue), lightning, fog towards the horizon (everywhere in thick fog).
    const skyLum = dot(texColor, vec3(0.2126, 0.7152, 0.0722));
    texColor.assign(mix(texColor, vec3(skyLum).mul(sub(0.72, U.cloudDark.mul(0.4))), U.overcast));
    texColor.addAssign(vec3(0.7, 0.75, 0.9).mul(U.flash).mul(0.5).mul(add(0.3, pow(max(dot(direction, U.flashDir), 0.0), 4.0))));
    const hz = sub(1.0, smoothstep(-0.02, 0.4, direction.y));
    texColor.assign(mix(texColor, U.fogCol, clamp(U.skyFog.mul(mix(hz, 1.0, U.skyFog.mul(U.skyFog))), 0.0, 1.0)));
    if (env) {
      const lum = dot(texColor, vec3(0.2126, 0.7152, 0.0722));
      texColor.assign(mix(vec3(lum), texColor, U.envSaturation));
      texColor.mulAssign(mix(U.envGround, 1.0, smoothstep(-0.25, 0.0, direction.y)));
    }
    return vec4(texColor, 1.0);
  })();

  material.side = THREE.BackSide;
  material.depthWrite = false;
  material.fog = false;
  material.vertexNode = vertexNode;
  material.colorNode = colorNode;
  return mesh;
}

/** Angular radius of the drawn sun and moon discs (~3x the real ones, so they read on screen). */
export const SUN_RADIUS = 0.026;
export const MOON_RADIUS = 0.024;

/**
 * The star field: WebGPU draws points one pixel wide, so the stars are instanced
 * sprites of `size` pixels; the moon's disc hides the stars behind it. `opacity` is set by the
 * sky each frame, as on the PointsMaterial.
 */
export function makeStarsNode(pos: Float32Array, col: Float32Array, size: number, moonDir: { value: THREE.Vector3 }, moonCos: number): THREE.Sprite {
  const mat = new THREE.PointsNodeMaterial({ transparent: true, opacity: 0, depthWrite: false, fog: false, sizeAttenuation: false });
  const P = instancedBufferAttribute(new THREE.InstancedBufferAttribute(pos, 3), 'vec3');
  const C = instancedBufferAttribute(new THREE.InstancedBufferAttribute(col, 3), 'vec3');
  const hidden = dot(normalize(P), (moonDir as N).isNode ? moonDir : uniform(moonDir.value)).greaterThan(moonCos);
  mat.positionNode = P;
  mat.sizeNode = select(hidden, 0.0, size);
  mat.colorNode = C;
  const s = new THREE.Sprite(mat);
  s.count = pos.length / 3;
  return s;
}
