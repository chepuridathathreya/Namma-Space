(function () {
  const VOXEL = 0.05, SOLID = 1.5, RAY_STEP = 0.025, RAY_START = 0.25, RAY_REACH = 8, CEILING = 3.2;
  const CATEGORIES = ["furniture", "appliance", "electrical", "door", "window", "room"];

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function round(value) { return Math.round(value * 100) / 100; }

  function slug(name, taken) {
    const base = name.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "") || "place";
    let id = base, n = 2;
    while (taken.has(id)) id = base + "_" + n++;
    return id;
  }

  function buildDensity(viewer) {
    const grid = viewer.grid, splats = viewer.splats();
    const nx = Math.ceil(grid.cols * grid.cell / VOXEL), nz = Math.ceil(grid.rows * grid.cell / VOXEL), ny = Math.ceil((CEILING + 0.2) / VOXEL);
    const y0 = grid.floorY - 0.2, cells = new Float32Array(nx * ny * nz);
    for (let i = 0; i < splats.count; i++) {
      const x = Math.floor((splats.xyz[i * 4] - grid.ox) / VOXEL), y = Math.floor((splats.xyz[i * 4 + 1] - y0) / VOXEL), z = Math.floor((splats.xyz[i * 4 + 2] - grid.oz) / VOXEL);
      if (x < 0 || y < 0 || z < 0 || x >= nx || y >= ny || z >= nz) continue;
      cells[(y * nz + z) * nx + x] += splats.color[i * 4 + 3] / 255;
    }
    return function (px, py, pz) {
      const x = Math.floor((px - grid.ox) / VOXEL), y = Math.floor((py - y0) / VOXEL), z = Math.floor((pz - grid.oz) / VOXEL);
      if (x < 0 || y < 0 || z < 0 || x >= nx || y >= ny || z >= nz) return 0;
      return cells[(y * nz + z) * nx + x];
    };
  }

  function start(viewer, ui) {
    const THREE = window.THREE, grid = viewer.grid, density = buildDensity(viewer);
    const draftKey = "namma_poi_draft_" + location.pathname;
    let current = null, aim = null;

    function aimPoint() {
      const pose = viewer.pose(), cosPitch = Math.cos(pose.pitch);
      const dx = -Math.sin(pose.yaw) * cosPitch, dy = Math.sin(pose.pitch), dz = -Math.cos(pose.yaw) * cosPitch;
      for (let t = RAY_START; t <= RAY_REACH; t += RAY_STEP) {
        const x = pose.x + dx * t, y = pose.y + dy * t, z = pose.z + dz * t;
        if (y <= grid.floorY) return { x: x, y: grid.floorY, z: z, surface: "floor" };
        if (y > grid.floorY + CEILING) break;
        if (density(x, y, z) >= SOLID) return { x: x, y: y, z: z, surface: "object" };
      }
      return { x: pose.x + dx * 1.5, y: pose.y + dy * 1.5, z: pose.z + dz * 1.5, surface: "air" };
    }

    const marker = new THREE.Group();
    const dot = new THREE.Mesh(new THREE.SphereGeometry(0.025, 16, 12), new THREE.MeshBasicMaterial({ color: 0xffffff, depthTest: false, depthWrite: false, transparent: true }));
    const drop = new THREE.Line(new THREE.BufferGeometry().setAttribute("position", new THREE.BufferAttribute(new Float32Array(6), 3)), new THREE.LineBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.6, depthTest: false, depthWrite: false }));
    dot.renderOrder = 7; drop.renderOrder = 7; dot.frustumCulled = false; drop.frustumCulled = false;
    marker.add(dot); marker.add(drop);
    viewer.scene.add(marker);

    const panel = el("div", "poi-editor panel"), title = el("div", "poi-editor-title", "Place editor");
    const readout = el("div", "poi-editor-aim"), rows = el("div", "poi-editor-list"), form = el("div", "poi-editor-form"), foot = el("div", "poi-editor-foot");
    const hint = el("p", "poi-editor-hint");
    hint.append("Aim the centre dot at an object and press ", el("kbd", "", "T"), " to tag it. ", el("kbd", "", "V"), " moves the chosen place to the dot.");
    panel.append(title, hint, readout, rows, form, foot);
    document.body.appendChild(panel);
    document.body.classList.add("poi-editing");

    function save() {
      try { localStorage.setItem(draftKey, JSON.stringify(ui.pois())); } catch (error) { ui.say("Draft could not be saved in this browser", 4); }
    }

    function commit(next) {
      ui.setPois(next);
      save();
      renderList();
      renderForm();
    }

    function exportJson() {
      return JSON.stringify({ version: 1, pois: ui.pois() }, null, 2) + "\n";
    }

    function field(label, value, apply, type) {
      const wrap = el("label", "", label), box = el("input");
      box.type = type || "text"; box.value = value;
      if (type === "number") box.step = "0.05";
      box.addEventListener("change", function () { apply(type === "number" ? Number(box.value) : box.value); commit(ui.pois().slice()); });
      wrap.appendChild(box);
      return wrap;
    }

    function renderForm() {
      form.textContent = "";
      if (!current || ui.pois().indexOf(current) < 0) { current = null; return; }
      const poi = current, kinds = el("datalist");
      kinds.id = "poiKinds";
      CATEGORIES.forEach(function (kind) { kinds.appendChild(el("option", "", kind)); });
      const kind = field("Category", poi.category || "", function (value) { poi.category = value.trim().toLowerCase(); });
      kind.querySelector("input").setAttribute("list", "poiKinds");
      form.append(
        field("Name", poi.name, function (value) { poi.name = value.trim() || poi.name; }),
        field("Other names (comma separated)", (poi.aliases || []).join(", "), function (value) { poi.aliases = value.split(",").map(function (word) { return word.trim(); }).filter(Boolean); }),
        kind, kinds,
        field("Description", poi.description || "", function (value) { poi.description = value.trim(); })
      );
      const numbers = el("div", "poi-editor-xyz");
      ["x", "y", "z"].forEach(function (axis) { numbers.appendChild(field(axis, poi[axis], function (value) { if (Number.isFinite(value)) poi[axis] = round(value); }, "number")); });
      form.appendChild(numbers);
      const actions = el("div", "poi-editor-actions");
      [["Move to dot", moveCurrent], ["Stand here", standHere], ["Delete", removeCurrent]].forEach(function (spec) {
        const button = el("button", "", spec[0]);
        button.type = "button"; button.addEventListener("click", function () { spec[1](); viewer.canvas.focus(); });
        actions.appendChild(button);
      });
      form.appendChild(actions);
    }

    function renderList() {
      rows.textContent = "";
      ui.pois().forEach(function (poi) {
        const row = el("button", "", poi.name);
        row.type = "button"; row.setAttribute("aria-pressed", String(poi === current));
        row.style.setProperty("--c", window.NammaPoiUI.colorOf(poi));
        row.addEventListener("click", function () { current = poi; ui.select(poi); renderList(); renderForm(); });
        rows.appendChild(row);
      });
      if (!ui.pois().length) rows.appendChild(el("p", "poi-editor-hint", "No places yet."));
    }

    function standing() {
      const pose = viewer.pose();
      return { x: round(pose.x), z: round(pose.z) };
    }

    function tag() {
      const point = aimPoint(), taken = new Set(ui.pois().map(function (poi) { return poi.id; }));
      const name = "Place " + (ui.pois().length + 1);
      const poi = { id: slug(name, taken), name: name, aliases: [], category: "furniture", x: round(point.x), y: round(point.y), z: round(point.z), description: "", stand: standing() };
      current = poi;
      commit(ui.pois().concat([poi]));
      ui.select(poi);
      const nameBox = form.querySelector("input");
      if (document.pointerLockElement) document.exitPointerLock();
      nameBox.focus(); nameBox.select();
    }

    function moveCurrent() {
      if (!current) return;
      const point = aimPoint();
      current.x = round(point.x); current.y = round(point.y); current.z = round(point.z); current.stand = standing();
      commit(ui.pois().slice());
    }

    function standHere() {
      if (!current) return;
      current.stand = standing();
      commit(ui.pois().slice());
    }

    function removeCurrent() {
      if (!current) return;
      const gone = current;
      current = null;
      commit(ui.pois().filter(function (poi) { return poi !== gone; }));
    }

    function download() {
      const link = el("a");
      link.href = URL.createObjectURL(new Blob([exportJson()], { type: "application/json" }));
      link.download = viewer.poiFile;
      link.click();
      URL.revokeObjectURL(link.href);
      ui.say("Downloaded " + viewer.poiFile + ". Put it in the site's assets folder.", 6);
    }

    function saveToProject() {
      fetch("/__save_pois", { method: "POST", headers: { "Content-Type": "application/json" }, body: exportJson() })
        .then(function (response) { return response.json().then(function (body) { return { ok: response.ok, body: body }; }); })
        .then(function (result) {
          if (!result.ok) { ui.say("Not saved: " + result.body.errors.join("; "), 10); return; }
          try { localStorage.removeItem(draftKey); } catch (error) { ui.say("Saved, but the old browser draft could not be cleared", 5); }
          const warnings = result.body.warnings.length ? " (" + result.body.warnings.length + " warning(s) in the STEP 4 window)" : "";
          ui.say("Saved " + result.body.saved + " places to the project" + warnings, 5);
        })
        .catch(function () { ui.say("No STEP 4 save server here. Use Download instead.", 6); });
    }

    [["Save to project", saveToProject], ["Download " + viewer.poiFile, download], ["Copy JSON", function () { navigator.clipboard.writeText(exportJson()).then(function () { ui.say("JSON copied", 2); }); }], ["Discard draft", function () { localStorage.removeItem(draftKey); location.reload(); }]].forEach(function (spec) {
      const button = el("button", "", spec[0]);
      button.type = "button"; button.addEventListener("click", spec[1]);
      foot.appendChild(button);
    });

    ui.onKey(function (event) {
      if (event.code === "KeyT") { tag(); return true; }
      if (event.code === "KeyV") { moveCurrent(); return true; }
      return false;
    });

    ui.onFrame(function () {
      aim = aimPoint();
      dot.position.set(aim.x, aim.y, aim.z);
      const line = drop.geometry.getAttribute("position");
      line.setXYZ(0, aim.x, aim.y, aim.z); line.setXYZ(1, aim.x, grid.floorY, aim.z); line.needsUpdate = true;
      readout.textContent = "Dot on " + aim.surface + ":  x " + aim.x.toFixed(2) + "  y " + aim.y.toFixed(2) + "  z " + aim.z.toFixed(2);
      const chosen = ui.selected();
      if (chosen !== current && chosen) { current = chosen; renderList(); renderForm(); }
    });

    let draft = null;
    try { draft = JSON.parse(localStorage.getItem(draftKey) || "null"); } catch (error) { draft = null; }
    if (Array.isArray(draft)) { ui.setPois(draft); ui.say("Loaded your unsaved draft. Discard draft returns to the file.", 6); }
    renderList();
    window.__poiEditor = { aimPoint: aimPoint, tag: tag, json: exportJson };
  }

  window.NammaPoiEditor = { start: start };
})();
