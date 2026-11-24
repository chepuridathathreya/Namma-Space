(function () {
  var ASSETS = "assets/";
  var WALK_SPEED = 1.4;
  var RUN_SPEED = 2.8;
  var PITCH_LIMIT = 80 * Math.PI / 180;
  var MAX_STEP = 0.05;
  var JUMP_SPEED = 2.7;
  var GRAVITY = 6.5;
  var q = new URLSearchParams(location.search);
  var embedMode = q.has("embed");

  var canvas = document.getElementById("stage");
  var renderer = new THREE.WebGLRenderer({ canvas: canvas, antialias: false, powerPreference: "high-performance" });
  var perfOn = /[?&]debug/.test(location.search), perfEl = document.getElementById("dbg"), perf = { sorts: 0, sortMs: 0, sortSent: 0, jsMs: 0, lastNow: 0, worstGap: 0 }, perfGpu = "unknown";
  (function () { var g = renderer.getContext(), x = g.getExtension("WEBGL_debug_renderer_info"); if (x) perfGpu = g.getParameter(x.UNMASKED_RENDERER_WEBGL); })();
  if (perfOn) perfEl.hidden = false;
  if (!(renderer.getContext() instanceof WebGL2RenderingContext)) { fail("This viewer needs WebGL2."); return; }
  renderer.setClearColor(0x181A19, 1);
  var scene = new THREE.Scene();
  var spark = new Spark.SparkRenderer({ renderer: renderer, preBlurAmount: 0.3, blurAmount: 0 });
  scene.add(spark);
  var camera = new THREE.PerspectiveCamera(70, 1, 0.05, 200);
  camera.rotation.order = "YXZ";

  var grid = null;
  var yaw = 0, pitch = -0.08;
  var startState = null;
  var poiData = null, addon = { step: null, frame: null, minimap: null, keydown: null };

  function fail(msg) {
    var e = document.getElementById("err"); e.hidden = false;
    e.textContent = location.protocol === "file:" ? "This page cannot load its files when opened from disk. Run python -m http.server in this folder, then open http://localhost:8000." : msg;
    document.getElementById("loadmsg").textContent = "Could not start";
  }
  function progress(f, msg) {
    document.getElementById("barfill").style.width = Math.round(f * 100) + "%";
    document.getElementById("loadpct").textContent = Math.round(f * 100) + "%";
    if (msg) document.getElementById("loadmsg").textContent = msg;
  }


  var splatMesh = null, splatMeshes = [], total = 0, splatXYZ = null, splatRGBA = null, colourMode = "base";
  var surface = null, wire = null, gridFloor = null, gridOutline = null, gridOccupied = null;
  var mode = q.get("mode") === "mesh" ? "mesh" : "splat";
  var debugOn = q.get("debug") === "1";

  function fetchBuf(url, onProgress) {
    return new Promise(function (resolve, reject) {
      var x = new XMLHttpRequest(); x.open("GET", url); x.responseType = "arraybuffer";
      x.onprogress = function (e) { if (onProgress && e.lengthComputable) onProgress(e.loaded / e.total); };
      x.onload = function () {
        if (x.status < 200 || x.status >= 300) { reject(new Error(url + " returned " + x.status)); return; }
        resolve(x.response);
      };
      x.onerror = function () { reject(new Error("Could not load " + url)); };
      x.send();
    });
  }

  function expandQ(buf) {
    var dv = new DataView(buf), n = dv.getUint32(4, true);
    var lx = dv.getFloat32(8, true), ly = dv.getFloat32(12, true), lz = dv.getFloat32(16, true);
    var hx = dv.getFloat32(20, true), hy = dv.getFloat32(24, true), hz = dv.getFloat32(28, true);
    var sl = dv.getFloat32(32, true), sh = dv.getFloat32(36, true);
    var P = new Uint16Array(buf, 40, n * 3), S = new Uint8Array(buf, 40 + n * 6, n * 3), C = new Uint8Array(buf, 40 + n * 9, n * 4), R = new Uint8Array(buf, 40 + n * 13, n * 4);
    var out = new ArrayBuffer(n * 32), f = new Float32Array(out), u = new Uint8Array(out), sk = (sh - sl) / 255;
    for (var j = 0; j < n; j++) {
      var o = j * 8, i3 = j * 3, b = j * 32, i4 = j * 4;
      f[o] = lx + P[i3] / 65535 * (hx - lx); f[o + 1] = ly + P[i3 + 1] / 65535 * (hy - ly); f[o + 2] = lz + P[i3 + 2] / 65535 * (hz - lz);
      f[o + 3] = Math.exp(sl + S[i3] * sk); f[o + 4] = Math.exp(sl + S[i3 + 1] * sk); f[o + 5] = Math.exp(sl + S[i3 + 2] * sk);
      u[b + 24] = C[i4]; u[b + 25] = C[i4 + 1]; u[b + 26] = C[i4 + 2]; u[b + 27] = C[i4 + 3];
      u[b + 28] = R[i4]; u[b + 29] = R[i4 + 1]; u[b + 30] = R[i4 + 2]; u[b + 31] = R[i4 + 3];
    }
    return out;
  }

  function unpackSplat(buf, name) {
    if (!/\.qsplat$/.test(name)) return Promise.resolve(buf);
    return new Response(new Blob([buf]).stream().pipeThrough(new DecompressionStream("gzip"))).arrayBuffer().then(expandQ);
  }

  function poiArrays(n) { splatXYZ = new Float32Array(n * 4); splatRGBA = new Uint8Array(n * 4); }

  function buildSplats(buf) {
    var n = buf.byteLength / 32, f = new Float32Array(buf), u = new Uint8Array(buf);
    var c = new THREE.Vector3(), s = new THREE.Vector3(), r = new THREE.Quaternion(), col = new THREE.Color();
    var packed = new Spark.PackedSplats({ maxSplats: n });
    total = n; poiArrays(n);
    for (var j = 0; j < n; j++) {
      var o = j * 8, b = j * 32, t = j * 4;
      c.set(f[o], f[o + 1], f[o + 2]); s.set(f[o + 3], f[o + 4], f[o + 5]);
      r.set((u[b + 29] - 128) / 128, (u[b + 30] - 128) / 128, (u[b + 31] - 128) / 128, (u[b + 28] - 128) / 128).normalize();
      col.setRGB(u[b + 24] / 255, u[b + 25] / 255, u[b + 26] / 255);
      packed.pushSplat(c, s, r, u[b + 27] / 255, col);
      splatXYZ[t] = f[o]; splatXYZ[t + 1] = f[o + 1]; splatXYZ[t + 2] = f[o + 2];
      splatRGBA[t] = u[b + 24]; splatRGBA[t + 1] = u[b + 25]; splatRGBA[t + 2] = u[b + 26]; splatRGBA[t + 3] = u[b + 27];
    }
    splatMesh = new Spark.SplatMesh({ packedSplats: packed });
    splatMeshes = [splatMesh];
    scene.add(splatMesh);
    document.getElementById("count").textContent = n.toLocaleString();
  }

  function buildSparkFiles(spec) {
    var group = new THREE.Group(), m = new THREE.Matrix4().fromArray(spec.matrix);
    m.decompose(group.position, group.quaternion, group.scale);
    var loaded = spec.files.map(function () { return 0; });
    splatMeshes = spec.files.map(function (file, i) {
      var mesh = new Spark.SplatMesh({ url: ASSETS + file, onProgress: function (e) {
        if (!e.lengthComputable) return;
        loaded[i] = e.loaded / e.total;
        progress(0.85 * loaded.reduce(function (a, b) { return a + b; }, 0) / loaded.length, "Loading full-colour splats " + Math.round(100 * loaded.reduce(function (a, b) { return a + b; }, 0) / loaded.length) + "%");
      } });
      group.add(mesh);
      return mesh;
    });
    splatMesh = group;
    scene.add(group);
    colourMode = "full";
    return Promise.all(splatMeshes.map(function (mesh) { return mesh.initialized; })).then(function () {
      var n = 0;
      splatMeshes.forEach(function (mesh) { mesh.forEachSplat(function () { n++; }); });
      total = n; poiArrays(n);
      var k = 0, v = new THREE.Vector3();
      splatMeshes.forEach(function (mesh) {
        mesh.forEachSplat(function (i, center, scales, quaternion, opacity, color) {
          v.copy(center).applyMatrix4(m);
          var t = k * 4;
          splatXYZ[t] = v.x; splatXYZ[t + 1] = v.y; splatXYZ[t + 2] = v.z;
          splatRGBA[t] = Math.round(Math.min(1, Math.max(0, color.r)) * 255); splatRGBA[t + 1] = Math.round(Math.min(1, Math.max(0, color.g)) * 255);
          splatRGBA[t + 2] = Math.round(Math.min(1, Math.max(0, color.b)) * 255); splatRGBA[t + 3] = Math.round(Math.min(1, Math.max(0, opacity)) * 255);
          k++;
        });
      });
      document.getElementById("count").textContent = n.toLocaleString();
    });
  }

  function buildMesh(buf) {
    var h = new Uint32Array(buf, 0, 2), nv = h[0], nf = h[1], off = 8;
    var V = new Float32Array(buf.slice(off, off + nv * 12)); off += nv * 12;
    var Cc = new Uint8Array(buf.slice(off, off + nv * 3)); off += nv * 3;
    var F = new Uint32Array(buf.slice(off, off + nf * 12));
    var g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.BufferAttribute(V, 3));
    g.setAttribute("color", new THREE.BufferAttribute(Cc, 3, true));
    g.setIndex(new THREE.BufferAttribute(F, 1));
    surface = new THREE.Mesh(g, new THREE.MeshBasicMaterial({ vertexColors: true, side: THREE.DoubleSide }));
    wire = new THREE.Mesh(g, new THREE.MeshBasicMaterial({ color: 0x94A3B8, wireframe: true, transparent: true, opacity: 0.35, depthTest: true }));
    surface.frustumCulled = false; wire.frustumCulled = false; wire.renderOrder = 2; surface.renderOrder = 1;
    scene.add(surface); scene.add(wire);
  }

  function parseGrid(json) {
    var cols = json.cols, rows = json.rows, blocked = new Uint8Array(cols * rows), occupied = new Uint8Array(cols * rows);
    for (var r = 0; r < rows; r++) {
      for (var c = 0; c < cols; c++) {
        blocked[r * cols + c] = json.blocked[r].charCodeAt(c) === 49 ? 1 : 0;
        occupied[r * cols + c] = json.occupied[r].charCodeAt(c) === 49 ? 1 : 0;
      }
    }
    var heights = null;
    if (json.heights) {
      heights = new Float32Array(cols * rows);
      for (var hr = 0; hr < rows; hr++) for (var hc = 0; hc < cols; hc++) heights[hr * cols + hc] = (json.heights[hr][hc] || 0) / 100;
    }
    grid = { cell: json.cell, ox: json.originX, oz: json.originZ, cols: cols, rows: rows, blocked: blocked, occupied: occupied, heights: heights, floorY: json.floorY, eye: json.eyeHeight, start: json.start };
  }

  function isBlocked(x, z) {
    var c = Math.floor((x - grid.ox) / grid.cell), r = Math.floor((z - grid.oz) / grid.cell);
    if (c < 0 || r < 0 || c >= grid.cols || r >= grid.rows) return true;
    return grid.blocked[r * grid.cols + c] === 1;
  }

  var WALKMAP = { walkable: 0xE5E7EB, margin: 0xFBBF24, obstacle: 0xF87171, marginReach: 4, fenceHeight: 0.45 };

  function cellClasses() {
    var cols = grid.cols, rows = grid.rows, data = new Uint8Array(cols * rows * 4), reach = WALKMAP.marginReach;
    function nearWalkable(c, r) {
      for (var dr = -reach; dr <= reach; dr++) {
        for (var dc = -reach; dc <= reach; dc++) {
          var nc = c + dc, nr = r + dr;
          if (nc >= 0 && nr >= 0 && nc < cols && nr < rows && !grid.blocked[nr * cols + nc]) return true;
        }
      }
      return false;
    }
    for (var r = 0; r < rows; r++) {
      for (var c = 0; c < cols; c++) {
        var i = r * cols + c, kind = 0;
        if (!grid.blocked[i]) kind = 1;
        else if (grid.occupied[i]) kind = 3;
        else if (nearWalkable(c, r)) kind = 2;
        data[i * 4] = kind * 85; data[i * 4 + 3] = 255;
      }
    }
    var t = new THREE.DataTexture(data, cols, rows, THREE.RGBAFormat, THREE.UnsignedByteType);
    t.minFilter = THREE.NearestFilter; t.magFilter = THREE.NearestFilter; t.generateMipmaps = false; t.needsUpdate = true;
    return t;
  }

  function floorLayer() {
    var x0 = grid.ox, z0 = grid.oz, x1 = x0 + grid.cols * grid.cell, z1 = z0 + grid.rows * grid.cell, y = grid.floorY + 0.01;
    var g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.BufferAttribute(new Float32Array([x0, y, z0, x1, y, z0, x1, y, z1, x0, y, z0, x1, y, z1, x0, y, z1]), 3));
    g.setAttribute("cellPos", new THREE.BufferAttribute(new Float32Array([0, 0, grid.cols, 0, grid.cols, grid.rows, 0, 0, grid.cols, grid.rows, 0, grid.rows]), 2));
    var m = new THREE.Mesh(g, new THREE.ShaderMaterial({
      transparent: true, depthTest: false, depthWrite: false, side: THREE.DoubleSide,
      uniforms: {
        tCells: { value: cellClasses() }, uSize: { value: new THREE.Vector2(grid.cols, grid.rows) },
        uWalkable: { value: new THREE.Color(WALKMAP.walkable) }, uMargin: { value: new THREE.Color(WALKMAP.margin) }, uObstacle: { value: new THREE.Color(WALKMAP.obstacle) }
      },
      vertexShader: "attribute vec2 cellPos; varying vec2 vCell; void main() { vCell = cellPos; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }",
      fragmentShader: [
        "uniform sampler2D tCells; uniform vec2 uSize; uniform vec3 uWalkable; uniform vec3 uMargin; uniform vec3 uObstacle; varying vec2 vCell;",
        "void main() {",
        "  float kind = floor(texture2D(tCells, (floor(vCell) + 0.5) / uSize).r * 3.0 + 0.5);",
        "  if (kind < 0.5) discard;",
        "  vec2 edge = abs(fract(vCell - 0.5) - 0.5) / fwidth(vCell);",
        "  float line = 1.0 - clamp(min(edge.x, edge.y), 0.0, 1.0);",
        "  float fade = clamp(1.5 - 0.5 * max(fwidth(vCell.x), fwidth(vCell.y)) * 6.0, 0.0, 1.0);",
        "  vec3 color = uWalkable; float fill = 0.10; float rule = 0.22;",
        "  if (kind > 2.5) { color = uObstacle; fill = 0.24; rule = 0.24; }",
        "  else if (kind > 1.5) { color = uMargin; fill = 0.06 + 0.26 * step(0.5, fract((vCell.x + vCell.y) * 1.5)); rule = 0.0; }",
        "  gl_FragColor = vec4(color, fill + rule * line * fade);",
        "  #include <colorspace_fragment>",
        "}"
      ].join("\n")
    }));
    m.frustumCulled = false; m.renderOrder = 3;
    return m;
  }

  function boundaryEdges(cells, tagged) {
    var cell = grid.cell, edges = [];
    function filled(c, r) { return c >= 0 && r >= 0 && c < grid.cols && r < grid.rows && cells[r * grid.cols + c] === 1; }
    for (var r = 0; r < grid.rows; r++) {
      for (var c = 0; c < grid.cols; c++) {
        if (!filled(c, r)) continue;
        var x0 = grid.ox + c * cell, z0 = grid.oz + r * cell, x1 = x0 + cell, z1 = z0 + cell;
        var tag = tagged ? [r * grid.cols + c] : [];
        if (!filled(c, r - 1)) edges.push.apply(edges, [x0, z0, x1, z0].concat(tag));
        if (!filled(c, r + 1)) edges.push.apply(edges, [x0, z1, x1, z1].concat(tag));
        if (!filled(c - 1, r)) edges.push.apply(edges, [x0, z0, x0, z1].concat(tag));
        if (!filled(c + 1, r)) edges.push.apply(edges, [x1, z0, x1, z1].concat(tag));
      }
    }
    return edges;
  }

  function outlineLayer(cells, color, opacity, lift) {
    var edges = boundaryEdges(cells), y = grid.floorY + lift, lines = [];
    for (var i = 0; i < edges.length; i += 4) lines.push(edges[i], y, edges[i + 1], edges[i + 2], y, edges[i + 3]);
    var g = new THREE.BufferGeometry(); g.setAttribute("position", new THREE.BufferAttribute(new Float32Array(lines), 3));
    var m = new THREE.LineSegments(g, new THREE.LineBasicMaterial({ color: color, transparent: true, opacity: opacity, depthTest: false, depthWrite: false }));
    m.frustumCulled = false; m.renderOrder = 4;
    return m;
  }

  function fenceLayer(cells, color, height, heights) {
    var tagged = !!heights, stride = tagged ? 5 : 4, edges = boundaryEdges(cells, tagged), y0 = grid.floorY + 0.01, walls = [], rise = [];
    for (var i = 0; i < edges.length; i += stride) {
      var ax = edges[i], az = edges[i + 1], bx = edges[i + 2], bz = edges[i + 3];
      var y1 = y0 + (tagged && heights[edges[i + 4]] > 0 ? heights[edges[i + 4]] : height);
      walls.push(ax, y0, az, bx, y0, bz, bx, y1, bz, ax, y0, az, bx, y1, bz, ax, y1, az);
      rise.push(0, 0, 1, 0, 1, 1);
    }
    var g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.BufferAttribute(new Float32Array(walls), 3));
    g.setAttribute("rise", new THREE.BufferAttribute(new Float32Array(rise), 1));
    var m = new THREE.Mesh(g, new THREE.ShaderMaterial({
      transparent: true, depthTest: false, depthWrite: false, side: THREE.DoubleSide,
      uniforms: { uColor: { value: new THREE.Color(color) } },
      vertexShader: "attribute float rise; varying float vRise; void main() { vRise = rise; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }",
      fragmentShader: "uniform vec3 uColor; varying float vRise; void main() { float fade = 1.0 - vRise; gl_FragColor = vec4(uColor, 0.22 * fade * fade);\n#include <colorspace_fragment>\n}"
    }));
    m.frustumCulled = false; m.renderOrder = 4;
    return m;
  }

  function buildGridOverlay() {
    var walkable = new Uint8Array(grid.blocked.length);
    for (var i = 0; i < walkable.length; i++) walkable[i] = grid.blocked[i] ? 0 : 1;
    gridFloor = floorLayer();
    gridOutline = outlineLayer(walkable, 0xE5E7EB, 0.7, 0.012);
    gridOccupied = new THREE.Group();
    gridOccupied.add(fenceLayer(grid.occupied, WALKMAP.obstacle, WALKMAP.fenceHeight, grid.heights));
    gridOccupied.add(outlineLayer(grid.occupied, 0xFCA5A5, 0.8, 0.012));
    scene.add(gridFloor); scene.add(gridOutline); scene.add(gridOccupied);
  }

  var miniPanel = document.getElementById("minimap"), miniCanvas = document.getElementById("minimapCanvas"), miniCtx = miniCanvas.getContext("2d"), mini = null;
  var mapBtn = document.getElementById("mapBtn");
  function setMiniHidden(hidden) { miniPanel.hidden = hidden; mapBtn.setAttribute("aria-pressed", hidden ? "false" : "true"); }
  mapBtn.addEventListener("click", function () { if (mini) setMiniHidden(!miniPanel.hidden); canvas.focus(); });

  function buildMinimap() {
    var minC = grid.cols, maxC = -1, minR = grid.rows, maxR = -1, pad = 3;
    for (var r = 0; r < grid.rows; r++) {
      for (var c = 0; c < grid.cols; c++) {
        if (grid.blocked[r * grid.cols + c]) continue;
        if (c < minC) minC = c; if (c > maxC) maxC = c; if (r < minR) minR = r; if (r > maxR) maxR = r;
      }
    }
    minC = Math.max(0, minC - pad); minR = Math.max(0, minR - pad); maxC = Math.min(grid.cols - 1, maxC + pad); maxR = Math.min(grid.rows - 1, maxR + pad);
    var w = maxC - minC + 1, h = maxR - minR + 1, size = miniCanvas.width, scale = Math.min(size / w, size / h);
    var offX = (size - w * scale) / 2, offY = (size - h * scale) / 2;
    var base = document.createElement("canvas"); base.width = size; base.height = size;
    var b = base.getContext("2d");
    for (var rr = minR; rr <= maxR; rr++) {
      for (var cc = minC; cc <= maxC; cc++) {
        var i = rr * grid.cols + cc, x = offX + (cc - minC) * scale, y = offY + (rr - minR) * scale;
        if (!grid.blocked[i]) b.fillStyle = "rgba(229, 231, 235, 0.32)";
        else if (grid.occupied[i]) b.fillStyle = "rgba(248, 113, 113, 0.3)";
        else b.fillStyle = "rgba(148, 163, 184, 0.06)";
        b.fillRect(x, y, Math.ceil(scale), Math.ceil(scale));
      }
    }
    mini = { base: base, minC: minC, minR: minR, scale: scale, offX: offX, offY: offY, size: size };
    setMiniHidden(window.matchMedia("(pointer: coarse)").matches && !embedMode);
  }

  function miniPoint(x, z) {
    return { x: mini.offX + ((x - grid.ox) / grid.cell - mini.minC) * mini.scale, y: mini.offY + ((z - grid.oz) / grid.cell - mini.minR) * mini.scale };
  }

  function drawMinimap() {
    if (!mini || miniPanel.hidden) return;
    var here = miniPoint(camera.position.x, camera.position.z), px = here.x, py = here.y;
    var heading = Math.atan2(-Math.cos(yaw), -Math.sin(yaw));
    var half = Math.atan(Math.tan(camera.fov * Math.PI / 360) * camera.aspect), reach = mini.size * 0.24;
    miniCtx.clearRect(0, 0, mini.size, mini.size);
    miniCtx.drawImage(mini.base, 0, 0);
    if (addon.minimap) addon.minimap(miniCtx, miniPoint, mini.size);
    var cone = miniCtx.createRadialGradient(px, py, 0, px, py, reach);
    cone.addColorStop(0, "rgba(255, 255, 255, 0.7)"); cone.addColorStop(1, "rgba(255, 255, 255, 0)");
    miniCtx.fillStyle = cone;
    miniCtx.beginPath(); miniCtx.moveTo(px, py); miniCtx.arc(px, py, reach, heading - half, heading + half); miniCtx.closePath(); miniCtx.fill();
    miniCtx.beginPath(); miniCtx.arc(px, py, mini.size * 0.022, 0, Math.PI * 2);
    miniCtx.fillStyle = "#ffffff"; miniCtx.fill();
    miniCtx.lineWidth = mini.size * 0.012; miniCtx.strokeStyle = "#38BDF8"; miniCtx.stroke();
  }

  var guide = document.getElementById("guide");
  var guideKey = "namma_guide_seen_" + location.pathname;
  function guideSeen() {
    try { return localStorage.getItem(guideKey) === "1"; } catch (e) { return false; }
  }
  function openGuide() {
    guide.hidden = false;
    if (document.pointerLockElement) document.exitPointerLock();
    document.getElementById("guideGo").focus();
  }
  function closeGuide() {
    guide.hidden = true;
    try { localStorage.setItem(guideKey, "1"); } catch (e) { }
    canvas.focus();
  }
  document.getElementById("guideGo").addEventListener("click", closeGuide);
  var settings = document.getElementById("settings"), settingsBtn = document.getElementById("settingsBtn");
  function openSettings() {
    if (document.pointerLockElement) document.exitPointerLock();
    settings.hidden = false;
    document.getElementById("settingsClose").focus();
  }
  function closeSettings() {
    settings.hidden = true;
    settingsBtn.focus();
  }
  settingsBtn.addEventListener("click", openSettings);
  document.getElementById("settingsClose").addEventListener("click", closeSettings);
  settings.addEventListener("pointerdown", function (e) { if (e.target === settings) closeSettings(); });
  document.getElementById("guideBtn").addEventListener("click", function () { settings.hidden = true; openGuide(); });

  function applyMode() {
    if (mode === "mesh" && !surface) mode = "splat";
    if (splatMesh) splatMesh.visible = mode === "splat";
    if (surface) surface.visible = mode === "mesh";
    if (wire) wire.visible = debugOn;
    if (gridFloor) gridFloor.visible = debugOn;
    if (gridOutline) gridOutline.visible = debugOn;
    if (gridOccupied) gridOccupied.visible = debugOn;
    Array.prototype.forEach.call(document.querySelectorAll("[data-mode]"), function (b) { b.setAttribute("aria-pressed", b.dataset.mode === mode ? "true" : "false"); });
    document.getElementById("debugBtn").setAttribute("aria-pressed", debugOn ? "true" : "false");
    document.body.classList.toggle("walkmap", debugOn);
  }
  function setMode(m) { mode = m; applyMode(); }
  function toggleDebug() { debugOn = !debugOn; applyMode(); }
  Array.prototype.forEach.call(document.querySelectorAll("[data-mode]"), function (b) { b.addEventListener("click", function () { setMode(b.dataset.mode); canvas.focus(); }); });
  document.getElementById("debugBtn").addEventListener("click", function () { toggleDebug(); canvas.focus(); });

  function setScale(k) {
    renderScale = k; resize();
    Array.prototype.forEach.call(document.querySelectorAll("#detail button"), function (b) { b.setAttribute("aria-pressed", parseFloat(b.dataset.scale) === k ? "true" : "false"); });
  }
  Array.prototype.forEach.call(document.querySelectorAll("#detail button"), function (b) { b.addEventListener("click", function () { setScale(parseFloat(b.dataset.scale)); canvas.focus(); }); });

  function resetToDoor() {
    camera.position.set(startState.x, grid.floorY + grid.eye, startState.z); jumpHeight = 0; jumpSpeed = 0;
    yaw = startState.yaw; pitch = startState.pitch;
  }

  var keys = {};
  function held(a, b) { return keys[a] || (b && keys[b]); }
  window.addEventListener("keydown", function (e) {
    if (!guide.hidden) { if (e.code === "Enter" || e.code === "Escape") closeGuide(); return; }
    if (!settings.hidden) { if (e.code === "Escape") closeSettings(); return; }
    if (addon.keydown && addon.keydown(e)) return;
    keys[e.code] = true;
    if (e.code === "KeyN" && mini) setMiniHidden(!miniPanel.hidden);
    if (e.code === "Digit1") setMode("splat");
    if (e.code === "Digit2") setMode("mesh");
    if (e.code === "KeyM") toggleDebug();
    if (e.code === "KeyR" && grid) resetToDoor();
    if (e.code === "Space" || e.code.indexOf("Arrow") === 0) e.preventDefault();
  });
  window.addEventListener("keyup", function (e) { keys[e.code] = false; });
  window.addEventListener("blur", function () { keys = {}; });

  var dragging = false, moved = 0, locked = false;
  canvas.addEventListener("pointerdown", function (e) { dragging = true; moved = 0; try { canvas.setPointerCapture(e.pointerId); } catch (x) {} canvas.focus(); });
  canvas.addEventListener("pointerup", function (e) {
    dragging = false;
    if (moved < 4 && !locked && e.pointerType === "mouse") { try { var r = canvas.requestPointerLock(); if (r && r.catch) r.catch(function () {}); } catch (x) {} }
  });
  canvas.addEventListener("pointermove", function (e) {
    var dx = e.movementX || 0, dy = e.movementY || 0;
    if (!(dragging || locked)) return;
    moved += Math.abs(dx) + Math.abs(dy);
    yaw -= dx * 0.0032; pitch -= dy * 0.0032; pitch = Math.max(-PITCH_LIMIT, Math.min(PITCH_LIMIT, pitch));
  });
  document.addEventListener("pointerlockchange", function () {
    locked = document.pointerLockElement === canvas; canvas.classList.toggle("locked", locked); document.body.classList.toggle("mouse-locked", locked);
  });

  var renderScale = embedMode ? 0.85 : 1;
  function resize() {
    var dpr = Math.min(window.devicePixelRatio || 1, embedMode ? 1 : 2) * renderScale;
    renderer.setPixelRatio(dpr); renderer.setSize(window.innerWidth, window.innerHeight, false);
    camera.aspect = window.innerWidth / window.innerHeight; camera.updateProjectionMatrix();
  }
  window.addEventListener("resize", resize); resize();

  function tryMove(dx, dz) {
    var x = camera.position.x, z = camera.position.z, nx = x + dx, nz = z + dz;
    if (!isBlocked(nx, nz)) { camera.position.x = nx; camera.position.z = nz; return; }
    if (!isBlocked(nx, z)) { camera.position.x = nx; return; }
    if (!isBlocked(x, nz)) { camera.position.z = nz; }
  }

  var stick = { x: 0, y: 0 };
  (function () {
    var base = document.getElementById("stick"), knob = base.firstElementChild, active = null, RADIUS = 36, DEAD_ZONE = 0.12;
    function point(e) {
      var r = base.getBoundingClientRect(), dx = e.clientX - (r.left + r.width / 2), dy = e.clientY - (r.top + r.height / 2);
      var len = Math.hypot(dx, dy) || 1, k = Math.min(1, len / RADIUS);
      stick.x = k < DEAD_ZONE ? 0 : dx / len * k; stick.y = k < DEAD_ZONE ? 0 : -dy / len * k;
      knob.style.transform = "translate(" + (dx / len * k * RADIUS).toFixed(1) + "px," + (dy / len * k * RADIUS).toFixed(1) + "px)";
    }
    function release() { active = null; stick.x = 0; stick.y = 0; knob.style.transform = ""; }
    base.addEventListener("pointerdown", function (e) { active = e.pointerId; base.setPointerCapture(e.pointerId); point(e); });
    base.addEventListener("pointermove", function (e) { if (e.pointerId === active) point(e); });
    base.addEventListener("pointerup", release);
    base.addEventListener("pointercancel", release);
    base.addEventListener("lostpointercapture", release);
  })();

  var jumpHeight = 0, jumpSpeed = 0;
  function stepWalk(dt, input) {
    var analog = input.stickX || input.stickY;
    var ahead = analog ? input.stickY : (input.forward ? 1 : 0) - (input.back ? 1 : 0), side = analog ? input.stickX : (input.right ? 1 : 0) - (input.left ? 1 : 0);
    if (ahead || side) {
      var len = Math.sqrt(ahead * ahead + side * side), dist = (input.run ? RUN_SPEED : WALK_SPEED) * Math.min(1, len) * dt;
      var fx = -Math.sin(yaw), fz = -Math.cos(yaw), rx = Math.cos(yaw), rz = -Math.sin(yaw);
      var vx = (fx * ahead + rx * side) / len, vz = (fz * ahead + rz * side) / len;
      var steps = Math.max(1, Math.ceil(dist / MAX_STEP)), each = dist / steps;
      for (var i = 0; i < steps; i++) tryMove(vx * each, vz * each);
    }
    if (jumpHeight > 0 || jumpSpeed > 0 || input.jump) {
      if (input.jump && jumpHeight === 0) jumpSpeed = JUMP_SPEED;
      jumpSpeed -= GRAVITY * dt;
      jumpHeight = Math.max(0, jumpHeight + jumpSpeed * dt);
      if (jumpHeight === 0) jumpSpeed = 0;
    }
    camera.position.y = grid.floorY + grid.eye + jumpHeight;
  }

  var last = performance.now(), frames = 0, fpsT = last;
  function tick(now) {
    var jsStart = performance.now();
    var dt = Math.min((now - last) / 1000, 0.1); last = now;
    var input = {
      forward: held("KeyW", "ArrowUp") || stick.y > 0.2, back: held("KeyS", "ArrowDown") || stick.y < -0.2,
      left: held("KeyA", "ArrowLeft") || stick.x < -0.2, right: held("KeyD", "ArrowRight") || stick.x > 0.2,
      run: held("ShiftLeft", "ShiftRight"), jump: held("Space"), stickX: stick.x, stickY: stick.y
    };
    if (addon.step) input = addon.step(dt, input) || input;
    stepWalk(dt, input);
    camera.rotation.set(pitch, yaw, 0);
    camera.updateMatrixWorld(); camera.matrixWorldInverse.copy(camera.matrixWorld).invert();
    if (addon.frame) addon.frame(dt, now);
    renderer.render(scene, camera);
    drawMinimap();
    frames++;
    if (now - fpsT > 500) {
      var fpsNow = Math.round(frames * 1000 / (now - fpsT)); document.getElementById("fps").textContent = fpsNow; document.getElementById("fpsTopVal").textContent = fpsNow;
      document.getElementById("pos").textContent = "x " + camera.position.x.toFixed(2) + "  y " + camera.position.y.toFixed(2) + "  z " + camera.position.z.toFixed(2) + " m";
      if (perfOn) {
        var span = now - fpsT;
        perfEl.textContent = "GPU: " + perfGpu + "\n" + "canvas " + renderer.domElement.width + "x" + renderer.domElement.height + " px, devicePixelRatio " + window.devicePixelRatio + "\n" + "frame interval avg " + (span / Math.max(frames, 1)).toFixed(1) + " ms, worst " + perf.worstGap.toFixed(0) + " ms" + "\n" + "JS per frame " + (perf.jsMs / Math.max(frames, 1)).toFixed(1) + " ms" + "\n" + "sorts/s " + (perf.sorts * 1000 / span).toFixed(0) + ", sort delay avg " + (perf.sorts ? perf.sortMs / perf.sorts : 0).toFixed(0) + " ms" + "\n" + "splats " + total.toLocaleString() + " (" + colourMode + " colour), render scale " + renderScale;
        perf.sorts = 0; perf.sortMs = 0; perf.jsMs = 0; perf.worstGap = 0;
      }
      frames = 0; fpsT = now;
    }
    if (perf.lastNow && now - perf.lastNow > perf.worstGap) perf.worstGap = now - perf.lastNow;
    perf.lastNow = now; perf.jsMs += performance.now() - jsStart;
    requestAnimationFrame(tick);
  }

  window.__v = {
    camera: camera,
    stepWalk: stepWalk,
    isBlocked: isBlocked,
    setScale: setScale,
    colour: function () { return colourMode; },
    grid: function () { return grid; },
    pose: function () { return { x: camera.position.x, y: camera.position.y, z: camera.position.z, yaw: yaw, pitch: pitch }; },
    setPose: function (x, z, newYaw) { camera.position.x = x; camera.position.z = z; yaw = newYaw; },
    look: function (dx, dy) { yaw -= dx * 0.0032; pitch = Math.max(-PITCH_LIMIT, Math.min(PITCH_LIMIT, pitch - dy * 0.0032)); },
    reset: resetToDoor
  };

  function startPois() {
    var editing = q.get("edit") === "1";
    if (!window.NammaPoiUI || (!poiData && !editing)) {
      Array.prototype.forEach.call(document.querySelectorAll("[data-places]"), function (el) { el.hidden = true; });
      return;
    }
    window.NammaPoiUI.start({
      scene: scene, camera: camera, canvas: canvas, grid: grid, addon: addon, data: poiData, editing: editing,
      poiFile: manifest.pois || "pois.json", walkSpeed: WALK_SPEED, miniCanvas: miniCanvas,
      pose: window.__v.pose,
      splats: function () { return { xyz: splatXYZ, color: splatRGBA, count: total }; },
      isLocked: function () { return locked; },
      setView: function (x, z, newYaw, newPitch) {
        camera.position.x = x; camera.position.z = z; yaw = newYaw;
        pitch = Math.max(-PITCH_LIMIT, Math.min(PITCH_LIMIT, newPitch));
      }
    });
  }

  var tuneCancelled = false, tuneTimer = 0;
  function measureFps(ms, done) {
    var n = 0, t0 = 0;
    function step(t) {
      if (!t0) t0 = t;
      n++;
      if (t - t0 >= ms) done(n * 1000 / (t - t0)); else requestAnimationFrame(step);
    }
    requestAnimationFrame(step);
  }
  function showTune(message) {
    var el = document.createElement("div");
    el.className = "panel notice"; el.textContent = message;
    document.getElementById("dock").prepend(el);
    setTimeout(function () { el.remove(); }, 9000);
  }
  function scheduleAutoTune() {
    if (q.get("detail") || q.get("auto") === "0") return;
    var ladder = [0.85, 0.7, 0.55, 0.45, 0.375], rung = 0;
    Array.prototype.forEach.call(document.querySelectorAll("#detail button"), function (b) { b.addEventListener("click", function () { tuneCancelled = true; }); });
    function round() {
      if (tuneCancelled) return;
      if (document.hidden) { tuneTimer = setTimeout(round, 1500); return; }
      measureFps(1500, function (fps) {
        if (tuneCancelled || document.hidden || fps >= 35 || rung >= ladder.length) return;
        var step = ladder[rung++];
        if (step >= renderScale) { tuneTimer = setTimeout(round, 1500); return; }
        setScale(step);
        showTune("Slow graphics detected. Resolution was lowered to " + Math.round(step * 100) + "%. Change it in Settings under Detail.");
        tuneTimer = setTimeout(round, 1500);
      });
    }
    tuneTimer = setTimeout(round, 2500);
  }

  var manifest = null;
  fetchBuf(ASSETS + "manifest.json").then(function (mb) {
    manifest = JSON.parse(new TextDecoder().decode(mb));
    var full = manifest.spark && q.get("colour") !== "base";
    return Promise.all([fetchBuf(ASSETS + manifest.grid), full ? null : fetchBuf(ASSETS + manifest.splat, function (p) { progress(0.85 * p, "Loading splat " + Math.round(100 * p) + "%"); }), manifest.pois ? fetchBuf(ASSETS + manifest.pois) : null]);
  }).then(function (res) {
    parseGrid(JSON.parse(new TextDecoder().decode(res[0])));
    if (res[2]) poiData = JSON.parse(new TextDecoder().decode(res[2]));
    startState = { x: grid.start.x, z: grid.start.z, yaw: Math.atan2(-grid.start.forwardX, -grid.start.forwardZ), pitch: -0.08 };
    resetToDoor();
    if (!res[1]) return buildSparkFiles(manifest.spark);
    progress(0.9, "Preparing splats");
    return unpackSplat(res[1], manifest.splat).then(function (raw) {
      return new Promise(function (r) { setTimeout(function () { buildSplats(raw); r(); }, 30); });
    });
  }).then(function () {
    progress(0.95, "Loading mesh"); return manifest.mesh ? fetchBuf(ASSETS + manifest.mesh) : null;
  }).then(function (mb) {
    if (mb) buildMesh(mb); else { document.querySelector('[data-mode="mesh"]').hidden = true; document.getElementById("viewField").hidden = true; }
    buildGridOverlay();
    buildMinimap();
    var detail = parseFloat(q.get("detail") || "0");
    if (detail > 0 && detail <= 1) setScale(detail);
    startPois();
    applyMode(); progress(1, "Ready");
    document.getElementById("loading").hidden = true; window.__ready = true;
    if (!guideSeen() && q.get("guide") !== "0") openGuide();
    scheduleAutoTune();
    requestAnimationFrame(tick);
  }).catch(function (e) { fail(String(e && e.message || e)); });
})();

(function () {
  var fs = document.getElementById("fsBtn");
  if (!fs) return;
  fs.addEventListener("click", function () {
    var el = document.documentElement;
    if (document.fullscreenElement) { document.exitFullscreen(); return; }
    if (el.requestFullscreen) el.requestFullscreen();
  });
})();
