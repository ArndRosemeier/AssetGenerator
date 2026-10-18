/**
 * Fur-shell hair: several skinned copies of the scalp / beard region of the
 * body, pushed out along the normal in the vertex shader, each alpha-tested
 * against a strand pattern that thins out with height. Gives dense, soft
 * coverage for short hair, buzz cuts, short beards and the base layer under
 * hair cards (no scalp shining through partings), at a cost of a few
 * hundred triangles per layer. Shares the body's vertex buffers; only the
 * index subset is per character.
 */
import * as THREE from 'three/webgpu';
import { createShellNodeMaterial } from './nodes/people';
import type { SkyVisPatch } from './sky';
import { beardCoverage, scalpCoverage, BEARD_IDS } from '../faceRegions';
import type { HumanStatic } from './staticData';

export interface ShellSpec {
  kind: 'scalp' | 'beard';
  /** Total thickness (m). */
  length: number;
  layers: number;
  /** Strand density 0..1. */
  density: number;
  /** Comb direction strength (strands lean with the surface "down/back"). */
  recede: number;
  beardStyle: number;
  /** Restrict scalp coverage to a band (mohawk/topknot/undercut) via face x/y limits. */
  maxAbsX?: number;
  minY?: number;
}

/** Triangle subset of the body covered by the region (at least one vertex with coverage). */
export function shellIndex(st: HumanStatic, spec: ShellSpec): Uint16Array {
  const face = st.face.array as Float32Array;
  const body = st.index.body;
  const cov = (v: number) => {
    const x = face[v * 3], y = face[v * 3 + 1], z = face[v * 3 + 2];
    if (spec.kind === 'beard') return beardCoverage(spec.beardStyle, x, y, z);
    let c = scalpCoverage(x, y, z, spec.recede);
    if (spec.maxAbsX !== undefined && Math.abs(x) > spec.maxAbsX) c = 0;
    if (spec.minY !== undefined && y < spec.minY) c = 0;
    return c;
  };
  const keep: number[] = [];
  for (let i = 0; i < body.length; i += 3) {
    if (cov(body[i]) > 0.05 || cov(body[i + 1]) > 0.05 || cov(body[i + 2]) > 0.05) keep.push(body[i], body[i + 1], body[i + 2]);
  }
  return Uint16Array.from(keep);
}

export interface ShellLayerHandle {
  material: THREE.MeshPhysicalMaterial;
  sky: SkyVisPatch;
  /** Its own values; hsCut: the hair cut under a hat (as HairUniforms.uCut). */
  uniforms: { hsCut: { value: THREE.Vector4 } };
}

/**
 * One shell layer. Layers are alpha-blended (soft, no alpha-test sparkle) and
 * use a low-frequency, anti-aliased streak pattern running with the hair flow
 * (face-coordinate space), fading to its mean once streaks get sub-pixel, so
 * the coat reads as coherent hair at any distance. Roots are darker (self
 * shadowing); a sheen lobe gives the soft anisotropic-looking rim highlight.
 */
export function createShellMaterial(spec: ShellSpec, layer: number, color: THREE.Color): ShellLayerHandle {
  return createShellNodeMaterial(spec, layer, color) as unknown as ShellLayerHandle;
}

/** Shell settings for a hair style / beard style (null = none). */
export function scalpShellFor(style: string, recede: number): ShellSpec | null {
  const base = { kind: 'scalp' as const, layers: 6, density: 0.95, recede, beardStyle: 0 };
  switch (style) {
    case 'bald': case 'crest': case 'leaves': return null;
    case 'shaved': return { ...base, length: 0.0015, layers: 3, density: 0.8 };
    case 'buzz': return { ...base, length: 0.004, layers: 4 };
    case 'crop': return { ...base, length: 0.007 };
    case 'mohawk': return { ...base, length: 0.004, layers: 4, maxAbsX: 0.3 };
    case 'topknot': return { ...base, length: 0.005, minY: 1.2 };
    case 'tonsure': return { ...base, length: 0.006 };
    case 'undercut': return { ...base, length: 0.003, layers: 3 };
    default: return { ...base, length: 0.006 };
  }
}

export function beardShellFor(style: string): ShellSpec | null {
  if (style === 'none' || style === 'stubble') return null;
  const id = BEARD_IDS[style] ?? 0;
  const len = style === 'short' || style === 'chinstrap' || style === 'goatee' || style === 'mustache' || style === 'mutton' ? 0.008 : 0.006;
  return { kind: 'beard', length: len, layers: 6, density: 0.92, recede: 0, beardStyle: id };
}
