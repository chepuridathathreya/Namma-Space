# hallway_bedroom_4k (vid_20261114_142211) training report

- Capture: 14 Nov 2026, one video of 3840 x 2160, 7 min 43 s, recorded at about 14.9 frames per second (6,912 frames), plus 79 extra photos. Phone settings were not written down.
- STEP 1 (laptop, 52 min 45 s, default incremental mapper): 937 sharp frames picked at 1920 x 1080, 47 half-second windows had no sharp frame. COLMAP placed 954 of 1,016 images (94%), 143,053 points, all 79 photos placed. COLMAP took 50 min 7 s, of which the mapper took 40 min 36 s.
- STEP 2 (free cloud T4, default profile, 30,000 steps, half-size images, images cached on the CPU):
  - Kaggle: 1,448 s, 393,733 gaussians, PSNR 29.1212, SSIM 0.9116, LPIPS 0.1439.
  - Colab: 1,534 s, 394,846 gaussians, PSNR 29.1156, SSIM 0.9116, LPIPS 0.1438. The Colab result is the one used for the site (it looked sharper in the viewer).
- STEP 3 (laptop, 15 s): 344,087 gaussians in the site after cleaning (3,640 ghosts below the floor removed), 5.4 MB qsplat. Walkable cells: camera-path map 1,065, splat map 983, combined 1,131.
- 16 Nov: the grid was rebuilt with obstacle heights (1,708 of 1,751 obstacle cells, tallest 2.31 m). The walkable cells did not change.
- Places: 15 in `site/assets/pois.json`. The first 14: 13 placed from headless aim shots, 1 (sink) added by hand in the editor.
- Known gaps: parts of the rooms were never filmed, and the ceiling is rough. These are capture gaps, not training faults.
- Deployed at https://namma-space.pages.dev/hallway-4k/.
- 25 Nov: full-colour Spark file exported from the Colab splat.ply with `src/pipeline/export_spark.py` (SH degree 3, 13.0 MiB, one file). All 344,087 published splats were found (median offset 0.07 mm), 344,084 kept. The site now loads it; `?colour=base` still shows the old file.
- 25 Nov: places re-tagged in STEP 4. Now 14 places (Kitchen Cabinet and Ceiling Fan removed, Washroom and a new Switchboard added). 12 have a hand-set stand spot; TV and Fridge use the automatic one. Every arrival was checked on desktop and at phone size.
