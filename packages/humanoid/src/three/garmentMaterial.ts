/**
 * Procedural garment shading for shell layers (ShellMaterial from the items
 * module): plain cloth weave, stripes, checks, quilting, chainmail rings,
 * scales, leather grain, fur, embroidery, patchwork, silk, plates and glowing
 * runes. Patterns are evaluated triplanar in bind-pose space, so they are
 * seamless and stay glued to the body while it animates; relief goes through
 * derivative bump mapping. Hems are cut along a smooth line and trimmed from a
 * per-vertex distance attribute (aEdge). Wear adds dirt, fraying and scuffs.
 */
import * as THREE from 'three/webgpu';
import { createGarmentNodeMaterial } from './nodes/people';
import type { SkyVisPatch } from './sky';
import type { ShellMaterial } from '../wearable';
import { srgbColor as lin } from './color';

const PATTERNS: Record<ShellMaterial['pattern'], number> = {
  plain: 0, stripes: 1, checks: 2, quilted: 3, chainmail: 4, scales: 5, leather: 6, fur: 7, embroidered: 8, patchwork: 9, silk: 10, plates: 11, runes: 12, bones: 13, hero: 14,
};

export interface GarmentHandle {
  material: THREE.MeshPhysicalMaterial;
  sky: SkyVisPatch;
}

type GarmentFig = { height: number; design: number; cut?: 'cowl' | 'full'; neckY?: number; neckSlope?: number };

/** The garment's uniforms (the graph is in nodes/people.ts). */
function garmentUniforms(m: ShellMaterial, seed: number, trim?: [number, number, number], fig?: GarmentFig) {
  const metal = m.metalness;
  return {
    gColor: { value: lin(m.color) },
    gColor2: { value: lin(m.color2) },
    gTrim: { value: lin(trim ?? m.color2) },
    gParams: { value: new THREE.Vector4(PATTERNS[m.pattern] ?? 0, Math.max(0.5, m.patternScale), m.wear, (seed % 997) * 0.37) },
    gGlow: { value: lin(m.glowColor).multiplyScalar(m.glow) },
    gMetal: { value: metal },
    gFig: { value: new THREE.Vector4(fig?.height ?? 1.75, fig?.design ?? 0, fig?.neckY ?? 0, fig?.neckSlope ?? 0) },
  };
}

/** Create a garment material for a shell. */
export function createGarmentMaterial(m: ShellMaterial, seed: number, trim?: [number, number, number], fig?: GarmentFig): GarmentHandle {
  return createGarmentNodeMaterial(m, garmentUniforms(m, seed, trim, fig)) as unknown as GarmentHandle;
}
