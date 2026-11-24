(function () {
  const CATEGORY_COLORS = { furniture: "#5aa9ff", appliance: "#ff9f43", electrical: "#ffd43b", door: "#51cf66", window: "#66d9e8", room: "#b197fc" };
  const DEFAULT_COLOR = "#ced4da";
  const ROUTE_COLOR = 0x38BDF8, ROUTE_WIDTH = 0.16, ROUTE_SPACING = 0.2, ROUTE_LIFT = 0.03;
  const LABEL_RANGE = 12, NAME_RANGE = 7, AIM_RADIUS = 110, NEARBY_RANGE = 3;
  const ARRIVE_DISTANCE = 0.3, LOOK_AHEAD = 0.7, WALK_PITCH = -0.3, TURN_RATE = 3.2, FLY_SECONDS = 0.9, TURN_SECONDS = 0.5, REROUTE_SECONDS = 0.1;

  function colorOf(poi) { return CATEGORY_COLORS[poi.category] || DEFAULT_COLOR; }
  function ease(t) { return t * t * (3 - 2 * t); }
  function angleBetween(from, to) { return Math.atan2(Math.sin(to - from), Math.cos(to - from)); }
  function clamp(value, low, high) { return Math.max(low, Math.min(high, value)); }
  function formatMetres(metres) { return Number.isFinite(metres) ? metres.toFixed(1) + " m" : "no route"; }

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function start(viewer) {
    const THREE = window.THREE, grid = viewer.grid, camera = viewer.camera, addon = viewer.addon;
    const nav = window.NammaNav.createNavigator(grid), home = nav.toCell(grid.start.x, grid.start.z);
    nav.setHome(home.c, home.r);
    const eyeY = grid.floorY + grid.eye;

    let pois = [], placed = [], index = null;
    let selected = null, aimed = null, route = null, walking = false, motion = null, rerouteClock = 0, clock = 0;
    let paletteOpen = false, results = [], cursor = 0, category = "", statusTimer = 0;
    const frameHooks = [], keyHooks = [];

    const labels = el("div", "poi-labels"), cross = el("div", "poi-cross");
    const status = el("div", "poi-status panel"), card = el("div", "poi-card panel");
    const palette = el("div", "poi-palette"), box = el("div", "poi-box panel");
    const input = el("input", "poi-input"), chips = el("div", "poi-chips"), list = el("div", "poi-results");
    viewer.canvas.insertAdjacentElement("afterend", labels);
    labels.insertAdjacentElement("afterend", cross);
    input.type = "search"; input.placeholder = "Search places, like bed"; input.setAttribute("aria-label", "Search places");
    list.setAttribute("role", "listbox");
    const searchRow = el("div", "poi-search-row"), closeSearch = el("button", "", "Close");
    closeSearch.type = "button"; closeSearch.addEventListener("click", function () { closePalette(); });
    searchRow.append(input, closeSearch);
    box.append(searchRow, chips, list, el("div", "poi-hint", "Up and Down to move, Enter to show the route, Esc to close"));
    palette.append(box); palette.hidden = true; status.hidden = true; card.hidden = true;
    document.body.append(palette);
    const dock = document.getElementById("dock"), action = document.getElementById("action");
    dock.prepend(status);
    action.prepend(card);

    const findButton = document.getElementById("findBtn");
    findButton.hidden = false;
    findButton.addEventListener("click", openPalette);

    function say(text, seconds) {
      status.textContent = text; status.hidden = false;
      clearTimeout(statusTimer);
      if (seconds) statusTimer = setTimeout(function () { status.hidden = true; }, seconds * 1000);
    }

    function cellPoint(x, z) { return { x: (x - grid.ox) / grid.cell, z: (z - grid.oz) / grid.cell }; }

    function sightClear(pose, x, z) {
      const a = cellPoint(pose.x, pose.z), b = cellPoint(x, z);
      return nav.lineClear(a.x, a.z, b.x, b.z, grid.occupied);
    }

    function setPois(next) {
      pois = next;
      placed = window.NammaPOI.placeOnGrid(pois, nav);
      index = window.NammaPOI.createIndex(pois, 2);
      labels.textContent = "";
      placed.forEach(function (entry) {
        const label = el("button", "poi-label"), name = el("span", "name", entry.poi.name);
        label.type = "button"; label.style.setProperty("--c", colorOf(entry.poi));
        label.append(name, el("span", "stem"), el("span", "pin"));
        label.addEventListener("click", function () { select(entry, "label"); });
        entry.label = label; labels.appendChild(label);
      });
      const keep = selected && placed.find(function (entry) { return entry.poi.id === selected.poi.id; });
      selected = null;
      if (keep) select(keep, "label"); else clearSelection();
      renderChips();
    }

    function entryOf(poi) { return placed.find(function (entry) { return entry.poi === poi; }); }

    const projected = new THREE.Vector3();
    function updateLabels() {
      const pose = viewer.pose(), width = window.innerWidth, height = window.innerHeight;
      const inRange = new Set(index.within(pose.x, pose.z, LABEL_RANGE));
      let best = null, bestGap = AIM_RADIUS;
      placed.forEach(function (entry) {
        const poi = entry.poi, label = entry.label;
        let shown = inRange.has(poi) || entry === selected;
        if (shown) {
          projected.set(poi.x, poi.y, poi.z).applyMatrix4(camera.matrixWorldInverse);
          shown = projected.z < -0.1;
          if (shown) { projected.applyMatrix4(camera.projectionMatrix); shown = Math.abs(projected.x) < 1.05 && Math.abs(projected.y) < 1.05; }
        }
        label.hidden = !shown;
        if (!shown) return;
        const sx = (projected.x * 0.5 + 0.5) * width, sy = (-projected.y * 0.5 + 0.5) * height;
        const distance = Math.hypot(poi.x - pose.x, poi.z - pose.z);
        const visible = distance < 1.5 || sightClear(pose, entry.stand ? entry.stand.x : poi.x, entry.stand ? entry.stand.z : poi.z);
        label.style.transform = "translate(" + sx.toFixed(1) + "px," + sy.toFixed(1) + "px)";
        label.classList.toggle("dim", !visible && entry !== selected);
        label.classList.toggle("far", distance > NAME_RANGE && entry !== selected);
        const gap = Math.hypot(sx - width / 2, sy - height / 2);
        if (gap < bestGap) { best = entry; bestGap = gap; }
      });
      if (best !== aimed) {
        if (aimed) aimed.label.classList.remove("aim");
        aimed = best;
      }
      if (aimed) aimed.label.classList.toggle("aim", viewer.isLocked());
      cross.hidden = !viewer.isLocked() && !viewer.editing;
    }

    function facing(fromX, fromZ, poi) {
      const dx = poi.x - fromX, dz = poi.z - fromZ;
      return { yaw: Math.atan2(-dx, -dz), pitch: clamp(Math.atan2(poi.y - eyeY, Math.hypot(dx, dz)), -0.6, 0.5) };
    }

    function planRoute() {
      if (!selected || !selected.stand) return null;
      const pose = viewer.pose(), found = nav.route(nav.toCell(pose.x, pose.z), selected.stand);
      if (!found) return null;
      const points = found.points.slice(), here = { x: pose.x, z: pose.z };
      if (points.length > 1) {
        const a = cellPoint(pose.x, pose.z), b = cellPoint(points[1].x, points[1].z);
        if (nav.lineClear(a.x, a.z, b.x, b.z)) points[0] = here; else points.unshift(here);
      } else {
        points.unshift(here);
      }
      let metres = 0;
      for (let i = 1; i < points.length; i++) metres += Math.hypot(points[i].x - points[i - 1].x, points[i].z - points[i - 1].z);
      return { points: points, metres: metres };
    }

    const ribbonMaterial = new THREE.ShaderMaterial({
      transparent: true, depthTest: false, depthWrite: false, side: THREE.DoubleSide,
      uniforms: { uColor: { value: new THREE.Color(ROUTE_COLOR) }, uTime: { value: 0 } },
      vertexShader: "attribute float along; attribute float side; attribute float seen; varying float vAlong; varying float vSide; varying float vSeen; void main() { vAlong = along; vSide = side; vSeen = seen; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }",
      fragmentShader: [
        "uniform vec3 uColor; uniform float uTime; varying float vAlong; varying float vSide; varying float vSeen;",
        "void main() {",
        "  float across = abs(vSide);",
        "  float body = 1.0 - smoothstep(0.78, 1.0, across);",
        "  float phase = fract(vAlong / 0.55 - uTime * 1.6 + across * 0.45);",
        "  float chevron = smoothstep(0.0, 0.1, phase) * (1.0 - smoothstep(0.34, 0.44, phase));",
        "  vec3 color = mix(uColor, vec3(1.0), chevron * 0.85);",
        "  float alpha = (0.62 + 0.33 * chevron) * body * smoothstep(0.0, 0.35, vAlong) * vSeen;",
        "  gl_FragColor = vec4(color, alpha);",
        "  #include <colorspace_fragment>",
        "}"
      ].join("\n")
    });
    const ribbon = new THREE.Mesh(new THREE.BufferGeometry(), ribbonMaterial);
    ribbon.frustumCulled = false; ribbon.renderOrder = 5; ribbon.visible = false;
    const goal = new THREE.Mesh(new THREE.RingGeometry(0.17, 0.24, 48), new THREE.MeshBasicMaterial({ color: ROUTE_COLOR, transparent: true, opacity: 0.9, side: THREE.DoubleSide, depthTest: false, depthWrite: false }));
    goal.rotation.x = -Math.PI / 2; goal.frustumCulled = false; goal.renderOrder = 6; goal.visible = false;
    viewer.scene.add(ribbon); viewer.scene.add(goal);

    function sampleRoute(points) {
      const samples = [];
      let travelled = 0;
      for (let i = 1; i < points.length; i++) {
        const a = points[i - 1], b = points[i], length = Math.hypot(b.x - a.x, b.z - a.z), pieces = Math.max(1, Math.ceil(length / ROUTE_SPACING));
        for (let k = i === 1 ? 0 : 1; k <= pieces; k++) {
          const t = k / pieces;
          samples.push({ x: a.x + (b.x - a.x) * t, z: a.z + (b.z - a.z) * t, along: travelled + length * t });
        }
        travelled += length;
      }
      return samples;
    }

    function drawRibbon() {
      ribbon.geometry.dispose();
      const samples = route ? sampleRoute(route.points) : [];
      ribbon.visible = goal.visible = samples.length > 1;
      if (!ribbon.visible) return;
      const count = samples.length, position = new Float32Array(count * 6), along = new Float32Array(count * 2), side = new Float32Array(count * 2), seen = new Float32Array(count * 2).fill(1), indices = [];
      const y = grid.floorY + ROUTE_LIFT, half = ROUTE_WIDTH / 2;
      for (let i = 0; i < count; i++) {
        const before = samples[Math.max(0, i - 1)], after = samples[Math.min(count - 1, i + 1)];
        const tx = after.x - before.x, tz = after.z - before.z, length = Math.hypot(tx, tz) || 1, nx = -tz / length * half, nz = tx / length * half;
        position.set([samples[i].x + nx, y, samples[i].z + nz, samples[i].x - nx, y, samples[i].z - nz], i * 6);
        along[i * 2] = along[i * 2 + 1] = samples[i].along;
        side[i * 2] = 1; side[i * 2 + 1] = -1;
        if (i > 0) indices.push(i * 2 - 2, i * 2 - 1, i * 2, i * 2 - 1, i * 2 + 1, i * 2);
      }
      const geometry = new THREE.BufferGeometry();
      geometry.setAttribute("position", new THREE.BufferAttribute(position, 3));
      geometry.setAttribute("along", new THREE.BufferAttribute(along, 1));
      geometry.setAttribute("side", new THREE.BufferAttribute(side, 1));
      geometry.setAttribute("seen", new THREE.BufferAttribute(seen, 1));
      geometry.setIndex(indices);
      geometry.userData.samples = samples;
      ribbon.geometry = geometry;
      const end = samples[count - 1];
      goal.position.set(end.x, y + 0.005, end.z);
    }

    function shadeRibbon() {
      const samples = ribbon.geometry.userData.samples;
      if (!ribbon.visible || !samples) return;
      const pose = viewer.pose(), seen = ribbon.geometry.getAttribute("seen");
      for (let i = 0; i < samples.length; i++) {
        const value = sightClear(pose, samples[i].x, samples[i].z) ? 1 : 0.28;
        seen.array[i * 2] = seen.array[i * 2 + 1] = value;
      }
      seen.needsUpdate = true;
    }

    function refreshRoute() {
      route = planRoute();
      drawRibbon();
      renderCard();
    }

    function clearSelection() {
      if (selected) selected.label.classList.remove("selected");
      selected = null; route = null; walking = false; motion = null;
      drawRibbon();
      card.hidden = true;
    }

    function select(entry, source) {
      if (selected) selected.label.classList.remove("selected");
      selected = entry; walking = false; motion = null;
      entry.label.classList.add("selected");
      refreshRoute();
      if (!entry.stand) say("No walkable spot near " + entry.poi.name, 4);
      else if (!route) say("No walkable route to " + entry.poi.name, 4);
      else if (source !== "label") turnToward(route.points.length > 1 && route.metres > 1.5 ? { x: route.points[1].x, y: eyeY - 0.25, z: route.points[1].z } : entry.poi);
    }

    function turnToward(target) {
      const pose = viewer.pose(), look = facing(pose.x, pose.z, target);
      motion = { kind: "turn", time: 0, seconds: TURN_SECONDS, from: pose, to: { yaw: look.yaw, pitch: look.pitch } };
    }

    function flyToSelected() {
      if (!selected || !selected.stand) return;
      const pose = viewer.pose(), look = facing(selected.stand.x, selected.stand.z, selected.poi);
      walking = false;
      motion = { kind: "fly", time: 0, seconds: FLY_SECONDS, from: pose, to: { x: selected.stand.x, z: selected.stand.z, yaw: look.yaw, pitch: look.pitch }, name: selected.poi.name };
    }

    function walkToSelected() {
      if (!selected || !route) return;
      motion = null; walking = true;
      say("Walking to " + selected.poi.name + ". Press a move key to stop.");
    }

    function arrive(name) {
      walking = false;
      if (selected) turnToward(selected.poi);
      say("Arrived at " + name, 3);
    }

    function advanceMotion(dt, inputState) {
      motion.time += dt;
      const t = ease(Math.min(1, motion.time / motion.seconds)), from = motion.from, to = motion.to, pose = viewer.pose();
      const yaw = from.yaw + angleBetween(from.yaw, to.yaw) * t, pitch = from.pitch + (to.pitch - from.pitch) * t;
      const flying = motion.kind === "fly";
      viewer.setView(flying ? from.x + (to.x - from.x) * t : pose.x, flying ? from.z + (to.z - from.z) * t : pose.z, yaw, pitch);
      if (motion.time >= motion.seconds) {
        const name = motion.name;
        motion = null;
        if (flying) { refreshRoute(); say("Arrived at " + name, 3); }
      }
      return flying ? {} : inputState;
    }

    function pointAhead(points, distance) {
      let left = distance;
      for (let i = 1; i < points.length; i++) {
        const a = points[i - 1], b = points[i], length = Math.hypot(b.x - a.x, b.z - a.z);
        if (length >= left) return { x: a.x + (b.x - a.x) * left / length, z: a.z + (b.z - a.z) * left / length };
        left -= length;
      }
      return points[points.length - 1];
    }

    function steerTarget(pose) {
      const from = cellPoint(pose.x, pose.z);
      for (let reach = LOOK_AHEAD; reach > 0.05; reach *= 0.6) {
        const target = pointAhead(route.points, reach), to = cellPoint(target.x, target.z);
        if (nav.lineClear(from.x, from.z, to.x, to.z)) return target;
      }
      return pointAhead(route.points, 0.05);
    }

    function advanceWalk(dt, inputState) {
      if (inputState.forward || inputState.back || inputState.left || inputState.right || inputState.jump) {
        walking = false; say("Walk stopped", 2);
        return inputState;
      }
      if (!route) { walking = false; say("No walkable route", 3); return inputState; }
      if (route.metres < ARRIVE_DISTANCE) { arrive(selected.poi.name); return {}; }
      const pose = viewer.pose(), target = steerTarget(pose), wanted = Math.atan2(-(target.x - pose.x), -(target.z - pose.z));
      const error = angleBetween(pose.yaw, wanted), turn = clamp(error, -TURN_RATE * dt, TURN_RATE * dt);
      viewer.setView(pose.x, pose.z, pose.yaw + turn, pose.pitch + (WALK_PITCH - pose.pitch) * Math.min(1, dt * 4));
      return { forward: Math.abs(error) < 0.9 };
    }

    function step(dt, inputState) {
      if (motion) return advanceMotion(dt, inputState);
      if (walking) return advanceWalk(dt, inputState);
      return inputState;
    }

    function frame(dt) {
      clock += dt; rerouteClock += dt;
      if (selected && !motion && rerouteClock >= REROUTE_SECONDS) {
        rerouteClock = 0;
        route = planRoute();
        drawRibbon();
        updateCardDistance();
      }
      ribbonMaterial.uniforms.uTime.value = clock;
      goal.scale.setScalar(1 + 0.16 * Math.sin(clock * 4));
      shadeRibbon();
      updateLabels();
      frameHooks.forEach(function (hook) { hook(dt); });
    }

    function drawMinimap(context, toMap, size) {
      if (route && route.points.length > 1) {
        context.beginPath();
        route.points.forEach(function (point, i) { const p = toMap(point.x, point.z); if (i) context.lineTo(p.x, p.y); else context.moveTo(p.x, p.y); });
        context.lineJoin = "round"; context.lineCap = "round";
        context.lineWidth = size * 0.02; context.strokeStyle = "#38BDF8"; context.stroke();
      }
      placed.forEach(function (entry) {
        const p = toMap(entry.poi.x, entry.poi.z), chosen = entry === selected;
        context.beginPath(); context.arc(p.x, p.y, size * (chosen ? 0.03 : 0.02), 0, Math.PI * 2);
        context.fillStyle = colorOf(entry.poi); context.fill();
        context.lineWidth = size * (chosen ? 0.012 : 0.006); context.strokeStyle = chosen ? "#ffffff" : "rgba(15,17,16,0.9)"; context.stroke();
        entry.map = p;
      });
    }

    viewer.miniCanvas.addEventListener("click", function (event) {
      const rect = viewer.miniCanvas.getBoundingClientRect(), scale = viewer.miniCanvas.width / rect.width;
      const x = (event.clientX - rect.left) * scale, y = (event.clientY - rect.top) * scale;
      let best = null, bestGap = viewer.miniCanvas.width * 0.06;
      placed.forEach(function (entry) {
        if (!entry.map) return;
        const gap = Math.hypot(entry.map.x - x, entry.map.y - y);
        if (gap < bestGap) { best = entry; bestGap = gap; }
      });
      if (best) select(best, "map");
    });

    viewer.canvas.addEventListener("pointerdown", function () {
      if (viewer.isLocked() && aimed && !viewer.editing) select(aimed, "label");
    });

    function nearbyOf(entry) {
      return index.within(entry.poi.x, entry.poi.z, NEARBY_RANGE).filter(function (poi) { return poi !== entry.poi; }).sort(function (a, b) { return Math.hypot(a.x - entry.poi.x, a.z - entry.poi.z) - Math.hypot(b.x - entry.poi.x, b.z - entry.poi.z); }).slice(0, 4);
    }

    function updateCardDistance() {
      const line = card.querySelector(".poi-distance");
      if (!line || !selected) return;
      if (!route) { line.textContent = "No walkable route from here"; return; }
      line.textContent = route.metres < ARRIVE_DISTANCE ? "You are here" : formatMetres(route.metres) + " walk, about " + Math.max(1, Math.round(route.metres / viewer.walkSpeed)) + " s";
    }

    function renderCard() {
      if (!selected) { card.hidden = true; return; }
      const poi = selected.poi;
      card.textContent = ""; card.hidden = false; card.style.setProperty("--c", colorOf(poi));
      const head = el("div", "poi-card-head"), close = el("button", "poi-close", "Close");
      close.type = "button"; close.addEventListener("click", clearSelection);
      head.append(el("span", "poi-tag", poi.category || "place"), close);
      card.append(head, el("h2", "", poi.name));
      card.setAttribute("aria-label", poi.name);
      if (poi.description) card.append(el("p", "poi-description", poi.description));
      card.append(el("p", "poi-distance"));
      const actions = el("div", "poi-actions");
      [["Walk there", "G", walkToSelected, "primary"], ["Fly there", "F", flyToSelected, ""]].forEach(function (spec) {
        const button = el("button", "btn " + spec[3]);
        button.type = "button"; button.append(spec[0], el("kbd", "", spec[1]));
        button.disabled = !selected.stand;
        button.addEventListener("click", function () { spec[2](); viewer.canvas.focus(); });
        actions.appendChild(button);
      });
      card.append(actions);
      const near = nearbyOf(selected);
      if (near.length) {
        const row = el("div", "poi-nearby");
        row.append(el("span", "", "Nearby"));
        near.forEach(function (other) {
          const link = el("button", "", other.name);
          link.type = "button"; link.addEventListener("click", function () { select(entryOf(other), "search"); });
          row.appendChild(link);
        });
        card.append(row);
      }
      updateCardDistance();
    }

    function renderChips() {
      const kinds = Array.from(new Set(pois.map(function (poi) { return poi.category; }).filter(Boolean))).sort();
      chips.textContent = "";
      [""].concat(kinds).forEach(function (kind) {
        const chip = el("button", "", kind || "All");
        chip.type = "button"; chip.setAttribute("aria-pressed", String(kind === category));
        chip.addEventListener("click", function () { category = kind; renderChips(); renderResults(); input.focus(); });
        chips.appendChild(chip);
      });
    }

    let searchFrom = null;
    function walkingMetres(poi) {
      const entry = entryOf(poi), found = entry && entry.stand && searchFrom ? nav.route(searchFrom, entry.stand) : null;
      return found ? found.metres : Infinity;
    }

    function renderResults() {
      const query = input.value.trim(), pool = category ? pois.filter(function (poi) { return poi.category === category; }) : pois;
      if (query) results = window.NammaPOI.search(query, pool, walkingMetres);
      else results = pool.map(function (poi) { return { poi: poi, metres: walkingMetres(poi) }; }).sort(function (a, b) { return a.metres - b.metres; });
      cursor = clamp(cursor, 0, Math.max(0, results.length - 1));
      list.textContent = "";
      if (!results.length) { list.append(el("div", "poi-empty", "No place matches “" + query + "”")); return; }
      results.forEach(function (result, i) {
        const row = el("button", "poi-row"), text = el("span", "poi-row-text");
        row.type = "button"; row.setAttribute("role", "option"); row.setAttribute("aria-selected", String(i === cursor));
        row.style.setProperty("--c", colorOf(result.poi));
        text.append(el("b", "", result.poi.name), el("small", "", [result.poi.category, result.poi.description].filter(Boolean).join(" · ")));
        row.append(el("i", "poi-dot"), text, el("span", "poi-row-metres", formatMetres(result.metres)));
        row.addEventListener("click", function () { choose(i); });
        row.addEventListener("pointermove", function () { if (cursor !== i) { cursor = i; markCursor(); } });
        list.appendChild(row);
      });
    }

    function markCursor() {
      Array.prototype.forEach.call(list.querySelectorAll(".poi-row"), function (row, i) {
        row.setAttribute("aria-selected", String(i === cursor));
        if (i === cursor) row.scrollIntoView({ block: "nearest" });
      });
    }

    function choose(i) {
      const result = results[i];
      if (!result) return;
      closePalette();
      select(entryOf(result.poi), "search");
    }

    function openPalette() {
      if (document.pointerLockElement) document.exitPointerLock();
      const pose = viewer.pose();
      searchFrom = nav.toCell(pose.x, pose.z);
      paletteOpen = true; palette.hidden = false; input.value = ""; cursor = 0;
      renderResults();
      input.focus();
    }

    function closePalette() {
      paletteOpen = false; palette.hidden = true;
      viewer.canvas.focus();
    }

    input.addEventListener("input", function () { cursor = 0; renderResults(); });
    palette.addEventListener("pointerdown", function (event) { if (event.target === palette) closePalette(); });

    function keydown(event) {
      if (paletteOpen) {
        if (event.code === "Escape") closePalette();
        else if (event.code === "ArrowDown") { cursor = Math.min(results.length - 1, cursor + 1); markCursor(); event.preventDefault(); }
        else if (event.code === "ArrowUp") { cursor = Math.max(0, cursor - 1); markCursor(); event.preventDefault(); }
        else if (event.code === "Enter") choose(cursor);
        return true;
      }
      if (/^(INPUT|TEXTAREA|SELECT)$/.test(event.target.tagName || "")) return true;
      if (event.code === "Slash" || (event.code === "KeyK" && (event.ctrlKey || event.metaKey))) { event.preventDefault(); openPalette(); return true; }
      if (event.ctrlKey || event.metaKey || event.altKey) return false;
      for (let i = 0; i < keyHooks.length; i++) if (keyHooks[i](event)) return true;
      if (event.code === "KeyE") { if (aimed) select(aimed, "label"); return true; }
      if (event.code === "KeyG") { walkToSelected(); return true; }
      if (event.code === "KeyF") { flyToSelected(); return true; }
      if (event.code === "KeyX") { clearSelection(); return true; }
      return false;
    }

    addon.step = step; addon.frame = frame; addon.minimap = drawMinimap; addon.keydown = keydown;

    const problems = viewer.data ? window.NammaPOI.validate(viewer.data) : [];
    if (problems.length) { console.warn("pois.json problems:\n" + problems.join("\n")); say("pois.json has " + problems.length + " problem(s), see the console", 8); }
    setPois(viewer.data && Array.isArray(viewer.data.pois) ? viewer.data.pois.filter(function (poi) { return poi && typeof poi.id === "string" && Number.isFinite(poi.x) && Number.isFinite(poi.y) && Number.isFinite(poi.z); }) : []);

    const ui = {
      nav: nav, say: say, select: function (poi) { const entry = entryOf(poi); if (entry) select(entry, "label"); }, clear: clearSelection,
      pois: function () { return pois; }, setPois: setPois, selected: function () { return selected ? selected.poi : null; },
      onFrame: function (hook) { frameHooks.push(hook); }, onKey: function (hook) { keyHooks.push(hook); }
    };
    window.__poi = ui;
    if (viewer.editing && window.NammaPoiEditor) window.NammaPoiEditor.start(viewer, ui);
  }

  window.NammaPoiUI = { start: start, colorOf: colorOf };
})();
