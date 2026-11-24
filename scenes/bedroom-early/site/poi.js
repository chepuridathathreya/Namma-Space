(function (root) {
  function normalise(text) {
    return String(text).toLowerCase().normalize("NFD").replace(/\p{M}/gu, "").replace(/[^a-z0-9 ]+/g, " ").replace(/\s+/g, " ").trim();
  }

  function editDistance(a, b, limit) {
    if (Math.abs(a.length - b.length) > limit) return limit + 1;
    var previous = [], row;
    for (var j = 0; j <= b.length; j++) previous[j] = j;
    for (var i = 1; i <= a.length; i++) {
      row = [i];
      var smallest = i;
      for (var k = 1; k <= b.length; k++) {
        row[k] = Math.min(previous[k] + 1, row[k - 1] + 1, previous[k - 1] + (a[i - 1] === b[k - 1] ? 0 : 1));
        if (row[k] < smallest) smallest = row[k];
      }
      if (smallest > limit) return limit + 1;
      previous = row;
    }
    return previous[b.length];
  }

  function scoreWord(query, word) {
    if (word === query) return 100;
    if (word.indexOf(query) === 0) return 80;
    if (word.indexOf(query) > 0) return 40;
    var limit = query.length <= 4 ? 1 : 2;
    return editDistance(query, word.slice(0, query.length + limit), limit) <= limit ? 20 : 0;
  }

  function scorePoi(query, poi) {
    var q = normalise(query);
    if (!q) return 0;
    var names = [poi.name].concat(poi.aliases || []).map(normalise), best = 0;
    for (var i = 0; i < names.length; i++) {
      if (names[i] === q) best = Math.max(best, 100);
      else if (names[i].indexOf(q) === 0) best = Math.max(best, 85);
      var words = names[i].split(" ");
      for (var w = 0; w < words.length; w++) best = Math.max(best, scoreWord(q, words[w]) * 0.8);
    }
    if (normalise(poi.category || "").indexOf(q) === 0) best = Math.max(best, 50);
    if (normalise(poi.description || "").indexOf(q) >= 0) best = Math.max(best, 25);
    return best;
  }

  function search(query, pois, walkingMetres) {
    var results = [];
    for (var i = 0; i < pois.length; i++) {
      var score = scorePoi(query, pois[i]);
      if (score > 0) results.push({ poi: pois[i], score: score, metres: walkingMetres ? walkingMetres(pois[i]) : null });
    }
    results.sort(function (a, b) {
      if (b.score !== a.score) return b.score - a.score;
      return (a.metres === null ? 0 : a.metres) - (b.metres === null ? 0 : b.metres);
    });
    return results;
  }

  function createIndex(pois, bucketMetres) {
    var size = bucketMetres || 2, buckets = new Map();
    function key(x, z) { return Math.floor(x / size) + "," + Math.floor(z / size); }
    pois.forEach(function (poi) {
      var k = key(poi.x, poi.z);
      if (!buckets.has(k)) buckets.set(k, []);
      buckets.get(k).push(poi);
    });
    function within(x, z, radius) {
      var out = [], span = Math.ceil(radius / size), cx = Math.floor(x / size), cz = Math.floor(z / size);
      for (var i = -span; i <= span; i++) {
        for (var j = -span; j <= span; j++) {
          var bucket = buckets.get((cx + i) + "," + (cz + j));
          if (!bucket) continue;
          for (var n = 0; n < bucket.length; n++) {
            if (Math.hypot(bucket[n].x - x, bucket[n].z - z) <= radius) out.push(bucket[n]);
          }
        }
      }
      return out;
    }
    return { within: within };
  }

  function viewCell(poi, near, nav, distance, reach) {
    var nearPoint = nav.toWorld(near.c, near.r), dx = nearPoint.x - poi.x, dz = nearPoint.z - poi.z, gap = Math.hypot(dx, dz);
    if (gap < 1e-6 || gap >= distance) return near;
    var targetX = poi.x + dx / gap * distance, targetZ = poi.z + dz / gap * distance;
    var span = Math.ceil(reach / nav.cell), best = near, bestMiss = Math.hypot(nearPoint.x - targetX, nearPoint.z - targetZ);
    for (var dr = -span; dr <= span; dr++) {
      for (var dc = -span; dc <= span; dc++) {
        var c = near.c + dc, r = near.r + dr;
        if (!nav.reachable(c, r) || !nav.lineClear(near.c + 0.5, near.r + 0.5, c + 0.5, r + 0.5)) continue;
        var point = nav.toWorld(c, r), miss = Math.hypot(point.x - targetX, point.z - targetZ);
        if (miss < bestMiss) { bestMiss = miss; best = { c: c, r: r }; }
      }
    }
    return best;
  }

  function placeOnGrid(pois, nav, options) {
    var distance = (options && options.standDistance) || 1.2, reach = (options && options.reach) || 2;
    return pois.map(function (poi) {
      var wanted = poi.stand ? nav.toCell(poi.stand.x, poi.stand.z) : nav.toCell(poi.x, poi.z);
      var near = nav.nearestWalkable(wanted.c, wanted.r, 40);
      var cell = near && !poi.stand ? viewCell(poi, near, nav, distance, reach) : near;
      var point = cell ? nav.toWorld(cell.c, cell.r) : null;
      return { poi: poi, stand: cell ? { c: cell.c, r: cell.r, x: point.x, z: point.z } : null };
    });
  }

  function validate(data) {
    var problems = [], seen = {};
    if (!data || !Array.isArray(data.pois)) return ["the file needs a \"pois\" list"];
    data.pois.forEach(function (poi, i) {
      var label = "poi " + (i + 1) + (poi && poi.id ? " (" + poi.id + ")" : "");
      if (!poi || typeof poi.id !== "string" || !poi.id) { problems.push(label + ": id is missing"); return; }
      if (seen[poi.id]) problems.push(label + ": id is used twice");
      seen[poi.id] = true;
      if (typeof poi.name !== "string" || !poi.name.trim()) problems.push(label + ": name is missing");
      ["x", "y", "z"].forEach(function (axis) { if (!Number.isFinite(poi[axis])) problems.push(label + ": " + axis + " must be a number"); });
      if (poi.aliases && !Array.isArray(poi.aliases)) problems.push(label + ": aliases must be a list");
      if (poi.stand && !(Number.isFinite(poi.stand.x) && Number.isFinite(poi.stand.z))) problems.push(label + ": stand needs x and z numbers");
    });
    return problems;
  }

  var api = { placeOnGrid: placeOnGrid, validate: validate, normalise: normalise, editDistance: editDistance, scorePoi: scorePoi, search: search, createIndex: createIndex };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.NammaPOI = api;
})(typeof window !== "undefined" ? window : globalThis);
