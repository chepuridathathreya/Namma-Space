# How to Run the Pipeline

Last updated: 2026-10-28. How each script works is in [HOW_IT_WORKS.md](HOW_IT_WORKS.md). This page is only the commands.

For a picture of the whole flow and the two setups, see the diagrams in the [README](../README.md#how-it-works).

There are two ways to run it. **Option A, one computer, is the recommended way and needs a single command.** Option B is the two-machine setup we used ourselves.

---

## Option A: everything on one computer

### What the computer needs

| Need | Detail |
|---|---|
| OS | Linux, or Windows with WSL2 (training is only proven on Linux) |
| GPU | NVIDIA, 16 GB of GPU memory or more at full 1080p, CUDA 12.x driver and toolkit |
| Disk | 20 GB free |
| Tools on PATH | `ffmpeg`, `ffprobe`, COLMAP 3.9 or newer, `ns-train` and `ns-export` (nerfstudio) |
| Python | 3.11 recommended, with `pip install -r requirements.txt` and, for training, `pip install -r requirements-train.txt` after installing PyTorch for your CUDA version |

The full table, measured GPU memory and why each item is needed are in [HARDWARE_AND_REMOTE_SETUP.md](HARDWARE_AND_REMOTE_SETUP.md).

### Check the machine first

```bash
python run_all.py --check
```

It lists every requirement as `ok` or `MISSING` with the fix for each one, and stops without doing any work.

### Try the bundled test sample (no video needed)

```bash
python run_all.py --test
```

This uses a small sample scene in `test/sample_scene.zip` (40 frames with the camera model and collision map already solved), trains for 1,000 steps instead of 30,000, and builds the website. It runs through all three stages in minutes and opens the result at http://localhost:8765/. The sample splat is rough on purpose: it proves the chain works on your machine, not the final quality.

### Run on your own video

```bash
python run_all.py --video path/to/walkthrough.mp4
```

It checks the machine, then runs STEP 1 (frames, COLMAP, floor and collision map), STEP 2 (training, 30,000 steps) and STEP 3 (align, clean, build the website) in order, prints the time each took, and serves the result at http://localhost:8765/.

Useful options:

| Option | Meaning |
|---|---|
| `--name my_scene` | scene name (default: the video file name) |
| `--steps 15000` | fewer training steps, faster and rougher |
| `--profile scalereg` or `quality` | training profile, see below |
| `--downscale 2 --cache cpu` | half-size training images and image cache in system RAM, to lower GPU memory (not measured on small cards) |
| `--allow-small-gpu` | continue even if the GPU has less than 16 GB |
| `--window 1` | the sharp-frame picker keeps half as many frames, so COLMAP is much faster |
| `--camera-height 1.4` | phone height above the floor in metres |
| `--no-serve` | build the website but do not start the local server |
| `--finish-only RESULT_ZIP` | skip STEPs 1 and 2 and build the site from an existing result zip (no GPU needed) |

Profiles: `default` (plain splatfacto), `scalereg` (scale regularisation, which reduces long thin "needle" splats), `quality` (splatfacto-big with scale regularisation and a bilateral grid for phone exposure changes).

Typical times on the Room scene (613 frames): STEP 1 about 21 minutes (COLMAP is most of it), STEP 2 about 14 minutes on a large GPU, STEP 3 about 15 seconds.

---

## Filming the video

The capture rules are in Step 0 and Step 0b of Option B below. They apply to both options.

---

## Option B: two machines (laptop plus a GPU PC)

Use this if your laptop cannot train but you have access to a GPU PC. Parts 1 and 3 run on the laptop, part 2 on the GPU PC.

```
 LAPTOP  STEP 1  ->  zip  ->  GPU PC  STEP 2  ->  zip  ->  LAPTOP  STEP 3  ->  website
```

### Before you start (one time)

**Laptop** needs: Python 3 with `numpy scipy opencv-python Pillow`, `ffmpeg`, and COLMAP (on PATH, or at `D:\Tools\COLMAP`).

**Remote PC** needs: a conda environment named `namma3dgs` with the packages from `requirements-train.txt` (see [HARDWARE_AND_REMOTE_SETUP.md](HARDWARE_AND_REMOTE_SETUP.md)) and the file `RUN_NEW_BUNDLE.sh` saved in its workspace folder. That file is in this repo at `namma_pipeline/remote/RUN_NEW_BUNDLE.sh`. Put it on the remote PC once; it takes any bundle zip and does everything.

---

## Step 0 - Film the video

- Landscape, **4K at 30 fps** (set it in the camera app: v1 and v2 were accidentally 1080p, and 4K gives much crisper frames after downscaling). Phone at chest or eye height, tilted slightly down. Lock focus, exposure and white balance. A fast shutter (about 1/120 s) in Pro mode cuts blur. Keep D: free: a 7-minute 4K video is 3-4 GB.
- Switch off bright ceiling lamps and close curtains where you can: glossy floors and wardrobes reflect them, and a splat can only fake a reflection with ghost copies.
- **One continuous walk at the same height and angle.** Never raise the phone toward the ceiling for a second lap; that bent v1.
- Walk slowly (about half a metre a second), turn slowly. Keep about 1 m from walls. Do not fill the frame with a plain wall or curtain.
- End where you started.

## Step 0b - Optional extra photos

Corners and places the walk shows only briefly can be helped with 20-40 photos. Put them in `namma_pipeline\1b_PUT_EXTRA_PHOTOS_HERE\`. STEP 1 adds them automatically and matches each one against every video frame, so a photo does not need to follow the walk; it only needs to show things the video also shows.

- Same phone, **1x lens (never 0.5x)**, landscape, same lights as the video.
- 2-3 photos per corner, each a step apart, at eye height and tilted up.
- Empty the folder after the run, or the next scene will pick up the old photos.

## Step 1 - Laptop: prepare (measured: 87 minutes for a 7-minute video at 883 frames; use `--window 1` for about half the frames and a much faster COLMAP)

1. Copy **one** video file into `namma_pipeline\1_PUT_VIDEO_HERE\`.
   The scene is named after the file, so use a clean name with letters, numbers and underscores, for example `hallway_bedroom_v2.mp4`.
2. Double-click **`STEP1_prepare_video.bat`**. A black window opens. Leave it open.
3. Watch it. It prints six stages and the time each took:

   | Stage | What you will see |
   |---|---|
   | 1 check video and tools | your video size, your GPU |
   | 2 pick the sharpest colour frame of every time window | every frame is scored for sharpness, the sharpest of each half-second is kept; an alignment check and a colour check |
   | 3 COLMAP | three long sub-steps with scrolling text. This is the slow part |
   | 4 health check | how many frames were placed |
   | 5 floor, scale and collision map | a few lines, a preview picture is saved |
   | 6 pack zip | the zip is written |

4. **It worked** when you see `STEP 1 FINISHED`, a TIME TAKEN table and a line `ZIP TO SEND : ...`.
   - Good: frames placed 80% or more; no warning about a second large model.
   - If you see `STOPPED:`, read the message. The usual causes are in the table at the end of this page.
5. The zip is in `namma_pipeline\2_SEND_TO_REMOTE\`, named `<scene>_to_remote.zip`. A full log is in `namma_pipeline\runs\<scene>\logs\step1.log`.

**You can stop here to test only the laptop side.** No remote PC is needed to check that STEP 1 works.

## Step 2 - Carry the zip to the remote PC

Copy the zip from `2_SEND_TO_REMOTE` to the remote PC any way that works: Google Drive, a GitHub release, a USB drive. Note the path where it lands, for example `~/Downloads/hallway_bedroom_v2_to_remote.zip`.

## Step 3 - Remote PC: train (about 12-16 minutes)

Open a terminal on the remote PC, go to the workspace folder that holds `RUN_NEW_BUNDLE.sh`, and run:

```bash
bash RUN_NEW_BUNDLE.sh ~/Downloads/hallway_bedroom_v2_to_remote.zip
```

That one command unzips the bundle into `bundles/<scene>_<date>/`, checks it, starts training as its own service (so the PC's memory guard cannot kill it), shows the progress live, and prints at the end:

```
DONE. RESULT ZIP TO CARRY BACK TO THE LAPTOP:
  .../results/<scene>_result.zip
```

Optional settings: `bash RUN_NEW_BUNDLE.sh <zip> [steps] [downscale] [cache] [profile]`, default `30000 1 gpu default`. Profiles: `default`, `scalereg` (stops long thin needle splats), `quality` (splatfacto-big + scale regularisation + exposure correction). Example: `bash RUN_NEW_BUNDLE.sh <zip> 30000 1 gpu quality`.


## Step 4 - Carry the result zip back

Copy `<scene>_result.zip` from the remote PC to the laptop folder `namma_pipeline\3_PUT_REMOTE_RESULT_HERE\`. Keep **only one** zip there (STEP 3 uses the newest).

## Step 5 - Laptop: finish and open the website (about 10 seconds)

1. Double-click **`STEP3_finish_and_open_website.bat`**.
2. It finds the matching STEP 1 data, lines the splat up with the collision map and checks it, then cleans it (deletes mirror ghosts under the floor, sorts splats best-first), builds a walkable map from the splat as well as the camera path, builds the website, and prints:
   ```
   OPEN THIS LINK:  http://localhost:8765/
   ```
   Your browser opens by itself.
3. Click the scene, then **W A S D** to walk, mouse to look, **Shift** to run, **M** to show the collision grid, **R** to go back to the start. The top-right number is your FPS.
4. Press **Ctrl+C** in the black window to stop the website.

**Detail buttons:** 250k, 500k and All set how many splats are drawn. The file is sorted best-first, so 250k keeps the best 250,000.

**Slow in your browser?** Add `?debug` to the end of the address (for example `http://localhost:8765/?debug`). A panel appears showing which GPU the browser really uses, the canvas size, the frame time, the JavaScript time per frame and the sort delay. Send a screenshot of it. On the dev laptop's RTX 3060 the viewer measured about 175 FPS with all splats at 1600x900, so a much lower number points at the browser or Windows, not at the scene.

**What to check in the browser:** are the doors straight, is there a double window, do the walls stop you, does the grid (M) match the walls and furniture.

## Step 6 - Afterwards

- The finished website files are in `namma_pipeline\runs\<scene>\site_build\site\`.
- When you are happy, move what you want to keep into the numbered project folder (for example `02_hallway_bedroom\`). Move the result zip out of `3_PUT_REMOTE_RESULT_HERE` so the next run starts clean.
- Uploading to Cloudflare is a separate step, not part of these three clicks yet.

---

## Running without the cloud (testing only the laptop side)

Do steps 0 and 1 only. Success criteria: `STEP 1 FINISHED`, frames placed 80% or more, a TIME TAKEN table, a zip in `2_SEND_TO_REMOTE`, and a collision map. To look at the map, open `namma_pipeline\runs\<scene>\world\<scene>_collision_preview.png` (green = walkable, red = obstacle, yellow = your path, blue = start). STEP 3 cannot run without a trained result.

## If something stops

| Message | Meaning | Do this |
|---|---|---|
| `no video found` | the folder is empty | put the video in `1_PUT_VIDEO_HERE` |
| `frames are grayscale` | colour was lost | check the video plays in colour |
| `only N% of frames were placed` | COLMAP could not follow the walk | re-shoot slower, farther from walls; or use `--window 0.33` for more frames |
| WARNING two large models | the walk broke into two pieces | re-shoot one continuous walk |
| `camera up directions disagree` | phone was not upright | hold it upright and landscape |
| remote: `STOPPED: this zip is not a NammaSpace bundle` | wrong zip | use the zip from `2_SEND_TO_REMOTE` |
| remote: `NO RESULT ZIP WAS PRODUCED` | training stopped | read the last lines above it and the log in `bundles/<scene>_<date>/logs/` |
| STEP 3: `does not line up` | the result is from a different bundle | use the result for the same scene |
| STEP 3: `missing ... runs\<scene>` | STEP 1 data for that scene is not on this laptop | run STEP 1 again for that video |

## Using options

Double-clicking runs with the defaults. To pass options, open a terminal and run, for example:

```
cd namma_pipeline
STEP1_prepare_video.bat --window 1
STEP1_prepare_video.bat --classic-frames --fps 2
STEP1_prepare_video.bat --name my_scene --video "D:\videos\walk.mp4"
STEP3_finish_and_open_website.bat --title "My Scene" --port 8800
```
