/**
 * Sky occlusion: sunlight and sky ambient must not reach deep into caves. Every humanoid material
 * scales sun + sky/hemisphere lighting by a "sky visibility" factor (0 = deep underground, 1 = open
 * sky) and adds a dim cave ambient (nodes/skyOcclusion.ts). Point lights are not affected.
 *
 * Modes:
 *  - 'attribute': per-vertex `skyVis` float attribute
 *  - 'uniform':   per-material value (characters)
 *  - 'varying':   the material provides `skyVisNode` (else reads the varying `vSkyVis`)
 */
import * as THREE from 'three/webgpu';

export type SkyVisMode = 'attribute' | 'uniform' | 'varying';

/** Global underground ambient (bluish, very dim) applied where sky visibility is 0. */
export const caveAmbient = { value: new THREE.Color(0.018, 0.02, 0.028) };

export interface SkyVisPatch {
  uniform?: { value: number };
}
