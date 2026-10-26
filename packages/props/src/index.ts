/**
 * Props made in Blender (AssetGenerator specs, packed by `ag.py pack`): meshes with ambient occlusion
 * baked into their vertex colours. `decodePack` reads an FMPK pack (v1, or v2 with `--slots`: the
 * material slot of every vertex, so a game can give wood, iron and cloth their own surface). The format
 * is described in blender/entrypoints/pack.py. Pure: no DOM, no three.js.
 *
 * Frame: metres, y up, the origin on the ground under the model's footprint centre, its front +z.
 */

export type V3 = readonly [number, number, number];

export interface PropModel {
  readonly name: string;
  /** Metres, 3 per vertex. */
  readonly positions: Float32Array;
  /** Unit normals, 3 per vertex. */
  readonly normals: Float32Array;
  /** Linear RGB with the baked occlusion, 3 per vertex. */
  readonly colors: Float32Array;
  readonly indices: Uint32Array;
  /** The spec's material names (v2; empty in a v1 pack). */
  readonly slotNames: readonly string[];
  /** Index into slotNames per vertex (v2; all 0 in a v1 pack). */
  readonly slots: Uint8Array;
  readonly min: V3;
  readonly max: V3;
}

/** Read an FMPK v1 or v2 pack into its models, by name. */
export function decodePack(bytes: Uint8Array): Map<string, PropModel> {
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  if (String.fromCharCode(...bytes.subarray(0, 4)) !== 'FMPK') throw new Error('not an FMPK pack');
  const version = view.getUint32(4, true);
  if (version !== 1 && version !== 2) throw new Error(`FMPK version ${version} is not known`);
  const text = new TextDecoder();
  const out = new Map<string, PropModel>();
  let at = 12;
  const pad = () => { at = (at + 3) & ~3; };
  const str = () => { const len = view.getUint16(at, true); const s = text.decode(bytes.subarray(at + 2, at + 2 + len)); at += 2 + len; return s; };
  for (let m = view.getUint32(8, true); m > 0; m--) {
    const name = str();
    pad();
    const slotNames: string[] = [];
    if (version === 2) {
      const count = view.getUint16(at, true);
      at += 2;
      for (let k = 0; k < count; k++) slotNames.push(str());
      pad();
    }
    const float = (k: number) => view.getFloat32(at + 4 * k, true);
    const scale = float(0), min: V3 = [float(1), float(2), float(3)], max: V3 = [float(4), float(5), float(6)];
    const n = view.getUint32(at + 28, true), ni = view.getUint32(at + 32, true);
    at += 36;
    const positions = new Float32Array(3 * n), normals = new Float32Array(3 * n), colors = new Float32Array(3 * n);
    for (let i = 0; i < 3 * n; i++) positions[i] = view.getInt16(at + 2 * i, true) * scale;
    at += 6 * n; pad();
    for (let i = 0; i < 3 * n; i++) normals[i] = view.getInt8(at + i) / 127;
    at += 3 * n;
    for (let i = 0; i < 3 * n; i++) { const c = bytes[at + i] / 255; colors[i] = c * c; }
    at += 3 * n;
    const slots = version === 2 ? bytes.slice(at, at + n) : new Uint8Array(n);
    if (version === 2) at += n;
    pad();
    const wide = n > 65535, indices = new Uint32Array(ni);
    for (let i = 0; i < ni; i++) indices[i] = wide ? view.getUint32(at + 4 * i, true) : view.getUint16(at + 2 * i, true);
    at += ni * (wide ? 4 : 2); pad();
    out.set(name, { name, positions, normals, colors, indices, slotNames, slots, min, max });
  }
  return out;
}
