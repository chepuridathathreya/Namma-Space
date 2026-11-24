(function (root) {
  var SQRT2 = Math.SQRT2;
  var NEIGHBOURS = [[1, 0, 1], [-1, 0, 1], [0, 1, 1], [0, -1, 1], [1, 1, SQRT2], [1, -1, SQRT2], [-1, 1, SQRT2], [-1, -1, SQRT2]];

  function octile(dc, dr) {
    dc = Math.abs(dc);
    dr = Math.abs(dr);
    return dc + dr + (SQRT2 - 2) * Math.min(dc, dr);
  }

  function MinHeap() {
    this.keys = [];
    this.items = [];
  }
  MinHeap.prototype.push = function (item, key) {
    var keys = this.keys, items = this.items, i = keys.length;
    keys.push(key);
    items.push(item);
    while (i > 0) {
      var parent = (i - 1) >> 1;
      if (keys[parent] <= key) break;
      keys[i] = keys[parent];
      items[i] = items[parent];
      i = parent;
    }
    keys[i] = key;
    items[i] = item;
  };
  MinHeap.prototype.pop = function () {
    var keys = this.keys, items = this.items, top = items[0];
    var lastKey = keys.pop(), lastItem = items.pop(), n = keys.length;
    if (n > 0) {
      var i = 0;
      while (true) {
        var child = 2 * i + 1;
        if (child >= n) break;
        if (child + 1 < n && keys[child + 1] < keys[child]) child++;
        if (keys[child] >= lastKey) break;
        keys[i] = keys[child];
        items[i] = items[child];
        i = child;
      }
      keys[i] = lastKey;
      items[i] = lastItem;
    }
    return top;
  };
  Object.defineProperty(MinHeap.prototype, "size", { get: function () { return this.items.length; } });

  function createNavigator(grid) {
    var cols = grid.cols, rows = grid.rows, blocked = grid.blocked, count = cols * rows;
    var g = new Float32Array(count), parent = new Int32Array(count), closed = new Uint8Array(count);

    function toCell(x, z) {
      return { c: Math.floor((x - grid.ox) / grid.cell), r: Math.floor((z - grid.oz) / grid.cell) };
    }
    function toWorld(c, r) {
      return { x: grid.ox + (c + 0.5) * grid.cell, z: grid.oz + (r + 0.5) * grid.cell };
    }
    function walkable(c, r) {
      return c >= 0 && r >= 0 && c < cols && r < rows && blocked[r * cols + c] === 0;
    }

    var region = null;

    function usable(c, r) {
      return walkable(c, r) && (region === null || region[r * cols + c] === 1);
    }

    function nearestWalkable(c, r, maxRadius) {
      if (usable(c, r)) return { c: c, r: r };
      var best = null, bestDistance = Infinity;
      for (var ring = 1; ring <= maxRadius && ring <= bestDistance; ring++) {
        for (var dr = -ring; dr <= ring; dr++) {
          for (var dc = -ring; dc <= ring; dc++) {
            if (Math.max(Math.abs(dc), Math.abs(dr)) !== ring || !usable(c + dc, r + dr)) continue;
            var d = Math.hypot(dc, dr);
            if (d < bestDistance) { bestDistance = d; best = { c: c + dc, r: r + dr }; }
          }
        }
      }
      return best;
    }

    function findPath(sc, sr, gc, gr) {
      if (!walkable(sc, sr) || !walkable(gc, gr)) return null;
      g.fill(Infinity);
      closed.fill(0);
      parent.fill(-1);
      var start = sr * cols + sc, goal = gr * cols + gc, heap = new MinHeap(), examined = 0;
      g[start] = 0;
      heap.push(start, octile(sc - gc, sr - gr));
      while (heap.size) {
        var cur = heap.pop();
        if (closed[cur]) continue;
        closed[cur] = 1;
        examined++;
        if (cur === goal) {
          var cells = [];
          for (var at = cur; at !== -1; at = parent[at]) cells.push({ c: at % cols, r: (at / cols) | 0 });
          cells.reverse();
          return { cells: cells, length: g[cur] * grid.cell, examined: examined };
        }
        var c = cur % cols, r = (cur / cols) | 0;
        for (var k = 0; k < 8; k++) {
          var step = NEIGHBOURS[k], nc = c + step[0], nr = r + step[1];
          if (!walkable(nc, nr)) continue;
          if (step[0] !== 0 && step[1] !== 0 && (blocked[r * cols + nc] === 1 || blocked[nr * cols + c] === 1)) continue;
          var next = nr * cols + nc, cost = g[cur] + step[2];
          if (cost < g[next]) {
            g[next] = cost;
            parent[next] = cur;
            heap.push(next, cost + octile(nc - gc, nr - gr));
          }
        }
      }
      return null;
    }

    function distanceField(sc, sr) {
      var dist = new Float32Array(count).fill(Infinity), done = new Uint8Array(count), heap = new MinHeap();
      if (!walkable(sc, sr)) return dist;
      dist[sr * cols + sc] = 0;
      heap.push(sr * cols + sc, 0);
      while (heap.size) {
        var cur = heap.pop();
        if (done[cur]) continue;
        done[cur] = 1;
        var c = cur % cols, r = (cur / cols) | 0;
        for (var k = 0; k < 8; k++) {
          var step = NEIGHBOURS[k], nc = c + step[0], nr = r + step[1];
          if (!walkable(nc, nr)) continue;
          if (step[0] !== 0 && step[1] !== 0 && (blocked[r * cols + nc] === 1 || blocked[nr * cols + c] === 1)) continue;
          var next = nr * cols + nc, cost = dist[cur] + step[2];
          if (cost < dist[next]) { dist[next] = cost; heap.push(next, cost); }
        }
      }
      for (var i = 0; i < count; i++) dist[i] *= grid.cell;
      return dist;
    }

    function setHome(c, r) {
      var field = distanceField(c, r);
      region = new Uint8Array(count);
      for (var i = 0; i < count; i++) region[i] = Number.isFinite(field[i]) ? 1 : 0;
      return region;
    }

    function lineClear(ax, az, bx, bz, layer) {
      var cells = layer || blocked;
      function open(c, r) { return c >= 0 && r >= 0 && c < cols && r < rows && cells[r * cols + c] === 0; }
      var dx = bx - ax, dz = bz - az, c = Math.floor(ax), r = Math.floor(az), endC = Math.floor(bx), endR = Math.floor(bz);
      var stepC = dx > 0 ? 1 : -1, stepR = dz > 0 ? 1 : -1;
      var tMaxC = dx === 0 ? Infinity : ((dx > 0 ? c + 1 : c) - ax) / dx;
      var tMaxR = dz === 0 ? Infinity : ((dz > 0 ? r + 1 : r) - az) / dz;
      var tDeltaC = dx === 0 ? Infinity : stepC / dx, tDeltaR = dz === 0 ? Infinity : stepR / dz;
      if (!open(c, r)) return false;
      for (var guard = 0; (c !== endC || r !== endR) && guard < cols + rows + 4; guard++) {
        if (Math.abs(tMaxC - tMaxR) < 1e-9) {
          if (!open(c + stepC, r) || !open(c, r + stepR)) return false;
          c += stepC; r += stepR; tMaxC += tDeltaC; tMaxR += tDeltaR;
        } else if (tMaxC < tMaxR) {
          c += stepC; tMaxC += tDeltaC;
        } else {
          r += stepR; tMaxR += tDeltaR;
        }
        if (!open(c, r)) return false;
      }
      return true;
    }

    function smooth(cells) {
      var out = [cells[0]], i = 0;
      while (i < cells.length - 1) {
        var j = cells.length - 1;
        while (j > i + 1 && !lineClear(cells[i].c + 0.5, cells[i].r + 0.5, cells[j].c + 0.5, cells[j].r + 0.5)) j--;
        out.push(cells[j]);
        i = j;
      }
      return out;
    }

    function route(from, to) {
      var a = nearestWalkable(from.c, from.r, 40), b = nearestWalkable(to.c, to.r, 40);
      if (!a || !b) return null;
      var found = findPath(a.c, a.r, b.c, b.r);
      if (!found) return null;
      var corners = smooth(found.cells), metres = 0, points = corners.map(function (p) { return toWorld(p.c, p.r); });
      for (var i = 1; i < points.length; i++) metres += Math.hypot(points[i].x - points[i - 1].x, points[i].z - points[i - 1].z);
      return { points: points, metres: metres, rawMetres: found.length, examined: found.examined, cells: found.cells };
    }

    return { cell: grid.cell, cols: cols, rows: rows, setHome: setHome, toCell: toCell, toWorld: toWorld, walkable: walkable, reachable: usable, nearestWalkable: nearestWalkable, findPath: findPath, distanceField: distanceField, lineClear: lineClear, smooth: smooth, route: route };
  }

  var api = { createNavigator: createNavigator, octile: octile };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.NammaNav = api;
})(typeof window !== "undefined" ? window : globalThis);
