"""Figures and tables for Chapter 5, built from the same tables the site reads.

No number is typed into this file. Everything comes from
docs/tables/summary_all_objects_accuracy_f1_EN.xlsx - the workbook the results
page and FINAL_results.xlsx are built from - so a figure can never disagree
with the table beside it. Re-run after any recompute.

Outputs (docs/figures/, docs/tables/):
  T5_1_main_results.csv / .md   six objects x four methods, the columns the
                                chapter actually cites
  fig_5_1_f1_by_object.pdf/.png F1@3cm, 24 points, objects sorted by their best
  fig_5_2_acc_vs_comp.pdf/.png  accuracy against completeness with the y=x line

Method colours are the site's own (--s-blue / --s-orange / --s-aqua /
--s-yellow in _performance_study_page_template.py) so print and dashboard read
as one system. VGGT's yellow is too light on white at print size, so every
marker carries a thin dark edge rather than a different hue.

Usage:  python3 src/registration/build_thesis_figures.py
"""

from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import openpyxl

ROOT = Path(__file__).resolve().parents[2]
SRC_XLSX = ROOT / "docs" / "tables" / "summary_all_objects_accuracy_f1_EN.xlsx"
FIG_DIR = ROOT / "docs" / "figures"
TAB_DIR = ROOT / "docs" / "tables"

# Same order as the site (build_object_page.METHOD_ORDER): correspondence first,
# then feed-forward, matching how Chapter 4 introduces them.
METHOD_ORDER = ["colmap", "hloc_colmap", "mast3r_ga", "vggt"]
METHOD_LABEL = {"colmap": "COLMAP", "hloc_colmap": "hloc + COLMAP",
                "mast3r_ga": "MASt3R-GA", "vggt": "VGGT"}
# The palette the current pages use (--t1/--t2/--t3 and --warn in
# _capture_page_template.py / _frame_count_page_template.py), so a figure in the
# thesis and the same result on the dashboard read as one system. The four sit
# at similar lightness, which colour alone would not survive a greyscale print -
# hence a distinct marker shape per method as well.
METHOD_COLOR = {"colmap": "#c15c85", "hloc_colmap": "#a8621f",
                "mast3r_ga": "#0d8054", "vggt": "#5d63c7"}
METHOD_MARKER = {"colmap": "o", "hloc_colmap": "s",
                 "mast3r_ga": "^", "vggt": "D"}

# The workbook's "shape" column carries a size hint ("sign on pole (~3.7m)"),
# which belongs in the object table, not on every axis. These are the names the
# site and Chapter 3 use.
OBJECT_LABEL = {
    "bus_stop_002": "bus shelter", "information_sign_002": "information sign",
    "bench_004": "bench", "bollard_003": "bollard",
    "flashlight_004": "lamppost", "bus_stop_sign_002": "bus-stop sign",
}

# 160 mm text width, the usual A4 body measure with 25 mm margins.
WIDTH_IN = 160 / 25.4
plt.rcParams.update({
    "font.size": 9, "axes.labelsize": 9, "axes.titlesize": 9,
    "xtick.labelsize": 8, "ytick.labelsize": 8, "legend.fontsize": 8,
    "axes.spines.top": False, "axes.spines.right": False,
    "figure.dpi": 300, "savefig.bbox": "tight",
})


def load_rows() -> list[dict]:
    """One dict per object x method, straight out of the EN workbook.

    The object columns are merged cells, so the object identity carries down
    until the next non-empty object_id - the same shape the workbook has on
    screen.
    """
    ws = openpyxl.load_workbook(SRC_XLSX, data_only=True)[
        openpyxl.load_workbook(SRC_XLSX).sheetnames[0]]
    rows, obj_id, obj_name, dbscan = [], None, None, None
    for r in list(ws.iter_rows(values_only=True))[1:]:
        if r[0]:
            obj_id, obj_name, dbscan = r[0], r[1], r[24]
        if not r[6]:
            continue
        rows.append({
            "object_id": obj_id, "object": OBJECT_LABEL.get(obj_id, obj_name),
            "dbscan": dbscan,
            "method": r[6], "acc_median_cm": r[7], "comp_median_cm": r[8],
            "acc3": r[11], "comp3": r[12], "f1_3": r[13],
            "f1_10": r[19], "df1": r[20],
        })
    return rows


def save(fig, stem: str) -> None:
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    for ext in ("pdf", "png"):
        fig.savefig(FIG_DIR / f"{stem}.{ext}")
    plt.close(fig)
    print(f"  -> docs/figures/{stem}.pdf + .png")


def table_5_1(rows: list[dict]) -> None:
    """The chapter's main table: only the columns the text actually cites.

    Medians, alignment RMSE, point counts and excluded-as-gap stay in the
    appendix - they explain how a number came about rather than what it says.
    """
    head = ["Object", "Method", "F1@3cm", "Acc@3cm", "Comp@3cm", "dF1@10-3"]
    order = {m: i for i, m in enumerate(METHOD_ORDER)}
    rows = sorted(rows, key=lambda r: (-max(x["f1_3"] for x in rows
                                            if x["object"] == r["object"]),
                                       r["object"], order[r["method"]]))
    lines, seen = [], set()
    for r in rows:
        obj = r["object"] if r["object"] not in seen else ""
        seen.add(r["object"])
        lines.append([obj, METHOD_LABEL[r["method"]], f'{r["f1_3"]:.1f}',
                      f'{r["acc3"]:.1f}', f'{r["comp3"]:.1f}', f'{r["df1"]:+.1f}'])
    TAB_DIR.mkdir(parents=True, exist_ok=True)
    (TAB_DIR / "T5_1_main_results.csv").write_text(
        "\n".join(",".join(c for c in [*row]) for row in [head, *lines]) + "\n")
    md = ["| " + " | ".join(head) + " |",
          "|" + "|".join(["---"] * len(head)) + "|"]
    md += ["| " + " | ".join(row) + " |" for row in lines]
    (TAB_DIR / "T5_1_main_results.md").write_text("\n".join(md) + "\n")
    print("  -> docs/tables/T5_1_main_results.csv + .md")


def fig_5_1(rows: list[dict]) -> None:
    """F1@3cm for all 24 runs, objects on the y axis, sorted by their best.

    A dot per method rather than grouped bars: 24 bars read as a picket fence,
    while dots show both the object's level and the spread between methods on
    it - which on several objects is wider than the spread between objects.
    """
    objects = sorted({r["object"] for r in rows},
                     key=lambda o: max(r["f1_3"] for r in rows if r["object"] == o))
    fig, ax = plt.subplots(figsize=(WIDTH_IN, 0.42 * len(objects) + 1.1))
    for i, obj in enumerate(objects):
        here = [r for r in rows if r["object"] == obj]
        ax.plot([min(r["f1_3"] for r in here), max(r["f1_3"] for r in here)],
                [i, i], color="#d7d4c8", lw=1.2, zorder=1)
        for r in here:
            ax.scatter(r["f1_3"], i, s=42, color=METHOD_COLOR[r["method"]],
                       marker=METHOD_MARKER[r["method"]], edgecolor="#181a17",
                       linewidth=0.6, zorder=3,
                       label=METHOD_LABEL[r["method"]] if i == 0 else None)
    ax.set_yticks(range(len(objects)), objects)
    ax.set_xlabel("F1 at 3 cm (%)")
    ax.set_xlim(0, 100)
    ax.grid(axis="x", color="#e6e3d9", lw=0.7)
    ax.set_axisbelow(True)
    ax.legend(loc="lower center", bbox_to_anchor=(0.5, 1.01), ncol=4,
              frameon=False, handletextpad=0.3, columnspacing=1.4)
    save(fig, "fig_5_1_f1_by_object")


def fig_5_2(rows: list[dict]) -> None:
    """Accuracy against completeness, one point per run, with the y=x line.

    The single figure the failure-mode section rests on: below the diagonal a
    method built more than the reference can vouch for, above it the surface is
    right but unfinished. Only the runs furthest from the diagonal are
    labelled - labelling all 24 would bury the pattern.
    """
    fig, ax = plt.subplots(figsize=(WIDTH_IN, WIDTH_IN * 0.80))
    ax.plot([0, 100], [0, 100], ls="--", lw=0.9, color="#8b9084", zorder=1)
    ax.text(62, 64, "accuracy = completeness", fontsize=7.5, color="#585d54",
            ha="left", va="bottom", rotation=45, rotation_mode="anchor")
    for m in METHOD_ORDER:
        here = [r for r in rows if r["method"] == m]
        ax.scatter([r["comp3"] for r in here], [r["acc3"] for r in here], s=42,
                   color=METHOD_COLOR[m], marker=METHOD_MARKER[m],
                   edgecolor="#181a17", linewidth=0.6,
                   label=METHOD_LABEL[m], zorder=3)
    # Four runs are named, chosen for the argument rather than by distance from
    # the diagonal: the two extremes below it, one clear case above it, and the
    # lamppost's other method - same object, opposite corners, which is the
    # point the section makes. Offsets are hand-set so nothing overlaps.
    ANNOTATED = [
        ("flashlight_004", "vggt", (-9, -4), "right"),
        ("bus_stop_sign_002", "mast3r_ga", (-9, -4), "right"),
        ("bus_stop_002", "colmap", (0, -14), "center"),
        ("flashlight_004", "colmap", (-9, 4), "right"),
    ]
    by_key = {(r["object_id"], r["method"]): r for r in rows}
    for obj_id, method, offset, ha in ANNOTATED:
        r = by_key.get((obj_id, method))
        if r is None:
            continue
        ax.annotate(f'{r["object"]} · {METHOD_LABEL[method]}',
                    (r["comp3"], r["acc3"]), textcoords="offset points",
                    xytext=offset, ha=ha, fontsize=7.5, color="#181a17")
    ax.set_xlabel("Completeness at 3 cm (%)")
    ax.set_ylabel("Accuracy at 3 cm (%)")
    ax.set_xlim(0, 105)
    ax.set_ylim(0, 105)
    ax.set_aspect("equal")
    ax.grid(color="#e6e3d9", lw=0.7)
    ax.set_axisbelow(True)
    ax.legend(loc="lower left", frameon=False, handletextpad=0.3)
    save(fig, "fig_5_2_acc_vs_comp")


def main() -> None:
    rows = load_rows()
    print(f"{len(rows)} runs from {SRC_XLSX.relative_to(ROOT)}")
    table_5_1(rows)
    fig_5_1(rows)
    fig_5_2(rows)


if __name__ == "__main__":
    main()
