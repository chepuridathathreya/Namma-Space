# How Everything Works - a Beginner's Guide

Last updated: 2026-10-15. This guide assumes you know nothing about 3D reconstruction. It explains the idea, every script, every file type, the website, and how the *old* pipeline worked and why it broke. The short plan and round-by-round roadmap are in [00_OVERVIEW_AND_FUTURE_PLAN.md](00_OVERVIEW_AND_FUTURE_PLAN.md).

---

## 1. The big idea in plain words

Imagine you walk through a room filming it. Later, a computer looks at the photos and works out:

1. **Where the camera was** for every photo, and what its lens is like. (This is **COLMAP**.)
2. **A cloud of 3D points** on the walls, floor and furniture, found because the same corner shows up in several photos. (Also COLMAP.)
3. It then **paints the room** with hundreds of thousands of tiny, soft, coloured, see-through blobs ("Gaussians") until the picture from every camera position matches the real photo. This is **3D Gaussian Splatting** and it is the slow, GPU-hungry part. The result is called a **splat**.
4. The splat looks real but is *not solid*. You could walk straight through a wall. So we also build a simple **floor plan** (the collision grid) saying which squares of floor are free and which are blocked.
5. A **web page** draws the splat and uses the floor plan to stop you at walls.

```
 video -> frames -> COLMAP -> camera positions + 3D points
                                     |                 \
                                     v                  v
                           3D Gaussian training      floor plan (collision grid)
                              (GPU, remote PC)              (laptop)
                                     |                       |
                                     +-----------+-----------+
                                                 v
                                      align + clean  ->  website
```

## 2. Words you will meet

| Word | Meaning |
|---|---|
| **Frame** | one still picture taken from the video (we take 2 per second) |
| **Blurry frame** | a frame shot while moving too fast. COLMAP cannot use it, so we drop it |
| **COLMAP** | free program that finds camera positions and 3D points from photos (this is called *Structure from Motion*, SfM) |
| **Sparse model** | COLMAP's output: camera positions plus a few hundred thousand 3D points |
| **Registered frame** | a frame COLMAP managed to place in the model. Frames it could not place are ignored |
| **Gaussian / splat** | one soft coloured blob. A scene is 500,000-800,000 of them |
| **3DGS** | 3D Gaussian Splatting, the training that makes the splat |
| **nerfstudio / splatfacto / gsplat** | the software that does the training (nerfstudio is the toolbox, splatfacto the method, gsplat the GPU code) |
| **Collision grid** | a floor plan made of 10 cm squares: free or blocked |
| **World frame** | the shared measuring system everything ends up in: Y is up, the floor is at height 0, units are metres |
| **.qsplat** | our own compressed splat file that the website reads quickly |
| **Remote GPU PC** | the strong Linux computer that does the training, because the laptop's graphics card (6 GB) and RAM are too small |
| **Hybrid** | splat (looks) + collision grid (rules) together |

## 3. The files you will see, and what is inside

| File | Made by | What it is |
|---|---|---|
| `frame_0001.jpg` ... | ffmpeg | the still pictures, in colour. The number is the order in the video |
| `database.db` | COLMAP | COLMAP's scratch notebook: corners found in every frame and which frames match. Big (up to 1 GB), only useful if COLMAP is run again |
| `cameras.bin` | COLMAP | the camera lens: image size, focal length, lens distortion. One camera for a phone |
| `images.bin` | COLMAP | for every registered frame: its name, its rotation (4 numbers, a quaternion), its position, and the 2D points it saw |
| `points3D.bin` | COLMAP | every 3D point: x y z, colour, error, and which frames see it |
| `world.json` | our script | the recipe that turns COLMAP's arbitrary coordinates into the world frame: `scale`, `rotation`, `translation` |
| `<scene>_collision.json` | our script | the floor plan: `cell` size, `originX/originZ`, `cols/rows`, `floorY`, `eyeHeight`, `radius`, `start`, and two grids of "0"/"1" characters: `occupied` (furniture/walls) and `blocked` (occupied plus a safety margin around it) |
| `splat.ply` | nerfstudio | the trained splat. One row per Gaussian: position, colour, opacity, size (3 numbers, stored as logarithms), rotation (4 numbers) |
| `dataparser_transforms.json` | nerfstudio | how nerfstudio moved/rotated/scaled the scene during training. Without it we cannot put the splat back where it belongs |
| `.qsplat` | our script | the website's splat. A 40-byte header (magic `QSPL`, count, bounding box, size range) then, for every Gaussian, 17 bytes: position (3 x 16-bit), size (3 x 8-bit), colour+opacity (4 x 8-bit), rotation (4 x 8-bit). Everything is then gzip-compressed |
| `manifest.json` | our script | tells the website which files to load: `{"splat": "...qsplat", "grid": "..._collision.json"}` (a `"mesh"` entry is optional) |
| `scene.json` | STEP 1 | the scene name, frame count, point count and video info. It travels with the zip so every step knows what it is working on |

A `.bin` file is just numbers stored compactly. You cannot read it in a text editor; the scripts read it with Python's `struct` module.

## 4. How the scripts are launched: .bat, .sh, .py

- **`.bat`** (Windows): a list of terminal commands you can double-click. `STEP1_prepare_video.bat` only says "go to this folder and run `python scripts\step1_prepare.py`", then `pause` so the window stays open to read.
- **`.sh`** (Linux "bash"): the same idea on Linux. `STEP2_train_on_remote.sh` is run with `bash scripts/STEP2_train_on_remote.sh`. Useful lines to recognise:
  - `set -uo pipefail`: stop on using an unset variable, and report failures inside pipes.
  - `cd "$(dirname "$0")/.."`: go to the folder this script lives in (so it works from anywhere).
  - `$((T_TRAIN-T_PREP))`: arithmetic, here seconds between two clock readings.
  - `fail "message"`: our own helper that prints `STOPPED: message` and quits.
- **`.py`** (Python): the real work. Each script does one job, prints what it is doing, and stops with a clear message if something is wrong instead of producing garbage.

## 5. STEP 1 on the laptop - what happens inside

You put a video in `namma_pipeline\1_PUT_VIDEO_HERE\` and double-click `STEP1_prepare_video.bat`. The code is `scripts/step1_prepare.py`. It runs six stages and prints how long each took.

| # | Stage | What it really does | Stops when |
|---|---|---|---|
| 1 | check video and tools | finds ffmpeg and COLMAP, reads the video size/duration, shows your GPU, names the scene after the video file | video missing or unreadable |
| 2 | pick the sharpest colour frame of every time window | `scripts/select_sharp_frames.py`. A phone video has 30 frames a second, but at any moment a few are blurred by hand shake. The script scores **every** frame for sharpness (Laplacian variance, on a small copy so it is fast), splits the video into half-second windows, and keeps the sharpest frame from the middle of each window. Windows where even the best frame is very soft are left out. Then `ffmpeg` extracts only the chosen frames at up to 1920 px wide. It checks the extracted frames match the scored ones, and that they are really in colour. (Old method: `--classic-frames`.) We do not use AI upscaling or deblurring: it invents slightly different detail in each frame, which breaks the agreement between views that COLMAP and training depend on | video too short or too dark, frames do not match the scores, frames are grey |
| 3 | COLMAP | three sub-steps, each printed live: **feature extraction** (finds corners in every frame), **matching** (links frames that see the same corners; we match each frame with its neighbours in time, which is right for a video), **mapper** (solves all camera positions and 3D points together) | COLMAP itself fails |
| 4 | health check | counts the registered frames per model. Keeps the biggest model. Warns if fewer than 80% of frames were placed, or if the walk split into two big pieces | under 40% placed, or no model |
| 5 | floor, scale, collision map | `build_collision_from_colmap.py`: finds the **up direction from the floor** (a plane fitted to the lowest points under your walking path), sets floor = height 0, scales to metres assuming the phone was about 1.4 m high, then builds the floor plan | camera "up" directions disagree (phone was not held upright) |
| 6 | pack zip for the remote PC | copies the placed frames (full size + half size), the three `.bin` files, `scene.json`, the remote scripts and `REMOTE_NOTES.md`, then zips and tests the zip | the zip fails its integrity check |

At the end it prints a **TIME TAKEN** table and the full path of the zip, which is also copied to `2_SEND_TO_REMOTE\`. Everything printed is also saved to `runs\<scene>\logs\step1.log`.

**How the collision map is built (stage 6), step by step:**
1. Up direction and floor: gravity cannot be measured from a video, so we find the floor itself.
2. Scale: COLMAP's units are arbitrary. If the camera is 1.4 m above the floor, one COLMAP unit = a known number of metres. Sanity checks print where the furniture surface and the top of the scene land (a bed should be 0.45-0.55 m, a ceiling 2.5-3.1 m).
3. Obstacles: 10 cm floor squares that have at least 3 points between 0.15 m and 1.7 m height are "occupied" (walls, furniture).
4. Free space: squares near where *you walked*, plus floor squares seen near your path. Anything within 20 cm of your own footsteps cannot be an obstacle.
5. A safety margin (the player's radius, 25 cm) is added around obstacles to make the `blocked` grid. Unreachable pockets are blocked.
6. A preview picture (`*_collision_preview.png`) and three MeshLab files (`*_points_world.ply`, `*_grid_world.ply`, `*_camera_path.ply`) let you check it by eye.

## 6. STEP 2 on the remote PC - what happens inside

You carry the zip to the remote PC, unzip it, and run `bash scripts/STEP2_train_on_remote.sh`. It has four stages:

1. **prepare and check**: activates the `namma3dgs` conda environment, reads the GPU's capability (the new Blackwell cards need a CUDA 12.8 build of PyTorch), counts frames, and checks again that the images are colour.
2. **training**: `ns-train splatfacto` reads `dataset/` and optimises the Gaussians. Default 30,000 steps at full image size. A background loop samples GPU memory every 2 seconds.
3. **export**: `ns-export gaussian-splat` writes `splat.ply`.
4. **pack**: copies `splat.ply`, `dataparser_transforms.json`, `config.yml`, `scene.json`, a `timing.txt` and the log into `results/<scene>_result.zip`.

It prints a **TIME TAKEN** table and the path of the result zip. If another user is using the same GPU, training is slower; the report says so.

## 7. STEP 3 on the laptop - what happens inside

You put the result zip in `3_PUT_REMOTE_RESULT_HERE\` and double-click `STEP3_finish_and_open_website.bat` (code: `scripts/step3_finish.py`, which calls `scripts/finish_scene.py`).

1. **Find the zip and the matching STEP 1 data.** `scene.json` inside the zip tells it which scene; it then looks for `runs\<scene>\` on the laptop.
2. **finish_scene.py** does the careful part:
   - *Undo nerfstudio's coordinate change.* nerfstudio re-centres, rotates and rescales the scene to make training easier. `dataparser_transforms.json` records this. We reverse it, then apply `world.json`, so the splat lands in the same world frame as the collision grid. Positions, rotations and sizes are all transformed.
   - *Check the result.* It measures how far the splat's Gaussians are from the real COLMAP points. If they do not line up (more than 0.4 m median), it **stops** instead of producing a website where walls are in the wrong place.
   - *Clean it.* Removes nearly transparent Gaussians, absurdly large ones, and ones far (over 1.2 m) from anything the camera saw ("floaters").
   - *Shrink it.* Keeps the most important 700,000 Gaussians so a normal laptop can draw them, and writes the `.qsplat`.
3. **polish_splat.py** tidies the splat. Shiny floors and glossy wardrobes cannot be modelled as mirrors, so training invents "ghost" copies of reflected things *below* the floor. This step deletes everything more than 12 cm under the floor (and anything above 3.3 m), then **sorts the Gaussians most-important-first** (opacity x size). That order matters: the website's 250k and Auto modes draw the first N, so they now draw the best N. An optional `--smooth-floor` averages the colour of floor Gaussians (off by default; the effect was small).
4. **build_collision_from_splat.py** widens the walkable map. The camera-path map only knows floor near where you walked; the trained splat also shows floor and furniture elsewhere. It combines both, keeps the one connected region that contains your walk, and **stops** if your own walked path or the start point would end up blocked. It writes a preview picture too (`..._walkable_map.png`).
   - *Build the website* by copying the viewer template and adding the scene's files.
5. **Start the website** on `http://localhost:8765/` and open your browser. Ctrl+C in the window stops it.

## 8. The website (viewer)

The viewer template lives in `namma_pipeline/viewer_template/` (the live bedroom site in `03_bedroom_early/site/` is left alone) and is copied into every scene's `site/`. It is plain files, no build step:

| File | Job |
|---|---|
| `index.html` | the page: title, buttons, the on-screen help |
| `main.js` | our own renderer. Loads `assets/manifest.json`, decodes the `.qsplat`, draws the Gaussians with WebGL, sorts them back-to-front every moment (so see-through blobs blend correctly), handles W A S D, mouse look, and **collision** |
| `vendor/three.min.js` | the Three.js library, kept local so the site works offline |
| `assets/` | `manifest.json`, the `.qsplat`, the collision JSON (and the optional mesh) |

**Collision in `main.js`:** every frame it tries to move you; if the new spot lies on a `blocked` square it slides you along the wall instead. Your eye height is fixed at `floorY + eyeHeight`. Detail buttons 250k, 500k and All set how many splats are drawn (the file is sorted best-first). Adding `?debug` to the address shows a diagnostics panel (GPU name, canvas size, frame time, sort delay). Buttons: `1` splat, `2` mesh (if any), `M` shows the grid, `R` resets to the start point, and the detail limits (250k / 500k / All) trade quality for speed.

**Why it can be slow:** the browser must sort and draw up to 700,000 blobs every frame. FPS depends on that number (and on the GPU), not on how long the training took. Fewer Gaussians = faster.

## 9. The old pipeline, and what went wrong (history, for learning)

**Experiment 1, teddy:** photos of a teddy on a table, COLMAP and splatting on Google Colab. Only 18 images, 1,930 points, 2,000 training steps: the splat looked flat. Lesson: you need many sharp, overlapping frames and 15,000+ steps.

**Experiment 2, bedroom:** one calm eye-level lap, 359 frames, all 359 placed, 134,897 points. Trained on a remote GPU PC. Success. Mesh made with Poisson reconstruction. Website at Cloudflare. Weakness: black ceiling.

**Experiment 3, hallway + bedroom (the messy one):** the old `local_pipeline` folder did frame extraction, COLMAP and "training" on the laptop. What happened:

| Problem | What was wrong | Fix |
|---|---|---|
| Frames were **grey** | the blur filter read each frame as grayscale to measure sharpness and then **saved that grey copy** as the training frame. Colour was lost, so the splat was grey | STEP 1 keeps the original colour file and refuses to continue if frames are grey |
| A **fake splat** | when training would not run, a script turned the raw COLMAP points directly into a `.splat`. It is just a thin cloud of dots, not 3DGS | removed; training only happens on the remote GPU |
| **Two scenes merged** | an agent mixed the bedroom-only splat with the hallway scene in one website | one video = one scene = one website |
| Wrong diagnosis | training inside Windows' Linux layer (WSL2) failed; it was blamed on the GPU driver. The logs show it died *before* the GPU was used: **the laptop ran out of RAM** while preparing 760 images | training moved to the remote PC |
| Fake downscaling | the `images_4` folder was a shortcut to the full-size images, so "downscale by 4" did nothing | STEP 1 makes real half-size images; nerfstudio is told what to use |
| `.qsplat` encoder | its file header was written wrongly and could never have worked | fixed; checked against the viewer's reader |
| Capture | a second walking round at a different angle (raising the phone for the ceiling) made COLMAP place walls twice: double window, bent door | see the capture rules in the overview |

## 10. A tour of one run folder

After STEP 1, `namma_pipeline\runs\<scene>\` contains:

```
frames\            the sharp colour frames (kept)
frames_rejected\   blurry/duplicate frames (kept for inspection)
colmap\
   database.db     COLMAP's notebook (large)
   sparse\0, 1...  every model COLMAP made
   best\           cameras.bin images.bin points3D.bin of the model we use
world\             world.json, <scene>_collision.json, preview png, MeshLab files
bundle\            the zip contents and the zip
logs\              step1.log, step1_summary.json, later step3.log
site_build\        (after STEP 3) the .qsplat, a cleaned .ply and the finished site\
```

`runs\` is generated and not pushed to GitHub. When a scene is finished you move what you want to keep into its numbered project folder.

## 11. When something goes wrong

| You see | Likely cause | Do this |
|---|---|---|
| `STOPPED: no video found` | video is not in `1_PUT_VIDEO_HERE` | put it there |
| `frames are grayscale` | video or extraction problem | check the video plays in colour |
| `only N% of frames were placed` | too fast turns, little overlap, plain walls | re-shoot slower, with overlap |
| WARNING two large models | the walk broke into two pieces (for example two rounds at different angles) | re-shoot one continuous eye-level walk |
| `camera up directions disagree` | phone held sideways/upside-down for long | hold it upright, landscape |
| STEP 3: `does not line up` | wrong or mismatched result zip | make sure the zip is from the same bundle |
| website is grey | training images were grey | STEP 2 would have stopped; check the frames |
| website very slow | too many Gaussians for the laptop GPU | use the 250k/500k buttons; later: lower the budget |
| remote: `ns-train not found` | environment not activated | the script tries `namma3dgs` |
| remote: GPU slow | another user is using it | report it; wait or retry |

## 12. Rules that keep this clean

- One video = one scene = one website. Never mix them.
- Never fake the training stage.
- Colour check at the start of both STEP 1 and STEP 2.
- Every stage prints what it did, how long it took, and stops with a clear message if the result is bad.
- Big files stay out of GitHub. Unwanted files go to `_quarantine\` first and are deleted only by you.
