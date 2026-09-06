"""Regenerate docs/tables/summary_all_objects_accuracy_f1.xlsx from the CURRENT contents of
config/objects.yaml's site (build_object_page.py's MERGED_OBJECTS) - one row per (object,
method), matching exactly what's live on each per-object report page at its OWN default
DBSCAN gap-tuner setting (or "no DBSCAN" for the two objects whose honest default is the
Ignore-DBSCAN checkbox).

The previous version of this table was stale: it mixed some now-removed far-view-only
captures (bus_stop_001, bench_003, flashlight_003, bus_stop_sign_001) with what are now the
ONLY captures for other objects (bollard_003, information_sign_002) - a leftover from before
those objects had a second capture. This rebuild reads MERGED_OBJECTS directly (imported from
build_object_page.py, not re-declared) so it can never drift from what the live pages show:
6 physical objects x 4 methods = 24 rows, one row per (object, method) using each object's
single remaining capture.

Numbers are computed exactly (no subsampling) - the live pages' WebGL viewer subsamples for
render performance and population-corrects the estimate; this script computes directly over
the full aligned cloud, so these are the precise values, not an approximation of them.

Usage:
    python -u src/registration/build_accuracy_f1_summary_table.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import open3d as o3d

from _block_bootstrap import bootstrap_draws, ci95, diff_ci95

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_object_page import MERGED_OBJECTS, METHOD_ORDER, DEFAULT_DBSCAN_SLIDERS  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUT_XLSX = PROJECT_ROOT / "docs" / "tables" / "summary_all_objects_accuracy_f1.xlsx"
OUT_XLSX_EN = PROJECT_ROOT / "docs" / "tables" / "summary_all_objects_accuracy_f1_EN.xlsx"
OUT_JSON = PROJECT_ROOT / "docs" / "tables" / "summary_all_objects_accuracy_f1.json"
# Same rows as the workbook, machine-readable, keyed the way the per-object pages key their
# panels ("<capture_id>__<method>"). build_object_page.py --relayout injects it into each
# page so that, while the tuner sits at that page's defaults, the panels show these exact
# numbers instead of the browser's subsample estimate of them. See that script's --relayout.

VOXEL_M = 0.01
# Voxel size used to density-match every reconstruction to the reference, in metres.
# Fixed at the 1 cm grid the LiDAR references are actually delivered on, rather than
# derived per-object from the reference's median NN-spacing. Two reasons: the delivered
# clouds are already thinned onto that grid, so the grid pitch is the real sampling
# limit; and the measured median NN-spacing sits *below* the pitch because overlapping
# scan passes leave exact-duplicate points at zero distance (bus_stop_001 reads 1.00 cm
# as delivered, 1.41 cm once duplicates are dropped). A fixed voxel also keeps the
# downsampling identical across objects and methods.

FLOOR_CM = 3.0
THRESHOLDS_CM = [3.0, 5.0, 10.0]

# Spelled out on the "symmetric Chamfer" column and repeated in FINAL_results.xlsx, because
# the name covers several different quantities and a number under it is unusable without one.
CHAMFER_NOTE = (
    "Symmetric Chamfer distance, in centimetres.\n\n"
    "Convention used here: the mean of the two one-sided means - reconstruction to reference "
    "(the accuracy side) and reference to reconstruction (the completeness side) - with the "
    "distances NOT squared, on the same 1 cm grid and the same gap-excluded points as every "
    "other column. Accuracy and completeness are those two halves; this is their half-sum.\n\n"
    "Papers on learned reconstruction (VGGT and MASt3R included) commonly report a SQUARED "
    "Chamfer, so their numbers are not directly comparable with these.\n\n"
    "Reported for completeness. The thresholded F1 columns remain the primary result: where "
    "the reference itself is incomplete, a raw symmetric distance is dominated by the regions "
    "the scanner never reached rather than by the quality of the reconstruction."
)

# Spatial block bootstrap for the 95% CIs, at 3 cm only - the threshold the text quotes; 5 and
# 10 cm are there as a bias check and do not need intervals. Same B and block size as the two
# ablations, so an interval here and an interval on capture_comparison.html mean the same
# thing. BLOCK_CM was picked for the bollard and the sign; re-checked here on the two largest
# objects (bus_stop 4.3 m, flashlight 5.8 m), where error correlation could plausibly run
# longer - see the note next to BLOCK_CM.
B_BOOT = 2000
BLOCK_CM = 5.0
# Checked, not assumed (`--block-check`, 2026-09-05): reran bus_stop (4.3 m) and flashlight
# (5.8 m) - the two objects larger than anything the constant was tuned on - at 5 and 10 cm.
# The interval does roughly double at 10 cm, but that is what coarser blocks do on their own:
# points lie on a surface, so a doubled edge leaves ~4x fewer blocks and a bootstrap over 4x
# fewer units is ~2x wider. Measured width ratio against sqrt(n_blocks_5 / n_blocks_10) came
# out 0.82-1.05, median 0.98 across the eight rows - the coarser grid explains all of the
# widening, and there is no error correlation beyond 5 cm left to capture. So 5 cm stays, which
# also keeps this table comparable with the two ablations.
BOOT_SEED = 123
# Accuracy/completeness/F1 are reported at all three thresholds now, not just 3cm - 3cm is
# still what the DBSCAN gap-mask itself is built against (FLOOR_CM/the live tuner's floor),
# so it stays the "primary" bolded-winner column; 5cm/10cm are additional, looser cuts over
# the exact same kept/candidate split (only the <= comparison changes, not the gap mask).
METHOD_LABEL_RU = {"mast3r_ga": "mast3r_ga", "vggt": "vggt", "colmap": "colmap", "hloc_colmap": "hloc_colmap"}

SHAPE_RU = {
    "bus_stop": "павильон", "information_sign": "стойка", "bench": "скамья",
    "bollard": "столбик", "flashlight": "фонарь ~6м", "bus_stop_sign": "знак ~3.7м",
}
SHAPE_EN = {
    "bus_stop": "bus shelter", "information_sign": "information sign", "bench": "bench",
    "bollard": "bollard", "flashlight": "lamppost (~6m)", "bus_stop_sign": "sign on pole (~3.7m)",
}
REF_NOTE_RU = {
    "bus_stop": "неполный эталон: отсутствует дальняя от проезжей части сторона остановки; часть эталона — результат склейки 2 сканов, местами наложение неточное",
    "information_sign": "неполный эталон: заснята только верхняя ~2/3 высоты столба и одна сторона — сравнение корректно только в этой области (не ошибка масштаба/поворота)",
    "bench": "неполный эталон: отсутствует задняя часть спинки лавочки и ножки",
    "bollard": "неполный эталон: снята только одна сторона (~90° сектор отсутствует) — недостающая сторона учтена через детекцию дыр (DBSCAN)",
    "flashlight": "полный эталон",
    "bus_stop_sign": "полный эталон",
}
REF_NOTE_EN = {
    "bus_stop": "incomplete reference: the bus stop's far side (away from the road) wasn't scanned; part of the reference is a merge of 2 scans that don't align perfectly in places",
    "information_sign": "incomplete reference: only the upper ~2/3 of the pole height and one side were scanned — comparison is only valid in that region (not a scale/rotation error)",
    "bench": "incomplete reference: the bench's backrest (rear side) and legs are missing",
    "bollard": "incomplete reference: only one side was scanned (~90° sector missing) — the missing side is handled via gap detection (DBSCAN)",
    "flashlight": "full reference",
    "bus_stop_sign": "full reference",
}


def nn_spacing_median(points: np.ndarray) -> float:
    from scipy.spatial import cKDTree
    tree = cKDTree(points)
    d, _ = tree.query(points, k=2)
    return float(np.median(d[:, 1]))


def dbscan_mode_str(dbscan_cfg: dict, checkbox_checked: bool) -> str:
    if checkbox_checked:
        return "no DBSCAN"
    ft, eps, mp = dbscan_cfg["ft_default"], dbscan_cfg["eps_default"], dbscan_cfg["mp_default"]
    return f"ft{ft:g}/eps{eps:g}/mp{mp:g}"


def f_score(p: float, r: float) -> float:
    return 0.0 if (p + r) == 0 else 2 * p * r / (p + r)


# robust axis-aligned bbox: 0.5/99.5 percentile per axis, not true min/max, so one stray
# floating point (a real risk on noisier methods like vggt) doesn't blow up the reported size
BBOX_PCT_LO, BBOX_PCT_HI = 0.5, 99.5


def bbox_dims_cm(points_m: np.ndarray) -> tuple[float, float, float]:
    """(length, width, height) in cm from a point cloud in meters. Z is trusted as the world
    "up" axis (every reference/reconstruction here has already had the ground plane removed
    and been centered - see remove_ground_plane.py); the two horizontal extents (X, Y) aren't
    guaranteed to align with the object's own long/short axes (registration doesn't rotate to
    match), so they're just sorted: length = the longer footprint extent, width = the shorter."""
    lo = np.percentile(points_m, BBOX_PCT_LO, axis=0)
    hi = np.percentile(points_m, BBOX_PCT_HI, axis=0)
    extent_m = hi - lo
    height_cm = float(extent_m[2]) * 100.0
    horiz = sorted([float(extent_m[0]), float(extent_m[1])], reverse=True)
    length_cm, width_cm = horiz[0] * 100.0, horiz[1] * 100.0
    return length_cm, width_cm, height_cm


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


RMSE_PATH = PROJECT_ROOT / "docs" / "tables" / "registration_rmse_from_aligned_clouds.json"
_rmse_table = json.loads(RMSE_PATH.read_text())["rows"] if RMSE_PATH.exists() else {}


def load_icp_rmse_cm(exp_id: str) -> tuple[float | None, float | None]:
    """Registration quality -> (rmse_cm, inlier_share_pct).

    Returned in cm, though the sidecar stores mm. Every other distance this table
    reports is in cm, and this column exists precisely to be read against one of them -
    accuracy median - to tell "this method is worse" from "this registration is worse".
    A reader cannot make that comparison across a unit change. The sidecar keeps mm
    because its field is named rmse_inlier_mm and two scripts read it; the conversion
    belongs here, at the point of reporting.

    Reported alongside F1 so a reader can tell "F1 differs because the method differs" from
    "F1 differs because this particular registration is worse" - it answers "maybe it's just
    badly aligned?" directly instead of leaving it to be inferred.

    Deliberately NOT each registration's own report.json: those describe superseded
    alignments for 14 of the 15 rows that have one (the aligned .ply was rewritten minutes
    to hours after transform.txt, so the stored inlier_rmse belongs to a cloud that is no
    longer on disk), and the other 9 report.json files are 0 bytes. The sidecar read here is
    measured from the same aligned .ply every accuracy number on this page uses, against the
    same reference, on the same 1 cm voxel grid and 3 cm threshold as F1@3cm - so the two
    columns describe the same clouds. See its "why" field.

    Nothing here reads or writes outputs/registrations/, which is deliberately read-only.
    """
    entry = _rmse_table.get(exp_id)
    if not entry:
        return None, None
    rmse_mm = entry.get("rmse_inlier_mm")
    return (None if rmse_mm is None else round(rmse_mm / 10.0, 2)), entry.get("inlier_share_pct")


def compute_rows(block_cm: float = BLOCK_CM, only_pages: set[str] | None = None) -> tuple[list[dict], list[dict]]:
    """(rows, significance) - one row per object x method, plus every pairwise method
    comparison within an object.

    `block_cm` and `only_pages` exist for the block-size check (--block-check); the table
    itself is always built with the module's own BLOCK_CM over every object.
    """
    rows = []
    boot_rng = np.random.default_rng(BOOT_SEED)
    f1_draws: dict[tuple[str, str], np.ndarray] = {}
    for page_id, cfg in MERGED_OBJECTS.items():
        if only_pages is not None and page_id not in only_pages:
            continue
        ref_path = PROJECT_ROOT / cfg["ref"]
        print(f"[ref] {page_id}: loading {ref_path.name}", flush=True)
        ref = load_reference(ref_path)
        rpts = np.asarray(ref.points)
        median_spacing = nn_spacing_median(rpts)
        ref_spacing_cm = median_spacing * 100.0

        dbscan_cfg = {**DEFAULT_DBSCAN_SLIDERS, **cfg.get("dbscan", {})}
        checkbox_checked = cfg["checkbox_checked"]
        dbscan_mode = dbscan_mode_str(dbscan_cfg, checkbox_checked)

        capture = cfg["captures"][0]  # exactly one capture per object now
        for method_id in METHOD_ORDER:
            if method_id not in capture["methods"]:
                continue
            exp_id, rel_path = capture["methods"][method_id]
            src_path = PROJECT_ROOT / rel_path
            print(f"  [{page_id}/{method_id}] {exp_id} <- {src_path.name}", flush=True)
            src = o3d.io.read_point_cloud(str(src_path))
            raw_points = len(src.points)
            matched = src.voxel_down_sample(VOXEL_M)
            mpts = np.asarray(matched.points)
            icp_rmse_cm, icp_inlier_pct = load_icp_rmse_cm(exp_id)

            d_s2t_cm = np.asarray(matched.compute_point_cloud_distance(ref)) * 100.0
            d_t2s_cm = np.asarray(ref.compute_point_cloud_distance(matched)) * 100.0

            if checkbox_checked:
                kept_mask = np.ones(len(mpts), dtype=bool)  # honest mode: nothing excluded
            else:
                below_mask = d_s2t_cm <= FLOOR_CM
                gap_mask = np.zeros(len(mpts), dtype=bool)
                far_idx = np.where(d_s2t_cm > dbscan_cfg["ft_default"])[0]
                if len(far_idx) > 0:
                    far_pcd = o3d.geometry.PointCloud()
                    far_pcd.points = o3d.utility.Vector3dVector(mpts[far_idx])
                    labels = np.array(far_pcd.cluster_dbscan(eps=dbscan_cfg["eps_default"] / 100.0, min_points=dbscan_cfg["mp_default"]))
                    gap_mask[far_idx[labels >= 0]] = True
                kept_mask = ~gap_mask

            n_excluded = int((~kept_mask).sum())
            d_kept_cm = d_s2t_cm[kept_mask]
            acc_median = float(np.median(d_kept_cm)) if d_kept_cm.size else float("nan")
            comp_median = float(np.median(d_t2s_cm)) if d_t2s_cm.size else float("nan")
            # The same two distance sets as MEANS, and their half-sum: the symmetric Chamfer
            # distance. Nothing new is measured here - accuracy and completeness already ARE the
            # two one-sided halves of Chamfer (reconstruction->reference and back). This only
            # prints the single number that name usually refers to, so a reader looking for
            # "Chamfer distance" does not conclude the work never computed one.
            # State the convention, because the literature has several: mean of the two one-sided
            # MEANS, distances NOT squared, in centimetres, over the same gap-excluded kept points
            # and the same 1 cm grid as every other number in this table. Papers on learned
            # methods (VGGT and MASt3R among them) commonly report a SQUARED Chamfer instead -
            # those figures are not directly comparable with these.
            acc_mean = float(np.mean(d_kept_cm)) if d_kept_cm.size else float("nan")
            comp_mean = float(np.mean(d_t2s_cm)) if d_t2s_cm.size else float("nan")
            chamfer_sym = 0.5 * (acc_mean + comp_mean)
            length_cm, width_cm, height_cm = bbox_dims_cm(mpts)

            row = {
                "object_id": capture["id"],
                "shape_ru": SHAPE_RU[page_id], "shape_en": SHAPE_EN[page_id],
                "ref_spacing_cm": round(ref_spacing_cm, 3),
                "method": method_id,
                "accuracy_median_cm": round(acc_median, 2),
                "completeness_median_cm": round(comp_median, 2),
                "accuracy_mean_cm": round(acc_mean, 2),
                "completeness_mean_cm": round(comp_mean, 2),
                "chamfer_sym_cm": round(chamfer_sym, 2),
                "icp_rmse_cm": icp_rmse_cm,
                "icp_inlier_pct": icp_inlier_pct,
                "raw_points": raw_points,
                "matched_points": len(mpts),
                "raw_to_matched_ratio": round(raw_points / len(mpts), 2) if len(mpts) else None,
                "dbscan_mode": dbscan_mode,
                "page_id": page_id,
                "panel_key": f'{capture["id"]}__{method_id}',
                "n_excluded": n_excluded,
                "ref_note_ru": REF_NOTE_RU[page_id], "ref_note_en": REF_NOTE_EN[page_id],
                "length_cm": round(length_cm, 1), "width_cm": round(width_cm, 1), "height_cm": round(height_cm, 1),
            }
            metrics_log = []
            for t in THRESHOLDS_CM:
                acc_t = float(np.mean(d_kept_cm <= t)) if d_kept_cm.size else 0.0
                comp_t = float(np.mean(d_t2s_cm <= t)) if d_t2s_cm.size else 0.0
                f1_t = f_score(acc_t, comp_t)
                key = f"{t:g}cm"
                row[f"accuracy_{key}_pct"] = round(acc_t * 100, 1)
                row[f"completeness_{key}_pct"] = round(comp_t * 100, 1)
                row[f"f1_{key}_pct"] = round(f1_t * 100, 1)
                metrics_log.append(f"acc@{key}={acc_t*100:.1f}% comp@{key}={comp_t*100:.1f}% F1@{key}={f1_t*100:.1f}%")
            # delta F1@10cm - F1@3cm: separates a pure offset/bias (closes fast as the threshold
            # widens, small delta) from a real gap/missing-coverage problem (stays low even at
            # 10cm, large delta) - the distinction the three thresholds were added for in the
            # first place, made explicit instead of left for the reader to compute themselves.
            row["f1_delta_10_3_pct"] = round(row["f1_10cm_pct"] - row["f1_3cm_pct"], 1)

            # 95% CIs at 3 cm, over exactly the point sets the numbers above were computed on:
            # the KEPT source points (after this object's own gap exclusion, or none at all
            # where the object's honest default is "no DBSCAN") and the full reference cloud.
            # An interval computed over a different set would not describe the number beside it.
            acc_b, comp_b, f1_b, n_blk_acc, n_blk_comp = bootstrap_draws(
                mpts[kept_mask], d_kept_cm <= 3.0, rpts, d_t2s_cm <= 3.0,
                block_cm / 100.0, B_BOOT, boot_rng,
            )
            f1_draws[(capture["id"], method_id)] = f1_b
            for name, draws in (("accuracy", acc_b), ("completeness", comp_b), ("f1", f1_b)):
                lo, hi = ci95(draws)
                row[f"{name}_3cm_ci_lo"] = round(lo, 1)
                row[f"{name}_3cm_ci_hi"] = round(hi, 1)
            row["n_blocks_acc"], row["n_blocks_comp"] = int(n_blk_acc), int(n_blk_comp)

            rmse_str = f"{icp_rmse_cm:.2f}cm/{icp_inlier_pct:.0f}%" if icp_rmse_cm is not None else "N/A"
            print(f"          acc_med={acc_median:.2f}cm comp_med={comp_median:.2f}cm "
                  f"chamfer_sym={chamfer_sym:.2f}cm  " + " ".join(metrics_log) +
                  f"  ΔF1(10-3)={row['f1_delta_10_3_pct']:+.1f}pp  ICP_RMSE={rmse_str}  "
                  f"raw={raw_points} matched={len(mpts)} (x{row['raw_to_matched_ratio']})  "
                  f"L={length_cm:.0f}cm W={width_cm:.0f}cm H={height_cm:.0f}cm", flush=True)

            rows.append(row)

    # --- pairwise: is method A actually ahead of method B on this object? ---------------
    # Not the overlap of their two individual intervals - that eyeball test is far too
    # conservative. The difference of the draws is the test, and it is UNPAIRED here: four
    # reconstructions of one object are four independent clouds with no frames in common,
    # exactly as on capture_comparison.html (the nested frame sets of the frame-count study
    # are the one place where pairing is available, and there it is used).
    point = {(r["object_id"], r["method"]): r["f1_3cm_pct"] for r in rows}
    significance = []
    for page_id, cfg in MERGED_OBJECTS.items():
        obj_id = cfg["captures"][0]["id"]
        methods = [m for m in METHOD_ORDER if (obj_id, m) in f1_draws and f1_draws[(obj_id, m)] is not None]
        for i, a in enumerate(methods):
            for b in methods[i + 1:]:
                lo, hi, includes_zero = diff_ci95(f1_draws[(obj_id, a)], f1_draws[(obj_id, b)])
                significance.append({
                    "object_id": obj_id, "method_a": a, "method_b": b,
                    "delta": round(point[(obj_id, a)] - point[(obj_id, b)], 1),
                    "ci_lo": round(lo, 1), "ci_hi": round(hi, 1),
                    "includes_zero": includes_zero,
                })
    print("\nPairwise F1@3cm between methods (unpaired block bootstrap):", flush=True)
    for r in significance:
        verdict = "not resolvable" if r["includes_zero"] else "RESOLVABLE"
        print(f"  {r['object_id']:<22}{r['method_a']:>12} - {r['method_b']:<12} "
              f"Δ={r['delta']:+6.1f}  95% CI=[{r['ci_lo']:+.1f},{r['ci_hi']:+.1f}]  {verdict}", flush=True)
    return rows, significance


def fmt_rmse(r: dict):
    """RMSE cell - measured from the same aligned cloud and reference as this row's F1."""
    v = r["icp_rmse_cm"]
    return "N/A" if v is None else v


def write_xlsx(rows: list[dict], significance: list[dict], path: Path, lang: str) -> None:
    from openpyxl import Workbook
    from openpyxl.comments import Comment
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

    thresh_keys = [f"{t:g}cm" for t in THRESHOLDS_CM]
    if lang == "ru":
        headers = ["object_id", "форма", "шаг реф., см", "длина, см", "ширина, см", "высота, см",
                   "метод", "accuracy median, см", "completeness median, см",
                   "RMSE выравнивания, см", "точек в 3см, %"]
        f1_cols = []
        for k in thresh_keys:
            headers += [f"accuracy@{k}, %", f"completeness@{k}, %", f"F1@{k}, %"]
            f1_cols.append(len(headers))
        headers += ["ΔF1@10-3см, п.п.",
                    "F1@3cm CI low", "F1@3cm CI high", "accuracy@3cm CI low", "accuracy@3cm CI high",
                    "completeness@3cm CI low", "completeness@3cm CI high",
                    "accuracy mean, см", "completeness mean, см", "симметричный Chamfer, см",
                    "точек до вокселя", "точек после 1см", "raw/matched, ×",
                    "режим DBSCAN", "примечание по эталону"]
        shape_key, note_key = "shape_ru", "ref_note_ru"
    else:
        headers = ["object_id", "shape", "ref. spacing (cm)", "length (cm)", "width (cm)", "height (cm)",
                   "method", "accuracy median (cm)", "completeness median (cm)",
                   "alignment RMSE (cm)", "points within 3cm (%)"]
        f1_cols = []
        for k in thresh_keys:
            headers += [f"accuracy@{k} (%)", f"completeness@{k} (%)", f"F1@{k} (%)"]
            f1_cols.append(len(headers))
        headers += ["ΔF1@10-3cm (pp)",
                    "F1@3cm CI low", "F1@3cm CI high", "accuracy@3cm CI low", "accuracy@3cm CI high",
                    "completeness@3cm CI low", "completeness@3cm CI high",
                    "accuracy mean (cm)", "completeness mean (cm)", "symmetric Chamfer (cm)",
                    "raw points", "matched points (1cm voxel)", "raw/matched ratio",
                    "DBSCAN mode", "reference note"]
        shape_key, note_key = "shape_en", "ref_note_en"
    n_cols = len(headers)
    dbscan_col, note_col = n_cols - 1, n_cols
    chamfer_col = n_cols - 5  # ..., symmetric Chamfer, raw, matched, ratio, DBSCAN mode, note

    wb = Workbook()
    ws = wb.active
    ws.title = "summary"
    ws.append(headers)
    header_fill = PatternFill("solid", fgColor="1F3864")
    header_font = Font(bold=True, color="FFFFFF")
    for c in ws[1]:
        c.font = header_font
        c.fill = header_fill
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    # Which Chamfer this is - the name covers several conventions, so it is spelled out on the
    # column rather than left to the reader. The two "mean" columns beside it are its halves.
    ws.cell(row=1, column=chamfer_col).comment = Comment(CHAMFER_NOTE, "build_accuracy_f1_summary_table.py", height=190, width=460)

    best_font = Font(bold=True)

    # winner (best F1@3cm) per object, computed up front - its bbox (length/width/height) is
    # what gets shown for the whole group, per "измерь по границам лучшей реконструкции".
    # 3cm (not 5/10) stays the tie-breaker since it's also what the DBSCAN gap mask floor uses.
    obj_groups: dict[str, list[int]] = {}
    for i, r in enumerate(rows):
        obj_groups.setdefault(r["object_id"], []).append(i)
    best_idx_by_obj = {obj_id: max(idxs, key=lambda i: rows[i]["f1_3cm_pct"]) for obj_id, idxs in obj_groups.items()}
    # separately, best-per-threshold within each object, for bolding each F1 column independently
    best_idx_by_obj_thresh = {
        (obj_id, k): max(idxs, key=lambda i: rows[i][f"f1_{k}_pct"])
        for obj_id, idxs in obj_groups.items() for k in thresh_keys
    }

    for r in rows:
        best = rows[best_idx_by_obj[r["object_id"]]]
        vals = [
            r["object_id"], r[shape_key], r["ref_spacing_cm"],
            best["length_cm"], best["width_cm"], best["height_cm"],
            r["method"],
            r["accuracy_median_cm"], r["completeness_median_cm"], fmt_rmse(r), r["icp_inlier_pct"],
        ]
        for k in thresh_keys:
            vals += [r[f"accuracy_{k}_pct"], r[f"completeness_{k}_pct"], r[f"f1_{k}_pct"]]
        vals += [r["f1_delta_10_3_pct"],
                 r["f1_3cm_ci_lo"], r["f1_3cm_ci_hi"],
                 r["accuracy_3cm_ci_lo"], r["accuracy_3cm_ci_hi"],
                 r["completeness_3cm_ci_lo"], r["completeness_3cm_ci_hi"],
                 r["accuracy_mean_cm"], r["completeness_mean_cm"], r["chamfer_sym_cm"],
                 r["raw_points"], r["matched_points"], r["raw_to_matched_ratio"],
                 r["dbscan_mode"], r[note_key]]
        ws.append(vals)

    # bold the best F1 per object group, independently per threshold column
    for (obj_id, k), best_i in best_idx_by_obj_thresh.items():
        col = f1_cols[thresh_keys.index(k)]
        ws.cell(row=best_i + 2, column=col).font = best_font

    # merge the per-object columns (object_id, shape, ref spacing, dimensions, DBSCAN mode,
    # reference note) down each object's row block - those repeat identically across its 4
    # method rows, only "метод"/"method" and the numeric accuracy columns vary per row.
    top_border = Border(top=Side(style="medium", color="9AA07A"))
    merge_cols = [1, 2, 3, 4, 5, 6, dbscan_col, note_col]
    for obj_id, idxs in obj_groups.items():
        first_row, last_row = idxs[0] + 2, idxs[-1] + 2  # +2: header row + 1-indexing
        for col in merge_cols:
            ws.merge_cells(start_row=first_row, start_column=col, end_row=last_row, end_column=col)
            top_cell = ws.cell(row=first_row, column=col)
            top_cell.alignment = Alignment(vertical="center", wrap_text=(col == note_col), horizontal=("left" if col in (1, 2, note_col) else "center"))
        for col in range(1, n_cols + 1):
            ws.cell(row=first_row, column=col).border = top_border

    widths = ([20, 14, 12, 11, 11, 11, 12, 15, 17, 15, 13] + [13, 16, 10] * len(thresh_keys)
              + [14] + [12] * 6 + [16, 19, 20] + [12, 15, 13, 14, 60])
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[ws.cell(row=1, column=i).column_letter].width = w
    ws.freeze_panes = "A2"
    ws.row_dimensions[1].height = 32

    # --- sheet 2: which method differences are real ------------------------------------
    ws2 = wb.create_sheet("significance")
    ws2.append([f"Pairwise F1@3cm differences between methods on the same object, "
                f"{B_BOOT} spatial block-bootstrap draws, {BLOCK_CM:g} cm blocks. Unpaired: the four "
                f"reconstructions of an object are independent clouds with no frames in common. "
                f"A CI spanning 0 means the two methods are not distinguishable on that object."])
    ws2["A1"].font = Font(italic=True, color="585D54")
    ws2.append([])
    ws2.append(["object_id", "method A", "method B", "ΔF1@3cm (pp)", "95% CI low", "95% CI high", "resolvable?"])
    for c in ws2[3]:
        c.font = header_font
        c.fill = header_fill
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    for r in significance:
        ws2.append([r["object_id"], r["method_a"], r["method_b"], r["delta"], r["ci_lo"], r["ci_hi"],
                    "no - CI spans 0" if r["includes_zero"] else "yes"])
    for row in ws2.iter_rows(min_row=4, min_col=7, max_col=7):
        for c in row:
            if c.value == "yes":
                c.font = Font(bold=True, color="0D8054")
    for col, w in zip("ABCDEFG", (22, 14, 14, 15, 13, 13, 17)):
        ws2.column_dimensions[col].width = w
    ws2.freeze_panes = "A4"

    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    print(f"Wrote {path.relative_to(PROJECT_ROOT)}")


def write_json(rows: list[dict], significance: list[dict], path: Path) -> None:
    """Per-page, per-panel exact metrics for the site to display verbatim."""
    pages: dict[str, dict] = {}
    for r in rows:
        page = pages.setdefault(r["page_id"], {"dbscan_mode": r["dbscan_mode"], "panels": {}})
        page["panels"][r["panel_key"]] = {
            **{f"{m}_{t:g}cm": r[f"{name}_{t:g}cm_pct"]
               for t in THRESHOLDS_CM
               for m, name in (("acc", "accuracy"), ("comp", "completeness"), ("f1", "f1"))},
            "acc_median_cm": r["accuracy_median_cm"],
            "comp_median_cm": r["completeness_median_cm"],
            # the two one-sided MEANS and their half-sum - the symmetric Chamfer distance.
            # Unsquared, in cm, over the same kept points as the medians above. See CHAMFER_NOTE.
            "acc_mean_cm": r["accuracy_mean_cm"],
            "comp_mean_cm": r["completeness_mean_cm"],
            "chamfer_sym_cm": r["chamfer_sym_cm"],
            "n_excluded": r["n_excluded"],
            # 95% block-bootstrap CIs at 3 cm, computed over the same kept points
            **{f"{m}_3cm_ci_{end}": r[f"{name}_3cm_ci_{end}"]
               for m, name in (("acc", "accuracy"), ("comp", "completeness"), ("f1", "f1"))
               for end in ("lo", "hi")},
            "n_blocks_acc": r["n_blocks_acc"], "n_blocks_comp": r["n_blocks_comp"],
        }
    path.write_text(json.dumps({
        "source": "build_accuracy_f1_summary_table.py",
        "bootstrap": {"n_draws": B_BOOT, "block_cm": BLOCK_CM, "threshold_cm": 3.0, "paired": False},
        "chamfer_convention": CHAMFER_NOTE,
        "significance": significance,
        "pages": pages,
    }, indent=2))
    print(f"Wrote {path.relative_to(PROJECT_ROOT)}")


def main() -> None:
    rows, significance = compute_rows()
    write_xlsx(rows, significance, OUT_XLSX, "ru")
    write_xlsx(rows, significance, OUT_XLSX_EN, "en")
    write_json(rows, significance, OUT_JSON)


def block_check(pages=("bus_stop", "flashlight")) -> None:
    """Does the interval widen on the two largest objects if the blocks are doubled?

    BLOCK_CM was chosen on the bollard (1 m) and the sign (2.5 m). If error correlation runs
    longer on a 4.3 m shelter or a 5.8 m lamppost, 5 cm blocks would still be splitting one
    mistake across several resampling units and the interval would come out too narrow. This
    reruns those two objects at 5 and 10 cm and prints both widths, so the choice is made from
    the numbers rather than from the assumption.
    """
    _load = {}
    for block in (5.0, 10.0):
        rows, _ = compute_rows(block_cm=block, only_pages=set(pages))
        _load[block] = {(r["object_id"], r["method"]): r for r in rows}
    # A wider interval at 10 cm is not by itself evidence of longer-range correlation: with
    # points on a surface, doubling the block edge leaves ~4x fewer blocks, and a bootstrap
    # over 4x fewer units is ~2x wider on its own. So the comparison that matters is the
    # measured width ratio against sqrt(n_blocks_5 / n_blocks_10) - the width the coarser
    # grid would produce with no extra correlation at all. Only a ratio clearly ABOVE that
    # means 5 cm blocks were splitting one mistake across several resampling units.
    import math
    print("\n--- block size check: 95% CI width at 3 cm (pp) ---", flush=True)
    print(f'{"object":<20}{"method":<14}{"F1 @5cm":>9}{"F1 @10cm":>10}{"ratio":>7}{"expected":>10}'
          f'{"blocks 5cm":>12}{"blocks 10cm":>12}', flush=True)
    excess = []
    for key in _load[5.0]:
        a, b = _load[5.0][key], _load[10.0][key]
        w = lambda r, m: r[f"{m}_3cm_ci_hi"] - r[f"{m}_3cm_ci_lo"]
        ratio = w(b, "f1") / w(a, "f1") if w(a, "f1") else float("nan")
        expected = math.sqrt(a["n_blocks_acc"] / b["n_blocks_acc"]) if b["n_blocks_acc"] else float("nan")
        excess.append(ratio / expected)
        print(f'{key[0]:<20}{key[1]:<14}{w(a,"f1"):9.2f}{w(b,"f1"):10.2f}{ratio:7.2f}{expected:10.2f}'
              f'{a["n_blocks_acc"]:12d}{b["n_blocks_acc"]:12d}', flush=True)
    print(f'\nmeasured / expected: min {min(excess):.2f}, median {sorted(excess)[len(excess)//2]:.2f}, '
          f'max {max(excess):.2f}  (1.0 = the coarser grid explains all of the widening)', flush=True)


if __name__ == "__main__":
    if "--block-check" in sys.argv[1:]:
        sys.exit(block_check())
    main()
