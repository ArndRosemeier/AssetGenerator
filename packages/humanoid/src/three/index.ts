/**
 * The renderer side of the humanoid: a skinned Character with its node materials, garments fitted
 * by the EquipmentRig (items come from the host's Wardrobe), and the Animator with its mocap clips.
 * Imports `three/webgpu` only (WebGPURenderer, WebGPU or its WebGL2 backend).
 */
export * from './Character';
export * from './Humanoid';
export * from './staticData';
export * from './equipment';
export * from './sky';
export * from './skinMaterial';
export * from './partMaterials';
export * from './hairShells';
export * from './garmentMaterial';
export * from './color';
export * from './skinIndex';
export * from './anim/types';
export * from './anim/pose';
export * from './anim/actions';
export * from './anim/clips';
export * from './anim/Animator';
