"""Isotropically rescale a reconstruction so its long-axis extent matches
the LiDAR reference's - without requiring a prior pose registration.

For repeat-test reconstructions that haven't been through
register_point_clouds.py yet (no rotation/translation fit to the LiDAR
frame), a pose-dependent scale fix like rescale_to_reference_extent.py
can't be used directly (it measures the source along the TARGET's axis,
which only makes sense once the source is already rotated into that
frame). This instead measures each cloud along its OWN PCA principal
axis - for an elongated, upright object like a bollard, that axis is the
object's long side (its height) regardless of arbitrary orientation - and
scales the source by the ratio of the two extents. Purely a size fix: no
rotation or translation is touched, so the output stays centered on the
source's own centroid.

Usage:
    python src/registration/scale_to_reference_height.py \\
        --source outputs/no_floor/exp_090_mast3r_bollard_003_test_1.ply \\
        --target data/lidar/bollard_003/bollard_003_no_floor.ply \\
        --output outputs/scale_corrected/exp_090_mast3r_bollard_003_test_1_scaled.ply
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


def principal_axis_extent(points: np.ndarray) -> tuple[np.ndarray, float]:
    """Centroid and point spread along the cloud's own dominant-variance
    axis (1st-99th percentile, robust to a few outlier points) - same
    convention as register_point_clouds.py's compute_principal_axis()."""
    centroid = points.mean(axis=0)
    centered = points - centroid
    cov = np.cov(centered.T)
    eigvals, eigvecs = np.linalg.eigh(cov)  # ascending order
    axis = eigvecs[:, -1]
    axis = axis / np.linalg.norm(axis)
    projections = centered @ axis
    extent = float(np.percentile(projections, 99) - np.percentile(projections, 1))
    return centroid, extent


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", required=True, help="reconstruction to rescale")
    parser.add_argument("--target", required=True, help="LiDAR reference point cloud (ground truth size)")
    parser.add_argument("--output", required=True, help="path to write the rescaled source")
    args = parser.parse_args()

    source_path = resolve_path(args.source)
    target_path = resolve_path(args.target)
    output_path = resolve_path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"Loading source: {source_path}")
    source = o3d.io.read_point_cloud(str(source_path))
    print(f"Loading target: {target_path}")
    target = o3d.io.read_point_cloud(str(target_path))

    source_centroid, source_extent = principal_axis_extent(np.asarray(source.points))
    _, target_extent = principal_axis_extent(np.asarray(target.points))
    scale = target_extent / source_extent
    print(
        f"Source extent (own principal axis) = {source_extent:.4f} m, "
        f"target extent (reference, ground truth) = {target_extent:.4f} m -> scale factor = {scale:.4f}"
    )

    transform = np.eye(4)
    transform[:3, :3] *= scale
    transform[:3, 3] = source_centroid - scale * source_centroid
    scaled_source = source.transform(transform)
    o3d.io.write_point_cloud(str(output_path), scaled_source)

    report = {
        "source": display_path(source_path),
        "target": display_path(target_path),
        "source_extent_own_axis": source_extent,
        "target_extent_own_axis": target_extent,
        "scale_factor": scale,
        "method": "own-PCA-principal-axis extent ratio (1st-99th percentile), scaled about source's own centroid - "
        "no rotation/translation fit; use before a full register_point_clouds.py pass",
    }
    report_path = output_path.with_suffix(".json")
    report_path.write_text(json.dumps(report, indent=2))
    print(f"Saved rescaled cloud -> {output_path}")
    print(f"Saved report -> {report_path}")


if __name__ == "__main__":
    main()
