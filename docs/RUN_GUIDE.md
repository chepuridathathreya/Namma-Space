# How to Run the Pipeline - Step by Step

Last updated: 2026-10-15. The explanation of why each step exists is in [01_HOW_EVERYTHING_WORKS_BEGINNER_GUIDE.md](01_HOW_EVERYTHING_WORKS_BEGINNER_GUIDE.md). This page is only the clicks.

The pipeline has three parts. Parts 1 and 3 run on your laptop. Part 2 runs on the remote GPU PC.

```
 LAPTOP  STEP 1  ->  zip  ->  REMOTE PC  STEP 2  ->  zip  ->  LAPTOP  STEP 3  ->  website
```

---

## Before you start (one time)

**Laptop** needs: Python 3 with `numpy scipy opencv-python Pillow`, `ffmpeg`, and COLMAP (on PATH, or at `D:\Tools\COLMAP`).

**Remote PC** needs: the conda environment `namma3dgs` (already built) and the file `RUN_NEW_BUNDLE.sh` saved in its workspace folder. That file is in this repo at `namma_pipeline/remote/RUN_NEW_BUNDLE.sh`. Put it on the remote PC once; it takes any bundle zip and does everything.

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
