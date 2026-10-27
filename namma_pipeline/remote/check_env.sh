#!/bin/bash
echo "== host =="; uname -a; cat /etc/os-release 2>/dev/null | head -3
echo "== cpu/ram/disk =="; lscpu | grep -E "Model name|^CPU\(s\)"; free -h | head -2; df -h . | tail -1
echo "== gpu =="; nvidia-smi --query-gpu=name,memory.total,memory.used,driver_version --format=csv 2>&1
nvidia-smi 2>&1 | grep -i "CUDA Version"
echo "== python / nerfstudio / torch =="
which python python3 conda 2>/dev/null
for PY in python python3; do command -v $PY >/dev/null && { $PY --version; break; }; done
command -v ns-train >/dev/null && { echo "ns-train: $(command -v ns-train)"; ns-train --help 2>&1 | head -2; } || echo "ns-train: NOT FOUND"
python - <<'EOF' 2>&1
try:
    import torch
    print("torch", torch.__version__, "cuda", torch.version.cuda, "available", torch.cuda.is_available())
    print("arch list", torch.cuda.get_arch_list())
    if torch.cuda.is_available():
        x = torch.randn(1024, 1024, device="cuda"); print("cuda matmul ok", float((x @ x).sum()) == float((x @ x).sum()))
except Exception as e:
    print("torch problem:", e)
try:
    import gsplat; print("gsplat", gsplat.__version__)
except Exception as e:
    print("gsplat problem:", e)
EOF
echo "== tools =="; for t in colmap ffmpeg rclone zip unzip git nvcc; do printf "%s: " $t; command -v $t || echo "-"; done
echo "== dataset =="; ls dataset/images | wc -l; ls dataset/colmap/sparse/0
