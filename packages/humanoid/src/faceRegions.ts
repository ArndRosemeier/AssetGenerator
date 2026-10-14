/**
 * Facial region functions in *face coordinates* (inter-pupil-distance
 * units, origin between the eyes of the neutral mesh: x lateral, y up,
 * z forward). The same definitions exist in TSL (three/nodes/peopleNoise.ts) for painted
 * features in the skin shader and in TS for placing hair/beard card roots,
 * so painted stubble and 3D beard hair always agree.
 */
import { smoothstep } from '@futuremagic/core';
export { smoothstep };

/** Beard style ids shared by shader and generator. */
export const BEARD_IDS: Record<string, number> = {
  none: -1, stubble: 0, short: 0, full: 0, long: 0, braided: 0, forked: 0, goatee: 1, mustache: 2, mutton: 3, chinstrap: 4,
};

/** Coverage (0..1) of facial hair for a style id at face coordinate (x,y,z). */
export function beardCoverage(style: number, x: number, y: number, z: number): number {
  if (style < 0) return 0;
  const ax = Math.abs(x);
  // Upper boundary: cheek line rising toward the sideburns; lower: under the jaw onto the neck.
  const cheek = -0.82 + 0.62 * smoothstep(0.35, 1.25, ax);
  const upper = 1 - smoothstep(cheek - 0.06, cheek + 0.06, y);
  const side = smoothstep(-1.45, -1.05, z); // not behind the ears
  const neck = smoothstep(-2.25, -1.95, y + 0.25 * ax) * (1 - smoothstep(1.3, 1.6, ax));
  const front = upper * side * neck;
  // The lips themselves stay bare.
  const lipZone = smoothstep(0.38, 0.5, Math.hypot(x / 1.1, (y + 1.18) / 0.36));
  const mustache = (1 - smoothstep(0.5, 0.62, ax)) * smoothstep(-1.12, -1.02, y) * (1 - smoothstep(-0.86, -0.78, y));
  const chin = (1 - smoothstep(0.42, 0.56, ax)) * (1 - smoothstep(-1.36, -1.28, y)) * smoothstep(-2.1, -1.95, y);
  switch (style) {
    case 0: return Math.max(front * lipZone, mustache);
    case 1: return Math.max(chin, mustache) * side;
    case 2: return mustache;
    case 3: return front * smoothstep(0.5, 0.75, ax) * lipZone;
    case 4: return front * smoothstep(-1.75, -1.6, -y - 0.18 * ax) * lipZone;
  }
  return 0;
}

/** Scalp hair coverage (1 = scalp). `recede` 0..1 pushes the hairline back (age). */
export function scalpCoverage(x: number, y: number, z: number, recede: number): number {
  const ax = Math.abs(x);
  const hairline = 1.05 + 0.18 * ax * ax + recede * (0.45 + 0.4 * smoothstep(0.2, 0.8, ax));
  const front = smoothstep(hairline - 0.08, hairline + 0.08, y);
  // Above/behind the ears and the nape at the back.
  const sides = smoothstep(-0.55, -0.85, z) * smoothstep(-0.05, 0.25, y + 0.35 * smoothstep(-1.2, -2.0, z));
  const nape = smoothstep(-1.05, -1.35, z) * smoothstep(-2.2, -1.8, y);
  return Math.min(1, Math.max(front, sides, nape)) * (y > -2.6 ? 1 : 0);
}

/** Hero masks: how far face coordinate (x,y,z) lies inside a head covering (negative: left
 *  open, in about eye-hole radii). The eyes are always open (a little more than the lids; the
 *  skin round them is painted by h_eyeMask); a cowl also leaves the mouth, chin and jaw bare
 *  between a line under the nose that drops along the cheeks and the jaw line, on the front of
 *  the face (it still wraps under the chin and round the neck). The shell takes a little more than
 *  the covered part and the shader cuts its edge clean (the garment material). */
export function maskDepth(cut: 'cowl' | 'full', x: number, y: number, z: number): number {
  const ax = Math.abs(x);
  let d = z > -0.6 ? Math.hypot((ax - 0.5) / 0.33, (y + 0.01) / 0.22) - 1 : 9;
  if (cut === 'cowl') d = Math.min(d, Math.max(y + 0.86 + 0.75 * smoothstep(0.5, 1.2, ax), -1.6 - 0.45 * (1 - smoothstep(0.3, 1.1, ax)) - y, -0.25 - z) / 0.25);
  return d;
}

