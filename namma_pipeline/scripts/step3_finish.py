import argparse
import functools
import glob
import http.server
import json
import os
import shutil
import socket
import sys
import webbrowser
import zipfile

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
PIPELINE_ROOT = os.path.abspath(os.path.join(SCRIPTS_DIR, ".."))
sys.path.insert(0, SCRIPTS_DIR)
from pipeline_common import Stages, StopPipeline, Tee, run_live


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        return

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


def stage_locate(context):
    inbox = os.path.join(PIPELINE_ROOT, "3_PUT_REMOTE_RESULT_HERE")
    archives = glob.glob(os.path.join(inbox, "*.zip"))
    if context["args"].result:
        archives = [context["args"].result]
    if not archives:
        raise StopPipeline(f"no result zip found in {inbox}. Copy the zip from the remote PC there and run STEP 3 again.")
    result = max(archives, key=os.path.getmtime)
    with zipfile.ZipFile(result) as archive:
        names = archive.namelist()
        needed = ("splat.ply", "dataparser_transforms.json", "scene.json")
        missing = [n for n in needed if n not in names]
        if missing:
            raise StopPipeline(f"the result zip is missing {missing}. It must come from STEP2_train_on_remote.sh.")
        scene = json.loads(archive.read("scene.json"))["scene"]
        if "timing.txt" in names:
            print("   remote timing:")
            for line in archive.read("timing.txt").decode().splitlines():
                print("      " + line)
    run_dir = os.path.join(PIPELINE_ROOT, "runs", scene)
    required = [
        os.path.join(run_dir, "world", "world.json"),
        os.path.join(run_dir, "world", f"{scene}_collision.json"),
        os.path.join(run_dir, "colmap", "best", "points3D.bin"),
    ]
    for path in required:
        if not os.path.exists(path):
            raise StopPipeline(f"missing {path}. The STEP 1 run for scene '{scene}' is not on this laptop.")
    context.update(result=result, scene=scene, run_dir=run_dir)
    print(f"   result zip : {result}")
    print(f"   scene      : {scene}")
    print(f"   STEP 1 data: {run_dir}")


def stage_finish(context):
    run_dir, scene = context["run_dir"], context["scene"]
    command = [
        sys.executable, os.path.join(SCRIPTS_DIR, "finish_scene.py"),
        "--result", context["result"],
        "--world", os.path.join(run_dir, "world", "world.json"),
        "--sparse", os.path.join(run_dir, "colmap", "best"),
        "--grid", os.path.join(run_dir, "world", f"{scene}_collision.json"),
        "--name", scene,
        "--out", os.path.join(run_dir, "site_build"),
        "--title", context["args"].title or scene.replace("_", " ").title(),
    ]
    site = run_live(command, "finish_scene", capture_prefix="WEBSITE_DIR=")
    if not site:
        raise StopPipeline("the finish step did not report a website folder")
    context["site"] = site
    build_dir = os.path.join(run_dir, "site_build")
    grid_name = f"{scene}_collision.json"
    world_ply = os.path.join(build_dir, f"{scene}_world.ply")
    shutil.copyfile(world_ply, os.path.join(build_dir, f"{scene}_world_unpolished.ply"))
    run_live([
        sys.executable, os.path.join(SCRIPTS_DIR, "polish_splat.py"),
        "--ply", world_ply,
        "--out-ply", world_ply,
        "--out-qsplat", os.path.join(build_dir, f"{scene}.qsplat"), os.path.join(site, "assets", f"{scene}.qsplat"),
        "--smooth-floor", str(context["args"].smooth_floor),
    ], "polish the splat")
    run_live([
        sys.executable, os.path.join(SCRIPTS_DIR, "build_collision_from_splat.py"),
        "--ply", os.path.join(build_dir, f"{scene}_world.ply"),
        "--world", os.path.join(run_dir, "world", "world.json"),
        "--sparse", os.path.join(run_dir, "colmap", "best"),
        "--grid", os.path.join(run_dir, "world", grid_name),
        "--out-grid", os.path.join(build_dir, grid_name), os.path.join(site, "assets", grid_name),
        "--preview", os.path.join(build_dir, f"{scene}_walkable_map.png"),
    ], "walkable map from the splat")


def find_free_port(start):
    for port in range(start, start + 30):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            if probe.connect_ex(("127.0.0.1", port)) != 0:
                return port
    raise StopPipeline("no free port found near 8765")


def stage_serve(context):
    port = find_free_port(context["args"].port)
    handler = functools.partial(QuietHandler, directory=context["site"])
    server = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
    context["url"] = f"http://localhost:{port}/"
    context["server"] = server


def main():
    parser = argparse.ArgumentParser(description="NammaSpace STEP 3: remote 3DGS result -> aligned splat + collision -> local website")
    parser.add_argument("--result", help="result zip (default: newest zip in 3_PUT_REMOTE_RESULT_HERE)")
    parser.add_argument("--title", help="title shown on the website")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-serve", action="store_true", help="build the website and stop without starting the local server")
    parser.add_argument("--smooth-floor", type=float, default=0.0, help="0 to 1: calm the colour of shiny floor gaussians (off by default)")
    arguments = parser.parse_args()

    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    context = {"args": arguments}
    stages = Stages("STEP 3", total=2 if arguments.no_serve else 3)
    try:
        stages.run("find the result zip and the matching STEP 1 data", lambda: stage_locate(context))
        log_dir = os.path.join(context["run_dir"], "logs")
        os.makedirs(log_dir, exist_ok=True)
        log_handle = open(os.path.join(log_dir, "step3.log"), "w", encoding="utf-8")
        sys.stdout = Tee(sys.__stdout__, log_handle)
        stages.run("align splat to the collision map, clean it, build the website", lambda: stage_finish(context))
        if not arguments.no_serve:
            stages.run("start the local website", lambda: stage_serve(context))
    except StopPipeline:
        print(stages.table())
        print("\n RESULT: STOPPED. Fix the problem above and run STEP 3 again.")
        sys.exit(1)
    print(stages.table())
    if arguments.no_serve:
        print("")
        print(f" STEP 3 FINISHED. Website files: {context['site']}")
        print(f"  Serve them with:  python -m http.server 8765 --directory {context['site']}")
        return
    print("")
    print("=" * 78)
    print(" STEP 3 FINISHED - YOUR WEBSITE IS RUNNING")
    print("=" * 78)
    print(f"  OPEN THIS LINK:  {context['url']}")
    print(f"  Website files :  {context['site']}")
    print("  Controls      :  click the scene, then W A S D to walk, mouse to look, Shift to run, M shows the collision grid")
    print("  Stop          :  press Ctrl+C in this window")
    print("", flush=True)
    webbrowser.open(context["url"])
    try:
        context["server"].serve_forever()
    except KeyboardInterrupt:
        print("\n website stopped.")


if __name__ == "__main__":
    main()
