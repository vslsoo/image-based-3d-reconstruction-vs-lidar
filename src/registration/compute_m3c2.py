"""Compute M3C2 (Multiscale Model to Model Cloud Comparison, Lague, Brodu &
Leroux 2013) distances between an aligned image-based reconstruction and its
LiDAR reference, via py4dgeo - the reference implementation from the
algorithm's original research group (3DGeo Heidelberg).

How this differs from evaluate_registration.py: Accuracy/Completeness there
are plain nearest-neighbor distances - "closest point in any direction."
M3C2 instead measures the distance along each core point's own local surface
normal (so slope/curvature-consistent, not skewed by whatever's nearest in an
arbitrary direction), and reports a Level of Detection per point
(LoD95% = 1.96 * (sqrt(spread1^2/n1 + spread2^2/n2)) + registration_error) -
the offset below which a difference isn't distinguishable from local cloud
roughness plus a given registration error, rather than treating every offset
as equally meaningful regardless of how noisy the clouds are there.

Core points (--corepoints): running M3C2 at every point of a multi-million-
point photogrammetry cloud is both unnecessary and slow (each core point
does a radius search against both epochs), and this project's four bench
reconstructions range 15x in raw point count (377k-5.8M) - comparing them at
their native densities would make core point coverage wildly uneven across
methods too. Defaults to the SOURCE (image-based) cloud, voxel-downsampled
with --corepoint-voxel-size (default 0.03m = 3cm, half of the projection
scale d below - dense enough that neighboring cylinders still overlap for
continuous coverage, coarse enough to avoid redundant, highly-correlated
core points and keep runtime reasonable). At 3cm this brings all four bench
methods down to a comparable 7.5k-15.6k core points regardless of their raw
density (vs. 377k-5811k un-downsampled) - point budget stops being a
confound between methods, the same concern compare_density_matched.py
addresses for Accuracy/Completeness. Pass --corepoints target to compute at
the LiDAR points instead (normals/reference role switch accordingly - see
run_m3c2()).

Choosing D (normal scale) and d (projection/cylinder scale): the default
scan used here (bench_001's LiDAR crop, 9118 points over a ~4.9m bbox
diagonal) has a median nearest-neighbor spacing of ~1.7cm (mean ~2.1cm,
90th-percentile ~3.7cm) - deriving D and d from THIS, the sparser of the two
clouds in every cylinder, is what matters: the denser photogrammetry side of
each comparison always has enough points regardless.
  - D=10cm (normal_radii=[0.05]): a local-plane roughness scan at increasing
    radii (fit a plane via PCA in a neighborhood, measure the RMS residual)
    showed roughness climbing steadily with radius rather than plateauing -
    expected for a bench (seat, backrest, thin ~5-8cm legs, real edges
    between them), not a flat surface where a clean "noise vs. signal"
    elbow would appear. At r=5cm (D=10cm) the neighborhood already averages
    ~21 points (a comfortable margin over the ~10-15 usually wanted for a
    stable PCA normal) while RMS roughness stays under 1cm - a scale wide
    enough for a robust normal without regularly bridging two genuinely
    different surfaces (e.g. a leg's opposite faces, or the seat/backrest
    corner).
  - d=6cm (projection_scale, cyl_radius=0.03): kept smaller than D, which is
    standard M3C2 practice (the comparison cylinder should stay more
    localized to the core point than the broader neighborhood used just to
    orient the normal) and still ~3x the median LiDAR spacing, enough for
    a handful of points from the sparse side per cylinder in most areas.
These are exposed as --normal-scale/--projection-scale, not hardcoded -
re-run the roughness scan for a different object's LiDAR crop before trusting
these specific values there.

Usage:
    python src/registration/compute_m3c2.py \\
        --source outputs/registrations/reg_026_to_lidar_bench_001/exp_026_hloc_colmap_bench_001_no_floor_aligned_to_bench_001_lidar.ply \\
        --target data/video/bench_001/lidar/bench_001_lidar.ply \\
        --output outputs/metrics/reg_026_to_lidar_bench_001/m3c2.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import open3d as o3d
import py4dgeo

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
# 1. M3C2
# ---------------------------------------------------------------------------

def run_m3c2(
    reference_points: np.ndarray,
    comparison_points: np.ndarray,
    corepoints: np.ndarray,
    normal_scale: float,
    projection_scale: float,
    registration_error: float,
) -> tuple[np.ndarray, np.ndarray]:
    """reference is epoch1 - corepoints must be drawn from it (that's what
    "core points" means: locations on epoch1 the comparison is evaluated
    at), and by default py4dgeo also estimates each corepoint's normal from
    epoch1, which only makes geometric sense if the corepoint actually lies
    on that surface. comparison is epoch2. A positive distance means the
    comparison cloud sits further along the outward reference-surface normal
    than the reference at that point, negative means it sits inside/behind
    it."""
    epoch_reference = py4dgeo.Epoch(reference_points.astype(np.float64))
    epoch_comparison = py4dgeo.Epoch(comparison_points.astype(np.float64))
    m3c2 = py4dgeo.M3C2(
        epochs=(epoch_reference, epoch_comparison),
        corepoints=corepoints.astype(np.float64),
        cyl_radius=projection_scale / 2,
        normal_radii=[normal_scale / 2],
        registration_error=registration_error,
    )
    return m3c2.run()


# ---------------------------------------------------------------------------
# 2. CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", required=True, help="aligned image-based point cloud (register_point_clouds.py output)")
    parser.add_argument("--target", required=True, help="reference point cloud (LiDAR)")
    parser.add_argument("--output", required=True, help="path to write the JSON report to")
    parser.add_argument(
        "--corepoints", choices=["source", "target"], default="source",
        help="which cloud's points to compute M3C2 at, voxel-downsampled by --corepoint-voxel-size first "
        "(default: source - the image-based reconstruction; see module docstring). Its normals are also "
        "estimated from this same cloud, since corepoints must actually lie on it.",
    )
    parser.add_argument(
        "--corepoint-voxel-size", type=float, default=0.03,
        help="voxel-downsample the corepoints cloud to this spacing (meters) before computing M3C2 "
        "(default: 0.03m = 3cm, half the projection scale d - see module docstring). Set to 0 to use the "
        "cloud at native resolution.",
    )
    parser.add_argument(
        "--normal-scale", type=float, default=0.10,
        help="D: diameter (meters) of the neighborhood used to estimate each core point's local surface "
        "normal (default: 0.10m - derived from bench_001's LiDAR point spacing, see module docstring)",
    )
    parser.add_argument(
        "--projection-scale", type=float, default=0.06,
        help="d: diameter (meters) of the cylinder used to collect corresponding points from both clouds "
        "(default: 0.06m - see module docstring)",
    )
    parser.add_argument(
        "--registration-error", type=float, default=0.01,
        help="assumed alignment/registration error (meters), folded into the Level of Detection (LoD95) "
        "threshold (default: 0.01m = 1cm)",
    )
    args = parser.parse_args()

    source_path = resolve_path(args.source)
    target_path = resolve_path(args.target)
    output_path = resolve_path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"Loading source: {source_path}")
    source_pcd = o3d.io.read_point_cloud(str(source_path))
    print(f"Loading target: {target_path}")
    target_pcd = o3d.io.read_point_cloud(str(target_path))
    print(f"Source points: {len(source_pcd.points)}, target points: {len(target_pcd.points)}")

    # Corepoints are drawn from - and normals estimated from - the same
    # cloud (the "reference"); the other cloud is the "comparison" the
    # reference is measured against. See run_m3c2()'s docstring.
    reference_pcd = source_pcd if args.corepoints == "source" else target_pcd
    comparison_pcd = target_pcd if args.corepoints == "source" else source_pcd

    corepoint_pcd = reference_pcd.voxel_down_sample(args.corepoint_voxel_size) if args.corepoint_voxel_size else reference_pcd
    corepoints = np.asarray(corepoint_pcd.points, dtype=np.float64)
    print(f"Core points (from {args.corepoints}, reference cloud): {len(corepoints)}")

    print(
        f"Running M3C2 (D={args.normal_scale * 100:.0f}cm, d={args.projection_scale * 100:.0f}cm, "
        f"registration_error={args.registration_error * 100:.0f}cm)..."
    )
    distances, uncertainties = run_m3c2(
        np.asarray(reference_pcd.points),
        np.asarray(comparison_pcd.points),
        corepoints,
        args.normal_scale,
        args.projection_scale,
        args.registration_error,
    )

    valid = np.isfinite(distances)
    n_total = len(distances)
    n_valid = int(valid.sum())
    lod95 = uncertainties["lodetection"]
    has_lod = valid & np.isfinite(lod95)
    significant = has_lod & (np.abs(distances) > lod95)

    valid_distances = distances[valid]
    abs_valid = np.abs(valid_distances)
    stats = {
        "mean_abs": float(abs_valid.mean()),
        "median_abs": float(np.median(abs_valid)),
        "rmse": float(np.sqrt(np.mean(valid_distances ** 2))),
        "std": float(valid_distances.std()),
        "p95_abs": float(np.percentile(abs_valid, 95)),
        "max_abs": float(abs_valid.max()),
        "mean_signed": float(valid_distances.mean()),
    } if n_valid else None

    print(
        f"\nCore points: {n_total} ({n_valid} valid, {n_total - n_valid} undefined - too few neighbors "
        "in one/both clouds within the cylinder)"
    )
    if stats:
        print(
            f"|M3C2 distance| (valid points): mean={stats['mean_abs']:.4f}  median={stats['median_abs']:.4f}  "
            f"rmse={stats['rmse']:.4f}  p95={stats['p95_abs']:.4f}  max={stats['max_abs']:.4f}"
        )
        n_lod = int(has_lod.sum())
        n_sig = int(significant.sum())
        frac_sig = n_sig / n_lod if n_lod else None
        print(
            f"Significant at 95% LoD (|distance| > LoD95, i.e. beyond cloud roughness + "
            f"{args.registration_error * 100:.0f}cm registration error): {n_sig} / {n_lod} points with a "
            f"defined LoD ({100 * frac_sig:.2f}%)" if n_lod else "No points had a defined LoD (too few "
            "neighbors everywhere - increase --normal-scale/--projection-scale)."
        )
    else:
        print("No valid M3C2 distances - every core point had too few neighbors in at least one cloud. "
              "Increase --normal-scale/--projection-scale.")

    distances_path = output_path.with_suffix(".distances.npz")
    np.savez(
        distances_path,
        corepoints=corepoints,
        distances=distances,
        lodetection=uncertainties["lodetection"],
        spread1=uncertainties["spread1"],
        num_samples1=uncertainties["num_samples1"],
        spread2=uncertainties["spread2"],
        num_samples2=uncertainties["num_samples2"],
    )

    report = {
        "source": display_path(source_path),
        "target": display_path(target_path),
        "corepoints_from": args.corepoints,
        "corepoint_voxel_size": args.corepoint_voxel_size,
        "reference_cloud": "source" if args.corepoints == "source" else "target",
        "comparison_cloud": "target" if args.corepoints == "source" else "source",
        "distance_sign_convention": (
            "positive = comparison cloud is further out along the reference cloud's own surface normal"
        ),
        "num_corepoints": n_total,
        "num_valid": n_valid,
        "normal_scale_D": args.normal_scale,
        "projection_scale_d": args.projection_scale,
        "registration_error": args.registration_error,
        "distance_stats": stats,
        "num_with_defined_lod": int(has_lod.sum()),
        "num_significant_at_lod95": int(significant.sum()),
        "fraction_significant_at_lod95": (int(significant.sum()) / int(has_lod.sum())) if has_lod.sum() else None,
        "per_point_distances_file": display_path(distances_path),
    }
    output_path.write_text(json.dumps(report, indent=2))
    print(f"\nSaved report -> {output_path}")
    print(f"Saved per-point distances/uncertainties -> {distances_path}")


if __name__ == "__main__":
    main()
