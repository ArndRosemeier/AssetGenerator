import { test } from 'node:test';
import assert from 'node:assert/strict';
import { Bone, Float32BufferAttribute, BufferGeometry, Group, Matrix4, MeshBasicNodeMaterial, Skeleton, SkinnedMesh, Uint16BufferAttribute, Vector3 } from 'three/webgpu';
import { skinLocally } from '../src/three/skinning';

/** One bent two-bone limb on a creature 32 km out; `local` skins it with `skinLocally`. */
function limb(local: boolean) {
  const root = new Group();
  const a = new Bone(), b = new Bone();
  b.position.set(0, 0.5, 0);
  a.add(b);
  const g = new BufferGeometry();
  g.setAttribute('position', new Float32BufferAttribute([0.1, 0.7, 0], 3));
  g.setAttribute('skinIndex', new Uint16BufferAttribute([1, 0, 0, 0], 4));
  g.setAttribute('skinWeight', new Float32BufferAttribute([1, 0, 0, 0], 4));
  const mesh = new SkinnedMesh(g, new MeshBasicNodeMaterial());
  mesh.position.set(0, 0.2, 0); // the mesh a little off its root, bound with a bind matrix
  mesh.add(a);
  root.add(mesh);
  root.updateMatrixWorld(true);
  mesh.bind(new Skeleton([a, b]), new Matrix4().makeTranslation(0, 0.05, 0));
  if (local) skinLocally(root);
  root.position.set(-32000, 80, 32000);
  root.rotation.y = 0.7;
  a.rotation.z = 0.3;
  b.rotation.x = -0.4;
  root.updateMatrixWorld(true);
  mesh.skeleton.update();
  // What the GPU computes from the uploaded matrices, then the model matrix.
  const gpu = new Vector3(0.1, 0.7, 0).applyMatrix4(mesh.bindMatrix).applyMatrix4(new Matrix4().fromArray(mesh.skeleton.boneMatrices!, 16)).applyMatrix4(mesh.bindMatrixInverse);
  return { mesh, gpu };
}

test('skinning: skinLocally skins where three does, with bone matrices free of the world position', () => {
  const ours = limb(true), theirs = limb(false);
  // three's CPU skinning, in doubles: where the vertex belongs (in the mesh's own space).
  const exact = theirs.mesh.getVertexPosition(0, new Vector3());
  assert.ok(ours.gpu.distanceTo(exact) < 1e-5, `${ours.gpu.toArray()} vs ${exact.toArray()}`);
  assert.ok(theirs.gpu.distanceTo(exact) > 1e-4, 'three\'s world matrices, rounded to 32 bits, miss by most of a millimetre');
  assert.ok(ours.mesh.getVertexPosition(0, new Vector3()).distanceTo(exact) < 1e-6, 'CPU skinning stays in the mesh\'s space');
  const t = new Vector3().setFromMatrixPosition(new Matrix4().fromArray(ours.mesh.skeleton.boneMatrices!, 16));
  assert.ok(t.length() < 2, `uploaded offset ${t.length()} m`);
  assert.ok(Math.abs(theirs.mesh.skeleton.boneMatrices![16 + 12]) > 1000);
});
