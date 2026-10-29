# Technical abstract: what goes in it

Portal requirement: one PDF, at most 5 pages, covering system architecture, pipeline design, SOP construction details and the technical approach. There is no minimum length. Target: 4 to 5 pages.

Final file name: `NammaSpace_Technical_Abstract.pdf`

## Page plan

| Page | Section | Source to condense | Status |
|---|---|---|---|
| 1 | Title, byline (Matrix, Chepuri Dathatreya), summary, system architecture with the block diagram | project page, README block diagram | to write |
| 2 | Pipeline design: frame selection, COLMAP, floor and scale, splat training, alignment and compression | report sections 2 to 6 | to write |
| 3 | SOP construction: settings, walk, extra photos, checks, failure cases | `docs/CAPTURE_SOP.md` | to write |
| 4 | Collision and web viewer, performance and the startup quality check | report sections 7 and 8, results page | to write |
| 5 | Results, problems we met, limits and next steps, links | report sections 9, 10 and 12 | to write |

## Figures to include

- [ ] System block diagram (README, redrawn to fit a page)
- [ ] Sparse COLMAP reconstructions with the camera path (`documentation_site/img/hero_sparse.jpg`)
- [ ] Collision grid, Room (`documentation_site/img/room_map.png`)
- [ ] Viewer screenshot with the live map (`documentation_site/img/viewer_ui.jpg`)
- [ ] Evaluation table (Room 27.14 dB, SSIM 0.913, LPIPS 0.191; Hallway and Bedroom 26.46 dB, 0.874, 0.244)

## Facts to confirm before writing

- [ ] Frame rate numbers to quote (24 to 38 fps integrated GPU, 170 to 180 fps RTX 3060)
- [ ] Whether to mention the one-machine training run as untested (the report already says so)
- [ ] Final live viewer link and repository link to print on the last page

# Rest of the Round 1 Drive folder

Folder shared as "Anyone with the link can view".

| Item | Status |
|---|---|
| Technical abstract PDF | to write (above) |
| Web viewer link document | to write: one page with https://namma-space-documentation.pages.dev/ |
| Demo video, 3 to 5 minutes | exists at 2:00, to be extended |
| Code repository link with setup instructions and a `test/` sample | repository and `test/sample_scene.zip` exist; the repository must be viewable by the judges at submission |
