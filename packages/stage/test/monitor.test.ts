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

test('monitor: after warm-up, builds closer than 200 ms or more than 5 per second are violations', () => {
  const m = new ShaderMonitor(() => 0);
  for (let i = 0; i < 10; i++) m.record('node-sync', 5, 'w', i); // warm-up: anything goes
  assert.deepEqual(m.violations(), []);
  m.phase = 'run';
  for (let i = 0; i < 5; i++) m.record('node-async', 5, 'ok', 1000 + i * 200);
  assert.deepEqual(m.violations(), []);
  m.record('node-async', 5, 'too soon', 1000 + 4 * 200 + 50);
  assert.ok(m.violations().some((v) => v.includes('ms apart')));
  assert.ok(m.violations().some((v) => v.includes('within one second')));
});
