"""Build a merged site/<page_id>.html report - one page per PHYSICAL OBJECT, showing every
capture of it side by side (e.g. bus_stop.html = bus_stop_001 + bus_stop_002, 8 panels total:
4 methods x 2 captures), all sharing one live DBSCAN gap tuner and one LiDAR reference.

The HTML/CSS/JS shell (WebGL viewer, DBSCAN-in-JS, panel building, capture-group headers) is
100% shared - see _object_page_template.py, extracted from bus_stop_sign_001.html and later
generalized to N captures. This script only computes the embedded data blob
(part1-data) from the aligned point clouds and slots them + a few per-object text bits into
that shell.

Pipeline per (capture, method) panel (mirrors build_capture_comparison_page.py exactly, so
numbers are comparable across pages): aligned cloud -> density-match onto a fixed
1 cm voxel grid (VOXEL_M, the pitch the LiDAR references are delivered on)
-> source<->target Chamfer distances -> split accuracy pool into
below-floor (<=FLOOR_CM, trivially "good") / candidate (>FLOOR_CM, DBSCAN decides gap vs
outlier) -> embed raw distance+position pools (capped at EMBED_CAP each, subsampled if larger)
so the browser can re-run DBSCAN and recompute Accuracy/Completeness/F1 live as the tuner
sliders move.

Usage:
    python -u src/registration/build_object_page.py <page_id>

Add the page's config to MERGED_OBJECTS below first.
"""

from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

import numpy as np

from _object_page_template import HEAD_TOP2, BODY_TEMPLATE, MAIN_JS_AND_TAIL
from _site_nav import NAV_CSS, nav_html

# open3d is imported lazily - see --relayout, which re-renders a page from the payload it
# already carries and never touches a point cloud. The import alone costs ~2 min in this venv.
o3d = None


def _load_open3d() -> None:
    global o3d
    if o3d is None:
        import open3d as _o3d
        o3d = _o3d

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SITE_DIR = PROJECT_ROOT / "site"

VOXEL_M = 0.01
# Voxel size used to density-match every reconstruction to the reference, in metres.
# Fixed at the 1 cm grid the LiDAR references are actually delivered on, rather than
# derived per-object from the reference's median NN-spacing. Two reasons: the delivered
# clouds are already thinned onto that grid, so the grid pitch is the real sampling
# limit; and the measured median NN-spacing sits *below* the pitch because overlapping
# scan passes leave exact-duplicate points at zero distance (bus_stop_001 reads 1.00 cm
# as delivered, 1.41 cm once duplicates are dropped). A fixed voxel also keeps the
# downsampling identical across objects and methods.

FLOOR_CM = 5.0
EMBED_CAP = 60000
# Correspondence pipelines first, then the feed-forward models - the order the index's
# introduction, both study pages and the thesis text all use. This list drives the panel order
# on every object page, in tuner.html, and the row order of the summary workbook (and through
# it results.html), so it is the one place that order is decided.
METHOD_ORDER = ["colmap", "hloc_colmap", "mast3r_ga", "vggt"]

# Standard DBSCAN tuner slider config (ft/eps/mp), used by every page unless overridden via a
# "dbscan" key in its MERGED_OBJECTS entry (e.g. information_sign needs a much wider
# far_threshold range because its reference has a systematic 25-30cm+ coverage gradient).
DEFAULT_DBSCAN_SLIDERS = {
    "ft_min": 5, "ft_max": 20, "ft_step": 0.5, "ft_default": 10,
    "eps_min": 0.5, "eps_max": 8, "eps_step": 0.1, "eps_default": 2,
    "mp_min": 2, "mp_max": 40, "mp_default": 10,
}

rng = np.random.default_rng(42)

# --- per-page config ------------------------------------------------------------------
# ref: reference LiDAR .ply (already floor-removed + centered), shared by all captures
# captures: ordered list of {id, n_photos, style, methods: {method_id: (exp_id, aligned .ply)}}
#   - id: the capture's own object_id (e.g. "bus_stop_001") - used as its group label prefix
#   - n_photos / style: shown in the group header, e.g. "bus_stop_001 - 48 photos - full view"
# callout: optional HTML block under the subtitle (None -> omitted)
# checkbox_checked / checkbox_note: "Ignore DBSCAN" default + explanatory sentence

MERGED_OBJECTS = {
    "bus_stop": {
        "ref": "data/lidar/bus_stop_001/bus_stop_001_no_floor_centered_2.ply",
        "captures": [
            {
                "id": "bus_stop_002", "n_photos": 96, "style": "far view + close-up (near) shots",
                "methods": {
                    "mast3r_ga": ("exp_142", "outputs/registrations/exp_142_to_lidar_bus_stop_001/exp_142_mast3r_ga_bus_stop_002_scaled_aligned_to_bus_stop_001_no_floor_centered.ply"),
                    "vggt": ("exp_141", "outputs/registrations/exp_141_to_lidar_bus_stop_001/exp_141_vggt_bus_stop_002_scaled_aligned_to_bus_stop_001_no_floor_centered.ply"),
                    "colmap": ("exp_139", "outputs/registrations/exp_139_to_lidar_bus_stop_001/exp_139_colmap_bus_stop_002_scaled_aligned_to_bus_stop_001_no_floor_centered.ply"),
                    "hloc_colmap": ("exp_140", "outputs/registrations/exp_140_to_lidar_bus_stop_001/exp_140_hloc_colmap_bus_stop_002_scaled_aligned_to_bus_stop_001_no_floor_centered.ply"),
                },
            },
        ],
        "callout": None,
        "checkbox_checked": False,
        "checkbox_note": "",
        # tuned per docs/tables/bus_stop_001_mini_report_ft10_eps3_mp5.xlsx
        "dbscan": {"ft_default": 10, "eps_default": 3, "mp_default": 5},
    },
    "information_sign": {
        # Reference is incomplete (only the upper ~2/3 of the pole and one side were scanned)
        # - hence the much wider far_threshold range (real gaps run 25-30cm+ near the bottom).
        "ref": "data/lidar/information_sign_002/information_sign_002_no_floor_centered.ply",
        "captures": [
            {
                "id": "information_sign_002", "n_photos": 75, "style": "hand-picked diverse subset (information_sign_002_test_1's 128-photo pool)",
                "methods": {
                    "mast3r_ga": ("exp_126", "outputs/registrations/exp_126_to_lidar_information_sign_002/exp_126_mast3r_ga_is_002_test_1_manual_n75_scaled_aligned_to_information_sign_002_no_floor_centered.ply"),
                    "vggt": ("exp_130", "outputs/registrations/exp_130_to_lidar_information_sign_002/exp_130_vggt_is_002_test_1_manual_n75_scaled_aligned_to_information_sign_002_no_floor_centered.ply"),
                    "colmap": ("exp_111", "outputs/registrations/exp_111_to_lidar_is_n75/exp_111_colmap_is_002_test_1_manual_n75_scaled_aligned_to_information_sign_002_no_floor_centered.ply"),
                    "hloc_colmap": ("exp_129", "outputs/registrations/exp_129_to_lidar_information_sign_002/exp_129_hloc_colmap_is_002_test_1_manual_n75_scaled_aligned_to_information_sign_002_no_floor_centered.ply"),
                },
            },
        ],
        "callout": (
            '    <div class="params" style="border-color:#f43f5e88;">\n'
            '      <b>Reference limitation:</b> the reference for this object is incomplete — the LiDAR captured only the upper ~2/3 of\n'
            '      the pole height and only one side. All methods, in both captures, show the same pattern: a smooth error gradient along\n'
            '      the pole — the top matches the LiDAR almost exactly, while the bottom is systematically farther (25-30 cm+), simply\n'
            '      because there is no reference there. This is <b>not</b> a scale/rotation error (alignment is correct); it is limited\n'
            '      reference coverage — the missing regions are handled via gap detection. Numbers below are computed as-is.\n'
            '    </div>'
        ),
        "checkbox_checked": False,
        "checkbox_note": "",
        # tuned per docs/tables/information_sign_002_mini_report_ft7_eps3_mp5.xlsx, then
        # rechecked live in tuner.html after the downsample voxel fix (2026-09-04) - the
        # reference's old per-object spacing (1.73cm) was ~73% off the corrected fixed 1cm
        # grid for this object, so the pre-fix defaults needed reconfirming. Updated to
        # ft=5/eps=2/mp=3. Slider range widened vs the standard 5-20cm since the known gap
        # is large (25-30cm+), so it's worth being able to explore further than the default.
        "dbscan": {
            "ft_min": 5, "ft_max": 30, "ft_step": 0.5, "ft_default": 5,
            "eps_min": 0.5, "eps_max": 10, "eps_step": 0.1, "eps_default": 2,
            "mp_min": 2, "mp_max": 40, "mp_default": 3,
        },
    },
    "bench": {
        "ref": "data/lidar/bench_003/bench_003_no_floor_centered.ply",
        "captures": [
            {
                "id": "bench_004", "n_photos": 94, "style": "far view + close-up (near) shots",
                "methods": {
                    "mast3r_ga": ("exp_134", "outputs/registrations/exp_134_to_lidar_bench_003/exp_134_mast3r_ga_bench_004_scaled_aligned_to_bench_003_no_floor_centered.ply"),
                    "vggt": ("exp_133", "outputs/registrations/exp_133_to_lidar_bench_003/exp_133_vggt_bench_004_scaled_aligned_to_bench_003_no_floor_centered.ply"),
                    "colmap": ("exp_131", "outputs/registrations/exp_131_to_lidar_bench_003/exp_131_colmap_bench_004_scaled_aligned_to_bench_003_no_floor_centered.ply"),
                    "hloc_colmap": ("exp_132", "outputs/registrations/exp_132_to_lidar_bench_003/exp_132_hloc_colmap_bench_004_scaled_aligned_to_bench_003_no_floor_centered.ply"),
                },
            },
        ],
        "callout": None,
        "checkbox_checked": False,
        "checkbox_note": "",
        # tuned per docs/tables/bench_003_mini_report_ft5_eps2_mp4.xlsx, then rechecked live
        # in tuner.html after the downsample voxel fix (2026-09-04) - old per-object spacing
        # (1.73cm) was ~73% off the corrected fixed 1cm grid for this object. Updated to
        # ft=5/eps=3/mp=2.
        "dbscan": {"ft_default": 5, "eps_default": 3, "mp_default": 2},
    },
    "bollard": {
        "ref": "data/lidar/bollard_003/bollard_003_no_floor_centered.ply",
        "captures": [
            {
                "id": "bollard_003", "n_photos": 69, "style": "far view + close-up (near) shots (uncurated pool)",
                "methods": {
                    "mast3r_ga": ("exp_146", "outputs/registrations/exp_146_to_lidar_bollard_003/exp_146_mast3r_ga_bollard_003_test_1_pool69_scaled_aligned_to_bollard_003_no_floor_centered.ply"),
                    "vggt": ("exp_145", "outputs/registrations/exp_145_to_lidar_bollard_003/exp_145_vggt_bollard_003_test_1_pool69_scaled_aligned_to_bollard_003_no_floor_centered.ply"),
                    "colmap": ("exp_143", "outputs/registrations/exp_143_to_lidar_bollard_003/exp_143_colmap_bollard_003_test_1_pool69_scaled_aligned_to_bollard_003_no_floor_centered.ply"),
                    "hloc_colmap": ("exp_144", "outputs/registrations/exp_144_to_lidar_bollard_003/exp_144_hloc_colmap_bollard_003_test_1_pool69_scaled_aligned_to_bollard_003_no_floor_centered.ply"),
                },
            },
        ],
        "callout": (
            '    <div class="callout" style="margin-top:12px; font-size:13px; line-height:1.5; background:var(--code-bg); '
            'border:1px solid var(--panel-border); border-left:3px solid var(--accent, #17805f); border-radius:8px; padding:10px 14px; color:var(--text-dim);">\n'
            '      <b>Object note:</b> the LiDAR reference was <b>not scanned from all sides</b> — a ~90° sector of the bollard is missing\n'
            '      (the reconstructions are full, 360°) in both captures. So part of the accuracy points fall into a “reference gap”; this\n'
            '      is <b>not a geometry error</b> but the absence of a reference there. That is exactly what the DBSCAN gap tuner above is for: it\n'
            '      clusters this sector and excludes it from F1.\n'
            '    </div>'
        ),
        "checkbox_checked": False,
        "checkbox_note": "",
        # tuned per docs/tables/bollard_003_mini_report_ft5_eps2_mp3.xlsx
        "dbscan": {"ft_default": 5, "eps_default": 2, "mp_default": 3},
    },
    "flashlight": {
        "ref": "data/lidar/flashlight_003/flashlight_003_no_floor_centered.ply",
        "captures": [
            {
                # NOTE: registration dirs/report.json on disk are mislabeled "to_lidar_flashlight_001"
                # (a different lamppost/scan); verified directly (Chamfer distance) that the aligned
                # clouds actually match flashlight_003 (median ~1cm) and not flashlight_001 (median
                # ~13cm, wrong height/bbox) - user confirmed flashlight_003 is the intended reference.
                "id": "flashlight_004", "n_photos": 105, "style": "far view + close-up (near) shots",
                "methods": {
                    "mast3r_ga": ("exp_150", "outputs/registrations/exp_150_to_lidar_flashlight_001/exp_150_mast3r_ga_flashlight_004_scaled_aligned_to_flashlight_001_no_floor_centered.ply"),
                    "vggt": ("exp_149", "outputs/registrations/exp_149_to_lidar_flashlight_001_2/exp_149_vggt_flashlight_004_scaled_aligned_to_flashlight_001_no_floor_centered.ply"),
                    "colmap": ("exp_147", "outputs/registrations/exp_147_to_lidar_flashlight_001/exp_147_colmap_flashlight_004_scaled_aligned_to_flashlight_001_no_floor_centered.ply"),
                    "hloc_colmap": ("exp_148", "outputs/registrations/exp_148_to_lidar_flashlight_001/exp_148_hloc_colmap_flashlight_004_scaled_aligned_to_flashlight_001_no_floor_centered.ply"),
                },
            },
        ],
        "callout": (
            '    <div class="callout" style="margin-top:12px; font-size:13px; line-height:1.5; background:var(--code-bg); '
            'border:1px solid var(--panel-border); border-left:3px solid #f43f5e; border-radius:8px; padding:10px 14px; color:var(--text-dim);">\n'
            '      <b>vggt fails on this lamppost.</b> flashlight_004 is a thin, tall lamppost (~6 m). mast3r_ga,\n'
            '      colmap and hloc_colmap reconstructed it cleanly (accuracy median ~1-3.5 cm), while <b>vggt produced a\n'
            '      blurred noise cloud</b> (median ~11 cm). Its points are far from\n'
            '      the surface — this is <b>real reconstruction noise</b>, not a reference gap, so DBSCAN gap-exclusion on vggt can\n'
            '      spuriously “improve” F1; comparing methods via vggt on this object is not valid.\n'
            '    </div>'
        ),
        "checkbox_checked": True,
        "checkbox_note": "this lamppost has no gaps, so this is the <b>honest</b> mode (and it does not let vggt spuriously “improve” by cutting away its noise).",
        "display_name": "lamppost",
    },
    "bus_stop_sign": {
        "ref": "data/lidar/bus_stop_sign_001/bus_stop_sign_001_no_floor_centered.ply",
        "captures": [
            {
                "id": "bus_stop_sign_002", "n_photos": 79, "style": "far view + close-up (near) shots",
                "methods": {
                    "mast3r_ga": ("exp_138", "outputs/registrations/exp_138_to_lidar_bus_stop_sign_001/exp_138_mast3r_ga_bus_stop_sign_002_scaled_aligned_to_bus_stop_sign_001_no_floor_centered.ply"),
                    "vggt": ("exp_137", "outputs/registrations/exp_137_to_lidar_bus_stop_sign_001/exp_137_vggt_bus_stop_sign_002_scaled_aligned_to_bus_stop_sign_001_no_floor_centered.ply"),
                    "colmap": ("exp_135", "outputs/registrations/exp_135_to_lidar_bus_stop_sign_001/exp_135_colmap_bus_stop_sign_002_scaled_aligned_to_bus_stop_sign_001_no_floor_centered.ply"),
                    "hloc_colmap": ("exp_136", "outputs/registrations/exp_136_to_lidar_bus_stop_sign_001/exp_136_hloc_colmap_bus_stop_sign_002_scaled_aligned_to_bus_stop_sign_001_no_floor_centered.ply"),
                },
            },
        ],
        "callout": (
            '    <div class="callout" style="margin-top:12px; font-size:13px; line-height:1.5; background:var(--code-bg); '
            'border:1px solid var(--panel-border); border-left:3px solid #f43f5e; border-radius:8px; padding:10px 14px; color:var(--text-dim);">\n'
            '      bus_stop_sign is a sign on a pole (~3.7 m). Reference coverage is almost full (no gaps), so any far points from a given\n'
            '      method are real noise, not a gap: for honest metrics without “improving” a noisy method by cutting away its noise,\n'
            '      enable <b>“Ignore DBSCAN”</b> in the tuner above (on by default here).\n'
            '    </div>'
        ),
        "checkbox_checked": True,
        "checkbox_note": "bus_stop_sign has no gaps, so this is the <b>honest</b> mode.",
        # tuned per docs/tables/bus_stop_sign_001_mini_report_ft5_eps2_mp3.xlsx
        "dbscan": {"ft_default": 5, "eps_default": 2, "mp_default": 3},
    },
}


# --- helpers --------------------------------------------------------------------

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


# --- main ------------------------------------------------------------------------

def build(page_id: str) -> None:
    _load_open3d()
    cfg = MERGED_OBJECTS[page_id]
    display_name = cfg.get("display_name", page_id)
    ref_path = PROJECT_ROOT / cfg["ref"]
    print(f"[ref] {page_id}: loading {ref_path.name}", flush=True)
    ref = load_reference(ref_path)
    rpts = np.asarray(ref.points)
    print(f"       {len(rpts)} pts, density-matching voxel = {VOXEL_M*100:.2f} cm", flush=True)

    part1 = {
        "floor_cm": FLOOR_CM,
        "target_pos": b64f(rpts),
        "n_target_total": int(len(rpts)),
    }

    panel_keys: list[str] = []

    for capture in cfg["captures"]:
        cap_id = capture["id"]
        group_label = f"{capture['n_photos']} photos · {capture['style']}"
        for method_id in METHOD_ORDER:
            if method_id not in capture["methods"]:
                continue
            exp_id, rel = capture["methods"][method_id]
            panel_key = f"{cap_id}__{method_id}"
            src_path = PROJECT_ROOT / rel
            print(f"[{panel_key}] {exp_id} <- {src_path.name}", flush=True)
            src = o3d.io.read_point_cloud(str(src_path))
            raw_points = len(src.points)

            matched = src.voxel_down_sample(VOXEL_M)
            mpts = np.asarray(matched.points)
            n_matched = len(mpts)

            d_s2t_cm = np.asarray(matched.compute_point_cloud_distance(ref)) * 100.0
            d_t2s_cm = np.asarray(ref.compute_point_cloud_distance(matched)) * 100.0

            below_mask = d_s2t_cm <= FLOOR_CM
            cand_mask = ~below_mask
            n_below_true = int(below_mask.sum())
            n_cand_true = int(cand_mask.sum())

            below_idx = np.where(below_mask)[0]
            cand_idx = np.where(cand_mask)[0]
            below_sel = below_idx[subsample(len(below_idx), EMBED_CAP)]
            cand_sel = cand_idx[subsample(len(cand_idx), EMBED_CAP)]

            acc_med = float(np.median(d_s2t_cm)) if n_matched else float("nan")
            comp_med = float(np.median(d_t2s_cm)) if len(d_t2s_cm) else float("nan")
            print(f"          raw={raw_points} matched={n_matched} below={n_below_true} "
                  f"candidates={n_cand_true} acc_med={acc_med:.2f}cm comp_med={comp_med:.2f}cm", flush=True)

            part1[panel_key] = {
                "label": f"{exp_id} {method_id}",
                "group": group_label,
                "n_source_total": n_matched,
                "n_below_floor_true": n_below_true,
                "n_candidates_true": n_cand_true,
                "below_pos": b64f(mpts[below_sel]),
                "below_dist_cm": b64f(d_s2t_cm[below_sel]),
                "below_approx": bool(len(below_sel) < n_below_true),
                "candidate_pos": b64f(mpts[cand_sel]),
                "candidate_dist_cm": b64f(d_s2t_cm[cand_sel]),
                "candidate_approx": bool(len(cand_sel) < n_cand_true),
                "target_dist_cm": b64f(d_t2s_cm),
            }
            panel_keys.append(panel_key)

    write_page(page_id, cfg, part1, panel_keys)


EXACT_JSON = PROJECT_ROOT / "docs" / "tables" / "summary_all_objects_accuracy_f1.json"


def exact_block(page_id: str) -> str:
    """The <script id="exact-data"> the page reads for its at-default figures.

    The browser recomputes Accuracy/F1 from a capped subsample of each pool, and DBSCAN on a
    thinned cloud finds fewer clusters - so the live gap mask under-excludes and Accuracy
    reads low (bus_stop/vggt: ~9 points). While the tuner is at this page's defaults there is
    an exact answer available, computed over the full cloud by
    build_accuracy_f1_summary_table.py, and the page shows that instead. Missing file =
    no block = the page falls back to the live estimate everywhere, as before.
    """
    if not EXACT_JSON.exists():
        print(f"  ! {EXACT_JSON.relative_to(PROJECT_ROOT)} not found - page will show live estimates only")
        return ""
    data = json.loads(EXACT_JSON.read_text())
    page = data.get("pages", {}).get(page_id)
    if not page:
        print(f"  ! no exact metrics for {page_id} in {EXACT_JSON.name} - live estimates only")
        return ""
    payload = json.dumps(page).replace("</", "<\\/")
    return f'<script type="application/json" id="exact-data">{payload}</script>\n'


def write_page(page_id: str, cfg: dict, part1: dict, panel_keys: list[str]) -> None:
    display_name = cfg.get("display_name", page_id)
    # ----- assemble HTML -----
    dbscan = {**DEFAULT_DBSCAN_SLIDERS, **cfg.get("dbscan", {})}

    body = (BODY_TEMPLATE.replace("__OBJ_DISPLAY__", display_name).replace("__OBJ_ID__", page_id)
            .replace("__SITE_NAV__", nav_html(page_id)))
    body = body.replace("__CALLOUT_BLOCK__", (cfg["callout"] or "") + ("\n" if cfg["callout"] else ""))
    body = body.replace("__CHECKBOX_CHECKED__", " checked" if cfg["checkbox_checked"] else "")
    body = body.replace("__CHECKBOX_NOTE__", (("        " + cfg["checkbox_note"] + "\n") if cfg["checkbox_note"] else ""))

    main_js = MAIN_JS_AND_TAIL.replace("__METHOD_IDS_JSON__", json.dumps(panel_keys))
    for key, val in dbscan.items():
        main_js = main_js.replace(f"__{key.upper()}__", str(val))
        body = body.replace(f"__{key.upper()}__", str(val))

    part1_json = part1 if isinstance(part1, str) else json.dumps(part1).replace("</", "<\\/")

    html = (
        "<!doctype html>\n<html lang=\"en\">\n<head>\n<meta charset=\"utf-8\">\n"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
        f"<title>{display_name} — Accuracy/Completeness/F1 (gap-aware)</title>\n"
        + HEAD_TOP2.replace("__NAV_CSS__", NAV_CSS) + "\n"
        + body + "\n"
        + f'<script type="application/json" id="part1-data">{part1_json}</script>\n'
        + exact_block(page_id)
        + main_js
    )

    out_path = SITE_DIR / f"{page_id}.html"
    out_path.write_text(html, encoding="utf-8")
    size_mb = out_path.stat().st_size / (1024 * 1024)
    print(f"\nWrote {out_path.relative_to(PROJECT_ROOT)} ({size_mb:.2f} MB)", flush=True)


def relayout(page_id: str) -> None:
    """Re-render site/<page_id>.html from the payload it already carries.

    The point clouds are the only expensive part, and they are already in the file. A change
    to the template, or a refreshed docs/tables/summary_all_objects_accuracy_f1.json, needs
    nothing recomputed - so this reuses the embedded blob verbatim. Use it ONLY when that
    blob is unchanged: any new field the template reads has to come from a full build.
    """
    import re

    path = SITE_DIR / f"{page_id}.html"
    html = path.read_text(encoding="utf-8")
    m = re.search(r'<script type="application/json" id="part1-data">(.*?)</script>', html, re.S)
    if not m:
        sys.exit(f"no embedded payload in {path} - run a full build instead")
    payload = m.group(1)
    panel_keys = json.loads(re.search(r"const METHOD_IDS = (\[.*?\]);", html).group(1))
    # re-sort by the current METHOD_ORDER: a relayout after that constant changes should move
    # the panels, not preserve the order the page happened to be built with
    panel_keys.sort(key=lambda k: (k.rsplit("__", 1)[0],
                                   METHOD_ORDER.index(k.rsplit("__", 1)[1])
                                   if k.rsplit("__", 1)[1] in METHOD_ORDER else len(METHOD_ORDER)))
    write_page(page_id, MERGED_OBJECTS[page_id], payload, panel_keys)


if __name__ == "__main__":
    args = sys.argv[1:]
    mode_relayout = "--relayout" in args
    args = [a for a in args if a != "--relayout"]
    if args == ["all"]:
        args = list(MERGED_OBJECTS)
    if not args or any(a not in MERGED_OBJECTS for a in args):
        print(f"Usage: python -u {sys.argv[0]} [--relayout] <page_id> [<page_id> ...] | all\n"
              f"Known: {list(MERGED_OBJECTS)}")
        sys.exit(1)
    for page_id in args:
        (relayout if mode_relayout else build)(page_id)
