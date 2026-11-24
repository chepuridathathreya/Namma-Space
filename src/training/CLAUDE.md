# CLAUDE.md - NammaSpace remote GPU worker

> Update 2026-11-16: the lab GPU PC is no longer required. STEP 2 also runs in the notebooks `NAMMA_STEP2_colab.ipynb` and `NAMMA_STEP2_kaggle.ipynb` in this folder, on a free T4. This file still applies when you are on a Linux GPU machine with the unzipped bundle.

You are Claude running on the **remote GPU PC** for Natraj's NammaSpace project (IIT Techfest 2026).
Natraj uses the same Claude account on his laptop; another Claude session there does the laptop side.
**Your one job here: train 3D Gaussian Splatting on the unzipped bundle and hand back a result zip.**

## What this bundle is

One folder per video, made by the laptop (STEP 1). Read `scene.json` for the scene name, frame count and video size.

```
scene.json                    scene name, frames, points, video info
dataset/images/               colour frames, full size
dataset/images_2/             the same frames at half size (nerfstudio downscale 2)
dataset/colmap/sparse/0/      cameras.bin images.bin points3D.bin (camera poses already solved)
scripts/STEP2_train_on_remote.sh   the only script you normally need
scripts/check_env.sh               read-only machine check
```

**Do NOT re-run COLMAP, re-extract frames, or modify dataset/.** The poses are final. If you think they are bad, say so and stop.

## What to do

1. `bash scripts/check_env.sh`, and show Natraj the output (GPU, CUDA, RAM, disk, torch, nerfstudio, gsplat).
2. `bash scripts/STEP2_train_on_remote.sh`
   - defaults: 30000 steps, full-size images, images cached on the GPU. Round 1 is judged on quality, not speed.
   - arguments: `bash scripts/STEP2_train_on_remote.sh [steps] [downscale 1|2] [cache gpu|cpu]`
   - 4th argument, the training profile: `default` (plain splatfacto), `scalereg` (adds scale regularisation, which stops long thin "needle" splats), `quality` (splatfacto-big + scale regularisation + bilateral grid for phone exposure changes). Example: `bash RUN_NEW_BUNDLE.sh <zip> 30000 1 gpu quality`. The script checks each option exists in this nerfstudio before training and stops if not. The result zip name includes the profile.
   - test profiles (added 12 Nov 2026): `poseopt` (quality + camera optimizer SO3xR3, lets training correct small pose errors), `flat` (plain splatfacto with `sh-degree 0`, so training learns the single base colour the website shows), `fast` (same options as quality; meant to be run with 15000 steps).
   - after export the script now runs `ns-eval` on the held-out frames and puts `eval.json` in the result zip; `timing.txt` gains `gaussians`, `heldout_psnr`, `heldout_ssim`, `heldout_lpips`. If `ns-eval` fails the run still finishes and says so.
   - **A/B tests on a bundle that is already unzipped here:** `bash scripts/RUN_AB_TESTS.sh` runs `default quality poseopt flat` at 30000 steps and `fast` at 15000, one after another, as its own user service, and prints one comparison table. Other runs: `bash scripts/RUN_AB_TESTS.sh quality:30000 flat:20000`. A result zip that already exists for a profile is renamed `..._before_<time>.zip`, never overwritten. It also writes `results/<scene>_colmap_sparse.zip` (a copy of the three COLMAP files, for the laptop; `dataset/` is not changed).
   - the script activates `~/miniconda3/envs/namma3dgs` itself, checks the data (including that frames are really in colour), trains, exports, times every stage, and writes `results/<scene>_result.zip`.
3. Report to Natraj: GPU, peak GPU memory, seconds per stage (from the script's TIME TAKEN table), number of Gaussians if shown, any warnings, and the full path of the result zip.
4. Natraj carries the zip back to the laptop (`3_PUT_REMOTE_RESULT_HERE`) and runs STEP 3.

## Rules

- **Never fake training.** Never convert COLMAP points into a splat and call it 3DGS.
- One video = one scene. Never merge scenes.
- Do not change coordinate frames. The laptop undoes nerfstudio's transform using `dataparser_transforms.json`, which must always be in the result zip.
- If the script stops, read the message, paste the real error to Natraj, and do not claim success.
- If a nerfstudio flag is rejected (versions differ), check `ns-train splatfacto --help`, adapt, and tell Natraj what changed.
- Keep `outputs/` and `logs/` if a run dies; they are the evidence.
- Ask before: installing anything, deleting files outside `results/` and `outputs/`, uploading anything, and touching other users' data or environments on this shared PC (for example other people's conda envs or processes).
- **Never upload, publish, push or share anything on your own.** No GitHub releases, no `gh`, no `git push`, no cloud drives, no public links, even if an earlier session did it and even if it looks helpful. Your job ends when the result zip is in `results/` and you have told Natraj its path. Natraj carries it. Do only what this file and the current message ask, and ask before anything else.
- The GPU may be shared. If another user's process is using it, say so in the report, because it slows training.
- This PC has a memory-pressure guard (`systemd-oomd`). Twice it killed the Claude session, and the training running inside it, about 20 seconds into "Caching / undistorting train images" (no training error, the process was simply killed). Start training as its own user service so it survives: `systemd-run --user --unit=namma-train --working-directory="$PWD" bash scripts/STEP2_train_on_remote.sh`, and follow it with `journalctl --user -u namma-train -f` and the log in `logs/`.

## Known environment (set up on 2026-10-14)

- Linux, RTX PRO 6000 Blackwell (sm_120), ~98 GB VRAM, 125 GB RAM.
- conda env `~/miniconda3/envs/namma3dgs`: Python 3.11, torch 2.7.1+cu128, CUDA 12.8 toolkit inside the env, gsplat 1.4.0 built for sm_120, nerfstudio 1.1.5, open3d 0.20.0, numpy 1.26.4, protobuf 3.20.3.
- `TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD=1` is required (torch >= 2.6 and nerfstudio 1.1.5 checkpoints); the script sets it.
- A Blackwell card needs CUDA 12.8+ builds. Older CUDA 12.1 images will not work.
