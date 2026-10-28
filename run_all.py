#!/usr/bin/env python3
import argparse
import glob
import importlib.util
import json
import os
import platform
import shutil
import subprocess
import sys
import time
import zipfile

REPO = os.path.dirname(os.path.abspath(__file__))
PIPELINE = os.path.join(REPO, "namma_pipeline")
SCRIPTS = os.path.join(PIPELINE, "scripts")
RUNS = os.path.join(PIPELINE, "runs")
OUTBOX = os.path.join(PIPELINE, "2_SEND_TO_REMOTE")
SAMPLE_ZIP = os.path.join(REPO, "test", "sample_scene.zip")
MIN_GPU_MIB = 16000
MIN_DISK_GB = 20


class Problem(Exception):
    pass


def banner(text):
    print("")
    print("=" * 78)
    print(f" {text}")
    print("=" * 78, flush=True)


def tool_path(name, extra_patterns=()):
    found = shutil.which(name)
    if found:
        return found
    for pattern in extra_patterns:
        matches = sorted(glob.glob(os.path.expandvars(pattern)))
        if matches:
            return matches[-1]
    return None


def module_present(name):
    return importlib.util.find_spec(name) is not None


def gpu_info():
    smi = shutil.which("nvidia-smi")
    if not smi:
        return None
    out = subprocess.run([smi, "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"], capture_output=True, text=True)
    if out.returncode != 0 or not out.stdout.strip():
        return None
    name, memory = [part.strip() for part in out.stdout.strip().splitlines()[0].split(",")]
    return name, int(memory)


def requirements_table(need_prepare, need_train):
    rows = []
    for module, package in (("numpy", "numpy"), ("scipy", "scipy"), ("cv2", "opencv-python"), ("PIL", "Pillow")):
        ok = module_present(module)
        rows.append((f"python package {package}", ok, True, "pip install -r requirements.txt"))
    ffmpeg = tool_path("ffmpeg", [r"%LOCALAPPDATA%\Microsoft\WinGet\Packages\Gyan.FFmpeg*\*\bin\ffmpeg.exe"])
    ffprobe = tool_path("ffprobe", [r"%LOCALAPPDATA%\Microsoft\WinGet\Packages\Gyan.FFmpeg*\*\bin\ffprobe.exe"])
    colmap = tool_path("colmap")
    rows.append(("ffmpeg and ffprobe", bool(ffmpeg and ffprobe), need_prepare, "install ffmpeg and put it on PATH"))
    rows.append(("COLMAP", bool(colmap), need_prepare, "install COLMAP 3.9 or newer and put it on PATH"))
    gpu = gpu_info()
    if gpu is None:
        rows.append(("NVIDIA GPU (nvidia-smi)", False, need_train, "needs an NVIDIA GPU with a working driver"))
    else:
        enough = gpu[1] >= MIN_GPU_MIB
        rows.append((f"GPU memory, {gpu[0]} has {gpu[1]} MiB, want {MIN_GPU_MIB}+", enough, need_train, "use a GPU with 16 GB or more, or pass --allow-small-gpu to try anyway"))
    rows.append(("ns-train and ns-export (nerfstudio)", bool(shutil.which("ns-train") and shutil.which("ns-export")), need_train, "pip install -r requirements-train.txt after PyTorch for your CUDA"))
    rows.append(("bash (Linux, macOS or WSL2)", platform.system() != "Windows", need_train, "run inside WSL2 on Windows"))
    free_gb = shutil.disk_usage(REPO).free / 1e9
    want_gb = MIN_DISK_GB if (need_prepare or need_train) else 3
    rows.append((f"free disk {free_gb:.0f} GB, want {want_gb}+", free_gb >= want_gb, True, "free some disk space"))
    return rows


def run_preflight(need_prepare, need_train, allow_small_gpu):
    banner("CHECKING REQUIREMENTS")
    rows = requirements_table(need_prepare, need_train)
    blocked = []
    for label, ok, required, hint in rows:
        if ok:
            state = "ok"
        elif not required:
            state = "not needed for this run"
        elif allow_small_gpu and label.startswith("GPU memory"):
            state = "too small, continuing because of --allow-small-gpu"
        else:
            state = "MISSING"
            blocked.append((label, hint))
        print(f"  {label:<58} {state}")
    if blocked:
        print("")
        for label, hint in blocked:
            print(f"  fix: {label} -> {hint}")
        raise Problem("some requirements are missing. See docs/HARDWARE_AND_REMOTE_SETUP.md for the full list.")
    print("\n  all requirements met")


def run_checked(command, cwd, label):
    print(f"\n$ {' '.join(command)}\n", flush=True)
    result = subprocess.run(command, cwd=cwd)
    if result.returncode != 0:
        raise Problem(f"{label} failed with exit code {result.returncode}")


def newest(pattern):
    matches = glob.glob(pattern)
    return max(matches, key=os.path.getmtime) if matches else None


def unpack(zip_path, destination):
    if os.path.isdir(destination):
        shutil.rmtree(destination)
    os.makedirs(destination)
    with zipfile.ZipFile(zip_path) as archive:
        archive.extractall(destination)
        top = {name.split("/")[0] for name in archive.namelist() if name.strip("/")}
    if len(top) != 1:
        raise Problem(f"{zip_path} does not have a single top folder")
    return os.path.join(destination, top.pop())


def stage_prepare(arguments):
    command = [sys.executable, os.path.join(SCRIPTS, "step1_prepare.py"), "--video", arguments.video]
    if arguments.name:
        command += ["--name", arguments.name]
    command += ["--camera-height", str(arguments.camera_height)]
    if arguments.window is not None:
        command += ["--window", str(arguments.window)]
    started = time.time()
    run_checked(command, PIPELINE, "STEP 1 (prepare)")
    bundle = newest(os.path.join(OUTBOX, "*_to_remote.zip"))
    if not bundle or os.path.getmtime(bundle) < started:
        raise Problem("STEP 1 finished but no new bundle zip was written to namma_pipeline/2_SEND_TO_REMOTE")
    return bundle


def stage_train(bundle, iterations, downscale, cache, profile):
    scene_dir = os.path.join(RUNS, "_train")
    top = unpack(bundle, scene_dir)
    scene = json.load(open(os.path.join(top, "scene.json")))["scene"]
    destination = os.path.join(RUNS, scene, "train")
    if os.path.isdir(destination):
        shutil.rmtree(destination)
    os.makedirs(os.path.dirname(destination), exist_ok=True)
    shutil.move(top, destination)
    shutil.rmtree(scene_dir, ignore_errors=True)
    run_checked(["bash", "scripts/STEP2_train_on_remote.sh", str(iterations), str(downscale), cache, profile], destination, "STEP 2 (training)")
    result = newest(os.path.join(destination, "results", "*_result.zip"))
    if not result:
        raise Problem("training finished but no result zip was written")
    return scene, result


def install_sample():
    if not os.path.isfile(SAMPLE_ZIP):
        raise Problem(f"test sample not found at {SAMPLE_ZIP}")
    work = os.path.join(RUNS, "_sample")
    root = unpack(SAMPLE_ZIP, work)
    scene = json.load(open(os.path.join(root, "scene.json")))["scene"]
    run_dir = os.path.join(RUNS, scene)
    for part in ("world", "colmap"):
        target = os.path.join(run_dir, part)
        if os.path.isdir(target):
            shutil.rmtree(target)
        os.makedirs(run_dir, exist_ok=True)
        shutil.copytree(os.path.join(root, "step1", part), target)
    bundle = os.path.join(root, "bundle")
    shutil.copyfile(os.path.join(root, "scene.json"), os.path.join(bundle, "scene.json"))
    for script in glob.glob(os.path.join(PIPELINE, "remote", "*.sh")):
        os.makedirs(os.path.join(bundle, "scripts"), exist_ok=True)
        shutil.copyfile(script, os.path.join(bundle, "scripts", os.path.basename(script)))
    destination = os.path.join(run_dir, "train")
    if os.path.isdir(destination):
        shutil.rmtree(destination)
    shutil.move(bundle, destination)
    shutil.rmtree(work, ignore_errors=True)
    return scene, destination


def stage_finish(result, title, no_serve):
    command = [sys.executable, os.path.join(SCRIPTS, "step3_finish.py"), "--result", result]
    if title:
        command += ["--title", title]
    if no_serve:
        command += ["--no-serve"]
    run_checked(command, PIPELINE, "STEP 3 (finish)")


def main():
    parser = argparse.ArgumentParser(description="NammaSpace on one computer: phone video to a walkable 3D scene in the browser.")
    parser.add_argument("--video", help="phone video of the room (mp4, mov, mkv)")
    parser.add_argument("--name", help="scene name (default: the video file name)")
    parser.add_argument("--test", action="store_true", help="run the bundled sample scene with a short training, no video needed")
    parser.add_argument("--check", action="store_true", help="only check the requirements and stop")
    parser.add_argument("--finish-only", metavar="RESULT_ZIP", help="skip steps 1 and 2: build the website from an existing result zip (no GPU needed, needs the matching STEP 1 data in namma_pipeline/runs)")
    parser.add_argument("--steps", type=int, help="training steps (default 30000, or 1000 with --test)")
    parser.add_argument("--profile", default="default", choices=["default", "scalereg", "quality"], help="training profile")
    parser.add_argument("--downscale", type=int, default=1, help="1 = full size images, 2 = half size (less GPU memory)")
    parser.add_argument("--cache", default="gpu", choices=["gpu", "cpu"], help="where to keep training images; cpu uses less GPU memory")
    parser.add_argument("--camera-height", type=float, default=1.4, help="phone height above the floor in metres")
    parser.add_argument("--window", type=float, help="seconds per frame window in the sharp-frame picker (1 = half as many frames, much faster COLMAP)")
    parser.add_argument("--allow-small-gpu", action="store_true", help="continue even if the GPU has less than 16 GB")
    parser.add_argument("--no-serve", action="store_true", help="build the website but do not start the local server")
    parser.add_argument("--title", help="title shown on the website")
    arguments = parser.parse_args()

    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    started = time.time()
    try:
        if arguments.check:
            run_preflight(need_prepare=True, need_train=True, allow_small_gpu=arguments.allow_small_gpu)
            return
        if arguments.finish_only:
            run_preflight(need_prepare=False, need_train=False, allow_small_gpu=True)
            stage_finish(arguments.finish_only, arguments.title, arguments.no_serve)
            return
        if arguments.test:
            run_preflight(need_prepare=False, need_train=True, allow_small_gpu=arguments.allow_small_gpu)
            banner("STEP 1 of 3: using the bundled sample (frames, camera model and collision map are ready)")
            scene, train_dir = install_sample()
            iterations = arguments.steps or 1000
        else:
            if not arguments.video:
                parser.error("give a video with --video, or use --test for the sample, or --check to test the machine")
            if not os.path.isfile(arguments.video):
                raise Problem(f"video not found: {arguments.video}")
            run_preflight(need_prepare=True, need_train=True, allow_small_gpu=arguments.allow_small_gpu)
            banner("STEP 1 of 3: prepare (frames, COLMAP, floor and collision map)")
            bundle = stage_prepare(arguments)
            iterations = arguments.steps or 30000
            scene = None
        banner(f"STEP 2 of 3: train the 3D Gaussian splat ({iterations} steps)")
        if arguments.test:
            run_checked(["bash", "scripts/STEP2_train_on_remote.sh", str(iterations), str(arguments.downscale), arguments.cache, arguments.profile], train_dir, "STEP 2 (training)")
            result = newest(os.path.join(train_dir, "results", "*_result.zip"))
            if not result:
                raise Problem("training finished but no result zip was written")
        else:
            scene, result = stage_train(bundle, iterations, arguments.downscale, arguments.cache, arguments.profile)
        banner("STEP 3 of 3: align, clean and build the website")
        stage_finish(result, arguments.title, arguments.no_serve)
    except Problem as problem:
        print(f"\n STOPPED: {problem}")
        sys.exit(1)
    finally:
        print(f"\n total time {int(time.time() - started)} s")


if __name__ == "__main__":
    main()
