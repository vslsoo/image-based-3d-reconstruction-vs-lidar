"""Extract candidate photogrammetry frames from a short walk-around video,
instead of requiring dozens of individually-taken photos.

Motivation: the diploma's field use case has limited time on-site, so it's
faster to shoot ~30s of video once than to carefully take ~40 photos with
distinct angles. This picks good frames out of that video automatically.

Pipeline: walk through every video frame with its timestamp -> within each
non-overlapping time window, keep only the sharpest frame (Laplacian
variance - a standard motion-blur detector: blurry frames have less
high-frequency edge content) -> save survivors as sequential JPGs.

The output is just a folder of JPGs, so it drops straight into the existing
pipeline as image_dir - the reconstruction scripts (run_colmap_experiment.py,
run_mast3r_sfm_experiment.py, run_hloc_colmap_experiment.py) already pick a
diverse subset from whatever pool of images they're given, the same way they
do for individually-taken photos.

Usage:
    python src/data_preparation/extract_video_frames.py video.mov data/raw/bollard_002/images/jpg
    python src/data_preparation/extract_video_frames.py video.mov data/raw/bollard_002/images/jpg --window-seconds 0.5
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterator

import cv2
import numpy as np


def sharpness_score(frame: np.ndarray) -> float:
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    return cv2.Laplacian(gray, cv2.CV_64F).var()


def iter_frames_with_timestamps(video_path: Path) -> Iterator[tuple[float, np.ndarray]]:
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise IOError(f"Could not open video: {video_path}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    frame_idx = 0
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            yield frame_idx / fps, frame
            frame_idx += 1
    finally:
        cap.release()


def select_sharpest_per_window(
    frames: Iterator[tuple[float, np.ndarray]], window_seconds: float
) -> list[tuple[float, np.ndarray]]:
    """Within each non-overlapping time window, keep only the sharpest frame -
    discards motion-blurred frames while still covering the whole video evenly."""
    selected = []
    window_start = None
    window_frames = []
    for timestamp, frame in frames:
        if window_start is None:
            window_start = timestamp
        if timestamp - window_start >= window_seconds and window_frames:
            selected.append(max(window_frames, key=lambda tf: sharpness_score(tf[1])))
            window_frames = []
            window_start = timestamp
        window_frames.append((timestamp, frame))
    if window_frames:
        selected.append(max(window_frames, key=lambda tf: sharpness_score(tf[1])))
    return selected


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("video", help="path to the input video (e.g. .mov, .mp4)")
    parser.add_argument("output_dir", help="directory to save the extracted frames as JPGs")
    parser.add_argument(
        "--window-seconds", type=float, default=1.0,
        help="keep only the sharpest frame within each window of this length (default: 1.0s, "
        "so a 30s video yields ~30 candidate frames)",
    )
    parser.add_argument("--quality", type=int, default=95, help="JPG quality from 1 to 100 (default: 95)")
    args = parser.parse_args()

    video_path = Path(args.video)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Reading {video_path}...")
    selected = select_sharpest_per_window(iter_frames_with_timestamps(video_path), args.window_seconds)
    print(f"Kept {len(selected)} frames (sharpest per {args.window_seconds}s window)")

    for i, (timestamp, frame) in enumerate(selected):
        out_path = output_dir / f"frame_{i:04d}.jpg"
        cv2.imwrite(str(out_path), frame, [cv2.IMWRITE_JPEG_QUALITY, args.quality])

    print(f"Saved {len(selected)} frames -> {output_dir}")
    print(
        "Ready to use as image_dir for the reconstruction scripts - they'll pick a diverse "
        "subset from this pool the same way as for individually-taken photos."
    )


if __name__ == "__main__":
    main()
