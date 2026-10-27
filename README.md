# NammaSpace

Walk through a real room in your browser, built from one phone video.

NammaSpace turns a walkthrough video into a 3D Gaussian splat and publishes it as a web page where you move with W A S D. Walls and furniture block you, so you can judge a space before you visit it. Built for IIT Techfest 2026, Round 1.

**Live demo:** https://namma-space.pages.dev/

## Scenes

| Scene | Folder | Notes |
|---|---|---|
| Room | [`01_room`](01_room) | Best scene. Held-out PSNR 27.14 dB, SSIM 0.913 |
| Hallway and Bedroom | [`02_hallway_bedroom`](02_hallway_bedroom) | Longer capture, hallway is strong |
| Early Bedroom | [`03_bedroom_early`](03_bedroom_early) | First capture, kept for comparison |

Each `site/` folder is a complete static website.

## How it works

```
phone video
   |
   v  STEP 1 (laptop)    sharp-frame picker, COLMAP camera poses, floor and scale, collision map
   v  STEP 2 (GPU PC)    3D Gaussian splat training with nerfstudio splatfacto
   v  STEP 3 (laptop)    align, clean, compress to .qsplat, build the website
   |
   v
web viewer: first-person walking with grid collision
```

| Stage | Time on Room (613 frames) |
|---|---|
| STEP 1, prepare (COLMAP is most of it) | about 21 min |
| STEP 2, train 30,000 steps | 14 min on an RTX PRO 6000 |
| STEP 3, finish and build site | 15 s |

Result: 541,337 Gaussians, 8 MB compressed splat. Details in [`01_room/notes/TRAINING_REPORT.md`](01_room/notes/TRAINING_REPORT.md).

## Run a scene locally

Requires Python 3.

```bash
cd 01_room/site
python -m http.server 8766
```

Open http://localhost:8766/index.html. On Windows, double-click `START_WINDOWS.bat` instead.

| Key | Action |
|---|---|
| W A S D | walk |
| Shift | run |
| Space | jump |
| Mouse | look (click the scene first) |
| M | show the walk map |
| R | back to the door |
| Esc | free the mouse |

Add `?debug` to the address for a performance panel.

## Rebuild a scene from your own video

| Where | You need |
|---|---|
| Laptop (STEP 1 and 3) | Python 3 with `numpy scipy opencv-python Pillow`, ffmpeg, COLMAP |
| GPU PC (STEP 2) | NVIDIA GPU, conda env with nerfstudio 1.1.5 and gsplat 1.4.0, see [`namma_pipeline/remote/REMOTE_NOTES.md`](namma_pipeline/remote/REMOTE_NOTES.md) |

1. Put one video in `namma_pipeline/1_PUT_VIDEO_HERE/` and run `STEP1_prepare_video.bat`. It writes a zip to `2_SEND_TO_REMOTE/`.
2. On the GPU PC, run `bash RUN_NEW_BUNDLE.sh <zip>` (from `namma_pipeline/remote/`). It writes a result zip.
3. Put the result zip in `3_PUT_REMOTE_RESULT_HERE/` and run `STEP3_finish_and_open_website.bat`. The site opens at http://localhost:8765/.

Full steps and troubleshooting: [`docs/RUN_GUIDE.md`](docs/RUN_GUIDE.md). How each script works: [`docs/HOW_IT_WORKS.md`](docs/HOW_IT_WORKS.md).

## Repository layout

```
01_room/               hero scene: site/ and training notes
02_hallway_bedroom/    second scene, site/
03_bedroom_early/      first scene, site/
home/                  scene picker page
deploy/                publishes all scenes as one Cloudflare Pages site
namma_pipeline/
  scripts/             pipeline code (frames, COLMAP, collision, splat cleanup, compression)
  remote/              GPU training scripts
  viewer_template/     the web viewer every scene is built from
docs/                  run guide and internals
```

Sample data for a quick test is coming in `test/`.

## Capture tips

Landscape video, phone at eye height, slow steady walk, locked focus and exposure, one continuous path that ends where it started. The full capture procedure is in [`docs/RUN_GUIDE.md`](docs/RUN_GUIDE.md).
