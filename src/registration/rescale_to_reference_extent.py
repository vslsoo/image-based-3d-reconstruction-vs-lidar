"""Correct an existing registration's SCALE ONLY, using the reference (LiDAR)
cloud's own end-to-end extent as ground truth - for cases where
register_point_clouds.py's rotation/position came out visually correct but
its ICP-fitted scale did not.

Why this can diverge from the ICP scale: register_point_clouds.py's ICP
scale sub-step (TransformationEstimationPointToPoint with scaling) fits
scale from whichever point correspondences fall inside the current
tightening distance threshold - for a thin, sparsely-sampled target (e.g. a
sign's LiDAR crop with only a few thousand points), that correspondence set
can end up unrepresentative of the object's true end-to-end size, letting
scale drift away from the coarse (axis-sweep/naive bbox) estimate during
refinement even though rotation/translation converge fine. The LiDAR target
is metric ground truth, so measuring the object's own extent end-to-end
(along its principal axis, 1st-99th percentile to stay robust to a handful
of outlier points) directly gives the true size - no correspondence search
needed.

Rescales the previously-aligned source uniformly about the TARGET's
centroid (assumes the existing rotation/translation already seated the
object roughly at the right place - only overall size changes), so it does
not undo a correct pose while fixing the size.

Usage:
    python src/registration/rescale_to_reference_extent.py \\
        --registration-dir outputs/registrations/reg_036_to_lidar_information_sign_001 \\
        --source outputs/no_floor/exp_036_vggt_information_sign_001_no_floor.ply \\
        --target data/lidar/information_sign_001/information_sign_001_no_floor.ply
"""

from __future__ import annotations

import argparse
import copy
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


def principal_axis_extent(points: np.ndarray, axis: np.ndarray, centroid: np.ndarray) -> float:
    """Point spread along a given axis, 1st-99th percentile (robust to a
    handful of outlier points) - same convention as
    register_point_clouds.py's compute_principal_axis(), but measured along
    a caller-supplied axis so both clouds can be measured along the SAME
    (target's) direction rather than each cloud's own independently-fitted
    axis."""
    projections = (points - centroid) @ axis
    return float(np.percentile(projections, 99) - np.percentile(projections, 1))


def target_principal_axis(points: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    centroid = points.mean(axis=0)
    cov = np.cov((points - centroid).T)
    eigvals, eigvecs = np.linalg.eigh(cov)  # ascending order
    axis = eigvecs[:, -1]
    return centroid, axis / np.linalg.norm(axis)


def extract_scale(transform: np.ndarray) -> float:
    return float(np.mean(np.linalg.norm(transform[:3, :3], axis=0)))


def point_cloud_distance_stats(source: o3d.geometry.PointCloud, target: o3d.geometry.PointCloud) -> dict:
    distances = np.asarray(source.compute_point_cloud_distance(target))
    return {
        "mean": float(distances.mean()),
        "median": float(np.median(distances)),
        "std": float(distances.std()),
        "rmse": float(np.sqrt(np.mean(distances ** 2))),
        "p95": float(np.percentile(distances, 95)),
        "max": float(distances.max()),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--registration-dir", required=True, help="output-dir of a prior register_point_clouds.py run")
    parser.add_argument("--source", required=True, help="same --source used for the original registration")
    parser.add_argument("--target", required=True, help="same --target used for the original registration")
    args = parser.parse_args()

    reg_dir = resolve_path(args.registration_dir)
    source_path = resolve_path(args.source)
    target_path = resolve_path(args.target)

    report_path = reg_dir / "report.json"
    transform_path = reg_dir / "transform.txt"
    report = json.loads(report_path.read_text())
    old_transform = np.loadtxt(transform_path)

    print(f"Loading source: {source_path}")
    source = o3d.io.read_point_cloud(str(source_path))
    print(f"Loading target: {target_path}")
    target = o3d.io.read_point_cloud(str(target_path))

    aligned_source = copy.deepcopy(source)
    aligned_source.transform(old_transform)

    target_points = np.asarray(target.points)
    aligned_source_points = np.asarray(aligned_source.points)

    target_centroid, target_axis = target_principal_axis(target_points)
    target_extent = principal_axis_extent(target_points, target_axis, target_centroid)
    # aligned_source is measured along TARGET's axis (not its own), and
    # about its OWN centroid (only spread matters here, not position) -
    # since after the existing registration both clouds should already
    # share close to the same orientation.
    source_extent = principal_axis_extent(
        aligned_source_points, target_axis, aligned_source_points.mean(axis=0)
    )
    correction = target_extent / source_extent
    print(
        f"Target extent (reference, ground truth) = {target_extent:.4f} m, "
        f"aligned source extent = {source_extent:.4f} -> correction factor = {correction:.4f}"
    )

    # Uniform scale about the target's centroid: assumes the existing
    # rotation/translation already seated the object at roughly the right
    # place, so this only grows/shrinks it in place rather than re-deriving
    # pose.
    scale_about_target = np.eye(4)
    scale_about_target[:3, :3] *= correction
    scale_about_target[:3, 3] = target_centroid - correction * target_centroid
    new_transform = scale_about_target @ old_transform

    corrected_source = copy.deepcopy(source)
    corrected_source.transform(new_transform)

    aligned_path = reg_dir / f"{source_path.stem}_aligned_to_{target_path.stem}.ply"
    o3d.io.write_point_cloud(str(aligned_path), corrected_source)
    np.savetxt(transform_path, new_transform, fmt="%.8f")

    voxel_size = report.get("voxel_size", 0.01)
    corrected_source_down = corrected_source.voxel_down_sample(voxel_size)
    distance_stats = point_cloud_distance_stats(corrected_source_down, target)
    print(
        f"Corrected distance stats: mean={distance_stats['mean']:.4f}, rmse={distance_stats['rmse']:.4f}, "
        f"p95={distance_stats['p95']:.4f}, max={distance_stats['max']:.4f}"
    )

    report["manual_extra_scale_correction"] = correction
    report["manual_extra_scale_correction_method"] = (
        "principal-axis extent ratio (target's own reference extent / aligned source's extent along the "
        "same axis, 1-99th percentile) - see rescale_to_reference_extent.py"
    )
    report["estimated_scale"] = extract_scale(new_transform)
    report["point_distance_stats"] = distance_stats
    report_path.write_text(json.dumps(report, indent=2))

    print(f"Saved rescaled cloud -> {aligned_path}")
    print(f"Saved corrected transform -> {transform_path}")
    print(f"Saved updated report -> {report_path}")


if __name__ == "__main__":
    main()
