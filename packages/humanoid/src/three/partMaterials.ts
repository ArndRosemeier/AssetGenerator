/**
 * Materials for the non-skin parts of a humanoid: procedural eyes (iris
 * with fibres, limbal ring, pupil shapes, glow, refraction parallax, wet
 * clearcoat cornea, lid shadow), strand-card hair with Kajiya–Kay dual
 * highlights, sylvan leaf hair, keratin horns/tusks, lashes, teeth, tongue.
 * All patched for sky occlusion ('uniform'). The node graphs are in nodes/people.ts.
 */
import * as THREE from 'three/webgpu';
import { createEyeNodeMaterial, createHairNodeMaterial, createHornNodeMaterial, createLashNodeMaterial, simpleNodeMaterial } from './nodes/people';
import type { SkyVisPatch } from './sky';
import { srgbColor as lin } from './color';

export interface PatchedMaterial<U = Record<string, { value: unknown }>> {
  material: THREE.Material;
  uniforms: U;
  sky: SkyVisPatch;
}

// ------------------------------------------------------------------ eyes

export interface EyeUniforms {
  uIris: { value: THREE.Color };
  uPupil: { value: THREE.Vector4 }; // x shape (0 round,1 slit,2 goat,3 none), y dilation, z glow, w seed
  uScleraTint: { value: THREE.Color };
}

export function createEyeMaterial(): PatchedMaterial<EyeUniforms> {
  return createEyeNodeMaterial() as unknown as PatchedMaterial<EyeUniforms>;
}

/** Eyeball geometry (unit radius scaled by caller) with a cornea bulge toward −Z. */
let eyeGeo: THREE.BufferGeometry | null = null;
export function eyeGeometry(): THREE.BufferGeometry {
  if (eyeGeo) return eyeGeo;
  const g = new THREE.SphereGeometry(1, 32, 24);
  const p = g.attributes.position as THREE.BufferAttribute;
  for (let i = 0; i < p.count; i++) {
    const z = p.getZ(i);
    if (z < -0.82) {
      // Cornea dome: bulge forward over the iris.
      const k = (-z - 0.82) / 0.18;
      p.setZ(i, z - 0.09 * Math.sin(k * Math.PI * 0.5));
    }
  }
  g.computeVertexNormals();
  eyeGeo = g;
  return g;
}

// ------------------------------------------------------------------ hair

export interface HairUniforms {
  uColor: { value: THREE.Color };
  uTip: { value: THREE.Color };
  uSpec: { value: THREE.Vector4 }; // x primary, y secondary, z shift, w leaf mode
  /** Hair cut (rest model space): strands where xyz·p > w are under a hat and not drawn. */
  uCut: { value: THREE.Vector4 };
}

export function createHairMaterial(leaf: boolean): PatchedMaterial<HairUniforms> {
  return createHairNodeMaterial(leaf) as unknown as PatchedMaterial<HairUniforms>;
}

export function applyHairColor(u: HairUniforms, hair: [number, number, number], leaf: boolean, accent?: [number, number, number]) {
  const c = lin(hair);
  u.uColor.value.copy(c);
  if (leaf) u.uTip.value.copy(accent ? lin(accent) : c.clone().multiply(new THREE.Color(1.3, 0.9, 0.5)));
  else u.uTip.value.copy(c.clone().multiplyScalar(1.25).lerp(new THREE.Color(0.6, 0.5, 0.35), 0.06));
  // Dark hair shows a cooler, stronger primary highlight; blond a softer one.
  const l = c.r * 0.3 + c.g * 0.6 + c.b * 0.1;
  // Light hair already scatters most light: keep its highlights soft.
  const dark = 1 - Math.min(1, l * 2.2);
  u.uSpec.value.x = 0.025 + dark * 0.06;
  u.uSpec.value.y = 0.05 + dark * 0.06;
}

// ------------------------------------------------------------------ horns / tusks / fins

export interface HornUniforms { uBase: { value: THREE.Color }; uTipC: { value: THREE.Color }; uRidge: { value: number } }

export function createHornMaterial(): PatchedMaterial<HornUniforms> {
  return createHornNodeMaterial() as unknown as PatchedMaterial<HornUniforms>;
}

export function simpleMaterial(color: THREE.ColorRepresentation, opts: THREE.MeshPhysicalMaterialParameters = {}): PatchedMaterial<Record<string, never>> {
  return simpleNodeMaterial(color, opts as Record<string, unknown>) as unknown as PatchedMaterial<Record<string, never>>;
}

/** Eyelash cards: strand texture along the lid. */
export function createLashMaterial(): PatchedMaterial<{ uColor: { value: THREE.Color } }> {
  return createLashNodeMaterial() as unknown as PatchedMaterial<{ uColor: { value: THREE.Color } }>;
}
