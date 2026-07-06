"""Run one VGGT (Visual Geometry Grounded Transformer, arXiv:2503.11651)
experiment: pick a diverse image subset, run a single feed-forward VGGT pass
over all of them at once, and export the resulting dense point cloud -
saving everything under outputs/ and logging the run to
config/experiments.yaml.

Unlike every other method in this repo - including MASt3R's global alignment
(run_mast3r_ga_experiment.py), which still runs a gradient-descent
optimization loop over camera poses/points after its forward pass - VGGT
predicts camera poses, depth maps, per-pixel confidence, and dense
per-pixel world-space point maps directly from a single transformer forward
pass over the whole image set. No COLMAP, no iterative optimization, no
separate MVS stage anywhere in this script.

Uses facebookresearch/vggt (vendored under external/vggt, custom
non-commercial research license - see external/vggt/LICENSE.txt). Runs on
CPU or GPU; bfloat16/float16 autocast (matching VGGT's own demo scripts)
only kicks in on CUDA.

Usage:
    python src/reconstruction/run_vggt_experiment.py bollard_001
    python src/reconstruction/run_vggt_experiment.py bollard_001 --num-images 20 --device cpu
"""

from __future__ import annotations

import argparse
import os

os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

import sys
from contextlib import nullcontext
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

VGGT_ROOT = resolve_path("external/vggt")
sys.path.insert(0, str(VGGT_ROOT))

from vggt.models.vggt import VGGT  # noqa: E402
from vggt.utils.geometry import unproject_depth_map_to_point_map  # noqa: E402
from vggt.utils.load_fn import load_and_preprocess_images  # noqa: E402
from vggt.utils.pose_enc import pose_encoding_to_extri_intri  # noqa: E402


def resolve_device(device_setting: str) -> str:
    if device_setting != "auto":
        return device_setting
    return "cuda" if torch.cuda.is_available() else "cpu"


def resolve_dtype(device: str) -> torch.dtype:
    if device != "cuda":
        return torch.float32
    return torch.bfloat16 if torch.cuda.get_device_capability()[0] >= 8 else torch.float16


# ---------------------------------------------------------------------------
# 1. VGGT feed-forward inference
# ---------------------------------------------------------------------------

def run_vggt_inference(model, device: str, dtype: torch.dtype, image_paths: list[str], config: dict) -> dict:
    images = load_and_preprocess_images(image_paths, mode=config["model"]["image_mode"]).to(device)

    autocast_ctx = torch.cuda.amp.autocast(dtype=dtype) if device == "cuda" else nullcontext()
    with torch.no_grad(), autocast_ctx:
        predictions = model(images)

    predictions["extrinsic"], predictions["intrinsic"] = pose_encoding_to_extri_intri(
        predictions["pose_enc"], images.shape[-2:]
    )

    for key, value in predictions.items():
        if isinstance(value, torch.Tensor):
            predictions[key] = value.cpu().numpy().squeeze(0)  # drop the batch dim (S, ...)

    return predictions


# ---------------------------------------------------------------------------
# 2. Export the dense point cloud
# ---------------------------------------------------------------------------

def export_dense_point_cloud(predictions: dict, config: dict, ply_path: Path) -> dict:
    if config["export"]["use_point_map"]:
        world_points = predictions["world_points"]
        conf = predictions["world_points_conf"]
    else:
        world_points = unproject_depth_map_to_point_map(
            predictions["depth"], predictions["extrinsic"], predictions["intrinsic"]
        )
        conf = predictions["depth_conf"]

    images = predictions["images"].transpose(0, 2, 3, 1)  # (S, 3, H, W) -> (S, H, W, 3), values in [0, 1]

    points = world_points.reshape(-1, 3)
    colors = images.reshape(-1, 3)
    conf_flat = conf.reshape(-1)

    threshold = np.percentile(conf_flat, config["export"]["conf_percentile"])
    mask = (conf_flat >= threshold) & (conf_flat > 1e-5)
    points, colors = points[mask], colors[mask]

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
    parser.add_argument("--config", default="config/vggt.yaml")
    parser.add_argument("--objects-config", default="config/objects.yaml")
    parser.add_argument("--experiments-config", default="config/experiments.yaml")
    parser.add_argument("--num-images", type=int, default=None, help="overrides image_selection.num_images")
    parser.add_argument("--selection-method", choices=["even", "random"], default=None)
    parser.add_argument("--device", default=None, help="overrides model.device (auto|cpu|cuda|mps)")
    parser.add_argument(
        "--weights", default=None,
        help="overrides model.weights - a HuggingFace hub id (e.g. facebook/VGGT-1B)",
    )
    args = parser.parse_args()

    config = yaml.safe_load(resolve_path(args.config).read_text())
    objects = yaml.safe_load(resolve_path(args.objects_config).read_text())["objects"]
    if args.object_id not in objects:
        raise SystemExit(f"Unknown object_id '{args.object_id}'. Known: {sorted(objects)}")

    device = resolve_device(args.device or config["model"]["device"])
    dtype = resolve_dtype(device)
    num_images = args.num_images or config["image_selection"]["num_images"]
    selection_method = args.selection_method or config["image_selection"]["method"]

    image_dir_rel = f"{objects[args.object_id]['images_dir']}/jpg"
    image_dir = resolve_path(image_dir_rel)

    experiments_path = resolve_path(args.experiments_config)
    exp_id = next_experiment_id(experiments_path)
    output_dir_rel = f"outputs/{exp_id}_vggt_{args.object_id}"
    output_dir = resolve_path(output_dir_rel)
    output_dir.mkdir(parents=True, exist_ok=True)

    all_images = list_images(image_dir)
    print(f"[{exp_id}] {len(all_images)} images found in {image_dir}")
    selected = select_image_subset(all_images, num_images, selection_method, config["image_selection"]["seed"])
    subset_dir = copy_image_subset(selected, output_dir / "images")
    image_paths = [str(subset_dir / p.name) for p in selected]
    print(f"[{exp_id}] Selected {len(selected)} images ({selection_method}) -> {subset_dir} (device={device}, dtype={dtype})")

    print(f"[{exp_id}] Loading VGGT model...")
    weights = args.weights or config["model"]["weights"]
    model = VGGT.from_pretrained(weights).to(device).eval()

    print(f"[{exp_id}] Running VGGT feed-forward inference...")
    predictions = run_vggt_inference(model, device, dtype, image_paths, config)

    ply_path = output_dir / f"{exp_id}_vggt_{args.object_id}.ply"
    export_stats = export_dense_point_cloud(predictions, config, ply_path)
    print(f"[{exp_id}] Done: {export_stats['points']} points -> {ply_path}")

    log_lines = [
        f"Registered images: {len(selected)}/{len(selected)}",
        f"Points in dense point cloud: {export_stats['points']}",
        f"Point cloud: {ply_path.relative_to(resolve_path('.'))}",
    ]

    entry = format_experiment_entry(
        exp_id=exp_id,
        object_id=args.object_id,
        method="vggt",
        image_dir_rel=image_dir_rel,
        output_dir_rel=output_dir_rel,
        total_images=len(selected),
        selection_method=selection_method,
        parameters={
            "device": device,
            "dtype": str(dtype).replace("torch.", ""),
            "image_mode": config["model"]["image_mode"],
            "use_point_map": config["export"]["use_point_map"],
            "conf_percentile": config["export"]["conf_percentile"],
        },
        log_lines=log_lines,
    )
    append_experiment_entry(experiments_path, entry)
    print(f"[{exp_id}] Logged experiment to {experiments_path}")


if __name__ == "__main__":
    main()
