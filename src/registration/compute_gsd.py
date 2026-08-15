"""Compute Ground Sampling Distance (GSD) - the real-world size represented
by one image pixel - for a COLMAP-family experiment's source photos.

GSD is a property of the capture (camera + distance to the subject), not of
the reconstruction method: COLMAP's calibrated focal length (from bundle
adjustment) describes the physical camera regardless of which algorithm
later processes the images. So this only needs a COLMAP-family experiment
(colmap or hloc_colmap) that saves a calibrated cameras.bin/images.bin -
VGGT/MASt3R-GA don't currently persist poses/intrinsics (only the output
.ply), so GSD can't be computed this way for them. But since every method
for a given object shares the same source video/frames, a single
COLMAP-family GSD answers the question for the whole object, not just that
one experiment.

Method: for each registered image, average the distance from its camera
center to every sparse 3D point it observes (the depth of the visible
object surface from that viewpoint), in COLMAP's raw SfM units. Convert to
meters using the scale register_point_clouds.py already fit for that same
reconstruction against the LiDAR reference (report.json's "estimated_scale",
further refined by "manual_extra_scale_correction" if present - see
register_point_clouds.py / compare_scale_reference.py). Focal length is read
straight from COLMAP's camera model in true pixel units - no scale
conversion needed for it, only for the depth.

    GSD_per_image = depth_m / f_px

Cross-check (bollard_002, exp_030): manually measuring the in-scene 9.5cm
reference marker's pixel size on one frame gave ~0.9mm/px - same order of
magnitude as this method's ~1.1mm/px. See docs/methodology_notes.md.

Usage:
    python src/registration/compute_gsd.py \\
        outputs/experiments/exp_030_colmap_bollard_002/sparse/0 \\
        outputs/registrations/reg_030_to_lidar_bollard_002/report.json \\
        --output outputs/metrics/reg_030_to_lidar_bollard_002/gsd.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pycolmap

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def resolve_path(path_str: str) -> Path:
    path = Path(path_str)
    return path if path.is_absolute() else (PROJECT_ROOT / path).resolve()


def display_path(path: Path) -> str:
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def load_scale(report: dict) -> float:
    scale = report["estimated_scale"]
    scale *= report.get("manual_extra_scale_correction", 1.0)
    return scale


def per_image_depths(rec: pycolmap.Reconstruction) -> dict[str, float]:
    depths = {}
    for image in rec.images.values():
        cam_center = np.array(image.projection_center())
        obs = [
            np.linalg.norm(np.array(rec.points3D[p2d.point3D_id].xyz) - cam_center)
            for p2d in image.points2D
            if p2d.has_point3D()
        ]
        if obs:
            depths[image.name] = float(np.mean(obs))
    return depths


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("sparse_dir", help="COLMAP sparse reconstruction dir (containing cameras.bin/images.bin/points3D.bin)")
    parser.add_argument("registration_report", help="register_point_clouds.py's report.json for this experiment's registration to LiDAR (supplies the SfM-units -> meters scale)")
    parser.add_argument("--output", default=None, help="optional path to save the result as JSON")
    args = parser.parse_args()

    sparse_dir = resolve_path(args.sparse_dir)
    report_path = resolve_path(args.registration_report)
    report = json.loads(report_path.read_text())
    scale = load_scale(report)

    rec = pycolmap.Reconstruction(str(sparse_dir))
    cameras = list(rec.cameras.values())
    if len(cameras) != 1:
        raise SystemExit(f"Expected a single shared camera, found {len(cameras)} in {display_path(sparse_dir)}")
    f_px = cameras[0].params[0]

    raw_depths = per_image_depths(rec)
    depths_m = {name: d * scale for name, d in raw_depths.items()}
    gsd_per_image = {name: d / f_px for name, d in depths_m.items()}

    depths_arr = np.array(list(depths_m.values()))
    gsd_arr = np.array(list(gsd_per_image.values()))

    result = {
        "sparse_dir": display_path(sparse_dir),
        "registration_report": display_path(report_path),
        "scale_m_per_raw_unit": scale,
        "focal_length_px": f_px,
        "image_size": [cameras[0].width, cameras[0].height],
        "n_images": len(gsd_arr),
        "camera_object_distance_m": {
            "mean": float(depths_arr.mean()),
            "median": float(np.median(depths_arr)),
            "std": float(depths_arr.std()),
            "min": float(depths_arr.min()),
            "max": float(depths_arr.max()),
        },
        "gsd_m_per_px": {
            "mean": float(gsd_arr.mean()),
            "median": float(np.median(gsd_arr)),
            "std": float(gsd_arr.std()),
            "min": float(gsd_arr.min()),
            "max": float(gsd_arr.max()),
        },
        "gsd_per_image_m_per_px": gsd_per_image,
    }

    print(f"=== {display_path(sparse_dir)} ({result['n_images']} images) ===")
    print(f"focal length: {f_px:.2f} px, image size: {cameras[0].width}x{cameras[0].height}")
    print(
        f"camera-object distance: {result['camera_object_distance_m']['mean']:.3f} m mean "
        f"(median {result['camera_object_distance_m']['median']:.3f} m)"
    )
    print(
        f"GSD: {result['gsd_m_per_px']['mean']*1000:.3f} mm/px mean "
        f"(median {result['gsd_m_per_px']['median']*1000:.3f} mm/px)"
    )

    if args.output:
        output_path = resolve_path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(result, indent=2))
        print(f"Saved -> {display_path(output_path)}")


if __name__ == "__main__":
    main()
