(function () {
  var ASSETS = "assets/";
  var WALK_SPEED = 1.4;
  var RUN_SPEED = 2.8;
  var PITCH_LIMIT = 80 * Math.PI / 180;
  var MAX_STEP = 0.05;
  var TEX_W = 1024;
  var q = new URLSearchParams(location.search);

  var canvas = document.getElementById("stage");
  var renderer = new THREE.WebGLRenderer({ canvas: canvas, antialias: false, powerPreference: "high-performance" });
  if (!renderer.capabilities.isWebGL2) { fail("This viewer needs WebGL2."); return; }
  renderer.setClearColor(0x0b0f0e, 1);
  var scene = new THREE.Scene();
  var camera = new THREE.PerspectiveCamera(70, 1, 0.05, 200);
  camera.rotation.order = "YXZ";

  var grid = null;
  var yaw = 0, pitch = -0.08;
  var startState = null;

  function fail(msg) {
    var e = document.getElementById("err"); e.hidden = false; e.textContent = msg;
    document.getElementById("loadmsg").textContent = "Could not start";
  }
  function progress(f, msg) {
    document.getElementById("barfill").style.width = Math.round(f * 100) + "%";
    if (msg) document.getElementById("loadmsg").textContent = msg;
  }

  var VERT = [
    "precision highp float; precision highp int; precision highp sampler2D;",
    "uniform sampler2D tA; uniform sampler2D tB; uniform sampler2D tC; uniform sampler2D tD;",
    "uniform mat4 uView; uniform mat4 uProj; uniform vec2 uViewport;",
    "in vec2 position; in float idx;",
    "out vec4 vColor; out vec2 vPos;",
    "void main() {",
    "  int i = int(idx + 0.5);",
    "  ivec2 tc = ivec2(i & " + (TEX_W - 1) + ", i >> 10);",
    "  vec4 A = texelFetch(tA, tc, 0); vec4 B = texelFetch(tB, tc, 0); vec4 C = texelFetch(tC, tc, 0); vec4 D = texelFetch(tD, tc, 0);",
    "  vec4 vc = uView * vec4(A.xyz, 1.0);",
    "  vec4 clip = uProj * vc;",
    "  float zc = -vc.z;",
    "  if (zc < 0.05 || abs(clip.x) > 1.3 * clip.w || abs(clip.y) > 1.3 * clip.w) { gl_Position = vec4(0.0, 0.0, 2.0, 1.0); return; }",
    "  float fx = uProj[0][0] * uViewport.x * 0.5; float fy = uProj[1][1] * uViewport.y * 0.5;",
    "  float vx = clamp(vc.x / zc, -1.3 / uProj[0][0], 1.3 / uProj[0][0]) * zc;",
    "  float vy = clamp(vc.y / zc, -1.3 / uProj[1][1], 1.3 / uProj[1][1]) * zc;",
    "  mat3 J = mat3(vec3(fx / zc, 0.0, 0.0), vec3(0.0, fy / zc, 0.0), vec3(fx * vx / (zc * zc), fy * vy / (zc * zc), 0.0));",
    "  mat3 Vrk = mat3(B.x, B.y, B.z, B.y, B.w, C.x, B.z, C.x, C.y);",
    "  mat3 T = J * mat3(uView);",
    "  mat3 cov = T * Vrk * transpose(T);",
    "  float c00 = cov[0][0] + 0.3; float c11 = cov[1][1] + 0.3; float c01 = cov[1][0];",
    "  float mid = 0.5 * (c00 + c11); float rad = length(vec2(0.5 * (c00 - c11), c01));",
    "  float l1 = mid + rad; float l2 = max(mid - rad, 0.05);",
    "  vec2 ev = vec2(c01, l1 - c00); float evl = length(ev);",
    "  vec2 e1 = vec2(1.0, 0.0);",
    "  if (evl > 1e-6) { e1 = ev / evl; } else if (c11 > c00) { e1 = vec2(0.0, 1.0); }",
    "  vec2 e2 = vec2(-e1.y, e1.x);",
    "  float s1 = min(sqrt(l1), 300.0); float s2 = min(sqrt(l2), 300.0);",
    "  vec2 pix = position.x * 3.0 * s1 * e1 + position.y * 3.0 * s2 * e2;",
    "  vColor = D; vPos = position * 3.0;",
    "  gl_Position = vec4(clip.xy / clip.w + pix * 2.0 / uViewport, 0.0, 1.0);",
    "}"
  ].join("\n");
  var FRAG = [
    "precision highp float;",
    "in vec4 vColor; in vec2 vPos; out vec4 outColor;",
    "void main() {",
    "  float r2 = dot(vPos, vPos);",
    "  if (r2 > 9.0) discard;",
    "  float a = vColor.a * exp(-0.5 * r2);",
    "  if (a < 0.004) discard;",
    "  outColor = vec4(vColor.rgb, a);",
    "}"
  ].join("\n");

  var splatMesh = null, worker = null, sortPending = false, lastSortKey = "", total = 0, limit = 0;
  var surface = null, wire = null, gridBlocked = null, gridOccupied = null;
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

  function buildSplats(buf) {
    var n = buf.byteLength / 32, g = 0;
    total = n;
    var rows = Math.ceil(n / TEX_W), size = TEX_W * rows;
    var A = new Float32Array(size * 4), B = new Float32Array(size * 4), C = new Float32Array(size * 4), D = new Uint8Array(size * 4);
    var pos = new Float32Array(n * 3), k = 0;
    var f = new Float32Array(buf), u = new Uint8Array(buf);
    for (var j = 0; j < n; j++, g++) {
      var o = j * 8, x = f[o], y = f[o + 1], z = f[o + 2], sx = f[o + 3], sy = f[o + 4], sz = f[o + 5], b = j * 32;
      var w = (u[b + 28] - 128) / 128, qx = (u[b + 29] - 128) / 128, qy = (u[b + 30] - 128) / 128, qz = (u[b + 31] - 128) / 128;
      var nn = Math.sqrt(w * w + qx * qx + qy * qy + qz * qz) || 1; w /= nn; qx /= nn; qy /= nn; qz /= nn;
      var r00 = 1 - 2 * (qy * qy + qz * qz), r01 = 2 * (qx * qy - w * qz), r02 = 2 * (qx * qz + w * qy);
      var r10 = 2 * (qx * qy + w * qz), r11 = 1 - 2 * (qx * qx + qz * qz), r12 = 2 * (qy * qz - w * qx);
      var r20 = 2 * (qx * qz - w * qy), r21 = 2 * (qy * qz + w * qx), r22 = 1 - 2 * (qx * qx + qy * qy);
      var a2 = sx * sx, b2 = sy * sy, c2 = sz * sz, t = k * 4;
      A[t] = x; A[t + 1] = y; A[t + 2] = z;
      B[t] = r00 * r00 * a2 + r01 * r01 * b2 + r02 * r02 * c2;
      B[t + 1] = r00 * r10 * a2 + r01 * r11 * b2 + r02 * r12 * c2;
      B[t + 2] = r00 * r20 * a2 + r01 * r21 * b2 + r02 * r22 * c2;
      B[t + 3] = r10 * r10 * a2 + r11 * r11 * b2 + r12 * r12 * c2;
      C[t] = r10 * r20 * a2 + r11 * r21 * b2 + r12 * r22 * c2;
      C[t + 1] = r20 * r20 * a2 + r21 * r21 * b2 + r22 * r22 * c2;
      D[t] = u[b + 24]; D[t + 1] = u[b + 25]; D[t + 2] = u[b + 26]; D[t + 3] = u[b + 27];
      pos[k * 3] = x; pos[k * 3 + 1] = y; pos[k * 3 + 2] = z; k++;
    }
    function tex(data, type) {
      var t = new THREE.DataTexture(data, TEX_W, rows, THREE.RGBAFormat, type);
      t.minFilter = THREE.NearestFilter; t.magFilter = THREE.NearestFilter; t.generateMipmaps = false; t.needsUpdate = true; return t;
    }
    var geo = new THREE.InstancedBufferGeometry();
    geo.setAttribute("position", new THREE.BufferAttribute(new Float32Array([-1, -1, 1, -1, 1, 1, -1, 1]), 2));
    geo.setIndex([0, 1, 2, 0, 2, 3]);
    var idx = new THREE.InstancedBufferAttribute(new Float32Array(n), 1); idx.setUsage(THREE.DynamicDrawUsage);
    for (var i = 0; i < n; i++) idx.array[i] = i;
    geo.setAttribute("idx", idx); geo.instanceCount = n;
    var mat = new THREE.RawShaderMaterial({
      glslVersion: THREE.GLSL3, vertexShader: VERT, fragmentShader: FRAG, transparent: true, depthTest: false, depthWrite: false, side: THREE.DoubleSide,
      uniforms: {
        tA: { value: tex(A, THREE.FloatType) }, tB: { value: tex(B, THREE.FloatType) }, tC: { value: tex(C, THREE.FloatType) }, tD: { value: tex(D, THREE.UnsignedByteType) },
        uView: { value: new THREE.Matrix4() }, uProj: { value: new THREE.Matrix4() }, uViewport: { value: new THREE.Vector2(1, 1) }
      }
    });
    splatMesh = new THREE.Mesh(geo, mat); splatMesh.frustumCulled = false; splatMesh.renderOrder = 0;
    scene.add(splatMesh);
    var src = "var pos,n,out,keys;onmessage=function(e){var d=e.data;if(d.pos){pos=new Float32Array(d.pos);n=pos.length/3;keys=new Uint16Array(n);return;}" +
      "var m=d.row,a=m[0],b=m[1],c=m[2],dd=m[3],mn=1e30,mx=-1e30,i,z,n=Math.min(d.lim||pos.length/3,pos.length/3);var zs=new Float32Array(n);" +
      "for(i=0;i<n;i++){z=a*pos[3*i]+b*pos[3*i+1]+c*pos[3*i+2]+dd;zs[i]=z;if(z<mn)mn=z;if(z>mx)mx=z;}" +
      "var sc=65535/(mx-mn||1),cnt=new Uint32Array(65537);for(i=0;i<n;i++){var k=((zs[i]-mn)*sc)|0;keys[i]=k;cnt[k+1]++;}" +
      "for(i=1;i<65537;i++)cnt[i]+=cnt[i-1];var res=new Float32Array(n);for(i=0;i<n;i++){res[cnt[keys[i]]++]=i;}" +
      "postMessage({order:res},[res.buffer]);};";
    worker = new Worker(URL.createObjectURL(new Blob([src], { type: "application/javascript" })));
    worker.onmessage = function (e) {
      idx.array.set(e.data.order); idx.needsUpdate = true; sortPending = false;
    };
    worker.postMessage({ pos: pos.buffer }, [pos.buffer]);
    limit = n; document.getElementById("count").textContent = n.toLocaleString();
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
    wire = new THREE.Mesh(g, new THREE.MeshBasicMaterial({ color: 0x5fd0b8, wireframe: true, transparent: true, opacity: 0.35, depthTest: true }));
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
    grid = { cell: json.cell, ox: json.originX, oz: json.originZ, cols: cols, rows: rows, blocked: blocked, occupied: occupied, floorY: json.floorY, eye: json.eyeHeight, start: json.start };
  }

  function isBlocked(x, z) {
    var c = Math.floor((x - grid.ox) / grid.cell), r = Math.floor((z - grid.oz) / grid.cell);
    if (c < 0 || r < 0 || c >= grid.cols || r >= grid.rows) return true;
    return grid.blocked[r * grid.cols + c] === 1;
  }

  function cellMesh(cells, color, opacity, lift) {
    var pos = [], cell = grid.cell, y = grid.floorY + lift;
    for (var r = 0; r < grid.rows; r++) {
      for (var c = 0; c < grid.cols; c++) {
        if (!cells[r * grid.cols + c]) continue;
        var x0 = grid.ox + c * cell, z0 = grid.oz + r * cell, x1 = x0 + cell, z1 = z0 + cell;
        pos.push(x0, y, z0, x1, y, z0, x1, y, z1, x0, y, z0, x1, y, z1, x0, y, z1);
      }
    }
    var g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.BufferAttribute(new Float32Array(pos), 3));
    var m = new THREE.Mesh(g, new THREE.MeshBasicMaterial({ color: color, transparent: true, opacity: opacity, side: THREE.DoubleSide, depthTest: false, depthWrite: false }));
    m.frustumCulled = false; m.renderOrder = 3;
    scene.add(m);
    return m;
  }

  function buildGridOverlay() {
    var inflatedOnly = new Uint8Array(grid.blocked.length);
    for (var i = 0; i < inflatedOnly.length; i++) inflatedOnly[i] = grid.blocked[i] && !grid.occupied[i] ? 1 : 0;
    gridBlocked = cellMesh(inflatedOnly, 0xe04848, 0.35, 0.02);
    gridOccupied = cellMesh(grid.occupied, 0xf09a2a, 0.6, 0.03);
  }

  function applyMode() {
    if (splatMesh) splatMesh.visible = mode === "splat";
    if (surface) surface.visible = mode === "mesh";
    if (wire) wire.visible = debugOn;
    if (gridBlocked) gridBlocked.visible = debugOn;
    if (gridOccupied) gridOccupied.visible = debugOn;
    Array.prototype.forEach.call(document.querySelectorAll("[data-mode]"), function (b) { b.setAttribute("aria-pressed", b.dataset.mode === mode ? "true" : "false"); });
    document.getElementById("debugBtn").setAttribute("aria-pressed", debugOn ? "true" : "false");
  }
  function setMode(m) { mode = m; applyMode(); }
  function toggleDebug() { debugOn = !debugOn; applyMode(); }
  Array.prototype.forEach.call(document.querySelectorAll("[data-mode]"), function (b) { b.addEventListener("click", function () { setMode(b.dataset.mode); canvas.focus(); }); });
  document.getElementById("debugBtn").addEventListener("click", function () { toggleDebug(); canvas.focus(); });

  function setDetail(k) {
    if (!splatMesh) return;
    limit = Math.min(k, total); var ia = splatMesh.geometry.getAttribute("idx"); for (var i = 0; i < limit; i++) ia.array[i] = i; ia.needsUpdate = true; splatMesh.geometry.instanceCount = limit; lastSortKey = "";
    document.getElementById("count").textContent = limit.toLocaleString();
    Array.prototype.forEach.call(document.querySelectorAll("#detail button"), function (b) { b.setAttribute("aria-pressed", parseInt(b.dataset.detail, 10) === k ? "true" : "false"); });
  }
  Array.prototype.forEach.call(document.querySelectorAll("#detail button"), function (b) { b.addEventListener("click", function () { setDetail(parseInt(b.dataset.detail, 10)); canvas.focus(); }); });

  function resetToDoor() {
    camera.position.set(startState.x, grid.floorY + grid.eye, startState.z);
    yaw = startState.yaw; pitch = startState.pitch;
  }

  var keys = {};
  function held(a, b) { return keys[a] || (b && keys[b]); }
  window.addEventListener("keydown", function (e) {
    keys[e.code] = true;
    if (e.code === "Digit1") setMode("splat");
    if (e.code === "Digit2") setMode("mesh");
    if (e.code === "KeyM") toggleDebug();
    if (e.code === "KeyR" && grid) resetToDoor();
    if (e.code === "Space" || e.code.indexOf("Arrow") === 0) e.preventDefault();
  });
  window.addEventListener("keyup", function (e) { keys[e.code] = false; });
  window.addEventListener("blur", function () { keys = {}; });

  var dragging = false, moved = 0, locked = false;
  var hint = document.getElementById("hint");
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
    locked = document.pointerLockElement === canvas; canvas.classList.toggle("locked", locked); hint.hidden = locked;
  });

  function resize() {
    var dpr = Math.min(window.devicePixelRatio || 1, 1.25);
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

  function stepWalk(dt, input) {
    var ahead = (input.forward ? 1 : 0) - (input.back ? 1 : 0), side = (input.right ? 1 : 0) - (input.left ? 1 : 0);
    if (ahead || side) {
      var len = Math.sqrt(ahead * ahead + side * side), dist = (input.run ? RUN_SPEED : WALK_SPEED) * dt;
      var fx = -Math.sin(yaw), fz = -Math.cos(yaw), rx = Math.cos(yaw), rz = -Math.sin(yaw);
      var vx = (fx * ahead + rx * side) / len, vz = (fz * ahead + rz * side) / len;
      var steps = Math.max(1, Math.ceil(dist / MAX_STEP)), each = dist / steps;
      for (var i = 0; i < steps; i++) tryMove(vx * each, vz * each);
    }
    camera.position.y = grid.floorY + grid.eye;
  }

  var last = performance.now(), frames = 0, fpsT = last;
  function tick(now) {
    var dt = Math.min((now - last) / 1000, 0.1); last = now;
    stepWalk(dt, {
      forward: held("KeyW", "ArrowUp"), back: held("KeyS", "ArrowDown"), left: held("KeyA", "ArrowLeft"), right: held("KeyD", "ArrowRight"),
      run: held("ShiftLeft", "ShiftRight")
    });
    camera.rotation.set(pitch, yaw, 0);
    camera.updateMatrixWorld(); camera.matrixWorldInverse.copy(camera.matrixWorld).invert();
    if (splatMesh && splatMesh.visible) {
      var u = splatMesh.material.uniforms;
      u.uView.value.copy(camera.matrixWorldInverse); u.uProj.value.copy(camera.projectionMatrix);
      u.uViewport.value.set(renderer.domElement.width, renderer.domElement.height);
      var e = camera.matrixWorldInverse.elements;
      var key = [e[2], e[6], e[10], e[14]].map(function (v) { return v.toFixed(3); }).join();
      if (!sortPending && key !== lastSortKey) { sortPending = true; lastSortKey = key; worker.postMessage({ row: [e[2], e[6], e[10], e[14]], lim: limit }); }
    }
    renderer.render(scene, camera);
    frames++;
    if (now - fpsT > 500) {
      document.getElementById("fps").textContent = Math.round(frames * 1000 / (now - fpsT));
      document.getElementById("pos").textContent = "x " + camera.position.x.toFixed(2) + "  y " + camera.position.y.toFixed(2) + "  z " + camera.position.z.toFixed(2) + " m";
      frames = 0; fpsT = now;
    }
    requestAnimationFrame(tick);
  }

  window.__v = {
    camera: camera,
    stepWalk: stepWalk,
    isBlocked: isBlocked,
    setDetail: setDetail,
    grid: function () { return grid; },
    pose: function () { return { x: camera.position.x, y: camera.position.y, z: camera.position.z, yaw: yaw, pitch: pitch }; },
    setPose: function (x, z, newYaw) { camera.position.x = x; camera.position.z = z; yaw = newYaw; },
    look: function (dx, dy) { yaw -= dx * 0.0032; pitch = Math.max(-PITCH_LIMIT, Math.min(PITCH_LIMIT, pitch - dy * 0.0032)); },
    reset: resetToDoor
  };

  var manifest = null;
  fetchBuf(ASSETS + "manifest.json").then(function (mb) {
    manifest = JSON.parse(new TextDecoder().decode(mb));
    return Promise.all([fetchBuf(ASSETS + manifest.grid), fetchBuf(ASSETS + manifest.splat, function (p) { progress(0.85 * p, "Loading splat " + Math.round(100 * p) + "%"); })]);
  }).then(function (res) {
    parseGrid(JSON.parse(new TextDecoder().decode(res[0])));
    startState = { x: grid.start.x, z: grid.start.z, yaw: Math.atan2(-grid.start.forwardX, -grid.start.forwardZ), pitch: -0.08 };
    resetToDoor();
    progress(0.9, "Preparing splats");
    return unpackSplat(res[1], manifest.splat).then(function (raw) {
      return new Promise(function (r) { setTimeout(function () { buildSplats(raw); r(); }, 30); });
    });
  }).then(function () {
    progress(0.95, "Loading mesh"); return manifest.mesh ? fetchBuf(ASSETS + manifest.mesh) : null;
  }).then(function (mb) {
    if (mb) buildMesh(mb); else document.querySelector('[data-mode="mesh"]').hidden = true;
    buildGridOverlay();
    var detail = parseInt(q.get("detail") || "0", 10);
    if (detail) setDetail(detail);
    applyMode(); progress(1, "Ready");
    document.getElementById("loading").hidden = true; window.__ready = true;
    requestAnimationFrame(tick);
  }).catch(function (e) { fail(String(e && e.message || e)); });
})();
