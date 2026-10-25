import { test } from 'node:test';
import assert from 'node:assert/strict';
import { surfaceNets, PAD, SIDE, OVERLAP, type Grid } from '../src/index';

/** Sample an analytic field the way meshChunk does (padded by PAD cells on every side). */
function grid(f: (x: number, y: number, z: number) => number, ox: number, oy: number, oz: number, step: number, cells: number): Grid {
  const n = cells + 2 * PAD + 1;
  const d = new Float32Array(n * n * n);
  for (let k = 0; k < n; k++) for (let j = 0; j < n; j++) for (let i = 0; i < n; i++) d[i + n * (j + n * k)] = f(ox + (i - PAD) * step, oy + (j - PAD) * step, oz + (k - PAD) * step);
  return { n, d };
}

const ball = (x: number, y: number, z: number) => Math.hypot(x - 16, y - 16, z - 16) - 10; // air outside: rock ball

test('volume: a rock ball meshes closed, on its surface, with outward winding', () => {
  const m = surfaceNets(grid(ball, 0, 0, 0, 1, 32), 0, 0, 0, 1)!;
  assert.ok(m && m.indices.length > 0);
  for (let i = 0; i < m.positions.length; i += 3) {
    const r = Math.hypot(m.positions[i] - 16, m.positions[i + 1] - 16, m.positions[i + 2] - 16);
    assert.ok(Math.abs(r - 10) < 0.3, `vertex off the surface: r=${r}`);
  }
  // Closed: every edge is used by exactly two triangles, once in each direction.
  const edges = new Map<string, number>();
  const ix = m.indices;
  for (let t = 0; t < ix.length; t += 3) for (let e = 0; e < 3; e++) {
    const a = ix[t + e], b = ix[t + ((e + 1) % 3)];
    edges.set(`${a}>${b}`, (edges.get(`${a}>${b}`) ?? 0) + 1);
  }
  for (const [k, c] of edges) {
    assert.equal(c, 1, `edge ${k} used ${c}× in one direction`);
    const [a, b] = k.split('>');
    assert.ok(edges.has(`${b}>${a}`), `edge ${k} has no twin: hole`);
  }
  // Winding: triangle normals point out of the rock, like the vertex normals.
  let agree = 0;
  for (let t = 0; t < ix.length; t += 3) {
    const p = (v: number) => [m.positions[v * 3], m.positions[v * 3 + 1], m.positions[v * 3 + 2]];
    const [a, b, c] = [p(ix[t]), p(ix[t + 1]), p(ix[t + 2])];
    const u = [b[0] - a[0], b[1] - a[1], b[2] - a[2]], v = [c[0] - a[0], c[1] - a[1], c[2] - a[2]];
    const nx = u[1] * v[2] - u[2] * v[1], ny = u[2] * v[0] - u[0] * v[2], nz = u[0] * v[1] - u[1] * v[0];
    const out = [a[0] - 16, a[1] - 16, a[2] - 16];
    if (nx * out[0] + ny * out[1] + nz * out[2] > 0) agree++;
  }
  assert.equal(agree, ix.length / 3);
  for (let i = 0; i < m.normals.length; i += 3) {
    const out = [m.positions[i] - 16, m.positions[i + 1] - 16, m.positions[i + 2] - 16];
    assert.ok(m.normals[i] * out[0] + m.normals[i + 1] * out[1] + m.normals[i + 2] * out[2] > 0);
  }
});

test('volume: neighbouring chunks of a slanted floor join without doubles or gaps', () => {
  const floor = (x: number, y: number, z: number) => y - (6.3 + 0.2 * x + 0.1 * z);
  const parts = [0, 16].map((ox) => surfaceNets(grid(floor, ox, 0, 0, 1, 16), ox, 0, 0, 1)!);
  // Merge the two meshes by vertex position (shared seam vertices are computed identically).
  const key = (m: (typeof parts)[0], v: number) => `${m.positions[v * 3].toFixed(4)},${m.positions[v * 3 + 1].toFixed(4)},${m.positions[v * 3 + 2].toFixed(4)}`;
  const tris = new Set<string>();
  const edges = new Map<string, number>();
  const pos = new Map<string, number[]>();
  for (const m of parts) {
    for (let t = 0; t < m.indices.length; t += 3) {
      const ks = [0, 1, 2].map((e) => key(m, m.indices[t + e]));
      const id = [...ks].sort().join('|');
      assert.ok(!tris.has(id), 'a triangle is in both chunks');
      tris.add(id);
      for (let e = 0; e < 3; e++) {
        const ek = `${ks[e]}>${ks[(e + 1) % 3]}`;
        edges.set(ek, (edges.get(ek) ?? 0) + 1);
        pos.set(ks[e], ks[e].split(',').map(Number));
      }
    }
  }
  // Every edge away from the outer border of the 32 x 16 strip has its twin: no gap at x = 16.
  let inner = 0;
  for (const ek of edges.keys()) {
    const [a, b] = ek.split('>');
    const pa = pos.get(a)!, pb = pos.get(b)!;
    const interior = (p: number[]) => p[0] > 0.5 && p[0] < 30.5 && p[2] > 0.5 && p[2] < 14.5;
    if (!interior(pa) || !interior(pb)) continue;
    inner++;
    assert.ok(edges.has(`${b}>${a}`), `gap at edge ${ek}`);
  }
  assert.ok(inner > 500);
});

test('volume: nothing to mesh gives null', () => {
  assert.equal(surfaceNets(grid(() => 5, 0, 0, 0, 1, 8), 0, 0, 0, 1), null);
  assert.equal(surfaceNets(grid(() => -5, 0, 0, 0, 1, 8), 0, 0, 0, 1), null);
});

test('volume: overlap adds the faces OVERLAP cells past the chosen sides, and only those', () => {
  const floor = (_x: number, y: number) => y - 6.3;
  const plain = surfaceNets(grid(floor, 0, 0, 0, 1, 16), 0, 0, 0, 1)!;
  const high = surfaceNets(grid(floor, 0, 0, 0, 1, 16), 0, 0, 0, 1, SIDE.highX | SIDE.highZ)!;
  const lowX = surfaceNets(grid(floor, 0, 0, 0, 1, 16), 0, 0, 0, 1, SIDE.lowX)!;
  const yOnly = surfaceNets(grid(floor, 0, 0, 0, 1, 16), 0, 0, 0, 1, SIDE.lowY | SIDE.highY)!;
  assert.equal(plain.indices.length / 6, 16 * 16);
  assert.equal(high.indices.length / 6, (16 + OVERLAP) ** 2);
  assert.equal(lowX.indices.length / 6, (16 + OVERLAP) * 16);
  assert.equal(yOnly.indices.length / 6, 16 * 16);
});
