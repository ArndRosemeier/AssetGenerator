/**
 * A game's material registry (the shader policy, docs of each game: SHADERS.md): every material the game draws with
 * is a kind, defined once by name, with the vertex attributes its meshes carry and one shared material built on
 * first use. The Stage's warm-up compiles the kinds behind the loading screen (`StageOptions.kinds`), so the set of
 * shaders is known up front. From MasterWorld's and Nauta's `materials.ts`.
 */
import type { Material } from 'three/webgpu';
import type { StageKind } from './stage';

/** A kind with its game's attribute names, and whether the warm-up leaves it out. */
export interface Kind<A extends string = string> extends StageKind {
  readonly attributes: readonly A[];
  /**
   * Not needed in the first seconds of play: left out of the warm-up behind the loading screen, so it does not
   * lengthen the load; built under the shader cap when first added (Stage.add).
   */
  readonly late: boolean;
}

/** Casts and receives the sun's shadow: the default for a lit kind. */
export const LIT_SHADOW: StageKind['shadow'] = { cast: true, receive: true };

export class Kinds<A extends string = string> {
  private readonly map = new Map<string, Kind<A>>();

  /** Defines a kind: its name (once), the attributes its meshes carry, and its one material (built on first use). */
  define(name: string, attributes: readonly A[], build: () => Material, shadow: StageKind['shadow'] = LIT_SHADOW, late = false): Kind<A> {
    if (this.map.has(name)) throw new Error(`material kind "${name}" defined twice`);
    let made: Material | null = null;
    const kind: Kind<A> = { name, attributes, shadow, late, make: () => (made ??= Object.assign(build(), { name })) };
    this.map.set(name, kind);
    return kind;
  }

  /** Every kind defined. */
  all(): readonly Kind<A>[] {
    return [...this.map.values()];
  }

  /** The kinds the warm-up builds behind the loading screen: all but the late ones. */
  warm(): readonly Kind<A>[] {
    return this.all().filter((k) => !k.late);
  }
}
