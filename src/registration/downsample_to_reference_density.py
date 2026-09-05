"""Voxel-downsample an aligned image-based reconstruction to match the point
spacing of the reference (LiDAR) cloud it will be scored against, before
running evaluate_registration.py / compare_density_matched.py.

Why this is a separate step: Accuracy/Completeness/F-score/Chamfer distance
are all nearest-neighbor-distance metrics, so they are density-dependent -
a denser cloud has smaller gaps between points and so smaller nearest-
neighbor distances almost by construction, independent of whether it is
geometrically more correct. If the reconstruction is much denser than the
LiDAR reference, its Accuracy/F-score gets inflated purely by point count,
not by better geometry. This is why the DTU MVS evaluation protocol
downsamples the reconstruction before computing Chamfer accuracy/
completeness (dense, well-textured regions otherwise dominate the metric),
and why the official Tanks and Temples toolbox voxel-downsamples both
clouds to a common resolution tied to the per-scene distance threshold
before computing precision/recall/F-score.

Only the SOURCE (image-based) cloud is downsampled here, never the
reference - matching the convention already used in
compare_density_matched.py. The LiDAR cloud's point spacing reflects the
scanner's actual physical sampling limit; thinning it further would just
discard real measurements for no benefit, whereas the source cloud's
density is an artifact of the reconstruction pipeline (denser in
well-textured regions, sparser elsewhere) that has nothing to do with
geometric accuracy.

Resolution used for matching: a fixed 1 cm voxel (DEFAULT_VOXEL_M), the grid
the LiDAR references are delivered thinned onto. This replaces the earlier
per-object "median nearest-neighbor distance of the reference" rule, which
read *below* the true grid pitch wherever overlapping scan passes left exact-
duplicate points at zero distance, and so thinned the source too finely. The
reference's median NN-spacing is still computed and reported for context, and
`--voxel 0` restores the old behaviour. Voxel downsampling only ever thins
points (never invents new ones), so if the source is already sparser than the
grid this is a no-op.

Usage:
    python src/registration/downsample_to_reference_density.py \\
        --source outputs/registrations/reg_025_to_lidar_bench_001/exp_025_colmap_bench_001_no_floor_aligned_to_bench_001_lidar.ply \\
        --target data/video/bench_001/lidar/bench_001_lidar.ply \\
        --output outputs/registrations/reg_025_to_lidar_bench_001/exp_025_colmap_bench_001_density_matched.ply

    # Use e.g. 2x the reference spacing as the voxel size, if you want the
    # source thinned more aggressively than a 1:1 spacing match:
    python src/registration/downsample_to_reference_density.py \\
        --source ... --target ... --output ... --spacing-multiplier 2.0
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import open3d as o3d
from scipy.spatial import cKDTree

PROJECT_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_VOXEL_M = 0.01
# The LiDAR references are delivered thinned onto a 1 cm grid, so that pitch - not each
# cloud's measured median NN-spacing - is the reference's real sampling limit. The measured
# median actually reads *below* the pitch, because overlapping scan passes leave exact-
# duplicate points at zero distance (bus_stop_001: 1.00 cm as delivered vs 1.41 cm once
# duplicates are dropped), which would thin the source too finely. Keep the same value as
# VOXEL_M in the page/table builders so every number in the reports is comparable.


def resolve_path(path_str: str) -> Path:
    path = Path(path_str)
    return path if path.is_absolute() else (PROJECT_ROOT / path).resolve()


def display_path(path: Path) -> str:
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


# ---------------------------------------------------------------------------
# 1. Reference spacing + density-matching downsample
# ---------------------------------------------------------------------------

def median_nearest_neighbor_spacing(points: np.ndarray, sample_size: int = 200_000) -> float:
    """Characteristic point spacing of a cloud: median distance from each
    point to its single nearest neighbor. Subsampled for speed on large
    clouds - the median is stable well below the full point count."""
    sample = points
    if sample_size and len(points) > sample_size:
        idx = np.random.default_rng(42).choice(len(points), sample_size, replace=False)
        sample = points[idx]

    tree = cKDTree(points)
    distances, _ = tree.query(sample, k=2)  # k=1 is the point itself (distance 0)
    return float(np.median(distances[:, 1]))


def downsample_to_spacing(pcd: o3d.geometry.PointCloud, voxel_size: float) -> o3d.geometry.PointCloud:
    if voxel_size <= 0:
        return pcd
    return pcd.voxel_down_sample(voxel_size)


# ---------------------------------------------------------------------------
# 2. CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", required=True, help="aligned image-based point cloud (register_point_clouds.py output)")
    parser.add_argument("--target", required=True, help="reference point cloud (LiDAR) - read-only, never modified")
    parser.add_argument("--output", required=True, help="path to write the density-matched source .ply to")
    parser.add_argument(
        "--voxel", type=float, default=DEFAULT_VOXEL_M,
        help=f"voxel size in metres (default: {DEFAULT_VOXEL_M}, the grid the LiDAR references are "
        "delivered on). Pass --voxel 0 to fall back to the reference's own median nearest-neighbor "
        "spacing instead of the fixed grid.",
    )
    parser.add_argument(
        "--spacing-multiplier", type=float, default=1.0,
        help="multiply the voxel size by this before use (default: 1.0; >1 thins more aggressively). "
        "Applies to whichever voxel size was chosen above.",
    )
    args = parser.parse_args()

    source_path = resolve_path(args.source)
    target_path = resolve_path(args.target)
    output_path = resolve_path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"Loading source: {source_path}")
    source = o3d.io.read_point_cloud(str(source_path))
    print(f"Loading target (reference, read-only): {target_path}")
    target = o3d.io.read_point_cloud(str(target_path))
    # Exact-duplicate points (overlapping scan passes, byte-identical coordinates) sit at
    # zero nearest-neighbour distance and drag the reported median below the true grid
    # pitch, so drop them before measuring - even though nothing here writes the reference.
    _tp = np.asarray(target.points)
    _, _uniq_idx = np.unique(_tp, axis=0, return_index=True)
    if len(_uniq_idx) < len(_tp):
        target = target.select_by_index(np.sort(_uniq_idx).tolist())
        print(f"Deduplicated reference for measurement: {len(_tp)} -> {len(_uniq_idx)} points")
    print(f"Source points: {len(source.points)}, target points: {len(target.points)}")

    target_points = np.asarray(target.points)
    reference_spacing = median_nearest_neighbor_spacing(target_points)
    base_voxel = args.voxel if args.voxel > 0 else reference_spacing
    basis = "fixed reference grid" if args.voxel > 0 else "reference median NN-spacing"
    voxel_size = base_voxel * args.spacing_multiplier
    print(f"\nReference median nearest-neighbor spacing: {reference_spacing:.5f} m (reported, not necessarily used)")
    print(f"Voxel size used for source downsampling: {voxel_size:.5f} m "
          f"({basis} {base_voxel:.5f} m x{args.spacing_multiplier})")

    matched = downsample_to_spacing(source, voxel_size)
    print(f"Source: {len(source.points)} -> {len(matched.points)} points")

    o3d.io.write_point_cloud(str(output_path), matched)
    print(f"\nSaved density-matched source -> {display_path(output_path)}")

    report_path = output_path.with_suffix(".json")
    report = {
        "source": display_path(source_path),
        "target": display_path(target_path),
        "output": display_path(output_path),
        "source_points_original": len(source.points),
        "source_points_matched": len(matched.points),
        "target_points": len(target_points),
        "reference_median_nn_spacing_m": reference_spacing,
        "voxel_basis": basis,
        "base_voxel_m": base_voxel,
        "spacing_multiplier": args.spacing_multiplier,
        "voxel_size_m": voxel_size,
    }
    report_path.write_text(json.dumps(report, indent=2))
    print(f"Saved report -> {display_path(report_path)}")


if __name__ == "__main__":
    main()
