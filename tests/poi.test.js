const assert = require("assert");
const path = require("path");
const { test } = require("node:test");
const { VIEWER, SCENES, loadGrid, loadPois, segmentStaysWalkable } = require("./helpers.js");
const { createNavigator } = require(path.join(VIEWER, "nav.js"));
const poi = require(path.join(VIEWER, "poi.js"));

const SAMPLE = [
  { id: "wardrobe", name: "Wardrobe", aliases: ["almirah", "closet"], category: "furniture" },
  { id: "window", name: "Window", category: "opening" },
  { id: "bed", name: "Bed", aliases: ["cot"], category: "furniture", description: "single bed with a red cover" },
  { id: "fan", name: "Ceiling Fan", category: "appliance" }
];

test("search ranks name, prefix, other names, typos and category", () => {
  const first = (query) => poi.search(query, SAMPLE)[0].poi.id;
  assert.strictEqual(first("ward"), "wardrobe");
  assert.strictEqual(first("almirah"), "wardrobe");
  assert.strictEqual(first("wardrbe"), "wardrobe");
  assert.strictEqual(first("fan"), "fan");
  assert.strictEqual(first("cot"), "bed");
  assert.strictEqual(first("win"), "window");
  assert.strictEqual(first("WARDROBE "), "wardrobe");
  assert.strictEqual(poi.search("furn", SAMPLE).length, 2);
  assert.strictEqual(poi.search("zzz", SAMPLE).length, 0);
  assert.strictEqual(poi.search("", SAMPLE).length, 0);
});

test("equal scores are ordered by walking distance", () => {
  const twins = [{ id: "far", name: "Door" }, { id: "near", name: "Door" }];
  const metres = { far: 9, near: 2 };
  assert.deepStrictEqual(poi.search("door", twins, (p) => metres[p.id]).map((r) => r.poi.id), ["near", "far"]);
});

test("the bucket index returns exactly the places inside the radius", () => {
  const places = [{ x: 0.5, z: 0.5, id: "a" }, { x: 3, z: 3, id: "b" }, { x: 9, z: 9, id: "c" }, { x: -2.5, z: -0.5, id: "d" }];
  const index = poi.createIndex(places, 2);
  const ids = (x, z, radius) => index.within(x, z, radius).map((p) => p.id).sort();
  assert.deepStrictEqual(ids(0, 0, 1.5), ["a"]);
  assert.deepStrictEqual(ids(2, 2, 2.2), ["a", "b"]);
  assert.deepStrictEqual(ids(-2, 0, 1), ["d"]);
  assert.deepStrictEqual(ids(20, 20, 3), []);
  for (const [x, z, radius] of [[1, 1, 3], [5, 5, 6], [-1, 0, 2.5]]) {
    const expected = places.filter((p) => Math.hypot(p.x - x, p.z - z) <= radius).map((p) => p.id).sort();
    assert.deepStrictEqual(ids(x, z, radius), expected);
  }
});

test("validate reports broken files and accepts good ones", () => {
  assert.strictEqual(poi.validate({ pois: [{ id: "a", name: "A", x: 0, y: 1, z: 0 }] }).length, 0);
  assert.ok(poi.validate({}).length > 0);
  assert.ok(poi.validate({ pois: [{ id: "a", name: "A", x: 0, y: 1 }] }).some((line) => line.includes("z must be a number")));
  assert.ok(poi.validate({ pois: [{ id: "a", name: "A", x: 0, y: 1, z: 0 }, { id: "a", name: "B", x: 0, y: 1, z: 0 }] }).some((line) => line.includes("used twice")));
  assert.ok(poi.validate({ pois: [{ id: "a", name: " ", x: 0, y: 1, z: 0 }] }).some((line) => line.includes("name is missing")));
});

for (const [name, scene] of Object.entries(SCENES)) {
  if (!scene.pois) continue;
  const grid = loadGrid(scene.grid), data = loadPois(scene.pois);
  const nav = createNavigator(grid), startCell = nav.toCell(grid.start.x, grid.start.z);
  nav.setHome(startCell.c, startCell.r);
  const placed = poi.placeOnGrid(data.pois, nav);

  test(name + ": pois.json is valid", () => {
    assert.deepStrictEqual(poi.validate(data), []);
  });

  test(name + ": every place has a reachable stand point within 2.5 m", () => {
    for (const entry of placed) {
      assert.ok(entry.stand, entry.poi.id + " has no stand point");
      assert.ok(nav.reachable(entry.stand.c, entry.stand.r), entry.poi.id + " stand point is not reachable");
      const gap = Math.hypot(entry.stand.x - entry.poi.x, entry.stand.z - entry.poi.z);
      assert.ok(gap <= 2.5, entry.poi.id + " stand point is " + gap.toFixed(2) + " m away");
    }
  });

  test(name + ": a walkable route joins every pair of places", () => {
    for (const from of placed) {
      for (const to of placed) {
        const route = nav.route(from.stand, to.stand);
        assert.ok(route, "no route from " + from.poi.id + " to " + to.poi.id);
        for (let k = 1; k < route.points.length; k++) assert.ok(segmentStaysWalkable(nav, route.points[k - 1], route.points[k]), from.poi.id + " to " + to.poi.id + " crosses a blocked cell");
      }
    }
  });

  test(name + ": a hand-written stand point is used when it is walkable", () => {
    const stand = nav.toWorld(startCell.c, startCell.r);
    const entry = poi.placeOnGrid([{ id: "manual", name: "Manual", x: data.pois[0].x, y: 1, z: data.pois[0].z, stand: stand }], nav)[0];
    assert.deepStrictEqual({ c: entry.stand.c, r: entry.stand.r }, startCell);
  });

  test(name + ": every place is found by its own name", () => {
    for (const place of data.pois) assert.strictEqual(poi.search(place.name, data.pois)[0].poi.id, place.id);
  });
}
