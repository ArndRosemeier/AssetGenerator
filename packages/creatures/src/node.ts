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
import { MeshStandardNodeMaterial, type Node } from 'three/webgpu';
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
