import argparse
import glob
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import time
import zipfile
from datetime import datetime

import cv2
import numpy as np
from PIL import Image, ImageOps

PIPELINE_ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
SCRIPTS_DIR = os.path.join(PIPELINE_ROOT, "scripts")
REMOTE_DIR = os.path.join(PIPELINE_ROOT, "remote")
VIDEO_EXTENSIONS = (".mp4", ".mov", ".mkv", ".avi", ".m4v")
STORED_EXTENSIONS = (".jpg", ".jpeg", ".png")
PHOTO_EXTENSIONS = (".jpg", ".jpeg", ".png", ".heic")
PHOTOS_INBOX = os.path.join(PIPELINE_ROOT, "1b_PUT_EXTRA_PHOTOS_HERE")

sys.path.insert(0, SCRIPTS_DIR)
from build_collision_from_colmap import read_images
from pipeline_common import Stages, StopPipeline, Tee, format_seconds, run_live
from select_sharp_frames import select_frames


def find_tool(name, candidate_patterns):
    found = shutil.which(name)
    if found:
        return found
    for pattern in candidate_patterns:
        matches = sorted(glob.glob(os.path.expandvars(pattern)))
        if matches:
            return matches[-1]
    raise StopPipeline(f"could not find '{name}'. Install it or add it to PATH.")


def probe_video(ffprobe, video):
    out = subprocess.run(
        [ffprobe, "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height,r_frame_rate,nb_frames,codec_name:format=duration", "-of", "json", video],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if out.returncode != 0:
        raise StopPipeline(f"ffprobe could not read the video: {out.stderr.strip()}")
    info = json.loads(out.stdout)
    stream = info["streams"][0]
    numerator, denominator = stream["r_frame_rate"].split("/")
    return {
        "width": int(stream["width"]),
        "height": int(stream["height"]),
        "fps": round(int(numerator) / max(int(denominator), 1), 2),
        "duration_s": round(float(info["format"]["duration"]), 1),
        "codec": stream.get("codec_name", "?"),
    }


def newest_video(folder):
    videos = [os.path.join(folder, f) for f in os.listdir(folder) if f.lower().endswith(VIDEO_EXTENSIONS)]
    if not videos:
        raise StopPipeline(f"no video found in {folder}. Put your phone video there and run again.")
    return max(videos, key=os.path.getmtime)


def count_header(path):
    with open(path, "rb") as handle:
        return struct.unpack("<Q", handle.read(8))[0]


def check_colour(frame_paths):
    sample = frame_paths[:: max(1, len(frame_paths) // 10)][:10]
    spreads = []
    for path in sample:
        pixels = np.asarray(Image.open(path).convert("RGB"), dtype=np.int16)[::8, ::8]
        spreads.append(float(np.abs(pixels[..., 0] - pixels[..., 2]).mean()))
    average = sum(spreads) / len(spreads)
    print(f"   colour check: average red-vs-blue difference {average:.1f} (a grayscale image gives 0.0)")
    if average < 1.0:
        raise StopPipeline("the frames are grayscale. Training on them would give a grey 3D scene. Check the video and the extraction settings.")


def stage_check_inputs(context):
    arguments = context["args"]
    context["ffmpeg"] = find_tool("ffmpeg", [r"%LOCALAPPDATA%\Microsoft\WinGet\Packages\Gyan.FFmpeg*\*\bin\ffmpeg.exe"])
    context["ffprobe"] = find_tool("ffprobe", [r"%LOCALAPPDATA%\Microsoft\WinGet\Packages\Gyan.FFmpeg*\*\bin\ffprobe.exe"])
    direct_exe = r"D:\Tools\COLMAP\bin\colmap.exe"
    context["colmap"] = direct_exe if os.path.isfile(direct_exe) else find_tool("colmap", [])
    print(f"   ffmpeg : {context['ffmpeg']}")
    print(f"   colmap : {context['colmap']}")
    video = arguments.video or newest_video(os.path.join(PIPELINE_ROOT, "1_PUT_VIDEO_HERE"))
    if not os.path.isfile(video):
        raise StopPipeline(f"video not found: {video}")
    context["video"] = video
    info = probe_video(context["ffprobe"], video)
    context["video_info"] = info
    print(f"   video  : {video}")
    print(f"   size   : {info['width']}x{info['height']} at {info['fps']} fps, {info['duration_s']} s, codec {info['codec']}")
    if info["height"] < 1080 and info["width"] < 1920:
        print("   WARNING: video is below 1080p. The 3D scene will look softer.")
    if info["duration_s"] > 900:
        print("   WARNING: video is longer than 15 minutes. COLMAP will take a long time.")
    gpu = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"], capture_output=True, text=True)
    print(f"   GPU    : {gpu.stdout.strip() or 'nvidia-smi not available'}")
    name = arguments.name or re.sub(r"[^A-Za-z0-9_]+", "_", os.path.splitext(os.path.basename(video))[0]).strip("_").lower()
    runs_root = os.path.join(PIPELINE_ROOT, "runs")
    run_dir, suffix = os.path.join(runs_root, name), 1
    while os.path.exists(run_dir):
        suffix += 1
        run_dir = os.path.join(runs_root, f"{name}_{suffix}")
    context["name"] = os.path.basename(run_dir)
    context["run_dir"] = run_dir
    print(f"   scene  : {context['name']}")
    print(f"   folder : {run_dir}")


def stage_extract_frames(context):
    frames_dir = os.path.join(context["run_dir"], "frames")
    os.makedirs(frames_dir, exist_ok=True)
    fps = context["args"].fps
    command = [
        context["ffmpeg"], "-v", "error", "-stats", "-y", "-i", context["video"],
        "-vf", f"fps={fps},scale='min(1920,iw)':-2", "-qscale:v", "2",
        os.path.join(frames_dir, "frame_%04d.jpg"),
    ]
    run_live(command, "ffmpeg")
    frames = sorted(glob.glob(os.path.join(frames_dir, "*.jpg")))
    if len(frames) < 30:
        raise StopPipeline(f"only {len(frames)} frames were extracted. The video is too short or unreadable.")
    context["frames_dir"] = frames_dir
    print(f"   extracted {len(frames)} colour frames at {fps} per second")
    check_colour(frames)


def stage_pick_sharp_frames(context):
    frames_dir = os.path.join(context["run_dir"], "frames")
    info = context["video_info"]
    arguments = context["args"]
    try:
        count = select_frames(context["ffmpeg"], context["video"], frames_dir, info["width"], info["height"], info["fps"], arguments.window, arguments.max_width)
    except RuntimeError as problem:
        raise StopPipeline(str(problem))
    context["frames_dir"] = frames_dir
    context["kept_frames"] = count
    check_colour(sorted(glob.glob(os.path.join(frames_dir, "*.jpg"))))


def stage_add_photos(context):
    folder = context["args"].photos or PHOTOS_INBOX
    sources = sorted(f for f in glob.glob(os.path.join(folder, "*")) if f.lower().endswith(PHOTO_EXTENSIONS))
    context["photo_groups"] = {}
    if not sources:
        print(f"   no extra photos in {folder} (optional), continuing with video frames only")
        return
    max_width = context["args"].max_width
    groups = context["photo_groups"]
    portrait = 0
    for index, source in enumerate(sources, 1):
        try:
            with Image.open(source) as opened:
                image = ImageOps.exif_transpose(opened).convert("RGB")
        except OSError as problem:
            print(f"   skipped {os.path.basename(source)}: {problem}")
            continue
        if image.height > image.width:
            portrait += 1
        longest = max(image.width, image.height)
        if longest > max_width:
            factor = max_width / longest
            image = image.resize((round(image.width * factor), round(image.height * factor)), Image.LANCZOS)
        name = f"photo_{index:03d}.jpg"
        image.save(os.path.join(context["frames_dir"], name), quality=95)
        groups.setdefault(image.size, []).append(name)
    count = sum(len(names) for names in groups.values())
    if count == 0:
        return
    context["kept_frames"] += count
    sizes = ", ".join(f"{len(names)} at {w}x{h}" for (w, h), names in groups.items())
    print(f"   added {count} extra photos from {folder} ({sizes})")
    print("   each photo size gets its own camera in COLMAP; photos are matched against every video frame")
    if portrait:
        print(f"   NOTE: {portrait} photos are portrait. Landscape photos at the 1x lens match the video best.")
    check_colour([os.path.join(context["frames_dir"], n) for names in groups.values() for n in names])


def stage_clean_frames(context):
    frames_dir = context["frames_dir"]
    rejected_dir = os.path.join(context["run_dir"], "frames_rejected")
    os.makedirs(rejected_dir, exist_ok=True)
    threshold = context["args"].blur_threshold
    frames = sorted(glob.glob(os.path.join(frames_dir, "*.jpg")))
    blurry, duplicates = [], []
    previous_thumbnail = None
    scores = []
    for index, path in enumerate(frames, 1):
        gray = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
        score = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        scores.append(score)
        thumbnail = cv2.resize(gray, (64, 36), interpolation=cv2.INTER_AREA).astype(np.float32)
        if score < threshold:
            blurry.append(path)
        elif previous_thumbnail is not None and float(np.abs(thumbnail - previous_thumbnail).mean()) < 0.8:
            duplicates.append(path)
        else:
            previous_thumbnail = thumbnail
        if index % 100 == 0 or index == len(frames):
            print(f"   scored {index}/{len(frames)} frames", flush=True)
    for path in blurry + duplicates:
        shutil.move(path, os.path.join(rejected_dir, os.path.basename(path)))
    kept = len(frames) - len(blurry) - len(duplicates)
    print(f"   sharpness (Laplacian variance): median {np.median(scores):.0f}, threshold {threshold:.0f}")
    print(f"   kept {kept} frames | rejected {len(blurry)} blurry, {len(duplicates)} near-duplicate (moved to frames_rejected/)")
    if kept < 30:
        raise StopPipeline(f"only {kept} sharp frames left. The video is too blurry or you stood still.")
    context["kept_frames"] = kept


def stage_colmap(context):
    colmap_dir = os.path.join(context["run_dir"], "colmap")
    sparse_dir = os.path.join(colmap_dir, "sparse")
    os.makedirs(sparse_dir, exist_ok=True)
    database = os.path.join(colmap_dir, "database.db")
    colmap = context["colmap"]
    timings = []

    def timed(label, command):
        begin = time.time()
        print(f"\n   --- COLMAP: {label} ---", flush=True)
        run_live(command, f"COLMAP {label}")
        timings.append((label, time.time() - begin))
        print(f"   --- {label} took {format_seconds(timings[-1][1])} ---", flush=True)

    extract = [
        colmap, "feature_extractor", "--database_path", database, "--image_path", context["frames_dir"],
        "--ImageReader.camera_model", "SIMPLE_RADIAL", "--ImageReader.single_camera", "1", "--FeatureExtraction.use_gpu", "1",
    ]
    groups = context.get("photo_groups", {})
    if groups:
        photo_names = {n for names in groups.values() for n in names}
        video_names = sorted(f for f in os.listdir(context["frames_dir"]) if f.lower().endswith(".jpg") and f not in photo_names)
        lists = [("video frames", video_names)] + [(f"photos {w}x{h}", names) for (w, h), names in groups.items()]
        for label, names in lists:
            list_path = os.path.join(colmap_dir, f"list_{label.replace(' ', '_')}.txt")
            open(list_path, "w").write("\n".join(names) + "\n")
            timed(f"1/3 feature extraction, {label} (finds corners in every image)", extract + ["--image_list_path", list_path])
    else:
        timed("1/3 feature extraction (finds corners in every frame)", extract)
    timed("2/3 matching (links frames that see the same things)", [
        colmap, "sequential_matcher", "--database_path", database,
        "--SequentialMatching.overlap", "10", "--SequentialMatching.quadratic_overlap", "1", "--FeatureMatching.use_gpu", "1",
    ])
    if groups:
        photos = sorted(photo_names)
        pairs = [f"{p} {v}" for p in photos for v in video_names]
        pairs += [f"{a} {b}" for i, a in enumerate(photos) for b in photos[i + 1:]]
        pairs_path = os.path.join(colmap_dir, "photo_pairs.txt")
        open(pairs_path, "w").write("\n".join(pairs) + "\n")
        timed(f"2b/3 matching every photo against every video frame ({len(pairs):,} pairs)", [
            colmap, "matches_importer", "--database_path", database, "--match_list_path", pairs_path,
            "--match_type", "pairs", "--FeatureMatching.use_gpu", "1",
        ])
    if context["args"].global_mapper:
        timed("3/3 global mapper (solves every camera position at once, faster)", [
            colmap, "global_mapper", "--database_path", database, "--image_path", context["frames_dir"], "--output_path", sparse_dir,
        ])
    else:
        timed("3/3 mapper (solves camera positions and the 3D points)", [
            colmap, "mapper", "--database_path", database, "--image_path", context["frames_dir"], "--output_path", sparse_dir,
        ])
    context["sparse_dir"] = sparse_dir


def stage_health_check(context):
    models = []
    for model_dir in sorted(glob.glob(os.path.join(context["sparse_dir"], "*"))):
        if os.path.isfile(os.path.join(model_dir, "images.bin")):
            models.append((count_header(os.path.join(model_dir, "images.bin")), count_header(os.path.join(model_dir, "points3D.bin")), model_dir))
    if not models:
        raise StopPipeline("COLMAP produced no 3D model at all. The frames probably do not overlap enough.")
    models.sort(reverse=True)
    for registered, points, model_dir in models:
        print(f"   model {os.path.basename(model_dir)}: {registered} frames placed, {points:,} 3D points")
    registered, points, best_dir = models[0]
    total = context["kept_frames"]
    share = registered / total
    print(f"   BEST model: {os.path.basename(best_dir)} with {registered} of {total} frames placed ({share * 100:.0f}%), {points:,} points")
    if share < 0.4:
        raise StopPipeline(f"only {share * 100:.0f}% of frames were placed. The capture likely has breaks or too fast turns. Re-shoot slowly with overlap.")
    if share < 0.8:
        print("   WARNING: fewer than 80% of frames were placed. Expect gaps or bending in the 3D scene.")
    if len(models) > 1 and models[1][0] > 0.15 * total:
        print(f"   WARNING: a second large model ({models[1][0]} frames) exists. The walk split into separate pieces; only the biggest is used.")
    if points < 20000:
        print("   WARNING: very few 3D points. The scene may look sparse.")
    best_copy = os.path.join(context["run_dir"], "colmap", "best")
    os.makedirs(best_copy, exist_ok=True)
    for name in ("cameras.bin", "images.bin", "points3D.bin"):
        shutil.copyfile(os.path.join(best_dir, name), os.path.join(best_copy, name))
    maximum = context["args"].max_frames
    if maximum and registered > maximum:
        names = sorted(read_images(os.path.join(best_copy, "images.bin"))[0])
        picked = [names[int(i * len(names) / maximum)] for i in range(maximum)]
        keep_file = os.path.join(context["run_dir"], "colmap", "keep_frames.txt")
        open(keep_file, "w").write("\n".join(picked))
        thinned = os.path.join(context["run_dir"], "colmap", "best_thinned")
        run_live([sys.executable, os.path.join(SCRIPTS_DIR, "subset_colmap.py"), best_copy, thinned, keep_file], "subset_colmap")
        for extra in ("frames.bin", "rigs.bin"):
            leftover = os.path.join(thinned, extra)
            if os.path.exists(leftover):
                os.remove(leftover)
        best_copy = thinned
        print(f"   thinned to {maximum} evenly spaced frames, as requested with --max-frames")
    photos_in = sum(len(n) for n in context.get("photo_groups", {}).values())
    if photos_in:
        placed = sum(1 for n in read_images(os.path.join(best_copy, "images.bin"))[0] if n.startswith("photo_"))
        context["photos_placed"] = placed
        print(f"   extra photos placed: {placed} of {photos_in}")
        if placed < photos_in:
            print("   (a photo that shares too little with the video is simply left out; that is harmless)")
    context["best_dir"] = best_copy
    context["registered"] = registered
    context["points"] = points


def stage_world_and_collision(context):
    world_dir = os.path.join(context["run_dir"], "world")
    run_live([
        sys.executable, os.path.join(SCRIPTS_DIR, "build_collision_from_colmap.py"),
        "--sparse", context["best_dir"], "--out", world_dir, "--name", context["name"],
        "--camera-height", str(context["args"].camera_height),
    ], "collision map")
    context["world_dir"] = world_dir


def pack_zip(zip_path, source_root, top_name):
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=3) as archive:
        for folder, _, files in os.walk(source_root):
            for file_name in files:
                full = os.path.join(folder, file_name)
                arcname = top_name + "/" + os.path.relpath(full, source_root).replace(os.sep, "/")
                kind = zipfile.ZIP_STORED if file_name.lower().endswith(STORED_EXTENSIONS) else zipfile.ZIP_DEFLATED
                archive.write(full, arcname, compress_type=kind)
    with zipfile.ZipFile(zip_path) as archive:
        if archive.testzip() is not None:
            raise StopPipeline("the zip file failed its integrity check")


def stage_pack_for_remote(context):
    name = context["name"]
    stage_root = os.path.join(context["run_dir"], "bundle", f"{name}_to_remote")
    if os.path.exists(stage_root):
        shutil.rmtree(stage_root)
    dataset = os.path.join(stage_root, "dataset")
    images_full = os.path.join(dataset, "images")
    images_half = os.path.join(dataset, "images_2")
    sparse_target = os.path.join(dataset, "colmap", "sparse", "0")
    for folder in (images_full, images_half, sparse_target, os.path.join(stage_root, "scripts")):
        os.makedirs(folder, exist_ok=True)
    names = read_images(os.path.join(context["best_dir"], "images.bin"))[0]
    for index, frame_name in enumerate(names, 1):
        source = os.path.join(context["frames_dir"], frame_name)
        shutil.copyfile(source, os.path.join(images_full, frame_name))
        with Image.open(source) as image:
            half = image.resize((image.width // 2, image.height // 2), Image.LANCZOS)
            half.save(os.path.join(images_half, frame_name), quality=92)
        if index % 100 == 0 or index == len(names):
            print(f"   prepared {index}/{len(names)} frames (full size + half size)", flush=True)
    for file_name in ("cameras.bin", "images.bin", "points3D.bin"):
        shutil.copyfile(os.path.join(context["best_dir"], file_name), os.path.join(sparse_target, file_name))
    info = context["video_info"]
    scene = {
        "scene": name,
        "frames": len(names),
        "points": context["points"],
        "photos": context.get("photos_placed", 0),
        "video": os.path.basename(context["video"]),
        "video_size": f"{info['width']}x{info['height']}",
        "created": datetime.now().isoformat(timespec="seconds"),
    }
    json.dump(scene, open(os.path.join(stage_root, "scene.json"), "w"), indent=2)
    shutil.copyfile(os.path.join(REMOTE_DIR, "CLAUDE.md"), os.path.join(stage_root, "CLAUDE.md"))
    for script in glob.glob(os.path.join(REMOTE_DIR, "*.sh")):
        shutil.copyfile(script, os.path.join(stage_root, "scripts", os.path.basename(script)))
    zip_name = f"{name}_to_remote.zip"
    run_zip = os.path.join(context["run_dir"], "bundle", zip_name)
    print(f"   zipping {len(names)} frames + camera model ...", flush=True)
    pack_zip(run_zip, stage_root, f"{name}_to_remote")
    outbox = os.path.join(PIPELINE_ROOT, "2_SEND_TO_REMOTE")
    os.makedirs(outbox, exist_ok=True)
    final_zip = os.path.join(outbox, zip_name)
    shutil.copyfile(run_zip, final_zip)
    context["final_zip"] = final_zip
    print(f"   zip size: {os.path.getsize(final_zip) / 1e6:.0f} MB")


def main():
    parser = argparse.ArgumentParser(description="NammaSpace STEP 1: video -> frames -> COLMAP -> collision map -> zip for the remote GPU PC")
    parser.add_argument("--video", help="video file (default: newest video in 1_PUT_VIDEO_HERE)")
    parser.add_argument("--name", help="scene name (default: the video file name)")
    parser.add_argument("--fps", type=float, default=2.0, help="frames per second to extract")
    parser.add_argument("--window", type=float, default=0.5, help="seconds per window; the sharpest frame of each window is kept (1 = half as many frames, much faster COLMAP)")
    parser.add_argument("--max-width", type=int, default=1920, help="frames are scaled down to this width")
    parser.add_argument("--classic-frames", action="store_true", help="use the old fixed-rate extraction with --fps instead of the sharpest-frame picker")
    parser.add_argument("--blur-threshold", type=float, default=35.0)
    parser.add_argument("--max-frames", type=int, default=0, help="0 = keep every placed frame (best quality)")
    parser.add_argument("--camera-height", type=float, default=1.4, help="phone height above the floor in metres")
    parser.add_argument("--photos", help="folder of extra photos to add (default: 1b_PUT_EXTRA_PHOTOS_HERE, used only if it has photos)")
    parser.add_argument("--global-mapper", action="store_true", help="use COLMAP's global mapper instead of the incremental mapper (faster; test it against the default)")
    arguments = parser.parse_args()

    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    context = {"args": arguments}
    stages = Stages("STEP 1", total=8 if arguments.classic_frames else 7)
    log_handle = None
    try:
        stages.run("check video and tools", lambda: stage_check_inputs(context))
        os.makedirs(os.path.join(context["run_dir"], "logs"), exist_ok=True)
        log_path = os.path.join(context["run_dir"], "logs", "step1.log")
        log_handle = open(log_path, "w", encoding="utf-8")
        sys.stdout = Tee(sys.__stdout__, log_handle)
        print(f"(everything below is also saved to {log_path})")
        if arguments.classic_frames:
            stages.run("extract colour frames", lambda: stage_extract_frames(context))
            stages.run("remove blurry and duplicate frames", lambda: stage_clean_frames(context))
        else:
            stages.run("pick the sharpest colour frame of every time window", lambda: stage_pick_sharp_frames(context))
        stages.run("add extra photos (optional)", lambda: stage_add_photos(context))
        stages.run("COLMAP: camera positions + 3D points", lambda: stage_colmap(context))
        stages.run("health check of the camera model", lambda: stage_health_check(context))
        stages.run("floor, scale and collision map", lambda: stage_world_and_collision(context))
        stages.run("pack zip for the remote GPU PC", lambda: stage_pack_for_remote(context))
    except StopPipeline:
        print(stages.table())
        print("\n RESULT: STOPPED. Fix the problem above and run STEP 1 again.")
        sys.exit(1)
    print(stages.table())
    print("")
    print("=" * 78)
    print(" STEP 1 FINISHED")
    print("=" * 78)
    print(f"  Scene            : {context['name']}")
    print(f"  Frames placed    : {context['registered']} of {context['kept_frames']}")
    print(f"  3D points        : {context['points']:,}")
    print(f"  Collision map    : {context['world_dir']}")
    print(f"  ZIP TO SEND      : {context['final_zip']}")
    print("")
    print("  NEXT: copy that zip to the remote GPU PC, unzip it, and run")
    print("        bash scripts/STEP2_train_on_remote.sh")
    print("        Then bring the result zip back into 3_PUT_REMOTE_RESULT_HERE and run STEP 3.")
    summary = {"scene": context["name"], "seconds": {title: round(seconds, 1) for title, seconds, _ in stages.rows}, "zip": context["final_zip"]}
    json.dump(summary, open(os.path.join(context["run_dir"], "logs", "step1_summary.json"), "w"), indent=2)
    if log_handle:
        sys.stdout = sys.__stdout__
        log_handle.close()


if __name__ == "__main__":
    main()
