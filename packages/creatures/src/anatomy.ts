/**
 * A procedural creature's body (docs/design/procedural-creatures.md): a species' genome
 * (src/creatures/bestiary.ts) laid out as a rest-pose skeleton and the shapes its flesh is made of.
 * Ported from Norgo's `body.ts` (Arnd's own world), with crabs, slugs, eye stalks, lures, pincers
 * and muscle under the skin added.
 *
 * The skeleton: bones with identity rest rotations, each at its rest position (a bone's rest
 * transform is its offset from its parent). Legs are laid out with the same two-bone IK the rig
 * uses (`solveKnee`), so the rest pose is a solved pose. The flesh: round cones, ellipsoids and
 * rounded boxes, each driven by one bone, blended smoothly into one skin by the mesher
 * (src/creatures/flesh.ts). Eyes are separate balls on the head (or on stalks).
 *
 * Model space: metres at size 1, +Y up, +Z forward, +X the creature's left. The origin is on the
 * ground under the body (at the bell's centre for a drifter).
 *
 * Pure: no three.js, so the mesher runs in a worker and the tests in Node.
 */
import { Rng, clamp, lerp, mixRgb } from '@futuremagic/core';
import type { Species } from './bestiary';

export type V3 = [number, number, number];

export type BoneKind = 'root' | 'spine' | 'neck' | 'head' | 'jaw' | 'tail' | 'leg' | 'arm' | 'pincer' | 'antenna' | 'tentacle' | 'bell' | 'ear' | 'lure' | 'stalk';

export interface BoneDef {
  readonly name: string;
  readonly parent: number;
  /** Rest position, model space. */
  readonly pos: V3;
  readonly kind: BoneKind;
}

/** What a piece of flesh is (the mesher blends them into the vertex colours). */
export const enum Part {
  Skin = 0,
  /** Horn, claw, hoof, teeth, spikes, a shell's lip. */
  Keratin = 1,
  /** Shell, plates, carapace. */
  Shell = 2,
  /** A glowing organ (lure, sac, the insides of see-through skin). */
  Glow = 3,
  /** Inside the mouth. */
  Mouth = 4,
}

/** Where on the body a piece is: the torso, a limb, the head (patterns fade off the limbs and head). */
export const enum Region { Body = 0, Limb = 1, Head = 2 }

export interface Prim {
  readonly type: 'cone' | 'ellipsoid' | 'box';
  /** cone: from a to b, radii ra at a and rb at b. ellipsoid: centre a, radii (ra·sx, ra·sy, ra·b[0]). box: from a to b, half sizes ra·sx, ra·sy. */
  readonly a: V3;
  readonly b: V3;
  readonly ra: number;
  readonly rb: number;
  /** Cross-section squash: side (x) and up (y) in the piece's own frame. */
  readonly sx: number;
  readonly sy: number;
  readonly bone: number;
  /** How softly it blends into the rest, metres (0: a hard edge). */
  readonly k: number;
  readonly part: Part;
  readonly region: Region;
}

export interface EyeDef {
  readonly bone: number;
  readonly pos: V3;
  readonly radius: number;
  /** Which way it looks (unit). */
  readonly dir: V3;
}

export type LegPole = 'fwd' | 'back' | 'up' | 'out';

export interface LegDef {
  /** The chain's bones from the hip; the foot is the end of the last. */
  readonly bones: number[];
  readonly lens: number[];
  readonly foot: V3;
  /** +1 left, -1 right. */
  readonly side: number;
  /** 0 the hindmost pair .. 1 the foremost (radial: angle / 2π). */
  readonly along: number;
  readonly pairIndex: number;
  readonly pole: LegPole;
  /** A third segment held at a lean (a raised heel). */
  readonly digitigrade: boolean;
  readonly ankleUp: number;
  readonly ankleFwd: number;
  readonly kind: 'leg' | 'arm' | 'radial';
}

export interface ChainDef {
  readonly bones: number[];
  readonly tip: V3;
  readonly side: number;
}

export interface Anatomy {
  readonly bones: BoneDef[];
  readonly prims: Prim[];
  readonly eyes: EyeDef[];
  readonly legs: LegDef[];
  /** Arms: an upright walker's, or a crab's claws (each with its pincer bone in `pincers`). */
  readonly arms: LegDef[];
  readonly pincers: number[];
  readonly spine: number[];
  readonly neck: number[];
  readonly head: number;
  readonly jaw: number;
  readonly tail: number[];
  readonly antennae: ChainDef[];
  readonly tentacles: ChainDef[];
  readonly lure: ChainDef | null;
  readonly ears: number[];
  readonly bell: number;
  /** A drifter: the origin is at the bell's centre, not on the ground. */
  readonly originCenter: boolean;
  /** Bounds of all the flesh, model space. */
  readonly min: V3;
  readonly max: V3;
  readonly headHeight: number;
  /** Length of a leg (the first), metres; the pelvis' height. */
  readonly legLength: number;
  readonly pelvisHeight: number;
}

// ------------------------------------------------------------------ vectors

const add = (a: V3, b: V3): V3 => [a[0] + b[0], a[1] + b[1], a[2] + b[2]];
const sub = (a: V3, b: V3): V3 => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
const mul = (a: V3, s: number): V3 => [a[0] * s, a[1] * s, a[2] * s];
const len = (a: V3): number => Math.hypot(a[0], a[1], a[2]);
const norm = (a: V3): V3 => {
  const l = len(a) || 1;
  return [a[0] / l, a[1] / l, a[2] / l];
};
const dot = (a: V3, b: V3): number => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
/** Between two points (core's `mixRgb` is the same lerp of a triple). */
const mix: (a: V3, b: V3, t: number) => V3 = mixRgb;

/** Small vector helpers on plain arrays, for the rig. */
export const vec = { add, sub, mul, len, norm, dot, mix };

/**
 * Two-bone IK: the knee for hip `h`, target `t`, segment lengths and a pole (the bend's side).
 * Shared by the layout and the rig.
 */
export function solveKnee(h: V3, t: V3, l1: number, l2: number, pole: V3, out: V3 = [0, 0, 0]): V3 {
  let dx = t[0] - h[0], dy = t[1] - h[1], dz = t[2] - h[2];
  let d = Math.hypot(dx, dy, dz);
  if (d < 1e-6) { dx = 0; dy = -1; dz = 0; d = 1e-6; }
  const ix = dx / d, iy = dy / d, iz = dz / d;
  const dc = clamp(d, Math.abs(l1 - l2) + 1e-4, l1 + l2 - 1e-4);
  const a = (l1 * l1 - l2 * l2 + dc * dc) / (2 * dc);
  const hgt = Math.sqrt(Math.max(0, l1 * l1 - a * a));
  const pd = pole[0] * ix + pole[1] * iy + pole[2] * iz;
  let px = pole[0] - ix * pd, py = pole[1] - iy * pd, pz = pole[2] - iz * pd;
  const pl = Math.hypot(px, py, pz);
  if (pl < 1e-6) { px = 0; py = 0; pz = 1; } else { px /= pl; py /= pl; pz /= pl; }
  out[0] = h[0] + ix * a + px * hgt;
  out[1] = h[1] + iy * a + py * hgt;
  out[2] = h[2] + iz * a + pz * hgt;
  return out;
}

// ------------------------------------------------------------------ builder

class Builder {
  readonly bones: BoneDef[] = [];
  readonly prims: Prim[] = [];
  readonly eyes: EyeDef[] = [];
  bone(name: string, parent: number, pos: V3, kind: BoneKind): number {
    this.bones.push({ name, parent, pos: [pos[0], pos[1], pos[2]], kind });
    return this.bones.length - 1;
  }
  cone(a: V3, b: V3, ra: number, rb: number, bone: number, k: number, part = Part.Skin, region = Region.Body, sx = 1, sy = 1): void {
    this.prims.push({ type: 'cone', a: [...a], b: [...b], ra, rb, sx, sy, bone, k, part, region });
  }
  ell(c: V3, r: V3, bone: number, k: number, part = Part.Skin, region = Region.Body): void {
    const m = Math.max(r[0], r[1], r[2]);
    this.prims.push({ type: 'ellipsoid', a: [...c], b: [r[2] / m, 0, 0], ra: m, rb: m, sx: r[0] / m, sy: r[1] / m, bone, k, part, region });
  }
  slab(a: V3, b: V3, hx: number, hy: number, bone: number, k: number, part = Part.Skin, region = Region.Body): void {
    const m = Math.max(hx, hy);
    this.prims.push({ type: 'box', a: [...a], b: [...b], ra: m, rb: m, sx: hx / m, sy: hy / m, bone, k, part, region });
  }
}

/** Lay out the rest-pose body of a species (deterministic). */
export function anatomyOf(sp: Species): Anatomy {
  const rng = new Rng(sp.seed ^ 0xb0d1);
  const B = new Builder();
  const plan = sp.plan;
  const L = sp.length;
  const R = L * sp.girth;
  const kBody = R * lerp(0.55, 0.12, sp.chunky);
  const jointed = plan === 'hexapod' || plan === 'octopod' || plan === 'myriapod' || plan === 'crab';
  const crab = plan === 'crab', slug = plan === 'slug', floater = plan === 'floater';
  const longBody = plan === 'serpent' || plan === 'myriapod' || slug;
  const originCenter = floater;
  const sx = sp.bodyWidth, sy = sp.bodyHeight;

  const root = B.bone('root', -1, [0, 0, 0], 'root');

  // ---------------- legs' reach sets the pelvis' height
  const pairs = sp.limbs.pairs;
  const legLen = L * sp.limbs.length;
  const sprawl = sp.limbs.splay;
  let pelvisY: number;
  if (originCenter) pelvisY = 0;
  else if (pairs === 0) pelvisY = R * sy * (slug ? 0.62 : 0.92);
  else if (crab) pelvisY = legLen * 0.38 + R * sy * 0.35;
  else if (jointed) pelvisY = legLen * 0.42 + R * 0.25;
  else pelvisY = legLen * (pairs === 2 ? sp.limbs.hindRatio : 1) * (1 - sprawl * 0.55) * 0.93 + R * 0.2;
  if (plan === 'radial') pelvisY = L * sp.armLen * 0.22 + R * sy * 0.5;
  // A walker's belly clears the ground.
  if (!originCenter && pairs > 0) pelvisY = Math.max(pelvisY, R * sy * 0.85);

  // ---------------- spine
  const spine: number[] = [];
  const nS = Math.max(1, sp.spineSegs);
  const biped = pairs === 1 && !sp.upright;
  const bodyPitch = sp.upright ? Math.PI / 2 - 0.08 : biped ? 0.18 : 0;
  const zBack = sp.upright || biped ? 0 : -L / 2;
  const spinePts: V3[] = [];
  for (let i = 0; i <= nS; i++) {
    const t = i / nS;
    const along = t * L;
    const arch = Math.sin(Math.PI * t) * sp.spineArch * L * 0.16;
    let y = pelvisY + along * Math.sin(bodyPitch) + arch * Math.cos(bodyPitch);
    const z = zBack + along * Math.cos(bodyPitch) - arch * Math.sin(bodyPitch);
    // Long front legs stand the body front-high.
    if (pairs === 2 && !sp.upright) y += (1 - sp.limbs.hindRatio) * legLen * 0.93 * (1 - sprawl * 0.55) * t;
    spinePts.push([0, y, z]);
  }
  if (plan === 'radial' || floater) spinePts.length = 1;
  let parent = root;
  for (let i = 0; i < Math.max(1, spinePts.length - 1); i++) {
    const b = B.bone('spine' + i, parent, spinePts[i], 'spine');
    spine.push(b);
    parent = b;
  }
  const pelvis = spine[0];
  const chest = spine[spine.length - 1];
  const chestPt = spinePts[spinePts.length - 1];
  const hipR = R * (longBody ? 1 : lerp(0.85, 1, 1 / sp.chest));
  const chestR = R * (longBody ? 1 : clamp(sp.chest, 0.7, 1.4));

  // ---------------- torso
  let bell = -1;
  const tentacles: ChainDef[] = [];
  if (floater) {
    // A drifting bell: a dome with a frilled rim, glowing sacs inside, tentacles hanging.
    const discR = L * 0.5;
    bell = B.bone('bell', pelvis, [0, 0, 0], 'bell');
    B.ell([0, discR * 0.15 * sy, 0], [discR, discR * 0.85 * sy, discR], bell, kBody);
    B.ell([0, -discR * 0.25 * sy, 0], [discR * 1.04, discR * 0.22, discR * 1.04], bell, discR * 0.12);
    B.cone([0, -discR * 0.2, 0], [0, -discR * 0.95, 0], discR * 0.3, discR * 0.1, bell, discR * 0.2, Part.Skin, Region.Limb);
    const sacs = Math.max(1, sp.dorsal.sacs);
    for (let i = 0; i < sacs; i++) {
      const a = (i / sacs) * Math.PI * 2 + rng.float();
      const r = sacs === 1 ? 0 : discR * 0.42;
      B.ell([Math.cos(a) * r, discR * 0.3 * sy, Math.sin(a) * r], [discR * 0.3, discR * 0.36, discR * 0.3], bell, discR * 0.1, Part.Glow);
    }
    for (let i = 0; i < sp.arms; i++) {
      const a = (i / sp.arms) * Math.PI * 2 + 0.3;
      const dx = Math.sin(a), dz = Math.cos(a);
      const segs = 5;
      const tl = L * sp.armLen * rng.range(0.7, 1.15);
      let p: V3 = [dx * discR * 0.8, -discR * 0.2, dz * discR * 0.8];
      let par = bell;
      const bones: number[] = [];
      for (let k = 0; k < segs; k++) {
        const q: V3 = add(p, [dx * tl * 0.03, -tl / segs, dz * tl * 0.03]);
        const b = B.bone(`tent${i}_${k}`, par, p, 'tentacle');
        bones.push(b);
        const r0 = discR * 0.08 * (1 - k / segs) + discR * 0.012;
        B.cone(p, q, r0, r0 * 0.75, b, r0 * 0.4, Part.Skin, Region.Limb);
        p = q;
        par = b;
      }
      tentacles.push({ bones, tip: p, side: i % 2 ? 1 : -1 });
    }
  } else if (plan === 'radial') {
    const discR = L * 0.5;
    B.ell([0, pelvisY, 0], [discR, R * sy * 0.6, discR], pelvis, kBody);
    B.ell([0, pelvisY + R * sy * 0.35, 0], [discR * 0.55, R * sy * 0.55, discR * 0.55], pelvis, kBody, Part.Shell);
  } else if (jointed && !crab && plan !== 'myriapod') {
    // An insect's or a spider's body comes in parts: a swollen abdomen behind, a narrow waist, and a
    // smaller thorax in front that carries the legs (not one capsule).
    const boneAt = (t: number) => spine[Math.min(spine.length - 1, Math.round(t * (spine.length - 1)))];
    const swell = lerp(1.05, 1.3, sp.chunky), waist = plan === 'octopod' ? 0.36 : 0.44;
    B.ell(mix(spinePts[0], chestPt, waist * 0.45), [R * sx * swell, R * sy * swell * 0.92, L * waist * 0.62], boneAt(0.1), R * 0.12, Part.Skin, Region.Body);
    B.cone(mix(spinePts[0], chestPt, waist * 0.8), mix(spinePts[0], chestPt, waist + 0.08), R * 0.34, R * 0.34, boneAt(waist), R * 0.08, Part.Shell, Region.Body, sx, sy);
    B.ell(mix(spinePts[0], chestPt, lerp(waist + 0.08, 1, 0.5)), [R * sx * 0.74, R * sy * 0.68, L * (1 - waist) * 0.5], boneAt(0.72), R * 0.1, Part.Shell, Region.Body);
  } else {
    for (let i = 0; i < spinePts.length - 1; i++) {
      const t0 = i / (spinePts.length - 1), t1 = (i + 1) / (spinePts.length - 1);
      let r0 = lerp(hipR, chestR, t0) * (longBody ? 1 : 1 - 0.12 * Math.sin(Math.PI * t0));
      let r1 = lerp(hipR, chestR, t1);
      // A slug narrows to its tail, a centipede's segments pinch.
      if (slug) { r0 = R * lerp(0.55, 1, Math.sin(Math.PI * lerp(0.2, 0.8, t0))); r1 = R * lerp(0.55, 1, Math.sin(Math.PI * lerp(0.2, 0.8, t1))); }
      B.cone(spinePts[i], spinePts[i + 1], r0, r1, spine[i], kBody, Part.Skin, Region.Body, sx, sy);
      if (plan === 'myriapod') B.ell(mix(spinePts[i], spinePts[i + 1], 0.5), [r0 * sx * 1.15, r0 * sy * 0.7, L / nS * 0.42], spine[i], r0 * 0.1, Part.Shell);
    }
    if (crab) {
      // A wide, flat carapace over the legs, its front edge notched.
      const c = mix(spinePts[0], chestPt, 0.5);
      B.ell(add(c, [0, R * sy * 0.3, 0]), [R * sx * 1.25, R * sy * 0.8, L * 0.62], spine[Math.floor(spine.length / 2)], R * 0.12, Part.Shell);
    } else if (slug) {
      // The foot it glides on: a flat sole along the whole body, a little wider than it.
      for (let i = 0; i < spinePts.length - 1; i++) {
        const a = spinePts[i], b = spinePts[i + 1];
        B.cone([a[0], R * 0.18, a[2]], [b[0], R * 0.18, b[2]], R * 0.95, R * 0.95, spine[i], R * 0.3, Part.Skin, Region.Limb, 1.25, 0.22);
      }
    } else if (!longBody && !jointed) {
      // Rib cage, haunches and shoulders give a vertebrate its silhouette.
      const mid = mix(spinePts[0], chestPt, 0.62);
      B.ell(add(mid, [0, -R * sp.belly * 0.6, 0]), [chestR * sx * 1.05, chestR * sy * (1 + sp.belly * 0.5), L * 0.36], spine[Math.floor((spine.length - 1) * 0.62)], kBody);
      B.ell(add(spinePts[0], [0, R * 0.05, 0]), [hipR * sx * 1.05, hipR * sy * 0.95, hipR * 1.1], pelvis, kBody);
    }
    if (sp.dorsal.shell > 0 && !crab) {
      if (slug) shellCoil(B, add(mix(spinePts[0], chestPt, 0.42), [0, R * sy * 0.55, 0]), R * (1.1 + sp.dorsal.shell * 0.6), spine[Math.floor(spine.length / 2)], rng);
      else {
        const c = mix(spinePts[0], chestPt, 0.45);
        B.ell(add(c, [0, R * sy * 0.45, 0]), [R * sx * 1.25 * (0.8 + sp.dorsal.shell * 0.3), R * sy * (0.75 + sp.dorsal.shell * 0.35), L * 0.55], spine[Math.floor(spine.length / 2)], R * 0.08, Part.Shell);
      }
    }
  }

  // ---------------- neck and head
  const neck: number[] = [];
  let headBone = chest, jaw = -1;
  const headR = L * sp.head.size;
  let headPos: V3 = [...chestPt];
  let lure: ChainDef | null = null;
  const antennae: ChainDef[] = [];
  if (!floater && plan !== 'radial') {
    const nLen = L * sp.neckLen;
    const raise = sp.upright ? Math.PI / 2 : sp.neckRaise;
    const nDir: V3 = sp.upright ? [0, 1, 0.05] : [0, Math.sin(raise), Math.cos(raise)];
    const nSeg = sp.neckSegs;
    let prev = chestPt;
    parent = chest;
    const neckBase = chestR * 0.62;
    for (let i = 0; i < nSeg; i++) {
      const t = (i + 1) / nSeg;
      const bend = sp.neckLen > 0.6 ? Math.sin(t * Math.PI) * 0.15 : 0;
      const p: V3 = add(prev, mul(norm(add(nDir, [0, -bend, bend])), nLen / nSeg));
      const b = B.bone('neck' + i, parent, prev, 'neck');
      neck.push(b);
      const r0 = lerp(neckBase, headR * 0.62, i / nSeg), r1 = lerp(neckBase, headR * 0.62, t);
      B.cone(prev, p, r0, r1, b, kBody * 0.8, Part.Skin, Region.Body, sx * 0.95, sy);
      // The muscle along a vertebrate's neck.
      if (!jointed && !longBody && i === 0 && nLen > R) B.ell(add(mix(prev, p, 0.5), [0, r0 * 0.25, 0]), [r0 * 0.85, r0 * 0.95, nLen / nSeg * 0.6], b, r0 * 0.5);
      prev = p;
      parent = b;
    }
    headPos = add(prev, [0, headR * 0.15, 0]);
    headBone = B.bone('head', parent, prev, 'head');
    const h = headR;
    const hk = h * lerp(0.4, 0.12, sp.chunky);
    B.ell(headPos, [h * 0.9, h * 0.85, h], headBone, hk, Part.Skin, Region.Head);
    // Brow and cheeks: a skull, not a ball.
    if (!jointed && !slug) {
      B.ell(add(headPos, [0, h * 0.35, h * 0.25]), [h * 0.72, h * 0.4, h * 0.6], headBone, hk * 0.8, Part.Skin, Region.Head);
      for (const s of [-1, 1]) B.ell(add(headPos, [s * h * 0.45, -h * 0.25, h * 0.15]), [h * 0.42, h * 0.45, h * 0.55], headBone, hk * 0.8, Part.Skin, Region.Head);
    }
    const snoutLen = h * sp.head.snout * 1.2;
    const snoutDir = norm([0, -0.25 - (sp.neckRaise > 0.6 ? 0.45 : 0), 1]);
    const snoutTip = add(headPos, mul(snoutDir, h * 0.5 + snoutLen));
    if (snoutLen > h * 0.15) {
      B.cone(add(headPos, mul(snoutDir, h * 0.3)), snoutTip, h * 0.62, h * 0.62 * sp.head.snoutTip, headBone, hk, Part.Skin, Region.Head, 1, 0.85);
      B.ell(snoutTip, [h * 0.3 * sp.head.snoutTip, h * 0.24 * sp.head.snoutTip, h * 0.2], headBone, h * 0.08, jointed ? Part.Keratin : Part.Mouth, Region.Head);
    }
    // The lower jaw on its own bone, so a bite opens the mouth.
    const jawPivot: V3 = add(headPos, [0, -h * 0.35, -h * 0.2]);
    jaw = B.bone('jaw', headBone, jawPivot, 'jaw');
    if (snoutLen > h * 0.2) {
      const jawTip = add(snoutTip, [0, -h * 0.25, -snoutLen * 0.08]);
      B.cone(add(jawPivot, [0, 0, h * 0.2]), jawTip, h * 0.45, h * 0.3 * sp.head.snoutTip, jaw, hk * 0.8, Part.Skin, Region.Head, 0.9, 0.6);
      if (!sp.peaceful && snoutLen > h * 0.4) {
        for (const s of [-1, 1]) {
          const fang = add(snoutTip, [s * h * 0.22 * sp.head.snoutTip, -h * 0.12, -snoutLen * 0.12]);
          B.cone(fang, add(fang, [0, -h * 0.32, h * 0.03]), h * 0.07, h * 0.005, headBone, h * 0.02, Part.Keratin, Region.Head);
        }
      }
    } else B.ell(add(jawPivot, [0, -h * 0.05, h * 0.55]), [h * 0.5, h * 0.25, h * 0.4], jaw, hk * 0.6, Part.Skin, Region.Head);
    if (sp.head.mandibles) {
      for (const s of [-1, 1]) {
        const base: V3 = add(headPos, [s * h * 0.45, -h * 0.25, h * 0.75]);
        const ml = h * sp.head.mandibles;
        const m = add(base, [s * ml * 0.35, -ml * 0.05, ml * 0.5]);
        const tip = add(m, [-s * ml * 0.35, 0, ml * 0.35]);
        B.cone(base, m, h * 0.16, h * 0.11, jaw, h * 0.05, Part.Keratin, Region.Head);
        B.cone(m, tip, h * 0.11, h * 0.01, jaw, h * 0.03, Part.Keratin, Region.Head);
      }
    }
    // Horns: curved chains of cones.
    for (let i = 0; i < sp.head.horns; i++) {
      const n = sp.head.horns;
      const pairI = Math.floor(i / 2);
      const s = n === 1 ? 0 : i % 2 === 0 ? 1 : -1;
      const hl = h * sp.head.hornLen * (pairI ? 0.6 : 1);
      let p: V3 = n === 1 ? add(headPos, [0, h * 0.55, h * (0.5 + sp.head.snout * 0.5)]) : add(headPos, [s * h * (0.5 + pairI * 0.15), h * 0.6, h * (0.15 - pairI * 0.35)]);
      let dir: V3 = norm([s * (0.6 + pairI * 0.3), 1 - Math.max(0, sp.head.hornSweep) * 0.6, -sp.head.hornSweep * 0.8 + (n === 1 ? 0.6 : 0)]);
      let r = h * 0.2 * (pairI ? 0.7 : 1) * (0.7 + sp.head.hornLen * 0.25);
      const segs = 4;
      for (let k = 0; k < segs; k++) {
        const q = add(p, mul(dir, hl / segs));
        const r2 = r * (k === segs - 1 ? 0.06 : 0.7);
        B.cone(p, q, r, r2, headBone, r * 0.3, Part.Keratin, Region.Head);
        const c = sp.head.hornCurl * 0.55;
        dir = norm(add(dir, [s * c * 0.3, (-c * 0.5 * (k + 1)) / segs, -c * 0.6]));
        p = q;
        r = r2;
      }
    }
    if (sp.head.tusks) {
      for (const s of [-1, 1]) {
        const tl = h * sp.head.tusks * 1.3;
        const base: V3 = add(snoutTip, [s * h * 0.28, -h * 0.25, -snoutLen * 0.3]);
        const m = add(base, [s * tl * 0.25, -tl * 0.25, tl * 0.4]);
        const tip = add(m, [s * tl * 0.1, tl * 0.35, tl * 0.25]);
        B.cone(base, m, h * 0.11, h * 0.08, headBone, h * 0.04, Part.Keratin, Region.Head);
        B.cone(m, tip, h * 0.08, h * 0.01, headBone, h * 0.03, Part.Keratin, Region.Head);
      }
    }
    if (sp.head.crest > 0) {
      const a = add(headPos, [0, h * 0.7, h * 0.3]);
      const b2 = add(headPos, [0, h * (0.8 + sp.head.crest * 0.6), -h * (0.6 + sp.head.crest * 0.7)]);
      B.cone(a, b2, h * 0.3, h * 0.08, headBone, h * 0.15, Part.Shell, Region.Head, 0.25, 1.6);
    }
    if (sp.head.frill > 0) {
      const fr = h * (1 + sp.head.frill);
      B.ell(add(headPos, [0, h * 0.2, -h * 0.7]), [fr, fr * 0.85, h * 0.12], headBone, h * 0.1, Part.Shell, Region.Head);
    }
    // Ears, on their own bones (they twitch, and lie back in anger).
    if (sp.head.ears > 0) {
      for (const s of [-1, 1]) {
        const el = h * sp.head.ears * 0.9;
        const base: V3 = add(headPos, [s * h * 0.55, h * 0.55, -h * 0.25]);
        const eb = B.bone('ear' + (s > 0 ? 'L' : 'R'), headBone, base, 'ear');
        const tip = add(base, mul(norm([s * 0.6, 1, -0.35]), el));
        B.cone(base, tip, h * 0.3 * (1.2 - sp.head.earPoint * 0.4), h * 0.03 + h * 0.15 * (1 - sp.head.earPoint), eb, h * 0.1, Part.Skin, Region.Head, 1, 0.35);
      }
    }
    // Eyes: in sockets on the skull, or on stalks.
    const ne = sp.head.eyes;
    const er = h * 0.2 * sp.head.eyeSize * (sp.head.pupil === 'compound' ? 1.25 : 1) * (ne > 4 ? 0.7 : 1);
    const frontal = sp.peaceful ? 0.25 : 0.65;
    for (let i = 0; i < ne; i++) {
      let s: number, row: number;
      if (ne === 1) { s = 0; row = 0; } else if (ne === 3) { s = i === 2 ? 0 : i === 0 ? 1 : -1; row = i === 2 ? 1 : 0; } else { s = i % 2 === 0 ? 1 : -1; row = Math.floor(i / 2); }
      const zf = h * (0.45 + frontal * 0.2) - row * h * 0.28;
      const ex = s * h * (0.62 - frontal * 0.18 - row * 0.05);
      const ey = h * (0.28 + row * 0.18) + (s === 0 && ne === 3 ? h * 0.25 : 0);
      const q = Math.hypot(ex / (h * 0.9), ey / (h * 0.85), zf / h) || 1;
      const sink = 0.98 - (er / h) * 0.45;
      let pos: V3 = add(headPos, [(ex / q) * sink, (ey / q) * sink, (zf / q) * sink]);
      const dir = norm([s * (1 - frontal), 0.15, 0.35 + frontal]);
      let bone = headBone;
      if (sp.head.stalks > 0 && row === 0) {
        // On a stalk: a thin chain that sways.
        const sl = h * sp.head.stalks * 1.3;
        const base = pos;
        const tip = add(base, mul(norm([s * 0.35, 1, 0.3]), sl));
        bone = B.bone(`stalk${i}`, headBone, base, 'stalk');
        B.cone(base, tip, er * 0.45, er * 0.32, bone, er * 0.3, Part.Skin, Region.Head);
        pos = tip;
        antennae.push({ bones: [bone], tip, side: s || 1 });
      }
      B.eyes.push({ bone, pos, radius: er * (row ? 0.75 : 1), dir });
      if (bone === headBone) B.ell(add(pos, mul(dir, -er * 0.5)), [er * 1.2, er * 1.1, er * 1.2], headBone, er * 0.6, Part.Skin, Region.Head);
    }
    // Feelers.
    if (sp.head.antennae > 0) {
      for (const s of [1, -1]) {
        const al = L * sp.head.antennae;
        let p: V3 = add(headPos, [s * h * 0.3, h * 0.55, h * 0.55]);
        let par = headBone;
        const bones: number[] = [];
        let dir: V3 = norm([s * 0.5, 0.7, 0.8]);
        for (let k = 0; k < 3; k++) {
          const q = add(p, mul(dir, al / 3));
          const b = B.bone(`ant${s > 0 ? 'L' : 'R'}${k}`, par, p, 'antenna');
          bones.push(b);
          B.cone(p, q, h * 0.05 * (1 - k * 0.25), h * 0.04 * (1 - k * 0.3), b, 0, Part.Keratin, Region.Head);
          dir = norm(add(dir, [s * 0.05, -0.3, 0.1]));
          p = q;
          par = b;
        }
        antennae.push({ bones, tip: p, side: s });
      }
    }
    if (sp.head.whiskers) {
      const tipZ = h * (0.5 + sp.head.snout * 1.2);
      for (const s of [1, -1]) for (let k = 0; k < 3; k++) {
        const base = add(headPos, [s * h * 0.3, -h * 0.05 + k * h * 0.06, tipZ * 0.85]);
        B.cone(base, add(base, [s * h * 1.3, (k - 1) * h * 0.25, -h * 0.2]), h * 0.015, h * 0.004, headBone, 0, Part.Keratin, Region.Head);
      }
    }
    // A lure: a stalk arching forward over the head with a glowing bulb at its end (it sways).
    if (sp.head.lure > 0) {
      const ll = h * sp.head.lure * 2.2;
      let p: V3 = add(headPos, [0, h * 0.8, h * 0.2]);
      let par = headBone;
      const bones: number[] = [];
      let dir: V3 = norm([0, 1, 0.35]);
      for (let k = 0; k < 4; k++) {
        const q = add(p, mul(dir, ll / 4));
        const b = B.bone(`lure${k}`, par, p, 'lure');
        bones.push(b);
        B.cone(p, q, h * 0.07 * (1 - k * 0.15), h * 0.055 * (1 - k * 0.15), b, h * 0.03, Part.Skin, Region.Head);
        dir = norm(add(dir, [0, -0.38, 0.32]));
        p = q;
        par = b;
      }
      B.ell(p, [h * 0.18, h * 0.2, h * 0.18], bones[bones.length - 1], h * 0.05, Part.Glow, Region.Head);
      lure = { bones, tip: p, side: 1 };
    }
  }

  // ---------------- tail
  const tail: number[] = [];
  if (sp.tail.length > 0 && !floater && plan !== 'radial') {
    const tl = L * sp.tail.length;
    const n = sp.tail.segments;
    let p: V3 = [...spinePts[0]];
    parent = pelvis;
    const baseDir: V3 = biped || sp.upright ? norm([0, -0.15, -1]) : norm([0, longBody ? 0 : -0.25, -1]);
    let r = hipR * sp.tail.thickness * (plan === 'serpent' ? 1.6 : 1) * (slug ? 1.4 : 1);
    const taper = plan === 'serpent' ? 0.86 : slug ? 0.6 : 0.78;
    for (let i = 0; i < n; i++) {
      const t = (i + 1) / n;
      const curl = sp.tail.curl * (jointed ? 1.4 : 0.5);
      // Curl lifts it more and more (a scorpion's arcs over its back).
      const ang = curl * t * t * 2.2;
      const d: V3 = norm([0, baseDir[1] + Math.sin(ang), baseDir[2] * Math.cos(ang)]);
      const q = add(p, mul(d, tl / n));
      const b = B.bone('tail' + i, parent, p, 'tail');
      tail.push(b);
      const r2 = Math.max(r * taper, R * 0.04);
      if (jointed) B.ell(mix(p, q, 0.5), [r * 1.1 * sx, r * sy, (tl / n) * 0.6], b, r * 0.15, Part.Shell);
      else B.cone(p, q, r, r2, b, kBody * 0.7, Part.Skin, Region.Body, sx, sy * (slug ? 0.6 : 1));
      r = r2;
      p = q;
      parent = b;
    }
    const last = tail[tail.length - 1];
    const lastDir = norm(sub(p, B.bones[last].pos));
    switch (sp.tail.tip) {
      case 'club':
        B.ell(p, [r * 3, r * 2.5, r * 3.5], last, r, Part.Shell);
        break;
      case 'sting':
        B.ell(p, [r * 2.2, r * 2.2, r * 2.6], last, r * 0.8, Part.Shell);
        B.cone(add(p, mul(lastDir, r * 1.5)), add(p, add(mul(lastDir, r * 5), [0, -r * 3, 0])), r * 0.9, r * 0.05, last, r * 0.4, Part.Keratin);
        break;
      case 'tuft':
        B.ell(add(p, mul(lastDir, r * 2)), [r * 2.6, r * 2.6, r * 4], last, r, Part.Skin);
        break;
      case 'spikes':
        for (const s of [-1, 1]) for (let k = 0; k < 2; k++) {
          const c = sub(p, mul(lastDir, k * r * 3));
          B.cone(c, add(c, [s * r * 6, r * 3, -r * 2]), r * 0.8, r * 0.05, last, r * 0.3, Part.Keratin);
        }
        break;
      case 'lure':
        B.ell(add(p, mul(lastDir, r * 1.5)), [r * 2.2, r * 2.2, r * 2.2], last, r * 0.5, Part.Glow);
        break;
    }
  }

  // ---------------- spines along the back
  if (!floater && plan !== 'radial' && sp.dorsal.spikes > 0) {
    const back = spinePts.map((q, i) => ({ q, b: spine[Math.min(i, spine.length - 1)] }));
    const tailPts = tail.map((b) => ({ q: B.bones[b].pos, b }));
    const ridge = [...tailPts.slice(0, Math.ceil(tailPts.length / 2)).reverse(), ...back];
    if (ridge.length > 1) {
      for (let i = 0; i < sp.dorsal.spikes; i++) {
        const t = (i + 0.5) / sp.dorsal.spikes;
        const f = t * (ridge.length - 1);
        const i0 = Math.floor(f), i1 = Math.min(ridge.length - 1, i0 + 1);
        const c = mix(ridge[i0].q, ridge[i1].q, f - i0);
        const r = lerp(hipR, chestR, t) * (sp.dorsal.shell ? 1.25 : 0.95) * sy;
        const h2 = L * sp.dorsal.spikeLen * (0.6 + Math.sin(t * Math.PI) * 0.6);
        const base = add(c, [0, r * 0.85, 0]);
        if (sp.dorsal.plates) B.cone(base, add(base, [0, h2 * 1.3, -h2 * 0.2]), h2 * 0.55, h2 * 0.08, ridge[i0].b, h2 * 0.15, Part.Shell, Region.Body, 0.18, 1);
        else B.cone(base, add(base, [0, h2, -h2 * 0.35]), Math.max(h2 * 0.25, R * 0.06), R * 0.008, ridge[i0].b, R * 0.06, Part.Keratin, Region.Body);
      }
    }
  }

  // ---------------- legs
  const legs: LegDef[] = [];
  const chainBones = (name: string, parentB: number, hip: V3, foot: V3, lens: number[], pole: V3, ankleUp: number, ankleFwd: number, kind: BoneKind): number[] => {
    let pts: V3[];
    if (lens.length === 3) {
      const ank = add(foot, mul(norm([0, ankleUp, ankleFwd]), lens[2]));
      pts = [hip, solveKnee(hip, ank, lens[0], lens[1], pole), ank];
    } else pts = [hip, solveKnee(hip, foot, lens[0], lens[1], pole)];
    const out: number[] = [];
    let par = parentB;
    for (let i = 0; i < pts.length; i++) {
      const b = B.bone(name + i, par, pts[i], kind);
      out.push(b);
      par = b;
    }
    return out;
  };
  const legFlesh = (bones: number[], foot: V3, rTop: number, footStyle: string, haunch: number, knees: boolean) => {
    const pts = bones.map((b) => B.bones[b].pos).concat([foot]);
    for (let i = 0; i < bones.length; i++) {
      const t0 = i / bones.length, t1 = (i + 1) / bones.length;
      const taper = jointed ? 0.55 : 0.42;
      const r0 = rTop * lerp(1, taper, t0), r1 = rTop * lerp(1, taper, t1);
      B.cone(pts[i], pts[i + 1], r0, r1, bones[i], Math.min(r0, r1) * 0.6, jointed ? Part.Shell : Part.Skin, Region.Limb);
      // Joints show: a knuckle at a vertebrate's knee and ankle, a ring at an arthropod's.
      if (i > 0 && (knees || jointed)) B.ell(pts[i], [r0 * 1.12, r0 * 1.12, r0 * 1.12], bones[i], r0 * 0.4, jointed ? Part.Shell : Part.Skin, Region.Limb);
    }
    // The thigh or upper arm's muscle.
    if (haunch > 0) B.ell(mix(pts[0], pts[1], 0.35), [rTop * 1.25 * haunch, rTop * 1.6 * haunch, rTop * 1.5 * haunch], bones[0], rTop * 0.8, Part.Skin, Region.Body);
    const last = bones[bones.length - 1];
    const fr = rTop * 0.45 * sp.limbs.footSize;
    switch (footStyle) {
      case 'hoof':
        B.cone(add(foot, [0, fr * 1.3, 0]), add(foot, [0, fr * 0.2, fr * 0.25]), fr * 1.05, fr * 1.25, last, fr * 0.2, Part.Keratin, Region.Limb);
        break;
      case 'paw':
        B.ell(add(foot, [0, fr * 0.65, fr * 0.6]), [fr * 1.3, fr * 0.7, fr * 1.6], last, fr * 0.5, Part.Skin, Region.Limb);
        break;
      case 'claw':
        B.ell(add(foot, [0, fr * 0.6, fr * 0.5]), [fr * 1.25, fr * 0.65, fr * 1.5], last, fr * 0.5, Part.Skin, Region.Limb);
        for (let c = -1; c <= 1; c++) {
          const cb = add(foot, [c * fr * 0.7, fr * 0.45, fr * 1.6]);
          B.cone(cb, add(cb, [c * fr * 0.15, -fr * 0.45, fr * 0.9]), fr * 0.28, fr * 0.02, last, fr * 0.1, Part.Keratin, Region.Limb);
        }
        break;
      case 'pad':
        for (let c = -1; c <= 1; c++) B.ell(add(foot, [c * fr * 0.9, fr * 0.3, fr * 1.2 + (c === 0 ? fr * 0.4 : 0)]), [fr * 0.5, fr * 0.35, fr * 0.5], last, fr * 0.4, Part.Skin, Region.Limb);
        B.ell(add(foot, [0, fr * 0.4, fr * 0.3]), [fr * 1.1, fr * 0.55, fr * 1.1], last, fr * 0.5, Part.Skin, Region.Limb);
        break;
      case 'point':
        B.cone(add(foot, [0, rTop * 0.35, 0]), foot, rTop * 0.3, rTop * 0.08, last, 0, Part.Keratin, Region.Limb);
        break;
    }
  };

  if (pairs > 0 && plan !== 'radial') {
    const legSpine = plan === 'myriapod' ? spine : spine;
    for (let j = 0; j < pairs; j++) {
      const t = pairs === 1 ? 0 : j / (pairs - 1);
      const hind = j === 0 && pairs > 1;
      const kneeFwd = hind || pairs === 1;
      let attach: V3;
      let parentB: number;
      if (crab) {
        // Along the carapace's sides, fanned from back to front.
        const tt = lerp(0.15, 0.8, t);
        attach = mix(spinePts[0], chestPt, tt);
        parentB = spine[Math.min(spine.length - 1, Math.round(tt * (spine.length - 1)))];
      } else if (jointed && plan !== 'myriapod') {
        // An insect's legs all on its thorax.
        const tt = lerp(0.45, 0.95, t);
        attach = mix(spinePts[0], chestPt, tt);
        parentB = spine[Math.min(spine.length - 1, Math.round(tt * (spine.length - 1)))];
      } else if (plan === 'myriapod' || pairs > 3) {
        const idx = Math.min(legSpine.length - 1, Math.round(t * (legSpine.length - 1)));
        parentB = legSpine[idx] ?? pelvis;
        attach = [...B.bones[parentB].pos];
      } else if (pairs === 1) {
        attach = [...spinePts[0]];
        parentB = pelvis;
      } else {
        const idx = Math.round(t * (spine.length - 1));
        parentB = t >= 1 ? chest : spine[idx];
        attach = t >= 1 ? [...chestPt] : [...spinePts[Math.round(t * (spinePts.length - 1))]];
      }
      const ll = legLen * (hind ? sp.limbs.hindRatio : 1);
      const rTop = jointed ? R * sp.limbs.thickness * 1.6 : R * sp.limbs.thickness * (hind ? 1.1 : 1);
      for (const s of [1, -1]) {
        const w = sp.upright ? Math.max(R * sx * 0.62, rTop * 1.5) : R * sx * (crab ? 0.95 : jointed ? 0.75 : 0.62);
        const hip: V3 = add(attach, [s * w, jointed ? 0 : -R * 0.35, 0]);
        let foot: V3;
        let lens: number[];
        let pole: V3;
        let ankleUp = 1, ankleFwd = 0;
        if (jointed) {
          const fan = crab ? (t - 0.5) * 1.4 : (t - 0.5) * 1.1;
          const reach = ll * (0.7 + sprawl * 0.25);
          foot = [hip[0] + s * reach * Math.cos(fan * 0.9), 0, hip[2] + reach * Math.sin(fan * 0.9) * 1.1];
          lens = [ll * 0.48, ll * 0.62];
          pole = [s * 0.4, 1, 0];
        } else {
          foot = [hip[0] + s * (sprawl * ll * 0.7 + R * 0.04), 0, hip[2] + (pairs === 1 ? 0.02 * L : 0)];
          const dig = sp.limbs.digitigrade || (pairs === 1 && !sp.upright);
          if (dig || (pairs >= 2 && !hind && !sp.upright)) {
            lens = [ll * 0.4, ll * 0.4, ll * 0.27];
            if (kneeFwd) { ankleUp = 0.82; ankleFwd = -0.55; pole = [s * sprawl, 0, 1]; }
            else { ankleUp = 0.95; ankleFwd = 0.18; pole = [s * sprawl, 0, -1]; }
          } else {
            lens = [ll * 0.5, ll * 0.52];
            pole = [s * sprawl * 1.5, sprawl * 0.8, kneeFwd ? 1 : -1];
          }
          if (sprawl > 0.4) pole = [s * 0.6, 1, kneeFwd ? 0.3 : -0.3];
        }
        const bones = chainBones(`leg${j}${s > 0 ? 'L' : 'R'}`, parentB, hip, foot, lens, pole, ankleUp, ankleFwd, 'leg');
        legFlesh(bones, foot, rTop, sp.limbs.foot, !jointed && (hind || pairs === 1) ? 1.15 : !jointed ? 0.9 : 0, !jointed);
        legs.push({
          bones, lens, foot, side: s, along: t, pairIndex: j,
          pole: jointed || sprawl > 0.4 ? 'up' : kneeFwd ? 'fwd' : 'back',
          digitigrade: lens.length === 3, ankleUp, ankleFwd, kind: 'leg',
        });
      }
    }
  }

  // A star's arms walk it: legs round the disc.
  if (plan === 'radial') {
    const n = sp.arms;
    const discR = L * 0.5;
    const al = L * sp.armLen;
    for (let i = 0; i < n; i++) {
      const a = (i / n) * Math.PI * 2 + 0.3;
      const dx = Math.sin(a), dz = Math.cos(a);
      const hip: V3 = [dx * discR * 0.85, pelvisY, dz * discR * 0.85];
      // The tip rests on its underside, not sunk to its middle.
      const foot: V3 = [dx * (discR + al * 0.8), R * 0.25, dz * (discR + al * 0.8)];
      const lens = [al * 0.5, al * 0.55];
      const bones = chainBones('arm' + i, pelvis, hip, foot, lens, [0, 1, 0], 1, 0, 'leg');
      legFlesh(bones, foot, R * 0.45, 'point', 0, false);
      legs.push({ bones, lens, foot, side: dx >= 0 ? 1 : -1, along: i / n, pairIndex: i, pole: 'up', digitigrade: false, ankleUp: 1, ankleFwd: 0, kind: 'radial' });
    }
  }

  // ---------------- arms: an upright walker's, or a crab's claws held in front
  const arms: LegDef[] = [];
  const pincers: number[] = [];
  if (sp.limbs.arms) {
    for (const s of [1, -1]) {
      const claw = sp.limbs.claws > 0;
      const big = claw && s > 0 ? sp.limbs.bigClaw : 1;
      const al = L * sp.limbs.armLength * (claw ? Math.sqrt(big) : 1);
      const sh: V3 = claw ? add(chestPt, [s * chestR * sx * 0.75, -chestR * 0.1, chestR * 0.2]) : add(chestPt, [s * chestR * sx * 1.05, -chestR * 0.15, 0]);
      const hand: V3 = claw ? add(sh, [s * al * 0.3, -al * 0.25, al * 0.75]) : add(sh, [s * al * 0.18, -al * 0.95, al * 0.12]);
      // Claws are held clear of the ground.
      if (claw) hand[1] = Math.max(hand[1], R * 0.32 * big * 0.8);
      const lens = [al * 0.5, al * 0.5];
      const bones = chainBones('arm' + (s > 0 ? 'L' : 'R'), chest, sh, hand, lens, claw ? [s, 0.6, 0] : [s * 0.2, 0, -1], 1, 0, 'arm');
      const rTop = (claw ? R * 0.22 * Math.sqrt(big) : R * sp.limbs.thickness * 0.95);
      legFlesh(bones, hand, rTop, claw ? 'none' : 'paw', claw ? 0 : 0.8, !claw);
      if (claw) {
        // The pincer: a swollen palm, a fixed finger and a moving one on its own bone.
        // Pointing forward, near level: a claw held out, not dug in.
        const f0 = norm(sub(hand, B.bones[bones[1]].pos));
        const fwd = norm([f0[0], Math.max(f0[1], -0.12), f0[2]]);
        const palmR = R * 0.32 * big;
        const palm = add(hand, mul(fwd, palmR * 0.9));
        B.ell(palm, [palmR * 0.75, palmR * 0.62, palmR * 1.1], bones[1], palmR * 0.3, Part.Shell, Region.Limb);
        const tipF = add(palm, add(mul(fwd, palmR * 2.1), [s * -palmR * 0.2, -palmR * 0.15, 0]));
        B.cone(add(palm, mul(fwd, palmR * 0.6)), tipF, palmR * 0.42, palmR * 0.06, bones[1], palmR * 0.15, Part.Shell, Region.Limb);
        const pivot = add(palm, add(mul(fwd, palmR * 0.5), [0, palmR * 0.35, 0]));
        const pb = B.bone('pincer' + (s > 0 ? 'L' : 'R'), bones[1], pivot, 'pincer');
        const tipM = add(pivot, add(mul(fwd, palmR * 1.6), [s * -palmR * 0.15, palmR * 0.1, 0]));
        B.cone(pivot, tipM, palmR * 0.32, palmR * 0.05, pb, palmR * 0.1, Part.Keratin, Region.Limb);
        pincers.push(pb);
      }
      arms.push({ bones, lens, foot: hand, side: s, along: 1, pairIndex: 0, pole: 'back', digitigrade: false, ankleUp: 1, ankleFwd: 0, kind: 'arm' });
    }
  }

  // ---------------- bounds
  const min: V3 = [1e9, 1e9, 1e9], max: V3 = [-1e9, -1e9, -1e9];
  const grow = (p: V3, r: number) => {
    for (let i = 0; i < 3; i++) {
      min[i] = Math.min(min[i], p[i] - r);
      max[i] = Math.max(max[i], p[i] + r);
    }
  };
  for (const pr of B.prims) {
    const r = pr.ra * Math.max(pr.sx, pr.sy, pr.type === 'ellipsoid' ? pr.b[0] : 1);
    grow(pr.a, r);
    if (pr.type !== 'ellipsoid') grow(pr.b, Math.max(pr.rb, pr.ra) * Math.max(pr.sx, pr.sy));
  }
  for (const e of B.eyes) grow(e.pos, e.radius);
  return {
    bones: B.bones, prims: B.prims, eyes: B.eyes, legs, arms, pincers,
    spine, neck, head: headBone, jaw, tail, antennae, tentacles, lure,
    ears: B.bones.map((b, i) => (b.kind === 'ear' ? i : -1)).filter((i) => i >= 0),
    bell, originCenter, min, max,
    headHeight: max[1] - (originCenter ? min[1] : 0),
    legLength: legs.length ? legs[0].lens.reduce((a, b) => a + b, 0) : R,
    pelvisHeight: pelvisY,
  };
}

/** A snail's shell: a coil of cones winding up and inwards, its mouth towards the head. */
function shellCoil(B: Builder, base: V3, size: number, bone: number, rng: Rng): void {
  const turns = rng.range(1.6, 2.6);
  const steps = 14;
  let prev: V3 | null = null, prevR = 0;
  for (let i = 0; i <= steps; i++) {
    const t = i / steps;
    const a = t * turns * Math.PI * 2;
    const rad = size * (1 - t * 0.85);
    const p: V3 = [Math.sin(a) * rad * 0.15, base[1] + Math.cos(a) * rad * 0.55 + t * size * 0.25, base[2] - size * 0.15 + Math.sin(a + Math.PI / 2) * rad * 0.55];
    const r = size * 0.55 * (1 - t * 0.8);
    if (prev) B.cone(prev, p, prevR, r, bone, size * 0.08, Part.Shell, Region.Body, 0.85, 1);
    prev = p;
    prevR = r;
  }
}
