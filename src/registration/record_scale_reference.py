"""Record a manual measurement of the known-size reference square (9.5cm x
9.5cm, present in-scene from exp_034 onward - see docs/methodology_notes.md)
as picked/measured on an experiment's RAW, un-registered point cloud.

Pipeline order this is meant to slot into (do this step FIRST, before the
square gets cropped away):
    1. THIS SCRIPT - measure the square's side on the raw reconstruction,
       record it here.
    2. crop_point_cloud.py - crop down to just the object (the square won't
       be in the crop).
    3. remove_ground_plane.py - strip the floor from the crop.
    4. register_point_clouds.py - register the cropped/floor-removed object
       against the LiDAR reference (this fits its OWN scale estimate via
       ICP - see that script's docstring on why photogrammetry scale is
       otherwise unknown).
    5. evaluate_registration.py - Accuracy/Completeness/F-score metrics.
    6. compare_scale_reference.py - THIS is where the measurement recorded
       in step 1 finally gets used: compares the square-implied scale
       against register_point_clouds.py's independently-fitted scale
       (step 4's report.json) as a cross-check.

The measured distance must be in the SAME units as the raw reconstruction
itself (COLMAP/hloc: arbitrary SfM units; MASt3R-GA/VGGT: claimed metric
meters natively) - measure two opposite corners of the square (e.g. via
CloudCompare's point-picking + distance tool, or Open3D) on the untouched
exp_NNN_*.ply / dense/fused.ply, not on anything cropped/registered.

Usage:
    python src/registration/record_scale_reference.py exp_034 0.01230
    python src/registration/record_scale_reference.py exp_034 0.01230 \\
        --note "picked opposite corners in CloudCompare on exp_034_vggt_bollard_002.ply"
"""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MEASUREMENTS_PATH = PROJECT_ROOT / "outputs/metrics/scale_reference.yaml"
SQUARE_SIDE_M = 0.095


def resolve_path(path_str: str) -> Path:
    path = Path(path_str)
    return path if path.is_absolute() else (PROJECT_ROOT / path).resolve()


def load_measurements(path: Path) -> dict:
    if not path.exists():
        return {"square_side_m": SQUARE_SIDE_M, "measurements": {}}
    return yaml.safe_load(path.read_text()) or {"square_side_m": SQUARE_SIDE_M, "measurements": {}}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("exp_id", help="e.g. exp_034 - the experiment whose RAW point cloud the square was measured on")
    parser.add_argument("raw_side_length", type=float, help="measured square side length, in the raw reconstruction's own units")
    parser.add_argument("--note", default=None, help="optional free-text note (how it was measured, which corners, etc.)")
    parser.add_argument("--output", default=str(DEFAULT_MEASUREMENTS_PATH))
    args = parser.parse_args()

    output_path = resolve_path(args.output)
    data = load_measurements(output_path)
    data["square_side_m"] = SQUARE_SIDE_M

    entry = {"raw_side_length": args.raw_side_length, "recorded_date": date.today().isoformat()}
    if args.note:
        entry["note"] = args.note
    data.setdefault("measurements", {})[args.exp_id] = entry

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(yaml.dump(data, sort_keys=False, allow_unicode=True))

    implied_scale = SQUARE_SIDE_M / args.raw_side_length
    print(f"Recorded {args.exp_id}: raw_side_length={args.raw_side_length} -> implied scale (m per raw unit) = {implied_scale:.6f}")
    print(f"Saved -> {output_path}")


if __name__ == "__main__":
    main()
