"""Render a point cloud to PNG images from several fixed viewpoints, headless
(no window shown) - lets Claude inspect a cleanup step's result directly
(via its image-reading tool) instead of a human screenshotting CloudCompare
each time.

Since these are raw, pre-registration reconstructions with no defined
"up" axis, there's no principled front/top/side - instead this orbits the
cloud's own centroid at a few azimuth angles (default 6, 60 degrees apart)
plus one straight-down view, which is enough to catch what visual QC here
actually cares about: floating debris disconnected from the main object,
or a flat slab (floor) still attached to one side.

Usage:
    python src/registration/render_point_cloud.py \\
        outputs/crops/exp_034_vggt_bollard_002_no_floor.ply \\
        --output-dir outputs/renders/exp_034_vggt_bollard_002_no_floor

    python src/registration/render_point_cloud.py \\
        outputs/crops/exp_034_vggt_bollard_002_no_floor.ply \\
        outputs/crops/exp_034_vggt_bollard_002_no_floor_removed_plane_1.ply \\
        --recolor --output-dir outputs/renders/exp_034_check
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import open3d as o3d

PROJECT_ROOT = Path(__file__).resolve().parents[2]

DISTINCT_COLORS = [
    (0.85, 0.1, 0.1),   # red
    (0.1, 0.65, 0.15),  # green
    (0.1, 0.4, 0.9),    # blue
    (0.9, 0.65, 0.0),   # orange
]


def resolve_path(path_str: str) -> Path:
    path = Path(path_str)
    return path if path.is_absolute() else (PROJECT_ROOT / path).resolve()


def display_path(path: Path) -> str:
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def orbit_directions(n_azimuth: int, elevation_deg: float) -> list[tuple[str, np.ndarray]]:
    """Unit view directions (camera -> object, i.e. what set_front expects)
    orbiting around the world Z axis at a fixed elevation, plus a straight
    top-down view."""
    elevation = np.radians(elevation_deg)
    directions = []
    for i in range(n_azimuth):
        azimuth = np.radians(360.0 * i / n_azimuth)
        x = np.cos(elevation) * np.cos(azimuth)
        y = np.cos(elevation) * np.sin(azimuth)
        z = np.sin(elevation)
        directions.append((f"az{int(np.degrees(azimuth)):03d}", np.array([-x, -y, -z])))
    directions.append(("top", np.array([0.0, 0.0, -1.0])))
    return directions


def render_views(
    geometries: list[o3d.geometry.PointCloud], output_dir: Path, point_size: float,
    n_azimuth: int, elevation_deg: float, width: int, height: int, zoom: float,
    focus_top_fraction: float | None,
) -> list[Path]:
    vis = o3d.visualization.Visualizer()
    vis.create_window(visible=False, width=width, height=height)
    for geom in geometries:
        vis.add_geometry(geom)

    opt = vis.get_render_option()
    opt.point_size = point_size
    opt.background_color = np.array([0.06, 0.09, 0.16])  # matches the dark blue CloudCompare screenshots

    combined = geometries[0]
    for g in geometries[1:]:
        combined = combined + g
    bbox = combined.get_axis_aligned_bounding_box()
    center = bbox.get_center()

    if focus_top_fraction is not None:
        # Re-center on just the top slice of the cloud's own longest axis
        # (where flying-pixel "streaks" off a rounded cap tend to sit) and
        # zoom in tighter - the default whole-object view is too zoomed out
        # to reliably spot thin sparse trails against the object silhouette.
        pts = np.asarray(combined.points)
        extent = bbox.get_extent()
        long_axis = int(np.argmax(extent))
        axis_min = bbox.get_min_bound()[long_axis]
        axis_max = bbox.get_max_bound()[long_axis]
        threshold = axis_max - focus_top_fraction * (axis_max - axis_min)
        top_mask = pts[:, long_axis] >= threshold
        if top_mask.sum() > 0:
            center = pts[top_mask].mean(axis=0)
        zoom = min(zoom, 0.35)

    ctr = vis.get_view_control()
    saved = []
    output_dir.mkdir(parents=True, exist_ok=True)
    for name, direction in orbit_directions(n_azimuth, elevation_deg):
        up = np.array([0.0, 0.0, 1.0]) if abs(direction[2]) < 0.99 else np.array([0.0, 1.0, 0.0])
        ctr.set_lookat(center)
        ctr.set_front((-direction).tolist())
        ctr.set_up(up.tolist())
        ctr.set_zoom(zoom)
        vis.poll_events()
        vis.update_renderer()
        out_path = output_dir / f"{name}.png"
        vis.capture_screen_image(str(out_path), do_render=True)
        saved.append(out_path)

    vis.destroy_window()
    return saved


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("paths", nargs="+", help="one or more .ply/.pcd files to render together")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--recolor", action="store_true", help="flat-color each cloud (useful with multiple inputs, e.g. kept vs removed points)")
    parser.add_argument("--point-size", type=float, default=2.0)
    parser.add_argument("--n-azimuth", type=int, default=6, help="number of orbit views around Z (default: 6, i.e. every 60 degrees)")
    parser.add_argument("--elevation", type=float, default=20.0, help="camera elevation angle in degrees (default: 20)")
    parser.add_argument("--width", type=int, default=800)
    parser.add_argument("--height", type=int, default=600)
    parser.add_argument("--zoom", type=float, default=0.7, help="Open3D zoom level, smaller = closer (default: 0.7)")
    parser.add_argument(
        "--focus-top-fraction", type=float, default=None,
        help="instead of framing the whole cloud, re-center on just the top slice (this fraction of the "
        "cloud's longest-axis extent, e.g. 0.15) and zoom in tighter - use this to check for flying-pixel "
        "noise trails around a rounded cap/silhouette edge that a whole-object view is too zoomed out to see",
    )
    args = parser.parse_args()

    output_dir = resolve_path(args.output_dir)
    geometries = []
    for i, path_str in enumerate(args.paths):
        path = resolve_path(path_str)
        pcd = o3d.io.read_point_cloud(str(path))
        print(f"{display_path(path)}: {len(pcd.points)} points")
        if args.recolor or not pcd.has_colors():
            pcd.paint_uniform_color(DISTINCT_COLORS[i % len(DISTINCT_COLORS)])
        geometries.append(pcd)

    saved = render_views(
        geometries, output_dir, args.point_size, args.n_azimuth, args.elevation, args.width, args.height,
        args.zoom, args.focus_top_fraction,
    )
    print(f"Saved {len(saved)} renders -> {display_path(output_dir)}/")
    for p in saved:
        print(f"  {p.name}")


if __name__ == "__main__":
    main()
