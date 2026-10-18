/**
 * The shape of a head, for headwear that fits it: how far the skull reaches from a point inside it in
 * every direction (a map over azimuth and elevation), measured from the morphed body, and the same for
 * the hair over it. Hats, caps and bands are built over this map instead of over a sphere, so the
 * skull never pokes through on a long head, a high forehead or a child's round one.
 *
 * Everything here is in head-socket space (the `head` socket: origin between the ears, +y up, +z
 * forward, +x to the body's left). A hat also names its band (`HatBand`): the line round the head where
 * its edge sits, the brow at the front and lower at the back. The hair above the band is under the hat
 * and is not drawn (`bandPlane`, the character's hair cut); the hair below it shows.
 */
import type { SocketFrame } from './bodyBuild';

type V3 = [number, number, number];

/** Azimuth columns and elevation rows of a head map. */
export const HEAD_AZ = 36;
export const HEAD_EL = 16;
/** Lowest elevation the map covers (below that is the jaw and neck). */
export const HEAD_EL_MIN = -Math.PI / 3;

export interface HeadShape {
  /** Centre of the map (socket space). */
  c: V3;
  /** Skull radius from `c` per bin, row-major (elevation rows of `HEAD_AZ` azimuths), dilated by a bin
   *  so that reading it anywhere never comes out inside the skull. */
  r: number[];
  /** The hair's outer radius per bin, where the character has hair (0: none); set by the character. */
  hair?: number[];
  /** Mean skull radius (as BodyFit.headRadius). */
  radius: number;
  /** Height of the brow line (just over the eyebrows) and of the tops of the ears. */
  brow: number;
  earTop: number;
  /** How far forward the ears sit (their z), for a band that must clear them. */
  earZ: number;
  /** Height of the top of the skull. */
  top: number;
}

/**
 * Where a hat's edge sits: `front` in head radii above the brow line at the forehead, `back` in head
 * radii above the ears' level (the socket's) at the back of the head; level from side to side. It is
 * kept above the ears.
 */
export interface HatBand { front: number; back: number }

const binOf = (az: number, el: number): [number, number] => {
  const a = ((az / (Math.PI * 2)) * HEAD_AZ + HEAD_AZ * 2) % HEAD_AZ;
  const e = ((el - HEAD_EL_MIN) / (Math.PI / 2 - HEAD_EL_MIN)) * HEAD_EL;
  return [a, e];
};

/** Direction of (azimuth, elevation): azimuth 0 forward (+z), π/2 to the left (+x). */
export const headDir = (az: number, el: number): V3 => [Math.sin(az) * Math.cos(el), Math.sin(el), Math.cos(az) * Math.cos(el)];

/** Rest model space → socket space. */
export function toSocket(f: SocketFrame, p: ArrayLike<number>, i = 0): V3 {
  const d = [p[i] - f.pos[0], p[i + 1] - f.pos[1], p[i + 2] - f.pos[2]], B = f.basis;
  return [d[0] * B[0] + d[1] * B[1] + d[2] * B[2], d[0] * B[3] + d[1] * B[4] + d[2] * B[5], d[0] * B[6] + d[1] * B[7] + d[2] * B[8]];
}

/** A radius map from points (socket space, from `c`): the max per bin, empty bins filled from their
 *  neighbours, then dilated by one bin so a bilinear read is never below a point it was made from. */
function radiusMap(c: V3, pts: Iterable<V3>, fillEmpty: boolean): number[] {
  const raw = new Array<number>(HEAD_AZ * HEAD_EL).fill(0);
  for (const p of pts) {
    const d: V3 = [p[0] - c[0], p[1] - c[1], p[2] - c[2]], r = Math.hypot(d[0], d[1], d[2]);
    if (r < 1e-6) continue;
    const el = Math.asin(Math.max(-1, Math.min(1, d[1] / r)));
    if (el < HEAD_EL_MIN) continue;
    const [a, e] = binOf(Math.atan2(d[0], d[2]), el);
    const k = Math.min(HEAD_EL - 1, Math.floor(e)) * HEAD_AZ + Math.floor(a);
    raw[k] = Math.max(raw[k], r);
  }
  const at = (e: number, a: number) => raw[e * HEAD_AZ + ((a + HEAD_AZ) % HEAD_AZ)];
  // Fill holes (a bin no vertex fell in) from the bins round it, a few passes.
  for (let pass = 0; fillEmpty && pass < 8; pass++) {
    let empty = 0;
    for (let e = 0; e < HEAD_EL; e++) for (let a = 0; a < HEAD_AZ; a++) {
      if (raw[e * HEAD_AZ + a] > 0) continue;
      let s = 0, n = 0;
      for (const [de, da] of [[0, 1], [0, -1], [1, 0], [-1, 0]]) {
        const ee = e + de;
        if (ee < 0 || ee >= HEAD_EL) continue;
        const v = at(ee, a + da);
        if (v > 0) { s += v; n++; }
      }
      if (n) raw[e * HEAD_AZ + a] = s / n; else empty++;
    }
    if (!empty) break;
  }
  const out = raw.slice();
  for (let e = 0; e < HEAD_EL; e++) for (let a = 0; a < HEAD_AZ; a++) {
    let m = 0;
    for (let de = -1; de <= 1; de++) for (let da = -1; da <= 1; da++) {
      const ee = e + de;
      if (ee >= 0 && ee < HEAD_EL) m = Math.max(m, at(ee, a + da));
    }
    // The top row's bins all meet at the crown: one radius for all of them.
    out[e * HEAD_AZ + a] = m;
  }
  const topRow = (HEAD_EL - 1) * HEAD_AZ;
  const crown = Math.max(...out.slice(topRow));
  for (let a = 0; a < HEAD_AZ; a++) out[topRow + a] = crown;
  return out;
}

/** Read a radius map at (azimuth, elevation), bilinear between bin centres. */
export function mapAt(map: number[], az: number, el: number): number {
  const [a, e] = binOf(az, Math.max(HEAD_EL_MIN, Math.min(Math.PI / 2, el)));
  const ac = a - 0.5, ec = Math.max(0, Math.min(HEAD_EL - 1, e - 0.5));
  const a0 = Math.floor(ac), e0 = Math.floor(ec), fa = ac - a0, fe = ec - e0, e1 = Math.min(HEAD_EL - 1, e0 + 1);
  const g = (ee: number, aa: number) => map[ee * HEAD_AZ + ((aa % HEAD_AZ) + HEAD_AZ) % HEAD_AZ];
  return (g(e0, a0) * (1 - fa) + g(e0, a0 + 1) * fa) * (1 - fe) + (g(e1, a0) * (1 - fa) + g(e1, a0 + 1) * fa) * fe;
}

/** The skull's radius from the map's centre toward (azimuth, elevation). */
export const skullAt = (h: HeadShape, az: number, el: number): number => mapAt(h.r, az, el);

/** The hair's outer radius there (the skull's where there is no hair). */
export const hairAt = (h: HeadShape, az: number, el: number): number => Math.max(skullAt(h, az, el), h.hair ? mapAt(h.hair, az, el) : 0);

/** The point at radius `r` from the map's centre toward (azimuth, elevation). */
export function headPoint(h: HeadShape, az: number, el: number, r: number): V3 {
  const d = headDir(az, el);
  return [h.c[0] + d[0] * r, h.c[1] + d[1] * r, h.c[2] + d[2] * r];
}

/**
 * Measure a head: `pos` the body's rest positions, `isHead(v)` the vertices rigid to the head bone
 * (the face below the brow is left out here), `isEar(v)` the ears', `eyes` the eyeballs (as
 * BodyData.eyes), `frame` the head socket.
 */
export function measureHead(pos: Float32Array, count: number, isHead: (v: number) => boolean, isEar: (v: number) => boolean, eyes: ArrayLike<number>, frame: SocketFrame, radius: number): HeadShape {
  const c: V3 = [0, radius * 0.12, radius * 0.08];
  // Eyebrows: a little over the eyeballs' tops. The face below them (nose, cheeks) is not skull.
  const eyeY = (toSocket(frame, eyes, 0)[1] + toSocket(frame, eyes, 4)[1]) / 2, eyeR = (eyes[3] + eyes[7]) / 2;
  const brow = eyeY + eyeR * 1.9;
  const skull: V3[] = [];
  let earTop = -Infinity, earZ = 0, earN = 0, top = -Infinity;
  for (let v = 0; v < count; v++) {
    if (isEar(v)) {
      const p = toSocket(frame, pos, v * 3);
      earTop = Math.max(earTop, p[1]); earZ += p[2]; earN++;
      continue;
    }
    if (!isHead(v)) continue;
    const p = toSocket(frame, pos, v * 3);
    if (p[1] < brow && p[2] > c[2] + radius * 0.3) continue;
    skull.push(p);
    top = Math.max(top, p[1]);
  }
  return {
    c, r: radiusMap(c, skull, true), radius, brow,
    earTop: isFinite(earTop) ? earTop : radius * 0.35,
    earZ: earN ? earZ / earN : 0,
    top,
  };
}

/** The hair's map from its rest positions (model space, xyz triples): set it on the shape. */
export function measureHair(h: HeadShape, frame: SocketFrame, positions: Float32Array[]): number[] {
  function* pts(): Iterable<V3> {
    for (const p of positions) for (let i = 0; i < p.length; i += 3) yield toSocket(frame, p, i);
  }
  return radiusMap(h.c, pts(), false);
}

/**
 * The plane of a band (socket space) as [nx, ny, nz, d]: a point p is above the band (under the hat)
 * where n·p > d. Level from side to side; kept clear of the ears.
 */
export function bandPlane(h: HeadShape, b: HatBand): [number, number, number, number] {
  const R = h.radius;
  const zF = h.c[2] + R, zB = h.c[2] - R;
  let yF = h.brow + b.front * R, yB = b.back * R;
  // Over the ears: the band's height where the ears are must clear their tops. The back comes up
  // (the front stays at the brow), as much as that can; then all of it.
  const w = Math.max(0, Math.min(0.85, (h.earZ - zB) / (zF - zB))), clear = h.earTop + R * 0.04;
  const yAtEar = yB + w * (yF - yB);
  if (yAtEar < clear) yB += (clear - yAtEar) / (1 - w);
  // Normal ⟂ (F − B) in the y–z plane, pointing up.
  let ny = zF - zB, nz = -(yF - yB);
  const l = Math.hypot(ny, nz);
  ny /= l; nz /= l;
  return [0, ny, nz, ny * yF + nz * zF];
}

/** Height of a band plane over the point (x, z): where the band crosses there. */
export const bandY = (p: [number, number, number, number], x: number, z: number): number => (p[3] - p[0] * x - p[2] * z) / p[1];

/** Elevation, toward azimuth `az`, where the skull (pushed out by `out`) meets the band plane. */
export function bandElevation(h: HeadShape, p: [number, number, number, number], az: number, out = 0): number {
  const side = (el: number) => {
    const q = headPoint(h, az, el, skullAt(h, az, el) + out);
    return p[0] * q[0] + p[1] * q[1] + p[2] * q[2] - p[3];
  };
  let lo = HEAD_EL_MIN, hi = Math.PI / 2;
  if (side(lo) > 0) return lo;
  for (let i = 0; i < 30; i++) {
    const m = (lo + hi) / 2;
    if (side(m) > 0) hi = m; else lo = m;
  }
  return (lo + hi) / 2;
}

/** A socket-space plane in rest model space (as [nx, ny, nz, d]: above where n·p > d). */
export function planeToModel(f: SocketFrame, p: [number, number, number, number]): [number, number, number, number] {
  const B = f.basis;
  const n: V3 = [B[0] * p[0] + B[3] * p[1] + B[6] * p[2], B[1] * p[0] + B[4] * p[1] + B[7] * p[2], B[2] * p[0] + B[5] * p[1] + B[8] * p[2]];
  return [n[0], n[1], n[2], p[3] + n[0] * f.pos[0] + n[1] * f.pos[1] + n[2] * f.pos[2]];
}
