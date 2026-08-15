"""Recompute Accuracy/Completeness distance stats (same source/target
directions as evaluate_registration.py) but excluding points with no
neighbor within a distance threshold, instead of averaging over all points.

Why: the plain mean/median/rmse in evaluate_registration.py include every
point, so a point that has genuinely nothing nearby (e.g. a LiDAR point on a
part of the object that was never reconstructed, for Completeness) pulls the
average up as if it were a small local error - conflating "coverage gap"
with "the covered parts are imprecise by N cm." Dropping points whose
nearest-neighbor distance exceeds the threshold answers a narrower question:
"among the points that DID find a match, how precise is that match" -
report the drop fraction alongside it so the exclusion itself stays visible
rather than silently making the numbers look better.

Usage:
    python src/registration/compute_inlier_distance_stats.py \\
        --source outputs/density_matched/bus_stop_001/exp_055_..._density_matched.ply \\
        --target data/lidar/bus_stop_001/bus_stop_001_no_floor_centered_downsampled.ply \\
        --output outputs/metrics/reg_055_to_lidar_bus_stop_001/inlier_10cm.json \\
        --threshold 0.10
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


def inlier_stats(distances: np.ndarray, threshold: float) -> dict:
    inliers = distances[distances <= threshold]
    n_total = int(distances.size)
    n_inliers = int(inliers.size)
    if n_inliers == 0:
        return {
            "n_total": n_total, "n_inliers": 0, "n_excluded": n_total, "pct_excluded": 100.0,
            "mean": float("nan"), "median": float("nan"), "rmse": float("nan"),
            "std": float("nan"), "p95": float("nan"), "max": float("nan"),
        }
    return {
        "n_total": n_total,
        "n_inliers": n_inliers,
        "n_excluded": n_total - n_inliers,
        "pct_excluded": float((n_total - n_inliers) / n_total * 100),
        "mean": float(inliers.mean()),
        "median": float(np.median(inliers)),
        "rmse": float(np.sqrt(np.mean(inliers**2))),
        "std": float(inliers.std()),
        "p95": float(np.percentile(inliers, 95)),
        "max": float(inliers.max()),
    }


def threshold_counts(distances: np.ndarray, thresholds: list[float]) -> dict:
    n_total = int(distances.size)
    out = {}
    for t in thresholds:
        n_within = int(np.sum(distances <= t))
        out[f"{t * 100:.0f}cm"] = {
            "n_within": n_within,
            "pct_within": float(n_within / n_total * 100) if n_total else float("nan"),
        }
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", required=True, help="density-matched aligned reconstruction .ply")
    parser.add_argument("--target", required=True, help="LiDAR reference .ply")
    parser.add_argument("--output", required=True, help="path to write the JSON report to")
    parser.add_argument("--threshold", type=float, default=0.10, help="max nearest-neighbor distance (m) to keep a point (default: 0.10)")
    parser.add_argument(
        "--report-thresholds", type=float, nargs="+", default=[0.03, 0.05, 0.10],
        help="additional distance thresholds (m) to report point counts/percentages within, over the FULL "
        "(unfiltered) population - independent of --threshold (default: 0.03 0.05 0.10)",
    )
    args = parser.parse_args()

    source_path = resolve_path(args.source)
    target_path = resolve_path(args.target)
    output_path = resolve_path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"Loading source: {display_path(source_path)}")
    source = o3d.io.read_point_cloud(str(source_path))
    print(f"Loading target: {display_path(target_path)}")
    target = o3d.io.read_point_cloud(str(target_path))
    print(f"Source points: {len(source.points)}, target points: {len(target.points)}")

    accuracy_dist = np.asarray(source.compute_point_cloud_distance(target))
    completeness_dist = np.asarray(target.compute_point_cloud_distance(source))

    accuracy = inlier_stats(accuracy_dist, args.threshold)
    completeness = inlier_stats(completeness_dist, args.threshold)
    accuracy["within_thresholds"] = threshold_counts(accuracy_dist, args.report_thresholds)
    completeness["within_thresholds"] = threshold_counts(completeness_dist, args.report_thresholds)

    for name, s in [("Accuracy (source->target)", accuracy), ("Completeness (target->source)", completeness)]:
        print(f"\n{name}, threshold={args.threshold*100:.0f}cm:")
        print(f"  kept {s['n_inliers']}/{s['n_total']} points ({s['pct_excluded']:.2f}% excluded, no neighbor within threshold)")
        print(f"  mean={s['mean']*100:.2f}cm median={s['median']*100:.2f}cm rmse={s['rmse']*100:.2f}cm p95={s['p95']*100:.2f}cm max={s['max']*100:.2f}cm")
        for label, t in s["within_thresholds"].items():
            print(f"  within {label}: {t['n_within']}/{s['n_total']} ({t['pct_within']:.2f}%)")

    report = {
        "source": display_path(source_path),
        "target": display_path(target_path),
        "threshold_m": args.threshold,
        "accuracy": accuracy,
        "completeness": completeness,
    }
    output_path.write_text(json.dumps(report, indent=2))
    print(f"\nSaved -> {display_path(output_path)}")


if __name__ == "__main__":
    main()
