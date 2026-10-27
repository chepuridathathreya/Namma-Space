"""
NammaSpace Quality Control - Blur Detection Script
Discards motion-blurred frames from video extraction to protect COLMAP SfM matching.
Based on Laplacian variance analysis.
"""

import os
import glob
import argparse
import cv2
from tqdm import tqdm


def filter_blurry_images(input_dir: str, output_dir: str, threshold: float = 15.0):
    os.makedirs(output_dir, exist_ok=True)
    image_paths = sorted(
        glob.glob(os.path.join(input_dir, "*.jpg")) +
        glob.glob(os.path.join(input_dir, "*.jpeg")) +
        glob.glob(os.path.join(input_dir, "*.png"))
    )

    if not image_paths:
        print(f"[Error] No images found in {input_dir}")
        return

    print(f"[*] Processing {len(image_paths)} frames with blur threshold = {threshold}...")
    kept_count = 0
    dropped_count = 0

    for path in tqdm(image_paths, desc="Filtering frames"):
        filename = os.path.basename(path)
        img = cv2.imread(path)
        if img is None:
            continue

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        score = cv2.Laplacian(gray, cv2.CV_64F).var()

        if score >= threshold:
            dest_path = os.path.join(output_dir, filename)
            cv2.imwrite(dest_path, img)
            kept_count += 1
        else:
            dropped_count += 1

    print("\n[+] Blur Detection Complete!")
    print(f"    - Kept sharp frames: {kept_count}")
    print(f"    - Dropped blurry frames: {dropped_count}")
    print(f"    - Output directory: {output_dir}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Filter motion-blurred frames for NammaSpace")
    parser.add_argument("--input-dir", type=str, required=True, help="Directory containing raw extracted frames")
    parser.add_argument("--output-dir", type=str, required=True, help="Directory to save sharp frames")
    parser.add_argument("--threshold", type=float, default=15.0, help="Laplacian variance threshold (default: 15.0)")
    args = parser.parse_args()

    filter_blurry_images(args.input_dir, args.output_dir, args.threshold)
