"""Shared helpers for the reconstruction experiment scripts (COLMAP, MASt3R+SfM, ...):
picking a diverse image subset and logging a finished run to config/experiments.yaml.
"""

from __future__ import annotations

import random
import re
from datetime import date
from pathlib import Path

import numpy as np
from PIL import ExifTags, Image

PROJECT_ROOT = Path(__file__).resolve().parents[2]
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png"}
EXIF_DATETIME_TAG = next(
    tag for tag, name in ExifTags.TAGS.items() if name == "DateTimeOriginal"
)


def resolve_path(path_str: str) -> Path:
    path = Path(path_str)
    return path if path.is_absolute() else (PROJECT_ROOT / path).resolve()


# ---------------------------------------------------------------------------
# Image subset selection
# ---------------------------------------------------------------------------

def _capture_order_key(image_path: Path):
    try:
        with Image.open(image_path) as img:
            timestamp = img.getexif().get(EXIF_DATETIME_TAG)
        if timestamp:
            return timestamp
    except Exception:
        pass
    return image_path.name


def list_images(image_dir: Path) -> list[Path]:
    images = [p for p in image_dir.iterdir() if p.suffix.lower() in IMAGE_EXTENSIONS]
    return sorted(images, key=_capture_order_key)


def select_image_subset(
    images: list[Path],
    num_images: int,
    method: str = "even",
    seed: int = 42,
) -> list[Path]:
    """Pick `num_images` images that cover different viewpoints.

    `images` must already be ordered by capture time / viewing angle
    (see list_images). "even" then samples spread-out indices across that
    order; "random" samples uniformly at random but keeps capture order in
    the output so downstream sequential matching still sees neighbors.
    """
    if len(images) <= num_images:
        return images
    if method == "even":
        indices = sorted({int(round(i)) for i in np.linspace(0, len(images) - 1, num_images)})
        return [images[i] for i in indices]
    if method == "random":
        indices = sorted(random.Random(seed).sample(range(len(images)), num_images))
        return [images[i] for i in indices]
    raise ValueError(f"Unknown selection method: {method}")


def copy_image_subset(images: list[Path], destination: Path) -> Path:
    destination.mkdir(parents=True, exist_ok=True)
    for image_path in images:
        (destination / image_path.name).write_bytes(image_path.read_bytes())
    return destination


# ---------------------------------------------------------------------------
# Experiment logging (config/experiments.yaml)
# ---------------------------------------------------------------------------

def next_experiment_id(experiments_path: Path) -> str:
    text = experiments_path.read_text() if experiments_path.exists() else ""
    ids = [int(m) for m in re.findall(r"exp_(\d+):", text)]
    return f"exp_{max(ids, default=0) + 1:03d}"


def format_experiment_entry(
    exp_id: str,
    object_id: str,
    method: str,
    image_dir_rel: str,
    output_dir_rel: str,
    total_images: int,
    selection_method: str,
    parameters: dict,
    log_lines: list[str],
) -> str:
    lines = [
        f"  {exp_id}:",
        f"    date: {date.today().isoformat()}",
        f"    object_id: {object_id}",
        f"    method: {method}",
        f"    image_subset: {total_images} selected ({selection_method})",
        f"    image_dir: {image_dir_rel}",
        f"    output_dir: {output_dir_rel}",
        "    parameters:",
    ]
    for key, value in parameters.items():
        if isinstance(value, bool):
            value = str(value).lower()
        lines.append(f"      {key}: {value}")
    lines.append("    log:")
    for line in log_lines:
        lines.append(f"      - {line}")
    return "\n".join(lines) + "\n"


def append_experiment_entry(experiments_path: Path, entry: str) -> None:
    with experiments_path.open("a") as f:
        f.write("\n" + entry)
