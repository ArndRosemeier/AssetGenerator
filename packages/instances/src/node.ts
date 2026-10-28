// @ts-nocheck -- three's TSL typings infer vector widths poorly; checked by rendering.
/**
 * For materials of instanced meshes: the instance matrix from the geometry attributes iM0..iM3 (a mat4 per
 * instance, as `instancedGeometry` and the draws here lay them out) and an optional per-instance tint
 * `iColor`. Applied before the material's own `positionNode`, in every pass (shadows too).
 */
import type * as THREE from 'three/webgpu';
import { attribute, diffuseColor, mat4, normalLocal, positionLocal, transformNormal, vec4 } from 'three/tsl';

export function geometryInstancing(mat: THREE.NodeMaterial): void {
  const pos = mat.setupPosition, dif = mat.setupDiffuseColor;
  mat.setupPosition = function (builder) {
    if (builder.hasGeometryAttribute('iM0')) {
      const M = mat4(attribute('iM0', 'vec4'), attribute('iM1', 'vec4'), attribute('iM2', 'vec4'), attribute('iM3', 'vec4'));
      positionLocal.assign(M.mul(vec4(positionLocal, 1.0)).xyz);
      if (builder.hasGeometryAttribute('normal')) normalLocal.assign(transformNormal(normalLocal, M));
    }
    return pos.call(this, builder);
  };
  mat.setupDiffuseColor = function (builder) {
    dif.call(this, builder);
    if (builder.hasGeometryAttribute('iColor')) diffuseColor.assign(vec4(diffuseColor.rgb.mul(attribute('iColor', 'vec3')), diffuseColor.a));
  };
}
