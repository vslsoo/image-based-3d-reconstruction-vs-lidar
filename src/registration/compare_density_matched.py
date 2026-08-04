"""Compare Accuracy/Completeness/F-score across several aligned reconstructions
of the same object against one shared LiDAR reference, after voxel-downsampling
every aligned cloud to roughly the same point count as the sparsest one.

Why this matters: Completeness (target -> source, "how much of the real
object did I manage to reconstruct") is easy to inflate purely by having more
points - a denser cloud has smaller gaps between points, so more target
points end up with SOME nearby source point regardless of whether the
underlying reconstruction is actually more complete geometrically. Comparing
raw-density Accuracy/Completeness/F-score across methods (e.g. a 5.8M-point
VGGT cloud against a 376k-point COLMAP cloud) confounds "reconstructed the
object more completely" with "sampled more densely." Matching point count
before comparing removes that confound, so any remaining gap reflects
reconstruction quality rather than point budget.

Only the SOURCE (image-based) clouds are downsampled here, never the LiDAR
target - it's the reference everything is measured against, already sparse,
and untouched by however many points each method's source happens to have.

Usage:
    python src/registration/compare_density_matched.py \\
        --aligned outputs/registrations/reg_023_to_lidar_bench_001_v3/exp_023_vggt_bench_001_no_floor_aligned_to_bench_001_lidar.ply vggt \\
        --aligned outputs/registrations/reg_024_to_lidar_bench_001/exp_024_mast3r_ga_bench_001_no_floor_aligned_to_bench_001_lidar.ply mast3r_ga \\
        --aligned outputs/registrations/reg_025_to_lidar_bench_001/exp_025_colmap_bench_001_no_floor_aligned_to_bench_001_lidar.ply colmap \\
        --aligned outputs/registrations/reg_026_to_lidar_bench_001/exp_026_hloc_colmap_bench_001_no_floor_aligned_to_bench_001_lidar.ply hloc_colmap \\
        --target data/raw/bench_001/lidar/bench_001_lidar.ply \\
        --output outputs/metrics/bench_001_density_matched_comparison.json
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


# ---------------------------------------------------------------------------
# 1. Density matching
# ---------------------------------------------------------------------------

def downsample_to_point_count(
    pcd: o3d.geometry.PointCloud, target_count: int, tol: float = 0.02, max_iter: int = 40,
) -> o3d.geometry.PointCloud:
    """Voxel-downsample pcd until its point count is within `tol` (relative)
    of target_count, via binary search on voxel size - voxel_down_sample's
    output count is monotonically non-increasing in voxel size, so this
    converges. Clouds already at or below target_count are returned as-is
    (nothing to remove; this only thins denser clouds down to match)."""
    if len(pcd.points) <= target_count:
        return pcd

    bbox_diag = float(np.linalg.norm(pcd.get_axis_aligned_bounding_box().get_extent()))
    lo, hi = bbox_diag * 1e-5, bbox_diag
    best = pcd
    for _ in range(max_iter):
        mid = (lo + hi) / 2
        down = pcd.voxel_down_sample(mid)
        n = len(down.points)
        if n == 0:
            hi = mid
            continue
        best = down
        if abs(n - target_count) / target_count <= tol:
            break
        if n > target_count:
            lo = mid
        else:
            hi = mid
    return best


# ---------------------------------------------------------------------------
# 2. Metrics (same definitions as evaluate_registration.py)
# ---------------------------------------------------------------------------

def compute_directional_distances(
    source: o3d.geometry.PointCloud, target: o3d.geometry.PointCloud
) -> tuple[np.ndarray, np.ndarray]:
    source_to_target = np.asarray(source.compute_point_cloud_distance(target))
    target_to_source = np.asarray(target.compute_point_cloud_distance(source))
    return source_to_target, target_to_source


def fraction_within(distances: np.ndarray, threshold: float) -> float:
    return float(np.mean(distances <= threshold))


def rmse_within(distances: np.ndarray, threshold: float) -> float:
    inliers = distances[distances <= threshold]
    if inliers.size == 0:
        return float("nan")
    return float(np.sqrt(np.mean(inliers ** 2)))


def f_score(precision: float, recall: float) -> float:
    if precision + recall == 0:
        return 0.0
    return float(2 * precision * recall / (precision + recall))


# ---------------------------------------------------------------------------
# 3. CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--aligned", nargs=2, action="append", metavar=("PATH", "LABEL"), required=True,
        help="an aligned source point cloud (register_point_clouds.py output) and a short label for it "
        "- repeat for each method being compared",
    )
    parser.add_argument("--target", required=True, help="reference point cloud (LiDAR) - never downsampled")
    parser.add_argument("--output", required=True, help="path to write the JSON report to")
    parser.add_argument(
        "--thresholds", type=float, nargs="+", default=[0.03, 0.05, 0.1],
        help="distance thresholds (meters) to report Accuracy@/Completeness@/F-score@ for "
        "(default: 0.03 0.05 0.1)",
    )
    args = parser.parse_args()

    target_path = resolve_path(args.target)
    output_path = resolve_path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"Loading target: {target_path}")
    target = o3d.io.read_point_cloud(str(target_path))
    print(f"Target points: {len(target.points)}")

    clouds = {}
    for path_str, label in args.aligned:
        path = resolve_path(path_str)
        print(f"Loading {label}: {path}")
        clouds[label] = (path, o3d.io.read_point_cloud(str(path)))

    for label, (_, pcd) in clouds.items():
        print(f"  {label}: {len(pcd.points)} points")

    match_count = min(len(pcd.points) for _, pcd in clouds.values())
    sparsest_label = min(clouds, key=lambda label: len(clouds[label][1].points))
    print(f"\nSparsest: {sparsest_label} ({match_count} points) - downsampling every cloud to match...")

    results = {}
    for label, (path, pcd) in clouds.items():
        matched = downsample_to_point_count(pcd, match_count)
        print(f"  {label}: {len(pcd.points)} -> {len(matched.points)} points")

        source_to_target, target_to_source = compute_directional_distances(matched, target)
        accuracy_at = {t: fraction_within(source_to_target, t) for t in args.thresholds}
        completeness_at = {t: fraction_within(target_to_source, t) for t in args.thresholds}
        accuracy_rmse_at = {t: rmse_within(source_to_target, t) for t in args.thresholds}
        completeness_rmse_at = {t: rmse_within(target_to_source, t) for t in args.thresholds}
        f_score_at = {t: f_score(accuracy_at[t], completeness_at[t]) for t in args.thresholds}

        results[label] = {
            "source": display_path(path),
            "original_points": len(pcd.points),
            "matched_points": len(matched.points),
            "accuracy_at_threshold": {f"{t * 100:.0f}cm": v for t, v in accuracy_at.items()},
            "completeness_at_threshold": {f"{t * 100:.0f}cm": v for t, v in completeness_at.items()},
            "accuracy_rmse_at_threshold": {f"{t * 100:.0f}cm": v for t, v in accuracy_rmse_at.items()},
            "completeness_rmse_at_threshold": {f"{t * 100:.0f}cm": v for t, v in completeness_rmse_at.items()},
            "f_score_at_threshold": {f"{t * 100:.0f}cm": v for t, v in f_score_at.items()},
        }

    print("\nDensity-matched comparison:")
    header = f"{'method':<14}{'pts (orig -> matched)':<24}" + "".join(
        f"{'Acc/Comp/F@' + str(int(t * 100)) + 'cm':<24}" for t in args.thresholds
    )
    print(header)
    for label, r in results.items():
        points_str = f"{r['original_points']} -> {r['matched_points']}"
        row = f"{label:<14}{points_str:<24}"
        for t in args.thresholds:
            key = f"{t * 100:.0f}cm"
            a = r["accuracy_at_threshold"][key] * 100
            c = r["completeness_at_threshold"][key] * 100
            f = r["f_score_at_threshold"][key] * 100
            row += f"{f'{a:.1f}/{c:.1f}/{f:.1f}':<24}"
        print(row)

    report = {
        "target": display_path(target_path),
        "target_points": len(target.points),
        "thresholds": args.thresholds,
        "matched_point_count": match_count,
        "sparsest_method": sparsest_label,
        "methods": results,
    }
    output_path.write_text(json.dumps(report, indent=2))
    print(f"\nSaved report -> {output_path}")


if __name__ == "__main__":
    main()
