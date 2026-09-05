"""Build site/performance_study.html — does compute cost (time, RAM, VRAM) grow with
the number of input frames, and how, per method?

Unlike the other `studies` pages (accuracy vs N, capture-approach comparison), this
page is purely about COST, not reconstruction quality, and reads only
docs/tables/experiment_metrics.jsonl — no point clouds, no open3d, runs in seconds.

Scope, deliberately narrow: "how does cost scale with N" is only answerable from a
CONTROLLED sweep — same object, same capture, same frame-selection algorithm, only N
varies. Two such sweeps exist in the project:

  - bollard_003_test_1           N = 15/30/45/60   (manual human-ranked selection)
  - information_sign_002_test_1  N = 25/50/75/100  (manual human-ranked selection)

Both have COLMAP + MASt3R-GA (swin-8) + VGGT full sweeps now; information_sign_002_test_1
also has MASt3R-GA/logwin-7 (config/mast3r_ga_logwin.yaml) and hloc+COLMAP (config/
hloc_colmap_busstop.yaml — exhaustive SuperPoint+LightGlue pairing, geom_consistency off,
matching run_colmap_experiment.py's dense stage exactly); bollard_003_test_1's hloc+COLMAP
sweep only ran N=15/30/45 (N=60 wasn't requested). A second, SIFT-overlap-greedy ("even")
selection exists at the same N grid for COLMAP/MASt3R-GA on both objects — used here
only as a robustness cross-check table (Section D), not charted, since scaling behaviour
turned out near-identical to the manual selection.

VGGT used to have NO controlled sweep - every VGGT run was a different object at a
different N, so isolating the N effect from the object effect wasn't possible, and it was
kept out of the controlled charts entirely (see git history for that version). Both
objects above now have a real N-sweep for it too (exp_162-168), so it's charted like every
other method - `main()` still strips each run's `model_load` stage from VGGT's `time_s`
(13-29s, HF cache hot/cold - unrelated to N, dominates total time at these small N) before
fitting, same correction as before, just no longer gating it out of the main comparison.
Any OTHER object's VGGT run (still just one point, no sweep) stays in the Section E
appendix - the two controlled objects are excluded from that appendix now that they have
real charted data above, so nothing appears twice.

Every controlled sweep here is complete as of this build. If a future N-sweep addition
leaves a method partial again, the page's own "X/N — sweep pending" badges (driven by
n_points vs n_expected per series) surface that automatically - just rerun this script
after syncing new data, no code changes needed for a routine update.

Usage:
    python src/registration/build_performance_study_page.py
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUT_HTML = PROJECT_ROOT / "site" / "performance_study.html"
METRICS_JSONL = PROJECT_ROOT / "docs" / "tables" / "experiment_metrics.jsonl"

METHOD_LABEL = {
    "colmap": "COLMAP",
    "hloc_colmap": "hloc + COLMAP",
    "mast3r_ga": "MASt3R-GA",
    "mast3r_ga_logwin7": "MASt3R-GA (logwin-7)",
    "vggt": "VGGT",
}
# validated 4-slot categorical (dataviz skill, references/palette.md, adjacent-pair order)
METHOD_COLORVAR = {
    "colmap": "--s-blue",
    "hloc_colmap": "--s-orange",
    "mast3r_ga": "--s-aqua",
    "mast3r_ga_logwin7": "--s-aqua",  # variant of the same method -> same hue, dashed line
    "vggt": "--s-yellow",
}
METHOD_DASH = {"mast3r_ga_logwin7": "5 3"}

# Keys stay the internal capture ids (that is what experiment_metrics.jsonl carries); the
# titles drop the "_test_1" suffix, so one object is not called three different things across
# the site - build_final_results_workbook.py strips it from the workbook for the same reason.
CONTROLLED_OBJECTS = {
    "bollard_003_test_1": {
        "title": "bollard_003",
        "shape": "bollard (~1 m post)",
        "sizes": [15, 30, 45, 60],
    },
    "information_sign_002_test_1": {
        "title": "information_sign_002",
        "shape": "information sign (~2.5 m)",
        "sizes": [25, 50, 75, 100],
    },
}
STAGE_LABEL = {
    "feature_extraction": "feature extraction",
    "matching": "matching",
    "sparse_mapping": "sparse mapping",
    "dense_undistort": "dense: undistort",
    "dense_patchmatch": "dense: patchmatch",
    "dense_fusion": "dense: fusion",
    "model_load": "model load",
    "matching_and_optimization": "matching + global optim.",
    "export": "export",
    "preprocess": "preprocess",
    "inference": "inference",
}
STAGE_ORDER = {
    "colmap": ["feature_extraction", "matching", "sparse_mapping", "dense_undistort", "dense_patchmatch", "dense_fusion"],
    "hloc_colmap": ["feature_extraction", "matching", "sparse_mapping", "dense_undistort", "dense_patchmatch", "dense_fusion"],
    "mast3r_ga": ["model_load", "matching_and_optimization", "export"],
    "vggt": ["model_load", "preprocess", "inference", "export"],
}
RAM_TOTAL_GIB = 175.09  # NOT reproducibility.hardware.ram_total_gib (503.7 in most rows, 1511.6 in
                         # exp_157) - that field is psutil.virtual_memory().total, which reads the
                         # underlying bare-metal HOST's /proc/meminfo, not the container's actual
                         # allocation, and drifts if RunPod reschedules the pod onto different
                         # shared hardware. The real, stable ceiling is the pod's own cgroup
                         # memory.max (verified on-pod: 187999997952 bytes = 175.09 GiB) - constant
                         # across every run regardless of host.
VRAM_TOTAL_MIB = 46068  # NVIDIA L40S, unaffected by the RAM issue above - same for every run


# --- load -------------------------------------------------------------------------

def base_selection_n(object_id: str) -> tuple[str, str, int] | tuple[None, None, None]:
    m = re.match(r"(.+?)(_manual)?_n(\d+)$", object_id)
    if not m:
        return None, None, None
    return m.group(1), ("manual" if m.group(2) else "even"), int(m.group(3))


def method_variant(row: dict) -> str:
    if row["method"] == "mast3r_ga" and "logwin" in row["config"]["config_file"]:
        return "mast3r_ga_logwin7"
    return row["method"]


def load_rows() -> list[dict]:
    rows = []
    for line in METRICS_JSONL.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return [r for r in rows if r["status"] == "success"]


# --- fits -----------------------------------------------------------------------

def power_fit(n: np.ndarray, y: np.ndarray) -> dict:
    """y ~ a * N^b  (fit in log-log space). Needs >=2 positive points."""
    mask = (n > 0) & (y > 0)
    if mask.sum() < 2:
        return {"b": None, "r2": None}
    ln, ly = np.log(n[mask]), np.log(y[mask])
    b, loga = np.polyfit(ln, ly, 1)
    pred = loga + b * ln
    ss_res = float(np.sum((ly - pred) ** 2))
    ss_tot = float(np.sum((ly - ly.mean()) ** 2))
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else float("nan")
    return {"b": round(float(b), 3), "r2": round(float(r2), 3)}


def linear_fit(n: np.ndarray, y: np.ndarray) -> dict:
    if len(n) < 2:
        return {"slope": None, "intercept": None, "r2": None}
    slope, intercept = np.polyfit(n, y, 1)
    pred = slope * n + intercept
    ss_res = float(np.sum((y - pred) ** 2))
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else float("nan")
    return {"slope": round(float(slope), 3), "intercept": round(float(intercept), 1), "r2": round(float(r2), 3)}


# --- main -------------------------------------------------------------------------

def main() -> None:
    rows = load_rows()

    # index controlled-sweep rows: (base_object, selection, method_variant) -> {N: row}
    controlled: dict[tuple[str, str, str], dict[int, dict]] = {}
    for r in rows:
        base, sel, n = base_selection_n(r["object_id"])
        if base not in CONTROLLED_OBJECTS:
            continue
        variant = method_variant(r)
        controlled.setdefault((base, sel, variant), {})[n] = r

    objects_out = []
    for obj_id, ocfg in CONTROLLED_OBJECTS.items():
        sizes = ocfg["sizes"]
        methods_present = sorted(
            {v for (b, sel, v) in controlled if b == obj_id and sel == "manual"},
            key=lambda m: list(METHOD_LABEL).index(m),
        )
        series = {}
        for variant in methods_present:
            by_n = controlled.get((obj_id, "manual", variant), {})
            pts = sorted(by_n.items())
            n_arr = np.array([n for n, _ in pts], dtype=float)
            if variant == "vggt":
                # VGGT's model_load stage (13-29s, HF cache hot/cold) is unrelated to N and
                # varies more than the actual per-frame signal at these small N - strip it so
                # the fit reflects frame-count scaling, not cache-warmth noise. RAM/VRAM peaks
                # are left alone: loading the model onto the GPU is real memory use regardless
                # of how long that load took.
                t_arr = np.array([r["timing"]["total_seconds"] - r["timing"]["stages"].get("model_load", 0) for _, r in pts], dtype=float)
            else:
                t_arr = np.array([r["timing"]["total_seconds"] for _, r in pts], dtype=float)
            ram_arr = np.array([r["memory"]["peak_ram_mib"] for _, r in pts], dtype=float)
            vram_arr = np.array([r["memory"].get("peak_vram_mib") or 0 for _, r in pts], dtype=float)

            # per-stage totals (median share, computed later globally) + per-N stage dict for hover
            stage_by_n = {
                n: {k: round(v, 1) for k, v in r["timing"]["stages"].items()}
                for n, r in pts
            }

            series[variant] = {
                "label": METHOD_LABEL[variant],
                "colorvar": METHOD_COLORVAR[variant],
                "dash": METHOD_DASH.get(variant),
                "n": n_arr.tolist(),
                "exp_ids": [r["exp_id"] for _, r in pts],
                "time_s": t_arr.tolist(),
                "ram_mib": ram_arr.tolist(),
                "vram_mib": vram_arr.tolist(),
                "stage_by_n": stage_by_n,
                "fit_time": power_fit(n_arr, t_arr),
                "fit_time_lin": linear_fit(n_arr, t_arr),
                "fit_ram_lin": linear_fit(n_arr, ram_arr),
                "fit_vram_lin": linear_fit(n_arr, vram_arr),
                "n_points": len(pts),
                "n_expected": len(sizes),
            }

        # robustness cross-check: "even" selection, same object/method, same N grid
        even_table = []
        for variant in methods_present:
            by_n = controlled.get((obj_id, "even", variant), {})
            if not by_n:
                continue
            pts = sorted(by_n.items())
            n_arr = np.array([n for n, _ in pts], dtype=float)
            t_arr = np.array([r["timing"]["total_seconds"] for _, r in pts], dtype=float)
            fit = power_fit(n_arr, t_arr)
            even_table.append({
                "method": METHOD_LABEL[variant],
                "n_points": len(pts),
                "exponent": fit["b"], "r2": fit["r2"],
                "rows": [
                    {"n": int(n), "time_s": round(float(r["timing"]["total_seconds"]), 1),
                     "ram_mib": round(float(r["memory"]["peak_ram_mib"]), 0),
                     "vram_mib": round(float(r["memory"].get("peak_vram_mib") or 0), 0)}
                    for n, r in pts
                ],
            })

        objects_out.append({
            "id": obj_id,
            "title": ocfg["title"],
            "shape": ocfg["shape"],
            "sizes": sizes,
            "series": series,
            "even_check": even_table,
        })

    # --- Section D: stage share, aggregated across ALL successful runs of each method
    # (architecture-intrinsic, not tied to N — deliberately not restricted to the
    # controlled sweep, since the question here is "where does the time go", not "does
    # it grow with N")
    stage_share = {}
    for method in ("colmap", "hloc_colmap", "mast3r_ga", "vggt"):
        g = [r for r in rows if r["method"] == method]
        stages = STAGE_ORDER[method]
        entry = {"n_runs": len(g), "stages": []}
        for s in stages:
            shares = [r["timing"]["stages"].get(s, 0) / r["timing"]["total_seconds"] * 100 for r in g if r["timing"]["total_seconds"] > 0]
            per_frame = [r["timing"]["stages"].get(s, 0) / r["num_images_input"] for r in g]
            entry["stages"].append({
                "key": s, "label": STAGE_LABEL[s],
                "median_pct": round(float(np.median(shares)), 1) if shares else 0.0,
                "median_s_per_frame": round(float(np.median(per_frame)), 3) if per_frame else 0.0,
            })
        stage_share[method] = entry

    # which single stage drives super-linear growth? per-stage power-law fit, controlled
    # sweep only, manual selection, pooled across both objects (N differs so pool on log N)
    stage_scaling = {}
    for method in ("colmap", "hloc_colmap", "mast3r_ga", "vggt"):
        stages = STAGE_ORDER[method]
        per_stage = {}
        for obj in objects_out:
            s = obj["series"].get(method)
            if not s or s["n_points"] < 2:
                continue
            for stg in stages:
                vals = [s["stage_by_n"][n].get(stg, 0.0) for n in s["n"]]
                per_stage.setdefault(stg, {"n": [], "v": []})
                per_stage[stg]["n"].extend(s["n"])
                per_stage[stg]["v"].extend(vals)
        out = []
        for stg in stages:
            d = per_stage.get(stg)
            if not d or len(d["n"]) < 2:
                out.append({"key": stg, "label": STAGE_LABEL[stg], "exponent": None, "r2": None})
                continue
            fit = power_fit(np.array(d["n"]), np.array(d["v"]))
            out.append({"key": stg, "label": STAGE_LABEL[stg], "exponent": fit["b"], "r2": fit["r2"]})
        stage_scaling[method] = out

    # --- Section E: VGGT cross-sectional appendix (NOT a controlled sweep — every row here
    # is a different object; model_load stripped since it's cache-state noise, not N). The
    # two objects with a real controlled VGGT sweep are excluded - their data is charted
    # properly above instead, so nothing shows up twice.
    def _in_controlled_sweep(r: dict) -> bool:
        base, sel, _ = base_selection_n(r["object_id"])
        return base in CONTROLLED_OBJECTS and sel == "manual"

    # exp_171/172 are re-runs of pool69 and flashlight_004 made with image_mode="pad";
    # every other VGGT run in this project used "crop". Padding letterboxes the frame instead
    # of centre-cropping it, so preprocess/inference timings are not comparable with the rest
    # of the column - excluded by the author. Without this they appear as a second, slower row
    # for objects already listed here.
    VGGT_EXCLUDED = {"exp_171", "exp_172"}
    vggt_rows = sorted(
        [r for r in rows if r["method"] == "vggt" and not _in_controlled_sweep(r)
         and r["exp_id"] not in VGGT_EXCLUDED],
        key=lambda r: r["num_images_input"],
    )
    vggt_table = []
    for r in vggt_rows:
        s = r["timing"]["stages"]
        work = s.get("preprocess", 0) + s.get("inference", 0)
        vggt_table.append({
            "object": r["object_id"], "n": r["num_images_input"],
            "model_load_s": round(s.get("model_load", 0), 1),
            "work_s": round(work, 1),
            "work_s_per_frame": round(work / r["num_images_input"], 3),
            "total_s": round(r["timing"]["total_seconds"], 1),
            "ram_mib": round(r["memory"]["peak_ram_mib"], 0),
            "vram_mib": round(r["memory"].get("peak_vram_mib") or 0, 0),
        })
    n_v = np.array([r["num_images_input"] for r in vggt_rows], dtype=float)
    work_v = np.array([r["timing"]["stages"].get("preprocess", 0) + r["timing"]["stages"].get("inference", 0) for r in vggt_rows], dtype=float)
    vggt_fit_total = power_fit(n_v, np.array([r["timing"]["total_seconds"] for r in vggt_rows], dtype=float))
    vggt_fit_work = power_fit(n_v, work_v)
    vggt_fit_work_lin = linear_fit(n_v, work_v)

    # hloc sweep completeness note (so the page states plainly what's still pending)
    hloc_status = {}
    for obj_id, ocfg in CONTROLLED_OBJECTS.items():
        s = controlled.get((obj_id, "manual", "hloc_colmap"), {})
        hloc_status[obj_id] = {"have": sorted(s.keys()), "expected": ocfg["sizes"]}

    data = {
        "ram_total_gib": RAM_TOTAL_GIB,
        "vram_total_mib": VRAM_TOTAL_MIB,
        "objects": objects_out,
        "stage_share": stage_share,
        "stage_scaling": stage_scaling,
        "vggt": {
            "rows": vggt_table,
            "fit_total": vggt_fit_total,
            "fit_work": vggt_fit_work,
            "fit_work_lin": vggt_fit_work_lin,
        },
        "hloc_status": hloc_status,
        "method_label": METHOD_LABEL,
    }

    html = build_html(data)
    OUT_HTML.parent.mkdir(parents=True, exist_ok=True)
    OUT_HTML.write_text(html, encoding="utf-8")
    print(f"Wrote {OUT_HTML.relative_to(PROJECT_ROOT)}  ({OUT_HTML.stat().st_size / 1024:.1f} KB)")

    for obj_id, st in hloc_status.items():
        missing = sorted(set(st["expected"]) - set(st["have"]))
        if missing:
            print(f"  [pending] hloc_colmap manual, {obj_id}: have N={st['have']}, still missing N={missing}")

    summary_path = PROJECT_ROOT / "docs" / "tables" / "performance_study_summary.json"
    summary_path.write_text(json.dumps(sanitize(data), indent=2))
    print(f"Wrote {summary_path.relative_to(PROJECT_ROOT)}")

    write_summary_xlsx(objects_out, PROJECT_ROOT / "docs" / "tables" / "performance_study_summary.xlsx")


def write_summary_xlsx(objects_out: list[dict], path: Path) -> None:
    from openpyxl import Workbook
    from openpyxl.styles import Font

    wb = Workbook()
    ws = wb.active
    ws.title = "performance_vs_N"
    headers = ["object", "method", "N", "exp_id", "total_s", "s_per_frame", "peak_ram_mib", "peak_vram_mib"]
    ws.append(headers)
    for cell in ws[1]:
        cell.font = Font(bold=True)
    for obj in objects_out:
        for variant, s in obj["series"].items():
            for i, n in enumerate(s["n"]):
                ws.append([
                    obj["id"], s["label"], int(n), s["exp_ids"][i],
                    round(s["time_s"][i], 1), round(s["time_s"][i] / n, 2),
                    round(s["ram_mib"][i], 0), round(s["vram_mib"][i], 0),
                ])
    for col in ws.columns:
        width = max(len(str(c.value)) if c.value is not None else 0 for c in col) + 2
        ws.column_dimensions[col[0].column_letter].width = min(width, 22)
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)


def sanitize(obj):
    """Recursively replace NaN/Infinity with None — json.dumps emits the bare NaN/
    Infinity/-Infinity tokens by default, which are invalid JSON and break
    JSON.parse() in the browser even though Python's own parser accepts them."""
    if isinstance(obj, float):
        return None if (obj != obj or obj in (float("inf"), float("-inf"))) else obj
    if isinstance(obj, dict):
        return {k: sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [sanitize(v) for v in obj]
    return obj


def build_html(data: dict) -> str:
    payload = json.dumps(sanitize(data)).replace("</", "<\\/")
    head = HTML_HEAD.replace("__NAV_CSS__", NAV_CSS).replace("__SITE_NAV__", nav_html("performance_study"))
    return head + f'\n<script type="application/json" id="page-data">{payload}</script>\n' + MAIN_JS + HTML_TAIL


from _performance_study_page_template import HTML_HEAD, MAIN_JS, HTML_TAIL  # noqa: E402
from _site_nav import NAV_CSS, nav_html  # noqa: E402


if __name__ == "__main__":
    main()
