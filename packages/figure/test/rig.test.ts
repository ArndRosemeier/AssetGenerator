import { test } from 'node:test';
import assert from 'node:assert/strict';
import { Bone, Group, Vector3 } from 'three/webgpu';
import { FigureRig } from '../src/index';

/** A stick figure with Actors' (game-engine) bone names, standing at the origin facing +Z, 1.8 m tall. */
function stickFigure(): { body: Group; bones: Bone[] } {
  const body = new Group(), bones: Bone[] = [];
  const bone = (name: string, parent: Bone | Group, x: number, y: number, z: number) => {
    const b = new Bone(); b.name = name; b.position.set(x, y, z); parent.add(b); bones.push(b); return b;
  };
  const pelvis = bone('pelvis', body, 0, 0.93, 0);
  const s1 = bone('spine_01', pelvis, 0, 0.1, 0), s2 = bone('spine_02', s1, 0, 0.15, 0), s3 = bone('spine_03', s2, 0, 0.15, 0);
  const neck = bone('neck_01', s3, 0, 0.15, 0);
  bone('head', neck, 0, 0.1, 0);
  for (const [s, x] of [['l', 1], ['r', -1]] as const) {
    const up = bone(`upperarm_${s}`, s3, 0.18 * x, 0.1, 0), lo = bone(`lowerarm_${s}`, up, 0, -0.3, 0), hand = bone(`hand_${s}`, lo, 0, -0.27, 0);
    for (const [f, fx] of [['index', 0.03], ['middle', 0.01], ['ring', -0.01], ['pinky', -0.03]] as const) {
      let p = hand;
      for (let j = 1; j <= 3; j++) p = bone(`${f}_0${j}_${s}`, p, j === 1 ? fx * x : 0, j === 1 ? -0.08 : -0.03, 0);
    }
    const th = bone(`thigh_${s}`, pelvis, 0.1 * x, -0.05, 0), calf = bone(`calf_${s}`, th, 0, -0.43, 0);
    bone(`foot_${s}`, calf, 0, -0.42, 0);
  }
  body.updateMatrixWorld(true);
  return { body, bones };
}

const at = (b: Bone) => b.getWorldPosition(new Vector3());

test('rig: measures the hips, and a hand reaches its goal with the elbow bent the asked way', () => {
  const { body, bones } = stickFigure();
  const rig = new FigureRig(body, bones);
  rig.fit(1.8);
  assert.ok(Math.abs(rig.hipHeight - 0.93) < 1e-6);
  const goal = new Vector3(0.35, 1.3, 0.35);
  rig.reachFor({ L: { p: goal, w: 1 } });
  assert.ok(at(rig.bone('hand_l')).distanceTo(goal) < 0.01, `hand at ${at(rig.bone('hand_l')).toArray()}`);
  // The other hand did not move.
  assert.ok(Math.abs(at(rig.bone('hand_r')).y - 0.86) < 1e-6);
  // Relaxed: back as bound.
  rig.relax();
  body.updateMatrixWorld(true);
  assert.ok(at(rig.bone('hand_l')).distanceTo(new Vector3(0.18, 0.86, 0)) < 1e-6);
});

test('rig: a goal out of reach stretches the limb towards it; half weight goes half way round', () => {
  const { body, bones } = stickFigure();
  const rig = new FigureRig(body, bones);
  rig.fit(1.8);
  const foot = rig.bone('foot_r'), rest = at(foot);
  const goal = new Vector3(-0.1, 0.5, 0.6);
  rig.reachFor({ footR: { p: goal, w: 0.5 } });
  const half = at(foot);
  assert.ok(half.distanceTo(rest) > 0.1 && half.distanceTo(goal) > 0.05, 'between');
  rig.relax();
  rig.reachFor({ footR: { p: new Vector3(-0.1, 0.2, 3), w: 1 } });
  const hip = at(rig.bone('thigh_r'));
  assert.ok(Math.abs(at(foot).distanceTo(hip) - 0.85) < 0.01, 'straight towards it');
});
