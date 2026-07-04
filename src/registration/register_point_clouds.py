"""Register (align) one point cloud onto another - e.g. a photogrammetry
point cloud (COLMAP, MASt3R, ...) onto a LiDAR reference scan.

Photogrammetry pipelines recover geometry only up to an unknown scale (no
metric reference), so this estimates a similarity transform - scale +
rotation + translation - not just a rigid one. Pass --rigid if both clouds
are already in the same real-world units (e.g. two LiDAR scans).

Pipeline: voxel downsample -> normal estimation -> FPFH features ->
RANSAC global registration (coarse alignment + scale) -> point-to-plane ICP
(fine alignment). Reports fitness/RMSE for both stages plus point-to-point
distance statistics between the aligned clouds, which is the actual
accuracy metric for comparing a photogrammetry reconstruction against a
LiDAR reference.

Usage:
    python src/registration/register_point_clouds.py \\
        --source outputs/exp_004_mast3r_bollard_001/exp_004_mast3r_bollard_001.ply \\
        --target outputs/exp_003_colmap_bollard_001/exp_003_colmap_bollard_001.ply \\
        --output-dir outputs/reg_004_to_003_bollard_001
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


# ---------------------------------------------------------------------------
# 1. Preprocessing
# ---------------------------------------------------------------------------

def bbox_diagonal(pcd: o3d.geometry.PointCloud) -> float:
    return float(np.linalg.norm(pcd.get_axis_aligned_bounding_box().get_extent()))


def preprocess(pcd: o3d.geometry.PointCloud, voxel_size: float):
    down = pcd.voxel_down_sample(voxel_size)
    down.estimate_normals(o3d.geometry.KDTreeSearchParamHybrid(radius=voxel_size * 2, max_nn=30))
    fpfh = o3d.pipelines.registration.compute_fpfh_feature(
        down, o3d.geometry.KDTreeSearchParamHybrid(radius=voxel_size * 5, max_nn=100)
    )
    return down, fpfh


# ---------------------------------------------------------------------------
# 2. Global registration (coarse alignment + scale, via RANSAC on FPFH matches)
# ---------------------------------------------------------------------------

def global_registration(source_down, target_down, source_fpfh, target_fpfh, voxel_size, allow_scaling):
    distance_threshold = voxel_size * 1.5
    return o3d.pipelines.registration.registration_ransac_based_on_feature_matching(
        source_down, target_down, source_fpfh, target_fpfh,
        mutual_filter=True,
        max_correspondence_distance=distance_threshold,
        estimation_method=o3d.pipelines.registration.TransformationEstimationPointToPoint(allow_scaling),
        ransac_n=4,
        checkers=[
            o3d.pipelines.registration.CorrespondenceCheckerBasedOnEdgeLength(0.9),
            o3d.pipelines.registration.CorrespondenceCheckerBasedOnDistance(distance_threshold),
        ],
        criteria=o3d.pipelines.registration.RANSACConvergenceCriteria(100000, 0.999),
    )


# ---------------------------------------------------------------------------
# 3. Local refinement (fine alignment, via point-to-plane ICP)
# ---------------------------------------------------------------------------

def refine_registration(source, target, voxel_size, initial_transform):
    distance_threshold = voxel_size * 0.4
    source.estimate_normals(o3d.geometry.KDTreeSearchParamHybrid(radius=voxel_size * 2, max_nn=30))
    target.estimate_normals(o3d.geometry.KDTreeSearchParamHybrid(radius=voxel_size * 2, max_nn=30))
    return o3d.pipelines.registration.registration_icp(
        source, target, distance_threshold, initial_transform,
        o3d.pipelines.registration.TransformationEstimationPointToPlane(),
    )


def extract_scale(transform: np.ndarray) -> float:
    linear = transform[:3, :3]
    return float(np.mean(np.linalg.norm(linear, axis=0)))


# ---------------------------------------------------------------------------
# 4. Accuracy metric: point-to-point distance after alignment
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# 5. CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", required=True, help="point cloud to align (e.g. photogrammetry output)")
    parser.add_argument("--target", required=True, help="reference point cloud to align onto (e.g. LiDAR scan)")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument(
        "--voxel-size-fraction", type=float, default=0.01,
        help="voxel size as a fraction of the target's bounding box diagonal (default: 0.01)",
    )
    parser.add_argument(
        "--rigid", action="store_true",
        help="disable scale estimation (use when both clouds are already in the same real-world units)",
    )
    args = parser.parse_args()

    source_path = resolve_path(args.source)
    target_path = resolve_path(args.target)
    output_dir = resolve_path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Loading source: {source_path}")
    source = o3d.io.read_point_cloud(str(source_path))
    print(f"Loading target: {target_path}")
    target = o3d.io.read_point_cloud(str(target_path))
    print(f"Source points: {len(source.points)}, target points: {len(target.points)}")

    voxel_size = bbox_diagonal(target) * args.voxel_size_fraction
    print(f"Voxel size: {voxel_size:.4f} (target bbox diagonal x {args.voxel_size_fraction})")

    source_down, source_fpfh = preprocess(source, voxel_size)
    target_down, target_fpfh = preprocess(target, voxel_size)
    print(f"Downsampled: source {len(source_down.points)}, target {len(target_down.points)}")

    allow_scaling = not args.rigid
    print(f"Running global registration (RANSAC + FPFH, scaling={allow_scaling})...")
    global_result = global_registration(source_down, target_down, source_fpfh, target_fpfh, voxel_size, allow_scaling)
    print(
        f"Global: fitness={global_result.fitness:.4f}, inlier_rmse={global_result.inlier_rmse:.4f}, "
        f"scale~{extract_scale(global_result.transformation):.4f}"
    )
    if global_result.fitness == 0.0:
        raise RuntimeError(
            "Global registration found no correspondences - clouds may not overlap, "
            "or try a different --voxel-size-fraction."
        )

    print("Refining with ICP (point-to-plane)...")
    icp_result = refine_registration(source, target, voxel_size, global_result.transformation)
    print(f"ICP: fitness={icp_result.fitness:.4f}, inlier_rmse={icp_result.inlier_rmse:.4f}")

    transform = icp_result.transformation
    aligned_source = copy.deepcopy(source)
    aligned_source.transform(transform)

    aligned_path = output_dir / "aligned_source.ply"
    o3d.io.write_point_cloud(str(aligned_path), aligned_source)
    transform_path = output_dir / "transform.txt"
    np.savetxt(transform_path, transform, fmt="%.8f")

    print("Computing point-to-point distances (aligned source -> target)...")
    distance_stats = point_cloud_distance_stats(aligned_source, target)
    print(
        f"Distance stats: mean={distance_stats['mean']:.4f}, rmse={distance_stats['rmse']:.4f}, "
        f"p95={distance_stats['p95']:.4f}, max={distance_stats['max']:.4f}"
    )

    report = {
        "source": display_path(source_path),
        "target": display_path(target_path),
        "voxel_size": voxel_size,
        "scaling_allowed": allow_scaling,
        "estimated_scale": extract_scale(transform),
        "global_registration": {
            "fitness": global_result.fitness,
            "inlier_rmse": global_result.inlier_rmse,
        },
        "icp_registration": {
            "fitness": icp_result.fitness,
            "inlier_rmse": icp_result.inlier_rmse,
        },
        "point_distance_stats": distance_stats,
    }
    report_path = output_dir / "report.json"
    report_path.write_text(json.dumps(report, indent=2))
    print(f"Saved aligned cloud -> {aligned_path}")
    print(f"Saved transform -> {transform_path}")
    print(f"Saved report -> {report_path}")


if __name__ == "__main__":
    main()
