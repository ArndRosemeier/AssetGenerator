import { test } from 'node:test';
import assert from 'node:assert/strict';
import { ShaderMonitor, codeHash } from '../src/monitor';

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

test('monitor: the same shader code built again after warm-up is named, the costliest first; different code is not', () => {
  const m = new ShaderMonitor(() => 0);
  const body = codeHash('vs body', 'fs shadow'), tile = codeHash('vs tile', 'fs ground');
  m.record('node-async', 3, 'tile', 0, tile);
  m.record('node-async', 2, 'once', 1, codeHash('vs once', 'fs once'));
  m.phase = 'run';
  for (let i = 0; i < 3; i++) m.record('node-sync', 2, 'body shadow', 1000 + i * 100, body);
  m.record('node-async', 9, 'tile', 2000, tile);
  m.record('node-async', 4, 'new kind', 3000, codeHash('vs new', 'fs new'));
  assert.deepEqual(m.repeats(), [
    { what: 'tile', times: 2, after: 1, ms: 9 },
    { what: 'body shadow', times: 3, after: 3, ms: 6 },
  ]);
  assert.equal(m.summary().repeats, 2);
  assert.match(m.report(), /built 3× alike \(3 after warm-up, 6 ms\): body shadow/);
});

test('codeHash: equal code, equal hash; the parts count apart', () => {
  assert.equal(codeHash('a', 'b'), codeHash('a', 'b'));
  assert.notEqual(codeHash('a', 'b'), codeHash('b', 'a'));
  assert.notEqual(codeHash('ab', ''), codeHash('a', 'b'));
});
