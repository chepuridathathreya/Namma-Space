# NammaSpace capture SOP

Standard operating procedure for filming an indoor space so that it can be rebuilt as a walkable 3D scene. It is written from what we actually did for the Room scene, which gave our best result, and from what went wrong in earlier captures. It does not describe a method we did not use.

## 1. Scope

- One indoor space, such as a room, a hallway or a bedroom, captured with one phone.
- One video is one scene. Scenes are never merged.
- Output of this procedure: a handheld video plus a small set of still photos, both taken by the same person with the same camera settings.

## 2. Equipment and settings

What was used for the Room scene (best result):

| Item | Setting |
|---|---|
| Phone | POCO X6 |
| Mode | Pro (manual) mode, for both video and photos |
| Lens | 0.6x ultra-wide camera. The ultra-wide lens covers more of each wall in a small space |
| Focus | Manual, not automatic |
| Shutter speed | 1/100 s |
| ISO | 800 |
| White balance | 5000 K, fixed |
| Exposure compensation (EV) | 0 |
| Video | 1920 x 1080, 30 frames per second |
| Orientation | Landscape |

Photos used the same Pro mode, the same 0.6x lens, the same orientation and the same aspect ratio as the video, so that the video frames and the photos share one camera model.

Why fixed settings matter: automatic exposure and white balance make the same wall change brightness from frame to frame, which makes matching frames harder and gives the trained splat visible brightness jumps.

Rule: choose the lens once and use it for the whole capture, video and photos together. Do not switch lenses partway through.

## 3. Before filming

- Aim for even lighting, and close curtains if sunlight makes bright patches on the floor or walls. Our Room capture did not have consistent lighting (see section 9).
- Keep people and pets out of the space. Moving things leave ghosts in the splat.
- Wipe the lens.
- Cover mirrors. In the Room we covered the mirror with a towel so that it would not create a ghost reflection.
- Plain white walls and ceilings, glass and glossy floors are hard cases. See section 7.

## 4. The video walk

1. Hold the phone at chest or eye height, in landscape, tilted slightly down.
2. Walk **one continuous lap**, slowly, at about half a metre per second.
3. Turn slowly. Avoid fast pans, and do not stand still.
4. Finish where you started.
5. If you want the ceiling in the same walk, tilt up slowly during the lap, sweep along each wall with overlap, then tilt back down.
6. **Do not walk a second lap at another height or angle.** In our first hallway capture a second lap with the phone raised toward the ceiling made the same wall appear in two places, which gave bent doors and a double window.

The Room video was 8,806 frames (about 4 minutes 53 seconds at 30 frames per second).

## 5. Extra photos for corners and ceiling

A walk shows corners and the top of the walls only briefly. To cover them we took still photos after the video, from the same eye height as the walk:

- Camera at eye level, in landscape, same lens (0.6x) and same Pro settings as the video.
- Tilt **up** for ceiling views, tilt **down** when standing at a corner.
- Go to every corner and take **three to four photos** per corner, a small step apart.
- Each photo should show things the video also shows, so that it can be matched to the video frames.

For the Room we used 26 photos. All 26 were registered by COLMAP.

The photos go in `namma_pipeline/1b_PUT_EXTRA_PHOTOS_HERE/`. The pipeline adds them to the frame set automatically. Empty that folder after each run, or the next scene will pick them up.

## 6. Checks before and after processing

The pipeline performs these checks and stops if one fails:

- **Colour check.** The extracted frames must have real colour. This exists because a bug once produced grey frames.
- **Sharpest-frame selection.** The video is cut into 0.5 s windows and the sharpest frame of each window is kept. A window with no frame above the sharpness threshold is reported. For the Room, 587 frames were picked and no window was left out.
- **Alignment check.** Extracted frames must match the frames that were scored.
- **Camera model health check.** The best COLMAP model must place almost every frame. Room: 613 of 613 frames placed (587 video frames and 26 photos), 135,780 points.

Visual checks you can do yourself:

- Open the sparse reconstruction and confirm the camera path is one clean loop and the walls are single, not doubled.
- Walk the result in the viewer and look for bent doors, doubled windows and floating blobs.

## 7. Known failure cases

| Problem | What it looked like | Cause | What to do |
|---|---|---|---|
| Second lap at another angle | Doubled walls, bent doors | Same wall placed twice | One lap, one height |
| Plain white ceiling not filmed | Black ceiling in the Early Bedroom | Too few features for COLMAP, and not captured | Tilt up slowly during the walk and add ceiling photos |
| Glossy floor, wardrobes, mirrors | Ghost copies below the floor | The splat copies a reflection as a second object | Cover mirrors, as we did with a towel in the Room; the pipeline also removes ghosts under the floor |
| Fast or broken walk | Fewer frames placed | COLMAP loses the path | Slow, continuous walk |
| Ceilings and corners seen briefly | Rough or dark areas | Barely covered | Extra photos as in section 5 |

## 8. What this procedure produced

| Scene | Frames | Held-out PSNR | SSIM | LPIPS |
|---|---:|---:|---:|---:|
| Room (this SOP) | 613 | 27.14 dB | 0.913 | 0.191 |
| Hallway and Bedroom v2 | 868 | 26.46 dB | 0.874 | 0.244 |

The Room is a different scene from the hallway, so these scores show progress in the method, not a controlled comparison. We have not run an experiment that isolates the effect of the extra photos.

## 9. Not recorded and not yet tested

- **Lighting:** not controlled and not consistent across the Room capture, and not measured.
- **Frame rate and resolution:** 1080p at 30 fps was used. A 4K re-capture for sharper frames is still open.
- **Capture time:** roughly 8 to 10 minutes for the video and the photos together, estimated and not timed.

## 10. Round 1 submission

What the Techfest portal asks for: a Google Drive folder link, shared as "Anyone with the link can view", containing the items below.

| Required item | What we provide |
|---|---|
| Technical abstract PDF, at most 5 pages: system architecture, pipeline design, SOP construction details and technical approach | to be written from the technical report and this SOP |
| Proof of concept and web viewer link: a document with a working free-roaming link | a short document containing https://namma-space-documentation.pages.dev/ |
| Demonstration video, 3 to 5 minutes: project scope, capture process and the 3D web walkthrough | the demo video exists and is currently shorter than 3 minutes, so it needs to be extended |
| Code repository: a link or folder with setup instructions to rebuild the model, and sample data in a test directory | the Namma-Space repository, its README and run guide, and `test/sample_scene.zip`; the repository must be viewable by the judges |

Evaluation criteria: SOP and pipeline soundness, visual quality and model fidelity, web viewer performance, and documentation and video clarity.
