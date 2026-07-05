"""Automatically remove the ground/floor plane from a point cloud via RANSAC
plane segmentation, then optionally keep only the largest remaining cluster
(the object itself) - an automatic alternative to manually cropping out the
floor in CloudCompare.

Why this matters: register_point_clouds.py's --axis-sweep mode needs a
clean, floor-free point cloud. PCA finds the direction of greatest
variance, and a flat floor patch large enough relative to the object
dominates that computation, producing a completely wrong "principal axis"
(diagnosed in docs/experiment_log.md - both bollard_001 crops still had the
floor in them, evidenced by the 2nd PCA eigenvalue being ~70-75% of the 1st,
the signature of a plane rather than a cylinder).

IMPORTANT CAVEAT: this removes the SINGLE LARGEST flat surface, whatever it
is - it has no notion of "floor" specifically. That's safe for objects with
no large flat surfaces of their own (a bollard, a post), but NOT safe as-is
for objects that are themselves largely flat (e.g. a wayfinding sign's face)
- on those it could just delete the object instead of the floor. Always
check removed_plane.ply (saved alongside the output) to confirm what
actually got removed before trusting the result.

Usage:
    python src/registration/remove_ground_plane.py \\
        outputs/crops/exp_003_colmap_bollard_001_cropped.ply \\
        outputs/crops/exp_003_colmap_bollard_001_no_floor.ply

    python src/registration/remove_ground_plane.py \\
        outputs/crops/exp_005_colmap_bollard_001_dense_cropped.ply \\
        outputs/crops/exp_005_colmap_bollard_001_dense_no_floor.ply \\
        --keep-largest-cluster
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import open3d as o3d

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def resolve_path(path_str: str) -> Path:
    path = Path(path_str)
    return path if path.is_absolute() else (PROJECT_ROOT / path).resolve()


def remove_ground_plane(
    pcd: o3d.geometry.PointCloud, distance_threshold: float, ransac_n: int = 3, num_iterations: int = 2000
) -> tuple[o3d.geometry.PointCloud, o3d.geometry.PointCloud, np.ndarray]:
    plane_model, inliers = pcd.segment_plane(distance_threshold, ransac_n, num_iterations)
    plane_points = pcd.select_by_index(inliers)
    without_plane = pcd.select_by_index(inliers, invert=True)
    return without_plane, plane_points, np.asarray(plane_model)


def keep_largest_cluster(pcd: o3d.geometry.PointCloud, cluster_eps: float, min_points: int = 20) -> o3d.geometry.PointCloud:
    labels = np.array(pcd.cluster_dbscan(eps=cluster_eps, min_points=min_points))
    if labels.max() < 0:
        return pcd  # no clusters found (all noise) - return as-is rather than emptying the cloud
    largest_label = np.bincount(labels[labels >= 0]).argmax()
    indices = np.where(labels == largest_label)[0]
    return pcd.select_by_index(indices)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("input", help="point cloud to clean (.ply)")
    parser.add_argument("output", help="where to save the floor-removed cloud")
    parser.add_argument(
        "--distance-threshold-fraction", type=float, default=0.01,
        help="RANSAC plane distance threshold as a fraction of the cloud's bbox diagonal (default: 0.01)",
    )
    parser.add_argument(
        "--keep-largest-cluster", action="store_true",
        help="after removing the floor, keep only the largest connected cluster (drops stray debris/other objects)",
    )
    parser.add_argument(
        "--cluster-eps-fraction", type=float, default=0.02,
        help="DBSCAN neighbor distance as a fraction of the cloud's bbox diagonal (default: 0.02)",
    )
    args = parser.parse_args()

    input_path = resolve_path(args.input)
    output_path = resolve_path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    pcd = o3d.io.read_point_cloud(str(input_path))
    total_points = len(pcd.points)
    print(f"Loaded {total_points} points from {input_path}")

    diagonal = float(np.linalg.norm(pcd.get_axis_aligned_bounding_box().get_extent()))
    distance_threshold = diagonal * args.distance_threshold_fraction

    without_floor, plane_points, plane_model = remove_ground_plane(pcd, distance_threshold)
    removed_fraction = len(plane_points.points) / total_points
    print(
        f"Removed {len(plane_points.points)} points ({removed_fraction:.1%} of the cloud), "
        f"plane normal: {plane_model[:3].round(3)}, {len(without_floor.points)} remain"
    )
    if removed_fraction > 0.5:
        print(
            f"WARNING: removed more than half the cloud ({removed_fraction:.1%}). For a small object on a "
            "large floor patch that's plausible, but if the object itself has a large flat surface (e.g. a "
            "sign face), this may have deleted the object instead of the floor - check removed_plane.ply below."
        )

    removed_path = output_path.parent / f"{output_path.stem}_removed_plane.ply"
    o3d.io.write_point_cloud(str(removed_path), plane_points)
    print(f"Saved removed points -> {removed_path} (inspect this to confirm it's really the floor, not the object)")

    if args.keep_largest_cluster:
        cluster_eps = diagonal * args.cluster_eps_fraction
        before = len(without_floor.points)
        without_floor = keep_largest_cluster(without_floor, cluster_eps)
        print(f"Kept largest cluster: {len(without_floor.points)} / {before} points")

    o3d.io.write_point_cloud(str(output_path), without_floor)
    print(f"Saved -> {output_path}")


if __name__ == "__main__":
    main()
