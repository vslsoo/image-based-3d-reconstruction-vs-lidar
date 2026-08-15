"""Remove source (image-based) points whose bad Accuracy is caused by a real
coverage gap in the LiDAR reference, not by reconstruction error - so
evaluate_registration.py / compute_inlier_distance_stats.py / compare_density_matched.py
/ F-score don't keep penalizing an otherwise-good reconstruction for a part
of the object the scanner never captured.

Why a plain distance threshold doesn't work: source->target distances for a
"real gap" point and a "genuinely wrong" reconstruction point look the same -
both just show up as one large number. Checked this directly on
bus_stop_001 (mast3r_ga/vggt/colmap/hloc_colmap): the accuracy-distance
histogram is unimodal and right-skewed (peak ~1-2cm, smooth falloff to
30-50cm, no valley), and forcing a 2-component GMM onto it "finds" two
components purely because it's skewed, not because two real populations
exist - the fitted crossover isn't trustworthy as a threshold.

What DOES separate the two causes: spatial coherence. A real reference gap
is a genuine, contiguous, physical region of the object with no coverage -
so the source points affected by it sit right next to each other in 3D. A
one-off reconstruction error (floating debris, a warped patch) is typically
an isolated point among otherwise well-matched neighbors. So:

    1. Take points with accuracy distance > --far-threshold (candidates).
    2. DBSCAN-cluster ONLY these candidates (not the whole cloud - the full
       reconstruction is dense/uniform and would just form one blob,
       telling you nothing; clustering only the flagged subset is what
       makes gap regions separable from scattered noise).
    3. Points in a real cluster (not DBSCAN noise) -> confirmed gap ->
       removed from the output cloud entirely.
    4. Isolated far points (DBSCAN noise) -> kept - still a real,
       unexplained error, should still be penalized.

Verified on bus_stop_001/exp_055 (mast3r_ga) by rendering the found clusters
from multiple angles: at eps=2cm every cluster that came out corresponds to
a real, contiguous structural region with no nearby LiDAR coverage (e.g. an
entire support post occluded from the scanner by the shelter's own panel)
matching gaps already noted by eye in qualitative_qc - not an artifact of
DBSCAN chaining. At eps=3cm a cluster also picked up the roof's front-edge
noise fringe, a known RECONSTRUCTION artifact (silhouette noise, not a
reference gap) already flagged in qualitative_qc - so eps=2cm was kept as
the default. Both --far-threshold and --eps are exposed, not hardcoded
project-wide: re-validate them visually (render the flagged clusters, e.g.
by adapting render_distance_heatmap.py's rendering helpers) before trusting
this on a different object/method - the object's own structure (how thin
its parts are, how large its real gaps are) determines what eps is safe.

Usage:
    python src/registration/remove_reference_gap_points.py \\
        --source outputs/density_matched/bus_stop_001/exp_055_mast3r_ga_bus_stop_001_coarse_aligned_to_bus_stop_001_no_floor_centered_density_matched.ply \\
        --target data/lidar/bus_stop_001/bus_stop_001_no_floor_centered_downsampled.ply \\
        --output outputs/gap_excluded/bus_stop_001/exp_055_mast3r_ga_gap_excluded.ply
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
# 1. Gap-cluster detection
# ---------------------------------------------------------------------------

def find_gap_point_mask(
    source: o3d.geometry.PointCloud,
    accuracy_dist: np.ndarray,
    far_threshold: float,
    eps: float,
    min_points: int,
) -> tuple[np.ndarray, list[dict]]:
    """Returns (gap_mask over ALL source points, per-cluster info for the
    report) - gap_mask[i] is True iff point i should be excluded because it
    belongs to a spatially coherent cluster of far points, not just because
    it's individually far."""
    pts = np.asarray(source.points)
    far_local_idx = np.where(accuracy_dist > far_threshold)[0]

    gap_mask = np.zeros(len(pts), dtype=bool)
    clusters_info: list[dict] = []
    if len(far_local_idx) == 0:
        return gap_mask, clusters_info

    far_pcd = o3d.geometry.PointCloud()
    far_pcd.points = o3d.utility.Vector3dVector(pts[far_local_idx])
    labels = np.array(far_pcd.cluster_dbscan(eps=eps, min_points=min_points))

    n_clusters = labels.max() + 1
    for c in range(n_clusters):
        member_local_idx = far_local_idx[labels == c]
        gap_mask[member_local_idx] = True
        cluster_pts = pts[member_local_idx]
        clusters_info.append({
            "cluster_id": c,
            "n_points": int(len(member_local_idx)),
            "centroid": cluster_pts.mean(axis=0).tolist(),
            "bbox_diag_m": float(np.linalg.norm(cluster_pts.max(axis=0) - cluster_pts.min(axis=0))),
            "mean_accuracy_dist_m": float(accuracy_dist[member_local_idx].mean()),
        })
    clusters_info.sort(key=lambda c: -c["n_points"])
    return gap_mask, clusters_info


# ---------------------------------------------------------------------------
# 2. CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", required=True, help="aligned/density-matched image-based point cloud")
    parser.add_argument("--target", required=True, help="LiDAR reference point cloud - read-only, never modified")
    parser.add_argument("--output", required=True, help="path to write the gap-excluded source .ply to")
    parser.add_argument(
        "--far-threshold", type=float, default=0.10,
        help="accuracy distance (m) above which a point is a gap-cluster CANDIDATE (default: 0.10, matches "
        "compute_inlier_distance_stats.py's default inlier cutoff)",
    )
    parser.add_argument(
        "--eps", type=float, default=0.02,
        help="DBSCAN radius (m) for clustering candidate far points (default: 0.02 = 2cm, validated by "
        "visual inspection on bus_stop_001/exp_055 - re-validate on other objects, see module docstring)",
    )
    parser.add_argument("--min-points", type=int, default=10, help="DBSCAN min_points (default: 10)")
    args = parser.parse_args()

    source_path = resolve_path(args.source)
    target_path = resolve_path(args.target)
    output_path = resolve_path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"Loading source: {display_path(source_path)}")
    source = o3d.io.read_point_cloud(str(source_path))
    print(f"Loading target (reference, read-only): {display_path(target_path)}")
    target = o3d.io.read_point_cloud(str(target_path))
    print(f"Source points: {len(source.points)}, target points: {len(target.points)}")

    accuracy_dist = np.asarray(source.compute_point_cloud_distance(target))
    gap_mask, clusters_info = find_gap_point_mask(
        source, accuracy_dist, args.far_threshold, args.eps, args.min_points,
    )

    n_total = len(source.points)
    n_gap = int(gap_mask.sum())
    n_far = int((accuracy_dist > args.far_threshold).sum())
    n_isolated_far = n_far - n_gap

    print(f"\nFar candidates (>{args.far_threshold*100:.0f}cm): {n_far} ({n_far/n_total*100:.2f}%)")
    print(f"  -> in a gap cluster (excluded): {n_gap} ({n_gap/n_total*100:.2f}%), {len(clusters_info)} clusters")
    print(f"  -> isolated/noise (kept, still penalized): {n_isolated_far} ({n_isolated_far/n_total*100:.2f}%)")
    print("\nTop clusters:")
    for c in clusters_info[:10]:
        print(
            f"  cluster {c['cluster_id']}: {c['n_points']} points, bbox_diag={c['bbox_diag_m']*100:.1f}cm, "
            f"mean_dist={c['mean_accuracy_dist_m']*100:.1f}cm, centroid={[round(x,3) for x in c['centroid']]}"
        )

    kept_idx = np.where(~gap_mask)[0].tolist()
    filtered = source.select_by_index(kept_idx)
    o3d.io.write_point_cloud(str(output_path), filtered)
    print(f"\nSource: {n_total} -> {len(filtered.points)} points (removed {n_gap} gap-cluster points)")
    print(f"Saved -> {display_path(output_path)}")

    report = {
        "source": display_path(source_path),
        "target": display_path(target_path),
        "output": display_path(output_path),
        "far_threshold_m": args.far_threshold,
        "eps_m": args.eps,
        "min_points": args.min_points,
        "n_total": n_total,
        "n_far_candidates": n_far,
        "n_excluded_gap_points": n_gap,
        "n_isolated_far_kept": n_isolated_far,
        "pct_excluded": n_gap / n_total * 100,
        "n_clusters": len(clusters_info),
        "clusters": clusters_info,
    }
    report_path = output_path.with_suffix(".json")
    report_path.write_text(json.dumps(report, indent=2))
    print(f"Saved report -> {display_path(report_path)}")


if __name__ == "__main__":
    main()
