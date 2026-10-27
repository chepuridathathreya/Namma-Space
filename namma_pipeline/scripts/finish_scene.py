import argparse
import json
import os
import re
import shutil
import sys
import zipfile

import numpy as np
from scipy.spatial import cKDTree
from scipy.spatial.transform import Rotation

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_collision_from_colmap import read_points
from compress_to_qsplat import vertex_to_qsplat

_PLY_TYPES = {"float": "<f4", "float32": "<f4", "double": "<f8", "float64": "<f8", "uchar": "u1", "uint8": "u1",
              "char": "i1", "int8": "i1", "short": "<i2", "ushort": "<u2", "int": "<i4", "int32": "<i4", "uint": "<u4", "uint32": "<u4"}


def read_ply_vertices(path):
    with open(path, "rb") as f:
        if f.readline().strip() != b"ply":
            die(f"{path} is not a PLY file")
        props, nvert, fmt, in_vertex = [], 0, None, False
        while True:
            line = f.readline().decode("ascii", "replace").strip()
            if line.startswith("format"):
                fmt = line.split()[1]
            elif line.startswith("element"):
                parts = line.split()
                in_vertex = parts[1] == "vertex"
                if in_vertex:
                    nvert = int(parts[2])
                elif nvert:
                    die("PLY has elements after vertex (unexpected for a splat export)")
            elif line.startswith("property") and in_vertex:
                _, typ, name = line.split()
                if typ == "list" or typ not in _PLY_TYPES:
                    die(f"unsupported PLY property type: {line}")
                props.append((name, _PLY_TYPES[typ]))
            elif line == "end_header":
                break
        if fmt != "binary_little_endian":
            die(f"PLY format {fmt} not supported (need binary_little_endian)")
        return np.fromfile(f, dtype=np.dtype(props), count=nvert)


def write_ply_vertices(path, arr):
    head = ["ply", "format binary_little_endian 1.0", f"element vertex {len(arr)}"]
    head += [f"property float {n}" for n in arr.dtype.names] + ["end_header"]
    with open(path, "wb") as f:
        f.write(("\n".join(head) + "\n").encode("ascii"))
        f.write(arr.tobytes())

A_CANDIDATES = {
    "identity": np.eye(3),
    "colmap_to_nerfstudio_swap": np.array([[0, 1, 0], [1, 0, 0], [0, 0, -1]], float),
}


def die(msg):
    sys.exit(f"STOP: {msg}")


def load_result(path, work):
    if path.lower().endswith(".zip"):
        os.makedirs(work, exist_ok=True)
        with zipfile.ZipFile(path) as z:
            z.extractall(work)
        path = work
    ply = dtj = None
    for root, _, files in os.walk(path):
        for f in files:
            if f == "splat.ply":
                ply = os.path.join(root, f)
            elif f == "dataparser_transforms.json":
                dtj = os.path.join(root, f)
    if ply is None:
        die("splat.ply not found in the result")
    if dtj is None:
        die("dataparser_transforms.json missing - cannot align the splat to the collision map")
    return ply, dtj


def affine_to_world(dt, world, A):
    T = np.array(dt["transform"], float)
    s_n = float(dt["scale"])
    R_n, t_n = T[:, :3], T[:, 3]
    s_w = float(world["scale"])
    Rw, tw = np.array(world["rotation"], float), np.array(world["translation"], float)
    M = Rw @ A.T @ R_n.T
    k = s_w / s_n
    off = -s_w * (Rw @ A.T @ R_n.T @ t_n) + tw
    return M, k, off


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--result", required=True)
    ap.add_argument("--world", required=True)
    ap.add_argument("--sparse", required=True)
    ap.add_argument("--grid", required=True)
    ap.add_argument("--name", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--max-gaussians", type=int, default=700000)
    ap.add_argument("--min-opacity", type=float, default=0.05)
    ap.add_argument("--max-scale-m", type=float, default=1.0, help="drop gaussians larger than this (m)")
    ap.add_argument("--max-dist-m", type=float, default=1.2, help="drop gaussians farther than this from any COLMAP point (m)")
    ap.add_argument("--fit-limit-m", type=float, default=0.4, help="STOP if median splat-to-points distance exceeds this (m)")
    ap.add_argument("--viewer-template", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "viewer_template"))
    ap.add_argument("--title", default=None)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)

    print("[1/7] reading result")
    ply_path, dtj_path = load_result(a.result, os.path.join(a.out, "_unzipped"))
    dt = json.load(open(dtj_path))
    world = json.load(open(a.world))
    v = read_ply_vertices(ply_path)
    n = len(v)
    need = ["x", "y", "z", "opacity", "scale_0", "scale_1", "scale_2", "rot_0", "rot_1", "rot_2", "rot_3", "f_dc_0", "f_dc_1", "f_dc_2"]
    missing = [k for k in need if k not in v.dtype.names]
    if missing:
        die(f"PLY lacks fields {missing} - is this a real splatfacto export?")
    print(f"      {n:,} gaussians, nerfstudio scale {dt['scale']:.5f}")
    X = np.column_stack([v["x"], v["y"], v["z"]]).astype(np.float64)
    if not np.isfinite(X).all():
        die("non-finite positions in PLY")

    print("[2/7] testing alignment candidates against the COLMAP points")
    cp, _, err, tl = read_points(os.path.join(a.sparse, "points3D.bin"))
    cp = cp[(err < 2.0) & (tl >= 3)]
    cw = world["scale"] * (np.array(world["rotation"]) @ cp.T).T + np.array(world["translation"])
    tree = cKDTree(cw)
    sub = X[np.random.default_rng(0).choice(n, min(n, 60000), replace=False)]
    scores = {}
    for name, A in A_CANDIDATES.items():
        M, k, off = affine_to_world(dt, world, A)
        w = k * (sub @ M.T) + off
        d = tree.query(w, k=1)[0]
        scores[name] = float(np.median(d))
        print(f"      candidate {name:28s} median distance to COLMAP points: {scores[name]:.3f} m")
    best = min(scores, key=scores.get)
    others = [s for k_, s in scores.items() if k_ != best]
    if scores[best] > a.fit_limit_m:
        die(f"best candidate is still {scores[best]:.2f} m from the COLMAP points (limit {a.fit_limit_m} m). "
            "The splat does not line up with the camera model. Not producing a viewer asset.")
    if others and scores[best] > 0.6 * min(others):
        print("      WARNING: the two candidates fit almost equally well - check the result by eye")
    print(f"      -> using '{best}'")
    M, k, off = affine_to_world(dt, world, A_CANDIDATES[best])

    print("[3/7] transforming gaussians into the viewer world frame")
    W = k * (X @ M.T) + off
    q = np.column_stack([v["rot_0"], v["rot_1"], v["rot_2"], v["rot_3"]]).astype(np.float64)
    q /= np.maximum(np.linalg.norm(q, axis=1, keepdims=True), 1e-9)
    rq = Rotation.from_quat(q[:, [1, 2, 3, 0]])
    q2 = (Rotation.from_matrix(M) * rq).as_quat()[:, [3, 0, 1, 2]]
    logk = np.log(k)
    S = np.column_stack([v["scale_0"], v["scale_1"], v["scale_2"]]).astype(np.float64) + logk
    op = 1.0 / (1.0 + np.exp(-np.asarray(v["opacity"], np.float64)))

    print("[4/7] trimming stray gaussians")
    keep = np.ones(n, bool)
    why = {}
    m = op >= a.min_opacity; why["transparent (<%.2f opacity)" % a.min_opacity] = int((~m & keep).sum()); keep &= m
    m = np.exp(S).max(1) <= a.max_scale_m; why["too large (>%.1f m)" % a.max_scale_m] = int((~m & keep).sum()); keep &= m
    d = np.full(n, np.inf)
    d[keep] = tree.query(W[keep], k=1, workers=-1)[0]
    m = d <= a.max_dist_m; why["far from any observed surface (>%.1f m)" % a.max_dist_m] = int((~m & keep).sum()); keep &= m
    for k_, c in why.items():
        print(f"      removed {c:>9,}  {k_}")
    print(f"      kept {keep.sum():,} of {n:,}")
    if keep.sum() < 50000:
        die("fewer than 50,000 gaussians survived trimming - something is wrong with the result")

    idx = np.nonzero(keep)[0]
    if len(idx) > a.max_gaussians:
        vol = np.exp(S[idx]).prod(1) ** (1 / 3)
        imp = op[idx] * np.clip(vol, 1e-4, None)
        idx = idx[np.argsort(imp)[-a.max_gaussians:]]
        print(f"      thinned to the {len(idx):,} most important (opacity x size) for the web viewer")

    print("[5/7] sanity checks in the world frame")
    Wk = W[idx]
    ys = Wk[:, 1]
    from scipy.signal import find_peaks
    hist, edges = np.histogram(ys, bins=80, range=(-0.5, 3.5))
    sm = np.convolve(hist.astype(float), np.ones(3) / 3, mode="same")
    pk = find_peaks(sm, prominence=0.1 * sm.max())[0]
    floor_y = float(edges[pk[0]] + 0.025) if len(pk) else float("nan")
    print(f"      lowest dense height band (floor) at y = {floor_y:+.2f} m (should be ~0.00)")
    print(f"      height range (1-99%): {np.percentile(ys, 1):+.2f} .. {np.percentile(ys, 99):+.2f} m")
    if not abs(floor_y) <= 0.25:
        print("      WARNING: floor is not at y=0 - splat and collision grid may be offset vertically")

    print("[6/7] writing cleaned PLY + .qsplat")
    names = ["x", "y", "z", "f_dc_0", "f_dc_1", "f_dc_2", "opacity", "scale_0", "scale_1", "scale_2", "rot_0", "rot_1", "rot_2", "rot_3"]
    out = np.empty(len(idx), [(nm, "<f4") for nm in names])
    out["x"], out["y"], out["z"] = Wk[:, 0], Wk[:, 1], Wk[:, 2]
    for j in range(3):
        out[f"f_dc_{j}"] = np.asarray(v[f"f_dc_{j}"])[idx]
        out[f"scale_{j}"] = S[idx, j]
    out["opacity"] = np.asarray(v["opacity"])[idx]
    for j in range(4):
        out[f"rot_{j}"] = q2[idx, j]
    clean_ply = os.path.join(a.out, f"{a.name}_world.ply")
    write_ply_vertices(clean_ply, out)
    qpath = os.path.join(a.out, f"{a.name}.qsplat")
    class _V:
        def __len__(self): return len(out)
        def __getitem__(self, k): return out[k]
        def __contains__(self, k): return k in out.dtype.names
    vertex_to_qsplat(_V(), qpath, max_gaussians=len(idx) + 1)

    print("[7/7] assembling the website (copy of the viewer template, the template itself is untouched)")
    shutil.copyfile(a.grid, os.path.join(a.out, f"{a.name}_collision.json"))
    manifest = {"splat": f"{a.name}.qsplat", "grid": f"{a.name}_collision.json"}
    json.dump(manifest, open(os.path.join(a.out, "manifest.json"), "w"))
    vt = os.path.join(a.out, "site")
    if os.path.exists(vt):
        shutil.rmtree(vt)
    shutil.copytree(a.viewer_template, vt, ignore=shutil.ignore_patterns("assets"))
    os.makedirs(os.path.join(vt, "assets"))
    for f in (f"{a.name}.qsplat", f"{a.name}_collision.json", "manifest.json"):
        shutil.copyfile(os.path.join(a.out, f), os.path.join(vt, "assets", f))
    if a.title:
        index_path = os.path.join(vt, "index.html")
        html = open(index_path, encoding="utf-8").read()
        html = html.replace("<title>NammaSpace Bedroom</title>", f"<title>NammaSpace {a.title}</title>")
        html = html.replace("NammaSpace &middot; Bedroom", f"NammaSpace &middot; {a.title}")
        html = re.sub(r'<p class="sub">.*?</p>', '<p class="sub">Walk-through of a 3D Gaussian splat. Walls and furniture block you using the collision grid built from the scan.</p>', html, flags=re.S)
        open(index_path, "w", encoding="utf-8").write(html)
    shutil.rmtree(os.path.join(a.out, "_unzipped"), ignore_errors=True)
    print(f"\nDONE. gaussians in viewer: {len(idx):,}   qsplat: {os.path.getsize(qpath) / 1e6:.1f} MB")
    print(f"WEBSITE_DIR={os.path.abspath(vt)}")


if __name__ == "__main__":
    main()
