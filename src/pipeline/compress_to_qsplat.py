"""
NammaSpace .qsplat Encoder
Converts raw 3D Gaussian Splatting point cloud / PLY into compressed .qsplat format.
Decoded seamlessly by viewer/main.js at 60 FPS.
"""

import struct
import gzip
import numpy as np

def ply_to_qsplat(ply_path, output_qsplat_path, max_gaussians=700000):
    from plyfile import PlyData  # only needed when reading a PLY here
    print(f"Loading PLY: {ply_path}")
    plydata = PlyData.read(ply_path)
    return vertex_to_qsplat(plydata['vertex'], output_qsplat_path, max_gaussians)


def vertex_to_qsplat(vertex, output_qsplat_path, max_gaussians=700000):
    """Encode gaussians (anything supporting vertex['name'] and 'name' in vertex) as .qsplat."""
    n_total = len(vertex)
    print(f"Total Gaussians in PLY: {n_total:,}")
    
    # Extract positions
    x = np.array(vertex['x'], dtype=np.float32)
    y = np.array(vertex['y'], dtype=np.float32)
    z = np.array(vertex['z'], dtype=np.float32)
    
    # Extract opacities if present
    if 'opacity' in vertex:
        opacity = 1.0 / (1.0 + np.exp(-np.array(vertex['opacity'], dtype=np.float32)))
    else:
        opacity = np.ones(n_total, dtype=np.float32)
        
    # Filter / sort top Gaussians by opacity/importance if over max_gaussians
    if n_total > max_gaussians:
        print(f"Selecting top {max_gaussians:,} most confident Gaussians...")
        indices = np.argsort(opacity)[-max_gaussians:]
        x, y, z, opacity = x[indices], y[indices], z[indices], opacity[indices]
        n = max_gaussians
    else:
        indices = slice(None)
        n = n_total

    # Bounding box
    lx, ly, lz = float(x.min()), float(y.min()), float(z.min())
    hx, hy, hz = float(x.max()), float(y.max()), float(z.max())
    
    # Avoid zero division
    dx = max(hx - lx, 1e-6)
    dy = max(hy - ly, 1e-6)
    dz = max(hz - lz, 1e-6)
    
    # Quantize positions to 16-bit uint (0..65535)
    px = np.clip((x - lx) / dx * 65535, 0, 65535).astype(np.uint16)
    py = np.clip((y - ly) / dy * 65535, 0, 65535).astype(np.uint16)
    pz = np.clip((z - lz) / dz * 65535, 0, 65535).astype(np.uint16)
    P = np.column_stack((px, py, pz)).flatten()
    
    # Extract & quantize scales
    if 'scale_0' in vertex:
        s0 = np.array(vertex['scale_0'][indices], dtype=np.float32)
        s1 = np.array(vertex['scale_1'][indices], dtype=np.float32)
        s2 = np.array(vertex['scale_2'][indices], dtype=np.float32)
    else:
        s0 = s1 = s2 = np.full(n, -4.0, dtype=np.float32)
        
    all_s = np.concatenate([s0, s1, s2])
    sl, sh = float(all_s.min()), float(all_s.max())
    ds = max(sh - sl, 1e-6)
    
    qs0 = np.clip((s0 - sl) / ds * 255, 0, 255).astype(np.uint8)
    qs1 = np.clip((s1 - sl) / ds * 255, 0, 255).astype(np.uint8)
    qs2 = np.clip((s2 - sl) / ds * 255, 0, 255).astype(np.uint8)
    S = np.column_stack((qs0, qs1, qs2)).flatten()
    
    # Extract & quantize colors (RGBA)
    SH_C0 = 0.28209479177387814
    if 'f_dc_0' in vertex:
        r = np.clip((0.5 + SH_C0 * np.array(vertex['f_dc_0'][indices])) * 255, 0, 255).astype(np.uint8)
        g = np.clip((0.5 + SH_C0 * np.array(vertex['f_dc_1'][indices])) * 255, 0, 255).astype(np.uint8)
        b = np.clip((0.5 + SH_C0 * np.array(vertex['f_dc_2'][indices])) * 255, 0, 255).astype(np.uint8)
    elif 'red' in vertex:
        r = np.array(vertex['red'][indices], dtype=np.uint8)
        g = np.array(vertex['green'][indices], dtype=np.uint8)
        b = np.array(vertex['blue'][indices], dtype=np.uint8)
    else:
        r = g = b = np.full(n, 200, dtype=np.uint8)
        
    a = np.clip(opacity * 255, 0, 255).astype(np.uint8)
    C = np.column_stack((r, g, b, a)).flatten()
    
    # Extract & quantize rotations (quaternions)
    if 'rot_0' in vertex:
        q0 = np.array(vertex['rot_0'][indices], dtype=np.float32)
        q1 = np.array(vertex['rot_1'][indices], dtype=np.float32)
        q2 = np.array(vertex['rot_2'][indices], dtype=np.float32)
        q3 = np.array(vertex['rot_3'][indices], dtype=np.float32)
        # Normalize
        qlen = np.sqrt(q0*q0 + q1*q1 + q2*q2 + q3*q3)
        qlen = np.maximum(qlen, 1e-6)
        q0, q1, q2, q3 = q0/qlen, q1/qlen, q2/qlen, q3/qlen
        rq0 = np.clip((q0 * 127.5) + 127.5, 0, 255).astype(np.uint8)
        rq1 = np.clip((q1 * 127.5) + 127.5, 0, 255).astype(np.uint8)
        rq2 = np.clip((q2 * 127.5) + 127.5, 0, 255).astype(np.uint8)
        rq3 = np.clip((q3 * 127.5) + 127.5, 0, 255).astype(np.uint8)
        R = np.column_stack((rq0, rq1, rq2, rq3)).flatten()
    else:
        R = np.zeros(n * 4, dtype=np.uint8)
        
    # Build raw binary payload
    header = struct.pack(
        "<IIffffffff",
        0x5153504C, # Magic 'QSPL'
        n,
        lx, ly, lz,
        hx, hy, hz,
        sl, sh
    )
    
    raw_bytes = header + P.tobytes() + S.tobytes() + C.tobytes() + R.tobytes()
    print(f"Raw buffer size: {len(raw_bytes)/(1024*1024):.2f} MB")
    
    # Compress with GZIP
    compressed = gzip.compress(raw_bytes, compresslevel=6)
    with open(output_qsplat_path, "wb") as f:
        f.write(compressed)
        
    final_size_mb = len(compressed) / (1024 * 1024)
    print(f"Success! Output written to {output_qsplat_path} ({final_size_mb:.2f} MB)")
    return final_size_mb

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("Usage: python compress_to_qsplat.py <input.ply> <output.qsplat> [max_gaussians]")
        sys.exit(1)
    max_g = int(sys.argv[3]) if len(sys.argv) > 3 else 700000
    ply_to_qsplat(sys.argv[1], sys.argv[2], max_g)
