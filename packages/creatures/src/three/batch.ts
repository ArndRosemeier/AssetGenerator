/**
 * Many small creatures of one body in one draw (birds: ../birds.ts, fish: ../fish.ts; their shaders in ../node.ts):
 * the game poses every one on the CPU each frame (`begin`, `add` for each, `end`); the shader moves the body's parts
 * (beats or folds the wings, sweeps the tail) and places it. Positions are kept relative to an origin the game sets
 * near the camera each frame, so creatures far from the world's origin hold still to the millimetre.
 */
import { BufferAttribute, DynamicDrawUsage, InstancedBufferAttribute, InstancedBufferGeometry, Mesh, Sphere, Vector3, type Material } from 'three/webgpu';
import { POSE_STRIDE } from '../pose';
import { birdMesh, packBird, type BirdPose } from '../birds';
import { fishMesh, packFish, type FishPose } from '../fish';

/** A body for a batch: its positions, one per-vertex attribute (`partName`, `partSize` floats each), triangles. */
interface BatchBody {
  readonly positions: Float32Array;
  readonly part: Float32Array;
  readonly partName: string;
  readonly partSize: number;
  readonly indices: Uint16Array;
}

type Pack<P> = (p: P, origin: { x: number; y: number; z: number }, place: Float32Array, turn: Float32Array, look: Float32Array, i: number) => void;

export class PoseBatch<P> {
  readonly mesh: Mesh<InstancedBufferGeometry>;
  private readonly attrs: InstancedBufferAttribute[];
  private readonly origin = new Vector3();
  private n = 0;

  /**
   * `material`: the game's registered material for the body; `prefix`: its instance attributes' (`bPlace`, `bTurn`,
   * `bLook` for birds). At most `capacity` are drawn.
   */
  constructor(body: BatchBody, private readonly pack: Pack<P>, prefix: string, name: string, material: Material, readonly capacity: number) {
    const g = new InstancedBufferGeometry();
    g.setAttribute('position', new BufferAttribute(body.positions, 3));
    g.setAttribute(body.partName, new BufferAttribute(body.part, body.partSize));
    g.setIndex(new BufferAttribute(body.indices, 1));
    this.attrs = ['Place', 'Turn', 'Look'].map((k) => {
      const a = new InstancedBufferAttribute(new Float32Array(capacity * POSE_STRIDE), POSE_STRIDE);
      a.setUsage(DynamicDrawUsage);
      g.setAttribute(prefix + k, a);
      return a;
    });
    g.instanceCount = 1;
    // Placed by the shader, anywhere around the origin.
    g.boundingSphere = new Sphere(new Vector3(), Infinity);
    this.mesh = new Mesh(g, material);
    this.mesh.name = name;
    this.mesh.frustumCulled = false;
    this.mesh.castShadow = false;
    this.mesh.receiveShadow = true;
    // Visible until the first frame (one instance of size 0, so nothing shows): the game's warm-up compiles it.
  }

  /** How many this frame holds. */
  get count(): number { return this.n; }

  /** Starts a frame's creatures, placed relative to (x, y, z): somewhere near the camera. */
  begin(x: number, y: number, z: number): void {
    this.origin.set(x, y, z);
    this.mesh.position.copy(this.origin);
    this.mesh.updateMatrix();
    this.n = 0;
  }

  /** One more; false when the batch is full. */
  add(p: P): boolean {
    if (this.n >= this.capacity) return false;
    const [place, turn, look] = this.attrs.map((a) => a.array as Float32Array);
    this.pack(p, this.origin, place, turn, look, this.n++);
    return true;
  }

  /** Hands the frame's creatures to the GPU (only the part in use). */
  end(): void {
    const used = this.n * POSE_STRIDE;
    for (const a of this.attrs) {
      a.clearUpdateRanges();
      if (used > 0) {
        a.addUpdateRange(0, used);
        a.needsUpdate = true;
      }
    }
    this.mesh.geometry.instanceCount = Math.max(1, this.n);
    this.mesh.visible = this.n > 0;
  }
}

/** Many small birds in one draw (`material`: the game's registered `birdMaterial()`). */
export class BirdBatch extends PoseBatch<BirdPose> {
  constructor(material: Material, capacity: number) {
    const b = birdMesh();
    super({ positions: b.positions, part: b.parts, partName: 'bPart', partSize: 2, indices: b.indices }, packBird, 'b', 'birds', material, capacity);
  }
}

/** Many small fish in one draw (`material`: the game's registered `fishMaterial()`). */
export class FishBatch extends PoseBatch<FishPose> {
  constructor(material: Material, capacity: number) {
    const f = fishMesh();
    super({ positions: f.positions, part: f.back, partName: 'fBack', partSize: 1, indices: f.indices }, packFish, 'f', 'fish', material, capacity);
  }
}
