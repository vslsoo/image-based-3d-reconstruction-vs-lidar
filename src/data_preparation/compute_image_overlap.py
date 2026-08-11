"""Estimate visual overlap between photos, independent of any reconstruction
method (COLMAP/hloc/MASt3R aren't involved).

Motivation: "enough overlap" has so far been judged after the fact from
whether a reconstruction registered all images (see experiments.yaml /
docs/methodology_notes.md). This gives a number you can check beforehand, or
use to characterize a dataset for the write-up, without running a full SfM
pipeline.

Method: SIFT keypoints per image -> ratio-test matching between a pair ->
RANSAC-verified geometric inliers (fundamental matrix). Overlap % = inliers /
min(keypoint count of the two images) - normalized so texture-rich vs
texture-poor images stay comparable.

Usage:
    # capture-order neighbors only (default) - good for a walk-around video/photo set
    python src/data_preparation/compute_image_overlap.py data/video/bollard_002/images/jpg

    # every pair, not just neighbors
    python src/data_preparation/compute_image_overlap.py data/video/bollard_002/images/jpg --pairs all

    # neighbors up to 2 frames apart, save a CSV
    python src/data_preparation/compute_image_overlap.py data/video/bollard_002/images/jpg \\
        --window 2 --csv outputs/bollard_002_overlap.csv
"""

from __future__ import annotations

import argparse
import csv
import itertools
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "reconstruction"))

from common import list_images, resolve_path  # noqa: E402

RATIO_TEST_THRESHOLD = 0.75
RANSAC_REPROJ_THRESHOLD = 3.0
LOW_OVERLAP_WARNING_PCT = 20.0


def load_grayscale(path: Path, max_size: int) -> np.ndarray:
    image = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if image is None:
        raise IOError(f"Could not read image: {path}")
    scale = max_size / max(image.shape)
    if scale < 1.0:
        image = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    return image


def detect_features(image: np.ndarray, detector: cv2.SIFT):
    keypoints, descriptors = detector.detectAndCompute(image, None)
    return keypoints, descriptors


def pairwise_overlap(kp1, desc1, kp2, desc2, matcher: cv2.BFMatcher) -> tuple[float, int]:
    """Returns (overlap_pct, num_inlier_matches). overlap_pct is inliers /
    min(keypoint count), so 0 when either image has no features at all."""
    if desc1 is None or desc2 is None or len(kp1) == 0 or len(kp2) == 0:
        return 0.0, 0

    raw_matches = matcher.knnMatch(desc1, desc2, k=2)
    good = [m for m, n in raw_matches if m.distance < RATIO_TEST_THRESHOLD * n.distance]
    if len(good) < 8:  # fundamental matrix needs >= 8 points
        return 0.0, len(good)

    pts1 = np.float32([kp1[m.queryIdx].pt for m in good])
    pts2 = np.float32([kp2[m.trainIdx].pt for m in good])
    _, inlier_mask = cv2.findFundamentalMat(
        pts1, pts2, cv2.FM_RANSAC, RANSAC_REPROJ_THRESHOLD, confidence=0.99
    )
    if inlier_mask is None:
        return 0.0, 0

    num_inliers = int(inlier_mask.sum())
    overlap_pct = 100.0 * num_inliers / min(len(kp1), len(kp2))
    return overlap_pct, num_inliers


def pairs_to_check(num_images: int, mode: str, window: int) -> list[tuple[int, int]]:
    if mode == "all":
        return list(itertools.combinations(range(num_images), 2))
    return [
        (i, j)
        for i in range(num_images)
        for j in range(i + 1, min(i + window + 1, num_images))
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("image_dir", help="folder of images, e.g. data/video/<object>/images/jpg")
    parser.add_argument(
        "--pairs", choices=["sequential", "all"], default="sequential",
        help="'sequential' (default) checks only capture-order neighbors (fast, matches how "
        "the object was walked around); 'all' checks every pair (O(n^2), use for small sets)",
    )
    parser.add_argument(
        "--window", type=int, default=1,
        help="for --pairs sequential: compare each image to its next N neighbors (default: 1)",
    )
    parser.add_argument("--max-size", type=int, default=1600, help="downscale longest side to this before matching")
    parser.add_argument("--csv", help="optional path to save per-pair results as CSV")
    args = parser.parse_args()

    image_dir = resolve_path(args.image_dir)
    images = list_images(image_dir)
    if len(images) < 2:
        raise ValueError(f"Need at least 2 images in {image_dir}, found {len(images)}")
    print(f"{len(images)} images found in {image_dir}")

    detector = cv2.SIFT_create()
    matcher = cv2.BFMatcher(cv2.NORM_L2)

    print("Extracting SIFT features...")
    features = [detect_features(load_grayscale(p, args.max_size), detector) for p in images]
    for path, (kp, _) in zip(images, features):
        print(f"  {path.name}: {len(kp)} keypoints")

    pairs = pairs_to_check(len(images), args.pairs, args.window)
    print(f"\nMatching {len(pairs)} pair(s) ({args.pairs})...")

    results = []
    for i, j in pairs:
        kp1, desc1 = features[i]
        kp2, desc2 = features[j]
        overlap_pct, num_inliers = pairwise_overlap(kp1, desc1, kp2, desc2, matcher)
        results.append((images[i].name, images[j].name, overlap_pct, num_inliers))

    print(f"\n{'image A':<20}{'image B':<20}{'overlap %':>10}{'inliers':>10}")
    for name_a, name_b, overlap_pct, num_inliers in results:
        flag = "  <-- low overlap" if overlap_pct < LOW_OVERLAP_WARNING_PCT else ""
        print(f"{name_a:<20}{name_b:<20}{overlap_pct:>9.1f}%{num_inliers:>10}{flag}")

    overlaps = [r[2] for r in results]
    print(f"\nMedian overlap: {np.median(overlaps):.1f}%  (min {np.min(overlaps):.1f}%, max {np.max(overlaps):.1f}%)")
    low = [r for r in results if r[2] < LOW_OVERLAP_WARNING_PCT]
    if low:
        print(f"{len(low)} pair(s) below {LOW_OVERLAP_WARNING_PCT:.0f}% overlap - possible coverage gap:")
        for name_a, name_b, overlap_pct, _ in low:
            print(f"  {name_a} <-> {name_b}: {overlap_pct:.1f}%")

    if args.csv:
        csv_path = resolve_path(args.csv)
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        with csv_path.open("w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["image_a", "image_b", "overlap_pct", "num_inliers"])
            writer.writerows(results)
        print(f"\nSaved -> {csv_path}")


if __name__ == "__main__":
    main()
