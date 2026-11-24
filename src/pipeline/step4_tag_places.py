import argparse
import collections
import datetime
import functools
import glob
import http.server
import json
import math
import os
import shutil
import socket
import sys
import webbrowser

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(SCRIPTS_DIR, "..", ".."))
BACKUP_DIR = os.path.join(REPO_ROOT, "tmp", "poi_backups")
sys.path.insert(0, SCRIPTS_DIR)
from pipeline_common import Stages, StopPipeline

SAVE_PATH = "/__save_pois"
MAX_BODY_BYTES = 2_000_000
CEILING_METRES = 3.2
MIN_PLACES_FOR_PASS = 1


def is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def cell_of(grid, x, z):
    column = math.floor((x - grid["originX"]) / grid["cell"])
    row = math.floor((z - grid["originZ"]) / grid["cell"])
    return column, row


def walkable(grid, x, z):
    column, row = cell_of(grid, x, z)
    if column < 0 or row < 0 or column >= grid["cols"] or row >= grid["rows"]:
        return False
    return grid["blocked"][row][column] == "0"


def validate(data, grid):
    errors, warnings = [], []
    if not isinstance(data, dict) or not isinstance(data.get("pois"), list):
        return ['the file needs a "pois" list'], warnings
    seen = set()
    for index, poi in enumerate(data["pois"], start=1):
        identifier = poi.get("id") if isinstance(poi, dict) else None
        label = f"place {index}" + (f" ({identifier})" if identifier else "")
        if not isinstance(poi, dict) or not isinstance(identifier, str) or not identifier:
            errors.append(f"{label}: id is missing")
            continue
        if identifier in seen:
            errors.append(f"{label}: id is used twice")
        seen.add(identifier)
        if not isinstance(poi.get("name"), str) or not poi["name"].strip():
            errors.append(f"{label}: name is missing")
        for axis in ("x", "y", "z"):
            if not is_number(poi.get(axis)):
                errors.append(f"{label}: {axis} must be a number")
        if "aliases" in poi and not isinstance(poi["aliases"], list):
            errors.append(f"{label}: aliases must be a list")
        stand = poi.get("stand")
        if stand is not None and not (isinstance(stand, dict) and is_number(stand.get("x")) and is_number(stand.get("z"))):
            errors.append(f"{label}: stand needs x and z numbers")
        if errors and errors[-1].startswith(label):
            continue
        if not str(poi.get("category", "")).strip():
            warnings.append(f"{label}: category is empty")
        if not str(poi.get("description", "")).strip():
            warnings.append(f"{label}: description is empty")
        if poi["name"].strip().lower().startswith("place ") and poi["name"].strip()[6:].isdigit():
            warnings.append(f"{label}: still has the default name '{poi['name']}'")
        if not -0.2 <= poi["y"] - grid["floorY"] <= CEILING_METRES:
            warnings.append(f"{label}: y {poi['y']} is outside the room height")
        if is_number(poi["x"]) and not (grid["originX"] <= poi["x"] <= grid["originX"] + grid["cols"] * grid["cell"] and grid["originZ"] <= poi["z"] <= grid["originZ"] + grid["rows"] * grid["cell"]):
            warnings.append(f"{label}: sits outside the walkable map")
        if stand is None:
            warnings.append(f"{label}: has no stand position, the walk-to route will guess one")
        elif not walkable(grid, stand["x"], stand["z"]):
            warnings.append(f"{label}: stand position is not on a walkable cell")
    return errors, warnings


def load_json(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def candidate_sites():
    patterns = [
        os.path.join(REPO_ROOT, "workspace", "runs", "*", "site_build", "site"),
        os.path.join(REPO_ROOT, "scenes", "*", "site"),
    ]
    sites = []
    for pattern in patterns:
        sites.extend(path for path in glob.glob(pattern) if os.path.exists(os.path.join(path, "assets", "manifest.json")))
    return sites


def newest_activity(site):
    assets = os.path.join(site, "assets")
    return max(os.path.getmtime(os.path.join(assets, name)) for name in os.listdir(assets))


def stage_locate(context):
    if context["args"].site:
        site = os.path.abspath(context["args"].site)
    else:
        sites = candidate_sites()
        if not sites:
            raise StopPipeline("no scene website found. Run STEP 3 first, or pass --site <folder with assets/manifest.json>.")
        site = max(sites, key=newest_activity)
    manifest_path = os.path.join(site, "assets", "manifest.json")
    if not os.path.exists(manifest_path):
        raise StopPipeline(f"{manifest_path} does not exist, so this is not a scene website folder.")
    manifest = load_json(manifest_path)
    grid_path = os.path.join(site, "assets", manifest.get("grid", ""))
    if not manifest.get("grid") or not os.path.exists(grid_path):
        raise StopPipeline(f"the manifest names no collision grid that exists ({grid_path}).")
    poi_name = manifest.get("pois") or "pois.json"
    poi_path = os.path.join(site, "assets", poi_name)
    for needed in ("poi_editor.js", "poi_ui.js", "poi.js"):
        if not os.path.exists(os.path.join(site, needed)):
            raise StopPipeline(f"{needed} is missing from {site}. Rebuild the site with the current viewer template.")
    if "__save_pois" not in open(os.path.join(site, "poi_editor.js"), encoding="utf-8").read():
        raise StopPipeline("this site's poi_editor.js has no 'Save to project' button. Copy src/viewer/poi_editor.js into the site.")
    context.update(site=site, grid=load_json(grid_path), poi_path=poi_path, poi_name=poi_name)
    existing = load_json(poi_path)["pois"] if os.path.exists(poi_path) else []
    print(f"   site        : {site}")
    print(f"   places file : {poi_path} ({len(existing)} places now)")
    print(f"   walkable map: {context['grid']['cols']} x {context['grid']['rows']} cells of {context['grid']['cell']} m")


def make_handler(context):
    class Handler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, format, *args):
            return

        def end_headers(self):
            self.send_header("Cache-Control", "no-store")
            super().end_headers()

        def reply(self, status, body):
            payload = json.dumps(body).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def do_POST(self):
            if self.path != SAVE_PATH:
                self.reply(404, {"errors": ["unknown address"], "warnings": []})
                return
            length = int(self.headers.get("Content-Length") or 0)
            if length <= 0 or length > MAX_BODY_BYTES:
                self.reply(400, {"errors": ["the places file is empty or too large"], "warnings": []})
                return
            try:
                data = json.loads(self.rfile.read(length).decode("utf-8"))
            except ValueError:
                self.reply(400, {"errors": ["the places file is not valid JSON"], "warnings": []})
                return
            errors, warnings = validate(data, context["grid"])
            if errors:
                print(f"   [{datetime.datetime.now():%H:%M:%S}] save REFUSED: {len(errors)} error(s)")
                for line in errors:
                    print(f"      error: {line}")
                self.reply(400, {"errors": errors, "warnings": warnings})
                return
            poi_path = context["poi_path"]
            if os.path.exists(poi_path):
                os.makedirs(BACKUP_DIR, exist_ok=True)
                stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                shutil.copyfile(poi_path, os.path.join(BACKUP_DIR, f"{stamp}_{context['poi_name']}"))
            with open(poi_path, "w", encoding="utf-8", newline="\n") as handle:
                json.dump({"version": data.get("version", 1), "pois": data["pois"]}, handle, indent=2, ensure_ascii=False)
                handle.write("\n")
            context["saves"] += 1
            print(f"   [{datetime.datetime.now():%H:%M:%S}] saved {len(data['pois'])} places ({len(warnings)} warning(s))")
            self.reply(200, {"saved": len(data["pois"]), "warnings": warnings})

    return Handler


def find_free_port(start):
    for port in range(start, start + 30):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            if probe.connect_ex(("127.0.0.1", port)) != 0:
                return port
    raise StopPipeline(f"no free port found near {start}")


def stage_tag(context):
    port = find_free_port(context["args"].port)
    handler = functools.partial(make_handler(context), directory=context["site"])
    server = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
    url = f"http://localhost:{port}/?edit=1"
    print("")
    print(f"  OPEN THIS LINK : {url}")
    print("  In the browser : click the scene, walk with W A S D, aim the centre dot at an object and press T")
    print("                   fill Name, Other names, Category, Description, then press 'Save to project'")
    print("                   V moves the chosen place to the dot, 'Stand here' records where a visitor should stand")
    print("  When finished  : press Save to project once more, then press Ctrl+C in this window")
    print("", flush=True)
    if not context["args"].no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n   editor stopped.")
    finally:
        server.server_close()
    if context["saves"] == 0:
        print("   note: nothing was saved in this session, the places file is unchanged.")


def stage_check(context):
    if not os.path.exists(context["poi_path"]):
        raise StopPipeline(f"{context['poi_path']} does not exist. Tag at least one place and press Save to project.")
    data = load_json(context["poi_path"])
    errors, warnings = validate(data, context["grid"])
    count = len(data.get("pois", []))
    if not errors and count < MIN_PLACES_FOR_PASS:
        errors.append("the places file has no places")
    categories = collections.Counter(str(poi.get("category", "")).strip().lower() or "(none)" for poi in data.get("pois", []) if isinstance(poi, dict))
    print(f"   places       : {count}")
    print("   by category  : " + ", ".join(f"{name} {number}" for name, number in sorted(categories.items())))
    for line in warnings:
        print(f"   warning      : {line}")
    for line in errors:
        print(f"   ERROR        : {line}")
    if errors:
        raise StopPipeline(f"{len(errors)} error(s) in {context['poi_path']}. Run STEP 4 again and fix them.")
    context["count"] = count
    context["warnings"] = len(warnings)


def stage_view(context):
    port = find_free_port(context["args"].port + 1)
    handler = functools.partial(make_handler(context), directory=context["site"])
    server = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
    url = f"http://localhost:{port}/index.html"
    print("")
    print(f"  OPEN THIS LINK : {url}")
    print("  This is the normal site with your saved places. Try the search box (/) and walk-to (G).")
    print("  Stop           : press Ctrl+C in this window")
    print("", flush=True)
    if not context["args"].no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n   site stopped.")
    finally:
        server.server_close()


def main():
    parser = argparse.ArgumentParser(description="NammaSpace STEP 4: tag places (POIs) in the viewer and save a checked pois.json into the site")
    parser.add_argument("--site", help="scene website folder (default: the most recently updated scene site)")
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--no-browser", action="store_true", help="do not open the browser automatically")
    parser.add_argument("--no-view", action="store_true", help="do not open the normal site after the places file is checked")
    arguments = parser.parse_args()

    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    context = {"args": arguments, "saves": 0}
    stages = Stages("STEP 4", total=3 if arguments.no_view else 4)
    try:
        stages.run("find the scene website and its walkable map", lambda: stage_locate(context))
        stages.run("tag places in the browser (Ctrl+C when finished)", lambda: stage_tag(context))
        stages.run("check the saved places file", lambda: stage_check(context))
        if not arguments.no_view:
            stages.run("open the normal site to test the places (Ctrl+C to stop)", lambda: stage_view(context))
    except StopPipeline:
        print(stages.table())
        print("\n RESULT: STOPPED. Fix the problem above and run STEP 4 again.")
        sys.exit(1)
    print(stages.table())
    print("")
    print("=" * 78)
    print(" STEP 4 FINISHED - PLACES FILE IS CHECKED")
    print("=" * 78)
    print(f"  Places saved  : {context['count']} ({context['warnings']} warning(s))")
    print(f"  File          : {context['poi_path']}")
    print(f"  Old versions  : {BACKUP_DIR}")
    print("  Next          : test search and walk-to on the site, then deploy when you decide to")
    print("", flush=True)


if __name__ == "__main__":
    main()
