/**
 * A skeleton: a humanoid with its flesh taken away and its bones shown, built from its own rest
 * skeleton (so a goblin's bones are a goblin's and a giant's a giant's) and skinned to the same
 * bones, so every clip, action and hit reaction plays on it as on the living. One mesh of bones in
 * vertex colours (long bones with knobbed ends, vertebrae, ribs, pelvis, shoulder blades, a skull
 * with a jaw), optionally crusted with crystals, and optionally a glow in the eye sockets.
 *
 * The skin, eyes, hair, beard and race parts are taken out of the character (not hidden: the
 * equipment rig shows hair again when a helmet comes off). Worn and held items still fit as on the
 * living; what a skeleton wears is the host's choice.
 *
 * Pure geometry plus two of the package's simple node materials; seeded (no Math.random).
 */
import * as THREE from 'three/webgpu';
import { Rng } from '@futuremagic/core';
import { bindSkin, type Character } from './Character';
import { simpleMaterial } from './partMaterials';

export interface Bones {
  /** The bone's colour, sRGB 0..1 (default old bone). */
  tint?: [number, number, number];
  /** How crusted with crystals, 0..1 (0: clean bone). */
  crust?: number;
  /** The crystals' colour, sRGB 0..1 (default salt, white with a little blue). */
  crustTint?: [number, number, number];
  /** A glow deep in the eye sockets, sRGB 0..1; none if left out. */
  eyes?: [number, number, number];
  /** Seeds the crust and the bones' small differences (default: the appearance's seed). */
  seed?: number;
}

type V = THREE.Vector3;
const v = (x = 0, y = 0, z = 0) => new THREE.Vector3(x, y, z);

/** The bone mesh being built: positions, normals, colours and one bone per vertex. */
class Build {
  readonly pos: number[] = [];
  readonly nrm: number[] = [];
  readonly col: number[] = [];
  readonly bone: number[] = [];
  readonly idx: number[] = [];
  colour: [number, number, number] = [1, 1, 1];

  private vert(p: V, n: V, b: number): number {
    this.pos.push(p.x, p.y, p.z);
    this.nrm.push(n.x, n.y, n.z);
    this.col.push(...this.colour);
    this.bone.push(b);
    return this.pos.length / 3 - 1;
  }

  /** An ellipsoid at `c` with three orthogonal half-axes. */
  ball(c: V, ax: V, ay: V, az: V, b: number, seg = 8, rings = 6): void {
    const i0 = this.pos.length / 3;
    const nx = ax.clone().divideScalar(ax.lengthSq()), ny = ay.clone().divideScalar(ay.lengthSq()), nz = az.clone().divideScalar(az.lengthSq());
    for (let r = 0; r <= rings; r++) {
      const th = (r / rings) * Math.PI, sy = Math.cos(th), sr = Math.sin(th);
      for (let s = 0; s <= seg; s++) {
        const ph = (s / seg) * Math.PI * 2, sx = Math.cos(ph) * sr, sz = Math.sin(ph) * sr;
        const p = c.clone().addScaledVector(ax, sx).addScaledVector(ay, sy).addScaledVector(az, sz);
        const n = v().addScaledVector(nx, sx).addScaledVector(ny, sy).addScaledVector(nz, sz).normalize();
        this.vert(p, n, b);
      }
    }
    for (let r = 0; r < rings; r++) for (let s = 0; s < seg; s++) {
      const a = i0 + r * (seg + 1) + s, d = a + seg + 1;
      this.idx.push(a, a + 1, d, a + 1, d + 1, d);
    }
  }

  /** A round ball. */
  sphere(c: V, r: number, b: number, seg = 6, rings = 4): void {
    this.ball(c, v(r, 0, 0), v(0, r, 0), v(0, 0, r), b, seg, rings);
  }

  /** A tube from `a` to `e`, radius `r0` to `r1` (open ends: knobs close them). */
  tube(a: V, e: V, r0: number, r1: number, b: number, sides = 6): void {
    const d = e.clone().sub(a);
    if (d.lengthSq() < 1e-10) return;
    d.normalize();
    const u = Math.abs(d.y) < 0.9 ? v(0, 1, 0) : v(1, 0, 0);
    const x = u.clone().cross(d).normalize(), y = d.clone().cross(x);
    const i0 = this.pos.length / 3;
    for (const [p, r] of [[a, r0], [e, r1]] as const) {
      for (let s = 0; s <= sides; s++) {
        const ph = (s / sides) * Math.PI * 2, n = x.clone().multiplyScalar(Math.cos(ph)).addScaledVector(y, Math.sin(ph));
        this.vert(p.clone().addScaledVector(n, r), n, b);
      }
    }
    for (let s = 0; s < sides; s++) {
      const a0 = i0 + s, a1 = a0 + sides + 1;
      this.idx.push(a0, a1, a0 + 1, a0 + 1, a1, a1 + 1);
    }
  }

  /** A curve of tube through `pts` (each segment on its own bone). */
  path(pts: readonly V[], r: number, bones: readonly number[]): void {
    for (let i = 0; i + 1 < pts.length; i++) {
      this.tube(pts[i], pts[i + 1], r, r, bones[i]);
      if (i > 0) this.sphere(pts[i], r, bones[i], 5, 3);
    }
  }

  /** A crystal (an octahedron) of size `s` stuck on at `p`, pointing along `n`. */
  crystal(p: V, n: V, s: number, b: number, rng: Rng): void {
    const u = Math.abs(n.y) < 0.9 ? v(0, 1, 0) : v(1, 0, 0);
    const x = u.clone().cross(n).normalize().applyAxisAngle(n, rng.float() * Math.PI), y = n.clone().cross(x);
    const tip = p.clone().addScaledVector(n, s * 1.6), foot = p.clone().addScaledVector(n, -s * 0.5);
    const ring = [x, y, x.clone().negate(), y.clone().negate()].map((d) => p.clone().addScaledVector(n, s * 0.4).addScaledVector(d, s * 0.55));
    for (let k = 0; k < 4; k++) {
      const a = ring[k], c = ring[(k + 1) % 4];
      for (const end of [tip, foot]) {
        const f = c.clone().sub(a).cross(end.clone().sub(a)).normalize();
        if (end === foot) f.negate();
        const i = this.vert(a, f, b), j = this.vert(c, f, b), l = this.vert(end, f, b);
        this.idx.push(...(end === tip ? [i, j, l] : [j, i, l]));
      }
    }
  }

  geometry(): THREE.BufferGeometry {
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.Float32BufferAttribute(this.pos, 3));
    g.setAttribute('normal', new THREE.Float32BufferAttribute(this.nrm, 3));
    g.setAttribute('color', new THREE.Float32BufferAttribute(this.col, 3));
    const n = this.bone.length, si = new Uint16Array(n * 4), sw = new Float32Array(n * 4);
    for (let i = 0; i < n; i++) { si[i * 4] = this.bone[i]; sw[i * 4] = 1; }
    g.setAttribute('skinIndex', new THREE.Uint16BufferAttribute(si, 4));
    g.setAttribute('skinWeight', new THREE.Float32BufferAttribute(sw, 4));
    g.setIndex(this.idx);
    g.computeBoundingSphere();
    return g;
  }
}

const lin = (c: [number, number, number]): [number, number, number] => {
  const k = new THREE.Color().setRGB(c[0], c[1], c[2], THREE.SRGBColorSpace);
  return [k.r, k.g, k.b];
};

/**
 * Lay the bones of `ch` out on its rest skeleton: the geometry of the bones (in the model's rest
 * space, one bone per vertex) and of the eye glow (null without `eyes`). Pure: no materials.
 */
export function boneGeometry(ch: Character, bones: Bones): { bones: THREE.BufferGeometry; glow: THREE.BufferGeometry | null } {
  const rest = ch.rest, I = (name: string) => ch.boneIndex.get(name) ?? -1, at = (name: string) => rest[I(name)].clone();
  const rng = new Rng(bones.seed ?? ch.app.seed);
  const s = ch.geo.build.body.height / 1.71;
  const B = new Build(), G = new Build();
  const bone = lin(bones.tint ?? [0.8, 0.74, 0.62]);
  const shade = (k: number): [number, number, number] => {
    const w = k * (0.9 + rng.float() * 0.15);
    return [bone[0] * w, bone[1] * w, bone[2] * w];
  };
  const crusts: { p: V; n: V; r: number; b: number }[] = [];
  /** A long bone between two heads, knobbed at both ends; remembered for the crust. */
  const long = (a: V, e: V, r: number, b: number, knob = 1.6) => {
    B.colour = shade(1);
    B.tube(a, e, r, r * 0.85, b);
    B.sphere(a, r * knob, b);
    B.sphere(e, r * knob * 0.9, b);
    crusts.push({ p: a.clone().lerp(e, 0.5), n: e.clone().sub(a), r, b });
  };

  // ---- legs and feet
  for (const side of ['L', 'R']) {
    const hip = at(`upperleg01.${side}`), knee = at(`lowerleg01.${side}`), ankle = at(`foot.${side}`), toes = at(`toes.${side}`);
    const out = Math.sign(hip.x) || 1;
    long(hip, at(`upperleg02.${side}`), 0.02 * s, I(`upperleg01.${side}`), 1.8);
    long(at(`upperleg02.${side}`), knee, 0.018 * s, I(`upperleg02.${side}`), 1.7);
    long(knee, ankle, 0.016 * s, I(`lowerleg01.${side}`), 1.6);
    // The fibula, thin, beside it.
    B.tube(knee.clone().add(v(out * 0.018 * s, -0.03 * s, 0.005 * s)), ankle.clone().add(v(out * 0.02 * s, 0.02 * s, 0)), 0.007 * s, 0.006 * s, I(`lowerleg02.${side}`));
    B.colour = shade(0.95);
    B.ball(ankle.clone().add(v(0, -0.03 * s, 0.035 * s)), v(0.016 * s, 0, 0), v(0, 0.018 * s, 0), v(0, 0, 0.026 * s), I(`foot.${side}`));
    const tip = toes.clone().add(toes.clone().sub(ankle).setY(0).normalize().multiplyScalar(0.05 * s)).setY(toes.y);
    for (const k of [-1, 0, 1]) {
      const sp = v(k * 0.018 * s, 0, 0);
      B.tube(ankle.clone().add(v(0, -0.02 * s, 0)), toes.clone().add(sp), 0.007 * s, 0.006 * s, I(`foot.${side}`));
      B.tube(toes.clone().add(sp), tip.clone().add(sp.multiplyScalar(1.3)), 0.005 * s, 0.004 * s, I(`toes.${side}`));
    }
  }

  // ---- pelvis
  const root = I('root'), hipL = at('upperleg01.L'), hipR = at('upperleg01.R'), mid = hipL.clone().lerp(hipR, 0.5);
  B.colour = shade(1);
  for (const side of [-1, 1]) {
    const c = mid.clone().add(v(side * 0.075 * s, 0.06 * s, 0.01 * s));
    const ax = v(side * 0.045 * s, 0.015 * s, -0.025 * s), ay = v(-side * 0.01 * s, 0.045 * s, 0), az = ax.clone().cross(ay).normalize().multiplyScalar(0.01 * s);
    B.ball(c, ax, ay, az, root);
    B.sphere(c.clone().add(v(-side * 0.015 * s, -0.06 * s, -0.01 * s)), 0.02 * s, root);
  }
  const pubis: V[] = [];
  for (let k = 0; k <= 6; k++) {
    const a = -Math.PI / 2 + (k / 6) * Math.PI;
    pubis.push(mid.clone().add(v(Math.sin(a) * 0.07 * s, -0.02 * s - Math.cos(a) * 0.015 * s, -Math.cos(a) * 0.045 * s - 0.005 * s)));
  }
  B.path(pubis, 0.012 * s, pubis.map(() => root));
  B.ball(mid.clone().add(v(0, 0.04 * s, 0.045 * s)), v(0.03 * s, 0, 0), v(0, 0.05 * s, 0.01 * s), v(0, 0, 0.014 * s), root);

  // ---- spine: vertebrae along the chain from the pelvis to the head
  const chain = ['spine05', 'spine04', 'spine03', 'spine02', 'spine01', 'neck01', 'neck02', 'neck03', 'head'].filter((n) => I(n) >= 0);
  const spineAt = (y: number): V => {
    for (let k = 0; k + 1 < chain.length; k++) {
      const a = at(chain[k]), e = at(chain[k + 1]);
      if (y <= e.y || k + 2 === chain.length) return a.lerp(e, Math.min(1, Math.max(0, (y - a.y) / (e.y - a.y || 1))));
    }
    return at(chain[0]);
  };
  const spineBone = (y: number): number => {
    let b = I(chain[0]);
    for (const n of chain) if (rest[I(n)].y <= y + 1e-4) b = I(n);
    return b;
  };
  const y0 = at(chain[0]).y + 0.02 * s, y1 = at('head').y - 0.01 * s;
  for (let y = y0; y < y1; y += 0.03 * s) {
    const neck = y > at('neck01').y - 0.01 * s, lumbar = y < at('spine02').y;
    const k = neck ? 0.7 : lumbar ? 1.25 : 1;
    const p = spineAt(y), b = spineBone(y);
    B.colour = shade(0.97);
    B.ball(p, v(0.018 * s * k, 0, 0), v(0, 0.011 * s, 0), v(0, 0, 0.016 * s * k), b, 6, 4);
    B.tube(p, p.clone().add(v(0, -0.012 * s, 0.026 * s * k)), 0.006 * s, 0.004 * s, b, 4);
  }

  // ---- ribcage and breastbone
  const neck1 = at('neck01'), sp1 = at('spine01'), sp2 = at('spine02');
  const yT = sp1.y + (neck1.y - sp1.y) * 0.72, yB = sp2.y + 0.035 * s, RIBS = 8;
  for (let i = 0; i < RIBS; i++) {
    const t = i / (RIBS - 1), y = yT + (yB - yT) * t, back = spineAt(y), b = spineBone(y);
    const rx = s * (0.085 + 0.055 * Math.sin(Math.PI * (0.2 + 0.65 * t))), rz = s * (0.055 + 0.032 * Math.sin(Math.PI * (0.15 + 0.6 * t)));
    const zc = back.z - rz * 0.95, end = Math.PI - (0.3 + 0.75 * t * t), drop = 0.05 * s * (0.6 + t);
    B.colour = shade(0.98);
    for (const side of [-1, 1]) {
      const pts: V[] = [];
      for (let k = 0; k <= 7; k++) {
        const th = 0.25 + (k / 7) * (end - 0.25);
        pts.push(v(side * rx * Math.sin(th), y - drop * (1 - Math.cos(th)) * 0.5, zc + rz * Math.cos(th)));
      }
      B.path(pts, 0.0065 * s, pts.map(() => b));
      if (i % 2 === 0) crusts.push({ p: pts[3], n: pts[4].clone().sub(pts[2]), r: 0.0065 * s, b });
    }
  }
  {
    const back = spineAt(yT - 0.06 * s), zf = back.z - 2 * s * (0.055 + 0.032 * Math.sin(Math.PI * 0.35)) * 0.97;
    B.colour = shade(1);
    B.ball(v(0, yT - 0.085 * s, zf), v(0.02 * s, 0, 0), v(0, 0.085 * s, 0.012 * s), v(0, 0, 0.008 * s), spineBone(yT - 0.085 * s));
  }

  // ---- shoulders and arms
  for (const side of ['L', 'R']) {
    const out = Math.sign(at(`shoulder01.${side}`).x) || 1, clav = I(`clavicle.${side}`), sh = at(`shoulder01.${side}`);
    B.colour = shade(1);
    const neckFront = v(out * 0.02 * s, yT + 0.005 * s, spineAt(yT).z - 0.1 * s);
    B.tube(neckFront, sh.clone().add(v(out * 0.02 * s, 0, 0)), 0.008 * s, 0.009 * s, clav);
    B.sphere(neckFront, 0.011 * s, clav);
    // The shoulder blade, flat behind.
    B.ball(sh.clone().add(v(-out * 0.035 * s, -0.07 * s, 0.07 * s)), v(out * 0.034 * s, 0.008 * s, -out * 0.01 * s), v(0, 0.055 * s, 0.01 * s), v(0, 0, 0.008 * s), I(`shoulder01.${side}`));
    long(at(`upperarm01.${side}`), at(`upperarm02.${side}`), 0.015 * s, I(`upperarm01.${side}`), 1.9);
    long(at(`upperarm02.${side}`), at(`lowerarm01.${side}`), 0.014 * s, I(`upperarm02.${side}`), 1.6);
    // Radius and ulna, side by side.
    const elbow = at(`lowerarm01.${side}`), mid2 = at(`lowerarm02.${side}`), wrist = at(`wrist.${side}`);
    const across = wrist.clone().sub(elbow).cross(v(0, 0, 1)).normalize().multiplyScalar(0.009 * s);
    for (const k of [-1, 1]) {
      const o = across.clone().multiplyScalar(k);
      B.colour = shade(0.97);
      B.tube(elbow.clone().add(o), mid2.clone().add(o.clone().multiplyScalar(1.1)), 0.0075 * s, 0.007 * s, I(`lowerarm01.${side}`));
      B.tube(mid2.clone().add(o.clone().multiplyScalar(1.1)), wrist.clone().add(o.clone().multiplyScalar(1.2)), 0.007 * s, 0.0065 * s, I(`lowerarm02.${side}`));
    }
    B.sphere(wrist, 0.014 * s, I(`wrist.${side}`));
    // Hands: a bone to each finger's base, then the finger's joints and a tip beyond the last.
    for (let f = 1; f <= 5; f++) {
      const names = [1, 2, 3].map((j) => `finger${f}-${j}.${side}`);
      if (names.some((n) => I(n) < 0)) continue;
      const p = names.map(at), tip = p[2].clone().add(p[2].clone().sub(p[1]).multiplyScalar(0.85));
      B.colour = shade(0.96);
      B.tube(wrist, p[0], 0.0045 * s, 0.004 * s, I(`wrist.${side}`), 4);
      B.path([...p, tip], 0.0035 * s, names.map(I));
    }
  }

  // ---- skull and jaw
  const head = I('head'), jaw = I('jaw') >= 0 ? I('jaw') : head, e = ch.geo.build.body.eyes;
  const eyeL = v(e[0], e[1], e[2]), eyeR = v(e[4], e[5], e[6]), E = eyeL.clone().lerp(eyeR, 0.5);
  const k = Math.max(0.6, eyeL.distanceTo(eyeR) / 0.066) * 0.5 + s * 0.5;
  B.colour = shade(1.04);
  B.ball(E.clone().add(v(0, 0.038 * k, 0.07 * k)), v(0.074 * k, 0, 0), v(0, 0.084 * k, 0), v(0, 0, 0.095 * k), head, 10, 8);
  // Cheeks and upper jaw.
  B.ball(E.clone().add(v(0, -0.04 * k, 0.01 * k)), v(0.05 * k, 0, 0), v(0, 0.035 * k, 0), v(0, 0, 0.04 * k), head);
  for (const side of [-1, 1]) B.ball(E.clone().add(v(side * 0.05 * k, -0.025 * k, 0.03 * k)), v(0.014 * k, 0, 0), v(0, 0.012 * k, 0), v(0, 0, 0.03 * k), head, 6, 4);
  // Teeth, upper and lower, in a curve.
  B.colour = shade(1.08);
  for (let t = 0; t < 8; t++) {
    const a = -1.1 + (t / 7) * 2.2;
    B.ball(E.clone().add(v(Math.sin(a) * 0.03 * k, -0.067 * k, -0.026 * k + (1 - Math.cos(a)) * 0.03 * k)), v(0.005 * k, 0, 0), v(0, 0.007 * k, 0), v(0, 0, 0.004 * k), head, 4, 3);
    B.ball(E.clone().add(v(Math.sin(a) * 0.028 * k, -0.081 * k, -0.022 * k + (1 - Math.cos(a)) * 0.03 * k)), v(0.005 * k, 0, 0), v(0, 0.006 * k, 0), v(0, 0, 0.004 * k), jaw, 4, 3);
  }
  // The jaw: a curve from one hinge round the chin to the other.
  B.colour = shade(1);
  const mand: V[] = [];
  for (let t = 0; t <= 8; t++) {
    const a = -1.45 + (t / 8) * 2.9;
    mand.push(E.clone().add(v(Math.sin(a) * 0.048 * k, -0.088 * k + (Math.abs(Math.sin(a)) ** 2) * 0.03 * k, -0.02 * k + (1 - Math.cos(a)) * 0.055 * k)));
  }
  B.path(mand, 0.008 * k, mand.map(() => jaw));
  for (const side of [0, mand.length - 1]) B.tube(mand[side], mand[side].clone().add(v(0, 0.045 * k, 0.01 * k)), 0.008 * k, 0.007 * k, jaw, 5);
  // The dark of the sockets and the nose, set into the bone.
  B.colour = [0.05, 0.045, 0.04];
  for (const p of [eyeL, eyeR]) B.ball(p.clone().add(v(0, 0.002 * k, -0.008 * k)), v(0.019 * k, 0, 0), v(0, 0.017 * k, 0), v(0, 0, 0.009 * k), head);
  B.ball(E.clone().add(v(0, -0.034 * k, -0.025 * k)), v(0.008 * k, 0, 0), v(0, 0.012 * k, 0), v(0, 0, 0.012 * k), head, 5, 3);
  if (bones.eyes) {
    G.colour = [1, 1, 1];
    for (const p of [eyeL, eyeR]) G.sphere(p.clone().add(v(0, 0, -0.012 * k)), 0.0055 * k, head, 6, 4);
  }

  // ---- crust: crystals along the long bones and ribs, and a few on the skull
  const crust = Math.min(1, Math.max(0, bones.crust ?? 0));
  if (crust > 0) {
    B.colour = lin(bones.crustTint ?? [0.86, 0.92, 1]);
    for (const c of crusts) {
      const n = Math.round(crust * (1 + rng.float() * 3));
      const d = c.n.clone().normalize(), u = Math.abs(d.y) < 0.9 ? v(0, 1, 0) : v(1, 0, 0), x = u.cross(d).normalize();
      for (let i = 0; i < n; i++) {
        const out = x.clone().applyAxisAngle(d, rng.float() * Math.PI * 2);
        const p = c.p.clone().addScaledVector(c.n, (rng.float() - 0.5) * 0.8).addScaledVector(out, c.r * 0.9);
        B.crystal(p, out, (0.006 + rng.float() * 0.012) * s * (0.6 + crust * 0.6), c.b, rng);
      }
    }
    for (let i = 0; i < Math.round(crust * 6); i++) {
      const n = v(rng.float() - 0.5, rng.float() * 0.8, rng.float() * 0.7).normalize();
      B.crystal(E.clone().add(v(0, 0.038 * k, 0.07 * k)).add(v(n.x * 0.072 * k, n.y * 0.082 * k, n.z * 0.093 * k)), n, (0.008 + rng.float() * 0.01) * k, head, rng);
    }
  }
  return { bones: B.geometry(), glow: bones.eyes ? G.geometry() : null };
}

/**
 * Turn `ch` into its skeleton: take its flesh out and add its bones (skinned to its skeleton),
 * and the glow of its eyes. Returns what it added, for disposal.
 */
export function skeletal(ch: Character, bones: Bones, castShadow: boolean): { geometries: THREE.BufferGeometry[]; materials: THREE.Material[] } {
  // The flesh: everything the character built in its LODs, and its eyeballs.
  for (const l of ch.lods) for (const o of [...l.children]) o.removeFromParent();
  for (const e of ch.eyes) for (const o of [...e.children]) o.removeFromParent();
  const geo = boneGeometry(ch, bones);
  const out = { geometries: [geo.bones], materials: [] as THREE.Material[] };
  const mat = simpleMaterial(0xffffff, { vertexColors: true, roughness: 0.62, sheen: 0.15 }).material;
  out.materials.push(mat);
  const add = (g: THREE.BufferGeometry, m: THREE.Material, shadow: boolean) => {
    const mesh = new THREE.SkinnedMesh(g, m);
    mesh.name = 'bones';
    bindSkin(mesh, ch);
    mesh.castShadow = shadow;
    mesh.receiveShadow = true;
    mesh.frustumCulled = false;
    ch.model.add(mesh);
  };
  add(geo.bones, mat, castShadow);
  if (geo.glow && bones.eyes) {
    const c = new THREE.Color().setRGB(bones.eyes[0], bones.eyes[1], bones.eyes[2], THREE.SRGBColorSpace);
    const glow = simpleMaterial(0x000000, { emissive: c, emissiveIntensity: 2.2, roughness: 1 }).material;
    out.geometries.push(geo.glow);
    out.materials.push(glow);
    add(geo.glow, glow, false);
  }
  return out;
}
