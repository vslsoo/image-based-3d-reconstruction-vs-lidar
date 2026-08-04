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
    # Downsample source once for correspondence search. The raw photogrammetry
    # cloud (COLMAP/MASt3R dense output) commonly runs 1-2M points, while the
    # LiDAR target here is already sparse (~10k points) and doesn't need
    # thinning. Every closest-point query in every ICP iteration below scans
    # source's point count, so this is the single biggest cost in this
    # function - and cutting it down doesn't hurt fit quality, since what a
    # tight threshold cares about is how close each *individual* point is to
    # the target surface, not how densely packed its neighbors in source are.
    source_down = source.voxel_down_sample(voxel_size)
    source_down.estimate_normals(o3d.geometry.KDTreeSearchParamHybrid(radius=voxel_size * 2, max_nn=30))
    target.estimate_normals(o3d.geometry.KDTreeSearchParamHybrid(radius=voxel_size * 2, max_nn=30))

    # The scale sub-step below (point-to-point-with-scale) weighs every
    # matched pair equally, so an unevenly-dense target - e.g. a LiDAR scan
    # whose return density spikes near one solid feature (a backrest, a cap)
    # relative to the rest of an elongated object - lets that dense patch
    # dominate the fitted scale instead of the object's true end-to-end size.
    # Matching the scale sub-step against a target voxel-downsampled more
    # coarsely than the rest of the pipeline (SCALE_TARGET_VOXEL_MULTIPLIER x
    # voxel_size - roughly one point per surface patch, regardless of how
    # many raw LiDAR returns landed there) keeps that estimate representative
    # of the whole object rather than its densest patch. The point-to-plane
    # pass below is unaffected and still matches against the full-resolution
    # target. Note: on the one dataset this was checked against (a bench,
    # COLMAP reconstruction), this made the aggregate point-distance metrics
    # very slightly worse than leaving the scale sub-step on the fine target
    # (mean/median/rmse/p95 all within ~1% of the unmodified version) - the
    # change is kept anyway because a visual check judged its result the more
    # correct fit; if that visual read doesn't hold up on other objects,
    # SCALE_TARGET_VOXEL_MULTIPLIER = 1.0 restores the original behavior.
    SCALE_TARGET_VOXEL_MULTIPLIER = 3.0
    scale_target = target.voxel_down_sample(voxel_size * SCALE_TARGET_VOXEL_MULTIPLIER)

    # Coarse-to-fine, and - when scale is unknown - scale and point-to-plane
    # passes are INTERLEAVED at each threshold rather than run as two
    # separate blocks (scale-refine-to-completion, then all point-to-plane).
    # Running all scale passes first locks the scale in based on a still-
    # coarse rotation/translation; point-to-plane afterwards can straighten
    # out the pose but (by construction) never touches scale again, so any
    # scale error from that early, cruder estimate survives to the final
    # result. On an elongated object this shows up as error growing with
    # distance from the pivot - e.g. a 4m bench visibly gapping by several
    # cm at the far end from the LiDAR reference while the center matches
    # almost exactly (diagnosed by binning point-to-target distance along
    # the object's own principal axis). Alternating the two lets each
    # tighten using the OTHER's latest result, so scale keeps improving
    # alongside pose instead of freezing early.
    #
    # Single fixed-threshold ICP (the naive one-shot approach) also
    # under-fits elongated objects for a related reason: Open3D's default
    # max_iteration (30) with one threshold lets the dominant central mass
    # dictate the fit while a smaller distinctive feature at one end (e.g. a
    # bollard's cap) is under-weighted - visually confirmed as a poorly-
    # seated cap despite reasonable overall fitness. Each pass here starts
    # from the previous one's result and tightens the threshold, letting the
    # fit progressively lock onto finer detail instead of settling for the
    # first coarse optimum. (Tried adding a TukeyLoss robust kernel too -
    # made no measurable difference either way, so left out to keep this
    # simple.)
    transform = initial_transform
    result = None
    for threshold_multiplier in (4.0, 2.0, 1.0, 0.4, 0.2):
        if allow_scaling:
            scale_result = o3d.pipelines.registration.registration_icp(
                source_down, scale_target, voxel_size * threshold_multiplier * SCALE_TARGET_VOXEL_MULTIPLIER, transform,
                o3d.pipelines.registration.TransformationEstimationPointToPoint(True),
            )
            transform = scale_result.transformation
        result = o3d.pipelines.registration.registration_icp(
            source_down, target, voxel_size * threshold_multiplier, transform,
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
    parser.add_argument(
        "--scale-sanity-factor", type=float, default=2.0,
        help="if FPFH+RANSAC's fitted scale is off by more than this factor from a naive, correspondence-"
        "free bbox-diagonal-ratio estimate, automatically retry with axis-sweep even if fitness looked "
        "fine (default: 2.0) - catches self-similar-structure mismatches (e.g. matching a bench's whole "
        "body to just its seat) that RANSAC can report as a confident, high-fitness fit anyway",
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
        fitted_scale = extract_scale(global_result.transformation)
        low_fitness = global_result.fitness < args.fallback_fitness_threshold

        # Fitness alone doesn't catch every bad fit: with scale unconstrained,
        # RANSAC can match the whole source to a self-similar sub-part of the
        # target (e.g. a bench's whole body onto just its seat, via repeated
        # legs/slats supplying enough locally-consistent correspondences) and
        # report a confidently high fitness while the scale is off by several
        # times. A naive, correspondence-free bbox-diagonal ratio has no such
        # failure mode - it's just the two clouds' overall extents - so a
        # large disagreement between it and RANSAC's fitted scale is itself
        # evidence something matched wrong.
        naive_scale = None
        scale_ratio = None
        scale_mismatch = False
        if allow_scaling:
            naive_scale = bbox_diagonal(target) / bbox_diagonal(source)
            scale_ratio = max(fitted_scale, naive_scale) / min(fitted_scale, naive_scale)
            scale_mismatch = scale_ratio > args.scale_sanity_factor

        if low_fitness or scale_mismatch:
            if scale_mismatch and not low_fitness:
                print(
                    f"Fitted scale {fitted_scale:.4f} is {scale_ratio:.1f}x off from the naive bbox-diagonal "
                    f"scale estimate ({naive_scale:.4f}, > {args.scale_sanity_factor}x threshold) despite "
                    f"fitness={global_result.fitness:.4f} - FPFH+RANSAC likely matched a self-similar "
                    "sub-part of the object rather than the whole thing (same failure class as rotational "
                    "symmetry, just via repeated structure like legs/slats instead of a round profile). "
                    "Falling back to axis-sweep seeding..."
                )
            else:
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
    # Full-res aligned_source is still what gets written to disk above; the
    # accuracy metric itself only needs a representative sample of it, and a
    # uniform voxel downsample also avoids biasing mean/median error toward
    # whichever surface patch source happens to be densest at.
    aligned_source_down = aligned_source.voxel_down_sample(voxel_size)
    distance_stats = point_cloud_distance_stats(aligned_source_down, target)
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
            {
                "fitness": global_result.fitness,
                "inlier_rmse": global_result.inlier_rmse,
                "fitted_scale": fitted_scale,
                "naive_bbox_scale_estimate": naive_scale,
                "scale_ratio_vs_naive": scale_ratio,
            }
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
