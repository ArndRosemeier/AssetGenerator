/**
 * The one way to make a `skinIndex` vertex attribute: three's node skinning reads it as uvec4,
 * which needs integer data.
 */
import * as THREE from 'three/webgpu';

export function skinIndexAttribute(indices: ArrayLike<number>): THREE.BufferAttribute {
  return new THREE.Uint16BufferAttribute(indices, 4);
}
