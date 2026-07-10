"""Remove sparse "flying" noise from a point cloud via statistical or radius
outlier removal - run this BEFORE remove_ground_plane.py.

Why this matters: feed-forward/depth-based methods (VGGT especially, but
also MASt3R's global alignment) predict a 3D point for every pixel, even
low-confidence ones. Wrong-depth pixels don't land on the object or the
floor - they scatter into a sparse trail hanging below (or around) the real
surfaces, visibly disconnected from the dense, coherent parts of the cloud.
remove_ground_plane.py's RANSAC only targets the single largest flat
surface, so it leaves this scattered noise untouched; DBSCAN clustering
(--keep-largest-cluster there) can remove it too, but is O(n) memory-hungry
enough to OOM on VGGT's very dense clouds (millions of points) on a laptop.
Statistical/radius outlier removal is the standard, far cheaper alternative
for exactly this "flying pixels" pattern: real surfaces are locally dense
(each point has many close neighbors), while the trailing noise is locally
sparse (each point sits mostly alone) - no global clustering pass needed,
just a per-point neighbor check.

Two methods (see Open3D's point cloud outlier removal tutorial):
    - statistical (default): flags a point as noise if its average distance
      to its nb_neighbors nearest neighbors is more than std_ratio standard
      deviations above the cloud-wide mean. Adapts to the cloud's own
      density, so it works across very different point counts/scales
      without retuning.
    - radius: flags a point as noise if it has fewer than nb_points
      neighbors within a fixed radius. More predictable/literal ("is there
      anything within X meters of me"), but the radius must be chosen
      relative to the cloud's scale (hence --radius-fraction, like
      remove_ground_plane.py's --distance-threshold-fraction).

Usage:
    python src/registration/remove_noise.py \\
        outputs/crops/exp_019_vggt_chair_001_video2_cropped.ply \\
        outputs/crops/exp_019_vggt_chair_001_video2_denoised.ply

    python src/registration/remove_noise.py \\
        outputs/crops/exp_019_vggt_chair_001_video2_cropped.ply \\
        outputs/crops/exp_019_vggt_chair_001_video2_denoised.ply \\
        --method radius --radius-fraction 0.003 --nb-points 8
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


def remove_noise(
    pcd: o3d.geometry.PointCloud, method: str,
    nb_neighbors: int, std_ratio: float,
    nb_points: int, radius: float,
) -> tuple[o3d.geometry.PointCloud, o3d.geometry.PointCloud]:
    if method == "statistical":
        clean, inlier_indices = pcd.remove_statistical_outlier(nb_neighbors=nb_neighbors, std_ratio=std_ratio)
    else:
        clean, inlier_indices = pcd.remove_radius_outlier(nb_points=nb_points, radius=radius)
    noise = pcd.select_by_index(inlier_indices, invert=True)
    return clean, noise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("input", help="point cloud to clean (.ply)")
    parser.add_argument("output", help="where to save the denoised cloud")
    parser.add_argument("--method", choices=["statistical", "radius"], default="statistical")
    parser.add_argument(
        "--nb-neighbors", type=int, default=20,
        help="(statistical) how many nearest neighbors to average the distance over (default: 20)",
    )
    parser.add_argument(
        "--std-ratio", type=float, default=2.0,
        help="(statistical) flag points whose average neighbor distance is more than this many standard "
        "deviations above the cloud-wide mean (default: 2.0 - lower removes more aggressively)",
    )
    parser.add_argument(
        "--nb-points", type=int, default=8,
        help="(radius) minimum number of neighbors required within --radius-fraction to keep a point (default: 8)",
    )
    parser.add_argument(
        "--radius-fraction", type=float, default=0.003,
        help="(radius) neighbor search radius as a fraction of the cloud's bbox diagonal (default: 0.003)",
    )
    args = parser.parse_args()

    input_path = resolve_path(args.input)
    output_path = resolve_path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    pcd = o3d.io.read_point_cloud(str(input_path))
    total_points = len(pcd.points)
    print(f"Loaded {total_points} points from {input_path}")

    diagonal = float(np.linalg.norm(pcd.get_axis_aligned_bounding_box().get_extent()))
    radius = diagonal * args.radius_fraction

    clean, noise = remove_noise(
        pcd, args.method, args.nb_neighbors, args.std_ratio, args.nb_points, radius,
    )
    removed_fraction = len(noise.points) / total_points
    print(
        f"Removed {len(noise.points)} points ({removed_fraction:.1%} of the original cloud) as noise, "
        f"{len(clean.points)} remain"
    )
    if removed_fraction > 0.3:
        print(
            f"WARNING: removed more than 30% of the cloud. Check {output_path.stem}_removed_noise.ply - this "
            "may be too aggressive (e.g. legitimately sparse but real detail getting flagged as noise)."
        )

    noise_path = output_path.parent / f"{output_path.stem}_removed_noise.ply"
    o3d.io.write_point_cloud(str(noise_path), noise)
    print(f"Saved removed points -> {noise_path} (inspect to confirm it's really noise, not real detail)")

    o3d.io.write_point_cloud(str(output_path), clean)
    print(f"Saved -> {output_path}")


if __name__ == "__main__":
    main()
