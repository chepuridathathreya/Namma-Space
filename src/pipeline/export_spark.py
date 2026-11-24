import argparse
import gzip
import json
import os
import struct
import sys

import numpy as np
from scipy.spatial import cKDTree

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from finish_scene import read_ply_vertices

SH_C0 = 0.28209479177387814
SPZ_MAGIC = 0x5053474E
SH_COUNT = {0: 0, 1: 3, 2: 8, 3: 15}


def sigmoid(x):
    return 1.0 / (1.0 + np.exp(-x))


def read_qsplat(path):
    raw = gzip.decompress(open(path, "rb").read())
    magic, n, lx, ly, lz, hx, hy, hz, sl, sh = struct.unpack("<IIffffffff", raw[:40])
    o = 40
    p = np.frombuffer(raw, np.uint16, n * 3, o).reshape(n, 3).astype(np.float64); o += n * 6
    s = np.frombuffer(raw, np.uint8, n * 3, o).reshape(n, 3).astype(np.float64); o += n * 3
    c = np.frombuffer(raw, np.uint8, n * 4, o).reshape(n, 4).astype(np.float64)
    lo, hi = np.array([lx, ly, lz]), np.array([hx, hy, hz])
    return {
        "pos": lo + p / 65535 * (hi - lo),
        "logscale": sl + s / 255 * (sh - sl),
        "rgba": c,
        "scale_step": (sh - sl) / 255,
    }


def descriptor(rgba, logscale):
    s = np.sort(logscale, axis=1)
    return np.column_stack([rgba[:, :4], (s[:, 1] - s[:, 0]) * 10, (s[:, 2] - s[:, 0]) * 10])


def umeyama(src, dst):
    mu_s, mu_d = src.mean(0), dst.mean(0)
    a, b = src - mu_s, dst - mu_d
    cov = b.T @ a / len(src)
    u, d, vt = np.linalg.svd(cov)
    e = np.eye(3)
    if np.linalg.det(u) * np.linalg.det(vt) < 0:
        e[2, 2] = -1
    r = u @ e @ vt
    var = (a ** 2).sum() / len(src)
    k = np.trace(np.diag(d) @ e) / var
    t = mu_d - k * r @ mu_s
    return k, r, t


def register(ply_pos, ply_desc, q_pos, q_desc, seed=0):
    tree = cKDTree(ply_desc)
    dist, nn = tree.query(q_desc, k=1, workers=-1)
    good = np.nonzero(dist < 1.0)[0]
    if len(good) < 1000:
        raise SystemExit(f"only {len(good)} attribute matches between the PLY and the qsplat; they are not the same splat")
    src, dst = ply_pos[nn[good]], q_pos[good]
    rng = np.random.default_rng(seed)
    best, best_in = None, -1
    extent = np.linalg.norm(q_pos.max(0) - q_pos.min(0))
    thr = 0.002 * extent
    for _ in range(3000):
        pick = rng.choice(len(src), 4, replace=False)
        k, r, t = umeyama(src[pick], dst[pick])
        if not np.isfinite(k) or k <= 0:
            continue
        res = np.linalg.norm(k * src @ r.T + t - dst, axis=1)
        inl = int((res < thr).sum())
        if inl > best_in:
            best_in, best = inl, res < thr
    k, r, t = umeyama(src[best], dst[best])
    return k, r, t, best_in, len(good)


def quant_u8(x):
    return np.clip(np.round(x), 0, 255).astype(np.uint8)


def quant_sh(x, bucket):
    q = np.round(x * 128.0).astype(np.int32) + 128
    q = (q + bucket // 2) // bucket * bucket
    return np.clip(q, 0, 255).astype(np.uint8)


def pack_quats(q_wxyz):
    q = q_wxyz[:, [1, 2, 3, 0]].astype(np.float64)
    q /= np.maximum(np.linalg.norm(q, axis=1, keepdims=True), 1e-12)
    big = np.argmax(np.abs(q), axis=1)
    flip = q[np.arange(len(q)), big] < 0
    q[flip] *= -1
    comp = big.astype(np.uint32)
    for i in range(4):
        use = big != i
        neg = (q[:, i] < 0).astype(np.uint32)
        mag = np.floor(511 * (np.abs(q[:, i]) / np.sqrt(0.5)) + 0.5).astype(np.uint32)
        mag = np.minimum(mag, 511)
        comp = np.where(use, (comp << np.uint32(10)) | (neg << np.uint32(9)) | mag, comp)
    return comp.astype("<u4").view(np.uint8).reshape(-1, 4)


def encode_spz(pos, opacity_logit, dc, logscale, quat_wxyz, rest, degree, frac_bits, sh_bits=8):
    n = len(pos)
    header = struct.pack("<IIIBBBB", SPZ_MAGIC, 3, n, degree, frac_bits, 0, 0)
    fixed = np.clip(np.round(pos * (1 << frac_bits)), -(1 << 23), (1 << 23) - 1).astype("<i4")
    p24 = fixed.view(np.uint8).reshape(n, 3, 4)[:, :, :3].reshape(-1)
    alpha = quant_u8(sigmoid(opacity_logit) * 255.0)
    colors = quant_u8(dc * (0.15 * 255.0) + 0.5 * 255.0).reshape(-1)
    scales = quant_u8((logscale + 10.0) * 16.0).reshape(-1)
    rots = pack_quats(quat_wxyz).reshape(-1)
    parts = [header, p24.tobytes(), alpha.tobytes(), colors.tobytes(), scales.tobytes(), rots.tobytes()]
    k = SH_COUNT[degree]
    if k:
        sh = np.empty((n, k, 3), np.uint8)
        bucket = 1 << (8 - sh_bits)
        sh[:, :3] = quant_sh(rest[:, :3], bucket)
        if k > 3:
            sh[:, 3:] = quant_sh(rest[:, 3:k], bucket)
        parts.append(sh.reshape(-1).tobytes())
    return gzip.compress(b"".join(parts), compresslevel=9)


def main():
    ap = argparse.ArgumentParser(description="Export a full-colour Spark asset (SPZ) for a scene that already has a published .qsplat")
    ap.add_argument("--ply", required=True, help="splat.ply exported by nerfstudio (with f_rest)")
    ap.add_argument("--assets", required=True, help="the scene's site/assets folder (manifest.json, .qsplat, collision grid)")
    ap.add_argument("--sh", type=int, default=3, choices=[0, 1, 2, 3])
    ap.add_argument("--max-mib", type=float, default=24.0, help="split into files no larger than this")
    ap.add_argument("--frac-bits", type=int, default=16)
    ap.add_argument("--sh-bits", type=int, default=8, help="bits kept per view-dependent colour coefficient (Niantic uses 5 and 4)")
    ap.add_argument("--match-m", type=float, default=0.002, help="a published splat counts as found when a PLY splat lies within this distance")
    a = ap.parse_args()

    manifest_path = os.path.join(a.assets, "manifest.json")
    manifest = json.load(open(manifest_path))
    name = os.path.splitext(manifest["splat"])[0]
    print(f"[1/5] reading {a.ply}")
    v = read_ply_vertices(a.ply)
    n = len(v)
    pos = np.column_stack([v["x"], v["y"], v["z"]]).astype(np.float64)
    dc = np.column_stack([v["f_dc_0"], v["f_dc_1"], v["f_dc_2"]]).astype(np.float64)
    op = np.asarray(v["opacity"], np.float64)
    ls = np.column_stack([v["scale_0"], v["scale_1"], v["scale_2"]]).astype(np.float64)
    quat = np.column_stack([v["rot_0"], v["rot_1"], v["rot_2"], v["rot_3"]]).astype(np.float64)
    rest_names = sorted([f for f in v.dtype.names if f.startswith("f_rest_")], key=lambda s: int(s.split("_")[-1]))
    per_channel = len(rest_names) // 3
    rest = np.zeros((n, 15, 3))
    if per_channel:
        flat = np.column_stack([v[f] for f in rest_names]).astype(np.float64).reshape(n, 3, per_channel)
        rest[:, :per_channel] = flat.transpose(0, 2, 1)
    print(f"      {n:,} splats, {per_channel} SH coefficients per channel beyond the base colour")

    print(f"[2/5] matching against the published {manifest['splat']}")
    q = read_qsplat(os.path.join(a.assets, manifest["splat"]))
    rgba = np.column_stack([np.floor(np.clip(0.5 + SH_C0 * dc, 0, 1) * 255), np.floor(sigmoid(op) * 255)])
    k, r, t, inliers, matched = register(pos, descriptor(rgba, ls), q["pos"], descriptor(q["rgba"], q["logscale"]))
    world = k * pos @ r.T + t
    d, nn = cKDTree(world).query(q["pos"], k=1, workers=-1)
    print(f"      scale {k:.5f}, {inliers:,} of {matched:,} attribute matches agree")
    found = d <= a.match_m
    keep = np.zeros(n, bool)
    keep[nn[found]] = True
    print(f"      {int(found.sum()):,} of {len(q['pos']):,} published splats found (median offset {np.median(d[found]) * 1000:.2f} mm), {int(keep.sum()):,} kept")
    if found.sum() < 0.9 * len(q["pos"]):
        raise SystemExit("fewer than 90% of the published splats were found in the PLY, so the alignment is wrong")

    print(f"[3/5] encoding SPZ with SH degree {a.sh}")
    idx = np.nonzero(keep)[0]
    vol = np.exp(ls[idx]).prod(1)
    idx = idx[np.argsort(-sigmoid(op[idx]) * np.cbrt(vol))]
    sample = encode_spz(pos[idx[:20000]], op[idx[:20000]], dc[idx[:20000]], ls[idx[:20000]], quat[idx[:20000]], rest[idx[:20000]], a.sh, a.frac_bits, a.sh_bits)
    per_splat = len(sample) / 20000
    parts = max(1, int(np.ceil(per_splat * len(idx) / (a.max_mib * 1024 * 1024) * 1.04)))
    files = []
    for i, chunk in enumerate(np.array_split(idx, parts)):
        blob = encode_spz(pos[chunk], op[chunk], dc[chunk], ls[chunk], quat[chunk], rest[chunk], a.sh, a.frac_bits, a.sh_bits)
        fname = f"{name}_sh{a.sh}_{i + 1}of{parts}.spz"
        open(os.path.join(a.assets, fname), "wb").write(blob)
        files.append(fname)
        print(f"      {fname}: {len(chunk):,} splats, {len(blob) / 1048576:.1f} MiB")
        if len(blob) > 25 * 1024 * 1024:
            raise SystemExit(f"{fname} is over the 25 MiB Cloudflare Pages limit")

    print("[4/5] writing the transform into manifest.json")
    m = np.eye(4)
    m[:3, :3] = k * r
    m[:3, 3] = t
    manifest["spark"] = {"files": files, "matrix": [float(x) for x in m.T.reshape(-1)], "sh": a.sh, "count": int(len(idx))}
    json.dump(manifest, open(manifest_path, "w"))
    print("[5/5] done")


if __name__ == "__main__":
    main()
