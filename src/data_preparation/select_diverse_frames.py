"""Pick a diverse (well spread-out) subset of images from a folder and save
them to a new directory.

This is the same selection logic the reconstruction scripts
(run_colmap_experiment.py, run_mast3r_sfm_experiment.py,
run_hloc_colmap_experiment.py) already use internally - exposed here as its
own step so you can inspect the chosen images (e.g. from
extract_video_frames.py's candidate pool) before running an expensive
reconstruction.

Usage:
    python src/data_preparation/select_diverse_frames.py \\
        data/raw/chair_001/images/jpg data/raw/chair_001/images/selected --num-images 15
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "reconstruction"))

from common import copy_image_subset, list_images, resolve_path, select_image_subset  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("image_dir", help="folder of candidate images (e.g. extract_video_frames.py's output)")
    parser.add_argument("output_dir", help="where to save the selected subset")
    parser.add_argument("--num-images", type=int, default=15)
    parser.add_argument("--method", choices=["even", "random"], default="even")
    parser.add_argument("--seed", type=int, default=42, help="only used when --method random")
    args = parser.parse_args()

    image_dir = resolve_path(args.image_dir)
    output_dir = resolve_path(args.output_dir)

    images = list_images(image_dir)
    print(f"{len(images)} images found in {image_dir}")
    selected = select_image_subset(images, args.num_images, args.method, args.seed)
    copy_image_subset(selected, output_dir)

    print(f"Selected {len(selected)} images ({args.method}) -> {output_dir}")
    for path in selected:
        print(" ", path.name)


if __name__ == "__main__":
    main()
