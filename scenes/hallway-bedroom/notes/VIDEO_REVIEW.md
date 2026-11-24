# Video review - hallway_bedroom_v2.mp4

Reviewed 2026-10-15, before running the pipeline. I looked at a frame every 5 seconds (89 frames, six contact sheets) and ran the same sharpness check that STEP 1 runs, on the video and, for comparison, on the old v1 video.

## The video

| | |
|---|---|
| File | `namma_pipeline/1_PUT_VIDEO_HERE/hallway_bedroom_v2.mp4` (renamed from `VID_20261015_190018.mp4`, so the scene is called `hallway_bedroom_v2`) |
| Length / size | 7 min 26 s, 1920x1080, landscape, 30 fps, h264, 1.1 GB |
| Frames at 2 per second | 893 |

## What is in it

**Two laps of the same route, both at eye level.** Lap 1 is about 0:00-3:55, lap 2 about 4:00-7:20: kitchen with fridge and water can, TV unit, the doorway, the bedroom (grey wardrobe, bed, blue flower door, window), back through the brown door, the empty room with the wooden door and sewing table, and round to the kitchen again.

- **No tilting toward the ceiling.** The phone stays at the same angle, slightly down. This avoids the v1 mistake.
- Two laps at the same angle and height are fine. The repeated route even helps COLMAP close the loop.
- The ceiling is almost never visible (a little at 0:35, 4:10, 6:45). Expect the ceiling to come out empty. The plan is a plain ceiling drawn in the viewer.
- Lighting is even. No people in shot.

## Numbers (same check as STEP 1)

| | v2 (this video) | v1 (the bent one) |
|---|---:|---:|
| Median sharpness (Laplacian variance) | **160** | 124 |
| Frames under the blur threshold (35) | **6 (0.7%)** | 25 (3.1%) |
| Nearly featureless frames (blank wall) | **18 (2%)** | 63 (8%) |
| Standing still (near-duplicates) | 0 | 0 |
| Fast turning (large change between frames) | 49% | 42% |

Sharper, far fewer blank-wall frames, so it should register better than v1. The fast-turning figure is similar and slightly higher: expected, because you turn often. COLMAP matches each frame with its 10 neighbours, which compensates.

## Weak spots (COLMAP may drop or mis-place these frames)

| When | What | Why it is hard |
|---|---|---|
| 1:53-1:57 and 5:54-5:56 | plain white wall (and the blurriest frames of the video) | nothing to lock onto |
| 6:32-6:33 | curtain filling the frame | same |
| 0:25-0:30, 2:25-2:35, 5:40-5:50, 6:25-6:30, 7:10 | camera very close to the window grill, wardrobe, door, curtain, switch plate | too close: no depth difference between frames, and the frame is one flat surface |
| 3:00-3:20 | large empty room: white walls, patterned floor | mostly the floor pattern helps |

A few seconds of such frames is normal. Registration will only suffer if there are long gaps.

## What to watch in STEP 1

- "frames placed" of 893 (after the blur filter): **80% or more is good**, below 80% STEP 1 warns, below 40% it stops.
- **One big model.** A warning about a second large model means the walk split into pieces.
- Expected time: v1 had 760 frames and COLMAP took about 27 minutes; this has about 890, so **expect roughly 30-40 minutes** for STEP 1. Training on the remote PC should take about 12-16 minutes (709 frames took 12 min).
- If few frames are placed, try again with `--fps 3` (more overlap, longer). Run STEP 1 from a terminal for that: `cd /d "D:\Namma space\namma_pipeline"` then `STEP1_prepare_video.bat --fps 3`.

## For the next shoot

Hold the phone farther from walls (about 1 m or more), and when you pass a plain wall or curtain, keep walking along it with something textured in the corner of the frame instead of filling the frame with it.
