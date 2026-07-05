"""Run one COLMAP experiment end to end: pick a diverse image subset, then
sparse + dense reconstruction, saving everything under outputs/ and logging
the run to config/experiments.yaml.

Usage:
    python src/reconstruction/run_colmap_experiment.py bollard_001
    python src/reconstruction/run_colmap_experiment.py bollard_001 --num-images 20
    python src/reconstruction/run_colmap_experiment.py bollard_001 --skip-dense

Reconstruction parameters live in config/reconstruction.yaml; the object's
image folder is looked up from config/objects.yaml by object_id.
"""

from __future__ import annotations

import argparse
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


# ---------------------------------------------------------------------------
# 1. Sparse reconstruction
# ---------------------------------------------------------------------------

def run_sparse_reconstruction(image_path: Path, workspace_path: Path, config: dict) -> tuple[Path, dict]:
    database_path = workspace_path / "database.db"
    sparse_path = workspace_path / "sparse"
    sparse_path.mkdir(parents=True, exist_ok=True)

    reader_options = pycolmap.ImageReaderOptions()
    reader_options.camera_model = config["camera"]["camera_model"]
    camera_mode = (
        pycolmap.CameraMode.SINGLE
        if config["camera"]["single_camera"]
        else pycolmap.CameraMode.AUTO
    )

    pycolmap.extract_features(
        database_path=database_path,
        image_path=image_path,
        camera_mode=camera_mode,
        reader_options=reader_options,
    )

    matching_method = config["matching"]["method"]
    if matching_method == "sequential":
        pycolmap.match_sequential(database_path=database_path)
    elif matching_method == "exhaustive":
        pycolmap.match_exhaustive(database_path=database_path)
    else:
        raise ValueError(f"Unknown matching method: {matching_method}")

    maps = pycolmap.incremental_mapping(
        database_path=database_path,
        image_path=image_path,
        output_path=sparse_path,
    )
    if not maps:
        raise RuntimeError("Incremental mapping registered no images - check image overlap/quality.")

    best_idx = max(maps, key=lambda idx: maps[idx].num_reg_images())
    reconstruction = maps[best_idx]
    model_path = sparse_path / str(best_idx)

    stats = {
        "registered_images": reconstruction.num_reg_images(),
        "points3D": reconstruction.num_points3D(),
        "observations": reconstruction.compute_num_observations(),
        "mean_track_length": reconstruction.compute_mean_track_length(),
        "mean_observations_per_image": reconstruction.compute_mean_observations_per_reg_image(),
        "mean_reprojection_error": reconstruction.compute_mean_reprojection_error(),
    }
    return model_path, stats


# ---------------------------------------------------------------------------
# 2. Dense reconstruction
# ---------------------------------------------------------------------------

def count_ply_vertices(ply_path: Path) -> int:
    with ply_path.open("rb") as f:
        for raw_line in f:
            line = raw_line.decode("ascii", errors="ignore").strip()
            if line.startswith("element vertex"):
                return int(line.split()[-1])
            if line == "end_header":
                break
    return -1


def run_dense_reconstruction(model_path: Path, image_path: Path, workspace_path: Path, config: dict) -> tuple[Path, dict]:
    if not pycolmap.has_cuda:
        raise RuntimeError("Dense reconstruction requires a CUDA-enabled COLMAP/pycolmap build.")

    dense_path = workspace_path / "dense"
    dense_path.mkdir(parents=True, exist_ok=True)
    fused_path = dense_path / "fused.ply"

    pycolmap.undistort_images(
        output_path=dense_path,
        input_path=model_path,
        image_path=image_path,
        output_type="COLMAP",
    )

    patch_options = pycolmap.PatchMatchOptions()
    patch_options.gpu_index = config["dense"].get("gpu_index", "0")
    patch_options.geom_consistency = config["dense"]["geom_consistency"]
    patch_options.cache_size = config["dense"]["cache_size"]
    patch_options.num_threads = config["dense"]["num_threads"]
    patch_options.allow_missing_files = True
    pycolmap.patch_match_stereo(
        workspace_path=dense_path,
        workspace_format="COLMAP",
        options=patch_options,
    )

    fusion_options = pycolmap.StereoFusionOptions()
    fusion_options.cache_size = config["dense"]["cache_size"]
    fusion_options.num_threads = config["dense"]["num_threads"]
    fusion_options.max_image_size = config["dense"]["max_image_size"]
    pycolmap.stereo_fusion(
        output_path=fused_path,
        workspace_path=dense_path,
        workspace_format="COLMAP",
        input_type="geometric",
        options=fusion_options,
        output_type="PLY",
    )

    stats = {"fused_points": count_ply_vertices(fused_path)}
    return fused_path, stats


# ---------------------------------------------------------------------------
# 3. CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("object_id", help="Key under `objects:` in config/objects.yaml")
    parser.add_argument("--config", default="config/reconstruction.yaml")
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
            "(e.g. Google Colab), or pass --skip-dense if you only want to test image "
            "selection / sparse reconstruction here."
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
    output_dir_rel = f"outputs/{exp_id}_colmap_{args.object_id}"
    output_dir = resolve_path(output_dir_rel)
    output_dir.mkdir(parents=True, exist_ok=True)

    all_images = list_images(image_dir)
    print(f"[{exp_id}] {len(all_images)} images found in {image_dir}")
    selected = select_image_subset(all_images, num_images, selection_method, config["image_selection"]["seed"])
    subset_dir = copy_image_subset(selected, output_dir / "images")
    print(f"[{exp_id}] Selected {len(selected)} images ({selection_method}) -> {subset_dir}")

    print(f"[{exp_id}] Running sparse reconstruction...")
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
        f"Mean observations per image: {sparse_stats['mean_observations_per_image']:.6f}",
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
        method="colmap",
        image_dir_rel=image_dir_rel,
        output_dir_rel=output_dir_rel,
        total_images=len(selected),
        selection_method=selection_method,
        parameters={
            "camera_model": config["camera"]["camera_model"],
            "single_camera": config["camera"]["single_camera"],
            "feature": config["features"]["type"],
            "matching": config["matching"]["method"],
            "mapper": config["mapper"]["type"],
            "dense_max_image_size": config["dense"]["max_image_size"],
        },
        log_lines=log_lines,
    )
    append_experiment_entry(experiments_path, entry)
    print(f"[{exp_id}] Logged experiment to {experiments_path}")


if __name__ == "__main__":
    main()
