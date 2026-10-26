/**
 * Skinning that stays exact far from the world origin.
 *
 * three's skeleton uploads `bone.matrixWorld × boneInverse`: the bone matrices carry the creature's world
 * position, and the GPU skins in 32-bit floats, which tens of kilometres out only resolve millimetres
 * (3.9 mm at 32 km). Every vertex then lands a little off, differently each frame, and the body shimmers.
 * `skinLocally` takes each mesh's own world transform out on the CPU, in doubles, so the GPU only sees
 * offsets within the creature. (Actors does the same in its RootSkeleton.)
 */
import { DetachedBindMode, Matrix4, SkinnedMesh, type Bone, type Object3D, type Skeleton, type Vector3, type Vector4 } from 'three/webgpu';

const meshInverse = new Matrix4(), offset = new Matrix4();

/**
 * Every skinned mesh in `object` uploads bone matrices relative to itself. A skeleton is read from its
 * first mesh: meshes sharing one must share that mesh's world transform (a glb's single skin does).
 */
export function skinLocally(object: Object3D): void {
  const done = new Set<Skeleton>();
  object.traverse((o) => {
    const mesh = o as SkinnedMesh;
    if (!mesh.isSkinnedMesh || !mesh.skeleton) return;
    // Detached: three keeps the bind inverse at inverse(bindMatrix) and leaves the world out of it.
    mesh.bindMode = DetachedBindMode;
    mesh.bindMatrixInverse.copy(mesh.bindMatrix).invert();
    mesh.applyBoneTransform = localBoneTransform as SkinnedMesh['applyBoneTransform'];
    const sk = mesh.skeleton;
    if (done.has(sk)) return;
    done.add(sk);
    sk.update = () => localUpdate(sk, mesh);
  });
}

/** Bone matrices `bindMatrix × inverse(mesh world) × bone world × boneInverse`: the detached formula gives what attached mode would. */
function localUpdate(sk: Skeleton, mesh: SkinnedMesh): void {
  meshInverse.copy(mesh.matrixWorld).invert().premultiply(mesh.bindMatrix);
  const m = sk.boneMatrices!;
  for (let i = 0; i < sk.bones.length; i++) {
    const bone: Bone | undefined = sk.bones[i];
    offset.multiplyMatrices(meshInverse, bone ? bone.matrixWorld : offset.identity());
    offset.multiply(sk.boneInverses[i]);
    offset.toArray(m, i * 16);
  }
  if (sk.boneTexture !== null) sk.boneTexture.needsUpdate = true;
}

/** three's CPU skinning (raycasts, bounds) reads bone world matrices: take the world back out, as attached mode does. */
function localBoneTransform(this: SkinnedMesh, index: number, target: Vector3 | Vector4): Vector3 | Vector4 {
  SkinnedMesh.prototype.applyBoneTransform.call(this, index, target as Vector3);
  return (target as Vector3).applyMatrix4(meshInverse.copy(this.matrixWorld).invert().multiply(this.bindMatrix));
}
