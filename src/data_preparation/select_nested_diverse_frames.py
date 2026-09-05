"""Pick a nested sequence of "best, all-around-the-object" image subsets from
a pool of individually-shot photos (no capture-order/angle metadata to rely
on, unlike a video walk-around) - e.g. 25 images, then 50 that include those
25 plus 25 more from new angles, then 75, then 100.

Method: since there's no pose/GPS to know true viewing angle, this treats
pairwise SIFT+RANSAC overlap (same measure as compute_image_overlap.py) as a
proxy for "how similar the viewpoint is" - two images with high overlap are
probably looking at the object from a similar angle. Selection is then
greedy farthest-point sampling on that similarity: start from the sharpest
image, then repeatedly add whichever remaining candidate has the LOWEST
maximum overlap with everything already picked (i.e. the biggest remaining
coverage gap). This is what makes the sequence naturally nested - the first
25 picks are always a prefix of the first 50, etc., no separate re-selection
needed per size. A quality gate first drops the blurriest tail (Laplacian
variance, same score as compute_motion_blur.py) so low-quality frames never
get pulled in just because they happen to look "different" (e.g. a
motion-smeared shot).

Usage:
    python src/data_preparation/select_nested_diverse_frames.py \\
        data/images/information_sign_002_test_1/pool_128/jpg \\
        data/images/information_sign_002_test_1/nested \\
        --sizes 25 50 75 100
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "reconstruction"))

from common import copy_image_subset, list_images, resolve_path  # noqa: E402
from compute_image_overlap import detect_features, load_grayscale, pairwise_overlap  # noqa: E402
from compute_motion_blur import sharpness_score  # noqa: E402

QUALITY_FILTER_PERCENTILE = 10.0  # drop the blurriest this-% before selecting


def build_overlap_matrix(images: list[Path], max_size: int) -> np.ndarray:
    detector = cv2.SIFT_create()
    matcher = cv2.BFMatcher(cv2.NORM_L2)

    print(f"Extracting SIFT features for {len(images)} images...")
    features = [detect_features(load_grayscale(p, max_size), detector) for p in images]

    n = len(images)
    overlap = np.zeros((n, n))
    total_pairs = n * (n - 1) // 2
    done = 0
    print(f"Matching {total_pairs} pairs (exhaustive)...")
    for i in range(n):
        kp1, desc1 = features[i]
        for j in range(i + 1, n):
            kp2, desc2 = features[j]
            pct, _ = pairwise_overlap(kp1, desc1, kp2, desc2, matcher)
            overlap[i, j] = overlap[j, i] = pct
            done += 1
        if (i + 1) % 10 == 0 or i == n - 1:
            print(f"  ...{done}/{total_pairs} pairs done ({images[i].name})")
    return overlap


def greedy_farthest_point_order(overlap: np.ndarray, sharpness: np.ndarray) -> list[int]:
    n = overlap.shape[0]
    seed = int(np.argmax(sharpness))
    order = [seed]
    remaining = set(range(n)) - {seed}

    while remaining:
        best_idx, best_key = None, None
        for cand in remaining:
            max_overlap_with_selected = max(overlap[cand, s] for s in order)
            # lower max-overlap (more different from everything picked so
            # far) wins; break ties by sharper image
            key = (max_overlap_with_selected, -sharpness[cand])
            if best_key is None or key < best_key:
                best_key, best_idx = key, cand
        order.append(best_idx)
        remaining.remove(best_idx)
    return order


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("image_dir", help="folder of candidate images (full original pool)")
    parser.add_argument("output_dir", help="where to write nested selected_<N>/jpg/ subfolders")
    parser.add_argument("--sizes", type=int, nargs="+", default=[25, 50, 75, 100])
    parser.add_argument("--max-size", type=int, default=1600, help="downscale longest side before SIFT matching")
    args = parser.parse_args()

    image_dir = resolve_path(args.image_dir)
    output_dir = resolve_path(args.output_dir)
    images = list_images(image_dir)
    print(f"{len(images)} images found in {image_dir}")

    max_needed = max(args.sizes)
    if len(images) < max_needed:
        raise SystemExit(f"Need at least {max_needed} images, found {len(images)}")

    print("Scoring sharpness (Laplacian variance)...")
    sharpness = np.array([sharpness_score(load_grayscale(p, args.max_size)) for p in images])
    cutoff = np.percentile(sharpness, QUALITY_FILTER_PERCENTILE)
    keep_mask = sharpness >= cutoff
    kept_images = [p for p, keep in zip(images, keep_mask) if keep]
    kept_sharpness = sharpness[keep_mask]
    dropped = len(images) - len(kept_images)
    print(f"Quality gate: dropped {dropped} blurriest image(s) (bottom {QUALITY_FILTER_PERCENTILE:.0f}%, "
          f"sharpness < {cutoff:.1f}), {len(kept_images)} remain")
    if len(kept_images) < max_needed:
        raise SystemExit(f"Only {len(kept_images)} images survive the quality gate, need {max_needed}")

    overlap = build_overlap_matrix(kept_images, args.max_size)
    order = greedy_farthest_point_order(overlap, kept_sharpness)

    print(f"\nSelection order (1st = seed/sharpest, later = fills biggest remaining coverage gap):")
    for rank, idx in enumerate(order[:max_needed], start=1):
        print(f"  {rank:3d}. {kept_images[idx].name}  (sharpness={kept_sharpness[idx]:.1f})")

    for size in sorted(args.sizes):
        chosen = [kept_images[idx] for idx in order[:size]]
        dest = output_dir / f"selected_{size}" / "jpg"
        copy_image_subset(chosen, dest)
        print(f"selected_{size}: {len(chosen)} images -> {dest}")


if __name__ == "__main__":
    main()
