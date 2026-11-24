# Training on a free cloud GPU (STEP 2)

STEP 2 needs an NVIDIA GPU. Without one, train in a free notebook. Both notebooks are in `src/training/`.

| Notebook | GPU | Where the data goes |
|---|---|---|
| `NAMMA_STEP2_colab.ipynb` | free Colab T4 | bundle zip in a Google Drive folder named `namma`; the result is saved back there |
| `NAMMA_STEP2_kaggle.ipynb` | free Kaggle T4 (about 30 GPU hours a week) | bundle zip uploaded as a private Kaggle Dataset |

## Steps

1. Run STEP 1 on your computer (`scripts/windows/step1_prepare.bat` or `python src/pipeline/step1_prepare.py`). It writes `workspace/to_gpu/<scene>_to_remote.zip`.
2. Upload that zip and run the notebook: 30,000 steps take about 25 minutes on a T4. Set `ITERS = 2000` for a quick test.
3. Download the result zip into `workspace/from_gpu/`.
4. Run STEP 3 (`scripts/windows/step3_finish.bat` or `python src/pipeline/step3_finish.py`).

## Settings to know

- The notebooks set `DOWNSCALE = 2`, so training sees half-size images (about 960 px wide). This keeps memory within a T4. The Room scene at full 1080p peaked at 16,251 MiB on a larger card, so full size will probably not fit a 16 GB T4.
- On the 4K scene both notebooks gave the same score (Kaggle 29.12 dB, Colab 29.12 dB), so results do not depend on the platform.
