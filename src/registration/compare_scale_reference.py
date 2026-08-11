"""Step 6 of the scale-reference pipeline (see record_scale_reference.py's
docstring for the full 6-step order): compare the known-size reference
square's implied scale (recorded on the RAW reconstruction, before it was
cropped away) against register_point_clouds.py's independently ICP-fitted
scale for that same experiment's registration to LiDAR.

Both numbers are "real-world meters per raw reconstruction unit" (see
register_point_clouds.py's extract_scale() - the transform it fits maps
source units directly into the target/LiDAR cloud's units, which are
already true meters), so they're directly comparable without any unit
conversion. Close agreement is a strong independent confirmation that a
given registration converged on the right scale; a large mismatch flags
that either the registration or the manual measurement is off and worth
rechecking (see register_point_clouds.py's own "scale_mismatch" fallback
logic for the failure mode this can catch - FPFH+RANSAC latching onto a
self-similar sub-part of the object).

Usage:
    python src/registration/compare_scale_reference.py \\
        exp_034 outputs/registrations/reg_034_to_lidar_bollard_002/report.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MEASUREMENTS_PATH = PROJECT_ROOT / "outputs/metrics/scale_reference.yaml"


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
    parser.add_argument("exp_id", help="e.g. exp_034 - must have a measurement recorded via record_scale_reference.py")
    parser.add_argument("report_json", help="register_point_clouds.py's report.json for this experiment's registration to LiDAR")
    parser.add_argument("--measurements", default=str(DEFAULT_MEASUREMENTS_PATH))
    parser.add_argument("--output", default=None, help="optional path to save the comparison as JSON")
    args = parser.parse_args()

    measurements_path = resolve_path(args.measurements)
    if not measurements_path.exists():
        raise SystemExit(f"No measurements file at {display_path(measurements_path)} - run record_scale_reference.py first.")
    data = yaml.safe_load(measurements_path.read_text())
    square_side_m = data["square_side_m"]

    if args.exp_id not in data.get("measurements", {}):
        raise SystemExit(
            f"No recorded measurement for {args.exp_id} in {display_path(measurements_path)} - "
            "run record_scale_reference.py for it first."
        )
    entry = data["measurements"][args.exp_id]
    raw_side_length = entry["raw_side_length"]
    marker_scale = square_side_m / raw_side_length

    report_path = resolve_path(args.report_json)
    report = json.loads(report_path.read_text())
    registration_scale = report["estimated_scale"]

    ratio = max(marker_scale, registration_scale) / min(marker_scale, registration_scale)
    percent_diff = (registration_scale - marker_scale) / marker_scale * 100

    print(f"{args.exp_id}: square side measured as {raw_side_length} raw units ({square_side_m} m true)")
    print(f"  Marker-implied scale:      {marker_scale:.6f} m/unit")
    print(f"  Registration-fitted scale: {registration_scale:.6f} m/unit  (from {display_path(report_path)})")
    print(f"  Ratio: {ratio:.4f}x   Difference: {percent_diff:+.2f}%")

    result = {
        "exp_id": args.exp_id,
        "square_side_m": square_side_m,
        "raw_side_length": raw_side_length,
        "marker_implied_scale": marker_scale,
        "registration_fitted_scale": registration_scale,
        "ratio": ratio,
        "percent_difference": percent_diff,
        "report_json": display_path(report_path),
    }

    if args.output:
        output_path = resolve_path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(result, indent=2))
        print(f"Saved -> {display_path(output_path)}")


if __name__ == "__main__":
    main()
