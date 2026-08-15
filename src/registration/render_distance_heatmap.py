"""Render cloud-to-cloud distance (Accuracy / Completeness, same definitions as
evaluate_registration.py) as a per-point color heatmap, so it's visible WHERE
the error is concentrated, not just the summary mean/median/rmse a table gives.

Accuracy (source -> target): colors the density-matched reconstruction by its
distance to the nearest LiDAR point - highlights where the reconstruction
itself deviates from the real surface (e.g. a warped panel, a drifted post).

Completeness (target -> source): colors the LiDAR reference by its distance to
the nearest reconstructed point - highlights holes/missing coverage in the
reconstruction (a LiDAR point far from any reconstructed point means nothing
was reconstructed there), not surface error.

Usage:
    python src/registration/render_distance_heatmap.py \\
        --source outputs/density_matched/bus_stop_001/exp_055_mast3r_ga_bus_stop_001_coarse_aligned_to_bus_stop_001_no_floor_centered_density_matched.ply \\
        --target data/lidar/bus_stop_001/bus_stop_001_no_floor_centered_downsampled.ply \\
        --output-dir outputs/renders/heatmap_055 --label "exp_055 mast3r_ga"
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib
import numpy as np
import open3d as o3d
from matplotlib import cm
from PIL import Image, ImageDraw, ImageFont

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def resolve_path(path_str: str) -> Path:
    path = Path(path_str)
    return path if path.is_absolute() else (PROJECT_ROOT / path).resolve()


def display_path(path: Path) -> str:
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def colorize(distances: np.ndarray, vmax: float) -> np.ndarray:
    norm = np.clip(distances / vmax, 0.0, 1.0)
    return matplotlib.colormaps["turbo"](norm)[:, :3]


def render_single_view(
    pcd: o3d.geometry.PointCloud, width: int, height: int, point_size: float,
    azimuth_deg: float, elevation_deg: float, zoom: float,
) -> np.ndarray:
    vis = o3d.visualization.Visualizer()
    vis.create_window(visible=False, width=width, height=height)
    vis.add_geometry(pcd)
    opt = vis.get_render_option()
    opt.point_size = point_size
    opt.background_color = np.array([0.06, 0.09, 0.16])

    elevation = np.radians(elevation_deg)
    azimuth = np.radians(azimuth_deg)
    x = np.cos(elevation) * np.cos(azimuth)
    y = np.cos(elevation) * np.sin(azimuth)
    z = np.sin(elevation)
    direction = np.array([-x, -y, -z])
    up = np.array([0.0, 0.0, 1.0]) if abs(direction[2]) < 0.99 else np.array([0.0, 1.0, 0.0])

    bbox = pcd.get_axis_aligned_bounding_box()
    ctr = vis.get_view_control()
    ctr.set_lookat(bbox.get_center())
    ctr.set_front((-direction).tolist())
    ctr.set_up(up.tolist())
    ctr.set_zoom(zoom)
    vis.poll_events()
    vis.update_renderer()

    buf = vis.capture_screen_float_buffer(do_render=True)
    vis.destroy_window()
    return (np.asarray(buf) * 255).astype(np.uint8)


def compose_with_legend(
    render_rgb: np.ndarray, vmax: float, title: str, stats: dict,
) -> Image.Image:
    h, w, _ = render_rgb.shape
    legend_w = 260
    canvas = Image.new("RGB", (w + legend_w, h), (15, 18, 28))
    canvas.paste(Image.fromarray(render_rgb), (0, 0))
    draw = ImageDraw.Draw(canvas)

    try:
        font_bold = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 15)
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 13)
    except OSError:
        font_bold = font = ImageFont.load_default()

    draw.text((10, 8), title, fill=(230, 230, 230), font=font_bold)

    bar_x, bar_y, bar_w, bar_h = w + 30, 60, 26, h - 180
    n_steps = 200
    cmap = matplotlib.colormaps["turbo"]
    for i in range(n_steps):
        frac = 1.0 - i / (n_steps - 1)  # top = max distance
        color = tuple(int(c * 255) for c in cmap(frac)[:3])
        y0 = bar_y + int(i / n_steps * bar_h)
        y1 = bar_y + int((i + 1) / n_steps * bar_h)
        draw.rectangle([bar_x, y0, bar_x + bar_w, y1], fill=color)
    draw.rectangle([bar_x, bar_y, bar_x + bar_w, bar_y + bar_h], outline=(200, 200, 200))

    draw.text((bar_x + bar_w + 8, bar_y - 6), f"{vmax * 100:.0f} cm", fill=(230, 230, 230), font=font)
    draw.text((bar_x + bar_w + 8, bar_y + bar_h - 8), "0 cm", fill=(230, 230, 230), font=font)
    draw.text((bar_x + bar_w + 8, bar_y + bar_h // 2 - 8), f"{vmax * 50:.0f} cm", fill=(180, 180, 180), font=font)

    text_y = bar_y + bar_h + 20
    lines = [
        f"mean:   {stats['mean'] * 100:.2f} cm",
        f"median: {stats['median'] * 100:.2f} cm",
        f"rmse:   {stats['rmse'] * 100:.2f} cm",
        f"p95:    {stats['p95'] * 100:.2f} cm",
        f"max:    {stats['max'] * 100:.2f} cm",
    ]
    for i, line in enumerate(lines):
        draw.text((w + 20, text_y + i * 18), line, fill=(210, 210, 210), font=font)

    return canvas


def distance_stats(distances: np.ndarray) -> dict:
    return {
        "mean": float(distances.mean()),
        "median": float(np.median(distances)),
        "rmse": float(np.sqrt(np.mean(distances**2))),
        "p95": float(np.percentile(distances, 95)),
        "max": float(distances.max()),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", required=True, help="density-matched aligned reconstruction .ply")
    parser.add_argument("--target", required=True, help="LiDAR reference .ply")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--label", required=True, help="short label used in image titles, e.g. 'exp_055 mast3r_ga'")
    parser.add_argument("--vmax", type=float, default=0.15, help="distance (m) mapped to the top of the color scale, clipped above (default: 0.15)")
    parser.add_argument("--point-size", type=float, default=2.5)
    parser.add_argument("--azimuth", type=float, default=40.0)
    parser.add_argument("--elevation", type=float, default=20.0)
    parser.add_argument("--zoom", type=float, default=0.7)
    parser.add_argument("--width", type=int, default=800)
    parser.add_argument("--height", type=int, default=600)
    args = parser.parse_args()

    source_path = resolve_path(args.source)
    target_path = resolve_path(args.target)
    output_dir = resolve_path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Loading source: {display_path(source_path)}")
    source = o3d.io.read_point_cloud(str(source_path))
    print(f"Loading target: {display_path(target_path)}")
    target = o3d.io.read_point_cloud(str(target_path))
    print(f"Source points: {len(source.points)}, target points: {len(target.points)}")

    accuracy_dist = np.asarray(source.compute_point_cloud_distance(target))
    completeness_dist = np.asarray(target.compute_point_cloud_distance(source))

    accuracy_colored = o3d.geometry.PointCloud(source)
    accuracy_colored.colors = o3d.utility.Vector3dVector(colorize(accuracy_dist, args.vmax))

    completeness_colored = o3d.geometry.PointCloud(target)
    completeness_colored.colors = o3d.utility.Vector3dVector(colorize(completeness_dist, args.vmax))

    for name, pcd, dist in [
        ("accuracy", accuracy_colored, accuracy_dist),
        ("completeness", completeness_colored, completeness_dist),
    ]:
        stats = distance_stats(dist)
        print(f"\n{name} (n={len(dist)}): mean={stats['mean']*100:.2f}cm median={stats['median']*100:.2f}cm "
              f"rmse={stats['rmse']*100:.2f}cm p95={stats['p95']*100:.2f}cm max={stats['max']*100:.2f}cm")

        render = render_single_view(pcd, args.width, args.height, args.point_size, args.azimuth, args.elevation, args.zoom)
        title = f"{args.label} - {name}" + (" (source -> LiDAR)" if name == "accuracy" else " (LiDAR -> source)")
        image = compose_with_legend(render, args.vmax, title, stats)

        out_path = output_dir / f"{name}.png"
        image.save(out_path)
        print(f"Saved -> {display_path(out_path)}")


if __name__ == "__main__":
    main()
