/**
 * Procedural trees and shrubs (geometry; materials in ./node, textures in ./textures). From Scale.
 *
 * Everything is generated in code and deterministic per (species, variant):
 *  - wood: recursive branching (per-species level parameters, gravitropism, random curvature),
 *    every branch is limited by a species crown envelope so silhouettes read as the real species;
 *  - leaves: alpha-tested cards carrying whole twig clusters from a procedural leaf atlas,
 *    with spherical (crown-ellipsoid) normals for soft canopy lighting and baked crown occlusion;
 *  - far: a ≤150-triangle canopy hull (envelope-shaped, noise-dissolved edges in the shader).
 *
 * Materials are instancing-ready: wind phase comes from the instance's world position, the wind
 * direction is world-space (instances may have any yaw / uniform scale). Shadow casters must use
 * the matching depth material (applyVegetationShadow) so shadows sway and are leaf-shaped.
 *
 * Extra (optional) attributes beyond the documented ones:
 *  - aOcc  (float, 0 = open, 1 = deep inside the crown) on wood + leaves: baked crown occlusion.
 *  - wood uv.x encodes the bark atlas strip: uv.x = strip * 16 + u (u wraps around the branch).
 *  - far: color (vec3 linear), aAutumn (vec3 linear autumn colour), uv = (kind, deciduous).
 */
import * as THREE from 'three';
import { Noise, Rng, clamp, smoothstep as smooth } from '@futuremagic/core';

export type TreeSpecies = 'plane' | 'linden' | 'maple' | 'oak' | 'birch' | 'pine' | 'palm' | 'cypress' | 'chestnut' | 'ginkgo';
export const TREE_SPECIES: TreeSpecies[] = ['plane', 'linden', 'maple', 'oak', 'birch', 'pine', 'palm', 'cypress', 'chestnut', 'ginkgo'];

export interface TreeModel {
  species: TreeSpecies;
  height: number;
  trunkRadius: number;
  wood: THREE.BufferGeometry;
  leaves: THREE.BufferGeometry;
  far: THREE.BufferGeometry;
  /** true for shrubModel() results. */
  isShrub?: boolean;
  /** Crown radius (m), handy for spacing / culling. */
  crownRadius?: number;
}

/** sRGB channel to linear. */
export const srgbToLinear = (c: number): number => (c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4));
const srgbToLin = srgbToLinear;

export const vegetationUniforms = {
  uTime: { value: 0 },
  /** 0 = calm, 1 = strong breeze, 2 = storm. */
  uWind: { value: 0.5 },
  /** 0 = summer green, 0.5 = early autumn, 1 = full autumn colours (evergreens ignore it). */
  uSeason: { value: 0 },
  /** A floating origin the instances are drawn relative to (set it to @futuremagic/stage FloatingOrigin's `at`). */
  uOrigin: { value: new THREE.Vector3() },
};

// ---------------------------------------------------------------------------------------------
// Small math helpers
// ---------------------------------------------------------------------------------------------

type V3 = THREE.Vector3;
const UP = new THREE.Vector3(0, 1, 0);
const v3 = (x = 0, y = 0, z = 0) => new THREE.Vector3(x, y, z);
const deg = Math.PI / 180;

function perpBasis(t: V3): [V3, V3] {
  const ref = Math.abs(t.y) < 0.92 ? UP : new THREE.Vector3(1, 0, 0);
  const p1 = new THREE.Vector3().crossVectors(t, ref).normalize();
  const p2 = new THREE.Vector3().crossVectors(t, p1).normalize();
  return [p1, p2];
}

function randUnit(rng: Rng): V3 {
  const o = rng.onSphere();
  return new THREE.Vector3(o[0], o[1], o[2]);
}

// ---------------------------------------------------------------------------------------------
// Geometry builder
// ---------------------------------------------------------------------------------------------

class VegBuilder {
  pos: number[] = [];
  nrm: number[] = [];
  uv: number[] = [];
  wind: number[] = [];
  tint: number[] = [];
  occ: number[] = [];
  idx: number[] = [];
  get count() { return this.pos.length / 3; }
  vert(p: V3, n: V3, u: number, v: number, w: number, tint: number, occ: number): number {
    this.pos.push(p.x, p.y, p.z);
    this.nrm.push(n.x, n.y, n.z);
    this.uv.push(u, v);
    this.wind.push(w);
    this.tint.push(tint);
    this.occ.push(occ);
    return this.count - 1;
  }
  tri(a: number, b: number, c: number) { this.idx.push(a, b, c); }
  build(withTint: boolean): THREE.BufferGeometry {
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.Float32BufferAttribute(this.pos, 3));
    g.setAttribute('normal', new THREE.Float32BufferAttribute(this.nrm, 3));
    g.setAttribute('uv', new THREE.Float32BufferAttribute(this.uv, 2));
    g.setAttribute('aWind', new THREE.Float32BufferAttribute(this.wind, 1));
    if (withTint) g.setAttribute('aLeafTint', new THREE.Float32BufferAttribute(this.tint, 1));
    g.setAttribute('aOcc', new THREE.Float32BufferAttribute(this.occ, 1));
    g.setIndex(this.count > 65535 ? new THREE.Uint32BufferAttribute(this.idx, 1) : new THREE.Uint16BufferAttribute(this.idx, 1));
    g.computeBoundingBox();
    g.computeBoundingSphere();
    return g;
  }
}

// ---------------------------------------------------------------------------------------------
// Crown envelope
// ---------------------------------------------------------------------------------------------

class Envelope {
  constructor(
    public base: number,
    public top: number,
    public rx: number,
    public rz: number,
    public prof: (t: number) => number,
    public cx = 0,
    public cz = 0,
  ) {}
  get cy() { return (this.base + this.top) * 0.5; }
  get ry() { return (this.top - this.base) * 0.5; }
  /** Normalised "radius" (≈1 on the envelope surface). */
  rel(p: V3): number {
    const t = (p.y - this.base) / (this.top - this.base);
    if (t > 1) return 1 + (t - 1) * 4;
    const f = Math.max(0.02, this.prof(clamp(t, 0, 1)));
    const dx = (p.x - this.cx) / (this.rx * f), dz = (p.z - this.cz) / (this.rz * f);
    const r = Math.sqrt(dx * dx + dz * dz);
    return t < 0 ? Math.max(r, 1 + -t * 3) : r;
  }
  inside(p: V3, m = 1): boolean { return this.rel(p) <= m; }
  /** Ellipsoid-ish normal + depth (0 centre, 1 surface) for lighting. */
  shade(p: V3, out: V3): number {
    out.set((p.x - this.cx) / this.rx, (p.y - this.cy) / this.ry, (p.z - this.cz) / this.rz);
    const d = out.length();
    if (d < 1e-4) out.set(0, 1, 0);
    else out.multiplyScalar(1 / d);
    return d;
  }
  /** Distance from centre to envelope along a direction (for far hulls). */
  extent(dir: V3): number {
    const c = v3(this.cx, this.cy, this.cz);
    const p = v3();
    const maxR = Math.max(this.rx, this.rz, this.ry) * 1.6;
    let last = 0;
    for (let s = 0.05; s < maxR; s += 0.08) {
      p.copy(c).addScaledVector(dir, s);
      if (this.inside(p, 1)) last = s;
      else if (s > last + 1) break;
    }
    return last;
  }
}

// ---------------------------------------------------------------------------------------------
// Species configuration
// ---------------------------------------------------------------------------------------------

interface LevelCfg {
  n: [number, number];
  start: number;
  end: number;
  angle: number;
  angleVar: number;
  /** length: multiple of crown radius ('width') or of parent length ('parent'). */
  len: number;
  lenRef: 'width' | 'parent';
  rr: number;
  segs: number;
  radial: number;
  up: number;
  curve: number;
  phyllo: number;
  whorl?: number;
  /** extra length factor along the parent: f(t) where t = attach fraction. */
  lenProfile?: (t: number) => number;
}

type CardMode = 'cluster' | 'flat' | 'up' | 'tuft';

interface SpeciesCfg {
  height: [number, number];
  trunkR: number;
  bark: number;
  leafCell: number;
  leafSize: number;
  density: number;
  leafStart: number;
  cardMode: CardMode;
  width: number;
  crownBase: number;
  prof: (t: number) => number;
  trunkTop: number;
  trunkUp: number;
  trunkCurve: number;
  lean: number;
  flare: number;
  lobes: number;
  levels: LevelCfg[];
  /** levels whose branches carry leaves (default: last level). */
  leafLevels?: number[];
  /** cards on the trunk itself (columnar conifers). */
  trunkLeaves?: number;
  /** canopy colour for far LOD (sRGB) and autumn colour (sRGB). */
  farColor: [number, number, number];
  autumn: [number, number, number];
  evergreen?: boolean;
  /** leaf cards per tuft (crossed). */
  cross?: number;
  /** target number of leaf tufts (overrides density when given). */
  cards?: number;
}

const L = (o: Partial<LevelCfg> & Pick<LevelCfg, 'n'>): LevelCfg => ({
  start: 0.2, end: 1, angle: 45, angleVar: 12, len: 0.5, lenRef: 'parent', rr: 0.55,
  segs: 4, radial: 5, up: 0.05, curve: 0.25, phyllo: 137.5, ...o,
});

function speciesCfg(sp: TreeSpecies | 'shrub', variant: number): SpeciesCfg {
  switch (sp) {
    case 'plane':
      return {
        height: [14, 18], trunkR: 0.36, bark: 3, leafCell: 0, cards: 1700, leafSize: 1.35, density: 4.2, leafStart: 0.25, cardMode: 'cluster',
        width: 7.2, crownBase: 0.24, prof: (t) => Math.pow(Math.sin(Math.PI * Math.pow(t, 0.8)), 0.55),
        trunkTop: 0.3, trunkUp: 0, trunkCurve: 0.08, lean: 0.04, flare: 0.35, lobes: 0.06,
        levels: [
          L({ n: [3, 4], start: 1, end: 1, whorl: 4, angle: 32, angleVar: 10, len: 1.25, lenRef: 'width', rr: 0.72, segs: 8, radial: 8, up: 0.06, curve: 0.22 }),
          L({ n: [8, 10], start: 0.18, end: 0.98, angle: 52, angleVar: 15, len: 0.55, rr: 0.5, segs: 4, radial: 5, up: 0.04, curve: 0.3 }),
          L({ n: [3, 4], start: 0.3, end: 1, angle: 48, angleVar: 15, len: 0.45, rr: 0.55, segs: 2, radial: 3, up: 0.0, curve: 0.3 }),
        ],
        farColor: [0.36, 0.45, 0.22], autumn: [0.72, 0.55, 0.25],
      };
    case 'linden':
      return {
        height: [13, 16], trunkR: 0.3, bark: 0, leafCell: 1, cards: 1600, leafSize: 1.15, density: 5.5, leafStart: 0.2, cardMode: 'cluster',
        width: 4.6, crownBase: 0.2, prof: (t) => Math.pow(Math.sin(Math.PI * Math.pow(t, 0.85)), 0.7),
        trunkTop: 0.93, trunkUp: 0.02, trunkCurve: 0.05, lean: 0.02, flare: 0.3, lobes: 0.03,
        levels: [
          L({ n: [15, 19], start: 0.2, end: 0.92, angle: 58, angleVar: 12, len: 1.5, lenRef: 'width', rr: 0.42, segs: 5, radial: 6, up: 0.1, curve: 0.2 }),
          L({ n: [5, 7], start: 0.2, end: 0.95, angle: 48, angleVar: 14, len: 0.5, rr: 0.55, segs: 3, radial: 4, up: -0.04, curve: 0.3 }),
        ],
        leafLevels: [1, 2],
        farColor: [0.3, 0.42, 0.18], autumn: [0.82, 0.68, 0.22],
      };
    case 'maple':
      return {
        height: [11, 14], trunkR: 0.3, bark: 0, leafCell: 2, cards: 1500, leafSize: 1.2, density: 4.6, leafStart: 0.25, cardMode: 'cluster',
        width: 5.2, crownBase: 0.26, prof: (t) => Math.pow(Math.sin(Math.PI * Math.pow(t, 0.9)), 0.5),
        trunkTop: 0.3, trunkUp: 0, trunkCurve: 0.06, lean: 0.03, flare: 0.3, lobes: 0.04,
        levels: [
          L({ n: [4, 5], start: 1, end: 1, whorl: 5, angle: 30, angleVar: 10, len: 1.3, lenRef: 'width', rr: 0.65, segs: 7, radial: 7, up: 0.08, curve: 0.2 }),
          L({ n: [7, 9], start: 0.2, end: 0.98, angle: 50, angleVar: 14, len: 0.55, rr: 0.5, segs: 3, radial: 4, up: 0.05, curve: 0.3 }),
          L({ n: [3, 3], start: 0.35, end: 1, angle: 45, angleVar: 12, len: 0.45, rr: 0.55, segs: 2, radial: 3, up: 0.02, curve: 0.3 }),
        ],
        farColor: [0.27, 0.4, 0.16], autumn: [0.85, 0.3, 0.08],
      };
    case 'oak':
      return {
        height: [12, 15], trunkR: 0.46, bark: 1, leafCell: 3, cards: 1700, leafSize: 1.15, density: 4.6, leafStart: 0.25, cardMode: 'cluster',
        width: 8, crownBase: 0.2, prof: (t) => Math.pow(Math.sin(Math.PI * Math.pow(t, 0.72)), 0.45),
        trunkTop: 0.26, trunkUp: 0, trunkCurve: 0.14, lean: 0.06, flare: 0.45, lobes: 0.1,
        levels: [
          L({ n: [4, 5], start: 0.7, end: 1, whorl: 1, phyllo: 140, angle: 66, angleVar: 12, len: 1.3, lenRef: 'width', rr: 0.62, segs: 9, radial: 8, up: 0.0, curve: 0.95 }),
          L({ n: [7, 9], start: 0.15, end: 0.98, angle: 60, angleVar: 18, len: 0.55, rr: 0.5, segs: 4, radial: 4, up: 0.02, curve: 0.85 }),
          L({ n: [3, 4], start: 0.3, end: 1, angle: 50, angleVar: 18, len: 0.45, rr: 0.55, segs: 2, radial: 3, up: 0.02, curve: 0.5 }),
        ],
        farColor: [0.26, 0.36, 0.15], autumn: [0.55, 0.36, 0.12],
      };
    case 'birch':
      return {
        height: [13, 16], trunkR: 0.17, bark: 2, leafCell: 4, cards: 1150, leafSize: 0.95, density: 6.5, leafStart: 0.15, cardMode: 'cluster',
        width: 3.0, crownBase: 0.3, prof: (t) => Math.pow(Math.sin(Math.PI * Math.pow(t, 0.75)), 0.9) * (1 - 0.25 * t),
        trunkTop: 0.96, trunkUp: 0.02, trunkCurve: 0.07, lean: 0.05, flare: 0.15, lobes: 0,
        levels: [
          L({ n: [20, 26], start: 0.28, end: 0.95, angle: 48, angleVar: 12, len: 1.6, lenRef: 'width', rr: 0.36, segs: 5, radial: 4, up: 0.02, curve: 0.25 }),
          L({ n: [4, 5], start: 0.25, end: 0.95, angle: 40, angleVar: 14, len: 0.6, rr: 0.55, segs: 3, radial: 3, up: -0.22, curve: 0.2 }),
        ],
        leafLevels: [1, 2],
        farColor: [0.38, 0.5, 0.22], autumn: [0.9, 0.75, 0.25],
      };
    case 'pine':
      if ((variant & 1) === 0) {
        // Stone / umbrella pine: tall bare trunk, flat spreading crown.
        return {
          height: [12, 15], trunkR: 0.3, bark: 4, leafCell: 8, cards: 950, leafSize: 1.05, density: 5, leafStart: 0.35, cardMode: 'tuft',
          width: 6, crownBase: 0.58,
          prof: (t) => (t < 0.45 ? Math.pow(t / 0.45, 0.6) : Math.sqrt(Math.max(0, 1 - Math.pow((t - 0.45) / 0.55, 2.4)))),
          trunkTop: 0.6, trunkUp: 0.03, trunkCurve: 0.12, lean: 0.1, flare: 0.25, lobes: 0.03,
          levels: [
            L({ n: [4, 5], start: 1, end: 1, whorl: 5, angle: 42, angleVar: 10, len: 1.3, lenRef: 'width', rr: 0.65, segs: 6, radial: 6, up: 0.1, curve: 0.3 }),
            L({ n: [5, 7], start: 0.35, end: 0.98, angle: 45, angleVar: 14, len: 0.5, rr: 0.5, segs: 3, radial: 4, up: 0.08, curve: 0.3 }),
            L({ n: [3, 4], start: 0.4, end: 1, angle: 40, angleVar: 14, len: 0.4, rr: 0.55, segs: 2, radial: 3, up: 0.1, curve: 0.3 }),
          ],
          farColor: [0.17, 0.3, 0.14], autumn: [0.17, 0.3, 0.14], evergreen: true, cross: 2,
        };
      }
      // Conical, whorled pine / spruce form.
      return {
        height: [12, 16], trunkR: 0.27, bark: 4, leafCell: 10, cards: 1800, leafSize: 1.1, density: 3.4, leafStart: 0.1, cardMode: 'flat',
        width: 3.4, crownBase: 0.1, prof: (t) => Math.pow(1 - t, 0.95) * Math.min(1, 0.55 + t * 4),
        trunkTop: 1.0, trunkUp: 0.03, trunkCurve: 0.03, lean: 0.015, flare: 0.25, lobes: 0.02,
        levels: [
          L({ n: [22, 26], whorl: 4, phyllo: 41, start: 0.1, end: 0.97, angle: 82, angleVar: 8, len: 1.4, lenRef: 'width', rr: 0.32, segs: 4, radial: 4, up: -0.02, curve: 0.12 }),
        ],
        leafLevels: [1],
        trunkLeaves: 3,
        farColor: [0.13, 0.25, 0.14], autumn: [0.13, 0.25, 0.14], evergreen: true,
      };
    case 'cypress':
      return {
        height: [12, 16], trunkR: 0.24, bark: 6, leafCell: 9, cards: 1500, leafSize: 0.72, density: 9, leafStart: 0.0, cardMode: 'up',
        width: 1.0, crownBase: 0.03, prof: (t) => Math.pow(Math.min(1, t * 5 + 0.25), 0.5) * Math.pow(1 - t, 0.62),
        trunkTop: 0.98, trunkUp: 0.05, trunkCurve: 0.02, lean: 0.01, flare: 0.2, lobes: 0.04,
        levels: [
          L({ n: [44, 56], start: 0.04, end: 0.96, angle: 22, angleVar: 8, len: 2.2, lenRef: 'width', rr: 0.32, segs: 3, radial: 3, up: 0.25, curve: 0.15 }),
        ],
        leafLevels: [1],
        trunkLeaves: 9,
        farColor: [0.11, 0.22, 0.1], autumn: [0.11, 0.22, 0.1], evergreen: true,
      };
    case 'chestnut':
      return {
        height: [14, 17], trunkR: 0.42, bark: 1, leafCell: 5, cards: 1700, leafSize: 1.35, density: 4.4, leafStart: 0.25, cardMode: 'cluster',
        width: 6.2, crownBase: 0.24, prof: (t) => Math.pow(Math.sin(Math.PI * Math.pow(t, 0.8)), 0.55),
        trunkTop: 0.32, trunkUp: 0, trunkCurve: 0.08, lean: 0.03, flare: 0.35, lobes: 0.06,
        levels: [
          L({ n: [3, 4], start: 1, end: 1, whorl: 4, angle: 30, angleVar: 9, len: 1.3, lenRef: 'width', rr: 0.7, segs: 8, radial: 8, up: 0.07, curve: 0.2 }),
          L({ n: [8, 10], start: 0.15, end: 0.98, angle: 55, angleVar: 14, len: 0.55, rr: 0.5, segs: 4, radial: 4, up: -0.03, curve: 0.25 }),
          L({ n: [3, 4], start: 0.3, end: 1, angle: 45, angleVar: 12, len: 0.45, rr: 0.55, segs: 2, radial: 3, up: 0.06, curve: 0.25 }),
        ],
        farColor: [0.24, 0.36, 0.14], autumn: [0.62, 0.42, 0.16],
      };
    case 'ginkgo':
      return {
        height: [12, 15], trunkR: 0.27, bark: 7, leafCell: 6, cards: 1150, leafSize: 1.0, density: 4.6, leafStart: 0.2, cardMode: 'cluster',
        width: 3.6, crownBase: 0.2, prof: (t) => Math.pow(Math.sin(Math.PI * Math.pow(t, 0.62)), 0.75) * (1 - 0.3 * t),
        trunkTop: 0.94, trunkUp: 0.02, trunkCurve: 0.05, lean: 0.03, flare: 0.2, lobes: 0.03,
        levels: [
          L({ n: [10, 13], start: 0.2, end: 0.9, angle: 48, angleVar: 20, len: 1.5, lenRef: 'width', rr: 0.42, segs: 5, radial: 5, up: 0.16, curve: 0.3 }),
          L({ n: [4, 5], start: 0.2, end: 0.95, angle: 48, angleVar: 16, len: 0.45, rr: 0.55, segs: 3, radial: 3, up: 0.1, curve: 0.3 }),
        ],
        leafLevels: [1, 2],
        farColor: [0.36, 0.48, 0.2], autumn: [0.98, 0.78, 0.12],
      };
    case 'shrub': {
      const box = (variant & 1) === 1;
      return {
        height: [1.2, 1.8], trunkR: 0.035, bark: 7, leafCell: box ? 11 : 7, cards: 320, leafSize: 0.5, density: 15, leafStart: 0.1, cardMode: 'cluster',
        width: 0.85, crownBase: 0.04, prof: (t) => Math.pow(Math.sin(Math.PI * Math.pow(t, 0.75)), 0.55),
        trunkTop: 0.02, trunkUp: 0, trunkCurve: 0, lean: 0, flare: 0, lobes: 0,
        levels: [
          L({ n: [6, 7], start: 1, end: 1, whorl: 7, angle: 38, angleVar: 16, len: 1.6, lenRef: 'width', rr: 1.0, segs: 4, radial: 4, up: 0.2, curve: 0.3 }),
          L({ n: [3, 4], start: 0.25, end: 0.95, angle: 45, angleVar: 14, len: 0.5, rr: 0.6, segs: 2, radial: 3, up: 0.1, curve: 0.3 }),
        ],
        leafLevels: [1, 2],
        farColor: box ? [0.16, 0.28, 0.12] : [0.27, 0.4, 0.17], autumn: box ? [0.16, 0.28, 0.12] : [0.7, 0.35, 0.12], evergreen: box,
      };
    }
    default:
      return speciesCfg('linden', variant);
  }
}

// ---------------------------------------------------------------------------------------------
// Branch growth
// ---------------------------------------------------------------------------------------------

interface Branch {
  pts: V3[];
  rad: number[];
  /** cumulative arc length per point */
  arc: number[];
  level: number;
  /** path distance from the root at the branch base */
  d0: number;
  children: Branch[];
}

function branchLen(b: Branch) { return b.arc[b.arc.length - 1]; }

function sampleBranch(b: Branch, t: number, outP: V3, outT: V3): number {
  const total = branchLen(b);
  const s = clamp(t, 0, 1) * total;
  let i = 1;
  while (i < b.arc.length - 1 && b.arc[i] < s) i++;
  const a0 = b.arc[i - 1], a1 = b.arc[i];
  const f = a1 > a0 ? (s - a0) / (a1 - a0) : 0;
  outP.lerpVectors(b.pts[i - 1], b.pts[i], f);
  outT.subVectors(b.pts[i], b.pts[i - 1]).normalize();
  return b.rad[i - 1] + (b.rad[i] - b.rad[i - 1]) * f;
}

function makeBranch(pts: V3[], r0: number, rTip: number, level: number, d0: number, taperPow = 1): Branch {
  const arc = [0];
  for (let i = 1; i < pts.length; i++) arc.push(arc[i - 1] + pts[i].distanceTo(pts[i - 1]));
  const total = arc[arc.length - 1] || 1;
  const rad = arc.map((a) => rTip + (r0 - rTip) * Math.pow(1 - a / total, taperPow));
  return { pts, rad, arc, level, d0, children: [] };
}

function growPath(rng: Rng, start: V3, dir: V3, len: number, segs: number, up: number, curve: number, env: Envelope | null, minLen: number): V3[] {
  const pts = [start.clone()];
  const d = dir.clone().normalize();
  const p = start.clone();
  const segL = len / segs;
  let acc = 0;
  for (let i = 0; i < segs; i++) {
    if (i > 0) {
      d.addScaledVector(UP, up * segL);
      d.addScaledVector(randUnit(rng), curve * Math.sqrt(segL) * 0.45);
      d.normalize();
    }
    const np = p.clone().addScaledVector(d, segL);
    if (env && acc + segL > minLen && !env.inside(np, 1)) {
      // bisect to the envelope boundary
      let lo = 0, hi = 1;
      const q = v3();
      for (let k = 0; k < 6; k++) {
        const m = (lo + hi) / 2;
        q.copy(p).addScaledVector(d, segL * m);
        if (env.inside(q, 1)) lo = m; else hi = m;
      }
      if (lo * segL > 0.08) pts.push(p.clone().addScaledVector(d, segL * lo));
      break;
    }
    p.copy(np);
    acc += segL;
    pts.push(p.clone());
  }
  return pts;
}

interface TreeSkeleton {
  branches: Branch[];
  env: Envelope;
  height: number;
  maxPath: number;
}

function buildSkeleton(cfg: SpeciesCfg, rng: Rng): TreeSkeleton {
  const H = rng.range(cfg.height[0], cfg.height[1]);
  const wScale = rng.range(0.88, 1.12);
  const branches: Branch[] = [];

  // Trunk
  const leanDir = randUnit(rng).setY(0).normalize();
  const trunkDir = UP.clone().addScaledVector(leanDir, cfg.lean * rng.range(0.4, 1.2)).normalize();
  const trunkLen = Math.max(0.05, H * cfg.trunkTop);
  const trunkSegs = trunkLen < 0.5 ? 1 : Math.max(6, Math.round(trunkLen / 0.7));
  const tPts = growPath(rng, v3(0, -0.15, 0), trunkDir, trunkLen + 0.15, trunkSegs, cfg.trunkUp, cfg.trunkCurve, null, 0);
  const excurrent = cfg.trunkTop > 0.8;
  const trunkR = cfg.trunkR * rng.range(0.9, 1.1);
  const trunk = makeBranch(tPts, trunkR * 1.05, excurrent ? 0.02 : trunkR * 0.78, 0, 0, excurrent ? 0.9 : 1);
  branches.push(trunk);
  const top = tPts[tPts.length - 1];

  const envBase = H * cfg.crownBase;
  const env = new Envelope(
    envBase, H,
    cfg.width * wScale * rng.range(0.92, 1.08), cfg.width * wScale * rng.range(0.92, 1.08),
    cfg.prof,
    excurrent ? top.x * 0.4 + rng.range(-0.2, 0.2) : top.x + rng.range(-0.3, 0.3),
    excurrent ? top.z * 0.4 + rng.range(-0.2, 0.2) : top.z + rng.range(-0.3, 0.3),
  );

  const P = v3(), T = v3();
  const spawn = (parent: Branch, li: number) => {
    const lv = cfg.levels[li];
    if (!lv) return;
    const nodes = rng.int(lv.n[0], lv.n[1]);
    const perNode = lv.whorl && lv.start < 1 ? lv.whorl : 1;
    const isTop = lv.start >= 1;
    let az = rng.range(0, Math.PI * 2);
    const pLen = branchLen(parent);
    const count = isTop ? nodes : nodes;
    for (let k = 0; k < count; k++) {
      const t = isTop ? 1 : lv.start + (lv.end - lv.start) * ((k + 0.5 + rng.range(-0.35, 0.35)) / count);
      const pr = sampleBranch(parent, t, P, T);
      for (let w = 0; w < perNode; w++) {
        let a = az + (perNode > 1 ? (w / perNode) * Math.PI * 2 + rng.range(-0.25, 0.25) : 0);
        if (isTop) a = az + (k / count) * Math.PI * 2 + rng.range(-0.3, 0.3);
        const ang = (lv.angle + rng.range(-lv.angleVar, lv.angleVar)) * deg;
        const [p1, p2] = perpBasis(T);
        const mk = (aa: number) => {
          const radial = p1.clone().multiplyScalar(Math.cos(aa)).addScaledVector(p2, Math.sin(aa));
          return T.clone().multiplyScalar(Math.cos(ang)).addScaledVector(radial, Math.sin(ang)).normalize();
        };
        let dir = mk(a);
        if (dir.y < -0.3 && li > 0) dir = mk(a + Math.PI);
        let len = lv.lenRef === 'width' ? lv.len * env.rx : lv.len * pLen * (1 - t * 0.45);
        len *= rng.range(0.75, 1.1) * (lv.lenProfile ? lv.lenProfile(t) : 1);
        const segs = Math.max(1, lv.segs);
        const minLen = Math.min(len, lv.lenRef === 'width' ? 0.8 : 0.25);
        const pts = growPath(rng, P, dir, len, segs, lv.up, lv.curve, env, minLen);
        if (pts.length < 2) continue;
        const r0 = Math.max(0.008, pr * lv.rr * rng.range(0.85, 1.05));
        const parentArcAt = parent.d0 + t * pLen;
        const b = makeBranch(pts, r0, Math.max(0.004, r0 * 0.18), li + 1, parentArcAt);
        parent.children.push(b);
        branches.push(b);
        spawn(b, li + 1);
      }
      az += lv.phyllo * deg + rng.range(-0.3, 0.3);
    }
  };
  spawn(trunk, 0);

  let maxPath = 1, maxY = 0;
  for (const b of branches) {
    maxPath = Math.max(maxPath, b.d0 + branchLen(b));
    for (const p of b.pts) maxY = Math.max(maxY, p.y);
  }
  return { branches, env, height: Math.max(H, maxY), maxPath };
}

// ---------------------------------------------------------------------------------------------
// Wood mesh
// ---------------------------------------------------------------------------------------------

/** Bark texture strips side by side in the bark atlas (wood uv.x = strip * 16 + u). */
export const BARK_STRIPS = 8;
const woodNoise = new Noise(0x7ee5);

function tube(bld: VegBuilder, b: Branch, radial: number, strip: number, maxPath: number, env: Envelope | null, trunk: SpeciesCfg | null, seed: number) {
  const n = b.pts.length;
  if (n < 2) return;
  // parallel transport frames
  const tans: V3[] = [];
  for (let i = 0; i < n; i++) {
    const a = b.pts[Math.max(0, i - 1)], c = b.pts[Math.min(n - 1, i + 1)];
    tans.push(c.clone().sub(a).normalize());
  }
  let [nx, ny] = perpBasis(tans[0]);
  const frames: [V3, V3][] = [];
  for (let i = 0; i < n; i++) {
    if (i > 0) {
      const q = new THREE.Quaternion().setFromUnitVectors(tans[i - 1], tans[i]);
      nx = nx.clone().applyQuaternion(q);
      ny = new THREE.Vector3().crossVectors(tans[i], nx).normalize();
      nx = new THREE.Vector3().crossVectors(ny, tans[i]).normalize();
    }
    frames.push([nx, ny]);
  }
  const r0 = b.rad[0];
  const wraps = Math.max(1, Math.round((2 * Math.PI * r0) / 0.55));
  const wrapWidth = (2 * Math.PI * Math.max(r0, 0.02)) / wraps;
  const base = bld.count;
  let v = (seed % 97) * 0.173;
  const p = v3(), nn = v3(), sh = v3();
  for (let i = 0; i < n; i++) {
    if (i > 0) v += b.pts[i].distanceTo(b.pts[i - 1]) / (wrapWidth * 4 * Math.max(0.35, b.rad[i] / r0));
    const c = b.pts[i];
    let r = b.rad[i];
    const y = c.y;
    if (trunk) r *= 1 + trunk.flare * Math.exp(-Math.max(0, y) / 0.45);
    const w = (b.d0 + b.arc[i]) / maxPath;
    let occ = 0;
    if (env) {
      const d = env.shade(c, sh);
      if (d < 1.05) occ = 0.55 * (1 - smooth(0.2, 1.05, d));
    }
    occ = Math.max(occ, 0.5 * Math.exp(-Math.max(0, y) / 0.35));
    const [fx, fy] = frames[i];
    for (let j = 0; j <= radial; j++) {
      const a = (j / radial) * Math.PI * 2;
      const ca = Math.cos(a), sa = Math.sin(a);
      nn.copy(fx).multiplyScalar(ca).addScaledVector(fy, sa);
      let rr = r;
      if (trunk && trunk.lobes > 0) {
        const k = woodNoise.n2(ca * 1.3 + seed * 0.01, y * 0.35) * 0.6 + woodNoise.n2(sa * 2.1, y * 0.9 + 4.2) * 0.4;
        rr *= 1 + trunk.lobes * k * (1 + 1.5 * Math.exp(-Math.max(0, y) / 0.8));
      }
      p.copy(c).addScaledVector(nn, rr);
      bld.vert(p, nn, strip * 16 + (j / radial) * wraps, v, w, 0, occ);
    }
  }
  const rs = radial + 1;
  for (let i = 0; i < n - 1; i++) {
    for (let j = 0; j < radial; j++) {
      const a = base + i * rs + j, b2 = a + rs;
      // Counter-clockwise seen from outside (the ring runs counter-clockwise around the branch
      // direction): the bark is front-sided, and the opposite winding showed the trunks inside-out.
      bld.tri(a, a + 1, b2);
      bld.tri(a + 1, b2 + 1, b2);
    }
  }
}

function buildWood(cfg: SpeciesCfg, sk: TreeSkeleton, seed: number): THREE.BufferGeometry {
  const bld = new VegBuilder();
  sk.branches.forEach((b, i) => {
    const radial = b.level === 0 ? (cfg.trunkR > 0.1 ? 10 : 6) : cfg.levels[b.level - 1].radial;
    tube(bld, b, radial, cfg.bark, sk.maxPath, b.level === 0 ? null : sk.env, b.level === 0 ? cfg : null, seed + i * 7);
  });
  return bld.build(false);
}

// ---------------------------------------------------------------------------------------------
// Leaf cards
// ---------------------------------------------------------------------------------------------

const ATLAS_GRID = 4;
/** atlas uv for a cell: (u,v) in [0,1], v = 0 at the card base. */
function cellUV(cell: number, u: number, v: number, wideCells = 1): [number, number] {
  const cx = cell % ATLAS_GRID, cy = Math.floor(cell / ATLAS_GRID);
  const m = 0.006;
  const uu = (cx + m + u * (wideCells - 2 * m)) / ATLAS_GRID;
  const vv = (cy + 1 - m - v * (1 - 2 * m)) / ATLAS_GRID;
  return [uu, vv];
}

function addCard(bld: VegBuilder, base: V3, axis: V3, side: V3, w: number, h: number, cell: number, sphN: V3, cardN: V3, wind: number, tint: number, occ: number, flip: boolean) {
  const s = cardN.dot(sphN) >= 0 ? 1 : -1;
  const n = sphN.clone().multiplyScalar(0.78).addScaledVector(cardN, 0.22 * s).normalize();
  const i0 = bld.count;
  const corners: [number, number][] = [[-0.5, 0], [0.5, 0], [0.5, 1], [-0.5, 1]];
  const p = v3();
  for (const [a, b] of corners) {
    p.copy(base).addScaledVector(side, a * w).addScaledVector(axis, b * h);
    const [u, v] = cellUV(cell, flip ? 0.5 - a : a + 0.5, b);
    bld.vert(p, n, u, v, Math.min(1, wind + b * 0.12), tint, occ);
  }
  bld.tri(i0, i0 + 1, i0 + 2);
  bld.tri(i0, i0 + 2, i0 + 3);
}

function buildLeaves(cfg: SpeciesCfg, sk: TreeSkeleton, rng: Rng): THREE.BufferGeometry {
  const bld = new VegBuilder();
  const env = sk.env;
  const P = v3(), T = v3(), sph = v3();
  const leafLevels = cfg.leafLevels ?? [cfg.levels.length];
  const maxLevel = cfg.levels.length;

  const placeCard = (pt: V3, tan: V3, wPath: number, sizeMul: number) => {
    pt = pt.clone();
    const size = cfg.leafSize * 1.3 * sizeMul * rng.range(0.8, 1.2);
    // unmodelled twigs: scatter the tuft around the branch, biased outwards
    if (cfg.cardMode !== 'flat') {
      const [q1, q2] = perpBasis(tan);
      const a = rng.range(0, Math.PI * 2);
      const off = q1.multiplyScalar(Math.cos(a)).addScaledVector(q2, Math.sin(a));
      const toOut = v3(pt.x - env.cx, pt.y - env.cy, pt.z - env.cz).normalize();
      if (off.dot(toOut) < 0) off.multiplyScalar(-0.6);
      pt = pt.clone().addScaledVector(off, rng.range(0, cfg.leafSize * 0.7));
    }
    const d = env.shade(pt, sph);
    const outward = v3(pt.x - env.cx, 0, pt.z - env.cz);
    if (outward.lengthSq() < 1e-4) outward.copy(randUnit(rng)).setY(0);
    outward.normalize();
    let axis: V3, nrm0: V3;
    switch (cfg.cardMode) {
      case 'flat': {
        const sideDir = v3().crossVectors(tan, UP).normalize().multiplyScalar(rng.sign());
        axis = tan.clone().addScaledVector(sideDir, rng.range(0.3, 1.0)).addScaledVector(UP, rng.range(-0.45, 0.35)).normalize();
        pt.y += rng.range(-0.25, 0.2);
        nrm0 = UP.clone().addScaledVector(randUnit(rng), 0.25);
        break;
      }
      case 'up':
        axis = UP.clone().multiplyScalar(1.2).addScaledVector(outward, rng.range(0.2, 0.7)).addScaledVector(randUnit(rng), 0.35).normalize();
        nrm0 = outward.clone().addScaledVector(randUnit(rng), 0.6);
        break;
      case 'tuft':
        axis = UP.clone().multiplyScalar(0.9).addScaledVector(tan, 0.6).addScaledVector(outward, 0.3).addScaledVector(randUnit(rng), 0.45).normalize();
        nrm0 = randUnit(rng);
        break;
      default: {
        const rnd = randUnit(rng);
        axis = tan.clone().multiplyScalar(0.55).addScaledVector(outward, 0.5).addScaledVector(rnd, 0.75).addScaledVector(UP, 0.25).normalize();
        nrm0 = UP.clone().multiplyScalar(0.7).addScaledVector(sph, 0.5).addScaledVector(randUnit(rng), 0.8);
      }
    }
    nrm0.addScaledVector(axis, -nrm0.dot(axis));
    if (nrm0.lengthSq() < 1e-4) nrm0.copy(perpBasis(axis)[0]);
    nrm0.normalize();
    const side = v3().crossVectors(axis, nrm0).normalize();
    const occ = clamp(0.8 * (1 - smooth(0.25, 1.0, d)) + 0.25 * clamp(-sph.y, 0, 1), 0, 1);
    const tint = rng.float();
    const base = pt.clone().addScaledVector(axis, -size * 0.08);
    const nCross = cfg.cross ?? 1;
    for (let c = 0; c < nCross; c++) {
      let sd = side, nr = nrm0;
      if (c > 0) {
        const q = new THREE.Quaternion().setFromAxisAngle(axis, (Math.PI / nCross) * c);
        sd = side.clone().applyQuaternion(q);
        nr = nrm0.clone().applyQuaternion(q);
      }
      addCard(bld, base, axis, sd, size, size, cfg.leafCell, sph, nr, wPath, tint, occ, rng.chance(0.5));
    }
  };

  let density = cfg.density;
  if (cfg.cards) {
    let total = 0, n = 0;
    for (const b of sk.branches) {
      if (!leafLevels.includes(b.level)) continue;
      const terminal = b.level === maxLevel || b.children.length === 0;
      const start = terminal ? cfg.leafStart : Math.max(cfg.leafStart, 0.55);
      total += branchLen(b) * (1 - start);
      n++;
    }
    density = Math.max(0.5, (cfg.cards - n) / Math.max(1, total));
  }
  for (const b of sk.branches) {
    const isLeafy = leafLevels.includes(b.level);
    if (!isLeafy) continue;
    const len = branchLen(b);
    const terminal = b.level === maxLevel || b.children.length === 0;
    const start = terminal ? cfg.leafStart : Math.max(cfg.leafStart, 0.55);
    const count = Math.max(1, Math.round(len * (1 - start) * density * rng.range(0.85, 1.15)));
    for (let i = 0; i < count; i++) {
      const t = start + (1 - start) * ((i + rng.range(0.1, 0.9)) / count);
      sampleBranch(b, t, P, T);
      const w = (b.d0 + t * len) / sk.maxPath;
      placeCard(P, T, Math.max(0.35, w), 1);
    }
    // tip card
    sampleBranch(b, 1, P, T);
    placeCard(P, T, Math.max(0.4, (b.d0 + len) / sk.maxPath), 1.1);
  }

  if (cfg.trunkLeaves) {
    const trunk = sk.branches[0];
    const tl = branchLen(trunk);
    const s0 = Math.max(0.02, (env.base - trunk.pts[0].y) / tl);
    const count = Math.round(tl * (1 - s0) * cfg.trunkLeaves);
    for (let i = 0; i < count; i++) {
      const t = s0 + (1 - s0) * ((i + rng.float()) / count);
      sampleBranch(trunk, t, P, T);
      const out = randUnit(rng).setY(0).normalize();
      const r = env.rx * cfg.prof(clamp((P.y - env.base) / (env.top - env.base), 0, 1)) * rng.range(0.1, 0.6);
      P.addScaledVector(out, r);
      placeCard(P, cfg.cardMode === 'flat' ? out : T, Math.max(0.3, (t * tl) / sk.maxPath), 0.95);
    }
  }
  return bld.build(true);
}

// ---------------------------------------------------------------------------------------------
// Far LOD
// ---------------------------------------------------------------------------------------------

class FarBuilder {
  pos: number[] = []; nrm: number[] = []; uv: number[] = []; col: number[] = []; aut: number[] = []; wind: number[] = [];
  push(p: V3, n: V3, kind: number, decid: number, col: [number, number, number], aut: [number, number, number], w: number) {
    this.pos.push(p.x, p.y, p.z);
    this.nrm.push(n.x, n.y, n.z);
    this.uv.push(kind, decid);
    this.col.push(srgbToLin(col[0]), srgbToLin(col[1]), srgbToLin(col[2]));
    this.aut.push(srgbToLin(aut[0]), srgbToLin(aut[1]), srgbToLin(aut[2]));
    this.wind.push(w);
  }
  build(): THREE.BufferGeometry {
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.Float32BufferAttribute(this.pos, 3));
    g.setAttribute('normal', new THREE.Float32BufferAttribute(this.nrm, 3));
    g.setAttribute('uv', new THREE.Float32BufferAttribute(this.uv, 2));
    g.setAttribute('color', new THREE.Float32BufferAttribute(this.col, 3));
    g.setAttribute('aAutumn', new THREE.Float32BufferAttribute(this.aut, 3));
    g.setAttribute('aWind', new THREE.Float32BufferAttribute(this.wind, 1));
    g.computeBoundingBox();
    g.computeBoundingSphere();
    return g;
  }
}

const BARK_FAR: [number, number, number][] = [
  [0.33, 0.29, 0.25], [0.3, 0.26, 0.22], [0.82, 0.8, 0.76], [0.55, 0.53, 0.43],
  [0.45, 0.3, 0.22], [0.47, 0.42, 0.35], [0.4, 0.29, 0.22], [0.38, 0.35, 0.31],
];

/**
 * A tapered prism of bark from `base` to `top` (radius `r` to `rTop`), its colour shaded by `shade` at each
 * end (1 in the open, lower where the crown covers it) and swaying `w` at each end.
 */
function farTrunk(fb: FarBuilder, base: V3, top: V3, r: number, barkIdx: number, sides = 4, rTop = r * 0.6, shade: [number, number] = [1, 1], w: [number, number] = [0, 0.3]) {
  const bark = BARK_FAR[barkIdx];
  const tint = (k: number): [number, number, number] => [bark[0] * k, bark[1] * k, bark[2] * k];
  const cols = [tint(shade[0]), tint(shade[1])];
  const axis = v3().subVectors(top, base).normalize();
  // Two directions across the axis (the prism's sides stay square to a leaning limb).
  const a = Math.abs(axis.y) < 0.9 ? v3(0, 1, 0) : v3(1, 0, 0);
  const u = v3().crossVectors(axis, a).normalize(), v = v3().crossVectors(u, axis);
  const p = v3(), n = v3();
  for (let i = 0; i < sides; i++) {
    const a0 = (i / sides) * Math.PI * 2 + 0.4, a1 = ((i + 1) / sides) * Math.PI * 2 + 0.4;
    const q = (ang: number, c: V3, rr: number) => c.clone().addScaledVector(u, Math.cos(ang) * rr).addScaledVector(v, Math.sin(ang) * rr);
    const am = (a0 + a1) / 2;
    n.copy(u).multiplyScalar(Math.cos(am)).addScaledVector(v, Math.sin(am));
    const quad = [q(a0, base, r), q(a1, base, r), q(a1, top, rTop), q(a0, top, rTop)];
    for (const k of [0, 2, 1, 0, 3, 2]) {
      p.copy(quad[k]);
      const end = k >= 2 ? 1 : 0;
      fb.push(p, n, 0, 0, cols[end], cols[end], w[end]);
    }
  }
}

/** How many of the trunk's biggest limbs a far hull shows, and how thick (of the trunk) a limb must be to count. */
const FAR_LIMBS = 4, FAR_LIMB_MIN = 0.3;

function buildFar(cfg: SpeciesCfg, sk: TreeSkeleton): THREE.BufferGeometry {
  const fb = new FarBuilder();
  const env = sk.env;
  const trunk = sk.branches[0];
  // The trunk reaches into the middle of the crown, so its end never shows below the hull's dissolved rim
  // (it stopped a third of the way in, and below the crown for pines: far woods read as bare posts).
  const fork = v3(), mid = v3(), tan = v3();
  const y0 = trunk.pts[0].y;
  const at = (y: number, out: V3) => {
    // The point of the trunk at height y (its tip if it ends lower), and the radius there.
    const tt = clamp((y - y0) / Math.max(1e-3, trunk.pts[trunk.pts.length - 1].y - y0), 0, 1);
    return sampleBranch(trunk, tt, out, tan);
  };
  const rFork = at(env.base, fork);
  at(env.cy, mid);
  mid.y = Math.max(mid.y, env.cy);
  const r0 = cfg.trunkR * 1.1;
  // Darker at the foot (as the near bark is) and up into the crown's shade: seen from afar a trunk stands in the wood's shadow.
  farTrunk(fb, v3(0, -0.1, 0), fork, r0, cfg.bark, 5, Math.max(rFork, r0 * 0.55), [0.8, 0.6], [0, 0.2]);
  farTrunk(fb, fork, mid, Math.max(rFork, r0 * 0.55), cfg.bark, 4, r0 * 0.25, [0.6, 0.45], [0.2, 0.4]);
  // The main limbs, part way out into the crown, so a far tree forks like the near one instead of standing as a post.
  const limbs = sk.branches
    .filter((b) => b.level === 1 && b.rad[0] >= cfg.trunkR * FAR_LIMB_MIN)
    .sort((a, b) => b.rad[0] - a.rad[0])
    .slice(0, FAR_LIMBS);
  for (const b of limbs) {
    const end = v3();
    sampleBranch(b, 0.6, end, tan);
    farTrunk(fb, b.pts[0], end, b.rad[0] * 1.1, cfg.bark, 3, b.rad[0] * 0.4, [0.6, 0.45], [0.2, 0.5]);
  }
  const ico = new THREE.IcosahedronGeometry(1, 1);
  const pa = ico.getAttribute('position');
  const c = v3(env.cx, env.cy, env.cz);
  const d = v3(), p = v3(), n = v3();
  const decid = cfg.evergreen ? 0 : 1;
  for (let i = 0; i < pa.count; i++) {
    d.fromBufferAttribute(pa, i).normalize();
    let e = env.extent(d) * 0.97;
    e *= 1 + 0.12 * woodNoise.n3(d.x * 1.7 + 3.1, d.y * 1.7, d.z * 1.7);
    p.copy(c).addScaledVector(d, Math.max(0.3, e));
    env.shade(p, n);
    n.lerp(d, 0.4).normalize();
    const shade = 0.75 + 0.25 * clamp(d.y * 0.5 + 0.5, 0, 1);
    const col: [number, number, number] = [cfg.farColor[0] * shade, cfg.farColor[1] * shade, cfg.farColor[2] * shade];
    const aut: [number, number, number] = [cfg.autumn[0] * shade * 0.85, cfg.autumn[1] * shade * 0.85, cfg.autumn[2] * shade * 0.85];
    fb.push(p, n, 1, decid, col, aut, 0.75);
  }
  ico.dispose();
  return fb.build();
}

// ---------------------------------------------------------------------------------------------
// Palm (dedicated builder)
// ---------------------------------------------------------------------------------------------

function buildPalm(variant: number): TreeModel {
  const rng = Rng.from('tree', 'palm', variant);
  const H = rng.range(8.5, 11.5);
  const wood = new VegBuilder();
  const leaves = new VegBuilder();
  const leanDir = randUnit(rng).setY(0).normalize();
  const lean = rng.range(0.25, 0.5);
  // curved trunk: leans out at the base and gravitropically turns up again
  const pts: V3[] = [v3(0, -0.15, 0)];
  const d = UP.clone().addScaledVector(leanDir, lean).normalize();
  const segs = 16;
  const segL = H / segs;
  const p = pts[0].clone();
  for (let i = 0; i < segs; i++) {
    p.addScaledVector(d, segL);
    pts.push(p.clone());
    d.addScaledVector(UP, 0.05 + 0.02 * (i / segs));
    d.addScaledVector(randUnit(rng), 0.015);
    d.normalize();
  }
  const trunk = makeBranch(pts, 0.22, 0.2, 0, 0);
  for (let i = 0; i < trunk.rad.length; i++) {
    const y = pts[i].y;
    trunk.rad[i] = 0.2 + 0.12 * Math.exp(-Math.max(0, y) / 0.6) + (i >= segs - 1 ? 0.03 : 0);
  }
  const maxPath = branchLen(trunk) + 4.5;
  tube(wood, trunk, 9, 5, maxPath, null, null, variant * 31);
  const top = pts[pts.length - 1].clone();
  const tTan = top.clone().sub(pts[pts.length - 2]).normalize();
  const crownC = top.clone().add(v3(0, 0.4, 0));

  // leaf-base "boots" knob under the crown
  const boot = makeBranch([top.clone().addScaledVector(tTan, -0.7), top.clone().addScaledVector(tTan, 0.25)], 0.27, 0.16, 1, branchLen(trunk) - 0.7);
  tube(wood, boot, 9, 5, maxPath, null, null, 5);

  const nFronds = rng.int(18, 23);
  const frond = (az: number, elev: number, len: number, dead: boolean) => {
    const dir0 = v3(Math.cos(az) * Math.cos(elev), Math.sin(elev), Math.sin(az) * Math.cos(elev));
    const start = top.clone().addScaledVector(dir0, 0.12);
    // petiole (wood)
    const petLen = dead ? 0.4 : 0.55;
    const pet = makeBranch([start.clone(), start.clone().addScaledVector(dir0, petLen)], 0.045, 0.03, 2, branchLen(trunk));
    tube(wood, pet, 4, 5, maxPath, null, null, 3);
    // leaflet strip with a V fold
    const fs = 11;
    const fd = dir0.clone();
    const c = pet.pts[1].clone();
    const halfW = dead ? 0.42 : 0.62;
    const cell = dead ? 14 : 12;
    const tint = rng.float();
    const base = leaves.count;
    const sl = (len - petLen) / fs;
    const sph = v3();
    for (let i = 0; i <= fs; i++) {
      const t = i / fs;
      if (i > 0) {
        fd.addScaledVector(UP, dead ? -0.5 * sl : -(0.12 + 0.25 * t) * sl * 1.6);
        fd.normalize();
        c.addScaledVector(fd, sl);
      }
      const side = v3().crossVectors(fd, UP);
      if (side.lengthSq() < 1e-4) side.set(Math.sin(az), 0, -Math.cos(az));
      side.normalize();
      const upP = v3().crossVectors(side, fd).normalize();
      const w = halfW * (i === fs ? 0.35 : 1) * (dead ? 0.8 : 1);
      const fold = dead ? -0.5 : 0.38;
      const wind = clamp((branchLen(trunk) + petLen + t * len) / maxPath, 0.5, 1);
      sph.subVectors(c, crownC).normalize();
      const occ = dead ? 0.35 : 0.15 * (1 - t);
      const nL = sph.clone().multiplyScalar(0.55).addScaledVector(upP, 0.45).normalize();
      const [u0, vL] = cellUV(cell, t, 1, 2);
      const [, vC] = cellUV(cell, t, 0.5, 2);
      const [, vR] = cellUV(cell, t, 0, 2);
      leaves.vert(c.clone().addScaledVector(side, -w).addScaledVector(upP, w * fold), nL, u0, vL, wind, tint, occ);
      leaves.vert(c.clone().addScaledVector(upP, -0.02), nL, u0, vC, wind, tint, occ);
      leaves.vert(c.clone().addScaledVector(side, w).addScaledVector(upP, w * fold), nL, u0, vR, wind, tint, occ);
    }
    for (let i = 0; i < fs; i++) {
      const a = base + i * 3, b = a + 3;
      leaves.tri(a, b, a + 1); leaves.tri(a + 1, b, b + 1);
      leaves.tri(a + 1, b + 1, a + 2); leaves.tri(a + 2, b + 1, b + 2);
    }
  };
  let az = rng.range(0, Math.PI * 2);
  for (let i = 0; i < nFronds; i++) {
    const f = i / (nFronds - 1);
    const elev = (70 - f * 95 + rng.range(-8, 8)) * deg;
    const len = rng.range(3.4, 4.4) * (f < 0.15 ? 0.8 : 1);
    frond(az, elev, len, false);
    az += 137.5 * deg + rng.range(-0.15, 0.15);
  }
  const nDead = rng.int(3, 6);
  for (let i = 0; i < nDead; i++) frond(rng.range(0, Math.PI * 2), rng.range(-82, -65) * deg, rng.range(2.2, 2.9), true);

  // far: trunk + 9 frond ribbons
  const fb = new FarBuilder();
  farTrunk(fb, v3(0, -0.1, 0), top, 0.24, 5);
  const green: [number, number, number] = [0.3, 0.42, 0.18];
  for (let i = 0; i < 9; i++) {
    const a = (i / 9) * Math.PI * 2 + 0.3;
    const elev = (i % 3 === 0 ? 30 : i % 3 === 1 ? 0 : -25) * deg;
    const dir = v3(Math.cos(a) * Math.cos(elev), Math.sin(elev), Math.sin(a) * Math.cos(elev));
    const side = v3(-Math.sin(a), 0, Math.cos(a));
    const mid = top.clone().addScaledVector(dir, 2.0).add(v3(0, -0.2, 0));
    const tip = top.clone().addScaledVector(dir, 3.8).add(v3(0, -1.2, 0));
    const n = v3(0, 1, 0);
    const q = [top.clone().addScaledVector(side, 0.15), mid.clone().addScaledVector(side, 0.55), tip, mid.clone().addScaledVector(side, -0.55), top.clone().addScaledVector(side, -0.15)];
    for (const k of [0, 1, 4, 1, 3, 4, 1, 2, 3]) fb.push(q[k], n, 0.5, 0, green, green, 0.8);
  }
  const height = top.y + 2.2;
  return {
    species: 'palm', height, trunkRadius: 0.22,
    wood: wood.build(false), leaves: leaves.build(true), far: fb.build(), crownRadius: 4.2,
  };
}

// ---------------------------------------------------------------------------------------------
// Public model API
// ---------------------------------------------------------------------------------------------

const treeCache = new Map<string, TreeModel>();

function buildGeneric(kind: TreeSpecies | 'shrub', variant: number): TreeModel {
  const cfg = speciesCfg(kind, variant);
  const rng = Rng.from('tree', kind, variant);
  const sk = buildSkeleton(cfg, rng.fork('skeleton'));
  const wood = buildWood(cfg, sk, variant * 131 + 7);
  const leaves = buildLeaves(cfg, sk, rng.fork('leaves'));
  const far = buildFar(cfg, sk);
  const bb = leaves.boundingBox!;
  const height = Math.max(sk.height, bb.max.y);
  return {
    species: kind === 'shrub' ? 'linden' : kind,
    height,
    trunkRadius: cfg.trunkR,
    wood, leaves, far,
    isShrub: kind === 'shrub' ? true : undefined,
    crownRadius: Math.max(sk.env.rx, sk.env.rz),
  };
}

export function treeModel(species: TreeSpecies, variant = 0): TreeModel {
  const v = Math.abs(variant | 0) % 64;
  const key = species + ':' + v;
  let m = treeCache.get(key);
  if (!m) {
    m = species === 'palm' ? buildPalm(v) : buildGeneric(species, v);
    treeCache.set(key, m);
  }
  return m;
}

export function shrubModel(variant = 0): TreeModel {
  const v = Math.abs(variant | 0) % 64;
  const key = 'shrub:' + v;
  let m = treeCache.get(key);
  if (!m) {
    m = buildGeneric('shrub', v);
    treeCache.set(key, m);
  }
  return m;
}

// ---------------------------------------------------------------------------------------------
// Procedural textures
// ---------------------------------------------------------------------------------------------
