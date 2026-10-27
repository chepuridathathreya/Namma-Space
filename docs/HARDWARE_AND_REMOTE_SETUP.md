# Hardware, requirements and why training runs on a remote GPU PC

This page explains what you need to rebuild a scene yourself, why our pipeline is split across two machines, and what that costs. You do not need any of this to view the finished scenes: open the live site or serve a `site/` folder with Python.

## The short version

| Part | Where it ran for us | Needs |
|---|---|---|
| STEP 1, prepare (frames, COLMAP, collision map) | Windows laptop, RTX 3060 Laptop (6 GB) | Python 3, ffmpeg, COLMAP, `requirements.txt`. No big GPU needed |
| STEP 2, train the 3D Gaussian splat | Remote Linux PC, RTX PRO 6000 Blackwell (98 GB) | NVIDIA GPU with a large amount of memory, CUDA 12.x, `requirements-train.txt` |
| STEP 3, finish and build the website | the same laptop | Python 3, `requirements.txt` |

If you have a capable NVIDIA GPU on one machine, you do not need a remote PC. Run all three steps on that machine and skip the zip carrying (see "If you have your own GPU").

## Requirements

### Laptop side (STEP 1 and STEP 3)

```bash
pip install -r requirements.txt
```

Also install and put on `PATH`:

- Python 3 (we ran 3.14 on the laptop).
- `ffmpeg`.
- COLMAP. On Windows the pipeline also looks in `D:\Tools\COLMAP`.

### GPU side (STEP 2)

| Item | What we used |
|---|---|
| OS | Linux (Ubuntu) |
| GPU | NVIDIA RTX PRO 6000 Blackwell, about 98 GB, compute capability sm_120 |
| CUDA | 12.8 toolkit (a Blackwell card needs CUDA 12.8 or newer builds; CUDA 12.1 images do not work on it) |
| Python | 3.11 in a conda environment |
| PyTorch | 2.7.1 built for CUDA 12.8 (install it first, from the PyTorch CUDA 12.8 index) |
| Training stack | `pip install -r requirements-train.txt` (nerfstudio 1.1.5, gsplat 1.4.0, open3d 0.20.0, numpy 1.26.4, protobuf 3.20.3) |
| Environment flag | `TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD=1` (PyTorch 2.6 and later with nerfstudio 1.1.5 checkpoints); the script sets it |

gsplat compiles CUDA code on first use, so the machine needs a working CUDA toolkit and a compiler, not only a driver. On our Blackwell card gsplat had to be built for sm_120.

### How much GPU memory

Measured on the whole card, so it includes any other process using it:

| Scene | Frames | Peak GPU memory | Training time (30,000 steps) |
|---|---:|---:|---:|
| Room | 613 | 16,251 MiB | 819 s |
| Hallway and Bedroom | 868 | 13,777 MiB | 995 s |

So plan for roughly 16 GB of GPU memory or more at full 1080p. We did not train on anything smaller. The script has options that should lower memory use (`downscale 2` for half-size images, `cache cpu` to keep images in system RAM), but we have not measured them on a small card, so treat them as untested. The 6 GB laptop GPU was judged too small and we did not run training on it.

## Why the pipeline is split across two machines

1. **The laptop GPU is too small and slow for training.** It has 6 GB of GPU memory and limited RAM. Training a splat at full image size needs far more.
2. **Only training needs the big GPU.** COLMAP, collision map building, cleaning and the website build run fine on a laptop, so we kept them there.
3. **The training PC is shared.** It is a lab machine, so we cannot install on it freely or leave work running unattended.

## What this setup costs you (the drawbacks)

- **Manual hand-off.** You carry a zip from the laptop to the GPU machine and carry a result zip back. We used a drive or a GitHub release. This is the biggest annoyance and the first thing to remove if you have one machine.
- **Two environments to keep in sync.** Python 3 on Windows for the laptop, a conda environment on Linux for training. Library versions matter (see the table above).
- **Fragile GPU setup.** A new GPU generation needed CUDA 12.8 builds and a gsplat compiled for it. Older CUDA images failed outright.
- **A shared GPU slows runs and can kill them.** Another user's process makes training slower, and the lab PC has a memory-pressure guard (`systemd-oomd`) that killed our training twice about 20 seconds into image caching. `RUN_NEW_BUNDLE.sh` therefore starts training as its own user service. You may not need that on your own machine.
- **Slow COLMAP on the laptop.** For the Room scene (613 frames) STEP 1 took about 21 minutes, and a 7-minute video at 883 frames took 87 minutes. Bundle adjustment ran on the CPU on our laptop.
- **The scripts are tied to our layout.** `RUN_NEW_BUNDLE.sh` and the `systemd-run` step assume a Linux user session. They are unnecessary if you train on your own machine.

## If you have your own GPU

You can skip the remote hand-off. We have **not** tested this exact route, so expect to adjust paths.

1. Run STEP 1 to produce the bundle zip, as in the [run guide](RUN_GUIDE.md).
2. On a Linux machine (or WSL2 with GPU support) with the GPU stack installed, unzip the bundle and run from the unzipped folder:

   ```bash
   bash scripts/STEP2_train_on_remote.sh
   ```

   Optional arguments: `[steps] [downscale 1|2] [cache gpu|cpu] [profile]`. The defaults are 30000 steps, full-size images, GPU image cache, `default` profile. Profiles: `default` (plain splatfacto), `scalereg` (scale regularisation, which reduces long thin "needle" splats), `quality` (splatfacto-big with scale regularisation and a bilateral grid for phone exposure changes).
3. Copy `results/<scene>_result.zip` into `namma_pipeline/3_PUT_REMOTE_RESULT_HERE/` and run STEP 3.

Native Windows training was not tried. The training script is a bash script written for Linux.

## What you can verify without any GPU

- The three finished scenes run in any modern browser with WebGL2: serve a `site/` folder with `python -m http.server`.
- The per-scene training reports record the exact settings, timings and held-out scores, for example [`01_room/notes/TRAINING_REPORT.md`](../01_room/notes/TRAINING_REPORT.md).
