import argparse
import json
import os
import sys

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage
from scipy.signal import find_peaks

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_collision_from_colmap import read_images
from finish_scene import read_ply_vertices


def die(message):
    sys.exit(f"STOP: {message}")


def rows_to_array(rows):
    return np.array([[c == "1" for c in row] for row in rows], dtype=bool)


def array_to_rows(array):
    return ["".join("1" if v else "0" for v in row) for row in array]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ply", required=True)
    parser.add_argument("--world", required=True)
    parser.add_argument("--sparse", required=True)
    parser.add_argument("--grid", required=True)
    parser.add_argument("--out-grid", nargs="+", required=True)
    parser.add_argument("--preview")
    parser.add_argument("--radius", type=float, default=0.2)
    parser.add_argument("--obstacle-hits", type=int, default=10)
    parser.add_argument("--min-opacity", type=float, default=0.4)
    args = parser.parse_args()

    grid = json.load(open(args.grid))
    world = json.load(open(args.world))
    cell, ox, oz, cols, rows = grid["cell"], grid["originX"], grid["originZ"], grid["cols"], grid["rows"]
    sparse_blocked = rows_to_array(grid["blocked"])
    sparse_occupied = rows_to_array(grid["occupied"])

    print("   [1/4] reading the cleaned splat")
    vertices = read_ply_vertices(args.ply)
    xyz = np.column_stack([vertices["x"], vertices["y"], vertices["z"]])
    opacity = 1.0 / (1.0 + np.exp(-vertices["opacity"].astype(np.float64)))
    solid = opacity > args.min_opacity
    print(f"         {len(xyz):,} gaussians, {solid.sum():,} solid enough to count")

    def to_cells(points):
        c = np.floor((points[:, 0] - ox) / cell).astype(int)
        r = np.floor((points[:, 2] - oz) / cell).astype(int)
        keep = (c >= 0) & (r >= 0) & (c < cols) & (r < rows)
        return r[keep], c[keep]

    print("   [2/4] finding the floor in the splat")
    histogram, edges = np.histogram(xyz[solid, 1], bins=100, range=(-0.5, 1.0))
    smooth = np.convolve(histogram, np.ones(3) / 3, mode="same")
    peaks = find_peaks(smooth, prominence=0.1 * smooth.max())[0]
    if len(peaks) == 0:
        die("could not find a floor in the splat")
    floor_y = float(edges[peaks[0]] + 0.0075)
    print(f"         splat floor at y = {floor_y:+.3f} m (the walking floor is y = 0.000)")

    print("   [3/4] building the walkable map from the splat")
    obstacle_band = solid & (xyz[:, 1] > floor_y + 0.2) & (xyz[:, 1] < floor_y + 1.7)
    floor_band = (opacity > 0.3) & (np.abs(xyz[:, 1] - floor_y) < 0.1)
    obstacle_hits = np.zeros((rows, cols), np.int32)
    np.add.at(obstacle_hits, to_cells(xyz[obstacle_band]), 1)
    floor_hits = np.zeros((rows, cols), np.int32)
    np.add.at(floor_hits, to_cells(xyz[floor_band]), 1)

    names, rotation, translation = read_images(os.path.join(args.sparse, "images.bin"))
    centers = -np.einsum("nji,nj->ni", rotation, translation)
    rw, tw, sw = np.array(world["rotation"]), np.array(world["translation"]), world["scale"]
    camera = sw * (rw @ centers.T).T + tw
    path = np.zeros((rows, cols), bool)
    for p, q in zip(camera[:-1], camera[1:]):
        steps = max(2, int(np.linalg.norm(q - p) / (cell * 0.5)))
        path[to_cells(p + np.linspace(0, 1, steps)[:, None] * (q - p))] = True

    splat_occupied = obstacle_hits >= args.obstacle_hits
    splat_occupied &= ndimage.distance_transform_edt(~path) * cell > 0.2
    splat_free = ((floor_hits >= 3) & ~splat_occupied) | path
    clearance = ndimage.distance_transform_edt(~splat_occupied) * cell
    splat_blocked = ~splat_free | (clearance < args.radius)
    splat_blocked[path & ~splat_occupied] = False

    print("   [4/4] combining with the camera-path map")
    blocked = sparse_blocked & splat_blocked
    blocked |= splat_occupied & ~path
    occupied = (sparse_occupied | splat_occupied) & blocked
    blocked[path & ~occupied] = False
    labels, count = ndimage.label(~blocked, structure=np.ones((3, 3)))
    sizes = ndimage.sum(np.ones_like(labels), labels, range(1, count + 1))
    main_region = int(np.argmax(sizes)) + 1
    inside = float((labels[path] == main_region).mean())
    blocked |= labels != main_region

    start_c = int(np.floor((grid["start"]["x"] - ox) / cell))
    start_r = int(np.floor((grid["start"]["z"] - oz) / cell))
    print(f"         walkable cells: camera-path map {int((~sparse_blocked).sum())}, splat map {int((~splat_blocked).sum())}, combined {int((~blocked).sum())}")
    print(f"         walked path inside the main region: {inside * 100:.0f}%  (regions found: {count})")
    if blocked[start_r, start_c]:
        die("the start position is blocked in the combined map")
    if inside < 0.98:
        die(f"only {inside * 100:.0f}% of the walked path is walkable in the combined map")

    result = dict(grid)
    result["blocked"] = array_to_rows(blocked)
    result["occupied"] = array_to_rows(occupied)
    for target in args.out_grid:
        json.dump(result, open(target, "w"))
        print(f"         wrote {target}")

    if args.preview:
        scale = 6
        image = Image.new("RGB", (cols * scale, rows * scale), (20, 20, 24))
        draw = ImageDraw.Draw(image)
        for r in range(rows):
            for c in range(cols):
                if occupied[r, c]:
                    colour = (190, 70, 60)
                elif not blocked[r, c]:
                    colour = (60, 140, 90)
                else:
                    colour = (32, 32, 38)
                draw.rectangle([c * scale, r * scale, c * scale + scale - 1, r * scale + scale - 1], fill=colour)
        for r, c in zip(*np.nonzero(path)):
            draw.ellipse([c * scale + 1, r * scale + 1, c * scale + scale - 2, r * scale + scale - 2], fill=(240, 220, 90))
        draw.ellipse([start_c * scale - 2, start_r * scale - 2, start_c * scale + scale + 1, start_r * scale + scale + 1], outline=(80, 160, 255))
        image.save(args.preview)
        print(f"         preview picture: {args.preview}")


if __name__ == "__main__":
    main()
