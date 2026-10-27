# Remote GPU worker notes

Step 2 of the pipeline trains the 3D Gaussian splat on a GPU machine. This file travels inside the bundle zip.

## Bundle layout

```
scene.json                         scene name, frame count, point count, video info
dataset/images/                    colour frames, full size
dataset/images_2/                  the same frames at half size
dataset/colmap/sparse/0/           cameras.bin, images.bin, points3D.bin (poses already solved)
scripts/STEP2_train_on_remote.sh   the training script
scripts/check_env.sh               read-only machine check
```

Do not re-run COLMAP or modify `dataset/`. The camera poses are final.

## Run

```bash
bash scripts/check_env.sh
bash scripts/STEP2_train_on_remote.sh [steps] [downscale 1|2] [cache gpu|cpu] [profile]
```

Defaults: 30000 steps, full-size images, `default` profile.

| Profile | What it adds |
|---|---|
| `default` | plain splatfacto |
| `scalereg` | scale regularisation, which stops long thin "needle" splats |
| `quality` | splatfacto-big, scale regularisation and a bilateral grid for phone exposure changes |

The script checks the data, trains, exports, prints the time of every stage and writes `results/<scene>_result.zip`. Copy that zip back to the laptop and run STEP 3.

## Rules

- Never fake training. COLMAP points are not a splat.
- One video is one scene. Never merge scenes.
- Do not change coordinate frames. The laptop undoes nerfstudio's transform with `dataparser_transforms.json`, so it must stay in the result zip.
- On a shared GPU, note other users' processes in the report, because they slow training.
- If the machine kills long jobs under memory pressure (`systemd-oomd`), start training as its own user service: `systemd-run --user --unit=namma-train --working-directory="$PWD" bash scripts/STEP2_train_on_remote.sh`.

## Tested environment

- Linux, NVIDIA RTX PRO 6000 Blackwell (sm_120), 98 GB VRAM
- conda env `namma3dgs`: Python 3.11, torch 2.7.1+cu128, CUDA 12.8, gsplat 1.4.0, nerfstudio 1.1.5, open3d 0.20.0, numpy 1.26.4
- `TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD=1` is required for torch 2.6 or newer with nerfstudio 1.1.5. The script sets it.
- Blackwell cards need CUDA 12.8 or newer builds.
