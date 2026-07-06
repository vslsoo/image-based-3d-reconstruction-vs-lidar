"""Run one MASt3R+SfM experiment end to end: pick a diverse image subset, match
them with MASt3R, run classical SfM (COLMAP's incremental mapper, or GLOMAP)
on those matches, and export the resulting point cloud - saving everything
under outputs/ and logging the run to config/experiments.yaml.

This is a different pipeline from run_colmap_experiment.py's COLMAP method:
MASt3R replaces SIFT for feature matching (better on low-texture surfaces),
and density comes from keeping MASt3R's per-pixel correspondences
(matching.dense_matching in config/mast3r_sfm.yaml) rather than from a
separate MVS stage.

Requires CUDA: mast3r.colmap.mapping.run_mast3r_matching (vendored under
external/mast3r) hardcodes device='cuda' for its nearest-neighbor matching
step regardless of what device the model itself runs on, so - unlike the
CPU-capable MASt3R method used in exp_004 (mast3r/demo.py's global-alignment
approach) - this SfM-based pipeline needs an actual CUDA GPU.

Usage:
    python src/reconstruction/run_mast3r_sfm_experiment.py bollard_001
    python src/reconstruction/run_mast3r_sfm_experiment.py bollard_001 --num-images 20
"""

from __future__ import annotations

import argparse
import os

os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

import shutil
import sys
from pathlib import Path

import pycolmap
import torch
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

MAST3R_ROOT = resolve_path("external/mast3r")
sys.path.insert(0, str(MAST3R_ROOT))
sys.path.insert(0, str(MAST3R_ROOT / "dust3r"))

from kapture.converter.colmap.database import COLMAPDatabase  # noqa: E402
from kapture.converter.colmap.database_extra import kapture_to_colmap  # noqa: E402
from mast3r.colmap.mapping import (  # noqa: E402
    glomap_run_mapper,
    kapture_import_image_folder_or_list,
    run_mast3r_matching,
)
from mast3r.image_pairs import make_pairs  # noqa: E402
from mast3r.model import AsymmetricMASt3R  # noqa: E402
import mast3r.utils.path_to_dust3r  # noqa: E402,F401 (adds dust3r's own deps to sys.path)
from dust3r.utils.image import load_images  # noqa: E402


def resolve_device(device_setting: str) -> str:
    if device_setting != "auto":
        return device_setting
    return "cuda" if torch.cuda.is_available() else "cpu"


# ---------------------------------------------------------------------------
# 1. MASt3R matching -> COLMAP database
# ---------------------------------------------------------------------------

def build_colmap_database(model, device: str, image_dir: Path, image_names: list[str], workspace_path: Path, config: dict) -> Path:
    """Match images with MASt3R and write the correspondences into a COLMAP
    database, so the SfM stage can run on MASt3R matches instead of SIFT."""
    maxdim = max(model.patch_embed.img_size)
    patch_size = model.patch_embed.patch_size

    image_paths = [str(image_dir / name) for name in image_names]
    imgs = load_images(image_paths, size=config["model"]["image_size"], verbose=False)
    pairs = make_pairs(imgs, scene_graph=config["matching"]["scenegraph"], prefilter=None, symmetrize=True)
    image_pairs_kapture = [(image_names[a["idx"]], image_names[b["idx"]]) for a, b in pairs]

    kdata = kapture_import_image_folder_or_list(
        (str(image_dir), image_names), config["matching"]["shared_intrinsics"]
    )

    database_path = workspace_path / "database.db"
    if database_path.exists():
        database_path.unlink()
    colmap_db = COLMAPDatabase.connect(str(database_path))
    kapture_to_colmap(
        kdata, str(image_dir), tar_handler=None, database=colmap_db,
        keypoints_type=None, descriptors_type=None, export_two_view_geometry=False,
    )
    colmap_image_pairs = run_mast3r_matching(
        model, maxdim, patch_size, device,
        kdata, str(image_dir), image_pairs_kapture, colmap_db,
        config["matching"]["dense_matching"], config["matching"]["pixel_tol"],
        config["matching"]["conf_thr"], config["matching"]["skip_geometric_verification"],
        config["matching"]["min_len_track"], config["matching"]["subsample"],
    )
    colmap_db.close()
    if not colmap_image_pairs:
        raise RuntimeError("MASt3R matching kept no image pairs - check image overlap/quality.")

    if not config["matching"]["skip_geometric_verification"]:
        pairs_txt = workspace_path / "pairs.txt"
        pairs_txt.write_text("\n".join(f"{a} {b}" for a, b in colmap_image_pairs) + "\n")
        pycolmap.verify_matches(str(database_path), str(pairs_txt))

    return database_path


# ---------------------------------------------------------------------------
# 2. SfM (classical mapper, seeded with MASt3R matches)
# ---------------------------------------------------------------------------

def run_sfm(database_path: Path, image_dir: Path, recon_path: Path, config: dict) -> tuple[Path, pycolmap.Reconstruction, dict]:
    recon_path.mkdir(parents=True, exist_ok=True)
    mapper = config["mapper"]["type"]
    if mapper == "glomap":
        glomap_bin = config["mapper"]["glomap_bin"]
        if shutil.which(glomap_bin) is None:
            raise RuntimeError(
                f"mapper.type is 'glomap' but '{glomap_bin}' isn't on PATH. "
                "Install GLOMAP or switch mapper.type to 'incremental' in config/mast3r_sfm.yaml."
            )
        glomap_run_mapper(glomap_bin, str(database_path), str(recon_path), str(image_dir))
    elif mapper == "incremental":
        pycolmap.incremental_mapping(
            database_path=str(database_path),
            image_path=str(image_dir),
            output_path=str(recon_path),
            options=pycolmap.IncrementalPipelineOptions({"multiple_models": False, "extract_colors": True}),
        )
    else:
        raise ValueError(f"Unknown mapper.type: {mapper}")

    model_path = recon_path / "0"
    if not model_path.exists():
        raise RuntimeError("SfM mapping produced no reconstruction - check matches/overlap.")

    reconstruction = pycolmap.Reconstruction(str(model_path))
    stats = {
        "registered_images": reconstruction.num_reg_images(),
        "points3D": reconstruction.num_points3D(),
        "observations": reconstruction.compute_num_observations(),
        "mean_track_length": reconstruction.compute_mean_track_length(),
        "mean_reprojection_error": reconstruction.compute_mean_reprojection_error(),
    }
    return model_path, reconstruction, stats


# ---------------------------------------------------------------------------
# 3. CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("object_id", help="Key under `objects:` in config/objects.yaml")
    parser.add_argument("--config", default="config/mast3r_sfm.yaml")
    parser.add_argument("--objects-config", default="config/objects.yaml")
    parser.add_argument("--experiments-config", default="config/experiments.yaml")
    parser.add_argument("--num-images", type=int, default=None, help="overrides image_selection.num_images")
    parser.add_argument("--selection-method", choices=["even", "random"], default=None)
    parser.add_argument("--device", default=None, help="overrides model.device (auto|cpu|cuda|mps)")
    parser.add_argument(
        "--weights", default=None,
        help="overrides model.weights - a local .pth path or a HuggingFace hub id "
        "(e.g. naver/MASt3R_ViTLarge_BaseDecoder_512_catmlpdpt_metric)",
    )
    args = parser.parse_args()

    config = yaml.safe_load(resolve_path(args.config).read_text())
    objects = yaml.safe_load(resolve_path(args.objects_config).read_text())["objects"]
    if args.object_id not in objects:
        raise SystemExit(f"Unknown object_id '{args.object_id}'. Known: {sorted(objects)}")

    device = resolve_device(args.device or config["model"]["device"])
    if device != "cuda":
        raise SystemExit(
            f"Resolved device is '{device}', but MASt3R's own matching code "
            "(mast3r.colmap.mapping.run_mast3r_matching, via get_im_matches) hardcodes "
            "device='cuda' for nearest-neighbor matching, independent of the model's "
            "device. Run this script on a CUDA machine (e.g. the same GPU pod used for "
            "run_colmap_experiment.py)."
        )
    num_images = args.num_images or config["image_selection"]["num_images"]
    selection_method = args.selection_method or config["image_selection"]["method"]

    image_dir_rel = f"{objects[args.object_id]['images_dir']}/jpg"
    image_dir = resolve_path(image_dir_rel)

    experiments_path = resolve_path(args.experiments_config)
    exp_id = next_experiment_id(experiments_path)
    output_dir_rel = f"outputs/{exp_id}_mast3r_sfm_{args.object_id}"
    output_dir = resolve_path(output_dir_rel)
    output_dir.mkdir(parents=True, exist_ok=True)

    all_images = list_images(image_dir)
    print(f"[{exp_id}] {len(all_images)} images found in {image_dir}")
    selected = select_image_subset(all_images, num_images, selection_method, config["image_selection"]["seed"])
    subset_dir = copy_image_subset(selected, output_dir / "images")
    image_names = [p.name for p in selected]
    print(f"[{exp_id}] Selected {len(selected)} images ({selection_method}) -> {subset_dir} (device={device})")

    print(f"[{exp_id}] Loading MASt3R model...")
    weights_setting = args.weights or config["model"]["weights"]
    # a local .pth path is resolved relative to the repo; anything else (e.g.
    # "naver/MASt3R_...") is passed through as a HuggingFace hub id
    weights = str(resolve_path(weights_setting)) if weights_setting.endswith(".pth") else weights_setting
    model = AsymmetricMASt3R.from_pretrained(weights).to(device)

    print(f"[{exp_id}] Running MASt3R matching -> COLMAP database...")
    database_path = build_colmap_database(model, device, subset_dir, image_names, output_dir, config)

    print(f"[{exp_id}] Running SfM ({config['mapper']['type']})...")
    sparse_path = output_dir / "sparse"
    model_path, reconstruction, sfm_stats = run_sfm(database_path, subset_dir, sparse_path, config)
    print(
        f"[{exp_id}] SfM done: {sfm_stats['registered_images']}/{len(selected)} images registered, "
        f"{sfm_stats['points3D']} points, mean reprojection error "
        f"{sfm_stats['mean_reprojection_error']:.3f}px"
    )

    ply_path = output_dir / f"{exp_id}_mast3r_sfm_{args.object_id}.ply"
    reconstruction.export_PLY(str(ply_path))
    print(f"[{exp_id}] Exported point cloud -> {ply_path}")

    log_lines = [
        f"Registered images: {sfm_stats['registered_images']}/{len(selected)}",
        f"Points in reconstruction: {sfm_stats['points3D']}",
        f"Observations: {sfm_stats['observations']}",
        f"Mean track length: {sfm_stats['mean_track_length']:.6f}",
        f"Mean reprojection error: {sfm_stats['mean_reprojection_error']:.6f}px",
        f"Point cloud: {ply_path.relative_to(resolve_path('.'))}",
    ]

    entry = format_experiment_entry(
        exp_id=exp_id,
        object_id=args.object_id,
        method="mast3r_sfm",
        image_dir_rel=image_dir_rel,
        output_dir_rel=output_dir_rel,
        total_images=len(selected),
        selection_method=selection_method,
        parameters={
            "device": device,
            "image_size": config["model"]["image_size"],
            "scenegraph": config["matching"]["scenegraph"],
            "shared_intrinsics": config["matching"]["shared_intrinsics"],
            "dense_matching": config["matching"]["dense_matching"],
            "subsample": config["matching"]["subsample"],
            "conf_thr": config["matching"]["conf_thr"],
            "mapper": config["mapper"]["type"],
        },
        log_lines=log_lines,
    )
    append_experiment_entry(experiments_path, entry)
    print(f"[{exp_id}] Logged experiment to {experiments_path}")


if __name__ == "__main__":
    main()
