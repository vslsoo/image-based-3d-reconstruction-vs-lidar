"""Run one MASt3R Global Alignment ("MASt3R-SfM", arXiv:2409.19152) experiment:
pick a diverse image subset, run MASt3R matching + sparse global alignment
(all camera poses and 3D points optimized jointly via gradient descent on
GPU - not COLMAP-style incremental bundle adjustment), and export the
resulting dense point cloud - saving everything under outputs/ and logging
the run to config/experiments.yaml.

This is the same underlying algorithm as exp_004 (originally run via
mast3r/demo.py's gradio interface) - scripted here instead of clicked
through, calling mast3r.cloud_opt.sparse_ga.sparse_global_alignment()
directly (the same function demo.py's get_reconstructed_scene calls).

Unlike run_mast3r_sfm_experiment.py (MASt3R matching feeding COLMAP's
classical incremental SfM, which scales poorly with MASt3R's high match
density - see exp_011's ~2h33m at 53 images), this pipeline optimizes
everything jointly instead of image-by-image, so it doesn't have that
bottleneck. Density comes directly from MASt3R's own per-pixel depth
predictions (scene.get_dense_pts3d()) - no separate MVS stage, and no
COLMAP/COLMAP database involved anywhere in this script.

Runs on CPU or GPU: sparse_global_alignment() properly respects its device
argument (no hardcoded 'cuda' the way run_mast3r_sfm_experiment.py's
matching step has), so unlike that script this one doesn't require CUDA -
just much slower on CPU (exp_004: ~40 min for 12 images on CPU).

Usage:
    python src/reconstruction/run_mast3r_ga_experiment.py bollard_001
    python src/reconstruction/run_mast3r_ga_experiment.py bollard_001 --num-images 20 --device cpu
"""

from __future__ import annotations

import argparse
import os

os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

import sys
from pathlib import Path

import numpy as np
import open3d as o3d
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

from mast3r.cloud_opt.sparse_ga import sparse_global_alignment  # noqa: E402
from mast3r.image_pairs import make_pairs  # noqa: E402
from mast3r.model import AsymmetricMASt3R  # noqa: E402
import mast3r.utils.path_to_dust3r  # noqa: E402,F401 (adds dust3r's own deps to sys.path)
from dust3r.utils.device import to_numpy  # noqa: E402
from dust3r.utils.image import load_images  # noqa: E402


def resolve_device(device_setting: str) -> str:
    if device_setting != "auto":
        return device_setting
    return "cuda" if torch.cuda.is_available() else "cpu"


# ---------------------------------------------------------------------------
# 1. MASt3R matching + sparse global alignment
# ---------------------------------------------------------------------------

def run_sparse_global_alignment(model, device: str, image_paths: list[str], cache_dir: Path, config: dict):
    imgs = load_images(image_paths, size=config["model"]["image_size"], verbose=False)
    pairs = make_pairs(imgs, scene_graph=config["matching"]["scenegraph"], prefilter=None, symmetrize=True)
    cache_dir.mkdir(parents=True, exist_ok=True)

    scene = sparse_global_alignment(
        image_paths, pairs, str(cache_dir), model,
        subsample=config["matching"]["subsample"],
        device=device,
        shared_intrinsics=config["matching"]["shared_intrinsics"],
        matching_conf_thr=config["matching"]["matching_conf_thr"],
        lr1=config["optimization"]["lr1"], niter1=config["optimization"]["niter1"],
        lr2=config["optimization"]["lr2"], niter2=config["optimization"]["niter2"],
        opt_depth=config["optimization"]["opt_depth"],
    )
    return scene


# ---------------------------------------------------------------------------
# 2. Export the dense point cloud (mirrors demo.py's as_pointcloud branch,
#    directly to PLY via Open3D instead of trimesh/GLB)
# ---------------------------------------------------------------------------

def export_dense_point_cloud(scene, min_conf_thr: float, clean_depth: bool, ply_path: Path) -> dict:
    pts3d, _, confs = scene.get_dense_pts3d(clean_depth=clean_depth)
    imgs = to_numpy(scene.imgs)
    pts3d = to_numpy(pts3d)
    mask = to_numpy([c > min_conf_thr for c in confs])

    points = np.concatenate([p[m.ravel()] for p, m in zip(pts3d, mask)]).reshape(-1, 3)
    colors = np.concatenate([im[m] for im, m in zip(imgs, mask)]).reshape(-1, 3)
    valid = np.isfinite(points.sum(axis=1))
    points, colors = points[valid], np.clip(colors[valid], 0.0, 1.0)

    pcd = o3d.geometry.PointCloud()
    pcd.points = o3d.utility.Vector3dVector(points.astype(np.float64))
    pcd.colors = o3d.utility.Vector3dVector(colors.astype(np.float64))
    ply_path.parent.mkdir(parents=True, exist_ok=True)
    o3d.io.write_point_cloud(str(ply_path), pcd)

    return {"points": len(points)}


# ---------------------------------------------------------------------------
# 3. CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("object_id", help="Key under `objects:` in config/objects.yaml")
    parser.add_argument("--config", default="config/mast3r_ga.yaml")
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
    num_images = args.num_images or config["image_selection"]["num_images"]
    selection_method = args.selection_method or config["image_selection"]["method"]

    image_dir_rel = f"{objects[args.object_id]['images_dir']}/jpg"
    image_dir = resolve_path(image_dir_rel)

    experiments_path = resolve_path(args.experiments_config)
    exp_id = next_experiment_id(experiments_path)
    output_dir_rel = f"outputs/{exp_id}_mast3r_ga_{args.object_id}"
    output_dir = resolve_path(output_dir_rel)
    output_dir.mkdir(parents=True, exist_ok=True)

    all_images = list_images(image_dir)
    print(f"[{exp_id}] {len(all_images)} images found in {image_dir}")
    selected = select_image_subset(all_images, num_images, selection_method, config["image_selection"]["seed"])
    subset_dir = copy_image_subset(selected, output_dir / "images")
    image_paths = [str(subset_dir / p.name) for p in selected]
    print(f"[{exp_id}] Selected {len(selected)} images ({selection_method}) -> {subset_dir} (device={device})")

    print(f"[{exp_id}] Loading MASt3R model...")
    weights_setting = args.weights or config["model"]["weights"]
    weights = str(resolve_path(weights_setting)) if weights_setting.endswith(".pth") else weights_setting
    model = AsymmetricMASt3R.from_pretrained(weights).to(device)

    print(f"[{exp_id}] Running MASt3R matching + sparse global alignment...")
    cache_dir = output_dir / "cache"
    scene = run_sparse_global_alignment(model, device, image_paths, cache_dir, config)

    ply_path = output_dir / f"{exp_id}_mast3r_ga_{args.object_id}.ply"
    export_stats = export_dense_point_cloud(
        scene, config["export"]["min_conf_thr"], config["export"]["clean_depth"], ply_path,
    )
    print(f"[{exp_id}] Done: {export_stats['points']} points -> {ply_path}")

    log_lines = [
        f"Registered images: {len(selected)}/{len(selected)}",
        f"Points in dense point cloud: {export_stats['points']}",
        f"Point cloud: {ply_path.relative_to(resolve_path('.'))}",
    ]

    entry = format_experiment_entry(
        exp_id=exp_id,
        object_id=args.object_id,
        method="mast3r_ga",
        image_dir_rel=image_dir_rel,
        output_dir_rel=output_dir_rel,
        total_images=len(selected),
        selection_method=selection_method,
        parameters={
            "device": device,
            "image_size": config["model"]["image_size"],
            "scenegraph": config["matching"]["scenegraph"],
            "shared_intrinsics": config["matching"]["shared_intrinsics"],
            "matching_conf_thr": config["matching"]["matching_conf_thr"],
            "lr1": config["optimization"]["lr1"],
            "niter1": config["optimization"]["niter1"],
            "lr2": config["optimization"]["lr2"],
            "niter2": config["optimization"]["niter2"],
            "opt_depth": config["optimization"]["opt_depth"],
            "min_conf_thr": config["export"]["min_conf_thr"],
        },
        log_lines=log_lines,
    )
    append_experiment_entry(experiments_path, entry)
    print(f"[{exp_id}] Logged experiment to {experiments_path}")


if __name__ == "__main__":
    main()
