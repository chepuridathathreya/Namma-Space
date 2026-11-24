# NammaSpace

A phone video of an indoor space becomes a photoreal 3D digital twin that runs in the browser. You can walk through it with collision, search for places in it, and follow a walkable route to them.

Team Matrix (Chepuri Dathatreya) · IIT Techfest 2026, NammaSpace challenge

**Live app:** https://namma-space.pages.dev/ · **Technical report (Round 1):** https://namma-space-documentation.pages.dev/report/

## Objective

The challenge asks for a pipeline that converts 2D smartphone captures of an indoor space into an interactive 3D digital twin with:

1. a reconstruction that looks as close to the real space as possible,
2. free roaming with obstacle-aware movement,
3. points of interest (POIs) that can be tagged and searched,
4. navigation from the visitor to a chosen POI.

Constraints set by the organizers: open-source tools only, no commercial reconstruction services, and reconstruction quality is judged first.

## Approach

![Architecture: phone video, then prepare, train, finish and tag places, then the web viewer](docs/img/architecture.svg)

| Step | What it does | Built with | Output |
|---|---|---|---|
| Capture | One slow, steady 4K walk at one height with exposure locked, plus about 80 photos of corners. Rules are in the [capture SOP](docs/capture-sop.md). | Phone camera | `video.mp4` |
| 1. Prepare | Keeps the sharpest frame of every half second, solves camera poses and sparse points, finds the floor, sets metric scale and builds a first collision grid from the camera path. | ffmpeg, OpenCV, COLMAP 3.9 | `bundle.zip` |
| 2. Train | Trains a 3D Gaussian splat for 30,000 steps and scores it on held-out frames. Runs on a free Colab or Kaggle T4 ([cloud training](docs/cloud-training.md)) or on a local NVIDIA GPU of 16 GB or more. | nerfstudio 1.1.5 (splatfacto), gsplat 1.4, PyTorch | `splat.ply` |
| 3. Finish | Moves the splat into the floor-aligned metric frame, removes floaters and mirror ghosts below the floor, compresses it best-first, and merges a splat-based collision grid with the camera-path grid. | NumPy, SciPy | `.qsplat`, `collision.json` |
| 4. Tag places | A browser editor: aim at an object, press `T`, name it. Each place is checked against the walkable grid before it is saved. See [places and routes](docs/places-and-routes.md). | the viewer, Python | `pois.json` |
| Viewer | Static website. Draws the splat with our own WebGL2 renderer, stops the visitor at walls, searches places and draws an A* route on the same grid. Details: [places and routes](docs/places-and-routes.md). | WebGL2, Three.js, plain JavaScript, Cloudflare Pages | website |

## Status

| Round | Scope | State |
|---|---|---|
| 1 | Reconstruction and free roaming | Submitted, qualified for Round 2 on 10 Nov 2026 |
| 2 | POI tagging, search and navigation | Built and live in all scenes with places: 15 places in the 4K scene, 6 in the hallway scene |
| 3 | On-site capture of a multi-floor venue | Not started |

## Results

Scores are measured on frames held out from training.

| Scene | Folder | Frames | Gaussians | PSNR | SSIM | LPIPS | Places |
|---|---|---:|---:|---:|---:|---:|---:|
| Hallway and bedroom, 4K | [`scenes/hallway-bedroom-4k`](scenes/hallway-bedroom-4k) | 937 | 394,846 | 29.12 dB | 0.912 | 0.144 | 15 |
| Room | [`scenes/room`](scenes/room) | 613 | 541,337 | 27.14 dB | 0.913 | 0.191 | |
| Hallway and bedroom | [`scenes/hallway-bedroom`](scenes/hallway-bedroom) | 868 | 650,654 | 26.46 dB | 0.874 | 0.244 | 6 |
| Early bedroom | [`scenes/bedroom-early`](scenes/bedroom-early) | not recorded | 700,000 shown | not scored | | | |

Gaussians are counts after training, except the early bedroom, which predates scoring. The 4K site shows 344,087 after cleaning. Settings and timings are in `notes/TRAINING_REPORT.md` for the Room, Hallway and 4K scenes.

## Run it

View a scene locally:

```bash
cd scenes/hallway-bedroom-4k/site
python -m http.server 8766
```

Then open http://localhost:8766/. Controls: `W A S D` walk, `Shift` run, `/` search places, `G` walk the route, `F` fly there, `N` live map, `M` collision grid.

Rebuild a scene on one Linux machine with an NVIDIA GPU of 16 GB or more:

```bash
pip install -r requirements.txt -r requirements-train.txt
python run_all.py --check
python run_all.py --test
python run_all.py --video my_walk.mp4
```

`--check` lists what is missing, `--test` runs a bundled 40-frame sample end to end, and `--video` runs a full capture. With no local GPU, run STEP 1 on your computer, train with a notebook in [`src/training/`](src/training) on Colab or Kaggle ([cloud training](docs/cloud-training.md)), and finish with STEP 3. Windows launchers for STEPS 1, 3 and 4 are in [`scripts/windows/`](scripts/windows). Full instructions: [run guide](docs/run-guide.md) and [hardware](docs/hardware.md).

Tested: STEPS 1 and 3 on Windows, STEP 2 on Linux, Colab and Kaggle. `run_all.py --test` has not yet been run on a separate clean GPU machine, and native Windows training was not tried.

Tests (Node.js 21 or newer) cover navigation and places on the real scene grids:

```bash
node --test "tests/*.test.js"
```

## Repository layout

```
run_all.py            whole pipeline on one machine
src/
  pipeline/           STEP 1 prepare, STEP 3 finish, STEP 4 tagging, collision, compression
  training/           STEP 2: GPU training script and the Colab and Kaggle notebooks
  viewer/             web viewer every scene site is built from
scenes/<name>/
  site/               the published website for that scene
  notes/              training report for that scene
web/
  landing/            landing page at namma-space.pages.dev
  report-site/        Round 1 project page, technical report, SOP and results
tests/                navigation and place tests, bundled sample scene
docs/                 capture SOP, run guide, cloud training, places and routes, hardware, how it works
scripts/              deploy.sh and the Windows launchers
workspace/            local working folders for videos, bundles and runs (not in git)
submission/round1/    Round 1 PDFs as submitted
```

The Round 1 submission cites paths from the old layout. Those paths are kept under the git tag `round-1-layout`.

## Known limits

- Ceilings and areas the camera barely saw are rough or dark.
- Collision is a 2D floor grid. It does not model stairs, overhangs or more than one floor yet.
- Scale comes from an assumed 1.4 m phone height, not from a measured reference.
- Places are tagged by hand.
