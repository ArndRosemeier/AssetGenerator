/**
 * Node materials (TSL) for procedural creatures (./three/figure.ts): one for the flesh of every
 * species, so a new species is never a new shader, and one for the eyes. The coat is painted into the
 * vertex colours; `look` carries per vertex the roughness, the integument, the glow and how see-through
 * the skin is. The flesh shader adds the integument's fine grain on the rest shape (so it holds still on
 * the moving body), faded where it would be finer than a pixel: fur, scales, chitin's seams, slime, a
 * hide's wrinkles, stone's cracks. Glowing spots pulse; see-through skin glows at the rim. A hit flashes
 * it red (`userData.hurt`, per object, 0..1). The game registers them in its own material registry
 * (warmed up before first use). From Dunfinity.
 */
import { DoubleSide, MeshStandardNodeMaterial, type Node } from 'three/webgpu';
import { BIRD_SHOULDER } from './birds';
import { Fn, If, abs, attribute, dot, faceDirection, float, mix, mx_noise_float, mx_noise_vec3, mx_worley_noise_vec2, normalView, positionGeometry, positionView, sin, smoothstep, time, uniform, vec2, vec3, vertexColor } from 'three/tsl';

/** Screen-space bump of `height` (no tangents needed). */
function critterBump(height: Node<'float'>, scale: number, n: Node<'vec3'> = normalView) {
  const dH = vec2(height.dFdx(), height.dFdy()).mul(scale);
  const sx = positionView.dFdx(), sy = positionView.dFdy();
  const r1 = sy.cross(n), r2 = n.cross(sx);
  const det = sx.dot(r1).mul(faceDirection);
  const grad = det.sign().mul(dH.x.mul(r1).add(dH.y.mul(r2)));
  return det.abs().mul(n).sub(grad).normalize();
}

export interface CritterFleshOptions {
  /** Light the rim catches so a creature in the dark still reads as a shape (colour times strength). */
  readonly outline?: Node<'vec3'>;
}

/** The flesh of every procedural creature (attributes position, normal, color, look; skinned). */
export function critterFlesh(o: CritterFleshOptions = {}): MeshStandardNodeMaterial {
  const m = new MeshStandardNodeMaterial({ vertexColors: true, roughness: 0.8, metalness: 0 });
  const look = attribute<'vec4'>('look', 'vec4');
  const kind = look.y.mul(8).floor();
  const p = positionGeometry;
  const fadeAt = (q: Node<'vec3'>) => smoothstep(0.6, 0.2, q.fwidth().length());
  const fur = Fn(() => {
    const q = p.mul(vec3(150, 150, 38));
    return mx_noise_float(q).mul(0.6).add(mx_noise_float(p.mul(vec3(60, 60, 15)).add(3.1)).mul(0.4)).mul(fadeAt(q));
  });
  const scales = Fn(() => {
    const q = p.mul(vec3(46, 46, 32));
    const c = mx_worley_noise_vec2(q);
    return smoothstep(0.0, 0.3, c.y.sub(c.x)).mul(fadeAt(q));
  });
  const seams = Fn(() => {
    const q = p.mul(7).add(mx_noise_vec3(p.mul(3)).mul(0.08));
    const s = q.z.fract();
    return smoothstep(0.0, 0.07, s).mul(smoothstep(1.0, 0.93, s)).mul(fadeAt(q)).add(fadeAt(q).oneMinus());
  });
  const wrinkles = Fn(() => {
    const q = p.mul(vec3(38, 38, 20));
    return abs(mx_noise_float(q)).oneMinus().mul(fadeAt(q));
  });
  const detail = Fn(() => {
    const height = float(0).toVar(), tint = float(1).toVar();
    If(kind.equal(0), () => { const f = fur(); height.assign(f); tint.assign(f.mul(0.24).add(0.86)); })
      .ElseIf(kind.equal(1), () => { const w = wrinkles(); height.assign(w.mul(0.6)); tint.assign(w.mul(0.12).add(0.92)); })
      .ElseIf(kind.equal(2), () => { const s = scales(); height.assign(s); tint.assign(s.mul(0.25).add(0.8)); })
      .ElseIf(kind.equal(3), () => { const s = seams(); height.assign(s.mul(0.8)); tint.assign(s.mul(0.4).add(0.6)); })
      .ElseIf(kind.equal(4), () => { const n = mx_noise_float(p.mul(18)); height.assign(n.mul(0.3)); tint.assign(n.mul(0.15).add(0.95)); })
      .Else(() => { const c = mx_worley_noise_vec2(p.mul(7)); const crack = smoothstep(0.0, 0.05, c.y.sub(c.x)); height.assign(crack); tint.assign(crack.mul(0.35).add(0.65)); });
    return vec2(height, tint);
  })();
  const hurt = uniform(0).onObjectUpdate(({ object }) => (object?.userData.hurt as number | undefined) ?? 0);
  m.colorNode = vertexColor().mul(detail.y);
  m.normalNode = critterBump(detail.x, 0.012);
  m.roughnessNode = look.x;
  const pulse = sin(time.mul(2.1).add(p.z.mul(9)).add(p.x.mul(5))).mul(0.25).add(0.75);
  const rim = float(1).sub(abs(dot(normalView, positionView.normalize().negate()))).pow(2);
  const outline = (o.outline ?? vec3(0.03, 0.03, 0.035)).mul(rim.mul(rim));
  m.emissiveNode = vertexColor().mul(look.z.mul(pulse).mul(2.2).add(look.w.mul(rim).mul(0.9))).add(outline).add(vec3(0.7, 0.04, 0.02).mul(hurt));
  return m;
}

/**
 * A procedural creature's eyes: wet balls, iris and pupil drawn from the ball's own shape (its +z looks
 * out), the iris colour per vertex; the pupil throws a little light back, so eyes shine in the dark.
 */
export function critterEye(): MeshStandardNodeMaterial {
  const m = new MeshStandardNodeMaterial({ vertexColors: true, roughness: 0.06, metalness: 0 });
  const e = positionGeometry.normalize();
  const ang = e.z.clamp(-1, 1).acos();
  const iris = smoothstep(1.05, 0.95, ang);
  const rings = mx_noise_float(vec3(e.y.atan(e.x).mul(6), ang.mul(30), 1));
  const pupil = smoothstep(0.38, 0.32, ang.div(0.6)).mul(smoothstep(-0.05, 0.05, e.z));
  const col = mix(vec3(0.42, 0.38, 0.34), vertexColor().mul(rings.mul(0.5).add(0.7)), iris);
  m.colorNode = mix(col, vec3(0.01, 0.01, 0.01), pupil);
  m.emissiveNode = vertexColor().mul(pupil.mul(0.35).add(iris.mul(0.06)));
  return m;
}

/**
 * Small birds, many in one draw (./three/birds.ts `BirdBatch`, the body from ./birds.ts): the wings
 * beat by the angle each bird is given (the outer part curls more) or fold along the back; the body is
 * banked, pitched, turned, sized and placed by its instance attributes. Flat shaded: at a bird's size
 * the facets read as feathers. The back's colour per bird, the belly paler, the beak dark.
 */
/**
 * The shader of every small fish (./fish.ts, ./three/batch.ts FishBatch): the body sweeps side to side, from
 * nothing at the snout to `sweep` body lengths at the tail's tip, a wave running back along it (`phase`, which the
 * game runs on); then it is rolled, pitched, turned, sized and placed. The back is the instance's colour, the flanks
 * and belly silvered, a little metallic so a turning shoal flashes.
 */
export function fishMaterial(): MeshStandardNodeMaterial {
  const m = new MeshStandardNodeMaterial({ roughness: 0.35, metalness: 0.35, flatShading: true, side: DoubleSide });
  const place = attribute<'vec4'>('fPlace', 'vec4'), turn = attribute<'vec4'>('fTurn', 'vec4'), look = attribute<'vec4'>('fLook', 'vec4');
  const back = attribute<'float'>('fBack', 'float'), p = positionGeometry;
  // The swimming wave: side to side, growing towards the tail, running back along the body.
  const q = vec3(p.x.add(look.w.mul(back.mul(back)).mul(sin(turn.w.sub(back.mul(3.4))))), p.y, p.z);
  // Roll (about z), pitch (about x, snout up), turn (about y), then size and place.
  const cr = turn.y.cos(), sr = turn.y.sin(), cp = turn.x.cos(), sp = turn.x.sin(), cy = place.w.cos(), sy = place.w.sin();
  const b1 = vec3(q.x.mul(cr).sub(q.y.mul(sr)), q.x.mul(sr).add(q.y.mul(cr)), q.z);
  const b2 = vec3(b1.x, b1.y.mul(cp).add(b1.z.mul(sp)), b1.z.mul(cp).sub(b1.y.mul(sp)));
  const b3 = vec3(b2.x.mul(cy).add(b2.z.mul(sy)), b2.y, b2.z.mul(cy).sub(b2.x.mul(sy)));
  m.positionNode = b3.mul(turn.z).add(place.xyz);
  // Dark back, silver flanks and a pale belly.
  const silver = mix(look.xyz, vec3(0.62, 0.66, 0.68), smoothstep(0.05, -0.04, p.y));
  m.colorNode = mix(silver, vec3(0.85, 0.86, 0.84), smoothstep(-0.04, -0.1, p.y));
  return m;
}

export function birdMaterial(): MeshStandardNodeMaterial {
  const m = new MeshStandardNodeMaterial({ roughness: 0.85, metalness: 0, flatShading: true, side: DoubleSide });
  const place = attribute<'vec4'>('bPlace', 'vec4'), turn = attribute<'vec4'>('bTurn', 'vec4'), look = attribute<'vec4'>('bLook', 'vec4');
  const part = attribute<'vec2'>('bPart', 'vec2');
  const p = positionGeometry, side = part.x, span = part.y, wingy = abs(side);
  // A wing turns about the body's long axis at its shoulder.
  const x0 = side.mul(BIRD_SHOULDER), d = abs(p.x.sub(x0));
  const th = turn.w.mul(span.mul(0.7).add(0.75));
  const spread = vec3(x0.add(side.mul(d).mul(th.cos())), p.y.add(d.mul(th.sin())), p.z);
  const folded = vec3(x0.add(side.mul(d).mul(0.1)), p.y.add(0.02).add(d.mul(0.04)), p.z.sub(d.mul(0.55)));
  const q = mix(p, mix(spread, folded, look.w), wingy);
  // Bank (about z), pitch (about x, nose up), turn (about y), then size and place.
  const cb = turn.y.cos(), sb = turn.y.sin(), cp = turn.x.cos(), sp = turn.x.sin(), cy = place.w.cos(), sy = place.w.sin();
  const b1 = vec3(q.x.mul(cb).sub(q.y.mul(sb)), q.x.mul(sb).add(q.y.mul(cb)), q.z);
  const b2 = vec3(b1.x, b1.y.mul(cp).add(b1.z.mul(sp)), b1.z.mul(cp).sub(b1.y.mul(sp)));
  const b3 = vec3(b2.x.mul(cy).add(b2.z.mul(sy)), b2.y, b2.z.mul(cy).sub(b2.x.mul(sy)));
  m.positionNode = b3.mul(turn.z).add(place.xyz);
  const back = look.xyz;
  const belly = mix(back, back.mul(1.8).add(vec3(0.12, 0.1, 0.07)), smoothstep(0.0, -0.06, p.y).mul(wingy.oneMinus()));
  const tips = mix(belly, back.mul(0.55), span.mul(span).mul(wingy));
  m.colorNode = mix(tips, vec3(0.05, 0.04, 0.02), smoothstep(0.44, 0.47, p.z));
  return m;
}
