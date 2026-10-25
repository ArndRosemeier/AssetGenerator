/**
 * Procedural creatures drawn: a species' flesh (flesh.ts) skinned to its anatomy's bones, padded to
 * `CRITTER_BONES` so every species shares one skinning shader; its eyes are balls riding their bones.
 * Each figure has its own skeleton and its own `CritterRig`, which poses it every frame from how it
 * moves. The game gives the materials (one for the flesh of every species, one for every eye; see
 * ../node.ts), so it keeps its own material registry. From Dunfinity.
 */
import { Bone, BufferAttribute, BufferGeometry, Group, Matrix4, Mesh, Quaternion, Skeleton, SkinnedMesh, SphereGeometry, Vector3, Float32BufferAttribute, type Material } from 'three/webgpu';
import { anatomyOf, type Anatomy } from '../anatomy';
import { fleshOf, type FleshData } from '../flesh';
import type { Species } from '../bestiary';
import { CritterRig, type GroundAt, type RigInput } from './rig';

/** How many bones every procedural creature's skeleton has (padded): the skinning shader is keyed by the count. */
export const CRITTER_BONES = 96;

/** The materials creatures are drawn with: `flesh` reads the attributes position, normal, color and look (vec4). */
export interface CritterMaterials {
  readonly flesh: Material;
  readonly eye: Material;
  /** Shadows: the flesh casts and receives, eyes receive. */
  readonly shadows?: boolean;
}

/** One species, meshed once; `figure()` gives a posable copy. */
export class CritterModel {
  readonly anatomy: Anatomy;
  private readonly geometry: BufferGeometry;
  private readonly eyeBall: BufferGeometry;

  constructor(readonly species: Species, private readonly materials: CritterMaterials, flesh?: FleshData) {
    this.anatomy = anatomyOf(species);
    if (this.anatomy.bones.length > CRITTER_BONES) throw new Error(`critter ${species.id}: ${this.anatomy.bones.length} bones, more than ${CRITTER_BONES}`);
    const f = flesh ?? fleshOf(this.anatomy, species);
    const g = new BufferGeometry();
    g.setAttribute('position', new BufferAttribute(f.positions, 3));
    g.setAttribute('normal', new BufferAttribute(f.normals, 3));
    g.setAttribute('color', new BufferAttribute(f.colors, 3));
    g.setAttribute('look', new BufferAttribute(f.looks, 4));
    g.setAttribute('skinIndex', new BufferAttribute(f.skinIndex, 4));
    g.setAttribute('skinWeight', new BufferAttribute(f.skinWeight, 4));
    g.setIndex(new BufferAttribute(f.indices, 1));
    g.computeBoundingSphere();
    this.geometry = g;
    const ball = new SphereGeometry(1, 18, 12);
    ball.deleteAttribute('uv');
    const [r, gg, b] = species.colors.eye;
    const n = ball.getAttribute('position').count;
    ball.setAttribute('color', new Float32BufferAttribute(Array.from({ length: n * 3 }, (_, i) => [r, gg, b][i % 3]), 3));
    this.eyeBall = ball;
  }

  /** Free its meshes (its figures are gone). */
  free(): void {
    this.geometry.dispose();
    this.eyeBall.dispose();
  }

  figure(ground: GroundAt): CritterFigure {
    return new CritterFigure(this, this.geometry, this.eyeBall, this.materials, ground);
  }
}

const _q = new Quaternion(), _z = new Vector3(0, 0, 1), _d = new Vector3();

/** One drawn creature: its root is placed and posed by its rig. */
export class CritterFigure {
  readonly root = new Group();
  readonly mesh: SkinnedMesh;
  readonly rig: CritterRig;

  constructor(readonly model: CritterModel, geometry: BufferGeometry, eyeBall: BufferGeometry, materials: CritterMaterials, ground: GroundAt) {
    const an = model.anatomy;
    const bones = an.bones.map((d) => {
      const b = new Bone();
      b.name = d.name;
      return b;
    });
    an.bones.forEach((d, i) => {
      const p = d.parent >= 0 ? an.bones[d.parent].pos : [0, 0, 0];
      bones[i].position.set(d.pos[0] - p[0], d.pos[1] - p[1], d.pos[2] - p[2]);
      if (d.parent >= 0) bones[d.parent].add(bones[i]);
    });
    const inverses = an.bones.map((d) => new Matrix4().makeTranslation(-d.pos[0], -d.pos[1], -d.pos[2]));
    // Padding: bones no vertex is weighted to, so every skeleton has the same count.
    const all = [...bones];
    while (all.length < CRITTER_BONES) { all.push(new Bone()); inverses.push(new Matrix4()); }
    const shadows = materials.shadows ?? true;
    this.mesh = new SkinnedMesh(geometry, materials.flesh);
    this.mesh.castShadow = this.mesh.receiveShadow = shadows;
    this.mesh.add(bones[0]);
    this.mesh.bind(new Skeleton(all, inverses), new Matrix4());
    // Its bounds are the rest pose's: a creature rolled over would be culled while in view.
    this.mesh.frustumCulled = false;
    for (const e of an.eyes) {
      const eye = new Mesh(eyeBall, materials.eye);
      eye.receiveShadow = shadows;
      const bp = an.bones[e.bone].pos;
      eye.position.set(e.pos[0] - bp[0], e.pos[1] - bp[1], e.pos[2] - bp[2]);
      eye.quaternion.copy(_q.setFromUnitVectors(_z, _d.set(e.dir[0], e.dir[1], e.dir[2]).normalize()));
      eye.scale.setScalar(e.radius);
      eye.frustumCulled = false;
      bones[e.bone].add(eye);
    }
    this.root.add(this.mesh);
    this.rig = new CritterRig(model.species, an, bones, this.root, ground);
  }

  /** Pose it after `inp`; `dt` seconds since the last pose; `hurt` (0..1) flashes it red (the flesh material reads `userData.hurt`). */
  animate(inp: RigInput, dt: number, hurt = 0): void {
    this.root.visible = true;
    this.mesh.userData.hurt = hurt;
    this.rig.update(dt, inp);
  }
}
