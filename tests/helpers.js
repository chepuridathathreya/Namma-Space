const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname, "..");
const VIEWER = path.join(ROOT, "namma_pipeline", "viewer_template");

const SCENES = {
  room: { grid: "01_room/site/assets/room_v1_collision.json" },
  hallway: { grid: "02_hallway_bedroom/site/assets/hallway_bedroom_v2_collision.json", pois: "02_hallway_bedroom/site/assets/pois.json" },
  hallway4k: { grid: "04_hallway_bedroom_4k/site/assets/vid_20261114_142211_collision.json", pois: "04_hallway_bedroom_4k/site/assets/pois.json" }
};

function loadGrid(relativePath) {
  const json = JSON.parse(fs.readFileSync(path.join(ROOT, relativePath), "utf8"));
  const layer = (rows) => {
    const cells = new Uint8Array(json.cols * json.rows);
    for (let r = 0; r < json.rows; r++) for (let c = 0; c < json.cols; c++) cells[r * json.cols + c] = rows[r].charCodeAt(c) === 49 ? 1 : 0;
    return cells;
  };
  return { cell: json.cell, ox: json.originX, oz: json.originZ, cols: json.cols, rows: json.rows, blocked: layer(json.blocked), occupied: layer(json.occupied), start: json.start };
}

function loadPois(relativePath) {
  return JSON.parse(fs.readFileSync(path.join(ROOT, relativePath), "utf8"));
}

function walkableCells(grid) {
  const cells = [];
  for (let r = 0; r < grid.rows; r++) for (let c = 0; c < grid.cols; c++) if (!grid.blocked[r * grid.cols + c]) cells.push({ c, r });
  return cells;
}

function seeded(seed) {
  let state = seed;
  return () => (state = (state * 1664525 + 1013904223) % 4294967296) / 4294967296;
}

function segmentStaysWalkable(nav, a, b) {
  const length = Math.hypot(b.x - a.x, b.z - a.z), steps = Math.max(1, Math.ceil(length / 0.001));
  for (let s = 0; s <= steps; s++) {
    const t = s / steps, cell = nav.toCell(a.x + (b.x - a.x) * t, a.z + (b.z - a.z) * t);
    if (!nav.walkable(cell.c, cell.r)) return false;
  }
  return true;
}

module.exports = { ROOT, VIEWER, SCENES, loadGrid, loadPois, walkableCells, seeded, segmentStaysWalkable };
