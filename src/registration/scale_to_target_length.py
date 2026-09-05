"""Isotropically rescale a reconstruction so one of its own PCA-axis extents
matches a given absolute length - no external reference cloud needed.

Companion to scale_to_reference_height.py, which matches the LARGEST-
variance axis (an elongated object's "height") to a reference cloud's own
extent along that axis. Here the axis is selectable by rank and the target
is a plain number, for cases where the axis that carries the trustworthy,
physically-known size isn't the tallest one - e.g. an information sign's
board WIDTH ("length", the middle-variance axis) is a fixed, known
~0.5 m regardless of how much post got swept into different captures'
crops, while the tallest axis (post + board) varies capture to capture and
isn't a reliable scale reference.

Axis ranks (ascending eigenvalue order, matching compute_principal_axis()'s
convention elsewhere in this project):
    0 = smallest-variance axis (an object's thinnest dimension, e.g. a flat
        sign's depth)
    1 = middle-variance axis   (e.g. a sign board's width/"length")
    2 = largest-variance axis  (e.g. the tallest/longest extent, "height" -
        same axis scale_to_reference_height.py uses)

By default the extent is measured 1st-99th percentile (robust to a few
outlier points). --minmax switches to the literal highest/lowest point
instead - use when the target itself was defined that way (e.g. "exactly
1 m between the topmost and bottommost point"); note this makes the fitted
scale sensitive to a single stray far point, unlike the percentile default.

--center-on optionally translates the result so its centroid lands on a
REFERENCE cloud's centroid (e.g. a LiDAR crop already recentered to its own
local origin) instead of staying at the source's own centroid - for lining
up a batch of reconstructions with a shared LiDAR reference's position
without a full rotation-fitting registration pass.

Usage:
    python src/registration/scale_to_target_length.py \\
        --source outputs/no_floor/exp_097_mast3r_ga_information_sign_002_test_1_n25.ply \\
        --axis-rank 1 --target-length 0.5 \\
        --output outputs/scale_corrected/exp_097_mast3r_ga_is_002_n25_scaled.ply

    python src/registration/scale_to_target_length.py \\
        --source outputs/no_floor/exp_119_mast3r_ga_bollard_003_test_1_manual_n15.ply \\
        --axis-rank 2 --target-length 1.0 --minmax \\
        --center-on data/lidar/bollard_003/bollard_003_no_floor_centered.ply \\
        --output outputs/scale_corrected/exp_119_mast3r_ga_bollard_003_test_1_manual_n15_scaled.ply
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import open3d as o3d

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def resolve_path(path_str: str) -> Path:
    path = Path(path_str)
    return path if path.is_absolute() else (PROJECT_ROOT / path).resolve()


def display_path(path: Path) -> str:
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def pca_axis_extent(points: np.ndarray, axis_rank: int, minmax: bool = False) -> tuple[np.ndarray, float]:
    """Centroid and point spread along the axis_rank-th PCA axis, ascending
    eigenvalue order (0=smallest-variance, 2=largest-variance for 3D points)
    - same convention as compute_principal_axis()/principal_axis_extent()
    elsewhere in this project, generalized to any axis rank rather than just
    the largest. Extent is 1st-99th percentile by default (robust to a few
    outlier points), or the literal max-min when minmax=True."""
    centroid = points.mean(axis=0)
    centered = points - centroid
    cov = np.cov(centered.T)
    eigvals, eigvecs = np.linalg.eigh(cov)  # ascending order
    axis = eigvecs[:, axis_rank]
    axis = axis / np.linalg.norm(axis)
    projections = centered @ axis
    if minmax:
        extent = float(projections.max() - projections.min())
    else:
        extent = float(np.percentile(projections, 99) - np.percentile(projections, 1))
    return centroid, extent


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", required=True, help="reconstruction to rescale")
    parser.add_argument(
        "--axis-rank", type=int, required=True, choices=[0, 1, 2],
        help="which PCA axis to measure/target, ascending eigenvalue order: "
        "0=smallest-variance, 1=middle, 2=largest-variance",
    )
    parser.add_argument("--target-length", type=float, required=True, help="desired extent (meters) along that axis")
    parser.add_argument(
        "--minmax", action="store_true",
        help="measure extent as the literal highest-lowest point (max-min) instead of the 1st-99th percentile "
        "default - sensitive to a single stray far point, but matches a target defined that way",
    )
    parser.add_argument(
        "--center-on", default=None,
        help="optional reference cloud (e.g. a LiDAR crop already centered at its own local origin) - after "
        "scaling, translate the result so its centroid lands on the reference's centroid instead of staying "
        "at the source's own centroid",
    )
    parser.add_argument("--output", required=True, help="path to write the rescaled source")
    args = parser.parse_args()

    source_path = resolve_path(args.source)
    output_path = resolve_path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"Loading source: {source_path}")
    source = o3d.io.read_point_cloud(str(source_path))

    source_centroid, source_extent = pca_axis_extent(np.asarray(source.points), args.axis_rank, args.minmax)
    scale = args.target_length / source_extent
    print(
        f"Source extent (own PCA axis rank {args.axis_rank}, {'minmax' if args.minmax else '1st-99th pct'}) = "
        f"{source_extent:.4f} m, target = {args.target_length:.4f} m -> scale factor = {scale:.4f}"
    )

    target_centroid = source_centroid
    center_on_path = None
    if args.center_on:
        center_on_path = resolve_path(args.center_on)
        reference = o3d.io.read_point_cloud(str(center_on_path))
        target_centroid = np.asarray(reference.points).mean(axis=0)
        print(f"Centering on: {center_on_path} (centroid={target_centroid.round(4)})")

    transform = np.eye(4)
    transform[:3, :3] *= scale
    transform[:3, 3] = target_centroid - scale * source_centroid
    scaled_source = source.transform(transform)
    o3d.io.write_point_cloud(str(output_path), scaled_source)

    report = {
        "source": display_path(source_path),
        "axis_rank": args.axis_rank,
        "extent_method": "minmax" if args.minmax else "1st-99th percentile",
        "source_extent_own_axis": source_extent,
        "target_length": args.target_length,
        "scale_factor": scale,
        "center_on": display_path(center_on_path) if center_on_path else None,
        "target_centroid": target_centroid.tolist(),
        "method": "own-PCA axis-rank extent vs. absolute target length, isotropically scaled about source's own "
        "centroid, then translated to the reference's centroid if --center-on was given - no rotation fit; use "
        "before a full register_point_clouds.py pass",
    }
    report_path = output_path.with_suffix(".json")
    report_path.write_text(json.dumps(report, indent=2))
    print(f"Saved rescaled cloud -> {output_path}")
    print(f"Saved report -> {report_path}")


if __name__ == "__main__":
    main()
