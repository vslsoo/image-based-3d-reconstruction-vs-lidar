"""Evaluate a registered image-based reconstruction against a reference
point cloud (LiDAR, once available - or another photogrammetry method used
as a stand-in reference in the meantime) via cloud-to-cloud distance
metrics.

Run this on the ALIGNED source point cloud - register_point_clouds.py's
output - not the raw, un-registered reconstruction: these metrics only mean
something once both clouds are in the same coordinate frame and scale.
Floor/background should already be stripped from both clouds beforehand
(crop_point_cloud.py / remove_ground_plane.py) - a shared floor slice would
inflate Accuracy/Completeness with matches that say nothing about how well
the object itself was reconstructed.

Metrics (all in the reference cloud's real-world units, e.g. meters):
    - Accuracy@<threshold>: fraction of SOURCE (image-based) points within
      <threshold> of the nearest TARGET (reference) point - "how much of
      what I reconstructed is actually correct."
    - Completeness@<threshold>: fraction of TARGET (reference) points with
      a SOURCE point within <threshold> - "how much of the real object did
      I manage to reconstruct."
    - RMSE / median / 95th percentile: distributional stats of the
      source->target distances (the "accuracy" direction), matching the
      convention used by MVS benchmarks like Tanks and Temples. The
      target->source ("completeness" direction) distribution is reported
      alongside it, for reference.

Usage:
    python src/registration/evaluate_registration.py \\
        --source outputs/regs/reg_010_to_013_bollard_video/exp_010_colmap_aligned_to_exp_013.ply \\
        --target outputs/crops/exp_013_hloc_colmap_bollard_001_video_no_floor.ply \\
        --output outputs/regs/reg_010_to_013_bollard_video/evaluation.json

    python src/registration/evaluate_registration.py \\
        --source outputs/regs/reg_010_to_013_bollard_video/exp_010_colmap_aligned_to_exp_013.ply \\
        --target outputs/crops/exp_013_hloc_colmap_bollard_001_video_no_floor.ply \\
        --output outputs/regs/reg_010_to_013_bollard_video/evaluation.json \\
        --thresholds 0.02 0.05 0.1
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
# 1. Distances and metrics
# ---------------------------------------------------------------------------

def compute_directional_distances(
    source: o3d.geometry.PointCloud, target: o3d.geometry.PointCloud
) -> tuple[np.ndarray, np.ndarray]:
    """Nearest-neighbor distance from every source point to target (the
    "accuracy" direction) and from every target point to source (the
    "completeness" direction)."""
    source_to_target = np.asarray(source.compute_point_cloud_distance(target))
    target_to_source = np.asarray(target.compute_point_cloud_distance(source))
    return source_to_target, target_to_source


def distance_stats(distances: np.ndarray) -> dict:
    return {
        "mean": float(distances.mean()),
        "median": float(np.median(distances)),
        "rmse": float(np.sqrt(np.mean(distances ** 2))),
        "std": float(distances.std()),
        "p95": float(np.percentile(distances, 95)),
        "max": float(distances.max()),
    }


def fraction_within(distances: np.ndarray, threshold: float) -> float:
    return float(np.mean(distances <= threshold))


# ---------------------------------------------------------------------------
# 2. CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", required=True, help="aligned image-based point cloud (register_point_clouds.py output)")
    parser.add_argument("--target", required=True, help="reference point cloud (LiDAR, or a stand-in reference method)")
    parser.add_argument("--output", required=True, help="path to write the JSON report to")
    parser.add_argument(
        "--thresholds", type=float, nargs="+", default=[0.05],
        help="distance thresholds (meters) to report Accuracy@/Completeness@ for (default: 0.05)",
    )
    args = parser.parse_args()

    source_path = resolve_path(args.source)
    target_path = resolve_path(args.target)
    output_path = resolve_path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"Loading source: {source_path}")
    source = o3d.io.read_point_cloud(str(source_path))
    print(f"Loading target: {target_path}")
    target = o3d.io.read_point_cloud(str(target_path))
    print(f"Source points: {len(source.points)}, target points: {len(target.points)}")

    source_to_target, target_to_source = compute_directional_distances(source, target)

    accuracy_stats = distance_stats(source_to_target)
    completeness_stats = distance_stats(target_to_source)

    accuracy_at = {t: fraction_within(source_to_target, t) for t in args.thresholds}
    completeness_at = {t: fraction_within(target_to_source, t) for t in args.thresholds}

    print("\nAccuracy direction (source -> target):")
    print(
        f"  mean={accuracy_stats['mean']:.4f}  median={accuracy_stats['median']:.4f}  "
        f"rmse={accuracy_stats['rmse']:.4f}  p95={accuracy_stats['p95']:.4f}  max={accuracy_stats['max']:.4f}"
    )
    for t, value in accuracy_at.items():
        print(f"  Accuracy@{t * 100:.0f}cm = {value * 100:.2f}%")

    print("\nCompleteness direction (target -> source):")
    print(
        f"  mean={completeness_stats['mean']:.4f}  median={completeness_stats['median']:.4f}  "
        f"rmse={completeness_stats['rmse']:.4f}  p95={completeness_stats['p95']:.4f}  max={completeness_stats['max']:.4f}"
    )
    for t, value in completeness_at.items():
        print(f"  Completeness@{t * 100:.0f}cm = {value * 100:.2f}%")

    report = {
        "source": display_path(source_path),
        "target": display_path(target_path),
        "source_points": len(source.points),
        "target_points": len(target.points),
        "thresholds": args.thresholds,
        "accuracy_at_threshold": {f"{t * 100:.0f}cm": v for t, v in accuracy_at.items()},
        "completeness_at_threshold": {f"{t * 100:.0f}cm": v for t, v in completeness_at.items()},
        "accuracy_direction_stats": accuracy_stats,
        "completeness_direction_stats": completeness_stats,
    }
    output_path.write_text(json.dumps(report, indent=2))
    print(f"\nSaved report -> {output_path}")


if __name__ == "__main__":
    main()
