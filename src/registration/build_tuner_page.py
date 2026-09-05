"""Build site/tuner.html - the exploratory, single-viewer DBSCAN gap-cluster tuner covering
EVERY capture (6 total: one per physical object - the far-view-only capture per object was
dropped, keeping only the far+close-up / hand-picked-diverse capture; see build_object_page.py
for the same removal on the per-object report pages). Object tab labels show photo count +
shooting style.

This is a lighter-weight sibling of build_object_page.py: no Accuracy/Completeness/F1, no
per-method 3D panel grid - just one shared WebGL viewer, an object selector, a method
selector, and live DBSCAN recompute on the selected (object, method) pair. See
_tuner_page_template.py for the shared HTML/CSS/JS shell (extracted from the original
tuner.html).

Per (object, method): aligned cloud -> density-match onto a fixed 1 cm voxel grid ->
source->target Chamfer distance -> split into context (<=EMBED_FLOOR_CM) / candidates
(>EMBED_FLOOR_CM, what DBSCAN clusters) -> each capped and subsampled for a lightweight
embed (this is an *approximate* explorer; exact numbers live on the per-object report pages).

Usage:
    python -u src/registration/build_tuner_page.py
"""

from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

import numpy as np

# open3d is imported lazily: --relayout re-renders the page from the payload it already
# carries (a template change, e.g. the site nav) and never touches a point cloud.
o3d = None


def _load_open3d() -> None:
    global o3d
    if o3d is None:
        import open3d as _o3d
        o3d = _o3d


from _tuner_page_template import TUNER_HEAD, TUNER_TAIL
from _site_nav import NAV_CSS, nav_html

PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUT_HTML = PROJECT_ROOT / "site" / "tuner.html"

VOXEL_M = 0.01
# Voxel size used to density-match every reconstruction to the reference, in metres.
# Fixed at the 1 cm grid the LiDAR references are actually delivered on, rather than
# derived per-object from the reference's median NN-spacing. Two reasons: the delivered
# clouds are already thinned onto that grid, so the grid pitch is the real sampling
# limit; and the measured median NN-spacing sits *below* the pitch because overlapping
# scan passes leave exact-duplicate points at zero distance (bus_stop_001 reads 1.00 cm
# as delivered, 1.41 cm once duplicates are dropped). A fixed voxel also keeps the
# downsampling identical across objects and methods.

EMBED_FLOOR_CM = 1.0
# Distance above which a point is embedded as a *candidate* (the pool the far_threshold
# slider filters and DBSCAN clusters). It has to sit at or below the slider's minimum:
# points closer than this are only embedded as grey context, so a far_threshold under
# EMBED_FLOOR_CM would silently cluster nothing in the 1-5cm band. Kept at 1.0 so the
# slider can go down to 1cm.
CONTEXT_CAP = 10000
CANDIDATE_CAP = 20000
LIDAR_REF_CAP = 20000
METHOD_ORDER = ["mast3r_ga", "vggt", "colmap", "hloc_colmap"]

rng = np.random.default_rng(42)

# Per-PHYSICAL-OBJECT far_threshold/eps slider config, tuned per docs/tables/*_mini_report_*.xlsx
# (min_points isn't customized per object in this tool - always the generic 2-40/default 10
# slider, matching the original tuner's behaviour).
FT_EPS_BY_OBJECT = {
    "bus_stop": {"far_threshold": {"min": 1, "max": 20, "step": 0.5, "default": 10}, "eps": {"min": 0.5, "max": 8, "step": 0.1, "default": 3}},
    "information_sign": {"far_threshold": {"min": 1, "max": 30, "step": 0.5, "default": 5}, "eps": {"min": 0.5, "max": 10, "step": 0.1, "default": 2}},
    "bench": {"far_threshold": {"min": 1, "max": 20, "step": 0.5, "default": 5}, "eps": {"min": 0.5, "max": 8, "step": 0.1, "default": 3}},
    "bollard": {"far_threshold": {"min": 1, "max": 20, "step": 0.5, "default": 5}, "eps": {"min": 0.5, "max": 8, "step": 0.1, "default": 2}},
    "flashlight": {"far_threshold": {"min": 1, "max": 20, "step": 0.5, "default": 10}, "eps": {"min": 0.5, "max": 8, "step": 0.1, "default": 2}},
    "bus_stop_sign": {"far_threshold": {"min": 1, "max": 20, "step": 0.5, "default": 5}, "eps": {"min": 0.5, "max": 8, "step": 0.1, "default": 2}},
}

# cosmetic-only relabeling for the object-tab button text (capture ids / dict keys are untouched)
DISPLAY_NAME_OVERRIDES = {"flashlight": "lamppost"}

# (physical_object, capture_id, n_photos, style, ref_path, {method_id: (exp_id, aligned .ply)})
CAPTURES = [
    ("bus_stop", "bus_stop_002", 96, "far view + close-up (near)", "data/lidar/bus_stop_001/bus_stop_001_no_floor_centered_2.ply", {
        "mast3r_ga": ("exp_142", "outputs/registrations/exp_142_to_lidar_bus_stop_001/exp_142_mast3r_ga_bus_stop_002_scaled_aligned_to_bus_stop_001_no_floor_centered.ply"),
        "vggt": ("exp_141", "outputs/registrations/exp_141_to_lidar_bus_stop_001/exp_141_vggt_bus_stop_002_scaled_aligned_to_bus_stop_001_no_floor_centered.ply"),
        "colmap": ("exp_139", "outputs/registrations/exp_139_to_lidar_bus_stop_001/exp_139_colmap_bus_stop_002_scaled_aligned_to_bus_stop_001_no_floor_centered.ply"),
        "hloc_colmap": ("exp_140", "outputs/registrations/exp_140_to_lidar_bus_stop_001/exp_140_hloc_colmap_bus_stop_002_scaled_aligned_to_bus_stop_001_no_floor_centered.ply"),
    }),
    ("information_sign", "information_sign_002", 75, "hand-picked diverse subset", "data/lidar/information_sign_002/information_sign_002_no_floor_centered.ply", {
        "mast3r_ga": ("exp_126", "outputs/registrations/exp_126_to_lidar_information_sign_002/exp_126_mast3r_ga_is_002_test_1_manual_n75_scaled_aligned_to_information_sign_002_no_floor_centered.ply"),
        "vggt": ("exp_130", "outputs/registrations/exp_130_to_lidar_information_sign_002/exp_130_vggt_is_002_test_1_manual_n75_scaled_aligned_to_information_sign_002_no_floor_centered.ply"),
        "colmap": ("exp_111", "outputs/registrations/exp_111_to_lidar_is_n75/exp_111_colmap_is_002_test_1_manual_n75_scaled_aligned_to_information_sign_002_no_floor_centered.ply"),
        "hloc_colmap": ("exp_129", "outputs/registrations/exp_129_to_lidar_information_sign_002/exp_129_hloc_colmap_is_002_test_1_manual_n75_scaled_aligned_to_information_sign_002_no_floor_centered.ply"),
    }),
    ("bench", "bench_004", 94, "far view + close-up (near)", "data/lidar/bench_003/bench_003_no_floor_centered.ply", {
        "mast3r_ga": ("exp_134", "outputs/registrations/exp_134_to_lidar_bench_003/exp_134_mast3r_ga_bench_004_scaled_aligned_to_bench_003_no_floor_centered.ply"),
        "vggt": ("exp_133", "outputs/registrations/exp_133_to_lidar_bench_003/exp_133_vggt_bench_004_scaled_aligned_to_bench_003_no_floor_centered.ply"),
        "colmap": ("exp_131", "outputs/registrations/exp_131_to_lidar_bench_003/exp_131_colmap_bench_004_scaled_aligned_to_bench_003_no_floor_centered.ply"),
        "hloc_colmap": ("exp_132", "outputs/registrations/exp_132_to_lidar_bench_003/exp_132_hloc_colmap_bench_004_scaled_aligned_to_bench_003_no_floor_centered.ply"),
    }),
    ("bollard", "bollard_003", 69, "far view + close-up (near)", "data/lidar/bollard_003/bollard_003_no_floor_centered.ply", {
        "mast3r_ga": ("exp_146", "outputs/registrations/exp_146_to_lidar_bollard_003/exp_146_mast3r_ga_bollard_003_test_1_pool69_scaled_aligned_to_bollard_003_no_floor_centered.ply"),
        "vggt": ("exp_145", "outputs/registrations/exp_145_to_lidar_bollard_003/exp_145_vggt_bollard_003_test_1_pool69_scaled_aligned_to_bollard_003_no_floor_centered.ply"),
        "colmap": ("exp_143", "outputs/registrations/exp_143_to_lidar_bollard_003/exp_143_colmap_bollard_003_test_1_pool69_scaled_aligned_to_bollard_003_no_floor_centered.ply"),
        "hloc_colmap": ("exp_144", "outputs/registrations/exp_144_to_lidar_bollard_003/exp_144_hloc_colmap_bollard_003_test_1_pool69_scaled_aligned_to_bollard_003_no_floor_centered.ply"),
    }),
    ("flashlight", "flashlight_004", 105, "far view + close-up (near)", "data/lidar/flashlight_003/flashlight_003_no_floor_centered.ply", {
        "mast3r_ga": ("exp_150", "outputs/registrations/exp_150_to_lidar_flashlight_001/exp_150_mast3r_ga_flashlight_004_scaled_aligned_to_flashlight_001_no_floor_centered.ply"),
        "vggt": ("exp_149", "outputs/registrations/exp_149_to_lidar_flashlight_001_2/exp_149_vggt_flashlight_004_scaled_aligned_to_flashlight_001_no_floor_centered.ply"),
        "colmap": ("exp_147", "outputs/registrations/exp_147_to_lidar_flashlight_001/exp_147_colmap_flashlight_004_scaled_aligned_to_flashlight_001_no_floor_centered.ply"),
        "hloc_colmap": ("exp_148", "outputs/registrations/exp_148_to_lidar_flashlight_001/exp_148_hloc_colmap_flashlight_004_scaled_aligned_to_flashlight_001_no_floor_centered.ply"),
    }),
    ("bus_stop_sign", "bus_stop_sign_002", 79, "far view + close-up (near)", "data/lidar/bus_stop_sign_001/bus_stop_sign_001_no_floor_centered.ply", {
        "mast3r_ga": ("exp_138", "outputs/registrations/exp_138_to_lidar_bus_stop_sign_001/exp_138_mast3r_ga_bus_stop_sign_002_scaled_aligned_to_bus_stop_sign_001_no_floor_centered.ply"),
        "vggt": ("exp_137", "outputs/registrations/exp_137_to_lidar_bus_stop_sign_001/exp_137_vggt_bus_stop_sign_002_scaled_aligned_to_bus_stop_sign_001_no_floor_centered.ply"),
        "colmap": ("exp_135", "outputs/registrations/exp_135_to_lidar_bus_stop_sign_001/exp_135_colmap_bus_stop_sign_002_scaled_aligned_to_bus_stop_sign_001_no_floor_centered.ply"),
        "hloc_colmap": ("exp_136", "outputs/registrations/exp_136_to_lidar_bus_stop_sign_001/exp_136_hloc_colmap_bus_stop_sign_002_scaled_aligned_to_bus_stop_sign_001_no_floor_centered.ply"),
    }),
]


def b64f(arr) -> str:
    return base64.b64encode(np.ascontiguousarray(arr, dtype="<f4").ravel().tobytes()).decode("ascii")


def subsample(idx_count: int, cap: int) -> np.ndarray:
    if idx_count <= cap:
        return np.arange(idx_count)
    return np.sort(rng.choice(idx_count, cap, replace=False))


def load_reference(path) -> o3d.geometry.PointCloud:
    """Read a reference (LiDAR) cloud and drop exact-duplicate points before any
    metric touches it.

    The delivered clouds carry a lot of them - 10-26% of the points on these objects
    (bus_stop_001 41337 -> 31692, flashlight_003 22637 -> 16690, bollard_003 2818 ->
    2526) - left over where overlapping scan passes cover the same surface twice, at
    byte-identical coordinates. They are not extra information, but they do skew the
    metrics: completeness is averaged over target points, so a duplicated point is
    counted as many times as it appears, quietly weighting the score toward whatever
    the scanner happened to pass twice. Distances themselves are unaffected (a
    duplicate is its own nearest neighbour), so this only removes the double-counting.
    """
    pcd = o3d.io.read_point_cloud(str(path))
    pts = np.asarray(pcd.points)
    _, first_idx = np.unique(pts, axis=0, return_index=True)
    if len(first_idx) < len(pts):
        # select_by_index (rather than rebuilding from the array) so colors/normals survive
        pcd = pcd.select_by_index(np.sort(first_idx).tolist())
        print(f"       deduplicated reference: {len(pts)} -> {len(first_idx)} points "
              f"({100 * (1 - len(first_idx) / len(pts)):.1f}% exact duplicates removed)", flush=True)
    return pcd


def wrap_html(payload: str) -> str:
    head = TUNER_HEAD.replace("__NAV_CSS__", NAV_CSS).replace("__SITE_NAV__", nav_html("tuner"))
    return head + f'\n<script type="application/json" id="tuner-data">{payload}</script>\n' + TUNER_TAIL


def relayout() -> None:
    """Re-render site/tuner.html from the payload already embedded in it - template-only
    changes (the site nav, a reworded caption) do not need the clouds recomputed."""
    import re

    html = OUT_HTML.read_text(encoding="utf-8")
    m = re.search(r'<script type="application/json" id="tuner-data">(.*?)</script>', html, re.S)
    if not m:
        sys.exit(f"no embedded payload in {OUT_HTML} - run a full rebuild instead")
    OUT_HTML.write_text(wrap_html(m.group(1)), encoding="utf-8")
    print(f"Re-rendered {OUT_HTML.relative_to(PROJECT_ROOT)} from its existing payload "
          f"({OUT_HTML.stat().st_size / (1024 * 1024):.2f} MB)")


def main() -> None:
    _load_open3d()
    ref_cache: dict[str, tuple] = {}  # ref_path -> (o3d pcd, capped_ref_pos_b64)
    data: dict[str, dict] = {}

    for phys_obj, cap_id, n_photos, style, ref_rel, methods in CAPTURES:
        ref_path = PROJECT_ROOT / ref_rel
        if ref_rel not in ref_cache:
            print(f"[ref] {ref_path.name}", flush=True)
            ref = load_reference(ref_path)
            rpts = np.asarray(ref.points)
            ref_sel = rpts[subsample(len(rpts), LIDAR_REF_CAP)]
            ref_cache[ref_rel] = (ref, b64f(ref_sel))
        ref, ref_pos_b64 = ref_cache[ref_rel]

        ft_eps = FT_EPS_BY_OBJECT[phys_obj]
        disp_prefix = DISPLAY_NAME_OVERRIDES.get(phys_obj)
        disp_cap_id = cap_id.replace(phys_obj, disp_prefix, 1) if disp_prefix else cap_id
        entry = {
            "label": f"{disp_cap_id} — {n_photos} photos, {style}",
            "far_threshold": ft_eps["far_threshold"],
            "eps": ft_eps["eps"],
            "methods": {"lidar_ref_pos": ref_pos_b64},
        }

        for method_id in METHOD_ORDER:
            exp_id, rel = methods[method_id]
            src_path = PROJECT_ROOT / rel
            print(f"  [{cap_id}/{method_id}] {exp_id} <- {src_path.name}", flush=True)
            src = o3d.io.read_point_cloud(str(src_path))
            matched = src.voxel_down_sample(VOXEL_M)
            mpts = np.asarray(matched.points)
            n_total = len(mpts)
            d_cm = np.asarray(matched.compute_point_cloud_distance(ref)) * 100.0

            ctx_mask = d_cm <= EMBED_FLOOR_CM
            cand_mask = ~ctx_mask
            ctx_idx = np.where(ctx_mask)[0]
            cand_idx = np.where(cand_mask)[0]
            n_candidates_true = int(cand_idx.size)

            ctx_sel = ctx_idx[subsample(len(ctx_idx), CONTEXT_CAP)]
            cand_sel = cand_idx[subsample(len(cand_idx), CANDIDATE_CAP)]

            entry["methods"][method_id] = {
                "label": f"{exp_id} {method_id}",
                "n_total": n_total,
                "embed_floor_cm": EMBED_FLOOR_CM,
                "n_candidates_true": n_candidates_true,
                "n_candidates_embedded": int(cand_sel.size),
                "is_approx": bool(cand_sel.size < n_candidates_true),
                "candidate_pos": b64f(mpts[cand_sel]),
                "candidate_dist_cm": b64f(d_cm[cand_sel]),  # cm - compared directly against the ft slider (also cm) in recompute()
                "context_pos": b64f(mpts[ctx_sel]),
            }

        data[cap_id] = entry

    payload = json.dumps(data).replace("</", "<\\/")
    html = wrap_html(payload)

    OUT_HTML.write_text(html, encoding="utf-8")
    size_mb = OUT_HTML.stat().st_size / (1024 * 1024)
    print(f"\nWrote {OUT_HTML.relative_to(PROJECT_ROOT)} ({size_mb:.2f} MB)", flush=True)


if __name__ == "__main__":
    if "--relayout" in sys.argv[1:]:
        sys.exit(relayout())
    main()
