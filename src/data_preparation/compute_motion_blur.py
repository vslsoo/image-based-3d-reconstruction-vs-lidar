"""Characterize motion blur across a set of photogrammetry source images,
independent of any reconstruction method (same "before you run SfM" spirit
as compute_image_overlap.py).

Method: Laplacian variance per image - the same no-reference sharpness score
extract_video_frames.py already uses internally to discard blurry frames
when picking candidates from raw video (see that script's docstring: blurry
frames have less high-frequency edge content, so the variance of the
Laplacian drops). Reported here as a summary statistic over a whole image
set, for dataset characterization / write-up rather than frame selection -
a lower mean/median means more motion blur in the capture overall.

Caveat: this is a *relative*, no-reference indicator, not a physical blur
radius in pixels - it also responds to scene texture/contrast, so only
compare scores computed the same way (same --max-size, similar scene
content) - e.g. across one object's own frames, or against another object
shot with the same camera/settings, not as an absolute number in isolation.

Usage:
    python src/data_preparation/compute_motion_blur.py \\
        outputs/experiments/exp_030_colmap_bollard_002/images

    python src/data_preparation/compute_motion_blur.py \\
        data/video/bollard_002/images/jpg --csv outputs/bollard_002_blur.csv
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "reconstruction"))

from common import list_images, resolve_path  # noqa: E402


def sharpness_score(gray: np.ndarray) -> float:
    return cv2.Laplacian(gray, cv2.CV_64F).var()


def load_grayscale(path: Path, max_size: int) -> np.ndarray:
    image = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if image is None:
        raise IOError(f"Could not read image: {path}")
    scale = max_size / max(image.shape)
    if scale < 1.0:
        image = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    return image


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("image_dir", help="folder of images to score")
    parser.add_argument("--max-size", type=int, default=1600, help="resize longest side to this before scoring, for a consistent scale across captures (default: 1600)")
    parser.add_argument("--csv", default=None, help="optional path to save per-image scores as CSV")
    args = parser.parse_args()

    image_dir = resolve_path(args.image_dir)
    images = list_images(image_dir)
    if not images:
        raise SystemExit(f"No images found in {image_dir}")

    scores = {}
    for path in images:
        gray = load_grayscale(path, args.max_size)
        scores[path.name] = sharpness_score(gray)

    values = np.array(list(scores.values()))
    ranked = sorted(scores.items(), key=lambda kv: kv[1])

    print(f"{len(images)} images in {image_dir} (scored at max side {args.max_size}px)")
    print(f"Laplacian variance: mean={values.mean():.1f}  median={np.median(values):.1f}  std={values.std():.1f}  min={values.min():.1f}  max={values.max():.1f}")
    print("Blurriest 5:")
    for name, score in ranked[:5]:
        print(f"  {name}: {score:.1f}")
    print("Sharpest 5:")
    for name, score in ranked[-5:]:
        print(f"  {name}: {score:.1f}")

    if args.csv:
        csv_path = resolve_path(args.csv)
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        with csv_path.open("w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["image", "laplacian_variance"])
            for name, score in scores.items():
                writer.writerow([name, score])
        print(f"Saved -> {csv_path}")


if __name__ == "__main__":
    main()
