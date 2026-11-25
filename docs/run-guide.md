# How to Run the Pipeline

Last updated: 2026-11-25. How each script works is in [how-it-works.md](how-it-works.md). This page is only the commands.

For a picture of the whole flow, see the diagram in the [README](../README.md#approach).

There are two ways to run it. **Option A, one computer with a large NVIDIA GPU, needs a single command.** Option B splits the work: STEPS 1 and 3 on a laptop, training on a free Colab or Kaggle GPU or on a separate GPU PC. Option B with a free cloud GPU is how the current scenes were built.

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

The full table, measured GPU memory and why each item is needed are in [hardware.md](hardware.md).

### Check the machine first

```bash
python run_all.py --check
```

It lists every requirement as `ok` or `MISSING` with the fix for each one, and stops without doing any work.

### Try the bundled test sample (no video needed)

```bash
python run_all.py --test
```

This uses a small sample scene in `tests/data/sample_scene.zip` (40 frames with the camera model and collision map already solved), trains for 1,000 steps instead of 30,000, and builds the website. It runs through all three stages in minutes and opens the result at http://localhost:8765/. The sample splat is rough on purpose: it proves the chain works on your machine, not the final quality.

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

## Option B: laptop plus a GPU (free cloud notebook or GPU PC)

Use this if your laptop cannot train. Parts 1 and 3 run on the laptop, part 2 on a free Colab or Kaggle GPU, or on a GPU PC.

```
 LAPTOP  STEP 1  ->  zip  ->  COLAB / KAGGLE / GPU PC  STEP 2  ->  zip  ->  LAPTOP  STEP 3  ->  website
```

### Before you start (one time)

**Laptop** needs: Python 3 with `numpy scipy opencv-python Pillow`, `ffmpeg`, and COLMAP (on PATH, or at `D:\Tools\COLMAP`).

**Free cloud GPU** needs: a Google account for Colab, or a phone-verified Kaggle account with Internet switched on in the notebook. The notebooks install everything themselves. Details: [cloud-training.md](cloud-training.md).

**Remote PC** (only if you use your own GPU PC instead) needs: a conda environment named `namma3dgs` with the packages from `requirements-train.txt` (see [hardware.md](hardware.md)) and the file `RUN_NEW_BUNDLE.sh` saved in its workspace folder. That file is in this repo at `src/training/RUN_NEW_BUNDLE.sh`. Put it on the remote PC once; it takes any bundle zip and does everything.

---

## Step 0 - Film the video

- Follow the tested settings in `docs/capture-sop.md` (Room scene: landscape, 1080p at 30 fps, Pro mode, manual focus, 1/100 s, ISO 800, 5000 K, EV 0). Phone at chest or eye height, tilted slightly down. 4K at 30 fps (3840x2160) gives sharper frames: the 4K hallway and bedroom scene scored PSNR 29.12 dB on held-out frames, the best of our scenes (the 1080p Room scored 27.14 dB). Keep disk free: a 7-minute 4K video is 3-4 GB.
- Switch off bright ceiling lamps and close curtains where you can: glossy floors and wardrobes reflect them, and a splat can only fake a reflection with ghost copies.
- **One continuous walk at the same height and angle.** Never raise the phone toward the ceiling for a second lap; that bent v1.
- Walk slowly (about half a metre a second), turn slowly. Keep about 1 m from walls. Do not fill the frame with a plain wall or curtain.
- End where you started.

## Step 0b - Optional extra photos

Corners and places the walk shows only briefly can be helped with 20-40 photos. Put them in `workspace\photos\`. STEP 1 adds them automatically and matches each one against every video frame, so a photo does not need to follow the walk; it only needs to show things the video also shows.

- Same phone, same lens and same Pro settings as the video (the Room used the 0.6x ultra-wide for both), landscape, same lights. Never switch lenses partway through.
- 2-3 photos per corner, each a step apart, at eye height and tilted up.
- Empty the folder after the run, or the next scene will pick up the old photos.

## Step 1 - Laptop: prepare (measured: 87 minutes for a 7-minute 1080p video at 883 frames, 53 minutes for the 7 m 43 s 4K video at 937 frames; use `--window 1` for about half the frames and a much faster COLMAP)

1. Copy **one** video file into `workspace\video\`.
   The scene is named after the file, so use a clean name with letters, numbers and underscores, for example `hallway_bedroom_v2.mp4`.
2. Double-click **`scripts/windows/step1_prepare.bat`**. A black window opens. Leave it open.
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
5. The zip is in `workspace\to_gpu\`, named `<scene>_to_remote.zip`. A full log is in `workspace\runs\<scene>\logs\step1.log`.

**You can stop here to test only the laptop side.** No remote PC is needed to check that STEP 1 works.

## Step 2 - Carry the zip to the GPU

- **Colab:** upload the zip to a Google Drive folder named `namma`.
- **Kaggle:** upload the zip as a private Kaggle Dataset.
- **GPU PC:** copy the zip there any way that works: Google Drive, a GitHub release, a USB drive. Note the path where it lands, for example `~/Downloads/hallway_bedroom_v2_to_remote.zip`.

## Step 3 - Train

### On a free cloud GPU (about 25 minutes on a T4)

Open `src/training/NAMMA_STEP2_colab.ipynb` in Colab or `src/training/NAMMA_STEP2_kaggle.ipynb` in Kaggle, pick the T4 GPU and run all cells. The notebooks train at half image size (`DOWNSCALE = 2`) so they fit the T4; set `ITERS = 2000` for a quick test. Colab saves the result zip back to the `namma` Drive folder; on Kaggle download it from the notebook output. The 4K scene took 1,534 s on Colab and 1,448 s on Kaggle, with the same score.

### On a GPU PC (about 12-16 minutes)

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

Copy the result zip from Drive, Kaggle or the GPU PC to the laptop folder `workspace\from_gpu\`. Keep **only one** zip there (STEP 3 uses the newest).

## Step 5 - Laptop: finish and open the website (about 15 seconds, plus the full-colour export)

1. Double-click **`scripts/windows/step3_finish.bat`**.
2. It finds the matching STEP 1 data, lines the splat up with the collision map and checks it, then cleans it (deletes mirror ghosts under the floor, sorts splats best-first), builds a walkable map from the splat as well as the camera path, writes the full-colour Spark file (`.spz`, split into parts under 25 MiB) next to the base-colour `.qsplat`, builds the website, and prints:
   ```
   OPEN THIS LINK:  http://localhost:8765/
   ```
   Your browser opens by itself.
3. Click the scene, then **W A S D** to walk, mouse to look, **Shift** to run, **M** to show the collision grid, **R** to go back to the start. The top-right number is your FPS.
4. Press **Ctrl+C** in the black window to stop the website.

**Detail buttons:** 60%, 80% and Full set the render resolution. All splats are always drawn. On a slow GPU the viewer lowers the resolution by itself and says so. Add `?colour=base` to the address to compare with the base-colour file.

**Slow in your browser?** Add `?debug` to the end of the address (for example `http://localhost:8765/?debug`). A panel appears showing which GPU the browser really uses, the canvas size, the frame time, the JavaScript time per frame and the sort delay. Send a screenshot of it. On the dev laptop's RTX 3060 the viewer measured about 175 FPS with all splats at 1600x900, so a much lower number points at the browser or Windows, not at the scene.

**What to check in the browser:** are the doors straight, is there a double window, do the walls stop you, does the grid (M) match the walls and furniture.

## Step 6 - Afterwards

- The finished website files are in `workspace\runs\<scene>\site_build\site\`.
- When you are happy, move what you want to keep into its scene folder (for example `scenes\hallway-bedroom\`). Move the result zip out of `workspace/from_gpu` so the next run starts clean.
- If a scene already has a site and you only need the full-colour file, run `python src/pipeline/export_spark.py --ply <splat.ply from the result zip> --assets scenes/<name>/site/assets`.

## Step 7 - Tag places (STEP 4)

1. Double-click **`scripts/windows/step4_tag_places.bat`**, or run `python src/pipeline/step4_tag_places.py --site scenes/<name>/site`.
2. The scene opens at `http://localhost:8766/?edit=1`. Aim the centre dot at an object, press `T` and type a name.
3. Press **Save to project**. Each place is checked against the walkable grid, the old file is backed up and `site/assets/pois.json` is written.

Search, routes and the place file format are in [places-and-routes.md](places-and-routes.md).

## Step 8 - Publish the website

Run `bash scripts/deploy.sh`. It copies the landing page and every scene site into a new folder under `tmp/wrangler_run/` and uploads it to the Cloudflare Pages project `namma-space`. It needs bash (Git Bash or WSL on Windows), Node.js for `npx wrangler`, and a Cloudflare login (`npx wrangler login`). Every file must be under 25 MiB, the Cloudflare Pages limit.

---

## Running without the cloud (testing only the laptop side)

Do steps 0 and 1 only. Success criteria: `STEP 1 FINISHED`, frames placed 80% or more, a TIME TAKEN table, a zip in `workspace/to_gpu`, and a collision map. To look at the map, open `workspace\runs\<scene>\world\<scene>_collision_preview.png` (green = walkable, red = obstacle, yellow = your path, blue = start). STEP 3 cannot run without a trained result.

## If something stops

| Message | Meaning | Do this |
|---|---|---|
| `no video found` | the folder is empty | put the video in `workspace/video` |
| `frames are grayscale` | colour was lost | check the video plays in colour |
| `only N% of frames were placed` | COLMAP could not follow the walk | re-shoot slower, farther from walls; or use `--window 0.33` for more frames |
| WARNING two large models | the walk broke into two pieces | re-shoot one continuous walk |
| `camera up directions disagree` | phone was not upright | hold it upright and landscape |
| remote: `STOPPED: this zip is not a NammaSpace bundle` | wrong zip | use the zip from `workspace/to_gpu` |
| remote: `NO RESULT ZIP WAS PRODUCED` | training stopped | read the last lines above it and the log in `bundles/<scene>_<date>/logs/` |
| STEP 3: `does not line up` | the result is from a different bundle | use the result for the same scene |
| STEP 3: `missing ... workspace\runs\<scene>` | STEP 1 data for that scene is not on this laptop | run STEP 1 again for that video |

## Using options

Double-clicking runs with the defaults. To pass options, open a terminal and run, for example:

```
scripts\windows\step1_prepare.bat --window 1
scripts\windows\step1_prepare.bat --classic-frames --fps 2
scripts\windows\step1_prepare.bat --name my_scene --video "D:\videos\walk.mp4"
scripts\windows\step3_finish.bat --title "My Scene" --port 8800
```
