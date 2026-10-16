/**
 * A ghost: every material of a humanoid seen through and glowing at its rim, in one tint. Applied
 * once to each material (a ghost's materials are its own: nothing here is shared with the living),
 * before the materials are first compiled; `Humanoid` reapplies it to what `dress` adds.
 */
import * as THREE from 'three/webgpu';
import { float, vec3, dot, normalView, positionViewDirection, saturate, pow, sub, materialEmissive, uniform } from 'three/tsl';

export interface Ghost {
  /** sRGB 0..1. */
  tint: [number, number, number];
  /** How much of it one sees, 0..1 (its rim more, its middle less). */
  opacity: number;
}

const done = new WeakSet<THREE.Material>();

/** How much of a ghost shows (0: gone, 1: as `Ghost.opacity` says), one per humanoid, set any frame without a recompile. */
export function ghostFade() {
  return uniform(1);
}
export type GhostFade = ReturnType<typeof ghostFade>;

/** Make every mesh under `root` ghostly, faded by `fade` (materials already ghostly are left as they are). */
export function ghostly(root: THREE.Object3D, g: Ghost, fade: GhostFade): void {
  const c = new THREE.Color().setRGB(g.tint[0], g.tint[1], g.tint[2], THREE.SRGBColorSpace), tint = vec3(c.r, c.g, c.b);
  root.traverse((o) => {
    const m = o as THREE.Mesh;
    if (!m.isMesh) return;
    m.castShadow = false;
    for (const mat of Array.isArray(m.material) ? m.material : [m.material]) {
      const n = mat as THREE.MeshPhysicalNodeMaterial;
      if (done.has(n)) continue;
      done.add(n);
      // Facing you, thin; at the edges, where one looks through more of it, stronger.
      const rim = pow(sub(1, saturate(dot(normalView, positionViewDirection))), 2);
      const seen = float(g.opacity).mul(rim.mul(1.6).add(0.35)).mul(fade);
      n.opacityNode = n.opacityNode ? (n.opacityNode as ReturnType<typeof float>).mul(seen) : seen;
      n.emissiveNode = ((n.emissiveNode ?? materialEmissive) as typeof tint).add(tint.mul(rim.mul(1.4).add(0.25)).mul(fade));
      n.transparent = true;
      n.depthWrite = false;
      n.needsUpdate = true;
    }
  });
}
