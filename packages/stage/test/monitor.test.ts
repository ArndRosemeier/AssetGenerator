import { test } from 'node:test';
import assert from 'node:assert/strict';
import { ShaderMonitor } from '../src/monitor';

test('monitor: a blocking build over 100 ms is a violation, an async one is not', () => {
  const m = new ShaderMonitor(() => 0);
  m.record('node-sync', 120, 'rock', 0);
  m.record('gpu-pipeline-async', 300, 'rock', 0);
  const v = m.violations();
  assert.equal(v.length, 1);
  assert.match(v[0], /node-sync "rock" blocked 120 ms/);
});

test('monitor: after warm-up, a build sooner than twice the last one\'s time after it is a violation', () => {
  const m = new ShaderMonitor(() => 0);
  for (let i = 0; i < 10; i++) m.record('node-sync', 5, 'w', i); // warm-up: anything goes
  assert.deepEqual(m.violations(), []);
  m.phase = 'run';
  m.record('node-async', 2, 'quick', 1000);
  m.record('node-async', 30, 'slow', 1006); // 4 ms after a 2 ms build
  m.record('node-async', 2, 'after', 1096); // 60 ms after a 30 ms build
  assert.deepEqual(m.violations(), []);
  m.record('node-async', 2, 'too soon', 1100); // 2 ms after a 2 ms build
  assert.ok(m.violations().some((v) => v.includes('"too soon"')));
});
