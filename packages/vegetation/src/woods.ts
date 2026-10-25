/**
 * Woods seen from afar, per pixel (TSL, three/webgpu): crowns and the shaded gaps between them, clumps, and
 * stands that thin into glades, from a ground point's crown cover and the trees' spacing. Drawn on the
 * ground where the trees themselves are no longer drawn, so whole forests keep their structure to the
 * horizon. Every scale fades to its mean once a pixel's footprint would make it shimmer, so a wood seen
 * from far away has the light of the same wood seen close.
 *
 * From Solarpolis (src/render/groundShaders.ts, docs/far-view.md: "Woods from afar", "Woods seen at a slant").
 */
import { clamp, dFdx, dFdy, dot, exp, float, floor, fract, length, log, max, mix, mx_noise_float, positionWorld, select, smoothstep, sqrt, vec3 } from 'three/tsl';
import type { Node } from 'three/webgpu';

/** A jittered offset 0..1 per integer lattice cell. */
export function cellHash(c: Node<'vec3'>): Node<'vec3'> {
  const a = fract(c.mul(vec3(0.1031, 0.103, 0.0973)));
  const b = a.add(dot(a, a.yxz.add(33.33)));
  return fract(b.xxy.add(b.yxx).mul(b.zyx));
}

/**
 * A pixel's footprint on the ground (m): long down the line of sight on ground seen at a slant, short across it.
 * `shown(size)` is how much of a pattern of that size may show: while the footprint's area is well under it (`foot`,
 * the geometric mean), and as long as the long side (`reach`) still samples it twice, or it would alias into streaks
 * along the view. Past that, a pattern gives way to its mean. Fragment stage only (screen-space derivatives).
 */
export function footprint(): { foot: Node<'float'>; reach: Node<'float'>; shown: (size: Node<'float'>) => Node<'float'> } {
  const fx = length(dFdx(positionWorld)), fy = length(dFdy(positionWorld));
  const reach = max(fx, fy), foot = sqrt(fx.mul(fy));
  return { foot, reach, shown: (size) => float(1).sub(smoothstep(0.15, 0.45, foot.div(size))).mul(float(1).sub(smoothstep(0.5, 1, reach.div(size)))) };
}

/** A crown's radius in its cell (the cells are the trees' spacing apart), for a mean-sized tree. */
const CROWN = 0.8;
/**
 * With a crown in every cell by chance P, the share of the ground they cover is 1 − e^(−CLOSE · P): the cells are a
 * jittered 3D lattice sliced by the ground, so crowns overlap and leave gaps as a real canopy does.
 */
const CLOSE = 2.14;
/** The floor between the crowns of a closed wood keeps this share of its light. */
const GAP_SHADE = 0.25;

export interface WoodsLight {
  /** The crowns' light at their tops, and its mean over a crown (match the near trees' hulls). Default 0.85, 0.5. */
  top?: number;
  mean?: number;
}

/**
 * The woods from afar: `ground` is the floor's colour, `crown` the crowns', `cover` the share of the ground the
 * crowns cover (0 … 1), `spacing` the trees' spacing (m), `world` the point (world, m). Closed woods stay closed and
 * open land stays open: the stands and clumps only move the cover where it is in between. Returns the colour and
 * `bump`, how far the normal leans out over each crown (world xz, up to 1 at its rim; add it to the ground's normal).
 */
export function woodsFromAfar(ground: Node<'vec3'>, crown: Node<'vec3'>, cover: Node<'float'>, spacing: Node<'float'>, world: Node<'vec3'>, light: WoodsLight = {}): { color: Node<'vec3'>; bump: Node<'vec3'> } {
  const top = light.top ?? 0.85, mean = light.mean ?? 0.5;
  const { foot, shown } = footprint();
  const cell = max(spacing, 2);
  // Stands (two dozen trees across), groves (ten) and clumps (five): the cover wanders where the woods are open or
  // thinning, so their edges break into groves and clearings rather than fading over the ground's points.
  const between = sqrt(clamp(cover.mul(float(1).sub(cover)), 0, 0.25)).mul(2);
  const stands = mx_noise_float(world.div(cell.mul(24))).mul(shown(cell.mul(24)));
  const groves = mx_noise_float(world.div(cell.mul(10)).add(vec3(3.7, 11.2, 1.9))).mul(shown(cell.mul(10)));
  const clumps = mx_noise_float(world.div(cell.mul(5)).add(vec3(17.3, 5.1, 9.7))).mul(shown(cell.mul(5)));
  const local = clamp(cover.add(stands.mul(0.8).add(groves.mul(0.55)).add(clumps.mul(0.4)).mul(between)), 0, 1);
  // The crowns: one per cell by chance, so that together they cover `local`; the nearest one decides.
  const chance = clamp(log(max(float(1).sub(local.mul(0.999)), 1e-3)).negate().div(CLOSE), 0, 1);
  const p = world.div(cell), base = floor(p.sub(0.5));
  let q: Node<'float'> = float(9);
  let off: Node<'vec3'> = vec3(0);
  for (let o = 0; o < 8; o++) {
    const c = base.add(vec3(o & 1, (o >> 1) & 1, (o >> 2) & 1));
    const jitter = cellHash(c);
    const there = fract(jitter.x.mul(7.31).add(jitter.y.mul(3.17)).add(jitter.z.mul(5.73))).lessThan(chance);
    const v = p.sub(c.add(jitter.mul(0.6).add(0.2))).div(jitter.z.mul(0.3).add(0.85).mul(CROWN));
    const d = length(v), nearer = there.and(d.lessThan(q));
    off = select(nearer, v, off);
    q = select(nearer, d, q);
  }
  const edge = foot.div(cell.mul(CROWN)).add(0.04);
  const inside = float(1).sub(smoothstep(float(1).sub(edge), float(1).add(edge), q));
  // Lit tops, darker rims; the floor between them in their shade.
  const dome = clamp(float(1).sub(q.mul(q).mul(0.5)), 0.5, 1);
  // A dome's mean over a crown is 0.75 (q² is even over its disc): the light runs from the mean there to the top's.
  const slope = (top - mean) / 0.25;
  // Crowns differ: groups of a few trees stand taller or lower, lighter or darker, yellower or bluer, so a canopy
  // seen from above is mottled even where every crown is too small to see.
  const tone = mx_noise_float(world.div(cell.mul(3)).add(vec3(5.3, 2.9, 7.1))).mul(shown(cell.mul(3)));
  const hue = mix(vec3(1.12, 1, 0.78), vec3(0.88, 1, 1.15), groves.mul(0.5).add(0.5));
  const tinted = crown.mul(hue).mul(tone.mul(0.45).add(stands.mul(0.35)).add(1));
  const crowns = tinted.mul(dome.mul(slope).add(top - slope));
  const gap = ground.mul(mix(float(1), float(GAP_SHADE), smoothstep(0.15, 0.6, local)));
  const near = mix(gap, crowns, inside);
  // Beyond the crowns' size: their mean over the covered share.
  const covered = float(1).sub(exp(chance.mul(-CLOSE)));
  const far = mix(gap, tinted.mul(mean), covered);
  // The land itself is never one flat colour: stands and clumps tint it a little, woods and open ground alike.
  const seen = shown(cell.mul(2.6));
  const color = mix(near, far, float(1).sub(seen)).mul(stands.mul(0.1).add(groves.mul(0.06)).add(clumps.mul(0.05)).add(1));
  // Each crown a dome to the light: the ground's normal leans out from the crown's middle (world xz), so the sun
  // lights one side and leaves the other in shade, as on the trees drawn near; further out the colour's mean carries it.
  // Only while a crown spans many pixels: a normal that turns within a pixel or two shimmers into moiré.
  const bump = vec3(off.x, 0, off.z).mul(inside).mul(shown(cell));
  return { color, bump };
}
