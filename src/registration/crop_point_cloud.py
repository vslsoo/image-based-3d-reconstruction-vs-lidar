"""Interactively crop a point cloud down to a region of interest (e.g. just
the object, removing floor/background) before registration.

Why: global registration (RANSAC + FPFH in register_point_clouds.py) can
lock onto large flat surfaces like the ground instead of the actual object,
since a plane barely constrains rotation/scale - it "matches" almost
anywhere. Crop both clouds down to just the object first, then run
register_point_clouds.py on the cropped versions instead of the raw ones.

Controls (Open3D's built-in crop editor - see
http://www.open3d.org/docs/latest/tutorial/Advanced/interactive_visualization.html):
    - Drag with left mouse button: rotate the view.
    - 'Y' then 'K': align view to look straight down the Y axis, then lock
      the view and enter polygon-selection mode.
    - Left-click to place polygon vertices around the region to KEEP; right-
      click (or close the polygon) to finish the selection.
    - 'C': crop the geometry to the current selection.
    - 'S': save the cropped point cloud to a file in the current directory.
    - Close the window when done.

This script changes into --output's parent directory before opening the
editor, so whatever Open3D auto-saves on 'S' lands next to --output - check
that directory afterwards, since the exact auto-generated filename can vary
by Open3D version (rename/move it to --output yourself if it differs).

Usage:
    python src/registration/crop_point_cloud.py \\
        outputs/exp_003_colmap_bollard_001/exp_003_colmap_bollard_001.ply \\
        outputs/exp_003_colmap_bollard_001/exp_003_cropped.ply
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import open3d as o3d

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def resolve_path(path_str: str) -> Path:
    path = Path(path_str)
    return path if path.is_absolute() else (PROJECT_ROOT / path).resolve()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("input", help="point cloud to crop (.ply)")
    parser.add_argument("output", help="hint for where to save - see the note above about checking this directory")
    args = parser.parse_args()

    input_path = resolve_path(args.input)
    output_path = resolve_path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    pcd = o3d.io.read_point_cloud(str(input_path))
    print(f"Loaded {len(pcd.points)} points from {input_path}")
    print()
    print("Controls: drag to rotate, 'Y' to align view then 'K' to lock and start a polygon")
    print("selection, left-click to add vertices around the region to KEEP, 'C' to crop,")
    print(f"'S' to save. Files saved via 'S' will land in {output_path.parent} - check there")
    print("afterwards and rename/move the result to your intended output filename if needed.")
    print()

    os.chdir(output_path.parent)
    o3d.visualization.draw_geometries_with_editing([pcd], window_name=f"Crop: {input_path.name}")


if __name__ == "__main__":
    main()
