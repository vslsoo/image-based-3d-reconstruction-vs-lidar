"""Compute point cloud density, using the same two methods historically used
by hand for this project (Autodesk Recap + CloudCompare), so LiDAR and
photogrammetry reconstructions can be compared on a common points/m^2 scale.

Method "grid" (matches the Recap workflow): bin points into non-overlapping
square cells of --cell-size x --cell-size (default 1m, as used by hand -
select a 1m x 1m area, export, count points; since the area is exactly
1 m^2, the point count already equals the density). Points are binned by
their raw X/Y (these clouds are already recentered with Z as true elevation
- see config/objects.yaml's PLY-truncation notes). ONLY MEANINGFUL FOR
ROUGHLY HORIZONTAL/PLANAR PATCHES (e.g. a section of pavement, or a bench
seat) - like the original by-hand workflow, it flattens everything onto the
global X/Y ground plane, so a vertical or curved surface (a bollard/lamppost
shaft) gets many different-height points collapsed onto nearly the same X/Y
cell, wildly overstating density. Use "cloudcompare" instead for anything
that isn't close to flat/horizontal.

Method "cloudcompare" (matches CloudCompare's Density tool, "Surface
density" mode - see https://www.cloudcompare.org/doc/wiki/index.php/Density):
for each point, count neighbors within --radius in full 3D (a sphere, via a
3D KD-tree - CloudCompare's kernel is a small local neighborhood, not a
global flattening), divide by the equivalent disc area (pi * radius^2). This
is a first-order local-surface-density approximation that works regardless
of the surface's orientation/curvature (as long as --radius is small
relative to the surface's own curvature - e.g. don't use a 0.05m radius on
a bollard shaft only ~0.1m in diameter), so it's the one to trust for
non-planar objects. Reported per-point (mean/median/std), and the two
methods were historically cross-checked against each other by hand on
roughly-flat patches where both are valid.

Usage:
    python src/registration/compute_point_density.py \\
        data/lidar/bollard_002/bollard_002_no_floor.ply

    python src/registration/compute_point_density.py \\
        data/video/bench_001/lidar/bench_001_lidar.ply \\
        outputs/experiments/exp_025_colmap_bench_001/dense/fused.ply \\
        --cell-size 0.2 --radius 0.05 \\
        --output outputs/metrics/density_comparison.json
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

import numpy as np
import open3d as o3d
from scipy.spatial import cKDTree

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
# 1. Loading (.ply via Open3D, .laz/.las via the pdal CLI - same split as
#    crop_objects_from_lidar.py, since Open3D can't read LAS/LAZ directly)
# ---------------------------------------------------------------------------

def load_points_xyz(path: Path) -> np.ndarray:
    if path.suffix.lower() == ".ply":
        pcd = o3d.io.read_point_cloud(str(path))
        return np.asarray(pcd.points)

    if path.suffix.lower() in (".laz", ".las"):
        result = subprocess.run(
            ["pdal", "translate", str(path), "STDOUT", "--writers.text.order=X,Y,Z"],
            check=True, capture_output=True, text=True,
        )
        lines = result.stdout.splitlines()[1:]  # skip header
        xyz = np.array([[float(v) for v in line.split(",")] for line in lines if line.strip()])
        return xyz

    raise ValueError(f"Unsupported point cloud format: {path.suffix} ({path})")


# ---------------------------------------------------------------------------
# 2. Method "grid" (Recap-style: fixed square cells, count points per cell)
# ---------------------------------------------------------------------------

def grid_density(xy: np.ndarray, cell_size: float) -> dict:
    mins = xy.min(axis=0)
    cell_idx = np.floor((xy - mins) / cell_size).astype(int)
    _, counts = np.unique(cell_idx, axis=0, return_counts=True)
    cell_area = cell_size ** 2
    per_cell_density = counts / cell_area

    footprint_area = len(counts) * cell_area
    whole_footprint_density = len(xy) / footprint_area

    return {
        "cell_size_m": cell_size,
        "occupied_cells": int(len(counts)),
        "points_per_cell_m2": {
            "mean": float(per_cell_density.mean()),
            "median": float(np.median(per_cell_density)),
            "std": float(per_cell_density.std()),
            "min": float(per_cell_density.min()),
            "max": float(per_cell_density.max()),
        },
        "whole_footprint_points_per_m2": float(whole_footprint_density),
        "footprint_area_m2": float(footprint_area),
    }


# ---------------------------------------------------------------------------
# 3. Method "cloudcompare" (per-point disc-neighbor count / disc area)
# ---------------------------------------------------------------------------

def cloudcompare_density(xyz: np.ndarray, radius: float, max_points: int | None = None) -> dict:
    sample = xyz
    if max_points is not None and len(xyz) > max_points:
        idx = np.random.default_rng(42).choice(len(xyz), max_points, replace=False)
        sample = xyz[idx]

    tree = cKDTree(xyz)  # full 3D, not flattened - see module docstring
    neighbor_counts = tree.query_ball_point(sample, r=radius, return_length=True) - 1  # exclude self
    disc_area = np.pi * radius ** 2
    per_point_density = neighbor_counts / disc_area

    return {
        "radius_m": radius,
        "points_sampled": int(len(sample)),
        "points_per_m2": {
            "mean": float(per_point_density.mean()),
            "median": float(np.median(per_point_density)),
            "std": float(per_point_density.std()),
            "min": float(per_point_density.min()),
            "max": float(per_point_density.max()),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("inputs", nargs="+", help="point cloud(s) to measure (.ply, .laz, .las)")
    parser.add_argument("--cell-size", type=float, default=1.0, help="grid method cell size in meters (default: 1.0, matching the Recap convention)")
    parser.add_argument("--radius", type=float, default=0.1, help="cloudcompare method disc radius in meters (default: 0.1)")
    parser.add_argument("--max-points", type=int, default=200_000, help="subsample the cloudcompare method to at most this many query points for speed (default: 200000, use 0 to disable)")
    parser.add_argument("--output", default=None, help="optional path to save all results as JSON")
    args = parser.parse_args()

    max_points = None if args.max_points == 0 else args.max_points
    results = {}

    for input_str in args.inputs:
        path = resolve_path(input_str)
        xyz = load_points_xyz(path)
        xy = xyz[:, :2]
        print(f"\n=== {display_path(path)} ({len(xyz)} points) ===")

        grid = grid_density(xy, args.cell_size)
        print(
            f"[grid, {args.cell_size}m cells] {grid['occupied_cells']} occupied cells, "
            f"{grid['points_per_cell_m2']['mean']:.1f} +/- {grid['points_per_cell_m2']['std']:.1f} pts/m^2 "
            f"(median {grid['points_per_cell_m2']['median']:.1f}); "
            f"whole-footprint: {grid['whole_footprint_points_per_m2']:.1f} pts/m^2 "
            f"over {grid['footprint_area_m2']:.2f} m^2"
        )

        cc = cloudcompare_density(xyz, args.radius, max_points)
        print(
            f"[cloudcompare, r={args.radius}m] {cc['points_per_m2']['mean']:.1f} +/- "
            f"{cc['points_per_m2']['std']:.1f} pts/m^2 (median {cc['points_per_m2']['median']:.1f})"
        )

        results[display_path(path)] = {"grid": grid, "cloudcompare": cc}

    if args.output:
        output_path = resolve_path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(results, indent=2))
        print(f"\nSaved -> {display_path(output_path)}")


if __name__ == "__main__":
    main()
