"""Build docs/tables/performance_winners_summary.xlsx - a quick "who wins" view on top of
performance_study_summary.{json,xlsx} (raw per-N-per-method time/RAM/VRAM). Same controlled-
sweep scope as site/performance_study.html: bollard_003_test_1 (N=15/30/45/60) and
information_sign_002_test_1 (N=25/50/75/100), manual frame selection only - see that page's
docstring for why (isolating the N effect needs same object/capture/selection, only N varies).

Three sheets:
  - "By N, per metric"  - one row per (object, N); winner (lowest) method + value for each of
    Time/RAM/VRAM, plus the runner-up gap (x times worse) so "wins by a little" vs "wins by a
    lot" is visible at a glance.
  - "Raw comparison"    - every method's Time/RAM/VRAM side by side per (object, N), winning
    cell per metric bold + green-filled (same "best-cell" convention as the site's summary
    tables).
  - "Overall win count" - across every (object, N, metric) triple, how many times each method
    won - the single fastest way to read "which method wins overall".

Usage:
    python src/registration/build_performance_winners_table.py
"""

from __future__ import annotations

import json
import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
METRICS_JSONL = PROJECT_ROOT / "docs" / "tables" / "experiment_metrics.jsonl"
OUT_XLSX = PROJECT_ROOT / "docs" / "tables" / "performance_winners_summary.xlsx"

METHOD_LABEL = {
    "colmap": "COLMAP",
    "hloc_colmap": "hloc + COLMAP",
    "mast3r_ga": "MASt3R-GA",
    "mast3r_ga_logwin7": "MASt3R-GA (logwin-7)",
    "vggt": "VGGT",
}
CONTROLLED_OBJECTS = {
    "bollard_003_test_1": [15, 30, 45, 60],
    "information_sign_002_test_1": [25, 50, 75, 100],
}


def _time_s(r: dict) -> float:
    # VGGT's model_load stage (13-29s, HF cache hot/cold) is unrelated to N and dominates
    # total time at these small N - strip it, same correction as performance_study.html,
    # so the "winner" isn't decided by which run happened to hit a cold cache.
    t = r["timing"]["total_seconds"]
    if r["method"] == "vggt":
        t -= r["timing"]["stages"].get("model_load", 0)
    return t


METRICS = [
    ("time_s", "Time (s)", _time_s),
    ("ram_mib", "Peak RAM (MiB)", lambda r: r["memory"]["peak_ram_mib"]),
    ("vram_mib", "Peak VRAM (MiB)", lambda r: r["memory"].get("peak_vram_mib") or 0),
]


def base_selection_n(object_id: str):
    m = re.match(r"(.+?)(_manual)?_n(\d+)$", object_id)
    if not m:
        return None, None, None
    return m.group(1), ("manual" if m.group(2) else "even"), int(m.group(3))


def method_variant(row: dict) -> str:
    if row["method"] == "mast3r_ga" and "logwin" in row["config"]["config_file"]:
        return "mast3r_ga_logwin7"
    return row["method"]


def load_controlled_rows() -> dict:
    """(object, N) -> {method_variant: row}, manual selection only, controlled objects only."""
    out: dict[tuple[str, int], dict[str, dict]] = {}
    for line in METRICS_JSONL.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        r = json.loads(line)
        if r["status"] != "success":
            continue
        base, sel, n = base_selection_n(r["object_id"])
        if base not in CONTROLLED_OBJECTS or sel != "manual":
            continue
        variant = method_variant(r)
        out.setdefault((base, n), {})[variant] = r
    return out


def main() -> None:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    from openpyxl.utils import get_column_letter

    by_obj_n = load_controlled_rows()

    BOLD = Font(bold=True)
    HEADER_FILL = PatternFill("solid", fgColor="D9ECE3")  # matches the site's forest-green accent-soft
    WIN_FILL = PatternFill("solid", fgColor="E4F5EA")
    WIN_FONT = Font(bold=True, color="17805F")

    wb = Workbook()

    # ---- Sheet 1: By N, per metric ----
    ws1 = wb.active
    ws1.title = "By N, per metric"
    headers1 = [
        "Object", "N", "n methods compared",
        "Time winner", "Time (s)", "2nd best (s)", "x faster than 2nd",
        "RAM winner", "RAM (MiB)", "2nd best (MiB)", "x lower than 2nd",
        "VRAM winner", "VRAM (MiB)", "2nd best (MiB)", "x lower than 2nd",
    ]
    ws1.append(headers1)
    for c in ws1[1]:
        c.font = BOLD
        c.fill = HEADER_FILL

    win_counts: dict[str, dict[str, int]] = {}  # metric_key -> {method: count}
    for metric_key, _, _ in METRICS:
        win_counts[metric_key] = {}

    for obj_id, sizes in CONTROLLED_OBJECTS.items():
        for n in sizes:
            methods_here = by_obj_n.get((obj_id, n), {})
            if len(methods_here) < 2:
                continue  # need >=2 methods to declare a "winner"
            row_out = [obj_id, n, len(methods_here)]
            for metric_key, _, getter in METRICS:
                vals = sorted(((getter(r), variant) for variant, r in methods_here.items()), key=lambda x: x[0])
                best_val, best_variant = vals[0]
                second_val = vals[1][0] if len(vals) > 1 else float("nan")
                ratio = second_val / best_val if best_val > 0 else float("nan")
                row_out += [METHOD_LABEL[best_variant], round(best_val, 1), round(second_val, 1), round(ratio, 2)]
                win_counts[metric_key][best_variant] = win_counts[metric_key].get(best_variant, 0) + 1
            ws1.append(row_out)

    for row in ws1.iter_rows(min_row=2):
        for col_idx in (4, 8, 12):  # winner-name columns
            cell = row[col_idx - 1]
            cell.font = WIN_FONT

    # ---- Sheet 2: Raw comparison, winner cell highlighted ----
    ws2 = wb.create_sheet("Raw comparison")
    method_order = ["colmap", "hloc_colmap", "mast3r_ga", "mast3r_ga_logwin7", "vggt"]
    headers2 = ["Object", "N"]
    for m in method_order:
        for _, label, _ in METRICS:
            headers2.append(f"{METHOD_LABEL[m]}\n{label}")
    ws2.append(headers2)
    for c in ws2[1]:
        c.font = BOLD
        c.fill = HEADER_FILL
        c.alignment = Alignment(wrap_text=True, vertical="center")

    for obj_id, sizes in CONTROLLED_OBJECTS.items():
        for n in sizes:
            methods_here = by_obj_n.get((obj_id, n), {})
            if not methods_here:
                continue
            row_out = [obj_id, n]
            # track per-metric best among methods present in this row, by column group
            best_per_metric = {}
            for metric_key, _, getter in METRICS:
                present = [(getter(r), variant) for variant, r in methods_here.items()]
                if present:
                    best_per_metric[metric_key] = min(present, key=lambda x: x[0])[1]
            for m in method_order:
                r = methods_here.get(m)
                for metric_key, _, getter in METRICS:
                    row_out.append(round(getter(r), 1) if r else None)
            ws2.append(row_out)
            r_idx = ws2.max_row
            col = 3
            for m in method_order:
                for metric_key, _, _ in METRICS:
                    if m in methods_here and best_per_metric.get(metric_key) == m:
                        cell = ws2.cell(row=r_idx, column=col)
                        cell.fill = WIN_FILL
                        cell.font = WIN_FONT
                    col += 1

    # ---- Sheet 3: Overall win count ----
    ws3 = wb.create_sheet("Overall win count")
    ws3.append(["Method", "Time wins", "RAM wins", "VRAM wins", "Total wins"])
    for c in ws3[1]:
        c.font = BOLD
        c.fill = HEADER_FILL
    all_methods = sorted({v for d in by_obj_n.values() for v in d}, key=lambda m: list(METHOD_LABEL).index(m))
    for m in all_methods:
        t = win_counts["time_s"].get(m, 0)
        ram = win_counts["ram_mib"].get(m, 0)
        vram = win_counts["vram_mib"].get(m, 0)
        ws3.append([METHOD_LABEL[m], t, ram, vram, t + ram + vram])
    ws3.append([])
    ws3.append(["Scope: controlled sweeps only (manual selection) - bollard_003_test_1 N=15/30/45/60,"])
    ws3.append(["information_sign_002_test_1 N=25/50/75/100. VGGT time is model_load-corrected"])
    ws3.append(["(HF cache hot/cold noise stripped). hloc+COLMAP is missing bollard_003_test_1 N=60"])
    ws3.append(["(not requested) - rerun this script after syncing if that changes."])
    for r in ws3.iter_rows(min_row=len(all_methods) + 3):
        for c in r:
            c.font = Font(italic=True, color="8B9084", size=10)

    # ---- column widths ----
    for ws in (ws1, ws2, ws3):
        for col_cells in ws.columns:
            length = max((len(str(c.value)) if c.value is not None else 0) for c in col_cells)
            letter = get_column_letter(col_cells[0].column)
            ws.column_dimensions[letter].width = min(max(length + 2, 10), 26)
        ws.freeze_panes = "A2"

    OUT_XLSX.parent.mkdir(parents=True, exist_ok=True)
    wb.save(OUT_XLSX)
    print(f"Wrote {OUT_XLSX.relative_to(PROJECT_ROOT)}")

    missing = []
    for obj_id, sizes in CONTROLLED_OBJECTS.items():
        for n in sizes:
            if "hloc_colmap" not in by_obj_n.get((obj_id, n), {}):
                missing.append(f"{obj_id} N={n}")
    if missing:
        print(f"  [pending] hloc_colmap missing for: {', '.join(missing)} - rerun after the pod sweep finishes")


if __name__ == "__main__":
    main()
