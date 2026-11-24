# room_v1 3DGS training report

- Scene: room_v1 (613 frames, 135,780 COLMAP points), video 1920x1080
- Method: splatfacto, default profile, 30,000 steps, full-size images (images cached on CPU automatically, more than 500 frames)
- Machine: NVIDIA RTX PRO 6000 Blackwell Max-Q (97,887 MiB), torch 2.7.1+cu128, nerfstudio 1.1.5, gsplat 1.4.0
- Times: prepare 5 s, training 819 s, export 19 s, total 843 s
- Peak GPU memory (whole GPU, other users included): 16,251 MiB
- Gaussians exported: 541,337 of 548,781 (7,444 low opacity dropped, 0 NaN/Inf)
- Held-out quality: PSNR 27.14 dB, SSIM 0.913, LPIPS 0.191
- Result zip: room_v1_default_result.zip (112 MB) with splat.ply, config.yml, dataparser_transforms.json, scene.json, timing.txt, step2.log
- Warnings: none. Another process was using about 2.8 GB of the GPU before the start.
