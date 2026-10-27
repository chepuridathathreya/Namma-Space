import argparse
import glob
import json
import os
import subprocess
import sys
import tempfile
import time

import cv2
import numpy as np

SCORE_WIDTH = 640
MIN_BRIGHTNESS = 25
MAX_BRIGHTNESS = 240
CANDIDATE_START = 0.2
CANDIDATE_END = 0.8
GATE_FRACTION = 0.12


def score_all_frames(ffmpeg, video, width, height):
    scaled_height = 2 * int(round(height * SCORE_WIDTH / width / 2))
    command = [
        ffmpeg, "-v", "error", "-i", video, "-fps_mode", "passthrough",
        "-vf", f"scale={SCORE_WIDTH}:{scaled_height},format=gray", "-f", "rawvideo", "-pix_fmt", "gray", "-",
    ]
    process = subprocess.Popen(command, stdout=subprocess.PIPE)
    frame_bytes = SCORE_WIDTH * scaled_height
    sharpness, brightness = [], []
    started = time.time()
    while True:
        raw = process.stdout.read(frame_bytes)
        if len(raw) < frame_bytes:
            break
        frame = np.frombuffer(raw, np.uint8).reshape(scaled_height, SCORE_WIDTH)
        sharpness.append(float(cv2.Laplacian(frame, cv2.CV_64F).var()))
        brightness.append(float(frame.mean()))
        if len(sharpness) % 3000 == 0:
            print(f"   scored {len(sharpness):,} frames ({time.time() - started:.0f}s)", flush=True)
    process.wait()
    if process.returncode != 0 or not sharpness:
        raise RuntimeError("ffmpeg could not decode the video")
    return np.array(sharpness), np.array(brightness)


def choose_frames(sharpness, brightness, fps, window_seconds):
    window = max(1, int(round(fps * window_seconds)))
    picks, baseline = [], []
    for start in range(0, len(sharpness), window):
        low = start + int(CANDIDATE_START * window)
        high = min(len(sharpness), start + int(CANDIDATE_END * window) + 1)
        indices = np.arange(low, high)
        indices = indices[(brightness[indices] >= MIN_BRIGHTNESS) & (brightness[indices] <= MAX_BRIGHTNESS)]
        baseline.append(sharpness[start])
        if len(indices):
            picks.append(int(indices[np.argmax(sharpness[indices])]))
    best_scores = sharpness[picks]
    gate = GATE_FRACTION * float(np.median(best_scores))
    kept = [i for i in picks if sharpness[i] >= gate]
    return kept, len(picks) - len(kept), np.array(baseline), gate, window


def balanced_sum(terms):
    if len(terms) == 1:
        return terms[0]
    middle = len(terms) // 2
    return "(" + balanced_sum(terms[:middle]) + "+" + balanced_sum(terms[middle:]) + ")"


def extract_frames(ffmpeg, video, indices, out_dir, max_width, quality):
    os.makedirs(out_dir, exist_ok=True)
    expression = balanced_sum([f"eq(n,{i})" for i in indices])
    script = f"select='{expression}',scale='min({max_width},iw)':-2"
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as handle:
        handle.write(script)
        script_path = handle.name
    command = [
        ffmpeg, "-v", "error", "-stats", "-y", "-i", video, "-fps_mode", "passthrough",
        "-/filter:v", script_path, "-qscale:v", str(quality), os.path.join(out_dir, "frame_%04d.jpg"),
    ]
    result = subprocess.run(command)
    os.remove(script_path)
    if result.returncode != 0:
        raise RuntimeError("ffmpeg could not extract the chosen frames")


def alignment_correlation(sharpness, indices, written):
    positions = np.linspace(0, len(indices) - 1, min(30, len(indices))).astype(int)
    stored, measured = [], []
    for k in positions:
        gray = cv2.imread(written[k], cv2.IMREAD_GRAYSCALE)
        height = gray.shape[0] * SCORE_WIDTH // gray.shape[1]
        small = cv2.resize(gray, (SCORE_WIDTH, height), interpolation=cv2.INTER_AREA)
        measured.append(cv2.Laplacian(small, cv2.CV_64F).var())
        stored.append(sharpness[indices[k]])
    return float(np.corrcoef(stored, measured)[0, 1])


def select_frames(ffmpeg, video, out_dir, width, height, fps, window_seconds=0.5, max_width=1920, quality=2):
    started = time.time()
    print(f"   scoring every frame of the video for sharpness (at {SCORE_WIDTH}px wide, native {fps:g} fps)", flush=True)
    sharpness, brightness = score_all_frames(ffmpeg, video, width, height)
    print(f"   scored {len(sharpness):,} frames in {time.time() - started:.0f}s", flush=True)
    kept, gated, baseline, gate, window = choose_frames(sharpness, brightness, fps, window_seconds)
    if len(kept) < 30:
        raise RuntimeError(f"only {len(kept)} usable frames. The video is too short, too dark or too blurry.")
    print(f"   one frame per {window_seconds:g} s window: picked the sharpest of the middle {int((CANDIDATE_END - CANDIDATE_START) * window)} frames of each window")
    print(f"   windows with no sharp frame left out: {gated} (sharpness below {gate:.0f})")
    picked = float(np.median(sharpness[kept]))
    fixed = float(np.median(baseline))
    print(f"   median sharpness: picked {picked:.0f} vs fixed-rate picking {fixed:.0f} ({(picked / fixed - 1) * 100:+.0f}%)")
    print(f"   extracting {len(kept)} frames at up to {max_width}px wide", flush=True)
    extract_frames(ffmpeg, video, kept, out_dir, max_width, quality)
    written = sorted(glob.glob(os.path.join(out_dir, "frame_*.jpg")))
    if len(written) != len(kept):
        raise RuntimeError(f"expected {len(kept)} frames but {len(written)} were written")
    correlation = alignment_correlation(sharpness, kept, written)
    print(f"   alignment check: extracted frames match the scored frames (correlation {correlation:.2f})")
    if correlation < 0.9:
        raise RuntimeError(f"the extracted frames do not match the frames that were scored (correlation {correlation:.2f}); the video may have variable frame timing")
    log = {
        "video": os.path.basename(video), "native_fps": fps, "window_seconds": window_seconds, "frames_in_video": int(len(sharpness)),
        "frames_picked": len(kept), "windows_left_out": gated,
        "median_sharpness_picked": picked, "median_sharpness_fixed_rate": fixed,
        "picked_times_seconds": [round(i / fps, 2) for i in kept],
    }
    json.dump(log, open(os.path.join(out_dir, "..", "frame_selection.json"), "w"), indent=1)
    return len(written)


def main():
    parser = argparse.ArgumentParser(description="Pick the sharpest frame of every short time window of a video")
    parser.add_argument("video")
    parser.add_argument("out_dir")
    parser.add_argument("--window", type=float, default=0.5, help="seconds per window; one frame is picked from each")
    parser.add_argument("--max-width", type=int, default=1920)
    args = parser.parse_args()
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from step1_prepare import find_tool, probe_video
    ffmpeg = find_tool("ffmpeg", [r"%LOCALAPPDATA%\Microsoft\WinGet\Packages\Gyan.FFmpeg*\*\bin\ffmpeg.exe"])
    ffprobe = find_tool("ffprobe", [r"%LOCALAPPDATA%\Microsoft\WinGet\Packages\Gyan.FFmpeg*\*\bin\ffprobe.exe"])
    info = probe_video(ffprobe, args.video)
    count = select_frames(ffmpeg, args.video, args.out_dir, info["width"], info["height"], info["fps"], args.window, args.max_width)
    print(f"   done: {count} frames in {args.out_dir}")


if __name__ == "__main__":
    main()
