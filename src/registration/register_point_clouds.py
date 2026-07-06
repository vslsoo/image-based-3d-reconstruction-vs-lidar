"""Register (align) one point cloud onto another - e.g. a photogrammetry
point cloud (COLMAP, MASt3R, ...) onto a LiDAR reference scan.

Photogrammetry pipelines recover geometry only up to an unknown scale (no
metric reference), so this estimates a similarity transform - scale +
rotation + translation - not just a rigid one. Pass --rigid if both clouds
are already in the same real-world units (e.g. two LiDAR scans).

Three ways to get the initial (coarse) alignment before ICP refinement:
  - automatic (default): voxel downsample -> normal estimation -> FPFH
    features -> RANSAC global registration. Works well for objects with
    distinctive, non-symmetric geometry. If its fitness comes back low
    (a symptom of rotational symmetry - see below), this automatically
    retries with --axis-sweep instead.
  - --axis-sweep: for elongated, axially-symmetric objects (bollards, posts,
    pipes, ...) where FPFH+RANSAC has no geometric signal to pick the
    correct rotation about the object's own axis - every point around the
    circumference looks alike to it. PCA finds each cloud's own principal
    axis (centroid + dominant direction of variance), which fixes
    translation and 2 of 3 rotation DOF automatically and unambiguously
    (no correspondence search needed); the one remaining DOF - rotation
    about that axis, genuinely undetermined by a perfectly symmetric
    shape's geometry - is resolved with a cheap brute-force angle sweep
    scored by point-to-point distance.
  - --manual: both clouds are shown together in one window, pushed apart
    side by side and colored red (source) / blue (target), and you click
    >=3 matching pairs by alternating: a point on the red cloud, then its
    match on the blue cloud, and so on. The initial transform is computed
    directly from those correspondences.

Either way, the coarse transform is then refined with point-to-plane ICP.
Reports fitness/RMSE for both stages plus point-to-point distance
statistics between the aligned clouds, which is the actual accuracy metric
for comparing a photogrammetry reconstruction against a LiDAR reference.

Usage:
    python src/registration/register_point_clouds.py \\
        --source outputs/exp_004_mast3r_bollard_001/exp_004_mast3r_bollard_001.ply \\
        --target outputs/exp_003_colmap_bollard_001/exp_003_colmap_bollard_001.ply \\
        --output-dir outputs/reg_004_to_003_bollard_001

    python src/registration/register_point_clouds.py \\
        --source outputs/crops/exp_004_mast3r_bollard_001_cropped.ply \\
        --target outputs/crops/exp_003_colmap_bollard_001_cropped.ply \\
        --output-dir outputs/reg_004_to_003_bollard_001_cropped \\
        --manual
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
# 2b. Manual seeding (coarse alignment from user-picked corresponding points)
# ---------------------------------------------------------------------------

def pick_paired_points(source: o3d.geometry.PointCloud, target: o3d.geometry.PointCloud) -> tuple[list[int], list[int]]:
    """Show both clouds together in one window, pushed apart side by side so
    they don't overlap on screen, keeping each cloud's own photographed
    colors (easier to spot matching features than flat colors) - and let
    the user pick corresponding points by alternating: one point on the
    source side, then its match on the target side, and so on."""
    source_display = copy.deepcopy(source)
    target_display = copy.deepcopy(target)
    # flat color is only a fallback for clouds without their own vertex colors
    if not source_display.has_colors():
        source_display.paint_uniform_color([0.85, 0.1, 0.1])
    if not target_display.has_colors():
        target_display.paint_uniform_color([0.1, 0.4, 0.9])

    # push apart along the widest axis so the two clouds sit side by side, not overlaid
    source_extent = source_display.get_axis_aligned_bounding_box().get_extent()
    target_extent = target_display.get_axis_aligned_bounding_box().get_extent()
    axis = int(np.argmax(np.maximum(source_extent, target_extent)))
    axis_name = "XYZ"[axis]
    gap = max(source_extent[axis], target_extent[axis]) * 1.2
    shift = np.zeros(3)
    shift[axis] = gap
    target_display.translate(shift)

    n_source = len(source_display.points)
    combined = source_display + target_display

    print(f"\nClouds keep their own colors. TARGET is shifted +{gap:.3f} along {axis_name} relative to SOURCE,")
    print("so SOURCE is the one at the original (lower) position, TARGET is the one pushed away.")
    print("Pick corresponding points by alternating: one point on SOURCE, then its match on TARGET,")
    print("then repeat - same physical feature each time (a scratch, a bolt, the same base corner).")
    print("shift+left-click: pick   shift+right-click: undo last pick   'Q': done, at least 3 pairs")
    window_title = (
        f"SOURCE=origin, TARGET=+{axis_name} shifted | alternate src/tgt | "
        "shift+click=pick, shift+right-click=undo, Q=done (>=3 pairs)"
    )
    vis = o3d.visualization.VisualizerWithEditing()
    vis.create_window(window_name=window_title)
    vis.add_geometry(combined)
    vis.get_render_option().point_size = 2.0
    vis.run()
    vis.destroy_window()

    picked = vis.get_picked_points()
    if len(picked) < 6 or len(picked) % 2 != 0:
        raise RuntimeError(
            f"Need an even number of picks (>=6), alternating source/target in pairs; got {len(picked)}."
        )

    source_idx, target_idx = [], []
    for i, global_idx in enumerate(picked):
        if i % 2 == 0:
            if global_idx >= n_source:
                raise RuntimeError(f"Pick #{i + 1} should be on SOURCE, but landed on TARGET.")
            source_idx.append(global_idx)
        else:
            if global_idx < n_source:
                raise RuntimeError(f"Pick #{i + 1} should be on TARGET, but landed on SOURCE.")
            target_idx.append(global_idx - n_source)
    return source_idx, target_idx


def manual_initial_transform(source: o3d.geometry.PointCloud, target: o3d.geometry.PointCloud, allow_scaling: bool) -> np.ndarray:
    source_idx, target_idx = pick_paired_points(source, target)
    correspondences = o3d.utility.Vector2iVector(np.column_stack([source_idx, target_idx]))
    estimator = o3d.pipelines.registration.TransformationEstimationPointToPoint(allow_scaling)
    return estimator.compute_transformation(source, target, correspondences)


# ---------------------------------------------------------------------------
# 2c. Axis-sweep seeding (for elongated, axially-symmetric objects)
# ---------------------------------------------------------------------------

def compute_principal_axis(points: np.ndarray) -> tuple[np.ndarray, np.ndarray, float]:
    """Centroid, unit principal axis (direction of greatest variance), and
    the point spread along that axis (1st-99th percentile, robust to a few
    outlier points) - purely a shape property, so it works the same
    regardless of which pipeline (or LiDAR) produced the cloud."""
    centroid = points.mean(axis=0)
    centered = points - centroid
    cov = np.cov(centered.T)
    eigvals, eigvecs = np.linalg.eigh(cov)  # ascending order
    axis = eigvecs[:, -1]
    axis = axis / np.linalg.norm(axis)
    projections = centered @ axis
    extent = float(np.percentile(projections, 99) - np.percentile(projections, 1))
    return centroid, axis, extent


def rotation_between_vectors(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Shortest-arc rotation matrix mapping unit vector a onto unit vector b."""
    a = a / np.linalg.norm(a)
    b = b / np.linalg.norm(b)
    cross = np.cross(a, b)
    cos_angle = np.dot(a, b)
    if np.linalg.norm(cross) < 1e-8:
        if cos_angle > 0:
            return np.eye(3)
        # antiparallel: 180 degrees about any axis perpendicular to a
        perp = np.array([1.0, 0.0, 0.0]) if abs(a[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
        perp = perp - a * np.dot(perp, a)
        perp = perp / np.linalg.norm(perp)
        return o3d.geometry.get_rotation_matrix_from_axis_angle(perp * np.pi)
    axis = cross / np.linalg.norm(cross)
    angle = np.arctan2(np.linalg.norm(cross), cos_angle)
    return o3d.geometry.get_rotation_matrix_from_axis_angle(axis * angle)


def axis_sweep_registration(
    source: o3d.geometry.PointCloud, target: o3d.geometry.PointCloud,
    voxel_size: float, allow_scaling: bool, angle_step_deg: float = 10.0,
) -> tuple[np.ndarray, float]:
    source_points = np.asarray(source.points)
    target_points = np.asarray(target.points)
    source_centroid, source_axis, source_extent = compute_principal_axis(source_points)
    target_centroid, target_axis, target_extent = compute_principal_axis(target_points)
    scale = (target_extent / source_extent) if allow_scaling else 1.0

    source_down = source.voxel_down_sample(voxel_size)
    target_down = target.voxel_down_sample(voxel_size)

    def score(transform: np.ndarray) -> float:
        candidate = copy.deepcopy(source_down)
        candidate.transform(transform)
        distances = np.asarray(candidate.compute_point_cloud_distance(target_down))
        return float(np.median(distances))

    best_transform, best_score = None, np.inf
    angles = np.deg2rad(np.arange(0, 360, angle_step_deg))
    for axis_sign in (1.0, -1.0):
        r_align = rotation_between_vectors(source_axis * axis_sign, target_axis)
        for angle in angles:
            r_twist = o3d.geometry.get_rotation_matrix_from_axis_angle(target_axis * angle)
            rotation = r_twist @ r_align
            transform = np.eye(4)
            transform[:3, :3] = scale * rotation
            transform[:3, 3] = target_centroid - scale * rotation @ source_centroid
            candidate_score = score(transform)
            if candidate_score < best_score:
                best_score, best_transform = candidate_score, transform

    return best_transform, best_score


# ---------------------------------------------------------------------------
# 3. Local refinement (fine alignment, via point-to-plane ICP)
# ---------------------------------------------------------------------------

def refine_registration(source, target, voxel_size, initial_transform, allow_scaling):
    distance_threshold = voxel_size * 0.4
    source.estimate_normals(o3d.geometry.KDTreeSearchParamHybrid(radius=voxel_size * 2, max_nn=30))
    target.estimate_normals(o3d.geometry.KDTreeSearchParamHybrid(radius=voxel_size * 2, max_nn=30))

    transform = initial_transform
    if allow_scaling:
        # Point-to-plane ICP (below) doesn't support scale estimation in Open3D
        # at all, so whatever scale the coarse stage guessed (axis-sweep's
        # rough extent-ratio estimate, or FPFH/RANSAC's) would otherwise never
        # get corrected. Refine scale (+ rotation/translation) first with a
        # scale-enabled point-to-point pass; point-to-plane afterwards keeps
        # that scale as-is (it only refines rotation/translation) while giving
        # a more precise final fit.
        scale_result = o3d.pipelines.registration.registration_icp(
            source, target, distance_threshold, transform,
            o3d.pipelines.registration.TransformationEstimationPointToPoint(True),
        )
        transform = scale_result.transformation

    # Coarse-to-fine point-to-plane passes instead of a single shot at
    # distance_threshold: Open3D's default max_iteration (30) with one fixed
    # threshold often stops short of a tight fit on elongated objects, since
    # the dominant cylindrical body supplies most correspondences and a
    # smaller distinctive feature at one end (e.g. a bollard's cap) gets
    # under-weighted - visually confirmed as a poorly-seated cap despite a
    # reasonable overall fitness. Each pass starts from the previous one's
    # result and tightens the threshold, letting the fit progressively lock
    # onto finer detail instead of settling for the first coarse optimum.
    # (Tried adding a TukeyLoss robust kernel here too - made no measurable
    # difference either way, so left out to keep this simple.)
    result = None
    for threshold_multiplier in (4.0, 2.0, 1.0, 0.4):
        result = o3d.pipelines.registration.registration_icp(
            source, target, voxel_size * threshold_multiplier, transform,
            o3d.pipelines.registration.TransformationEstimationPointToPlane(),
            o3d.pipelines.registration.ICPConvergenceCriteria(max_iteration=100),
        )
        transform = result.transformation
    return result


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
    parser.add_argument(
        "--manual", action="store_true",
        help="pick >=3 corresponding points by hand for the initial alignment instead of FPFH+RANSAC "
        "(use for symmetric objects, e.g. bollards, where automatic matching can't tell rotations apart)",
    )
    parser.add_argument(
        "--axis-sweep", action="store_true",
        help="force PCA + rotational-sweep seeding (see module docstring) instead of FPFH+RANSAC; "
        "normally only used as an automatic fallback when FPFH+RANSAC fitness is low",
    )
    parser.add_argument(
        "--fallback-fitness-threshold", type=float, default=0.3,
        help="if plain FPFH+RANSAC fitness is below this, automatically retry with axis-sweep (default: 0.3)",
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

    allow_scaling = not args.rigid
    global_result = None
    initial_alignment = None
    if args.manual:
        print("Manual seeding: pick >=3 corresponding points on each cloud, in the same order.")
        initial_transform = manual_initial_transform(source, target, allow_scaling)
        print(f"Manual seed: scale~{extract_scale(initial_transform):.4f}")
        initial_alignment = "manual"
    elif args.axis_sweep:
        print("Axis-sweep seeding: PCA principal axis + brute-force rotation sweep...")
        initial_transform, sweep_score = axis_sweep_registration(source, target, voxel_size, allow_scaling)
        print(f"Axis-sweep: median distance={sweep_score:.4f}, scale~{extract_scale(initial_transform):.4f}")
        initial_alignment = "axis_sweep"
    else:
        source_down, source_fpfh = preprocess(source, voxel_size)
        target_down, target_fpfh = preprocess(target, voxel_size)
        print(f"Downsampled: source {len(source_down.points)}, target {len(target_down.points)}")

        print(f"Running global registration (RANSAC + FPFH, scaling={allow_scaling})...")
        global_result = global_registration(source_down, target_down, source_fpfh, target_fpfh, voxel_size, allow_scaling)
        print(
            f"Global: fitness={global_result.fitness:.4f}, inlier_rmse={global_result.inlier_rmse:.4f}, "
            f"scale~{extract_scale(global_result.transformation):.4f}"
        )
        if global_result.fitness < args.fallback_fitness_threshold:
            print(
                f"Fitness {global_result.fitness:.4f} < {args.fallback_fitness_threshold} - looks like the "
                "symmetric-object failure mode (FPFH+RANSAC has no signal to pick the right rotation). "
                "Falling back to axis-sweep seeding..."
            )
            initial_transform, sweep_score = axis_sweep_registration(source, target, voxel_size, allow_scaling)
            print(f"Axis-sweep: median distance={sweep_score:.4f}, scale~{extract_scale(initial_transform):.4f}")
            initial_alignment = "fpfh_ransac_then_axis_sweep_fallback"
        else:
            initial_transform = global_result.transformation
            initial_alignment = "fpfh_ransac"

    print("Refining with ICP (point-to-plane)...")
    icp_result = refine_registration(source, target, voxel_size, initial_transform, allow_scaling)
    print(f"ICP: fitness={icp_result.fitness:.4f}, inlier_rmse={icp_result.inlier_rmse:.4f}")

    transform = icp_result.transformation
    aligned_source = copy.deepcopy(source)
    aligned_source.transform(transform)

    aligned_path = output_dir / f"{source_path.stem}_aligned_to_{target_path.stem}.ply"
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
        "initial_alignment": initial_alignment,
        "estimated_scale": extract_scale(transform),
        "global_registration": (
            {"fitness": global_result.fitness, "inlier_rmse": global_result.inlier_rmse}
            if global_result is not None else None
        ),
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
