"""Structured, machine-readable per-experiment metrics: stage timing, peak
CPU/GPU memory, and reproducibility metadata - written as one JSON line per
run to docs/tables/experiment_metrics.jsonl, alongside the existing
human-readable config/experiments.yaml entry that common.py already writes.

Used by all five run_*_experiment.py scripts via RunTimer (stage timing),
GPUMemorySampler (peak VRAM, GPU-wide so it also sees pycolmap's CUDA usage,
not just torch's), peak_rss_mib (peak CPU RAM), and write_metrics_row.
"""

from __future__ import annotations

import json
import os
import platform
import subprocess
import threading
import time
from contextlib import contextmanager
from pathlib import Path

from common import PROJECT_ROOT, resolve_path

METRICS_PATH = resolve_path("docs/tables/experiment_metrics.jsonl")


class RunTimer:
    """Wall-clock total plus named stage durations via `with timer.stage("x"): ...`.
    Durations accumulate if the same stage name is entered more than once."""

    def __init__(self):
        self._start = time.monotonic()
        self.stages: dict[str, float] = {}

    @contextmanager
    def stage(self, name: str):
        t0 = time.monotonic()
        try:
            yield
        finally:
            self.stages[name] = self.stages.get(name, 0.0) + (time.monotonic() - t0)

    @property
    def total_seconds(self) -> float:
        return time.monotonic() - self._start


class GPUMemorySampler:
    """Polls `nvidia-smi` in a background thread to track peak VRAM (MiB).
    Deliberately GPU-wide rather than torch.cuda.max_memory_allocated():
    pycolmap's dense MVS stage (patch_match_stereo/stereo_fusion) allocates
    CUDA memory outside torch's allocator, so torch's own peak-memory stats
    would silently miss it for the COLMAP/HLOC methods."""

    def __init__(self, interval: float = 0.5, gpu_index: int = 0):
        self.interval = interval
        self.gpu_index = gpu_index
        self.peak_mib = 0
        self._samples_taken = 0
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def _poll(self) -> None:
        while not self._stop.is_set():
            try:
                out = subprocess.run(
                    ["nvidia-smi", f"--id={self.gpu_index}",
                     "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
                    capture_output=True, text=True, timeout=5,
                )
                self.peak_mib = max(self.peak_mib, int(out.stdout.strip().splitlines()[0]))
                self._samples_taken += 1
            except Exception:
                pass
            self._stop.wait(self.interval)

    def start(self) -> "GPUMemorySampler":
        self._thread = threading.Thread(target=self._poll, daemon=True)
        self._thread.start()
        return self

    def stop(self) -> int | None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=self.interval * 2)
        # distinguish "never got a reading" (no nvidia-smi / no GPU) from a
        # legitimately-idle GPU that reported 0 MiB used - both look like
        # `not self.peak_mib`, but only the former should log as unknown/None
        return self.peak_mib if self._samples_taken > 0 else None


def peak_rss_mib() -> float:
    """Peak resident set size of this process (+ reaped children) so far, in
    MiB. `ru_maxrss` is already a running maximum over the process's whole
    lifetime - no sampling thread needed. Units differ by OS: KB on Linux
    (RunPod pods), bytes on macOS."""
    import resource
    self_rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    children_rss = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
    total = self_rss + children_rss
    return total / 1024 if platform.system() == "Linux" else total / (1024 * 1024)


def git_commit_hash() -> str:
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], cwd=PROJECT_ROOT,
            capture_output=True, text=True, timeout=5,
        ).stdout.strip()
        dirty = subprocess.run(
            ["git", "status", "--porcelain"], cwd=PROJECT_ROOT,
            capture_output=True, text=True, timeout=5,
        ).stdout.strip()
        return f"{commit}+dirty" if dirty else commit
    except Exception:
        return "unknown"


_DIST_NAME_ALIASES = {
    # importlib.metadata looks up by *distribution* name, which doesn't
    # always match the import name - e.g. `import pycolmap` can come from
    # either the `pycolmap` or `pycolmap-cuda12` PyPI distribution depending
    # on which one this pod installed (see project memory: pycolmap-cuda12
    # is the recommended install path).
    "pycolmap": ["pycolmap", "pycolmap-cuda12"],
}


def library_versions(names: list[str]) -> dict[str, str]:
    from importlib.metadata import PackageNotFoundError, version
    out = {}
    for name in names:
        for candidate in _DIST_NAME_ALIASES.get(name, [name]):
            try:
                out[name] = version(candidate)
                break
            except PackageNotFoundError:
                continue
        else:
            out[name] = "n/a"
    return out


def hardware_info() -> dict:
    info = {
        "cpu": platform.processor() or platform.machine(),
        "cpu_count": os.cpu_count(),
        "ram_total_gib": None,
        "gpu_name": None,
        "gpu_vram_total_mib": None,
    }
    try:
        import psutil
        info["ram_total_gib"] = round(psutil.virtual_memory().total / (1024 ** 3), 1)
    except Exception:
        pass
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=5,
        )
        name, mem = out.stdout.strip().splitlines()[0].split(", ")
        info["gpu_name"] = name
        info["gpu_vram_total_mib"] = int(mem.replace(" MiB", ""))
    except Exception:
        pass
    return info


def classify_failure(exc: BaseException) -> str:
    """Best-effort bucketing of an exception into a short reason code, so
    failed runs are still queryable/groupable in the metrics table instead
    of each carrying a unique free-text message.

    Note: a hard CUDA/cgroup OOM-kill (SIGKILL of the whole process tree -
    see the container-memory-limit gotcha in project memory) never reaches
    this handler at all, since the process dies outright with no Python
    exception. Runs killed that way leave no row here; detect them from the
    shell exit code instead (e.g. 137) if wrapping these scripts in a driver
    that logs on non-zero exit."""
    message = str(exc).lower()
    if "out of memory" in message or isinstance(exc, MemoryError):
        return "oom"
    if "no images registered" in message or "registered no images" in message:
        return "no_registration"
    if "kept no image pairs" in message or "no reconstruction" in message:
        return "no_matches"
    return f"{type(exc).__name__}: {exc}"[:300]


def build_metrics_row(
    *,
    exp_id: str,
    object_id: str,
    method: str,
    status: str,
    failure_reason: str | None,
    num_images_input: int,
    num_images_registered: int | None,
    timer: RunTimer,
    peak_ram_mib: float,
    peak_vram_mib: int | None,
    output_stats: dict,
    config_file: str,
    selection_method: str,
    seed: int,
    parameters: dict,
) -> dict:
    from datetime import date
    hw = hardware_info()
    registration_rate = (
        round(num_images_registered / num_images_input, 4)
        if num_images_registered is not None and num_images_input else None
    )
    return {
        "exp_id": exp_id,
        "date": date.today().isoformat(),
        "object_id": object_id,
        "method": method,
        "status": status,
        "failure_reason": failure_reason,
        "num_images_input": num_images_input,
        "num_images_registered": num_images_registered,
        "registration_rate": registration_rate,
        "timing": {
            "total_seconds": round(timer.total_seconds, 2),
            "stages": {k: round(v, 2) for k, v in timer.stages.items()},
        },
        "memory": {
            "peak_ram_mib": round(peak_ram_mib, 1),
            "peak_vram_mib": peak_vram_mib,
            "gpu_vram_total_mib": hw["gpu_vram_total_mib"],
        },
        "output": output_stats,
        "config": {
            "config_file": config_file,
            "num_images_requested": num_images_input,
            "selection_method": selection_method,
            "seed": seed,
            "parameters": parameters,
        },
        "reproducibility": {
            "git_commit": git_commit_hash(),
            "hardware": hw,
            "library_versions": library_versions(
                ["torch", "pycolmap", "numpy", "opencv-python", "open3d"]
            ),
        },
    }


def write_metrics_row(row: dict, path: Path = METRICS_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(json.dumps(row, default=str) + "\n")
