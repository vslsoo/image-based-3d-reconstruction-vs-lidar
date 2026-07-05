"""Run one SuperPoint+LightGlue -> COLMAP experiment: pick a diverse image
subset, extract SuperPoint keypoints, match them with LightGlue, run
COLMAP's own SfM mapper on those matches, then COLMAP's dense MVS - saving
everything under outputs/ and logging the run to config/experiments.yaml.

This is a different front-end from run_colmap_experiment.py's COLMAP method
(SuperPoint+LightGlue instead of SIFT for features/matching) and from
run_mast3r_sfm_experiment.py (a learned matcher feeding classical SfM, same
idea as the MASt3R+SfM pipeline, but via hloc instead of a hand-rolled
kapture/pycolmap bridge). COLMAP itself still does the actual sparse
triangulation/bundle-adjustment and dense MVS, exactly as in the COLMAP-only
pipeline - only the feature extraction/matching stage changes.

Uses hloc (https://github.com/cvg/Hierarchical-Localization, vendored under
external/hloc, Apache-2.0) to extract features, match them, and populate a
COLMAP database; dense reconstruction reuses run_colmap_experiment.py's
implementation directly and needs a CUDA-enabled COLMAP/pycolmap build.

Usage:
    python src/reconstruction/run_hloc_colmap_experiment.py bollard_001
    python src/reconstruction/run_hloc_colmap_experiment.py bollard_001 --num-images 20 --skip-dense
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pycolmap
import yaml

from common import (
    append_experiment_entry,
    copy_image_subset,
    format_experiment_entry,
    list_images,
    next_experiment_id,
    resolve_path,
    select_image_subset,
)
from run_colmap_experiment import count_ply_vertices, run_dense_reconstruction

HLOC_ROOT = resolve_path("external/hloc")
sys.path.insert(0, str(HLOC_ROOT))

from hloc import extract_features, match_features, pairs_from_exhaustive, reconstruction  # noqa: E402


# ---------------------------------------------------------------------------
# 1. Sparse reconstruction (SuperPoint+LightGlue matching -> COLMAP SfM)
# ---------------------------------------------------------------------------

def write_window_pairs(output_path: Path, image_names: list[str], window_size: int) -> None:
    """hloc ships pairs_from_exhaustive (all O(n^2) pairs) but no sliding-window
    generator - this matches each image against its `window_size` nearest
    neighbors in capture order, cyclically (a walk-around is a loop), giving
    O(n) pairs instead."""
    n = len(image_names)
    pairs = set()
    for i in range(n):
        for offset in range(1, window_size + 1):
            j = (i + offset) % n
            if j == i:
                continue
            pairs.add((min(i, j), max(i, j)))
    with open(output_path, "w") as f:
        f.write("\n".join(f"{image_names[i]} {image_names[j]}" for i, j in sorted(pairs)))


def run_sparse_reconstruction(image_dir: Path, workspace_path: Path, config: dict) -> tuple[Path, dict]:
    feature_conf = extract_features.confs[config["features"]["conf"]]
    matcher_conf = match_features.confs[config["matching"]["conf"]]
    image_names = [p.name for p in list_images(image_dir)]

    pairs_path = workspace_path / "pairs.txt"
    if config["matching"].get("pairing", "exhaustive") == "window":
        write_window_pairs(pairs_path, image_names, config["matching"]["window_size"])
    else:
        pairs_from_exhaustive.main(pairs_path, image_list=image_names)

    features_path = extract_features.main(feature_conf, image_dir, export_dir=workspace_path)
    matches_path = workspace_path / "matches.h5"
    match_features.main(
        matcher_conf, pairs_path, features=features_path,
        export_dir=workspace_path, matches=matches_path,
    )

    sfm_path = workspace_path / "sparse"
    camera_mode = (
        pycolmap.CameraMode.SINGLE
        if config["camera"]["single_camera"]
        else pycolmap.CameraMode.AUTO
    )
    reconstruction_obj = reconstruction.main(
        sfm_path, image_dir, pairs_path, features_path, matches_path,
        camera_mode=camera_mode,
        image_options={"camera_model": config["camera"]["camera_model"]},
    )
    if reconstruction_obj is None:
        raise RuntimeError("hloc/COLMAP reconstruction failed - check image overlap/quality.")

    # hloc's reconstruction.main() already moves the largest model's files
    # directly into sfm_path (not sfm_path/0/), unlike raw pycolmap.incremental_mapping
    stats = {
        "registered_images": reconstruction_obj.num_reg_images(),
        "points3D": reconstruction_obj.num_points3D(),
        "observations": reconstruction_obj.compute_num_observations(),
        "mean_track_length": reconstruction_obj.compute_mean_track_length(),
        "mean_reprojection_error": reconstruction_obj.compute_mean_reprojection_error(),
    }
    return sfm_path, stats


# ---------------------------------------------------------------------------
# 2. CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("object_id", help="Key under `objects:` in config/objects.yaml")
    parser.add_argument("--config", default="config/hloc_colmap.yaml")
    parser.add_argument("--objects-config", default="config/objects.yaml")
    parser.add_argument("--experiments-config", default="config/experiments.yaml")
    parser.add_argument("--num-images", type=int, default=None, help="overrides image_selection.num_images")
    parser.add_argument("--selection-method", choices=["even", "random"], default=None)
    parser.add_argument(
        "--skip-dense",
        action="store_true",
        help="debug only: run sparse reconstruction and stop there, even with CUDA available",
    )
    args = parser.parse_args()

    if not args.skip_dense and not pycolmap.has_cuda:
        raise SystemExit(
            "Dense reconstruction requires a CUDA-enabled COLMAP/pycolmap build, "
            "which isn't available on this machine. Run this script on a CUDA machine "
            "(e.g. the same GPU pod used for the other experiments), or pass "
            "--skip-dense if you only want to test image selection / sparse reconstruction here."
        )

    config = yaml.safe_load(resolve_path(args.config).read_text())
    objects = yaml.safe_load(resolve_path(args.objects_config).read_text())["objects"]
    if args.object_id not in objects:
        raise SystemExit(f"Unknown object_id '{args.object_id}'. Known: {sorted(objects)}")

    num_images = args.num_images or config["image_selection"]["num_images"]
    selection_method = args.selection_method or config["image_selection"]["method"]

    image_dir_rel = f"{objects[args.object_id]['images_dir']}/jpg"
    image_dir = resolve_path(image_dir_rel)

    experiments_path = resolve_path(args.experiments_config)
    exp_id = next_experiment_id(experiments_path)
    output_dir_rel = f"outputs/{exp_id}_hloc_colmap_{args.object_id}"
    output_dir = resolve_path(output_dir_rel)
    output_dir.mkdir(parents=True, exist_ok=True)

    all_images = list_images(image_dir)
    print(f"[{exp_id}] {len(all_images)} images found in {image_dir}")
    selected = select_image_subset(all_images, num_images, selection_method, config["image_selection"].get("seed", 42))
    subset_dir = copy_image_subset(selected, output_dir / "images")
    print(f"[{exp_id}] Selected {len(selected)} images ({selection_method}) -> {subset_dir}")

    print(f"[{exp_id}] Running sparse reconstruction (SuperPoint+LightGlue -> COLMAP)...")
    model_path, sparse_stats = run_sparse_reconstruction(subset_dir, output_dir, config)
    print(
        f"[{exp_id}] Sparse done: {sparse_stats['registered_images']}/{len(selected)} images registered, "
        f"{sparse_stats['points3D']} points, mean reprojection error "
        f"{sparse_stats['mean_reprojection_error']:.3f}px"
    )

    log_lines = [
        f"Registered images: {sparse_stats['registered_images']}/{len(selected)}",
        f"Points in sparse reconstruction: {sparse_stats['points3D']}",
        f"Observations: {sparse_stats['observations']}",
        f"Mean track length: {sparse_stats['mean_track_length']:.6f}",
        f"Mean reprojection error: {sparse_stats['mean_reprojection_error']:.6f}px",
    ]

    if args.skip_dense:
        print(f"[{exp_id}] Dense reconstruction skipped: debug run via --skip-dense")
        log_lines.append("Dense reconstruction skipped: debug run via --skip-dense (not a full experiment)")
    else:
        print(f"[{exp_id}] Running dense reconstruction...")
        fused_path, dense_stats = run_dense_reconstruction(model_path, subset_dir, output_dir, config)
        print(f"[{exp_id}] Dense done: {dense_stats['fused_points']} points -> {fused_path}")
        log_lines.append(f"Dense fused point cloud: {dense_stats['fused_points']} points")

    entry = format_experiment_entry(
        exp_id=exp_id,
        object_id=args.object_id,
        method="hloc_colmap",
        image_dir_rel=image_dir_rel,
        output_dir_rel=output_dir_rel,
        total_images=len(selected),
        selection_method=selection_method,
        parameters={
            "camera_model": config["camera"]["camera_model"],
            "single_camera": config["camera"]["single_camera"],
            "features": config["features"]["conf"],
            "matching": config["matching"]["conf"],
            "pairing": config["matching"].get("pairing", "exhaustive"),
            "window_size": config["matching"].get("window_size"),
            "dense_max_image_size": config["dense"]["max_image_size"],
        },
        log_lines=log_lines,
    )
    append_experiment_entry(experiments_path, entry)
    print(f"[{exp_id}] Logged experiment to {experiments_path}")


if __name__ == "__main__":
    main()
