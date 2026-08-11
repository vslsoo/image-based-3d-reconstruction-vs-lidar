"""Crop object-sized regions out of the full-resolution LiDAR tracks, using
a small reference/"object" point cloud per object to define the crop
boundary, then merge the per-track crops into one file per object.

Why: Sensat-Euston-Track2.laz and Track3.laz are the original, un-downsampled
scans (~5.1 GB / ~2.4 GB) - too dense to work with directly, but the only
source with full detail. The downsampled+merged file
(data/lidar/original/downsampled/Sensat-Euston-Track2_Track3_merged_0.1m.laz) is meant
for *browsing* (e.g. in CloudCompare) to pick out where each object is - once
you've roughly selected/exported a small cloud around an object from that
browsing session (a "reference" cloud, in the SAME absolute coordinates as
the merged file - do not recenter/shift it), this script takes that
reference cloud's bounding box and re-crops the SAME region directly from
the two ORIGINAL full-density tracks (matches the precedent in
config/objects.yaml for bench_001: "Always re-crop the final bbox directly
from the original file with pdal rather than trusting an interactively-
exported subset" - CloudCompare's viewport LOD thinning silently drops
points on interactive crops/exports).

An object can straddle the Track2/Track3 boundary or appear (partially) in
both, so each object's final output is Track2's crop MERGED with Track3's
crop for that same bbox, not either one alone.

Coordinate system: Track2/Track3 use large UTM-like absolute coordinates
(~291000/287000-scale). This script crops and writes output entirely in
those same absolute coordinates (.laz, no precision loss) - it does NOT
recenter. If you need a locally-shifted .ply for Open3D-based scripts
downstream (register_point_clouds.py, remove_ground_plane.py, ...), recenter
it yourself afterwards - see the PLY-precision-truncation pitfall documented
on bench_001 in config/objects.yaml before ever writing these absolute
coordinates through a .ply.

Requires the `pdal` CLI (brew install pdal) - same tool already used by
reduce_and_merge_lidar_for_cloudcompare.sh.

Usage:
    # One object, output path derived from the reference file's name:
    # -> data/lidar/bollard_002/bollard_002.laz
    python src/data_preparation/crop_objects_from_lidar.py \\
        outputs/refs/bollard_002_ref.laz

    # Several objects in one run, with a margin around each rough selection:
    python src/data_preparation/crop_objects_from_lidar.py \\
        outputs/refs/flashlight_001_ref.ply outputs/refs/bollard_002_ref.ply \\
        --margin 0.3

    # Explicit output path (only valid for a single reference cloud):
    python src/data_preparation/crop_objects_from_lidar.py \\
        outputs/refs/bench_002_ref.laz \\
        --output data/lidar/bench_002/bench_002.laz
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_TRACK2 = PROJECT_ROOT / "data/lidar/original/Sensat-Euston-Track2.laz"
DEFAULT_TRACK3 = PROJECT_ROOT / "data/lidar/original/Sensat-Euston-Track3.laz"


def resolve_path(path_str: str) -> Path:
    path = Path(path_str)
    return path if path.is_absolute() else (PROJECT_ROOT / path).resolve()


def get_bounds(path: Path) -> dict[str, float]:
    """minx/maxx/miny/maxy/minz/maxz of a point cloud - any format PDAL can
    read. Tries the cheap path first: `--metadata` reads bounds straight out
    of the LAS/LAZ header, no data scan, which matters a lot on the ~5.1 GB/
    ~2.4 GB Track2/Track3 originals. readers.ply has no such header, so
    metadata.minx/etc. come back empty there - fall back to `--stats`, which
    computes bounds by scanning the actual points (stats.bbox.native.bbox) -
    fine for small reference clouds, but never call this on the big tracks
    with a format that needs the fallback."""
    result = subprocess.run(
        ["pdal", "info", "--metadata", str(path)], check=True, capture_output=True, text=True,
    )
    metadata = json.loads(result.stdout)["metadata"]
    if metadata.get("minx") is not None:
        return {k: float(metadata[k]) for k in ("minx", "maxx", "miny", "maxy", "minz", "maxz")}

    result = subprocess.run(
        ["pdal", "info", "--stats", str(path)], check=True, capture_output=True, text=True,
    )
    bbox = json.loads(result.stdout)["stats"]["bbox"]["native"]["bbox"]
    return {k: float(bbox[k]) for k in ("minx", "maxx", "miny", "maxy", "minz", "maxz")}


def get_count(path: Path) -> int:
    result = subprocess.run(
        ["pdal", "info", "--metadata", str(path)], check=True, capture_output=True, text=True,
    )
    return int(json.loads(result.stdout)["metadata"]["count"])


def pad_bounds(bounds: dict[str, float], margin_xy: float, margin_z: float) -> dict[str, float]:
    return {
        "minx": bounds["minx"] - margin_xy, "maxx": bounds["maxx"] + margin_xy,
        "miny": bounds["miny"] - margin_xy, "maxy": bounds["maxy"] + margin_xy,
        "minz": bounds["minz"] - margin_z, "maxz": bounds["maxz"] + margin_z,
    }


def crop_bounds_arg(bounds: dict[str, float]) -> str:
    return (
        f"([{bounds['minx']:.3f},{bounds['maxx']:.3f}],"
        f"[{bounds['miny']:.3f},{bounds['maxy']:.3f}],"
        f"[{bounds['minz']:.3f},{bounds['maxz']:.3f}])"
    )


def bounds_overlap(a: dict[str, float], b: dict[str, float]) -> bool:
    return not (
        a["maxx"] < b["minx"] or a["minx"] > b["maxx"]
        or a["maxy"] < b["miny"] or a["miny"] > b["maxy"]
        or a["maxz"] < b["minz"] or a["minz"] > b["maxz"]
    )


def crop_track(track_path: Path, bounds: dict[str, float], out_path: Path) -> int:
    subprocess.run(
        [
            "pdal", "translate", str(track_path), str(out_path), "crop",
            f"--filters.crop.bounds={crop_bounds_arg(bounds)}",
            "--writers.las.compression=laszip", "--writers.las.minor_version=4",
        ],
        check=True,
    )
    return get_count(out_path)


def crop_one_object(
    ref_path: Path, output_path: Path, track2: Path, track3: Path,
    margin_xy: float, margin_z: float, keep_intermediates: bool,
) -> None:
    print(f"== {ref_path.name} ==")
    ref_bounds = get_bounds(ref_path)
    bounds = pad_bounds(ref_bounds, margin_xy, margin_z)
    print(f"Reference bbox: {crop_bounds_arg(ref_bounds)}")
    if margin_xy or margin_z:
        print(f"Padded bbox (margin_xy={margin_xy}, margin_z={margin_z}): {crop_bounds_arg(bounds)}")

    for name, track_path in (("Track2", track2), ("Track3", track3)):
        track_bounds = get_bounds(track_path)
        if not bounds_overlap(bounds, track_bounds):
            print(
                f"WARNING: crop bbox does not overlap {name}'s bounds at all "
                f"({crop_bounds_arg(track_bounds)}) - check that {ref_path.name} is in the same "
                "absolute coordinate system as the tracks (not recentered/shifted)."
            )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    track2_out = output_path.parent / f"{output_path.stem}_track2.laz"
    track3_out = output_path.parent / f"{output_path.stem}_track3.laz"

    print("Cropping Track2...")
    count2 = crop_track(track2, bounds, track2_out)
    print(f"  {count2} points")
    print("Cropping Track3...")
    count3 = crop_track(track3, bounds, track3_out)
    print(f"  {count3} points")

    if count2 == 0 and count3 == 0:
        raise RuntimeError(
            f"Crop of {ref_path.name} produced 0 points from both tracks - check the reference "
            "cloud's coordinates (see the WARNING above, if any) or the margin."
        )

    non_empty = [p for p, c in ((track2_out, count2), (track3_out, count3)) if c > 0]
    if len(non_empty) == 1:
        shutil.copy(non_empty[0], output_path)
    else:
        subprocess.run(
            ["pdal", "merge", str(track2_out), str(track3_out), str(output_path),
             "--writers.las.compression=laszip", "--writers.las.minor_version=4"],
            check=True,
        )
    total = get_count(output_path)
    print(f"-> {output_path} ({total} points)")

    if not keep_intermediates:
        track2_out.unlink(missing_ok=True)
        track3_out.unlink(missing_ok=True)
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("refs", nargs="+", help="one or more reference/object point clouds defining crop bounds")
    parser.add_argument(
        "--output", default=None,
        help="explicit output path (only valid with a single reference cloud). Default: "
        "data/lidar/<name>/<name>.laz, where <name> is the reference file's stem with a "
        "trailing '_ref'/'_selection'/'_crop' suffix stripped.",
    )
    parser.add_argument("--output-dir", default="data/lidar", help="base dir for the default output convention (default: data/lidar)")
    parser.add_argument("--track2", default=str(DEFAULT_TRACK2), help="path to the original Track2 .laz")
    parser.add_argument("--track3", default=str(DEFAULT_TRACK3), help="path to the original Track3 .laz")
    parser.add_argument(
        "--margin", type=float, default=0.0,
        help="meters to pad the reference bbox by in X/Y before cropping (default: 0 - exact bbox). "
        "Useful if the reference cloud is a tight/rough selection that might clip real edges of the object.",
    )
    parser.add_argument(
        "--margin-z", type=float, default=None,
        help="meters to pad the reference bbox by in Z (default: same as --margin)",
    )
    parser.add_argument(
        "--keep-intermediates", action="store_true",
        help="keep the per-track crop files (<name>_track2.laz / <name>_track3.laz) alongside the merged "
        "output, instead of deleting them once merged",
    )
    args = parser.parse_args()

    if args.output and len(args.refs) > 1:
        parser.error("--output can only be used with a single reference cloud")

    if shutil.which("pdal") is None:
        parser.error("pdal CLI not found - install it first (brew install pdal)")

    track2 = resolve_path(args.track2)
    track3 = resolve_path(args.track3)
    for p in (track2, track3):
        if not p.is_file():
            parser.error(f"Track file not found: {p}")

    margin_z = args.margin if args.margin_z is None else args.margin_z
    output_dir = resolve_path(args.output_dir)

    for ref_str in args.refs:
        ref_path = resolve_path(ref_str)
        if not ref_path.is_file():
            parser.error(f"Reference cloud not found: {ref_path}")

        if args.output:
            output_path = resolve_path(args.output)
        else:
            name = ref_path.stem
            for suffix in ("_ref", "_reference", "_selection", "_crop", "_bounds"):
                if name.endswith(suffix):
                    name = name[: -len(suffix)]
                    break
            output_path = output_dir / name / f"{name}.laz"

        crop_one_object(ref_path, output_path, track2, track3, args.margin, margin_z, args.keep_intermediates)


if __name__ == "__main__":
    main()
