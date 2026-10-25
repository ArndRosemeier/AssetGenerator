/**
 * @deprecated Use Actors (github.com/ArndRosemeier/Actors, `@actors/*`) for every human, people and giant
 * (Arnd, 2026-10-25). This package gets no new features; games move their characters to Actors.
 *
 * @futuremagic/humanoid: Scale's humans. This entry is the pure body build (no three.js, no DOM):
 * appearance → morphed body, skeleton, sockets, hair and parts. It runs in workers and tests.
 * The renderer side lives in `three/` (import `@futuremagic/humanoid/three/...`).
 */
export * from './types';
export * from './assetFormat';
export * from './assets';
export * from './macro';
export * from './shape';
export * from './races';
export * from './appearance';
export * from './bodyBuild';
export * from './parts';
export * from './characterBuild';
export * from './wearable';
export * from './seating';
export * from './headwear';
export { BEARD_IDS, beardCoverage, scalpCoverage } from './faceRegions';
