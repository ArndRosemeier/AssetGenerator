/**
 * Many small birds in one draw (../birds.ts for the body, ../node.ts `birdMaterial` for the shader):
 * the game poses every bird on the CPU each frame (`begin`, `add` for each, `end`); the shader beats
 * or folds the wings and places the body. Positions are kept relative to an origin the game sets near
 * the camera each frame, so birds far from the world's origin hold still to the millimetre.
 */
import { BufferAttribute, DynamicDrawUsage, InstancedBufferAttribute, InstancedBufferGeometry, Mesh, Sphere, Vector3, type Material } from 'three/webgpu';
import { BIRD_STRIDE, birdMesh, packBird, type BirdPose } from '../birds';

export class BirdBatch {
  readonly mesh: Mesh<InstancedBufferGeometry>;
  private readonly place: InstancedBufferAttribute;
  private readonly turn: InstancedBufferAttribute;
  private readonly look: InstancedBufferAttribute;
  private readonly origin = new Vector3();
  private n = 0;

  /** `material`: the game's registered `birdMaterial()`. At most `capacity` birds are drawn. */
  constructor(material: Material, readonly capacity: number) {
    const body = birdMesh();
    const g = new InstancedBufferGeometry();
    g.setAttribute('position', new BufferAttribute(body.positions, 3));
    g.setAttribute('bPart', new BufferAttribute(body.parts, 2));
    g.setIndex(new BufferAttribute(body.indices, 1));
    const attr = (name: string) => {
      const a = new InstancedBufferAttribute(new Float32Array(capacity * BIRD_STRIDE), BIRD_STRIDE);
      a.setUsage(DynamicDrawUsage);
      g.setAttribute(name, a);
      return a;
    };
    this.place = attr('bPlace');
    this.turn = attr('bTurn');
    this.look = attr('bLook');
    g.instanceCount = 1;
    // Placed by the shader, anywhere around the origin.
    g.boundingSphere = new Sphere(new Vector3(), Infinity);
    this.mesh = new Mesh(g, material);
    this.mesh.name = 'birds';
    this.mesh.frustumCulled = false;
    this.mesh.castShadow = false;
    this.mesh.receiveShadow = true;
    // Visible until the first frame (one bird of size 0, so nothing shows): the game's warm-up compiles it.
  }

  /** How many birds this frame holds. */
  get count(): number { return this.n; }

  /** Starts a frame's birds, placed relative to (x, y, z): somewhere near the camera. */
  begin(x: number, y: number, z: number): void {
    this.origin.set(x, y, z);
    this.mesh.position.copy(this.origin);
    this.mesh.updateMatrix();
    this.n = 0;
  }

  /** One bird; false when the batch is full. */
  add(p: BirdPose): boolean {
    if (this.n >= this.capacity) return false;
    packBird(p, this.origin, this.place.array as Float32Array, this.turn.array as Float32Array, this.look.array as Float32Array, this.n++);
    return true;
  }

  /** Hands the frame's birds to the GPU (only the part in use). */
  end(): void {
    const used = this.n * BIRD_STRIDE;
    for (const a of [this.place, this.turn, this.look]) {
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
