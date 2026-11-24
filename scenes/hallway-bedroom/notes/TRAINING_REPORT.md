# NammaSpace · hallway_bedroom_v2 · 3DGS training report

**Result zip:** `hallway_bedroom_v2_3dgs_30k_1920x1080_colour_868f_result.zip`
(SHA-256 `fbe64f268dc84e3e6ddbec5c6918e9f4aa912aa39a2cec27ebca1067137b11ac`)

Trained on the remote GPU PC on **2026-10-15, 21:25 → 21:42 IST**, using `RUN_NEW_BUNDLE.sh` (unzip, check, run STEP 2 as a user service, file the run).

## What was done

The laptop's STEP 1 made a COLMAP bundle from `hallway_bedroom_v2.mp4` (1920×1080): **868 colour frames** with solved camera poses (372,395 sparse points). On the GPU PC, `STEP2_train_on_remote.sh` with its defaults trained a real **3D Gaussian Splatting** model (nerfstudio `splatfacto`, gsplat), exported `splat.ply` and packed the result zip. COLMAP was not re-run, frames and poses are untouched, and coordinate frames are unchanged (`dataparser_transforms.json` is in the zip).

## Settings

| Setting | Value |
|---|---|
| Steps | 30,000 |
| Image size | full size, 1920×1080 (downscale 1) |
| Frames | 868: 759 train, 109 held out for evaluation (every 8th frame) |
| Image cache | GPU requested; nerfstudio switched to CPU because there are more than 500 images (no effect on quality) |
| Colour check | red-vs-blue difference 16.9 (grey would be 0.0) |

## Time taken

| Stage | Seconds |
|---|---:|
| Check and prepare | 0 |
| Training | 995 (16 min 35 s) |
| Export | 23 |
| **Total** | **1,018 (17 min)** |

## GPU

NVIDIA RTX PRO 6000 Blackwell Max-Q, 97,887 MiB, driver 580.178.04. Peak GPU memory for the whole card: **13,777 MiB** (includes everything else on the card). The GPU was already in use by other work when training started (6.1 GB), so the card was shared and seconds may be slightly longer than on an idle GPU.

## Result

| Item | Value |
|---|---|
| Gaussians at end of training | 658,476 |
| Gaussians exported | **650,654** (7,822 low-opacity dropped, 0 NaN/Inf) |
| Held-out quality (109 eval frames, step 29,000) | **PSNR 26.46 dB · SSIM 0.874 · LPIPS 0.244** |
| Train PSNR (step 29,990) | 25.59 dB |
| Splat colour | channels clearly differ (mean abs R−G 0.239, G−B 0.201): colour, not grey |

## What's in the zip

`splat.ply` (161,363,785 B, 650,654 Gaussians), `dataparser_transforms.json`, `config.yml`, `scene.json`, `timing.txt`, `step2.log`. The 30k checkpoint stays on the GPU PC under `bundles/hallway_bedroom_v2/outputs/`.

## Environment

conda env `namma3dgs`: Python 3.11.17, torch 2.7.1+cu128, nerfstudio 1.1.5, gsplat 1.4.0, open3d 0.20.0.

## Problems

None this run. The v2 STEP 2 script had the same `set -u` / `conda activate` problem as v1 (`NVCC_PREPEND_FLAGS: unbound variable`); `RUN_NEW_BUNDLE.sh` added `set +u` / `set -u` around `conda activate` automatically (original kept as `.orig`). No memory-guard kills.

## Comparison with v1

| Scene | Frames | Steps | Train s | Gaussians | PSNR | SSIM | LPIPS |
|---|---:|---:|---:|---:|---:|---:|---:|
| hallway_bedroom_v1 | 709 | 30,000 | 725 | 741,950 | 23.56 | 0.852 | 0.290 |
| **hallway_bedroom_v2** | **868** | **30,000** | **995** | **650,654** | **26.46** | **0.874** | **0.244** |
