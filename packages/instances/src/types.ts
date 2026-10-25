import type { BufferGeometry, Camera, Group, Material, Vector3 } from 'three/webgpu';
import type { LodRange } from './select';

/** One mesh drawn per instance of a level: a geometry and its material (the material reads iM0..iM3). */
export interface DrawPart {
  geometry: BufferGeometry;
  material: Material;
  castShadow?: boolean;
  receiveShadow?: boolean;
  /** Draw order among opaque meshes (three's renderOrder), e.g. a depth pre-pass before its colour pass. */
  renderOrder?: number;
  name?: string;
}

/** A level of detail and the parts drawn at it. */
export interface DrawLod extends LodRange { parts: DrawPart[] }

/** A kind of instance (a tree species, a building type): its levels, nearest first. */
export interface DrawKind { lods: DrawLod[] }

export interface DrawOptions {
  /** Distances across the ground (x, z) instead of in 3D. */
  horizontal?: boolean;
  /**
   * The light's direction (where it shines to, normalized) and how far shadows reach (m), read on every
   * update: instances outside the view whose shadows could fall into it stay drawn (the shadow pass draws
   * the same list).
   */
  shadow?: { dir: Vector3; reach: number };
  /** CPU path: choose the levels again once the camera has moved this far (m). Default 8. */
  step?: number;
  /** Instances to make room for at first (they grow as needed). Default 4096. */
  capacity?: number;
  /** Always the CPU path. */
  cpu?: boolean;
}

/** Instances of several kinds, each drawn at the level its distance asks for. */
export interface InstanceDraws {
  /** Every mesh; add it to the scene (once its shaders are built). */
  readonly group: Group;
  /** 'gpu': culled and packed by compute passes, drawn indirectly. 'cpu': levels chosen on the CPU, no view culling. */
  readonly path: 'gpu' | 'cpu';
  /** The instances: `count` records of RECORD floats (matrix, kind, dither). Copied; `data` may be reused. */
  set(data: Float32Array, count: number): void;
  /** Every frame before rendering. */
  update(camera: Camera): void;
  /** Builds what the path needs ahead (the GPU path's compute shaders); call behind the loading screen. */
  ready(): Promise<void>;
  /**
   * Builds the draw shaders with `compile` (e.g. a Stage's prepare) on the group, every part with at least one
   * instance meanwhile (kinds not around yet included), then puts the real counts back.
   */
  prepare(compile: (group: Group) => Promise<void>): Promise<void>;
  /** Instances drawn per part, in group order (the GPU path reads them back: for checks and HUDs, not every frame). */
  counts(): Promise<number[]>;
  dispose(): void;
}
