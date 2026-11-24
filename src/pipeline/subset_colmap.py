#!/usr/bin/env python3
"""
Build a SMALL subset COLMAP model so splatfacto can be smoke-tested inside the
6.7 GiB WSL cap.

Why: nerfstudio's full_images_datamanager undistorts every training image into
RAM before the first step. For 359 frames that exceeds the WSL cap. Reducing the
frame count is the only lever that works without a host-level .wslconfig change.

Writes:  <dest>/colmap/sparse/0/{cameras,images,points3D,project.ini,rigs,frames}.bin
Only cameras/images/points3D are rewritten. Cameras are copied verbatim and the
focal length is left untouched, so the subset stays geometrically valid.

Usage: subset_colmap.py <src_sparse_dir> <dst_sparse_dir> <keep_csv_or_count>
"""
import os
import shutil
import struct
import sys


def read_cameras(path):
    with open(path, "rb") as f:
        n = struct.unpack("<Q", f.read(8))[0]
        out = []
        for _ in range(n):
            cid, mid, w, h = struct.unpack("<iiQQ", f.read(24))
            out.append({"camera_id": cid, "model_id": mid, "width": w, "height": h})
    return out


def write_cameras(path, cams):
    with open(path, "wb") as f:
        f.write(struct.pack("<Q", len(cams)))
        for c in cams:
            f.write(struct.pack("<iiQQ", c["camera_id"], c["model_id"], c["width"], c["height"]))
            for v in c["params"]:
                f.write(struct.pack("<d", v))


def read_camera_params(path, cams):
    """Second pass to recover the double params per camera (model dependent)."""
    with open(path, "rb") as f:
        n = struct.unpack("<Q", f.read(8))[0]
        idx = 0
        while True:
            chunk = f.read(24)
            if len(chunk) < 24:
                break
            cid, mid, w, h = struct.unpack("<iiQQ", chunk)
            if mid == 0:      # SIMPLE_PINHOLE
                npar = 3
            elif mid == 1:    # PINHOLE
                npar = 4
            elif mid == 2:    # SIMPLE_RADIAL
                npar = 4
            elif mid == 3:    # RADIAL
                npar = 5
            elif mid == 4:    # OPENCV
                npar = 8
            elif mid == 5:    # FULL_OPENCV
                npar = 12
            else:
                npar = 4
            raw = f.read(8 * npar)
            cams[idx]["params"] = list(struct.unpack("<" + "d" * npar, raw))
            idx += 1
            if idx >= n:
                break
    return cams


def read_images(path):
    with open(path, "rb") as f:
        n = struct.unpack("<Q", f.read(8))[0]
        out = []
        for _ in range(n):
            iid, qw, qx, qy, qz, tx, ty, tz, cid = struct.unpack("<idddddddi", f.read(8 + 56))
            name = b""
            while True:
                ch = f.read(1)
                if ch == b"\0" or not ch:
                    break
                name += ch
            out.append({"image_id": iid, "qvec": (qw, qx, qy, qz),
                        "tvec": (tx, ty, tz), "camera_id": cid,
                        "name": name.decode("utf-8", "replace")})
            # points2D block: uint64 count then count of xy + point3D_id (2*8+8)
            npts = struct.unpack("<Q", f.read(8))[0]
            f.read(npts * 24)
    return out


def write_images(path, images):
    with open(path, "wb") as f:
        f.write(struct.pack("<Q", len(images)))
        for im in images:
            f.write(struct.pack("<idddddddi", im["image_id"], *im["qvec"], *im["tvec"], im["camera_id"]))
            f.write(im["name"].encode("utf-8") + b"\0")
            f.write(struct.pack("<Q", len(im["p2d"])))
            for x, y, pid in im["p2d"]:
                f.write(struct.pack("<ddq", x, y, pid))


def read_points(path):
    with open(path, "rb") as f:
        n = struct.unpack("<Q", f.read(8))[0]
        out = []
        for _ in range(n):
            pid, x, y, z, r, g, b, err = struct.unpack("<QdddBBBd", f.read(8 + 24 + 3 + 8))
            # COLMAP writes the track as a length-prefixed vector:
            # uint64 count, then count x (image_id int32, point2D_idx int32)
            ntrack = struct.unpack("<Q", f.read(8))[0]
            track = [struct.unpack("<ii", f.read(8)) for _ in range(ntrack)]
            out.append({"point3D_id": pid, "xyz": (x, y, z), "rgb": (r, g, b),
                        "error": err, "track": track})
    return out


def write_points(path, points):
    with open(path, "wb") as f:
        f.write(struct.pack("<Q", len(points)))
        for p in points:
            f.write(struct.pack("<QdddBBBd", p["point3D_id"], *p["xyz"], *p["rgb"], p["error"]))
            f.write(struct.pack("<Q", len(p["track"])))
            for iid, idx in p["track"]:
                f.write(struct.pack("<ii", iid, idx))


def main():
    src, dst, keep_spec = sys.argv[1], sys.argv[2], sys.argv[3]
    os.makedirs(dst, exist_ok=True)

    if keep_spec.isdigit():
        keep_n = int(keep_spec)
        images = read_images(os.path.join(src, "images.bin"))
        names = [im["name"] for im in images]
        keep = set(names[:keep_n])          # first N in COLMAP order = temporal order
    else:
        keep = set(open(keep_spec).read().split())

    print("source images:", len(read_images(os.path.join(src, "images.bin"))))

    # images: drop dropped ids and their 2D observations
    images_all = read_images(os.path.join(src, "images.bin"))
    dropped = {im["image_id"] for im in images_all if im["name"] not in keep}
    kept_images = [im for im in images_all if im["name"] in keep]
    print("kept images:", len(kept_images), "dropped:", len(dropped))

    # cameras: keep only referenced ones
    cams = read_cameras(os.path.join(src, "cameras.bin"))
    cams = read_camera_params(os.path.join(src, "cameras.bin"), cams)
    used_cams = {im["camera_id"] for im in kept_images}
    cams = [c for c in cams if c["camera_id"] in used_cams]
    write_cameras(os.path.join(dst, "cameras.bin"), cams)
    print("kept cameras:", len(cams))

    # recovery of per-image 2D points requires re-reading with ids, so re-parse
    # images.bin once more retaining the points2D payload
    with open(os.path.join(src, "images.bin"), "rb") as f:
        n = struct.unpack("<Q", f.read(8))[0]
        for _ in range(n):
            iid = struct.unpack("<i", f.read(4))[0]
            f.read(32 + 24 + 4)      # qvec(4 doubles) + tvec(3 doubles) + camera_id
            name = b""
            while True:
                ch = f.read(1)
                if ch == b"\0" or not ch:
                    break
                name += ch
            npts = struct.unpack("<Q", f.read(8))[0]
            p2d = [(struct.unpack("<dd", f.read(16)) + (struct.unpack("<q", f.read(8))[0],))
                   for _ in range(npts)]
            for im in kept_images:
                if im["image_id"] == iid:
                    im["p2d"] = [(x, y, pid) for (x, y, pid) in p2d]
                    break
    write_images(os.path.join(dst, "images.bin"), kept_images)

    # points3D: keep tracks that still reference at least 2 kept images
    pts = read_points(os.path.join(src, "points3D.bin"))
    kept_pts = []
    for p in pts:
        tr = [(i, t) for (i, t) in p["track"] if i not in dropped]
        if len(tr) >= 2:
            p["track"] = tr
            kept_pts.append(p)
    write_points(os.path.join(dst, "points3D.bin"), kept_pts)
    print("kept points3D:", len(kept_pts), "of", len(pts))

    # rigs/frames: copy verbatim if present
    for extra in ("rigs.bin", "frames.bin"):
        s = os.path.join(src, extra)
        if os.path.exists(s):
            shutil.copyfile(s, os.path.join(dst, extra))
    pi = os.path.join(src, "project.ini")
    if os.path.exists(pi):
        shutil.copyfile(pi, os.path.join(dst, "project.ini"))
    print("wrote subset model to", dst)


if __name__ == "__main__":
    main()
