import argparse
import os
import shutil
import sys

import numpy as np
from scipy.signal import find_peaks

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from compress_to_qsplat import vertex_to_qsplat
from finish_scene import read_ply_vertices, write_ply_vertices

SH_C0 = 0.28209479177387814


class Fields:
    def __init__(self, array):
        self.array = array

    def __len__(self):
        return len(self.array)

    def __getitem__(self, key):
        return self.array[key]

    def __contains__(self, key):
        return key in self.array.dtype.names


def find_floor_y(y, opacity):
    solid = opacity > 0.4
    histogram, edges = np.histogram(y[solid], bins=100, range=(-0.5, 1.0))
    smooth = np.convolve(histogram, np.ones(3) / 3, mode="same")
    peaks = find_peaks(smooth, prominence=0.1 * smooth.max())[0]
    if len(peaks) == 0:
        sys.exit("STOP: could not find a floor in the splat")
    return float(edges[peaks[0]] + 0.0075)


def smooth_floor_colour(data, floor_y, strength, cell):
    near = (np.abs(data["y"] - floor_y) < 0.08) & (1.0 / (1.0 + np.exp(-data["opacity"])) > 0.2)
    index = np.nonzero(near)[0]
    cx = np.floor(data["x"][index] / cell).astype(np.int64)
    cz = np.floor(data["z"][index] / cell).astype(np.int64)
    keys = cx * 100000 + cz
    unique, inverse = np.unique(keys, return_inverse=True)
    weight = 1.0 / (1.0 + np.exp(-data["opacity"][index]))
    for channel in ("f_dc_0", "f_dc_1", "f_dc_2"):
        total = np.zeros(len(unique))
        np.add.at(total, inverse, weight * data[channel][index])
        norm = np.zeros(len(unique))
        np.add.at(norm, inverse, weight)
        mean = total / np.maximum(norm, 1e-9)
        data[channel][index] = (1.0 - strength) * data[channel][index] + strength * mean[inverse]
    return len(index)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ply", required=True)
    parser.add_argument("--out-ply", required=True)
    parser.add_argument("--out-qsplat", nargs="+", required=True)
    parser.add_argument("--floor-margin", type=float, default=0.12)
    parser.add_argument("--ceiling", type=float, default=3.3)
    parser.add_argument("--smooth-floor", type=float, default=0.0)
    parser.add_argument("--smooth-cell", type=float, default=0.25)
    parser.add_argument("--max-gaussians", type=int, default=700000)
    args = parser.parse_args()

    data = read_ply_vertices(args.ply).copy()
    count = len(data)
    opacity = 1.0 / (1.0 + np.exp(-data["opacity"].astype(np.float64)))
    floor_y = find_floor_y(data["y"], opacity)
    print(f"   splat floor at y = {floor_y:+.3f} m, {count:,} gaussians in")

    below = data["y"] < floor_y - args.floor_margin
    above = data["y"] > args.ceiling
    keep = ~(below | above)
    print(f"   removed {int(below.sum()):,} below the floor (mirror ghosts, more than {args.floor_margin * 100:.0f} cm under it)")
    print(f"   removed {int(above.sum()):,} above {args.ceiling:.1f} m")
    data = data[keep]

    if args.smooth_floor > 0:
        touched = smooth_floor_colour(data, floor_y, args.smooth_floor, args.smooth_cell)
        print(f"   smoothed the colour of {touched:,} floor gaussians (strength {args.smooth_floor:.2f}, {args.smooth_cell * 100:.0f} cm cells)")

    opacity = 1.0 / (1.0 + np.exp(-data["opacity"].astype(np.float64)))
    size = np.exp(np.column_stack([data["scale_0"], data["scale_1"], data["scale_2"]]).astype(np.float64))
    importance = opacity * np.cbrt(size.prod(axis=1))
    order = np.argsort(-importance)[: args.max_gaussians]
    data = data[order]
    print(f"   sorted most-important-first (opacity x size), kept {len(data):,}")
    first = importance[order][:250000].mean()
    rest = importance[order][250000:].mean() if len(order) > 250000 else float("nan")
    print(f"   first 250,000 carry {first / importance.mean():.1f}x the average importance, the rest {rest / importance.mean():.1f}x")

    write_ply_vertices(args.out_ply, data)
    vertex_to_qsplat(Fields(data), args.out_qsplat[0], max_gaussians=len(data) + 1)
    for extra in args.out_qsplat[1:]:
        shutil.copyfile(args.out_qsplat[0], extra)
    print(f"   wrote {args.out_ply} and {len(args.out_qsplat)} .qsplat file(s), {os.path.getsize(args.out_qsplat[0]) / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
