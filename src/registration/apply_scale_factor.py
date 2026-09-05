"""Isotropically rescale a reconstruction by an EXTERNALLY SUPPLIED scale
factor (or measured-length ratio) - no PCA-axis extent measurement of its
own, unlike scale_to_target_length.py / scale_to_reference_height.py.

Why: those two scripts measure the source's extent themselves (along a PCA
axis) and derive the scale factor from that. Sometimes the "detail" whose
real-world size is known isn't a PCA axis at all - e.g. a single manually
measured edge/distance in a viewer like CloudCompare (a specific vertical
post, a specific span between two picked points). In that case the user has
already measured the same detail in both the reference and each source
cloud; this script just applies target_length / measured_length as a
uniform scale about the source's own centroid, then optionally translates
to a reference cloud's centroid - same centering behavior as
scale_to_target_length.py's --center-on, so outputs from either script drop
into the same downstream register_point_clouds.py step.

Usage:
    python src/registration/apply_scale_factor.py \\
        --source outputs/no_floor/exp_139_colmap_bus_stop_002.ply \\
        --measured-length 2.63 --target-length 2.5 \\
        --center-on data/lidar/bus_stop_001/bus_stop_001_no_floor_centered.ply \\
        --output outputs/scale_corrected/bus_stop_002/exp_139_colmap_bus_stop_002_scaled.ply

    # or pass --scale-factor directly if you've already computed the ratio
    python src/registration/apply_scale_factor.py \\
        --source outputs/no_floor/exp_141_vggt_bus_stop_002.ply \\
        --scale-factor 4.9020 \\
        --center-on data/lidar/bus_stop_001/bus_stop_001_no_floor_centered.ply \\
        --output outputs/scale_corrected/bus_stop_002/exp_141_vggt_bus_stop_002_scaled.ply
"""

from __future__ import annotations

import argparse
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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", required=True, help="reconstruction to rescale")
    parser.add_argument(
        "--scale-factor", type=float, default=None,
        help="scale factor to apply directly (mutually exclusive with --measured-length/--target-length)",
    )
    parser.add_argument(
        "--measured-length", type=float, default=None,
        help="length of the same detail as measured in this source cloud (e.g. a manual CloudCompare distance)",
    )
    parser.add_argument(
        "--target-length", type=float, default=None,
        help="known/reference length of that same detail (e.g. measured in the LiDAR reference)",
    )
    parser.add_argument(
        "--center-on", default=None,
        help="optional reference cloud - after scaling, translate the result so its centroid lands on the "
        "reference's centroid instead of staying at the source's own centroid",
    )
    parser.add_argument("--output", required=True, help="path to write the rescaled source")
    args = parser.parse_args()

    if args.scale_factor is None:
        if args.measured_length is None or args.target_length is None:
            parser.error("pass either --scale-factor, or both --measured-length and --target-length")
        scale = args.target_length / args.measured_length
    else:
        if args.measured_length is not None or args.target_length is not None:
            parser.error("--scale-factor is mutually exclusive with --measured-length/--target-length")
        scale = args.scale_factor

    source_path = resolve_path(args.source)
    output_path = resolve_path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"Loading source: {source_path}")
    source = o3d.io.read_point_cloud(str(source_path))
    source_centroid = np.asarray(source.points).mean(axis=0)
    print(f"Scale factor = {scale:.4f}")

    target_centroid = source_centroid
    center_on_path = None
    if args.center_on:
        center_on_path = resolve_path(args.center_on)
        reference = o3d.io.read_point_cloud(str(center_on_path))
        target_centroid = np.asarray(reference.points).mean(axis=0)
        print(f"Centering on: {center_on_path} (centroid={target_centroid.round(4)})")

    transform = np.eye(4)
    transform[:3, :3] *= scale
    transform[:3, 3] = target_centroid - scale * source_centroid
    scaled_source = source.transform(transform)
    o3d.io.write_point_cloud(str(output_path), scaled_source)

    report = {
        "source": display_path(source_path),
        "measured_length": args.measured_length,
        "target_length": args.target_length,
        "scale_factor": scale,
        "center_on": display_path(center_on_path) if center_on_path else None,
        "target_centroid": target_centroid.tolist(),
        "method": "externally supplied scale factor (or measured-length/target-length ratio), applied "
        "isotropically about source's own centroid, then translated to the reference's centroid if "
        "--center-on was given - no rotation fit, no PCA-axis measurement; use before a full "
        "register_point_clouds.py pass",
    }
    report_path = output_path.with_suffix(".json")
    report_path.write_text(json.dumps(report, indent=2))
    print(f"Saved rescaled cloud -> {output_path}")
    print(f"Saved report -> {report_path}")


if __name__ == "__main__":
    main()
