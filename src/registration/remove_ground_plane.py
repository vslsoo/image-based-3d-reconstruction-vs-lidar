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


def compute_principal_axis(points: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Centroid and unit principal axis (direction of greatest variance) -
    the object's own long axis, regardless of how the cloud happens to be
    rotated (photogrammetry/VGGT poses have no notion of "up")."""
    centroid = points.mean(axis=0)
    centered = points - centroid
    cov = np.cov(centered.T)
    eigvals, eigvecs = np.linalg.eigh(cov)  # ascending order
    axis = eigvecs[:, -1]
    return centroid, axis / np.linalg.norm(axis)


def axis_extreme_indices(points: np.ndarray, fraction: float, end: str) -> np.ndarray:
    """Indices of the points lying in one extreme end of the cloud's own
    principal axis (e.g. the bottom 25% by height)."""
    centroid, axis = compute_principal_axis(points)
    projections = (points - centroid) @ axis
    percentile = fraction * 100
    if end == "min":
        threshold = np.percentile(projections, percentile)
        mask = projections <= threshold
    else:
        threshold = np.percentile(projections, 100 - percentile)
        mask = projections >= threshold
    return np.where(mask)[0]


def plane_inlier_mask(points: np.ndarray, plane_model: np.ndarray, distance_threshold: float) -> np.ndarray:
    """Boolean mask of which points lie within distance_threshold of an
    already-fitted plane."""
    normal = plane_model[:3]
    distances = np.abs(points @ normal + plane_model[3])
    return distances <= distance_threshold


def remove_ground_plane(
    pcd: o3d.geometry.PointCloud, distance_threshold: float, ransac_n: int = 3, num_iterations: int = 2000,
    restrict_fraction: float | None = None, restrict_end: str = "min", apply_fraction: float | None = None,
) -> tuple[o3d.geometry.PointCloud, o3d.geometry.PointCloud, np.ndarray]:
    points = np.asarray(pcd.points)

    if restrict_fraction is None:
        plane_model, inliers = pcd.segment_plane(distance_threshold, ransac_n, num_iterations)
        plane_model = np.asarray(plane_model)
    else:
        # Fit only on candidates at one extreme of the object's own
        # principal axis (e.g. the bottom 25% by height) - so a tall
        # object's own (possibly reflective/near-planar) side surface,
        # spanning most of its height, can't out-compete the real floor,
        # which only occupies one end.
        fit_indices = axis_extreme_indices(points, restrict_fraction, restrict_end)
        plane_model, subset_inliers = pcd.select_by_index(fit_indices.tolist()).segment_plane(
            distance_threshold, ransac_n, num_iterations
        )
        plane_model = np.asarray(plane_model)

        # Apply that plane within a window around the same end - wider
        # than the fit window, so the real floor's full extent is caught
        # even outside it, but not so wide it reaches the object's far
        # end. A reflective/near-planar patch there (e.g. a mirrored
        # "ghost floor" on a glossy cap) can coincidentally satisfy the
        # same plane equation despite being a completely different
        # physical surface - restricting where we even *look* for
        # inliers rules that out regardless of how well it fits.
        apply_indices = (
            np.arange(len(points)) if apply_fraction is None
            else axis_extreme_indices(points, apply_fraction, restrict_end)
        )
        inlier_mask = plane_inlier_mask(points[apply_indices], plane_model, distance_threshold)
        inliers = apply_indices[inlier_mask].tolist()

    plane_points = pcd.select_by_index(inliers)
    without_plane = pcd.select_by_index(inliers, invert=True)
    return without_plane, plane_points, plane_model


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
        "--num-planes", type=int, default=1,
        help="remove this many planes, re-fitting on the remainder each time (default: 1) - use >1 when "
        "there's more than one large flat surface (e.g. a floor plus a raised curb/plinth, or a reflective "
        "object's mirrored floor - check each removed_plane_N.ply)",
    )
    parser.add_argument(
        "--restrict-search-fraction", type=float, default=None,
        help="restrict plane-fitting candidates to this fraction of points at one extreme of the cloud's own "
        "principal axis (e.g. 0.25 = bottom quarter by height) before fitting - prevents a tall object's own "
        "flat/reflective side (spanning most of its height) from out-competing the real floor, which only "
        "occupies one end. The fitted plane is still applied to the FULL cloud afterwards, so the floor's "
        "true extent is fully removed even outside this restricted window. Default: off (fit on the whole cloud).",
    )
    parser.add_argument(
        "--restrict-search-end", choices=["min", "max"], default="min",
        help="which extreme of the principal axis to restrict to (default: min - flip to 'max' if the floor "
        "turns out to be at the other end)",
    )
    parser.add_argument(
        "--restrict-apply-fraction", type=float, default=None,
        help="when using --restrict-search-fraction, also cap how far the fitted plane is applied when removing "
        "points - a window around the same end, wider than the fit fraction (e.g. fit 0.25, apply 0.5) so the "
        "floor's full extent is still removed but a coincidentally-coplanar patch at the object's far end isn't. "
        "Default: unset, meaning apply to the whole cloud (only safe if nothing at the far end matches the plane).",
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

    without_floor = pcd
    total_removed = 0
    for plane_idx in range(1, args.num_planes + 1):
        without_floor, plane_points, plane_model = remove_ground_plane(
            without_floor, distance_threshold,
            restrict_fraction=args.restrict_search_fraction, restrict_end=args.restrict_search_end,
            apply_fraction=args.restrict_apply_fraction,
        )
        removed_fraction = len(plane_points.points) / total_points
        total_removed += len(plane_points.points)
        print(
            f"[plane {plane_idx}/{args.num_planes}] Removed {len(plane_points.points)} points "
            f"({removed_fraction:.1%} of the original cloud), plane normal: {plane_model[:3].round(3)}, "
            f"{len(without_floor.points)} remain"
        )
        removed_path = output_path.parent / f"{output_path.stem}_removed_plane_{plane_idx}.ply"
        o3d.io.write_point_cloud(str(removed_path), plane_points)
        print(f"  Saved removed points -> {removed_path} (inspect to confirm it's really floor, not the object)")

    total_removed_fraction = total_removed / total_points
    if total_removed_fraction > 0.5:
        print(
            f"WARNING: removed more than half the cloud ({total_removed_fraction:.1%}) in total. For a small "
            "object on a large floor patch that's plausible, but if the object itself has a large flat surface "
            "(e.g. a sign face), this may have deleted the object instead - check the removed_plane_N.ply files."
        )

    if args.keep_largest_cluster:
        cluster_eps = diagonal * args.cluster_eps_fraction
        before = len(without_floor.points)
        without_floor = keep_largest_cluster(without_floor, cluster_eps)
        print(f"Kept largest cluster: {len(without_floor.points)} / {before} points")

    o3d.io.write_point_cloud(str(output_path), without_floor)
    print(f"Saved -> {output_path}")


if __name__ == "__main__":
    main()
