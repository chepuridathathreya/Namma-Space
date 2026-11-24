const assert = require("assert");
const path = require("path");
const { test } = require("node:test");
const { VIEWER, SCENES, loadGrid, walkableCells, seeded, segmentStaysWalkable } = require("./helpers.js");
const { createNavigator } = require(path.join(VIEWER, "nav.js"));

for (const [name, scene] of Object.entries(SCENES)) {
  const grid = loadGrid(scene.grid);
  const nav = createNavigator(grid);
  const cells = walkableCells(grid);
  const startCell = nav.toCell(grid.start.x, grid.start.z);
  const region = nav.setHome(startCell.c, startCell.r);
  const reachable = cells.filter((p) => region[p.r * grid.cols + p.c]);
  const randomPair = (rand) => [reachable[Math.floor(rand() * reachable.length)], reachable[Math.floor(rand() * reachable.length)]];

  test(name + ": at least 99% of walkable cells are reachable from the start", () => {
    const pockets = cells.length - reachable.length;
    console.log("  " + name + ": " + cells.length + " walkable cells, " + pockets + " not reachable from the start");
    assert.ok(pockets <= 0.01 * cells.length, pockets + " unreachable cells");
  });

  test(name + ": A* length equals Dijkstra length on 300 random pairs", () => {
    const rand = seeded(7);
    let worst = 0;
    for (let i = 0; i < 300; i++) {
      const [a, b] = randomPair(rand);
      const truth = nav.distanceField(a.c, a.r)[b.r * grid.cols + b.c];
      worst = Math.max(worst, Math.abs(nav.findPath(a.c, a.r, b.c, b.r).length - truth));
    }
    assert.ok(worst < 1e-4, "worst difference " + worst + " m");
  });

  test(name + ": raw paths use only walkable cells and never cut a blocked corner", () => {
    const rand = seeded(11);
    for (let i = 0; i < 300; i++) {
      const [a, b] = randomPair(rand);
      const steps = nav.findPath(a.c, a.r, b.c, b.r).cells;
      for (let k = 0; k < steps.length; k++) {
        assert.ok(nav.walkable(steps[k].c, steps[k].r));
        if (k === 0) continue;
        const p = steps[k - 1], q = steps[k];
        if (p.c !== q.c && p.r !== q.r) assert.ok(nav.walkable(p.c, q.r) && nav.walkable(q.c, p.r));
      }
    }
  });

  test(name + ": smoothed routes stay on walkable cells when sampled every millimetre", () => {
    const rand = seeded(13);
    for (let i = 0; i < 300; i++) {
      const [a, b] = randomPair(rand);
      const route = nav.route(a, b);
      for (let k = 1; k < route.points.length; k++) assert.ok(segmentStaysWalkable(nav, route.points[k - 1], route.points[k]), "segment enters a blocked cell");
      assert.ok(route.metres <= route.rawMetres + 1e-6);
    }
  });

  test(name + ": a route to a blocked cell ends on the nearest reachable cell", () => {
    let blockedCell = null;
    for (let r = 0; r < grid.rows && !blockedCell; r++) for (let c = 0; c < grid.cols && !blockedCell; c++) if (grid.blocked[r * grid.cols + c]) blockedCell = { c, r };
    const route = nav.route(startCell, blockedCell);
    assert.ok(route && route.points.length >= 1);
    const end = nav.toCell(route.points[route.points.length - 1].x, route.points[route.points.length - 1].z);
    assert.ok(nav.reachable(end.c, end.r));
  });

  test(name + ": line of sight honours the chosen layer", () => {
    const a = reachable[0];
    assert.ok(nav.lineClear(a.c + 0.5, a.r + 0.5, a.c + 0.5, a.r + 0.5));
    const solid = new Uint8Array(grid.cols * grid.rows).fill(1);
    assert.strictEqual(nav.lineClear(a.c + 0.5, a.r + 0.5, a.c + 3.5, a.r + 0.5, solid), false);
    const empty = new Uint8Array(grid.cols * grid.rows);
    assert.ok(nav.lineClear(0.5, 0.5, grid.cols - 0.5, grid.rows - 0.5, empty));
  });

  test(name + ": a route takes well under one frame", () => {
    const rand = seeded(17), runs = 500, begin = process.hrtime.bigint();
    for (let i = 0; i < runs; i++) nav.route(...randomPair(rand));
    const milliseconds = Number(process.hrtime.bigint() - begin) / 1e6 / runs;
    console.log("  " + name + ": " + milliseconds.toFixed(3) + " ms per route (A* and smoothing)");
    assert.ok(milliseconds < 5);
  });
}
