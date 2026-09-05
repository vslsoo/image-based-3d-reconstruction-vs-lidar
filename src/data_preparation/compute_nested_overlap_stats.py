"""Physically-meaningful "coverage density" x-axis for a nested frame-count study
(e.g. F1@3cm(N) for information_sign_002_test_1's selected_25/50/75/100 subsets).

Motivation: N alone isn't comparable across objects of different size/shape (see
select_nested_diverse_frames.py) - two objects can need very different N to reach
"fully covered". Median pairwise SIFT/RANSAC overlap of the actual subset of images
used at each N is a physically-grounded stand-in for "how densely is the object
covered", usable as an x-axis alongside the simpler N/N_max normalization.

Method: compute the full pairwise overlap matrix ONCE, over the largest nested subset
(selected_<max(sizes)>/jpg - a superset of every smaller subset, since selection is
nested/prefix-based). Cache it to disk. Then for each requested size, look up which of
those images are actually present in that size's selected_<N>/jpg folder (nested
prefix membership - no need to redo the greedy farthest-point order) and report the
median/mean pairwise overlap restricted to that subset.

Usage:
    python src/data_preparation/compute_nested_overlap_stats.py \\
        data/images/information_sign_002_test_1/nested \\
        --sizes 25 50 75 100 \\
        --out docs/tables/information_sign_002_nested_overlap.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "reconstruction"))

from common import list_images, resolve_path  # noqa: E402
from compute_image_overlap import detect_features, load_grayscale, pairwise_overlap  # noqa: E402


def build_overlap_matrix(images: list[Path], max_size: int) -> np.ndarray:
    detector = cv2.SIFT_create()
    matcher = cv2.BFMatcher(cv2.NORM_L2)

    print(f"Extracting SIFT features for {len(images)} images...", flush=True)
    features = [detect_features(load_grayscale(p, max_size), detector) for p in images]

    n = len(images)
    overlap = np.zeros((n, n))
    total_pairs = n * (n - 1) // 2
    done = 0
    print(f"Matching {total_pairs} pairs (exhaustive)...", flush=True)
    for i in range(n):
        kp1, desc1 = features[i]
        for j in range(i + 1, n):
            kp2, desc2 = features[j]
            pct, _ = pairwise_overlap(kp1, desc1, kp2, desc2, matcher)
            overlap[i, j] = overlap[j, i] = pct
            done += 1
        if (i + 1) % 10 == 0 or i == n - 1:
            print(f"  ...{done}/{total_pairs} pairs done ({images[i].name})", flush=True)
    return overlap


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("nested_dir", help="folder containing selected_<N>/jpg subfolders (from select_nested_diverse_frames.py)")
    parser.add_argument("--sizes", type=int, nargs="+", default=[25, 50, 75, 100])
    parser.add_argument("--max-size", type=int, default=1600, help="downscale longest side before SIFT matching")
    parser.add_argument("--out", required=True, help="output JSON path for per-size overlap stats")
    parser.add_argument("--cache", help="optional .npz path to cache the full overlap matrix (skip recompute if present)")
    args = parser.parse_args()

    nested_dir = resolve_path(args.nested_dir)
    sizes = sorted(args.sizes)
    max_size_n = sizes[-1]
    superset_dir = nested_dir / f"selected_{max_size_n}" / "jpg"
    images = list_images(superset_dir)
    print(f"{len(images)} images in superset {superset_dir}")
    if len(images) != max_size_n:
        print(f"WARNING: expected {max_size_n} images, found {len(images)}")
    names = [p.name for p in images]

    cache_path = resolve_path(args.cache) if args.cache else None
    if cache_path and cache_path.exists():
        print(f"Loading cached overlap matrix from {cache_path}")
        cached = np.load(cache_path, allow_pickle=True)
        cached_names = list(cached["names"])
        if cached_names == names:
            overlap = cached["overlap"]
        else:
            print("Cache name mismatch, recomputing.")
            overlap = build_overlap_matrix(images, args.max_size)
    else:
        overlap = build_overlap_matrix(images, args.max_size)

    if cache_path:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(cache_path, overlap=overlap, names=np.array(names, dtype=object))
        print(f"Cached overlap matrix -> {cache_path}")

    name_to_idx = {name: i for i, name in enumerate(names)}

    stats = []
    for size in sizes:
        size_dir = nested_dir / f"selected_{size}" / "jpg"
        size_images = list_images(size_dir)
        idx = [name_to_idx[p.name] for p in size_images if p.name in name_to_idx]
        missing = [p.name for p in size_images if p.name not in name_to_idx]
        if missing:
            print(f"WARNING selected_{size}: {len(missing)} image(s) not found in superset: {missing[:5]}...")
        idx = np.array(sorted(idx))
        sub = overlap[np.ix_(idx, idx)]
        iu = np.triu_indices(len(idx), k=1)
        pair_vals = sub[iu]
        row = {
            "size": size,
            "n_images": int(len(idx)),
            "n_pairs": int(len(pair_vals)),
            "median_overlap_pct": float(np.median(pair_vals)) if pair_vals.size else None,
            "mean_overlap_pct": float(np.mean(pair_vals)) if pair_vals.size else None,
            "p25_overlap_pct": float(np.percentile(pair_vals, 25)) if pair_vals.size else None,
            "p75_overlap_pct": float(np.percentile(pair_vals, 75)) if pair_vals.size else None,
            "min_overlap_pct": float(np.min(pair_vals)) if pair_vals.size else None,
            "max_overlap_pct": float(np.max(pair_vals)) if pair_vals.size else None,
        }
        print(f"  N={size:4d}  pairs={row['n_pairs']:5d}  median_overlap={row['median_overlap_pct']:.2f}%  "
              f"mean={row['mean_overlap_pct']:.2f}%  [{row['min_overlap_pct']:.2f}, {row['max_overlap_pct']:.2f}]")
        stats.append(row)

    out_path = resolve_path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps({
        "nested_dir": str(args.nested_dir),
        "superset_size": max_size_n,
        "sizes": stats,
    }, indent=2))
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()
