"""Open an interactive window to inspect and compare one or more point clouds.

Each cloud gets its own row with a checkbox in the settings panel on the
right (under "Geometries") - toggle clouds on/off individually to see how
well a registration lined them up. Mouse controls: left-drag to rotate,
right-drag (or ctrl+drag) to pan, scroll to zoom, 'r' to reset the view.

Pass multiple files to overlay them (e.g. target + aligned source from a
registration run) - use --recolor to flat-color each one so you can tell
them apart regardless of their original vertex colors.

Usage:
    python src/registration/visualize_point_clouds.py outputs/exp_003_colmap_bollard_001/exp_003_colmap_bollard_001.ply

    python src/registration/visualize_point_clouds.py \\
        outputs/exp_003_colmap_bollard_001/exp_003_colmap_bollard_001.ply \\
        outputs/reg_004_to_003_bollard_001/aligned_source.ply \\
        --recolor
"""

from __future__ import annotations

import argparse
from pathlib import Path

import open3d as o3d

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# one flat color per cloud, in order, when --recolor is set (or a cloud has no vertex colors)
DISTINCT_COLORS = [
    (0.85, 0.1, 0.1),   # red
    (0.1, 0.65, 0.15),  # green
    (0.1, 0.4, 0.9),    # blue
    (0.9, 0.65, 0.0),   # orange
]


def resolve_path(path_str: str) -> Path:
    path = Path(path_str)
    return path if path.is_absolute() else (PROJECT_ROOT / path).resolve()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("paths", nargs="+", help="one or more .ply/.pcd files to show together")
    parser.add_argument(
        "--recolor", action="store_true",
        help="flat-color each cloud (useful to tell overlaid clouds apart, e.g. before/after registration)",
    )
    parser.add_argument("--point-size", type=int, default=2)
    args = parser.parse_args()

    named_geometries = []
    for i, path_str in enumerate(args.paths):
        path = resolve_path(path_str)
        pcd = o3d.io.read_point_cloud(str(path))
        print(f"{path.name}: {len(pcd.points)} points, colors={'yes' if pcd.has_colors() else 'no'}")
        if args.recolor or not pcd.has_colors():
            pcd.paint_uniform_color(DISTINCT_COLORS[i % len(DISTINCT_COLORS)])
        named_geometries.append({"name": path.name, "geometry": pcd, "is_visible": True})

    o3d.visualization.draw(
        named_geometries,
        title=" + ".join(g["name"] for g in named_geometries),
        width=1280,
        height=800,
        show_ui=True,
        point_size=args.point_size,
    )


if __name__ == "__main__":
    main()
