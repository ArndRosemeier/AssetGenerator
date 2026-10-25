/**
 * The farmland's props as meshes, in the building format (BuildingMesh, so they draw with the buildings'
 * shader): post-and-rail fences round the paddocks and stacks of hay. `detail` false gives the far
 * version (every other post, one rail; a coarser stack).
 */
import { Rng } from '@futuremagic/core';
import { BuildingMat, Frame, Out, type BuildingMesh, type RGB } from './building';
import type { TownProp } from './farmland';

/** Weathered fence wood, from silver to brown. */
const WOODS: RGB[] = [[150, 136, 120], [128, 108, 88], [112, 96, 82]];
/** Hay, sun-bleached to fresh. */
const HAYS: RGB[] = [[255, 238, 176], [246, 226, 160], [255, 246, 196]];

export function propMesh(p: TownProp, origin: [number, number, number], detail = true): BuildingMesh {
  const out = new Out(new Frame({ cx: 0, cz: 0, ux: 1, uz: 0, vx: 0, vz: 1, y: 0 }, origin));
  const r = new Rng(p.seed);
  if (p.kind === 'fence') fence(out, p.posts, r.pick(WOODS), detail);
  else haystack(out, p.x, p.y, p.z, p.r, p.h, r.pick(HAYS), detail);
  return {
    position: Float32Array.from(out.pos), normal: Float32Array.from(out.nrm), uv: Float32Array.from(out.uv),
    mat: Uint8Array.from(out.mat), tint: Uint8Array.from(out.tint), index: Uint32Array.from(out.idx),
  };
}

/** Rails only join posts nearer than this (the gate is a wider gap). */
const RAIL_SPAN = 4;

function fence(o: Out, posts: number[], c: RGB, detail: boolean): void {
  const n = posts.length / 3, w = 0.07;
  for (let i = 0; i < n; i++) {
    if (!detail && i % 2 && i !== n - 1) continue;
    const x = posts[i * 3], y = posts[i * 3 + 1], z = posts[i * 3 + 2];
    o.box(x - w, x + w, y - 0.3, y + 1.25, z - w, z + w, BuildingMat.Oak, c);
  }
  for (let i = 0; i + 1 < n; i++) {
    const a = i * 3, b = a + 3;
    if (Math.hypot(posts[b] - posts[a], posts[b + 2] - posts[a + 2]) > RAIL_SPAN) continue;
    for (const h of detail ? [0.5, 1.02] : [0.8]) rail(o, posts[a], posts[a + 1] + h, posts[a + 2], posts[b], posts[b + 1] + h, posts[b + 2], c);
  }
}

/** A rail (8 by 12 cm) from one post to the next: its four long faces. */
function rail(o: Out, ax: number, ay: number, az: number, bx: number, by: number, bz: number, c: RGB): void {
  const L = Math.hypot(bx - ax, bz - az) || 1, nx = -(bz - az) / L, nz = (bx - ax) / L, s = 0.04, t = 0.06;
  const P = (e: number, side: number, up: number) => [e ? bx : ax, (e ? by : ay) + up * t, e ? bz : az].map((v, k) => v + (k === 0 ? nx * s * side : k === 2 ? nz * s * side : 0));
  const uv = [[0, 0], [L, 0], [L, 0.12], [0, 0.12]];
  o.quad([P(0, 1, -1), P(1, 1, -1), P(1, 1, 1), P(0, 1, 1)], [nx, 0, nz], uv, BuildingMat.Oak, c);
  o.quad([P(0, -1, -1), P(1, -1, -1), P(1, -1, 1), P(0, -1, 1)], [-nx, 0, -nz], uv, BuildingMat.Oak, c);
  o.quad([P(0, -1, 1), P(1, -1, 1), P(1, 1, 1), P(0, 1, 1)], [0, 1, 0], uv, BuildingMat.Oak, c);
  o.quad([P(0, -1, -1), P(1, -1, -1), P(1, 1, -1), P(0, 1, -1)], [0, -1, 0], uv, BuildingMat.Oak, c);
}

/** A round stack: straight sides a third of the way up, then a dome. */
function haystack(o: Out, x: number, y: number, z: number, R: number, H: number, c: RGB, detail: boolean): void {
  const seg = detail ? 12 : 6, bands = detail ? 5 : 2;
  // The profile from the foot (a little in the ground) to the top: (radius, height).
  const prof: [number, number][] = [[R * 0.92, -0.2], [R, H * 0.35]];
  for (let i = 1; i <= bands; i++) {
    const t = (i / bands) * (Math.PI / 2);
    prof.push([R * Math.cos(t) * (i === bands ? 0 : 1), H * 0.35 + (H * 0.65) * Math.sin(t)]);
  }
  for (let k = 0; k < seg; k++) {
    const a0 = (k / seg) * Math.PI * 2, a1 = ((k + 1) / seg) * Math.PI * 2, am = (a0 + a1) / 2;
    for (let i = 0; i + 1 < prof.length; i++) {
      const [r0, h0] = prof[i], [r1, h1] = prof[i + 1];
      const dn = [Math.cos(am) * (h1 - h0), r0 - r1, Math.sin(am) * (h1 - h0)], l = Math.hypot(dn[0], dn[1], dn[2]) || 1;
      const nrm = [dn[0] / l, dn[1] / l, dn[2] / l];
      const s0 = (R * (a1 - a0)) * k, s1 = s0 + R * (a1 - a0);
      const p = (r: number, h: number, a: number) => [x + Math.cos(a) * r, y + h, z + Math.sin(a) * r];
      if (r1 < 1e-3) o.tri([p(r0, h0, a0), p(r0, h0, a1), p(0, h1, am)], nrm, [[s0, h0], [s1, h0], [(s0 + s1) / 2, h1]], BuildingMat.Thatch, c);
      else o.quad([p(r0, h0, a0), p(r0, h0, a1), p(r1, h1, a1), p(r1, h1, a0)], nrm, [[s0, h0], [s1, h0], [s1, h1], [s0, h1]], BuildingMat.Thatch, c);
    }
  }
}
