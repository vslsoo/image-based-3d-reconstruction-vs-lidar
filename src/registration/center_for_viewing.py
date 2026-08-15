"""Translate a LiDAR reference cloud and one or more experiment clouds so
they all share the same centroid (moved to a small local origin) - purely so
they open up co-located in a viewer like CloudCompare. This is translation
ONLY: no rotation or scale correction, unlike register_point_clouds.py. Use
it when clouds are currently absurdly far apart for a trivial reason (the
LiDAR crop is still in Sensat-Euston's absolute UTM-scale coordinates, while
a photogrammetry experiment cloud is in its own arbitrary near-origin units)
and you just want to eyeball them together, not measure alignment accuracy.

Usage:
    python src/registration/center_for_viewing.py \\
        --target data/lidar/bus_stop_001/bus_stop_001_no_floor.ply \\
        --sources outputs/no_floor/exp_055_mast3r_ga_bus_stop_001_no_floor.ply \\
                  outputs/no_floor/exp_056_vggt_bus_stop_001_no_floor.ply
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


def display_path(path: Path) -> str:
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def center_on_own_centroid(path: Path) -> Path:
    pcd = o3d.io.read_point_cloud(str(path))
    points = np.asarray(pcd.points)
    centroid = points.mean(axis=0)
    pcd.translate(-centroid)
    out_path = path.parent / f"{path.stem}_centered.ply"
    o3d.io.write_point_cloud(str(out_path), pcd)
    print(f"{display_path(path)}: centroid was {centroid} -> shifted to origin, {len(points)} points")
    print(f"  -> {display_path(out_path)}")
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--target", required=True, help="LiDAR reference cloud")
    parser.add_argument("--sources", required=True, nargs="+", help="one or more experiment clouds")
    args = parser.parse_args()

    center_on_own_centroid(resolve_path(args.target))
    for source_str in args.sources:
        center_on_own_centroid(resolve_path(source_str))


if __name__ == "__main__":
    main()
