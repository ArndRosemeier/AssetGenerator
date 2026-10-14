/**
 * Realistic procedural skin (the node graph is in nodes/people.ts):
 *
 *  - Albedo is computed in the shader from the appearance (tone, regional variation from
 *    per-vertex masks: lips, blush, eye sockets, nose, ears, nails), painted features in face
 *    coordinates (eyebrows, stubble, shaved scalp, scars, warpaint, tattoos), age blotches and the
 *    race pattern evaluated in 3D bind-pose space so patterns have no UV seams.
 *  - Micro detail: pores and micro wrinkles from a shared tiling texture, age wrinkles and pattern
 *    relief, all through derivative bump mapping.
 *  - Lighting: per-channel wrap diffuse (subsurface look), back-light translucency on thin parts,
 *    sheen for peach fuzz, skin IOR specular.
 *  - Facial expressions: expression-unit deltas from a shared texture, added ahead of skinning.
 *
 * All characters share one shader; per-character data lives in uniforms.
 */
import * as THREE from 'three/webgpu';
import type { SkyVisPatch } from './sky';
import type { HumanoidAppearance } from '../types';
import { BEARD_IDS } from '../faceRegions';
import { poreTexture } from './textures';
import { MARK_IDS } from '../appearance';
import { srgbColor as lin } from './color';
import { createSkinNodeMaterial } from './nodes/people';

export const PATTERN_IDS: Record<HumanoidAppearance['skinPattern'], number> = {
  none: 0, freckles: 1, scales: 2, bark: 3, spots: 4, tattoos: 5, veins: 6, stripes: 7, crystals: 8,
};
const BROW_PARAMS: Record<string, [number, number, number, number]> = {
  none: [0, 0, 0, 0], thin: [0.6, 0.9, 0, 0.75], normal: [1, 0.7, 0, 0.9], thick: [1.35, 0.6, 0, 1], bushy: [1.75, 0.5, 0, 1.1],
  arched: [0.95, 1.6, 0, 0.9], unibrow: [1.35, 0.5, 0.9, 1], scaled: [0, 0, 0, 0],
};

export interface SkinUniforms {
  uTone: { value: THREE.Color };
  uAccent: { value: THREE.Color };
  uHair: { value: THREE.Color };
  uPattern: { value: THREE.Vector4 };
  uLook: { value: THREE.Vector4 };
  uBrow: { value: THREE.Vector4 };
  uBeard: { value: THREE.Vector4 };
  uMarks: { value: number };
  uExprW: { value: Float32Array };
  uExprTex: { value: THREE.Texture | null };
  uFaceScale: { value: number };
  uPores: { value: THREE.Texture };
  uHide: { value: number };
  /** A worn eye mask: x off (0) / domino (1) / round a cowl's eye holes (2), yzw its colour (linear). Set by the equipment. */
  uMask: { value: THREE.Vector4 };
  /** The material's sheenColor, tinted from the skin tone by applySkinLook. */
  sheenTarget?: THREE.Color;
}

export interface SkinMaterialHandle {
  material: THREE.MeshPhysicalNodeMaterial;
  uniforms: SkinUniforms;
  sky: SkyVisPatch;
}

/** The per-character skin uniforms. */
function skinUniforms(opts: { exprTex: THREE.Texture | null; exprUnits: number }): SkinUniforms {
  return {
    uTone: { value: new THREE.Color(0.7, 0.5, 0.4) },
    uAccent: { value: new THREE.Color(0.3, 0.2, 0.15) },
    uHair: { value: new THREE.Color(0.1, 0.07, 0.05) },
    uPattern: { value: new THREE.Vector4() },
    uLook: { value: new THREE.Vector4() },
    uBrow: { value: new THREE.Vector4() },
    uBeard: { value: new THREE.Vector4(-1, 0, 0, 0) },
    uMarks: { value: 0 },
    uExprW: { value: new Float32Array(Math.max(1, opts.exprUnits)) },
    uExprTex: { value: opts.exprTex },
    uFaceScale: { value: 1 },
    uPores: { value: poreTexture() },
    uHide: { value: 0 },
    uMask: { value: new THREE.Vector4() },
  };
}

/** Create the skin material for one character. */
export function createSkinMaterial(opts: { expr: boolean; exprTex: THREE.Texture | null; exprUnits: number; lod: number }): SkinMaterialHandle {
  return createSkinNodeMaterial(opts, skinUniforms(opts));
}

/** Push an appearance into the skin uniforms. */
export function applySkinLook(u: SkinUniforms, a: HumanoidAppearance, opts: { shavedScalp: number; hairCovered: boolean }) {
  u.uTone.value.copy(lin(a.skinTone));
  // Peach-fuzz sheen tinted by the skin itself (a grey sheen reads as plastic).
  if (u.sheenTarget) u.sheenTarget.copy(lin(a.skinTone)).multiplyScalar(0.55);
  u.uAccent.value.copy(lin(a.skinAccent));
  u.uHair.value.copy(lin(a.hairColor));
  const seed = ((a.seed >>> 0) % 9973) / 9973;
  const glow = a.skinPattern === 'veins' ? 0.6 + a.eyeGlow * 0.6 : a.skinPattern === 'crystals' ? 0.4 : 0;
  u.uPattern.value.set(PATTERN_IDS[a.skinPattern] ?? 0, a.patternStrength, seed, glow);
  const blush = (1 - a.gender) * 0.35 + (a.age < 0.45 ? 0.2 : 0);
  u.uLook.value.set(a.age, a.gender, blush, opts.shavedScalp);
  const bp = BROW_PARAMS[a.browStyle] ?? BROW_PARAMS.normal;
  // Elders: thinner, sparser brows; males slightly thicker.
  const thick = bp[0] * (0.9 + a.gender * 0.2) * (a.age > 0.75 ? 0.85 : 1);
  u.uBrow.value.set(thick, bp[1], bp[2], bp[3]);
  const beardId = BEARD_IDS[a.beardStyle] ?? -1;
  // Stubble density: stubble style dense shadow, full beards get a dark base under the cards.
  const dens = a.beardStyle === 'none' ? 0 : a.beardStyle === 'stubble' ? 0.75 : 0.95;
  const recede = a.gender > 0.5 ? Math.max(0, a.age - 0.6) * 1.6 : 0;
  const lipTint = a.race === 'umbral' ? 0.35 : a.race === 'drakeborn' ? 0.3 : 0;
  u.uBeard.value.set(beardId, dens, recede, lipTint);
  let bits = 0;
  for (const m of a.marks) {
    const i = MARK_IDS.indexOf(m);
    if (i === 6 + 0 && m === 'warpaint_stripes') bits |= 1 << 6;
    else if (m === 'warpaint_mask') bits |= 1 << 7;
    else if (m === 'freckle_patch') bits |= 1 << 8;
    else if (m === 'tattoo_face') bits |= 1 << 5;
    else if (i >= 0 && i < 5) bits |= 1 << i;
  }
  u.uMarks.value = bits;
}
