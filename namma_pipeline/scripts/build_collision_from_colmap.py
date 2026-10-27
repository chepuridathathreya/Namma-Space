import argparse
import json
import os
import struct
import sys

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage


def read_images(path):
    names, Rs, ts = [], [], []
    with open(path, "rb") as f:
        n = struct.unpack("<Q", f.read(8))[0]
        for _ in range(n):
            _img_id, qw, qx, qy, qz, tx, ty, tz, _cam = struct.unpack("<i7di", f.read(64))
            name = b""
            while (ch := f.read(1)) != b"\x00":
                name += ch
            n2d = struct.unpack("<Q", f.read(8))[0]
            f.seek(n2d * 24, 1)
            q = np.array([qw, qx, qy, qz])
            q /= np.linalg.norm(q)
            w, x, y, z = q
            R = np.array([
                [1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)],
                [2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)],
                [2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)],
            ])
            names.append(name.decode())
            Rs.append(R)
            ts.append([tx, ty, tz])
    order = np.argsort(names)
    return [names[i] for i in order], np.array(Rs)[order], np.array(ts)[order]


def read_points(path):
    with open(path, "rb") as f:
        data = f.read()
    n = struct.unpack_from("<Q", data, 0)[0]
    xyz = np.empty((n, 3))
    rgb = np.empty((n, 3), np.uint8)
    err = np.empty(n)
    tl = np.empty(n, np.int64)
    off = 8
    for i in range(n):
        _pid, x, y, z, r, g, b, e, L = struct.unpack_from("<Q3d3BdQ", data, off)
        xyz[i] = (x, y, z)
        rgb[i] = (r, g, b)
        err[i] = e
        tl[i] = L
        off += 51 + 8 * L
    return xyz, rgb, err, tl


def write_ply(path, verts, colors, faces=None):
    verts = np.asarray(verts, np.float32)
    colors = np.asarray(colors, np.uint8)
    nf = 0 if faces is None else len(faces)
    head = ("ply\nformat binary_little_endian 1.0\n"
            f"element vertex {len(verts)}\nproperty float x\nproperty float y\nproperty float z\n"
            "property uchar red\nproperty uchar green\nproperty uchar blue\n"
            f"element face {nf}\nproperty list uchar int vertex_indices\nend_header\n")
    v = np.empty(len(verts), [("p", "<f4", 3), ("c", "u1", 3)])
    v["p"], v["c"] = verts, colors
    with open(path, "wb") as f:
        f.write(head.encode())
        f.write(v.tobytes())
        if nf:
            fa = np.empty(nf, [("n", "u1"), ("i", "<i4", 4)])
            fa["n"], fa["i"] = 4, faces
            f.write(fa.tobytes())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sparse", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--name", required=True)
    ap.add_argument("--camera-height", type=float, default=1.4, help="phone height above floor while recording (m)")
    ap.add_argument("--cell", type=float, default=0.1)
    ap.add_argument("--radius", type=float, default=0.25, help="player radius for wall inflation (m)")
    ap.add_argument("--path-free", type=float, default=0.6, help="free space around walked path (m)")
    ap.add_argument("--floor-reach", type=float, default=1.2, help="floor cells within this distance of path are walkable (m)")
    ap.add_argument("--obstacle-min", type=float, default=0.15, help="obstacle band bottom above floor (m)")
    ap.add_argument("--obstacle-max", type=float, default=1.7, help="obstacle band top above floor (m)")
    ap.add_argument("--min-hits", type=int, default=3, help="points per cell to count as obstacle")
    ap.add_argument("--body-clear", type=float, default=0.2, help="you physically walked here: no obstacles within this of the path (m)")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)

    print(f"[1/6] reading COLMAP model: {a.sparse}")
    names, R, t = read_images(os.path.join(a.sparse, "images.bin"))
    xyz, rgb, err, tl = read_points(os.path.join(a.sparse, "points3D.bin"))
    keep = (err < 2.0) & (tl >= 3)
    print(f"      cameras: {len(names)}   points: {len(xyz)}   clean points (err<2px, track>=3): {keep.sum()}")
    xyz, rgb = xyz[keep], rgb[keep]

    centers = -np.einsum("nji,nj->ni", R, t)
    cam_up = -R[:, 1, :]
    cam_fwd = R[:, 2, :]

    print("[2/6] finding up direction from the floor under the walked path")
    up = cam_up.mean(0)
    up /= np.linalg.norm(up)
    agree = (cam_up @ up).mean()
    print(f"      mean camera-up agreement: {agree:.3f} (1.0 = phone perfectly upright)")
    if agree < 0.7:
        sys.exit("ABORT: camera up directions disagree too much; cannot trust gravity estimate")
    sub = centers[:: max(1, len(centers) // 300)]
    ext = np.linalg.norm(np.ptp(centers, 0))
    reach = 0.05 * ext
    for _ in range(4):
        h_all = xyz @ up
        flat_pts = xyz - np.outer(h_all, up)
        floor_samples = []
        for c in sub:
            cf = c - (c @ up) * up
            near = np.linalg.norm(flat_pts - cf, axis=1) < reach
            if near.sum() < 50:
                continue
            hn = h_all[near]
            low = hn <= np.percentile(hn, 3)
            floor_samples.append(xyz[near][low])
        F = np.concatenate(floor_samples)
        rng = np.random.default_rng(0)
        best, best_n = None, 0
        tol = 0.01 * ext
        for _ in range(300):
            a3 = F[rng.choice(len(F), 3, replace=False)]
            nrm = np.cross(a3[1] - a3[0], a3[2] - a3[0])
            if np.linalg.norm(nrm) < 1e-9:
                continue
            nrm /= np.linalg.norm(nrm)
            inl = np.abs((F - a3[0]) @ nrm) < tol
            if inl.sum() > best_n:
                best, best_n = inl, inl.sum()
        Fi = F[best]
        nrm = np.linalg.svd(Fi - Fi.mean(0), full_matrices=False)[2][2]
        up = nrm * np.sign(nrm @ cam_up.mean(0))
    floor_inlier = best_n / len(F)
    print(f"      floor plane fit: {best_n} of {len(F)} floor samples on one plane ({floor_inlier * 100:.0f}%)")
    print(f"      phone tilt vs floor-up: {np.degrees(np.arccos(np.clip(cam_up.mean(0) / np.linalg.norm(cam_up.mean(0)) @ up, -1, 1))):.1f} deg")

    flat = centers - centers.mean(0)
    flat -= np.outer(flat @ up, up)
    X = np.linalg.svd(flat, full_matrices=False)[2][0]
    X -= (X @ up) * up
    X /= np.linalg.norm(X)
    Z = np.cross(X, up)
    Rot = np.stack([X, up, Z])
    assert np.linalg.det(Rot) > 0.99

    print("[3/6] finding floor and metric scale")
    h_pts = xyz @ up
    h_cam = centers @ up
    floor_h = np.median(Fi @ up)
    cam_h = np.median(h_cam)
    spread = np.percentile(h_cam, 90) - np.percentile(h_cam, 10)
    scale = a.camera_height / (cam_h - floor_h)
    print(f"      floor is {cam_h - floor_h:.3f} COLMAP units below the median camera -> scale {scale:.4f} m/unit")
    print(f"      camera height range while walking (10-90%): {spread * scale:.2f} m")
    resid = (Fi @ up - floor_h) * scale
    print(f"      floor flatness (inliers, 5-95%): {np.percentile(resid, 5):+.2f} .. {np.percentile(resid, 95):+.2f} m")

    T = -scale * (Rot @ (up * floor_h))
    W = (scale * (Rot @ xyz.T)).T + T
    Wc = (scale * (Rot @ centers.T)).T + T
    shift = np.array([-np.median(Wc[:, 0]), 0.0, -np.median(Wc[:, 2])])
    T += shift
    W += shift
    Wc += shift

    ceil = float(np.percentile(W[:, 1], 99.5))
    hh, ee = np.histogram(W[:, 1], bins=30, range=(0.2, 1.2))
    furn = ee[hh.argmax()] + 0.5 * (ee[1] - ee[0])
    print(f"      sanity: top of scene ~{ceil:.2f} m (ceiling is usually 2.6-3.1 m); "
          f"strongest furniture surface at ~{furn:.2f} m (bed ~0.45-0.55, desk ~0.75)")
    if not 2.0 < ceil < 3.6:
        print("      WARNING: scale looks wrong - re-run with a different --camera-height")

    print("[4/6] rasterising occupancy grid")
    pad = 1.0
    mn = np.minimum(Wc[:, [0, 2]].min(0), np.percentile(W[:, [0, 2]], 1, axis=0)) - pad
    mx = np.maximum(Wc[:, [0, 2]].max(0), np.percentile(W[:, [0, 2]], 99, axis=0)) + pad
    cols, rows = (np.ceil((mx - mn) / a.cell)).astype(int)

    def to_cells(P):
        c = np.floor((P[:, 0] - mn[0]) / a.cell).astype(int)
        r = np.floor((P[:, 2] - mn[1]) / a.cell).astype(int)
        ok = (c >= 0) & (r >= 0) & (c < cols) & (r < rows)
        return r[ok], c[ok]

    band = (W[:, 1] > a.obstacle_min) & (W[:, 1] < a.obstacle_max)
    hits = np.zeros((rows, cols), np.int32)
    np.add.at(hits, to_cells(W[band]), 1)
    occupied = hits >= a.min_hits

    floor_pts = np.abs(W[:, 1]) < 0.08
    floor_seen = np.zeros((rows, cols), bool)
    floor_seen[to_cells(W[floor_pts])] = True

    path = np.zeros((rows, cols), bool)
    seg = []
    for p, q in zip(Wc[:-1], Wc[1:]):
        k = max(2, int(np.linalg.norm(q - p) / (a.cell * 0.5)))
        seg.append(p + np.linspace(0, 1, k)[:, None] * (q - p))
    path[to_cells(np.concatenate(seg))] = True

    dist_to_path = ndimage.distance_transform_edt(~path) * a.cell
    occupied &= dist_to_path > a.body_clear
    free = (dist_to_path <= a.path_free) | (floor_seen & (dist_to_path <= a.floor_reach))
    free &= ~occupied
    dist_to_obst = ndimage.distance_transform_edt(~occupied) * a.cell
    blocked = ~free | (dist_to_obst < a.radius)
    blocked[path & ~occupied] = False

    lab, nlab = ndimage.label(~blocked, structure=np.ones((3, 3)))
    sizes = ndimage.sum(np.ones_like(lab), lab, range(1, nlab + 1))
    main = sizes.argmax() + 1
    frac = (lab[path] == main).mean()
    print(f"      walkable regions: {nlab}   path cells inside largest region: {frac * 100:.1f}%")
    blocked |= lab != main
    if frac < 0.9:
        print("      WARNING: walked path is split into separate regions - check the preview image")
    print(f"      grid {cols} x {rows} cells ({cols * a.cell:.1f} m x {rows * a.cell:.1f} m), "
          f"obstacle cells {occupied.sum()}, walkable cells {(~blocked).sum()}")

    print("[5/6] writing outputs")
    f0 = (scale * (Rot @ cam_fwd[0]))
    f0[1] = 0
    f0 /= np.linalg.norm(f0) or 1
    grid = {
        "cell": a.cell, "originX": float(mn[0]), "originZ": float(mn[1]),
        "cols": int(cols), "rows": int(rows), "floorY": 0.0, "eyeHeight": 1.6, "radius": a.radius,
        "start": {"x": float(Wc[0, 0]), "z": float(Wc[0, 2]), "forwardX": float(f0[0]), "forwardZ": float(f0[2])},
        "occupied": ["".join("1" if v else "0" for v in row) for row in occupied],
        "blocked": ["".join("1" if v else "0" for v in row) for row in blocked],
    }
    grid_path = os.path.join(a.out, f"{a.name}_collision.json")
    with open(grid_path, "w") as f:
        json.dump(grid, f)
    world = {
        "note": "world = scale * rotation @ colmap + translation  (Y up, floor y=0, metres)",
        "scale": float(scale), "rotation": Rot.tolist(), "translation": T.tolist(),
        "camera_height_assumed_m": a.camera_height, "ceiling_m": None if ceil is None else float(ceil),
        "source_sparse": os.path.abspath(a.sparse), "cameras": len(names),
    }
    with open(os.path.join(a.out, "world.json"), "w") as f:
        json.dump(world, f, indent=2)

    px = 6
    img = Image.new("RGB", (cols * px, rows * px), (20, 20, 24))
    d = ImageDraw.Draw(img)
    for r in range(rows):
        for c in range(cols):
            col = (190, 70, 60) if occupied[r, c] else (90, 40, 40) if blocked[r, c] else (60, 140, 90)
            if blocked[r, c] and not occupied[r, c] and not free[r, c]:
                col = (32, 32, 38)
            d.rectangle([c * px, r * px, c * px + px - 1, r * px + px - 1], fill=col)
    pr, pc = to_cells(Wc)
    for r, c in zip(pr, pc):
        d.ellipse([c * px + 1, r * px + 1, c * px + px - 2, r * px + px - 2], fill=(240, 220, 90))
    sr, sc = to_cells(Wc[:1])
    d.ellipse([sc[0] * px - 6, sr[0] * px - 6, sc[0] * px + 6, sr[0] * px + 6], outline=(80, 180, 255), width=3)
    img.save(os.path.join(a.out, f"{a.name}_collision_preview.png"))

    write_ply(os.path.join(a.out, f"{a.name}_points_world.ply"), W, rgb)
    quads, qcol = [], []
    for r in range(rows):
        for c in range(cols):
            if occupied[r, c]:
                col, y = (220, 60, 50), 0.02
            elif not blocked[r, c]:
                col, y = (60, 180, 90), 0.01
            elif free[r, c]:
                col, y = (120, 40, 40), 0.01
            else:
                continue
            x0, z0 = mn[0] + c * a.cell, mn[1] + r * a.cell
            quads.append([[x0, y, z0], [x0 + a.cell, y, z0], [x0 + a.cell, y, z0 + a.cell], [x0, y, z0 + a.cell]])
            qcol.append([col] * 4)
    quads = np.array(quads).reshape(-1, 3)
    write_ply(os.path.join(a.out, f"{a.name}_grid_world.ply"), quads, np.array(qcol).reshape(-1, 3),
              np.arange(len(quads)).reshape(-1, 4))
    write_ply(os.path.join(a.out, f"{a.name}_camera_path.ply"), Wc, np.tile([250, 220, 60], (len(Wc), 1)))

    print(f"[6/6] done\n      {grid_path}\n      {os.path.join(a.out, 'world.json')}\n"
          f"      {os.path.join(a.out, a.name + '_collision_preview.png')}  (green=walkable, red=obstacle, yellow=your path, blue=start)\n"
          f"      MeshLab: {a.name}_points_world.ply + {a.name}_grid_world.ply + {a.name}_camera_path.ply")


if __name__ == "__main__":
    main()
