"""Figures and tables for Chapter 5, built from the same tables the site reads.

No number is typed into this file. Everything comes from
docs/tables/summary_all_objects_accuracy_f1_EN.xlsx - the workbook the results
page and FINAL_results.xlsx are built from - so a figure can never disagree
with the table beside it. Re-run after any recompute.

Outputs (docs/figures/, docs/tables/):
  T5_1_main_results.csv / .md   six objects x four methods, the columns the
                                chapter actually cites
  fig_4_1_two_directions.*      schematic: the two nearest-neighbour directions
  fig_4_2_m3c2.*                schematic: the M3C2 cylinder and its projection
  fig_4_3_voxel_iou.*           schematic: voxel IoU under a shift of the grid
  fig_5_1_f1_by_object.pdf/.png F1@3cm, 24 points, objects sorted by their best
  fig_5_2_acc_vs_comp.pdf/.png  accuracy against completeness with the y=x line
  fig_5_3_capture_routes.*      pairwise differences between capture routes
  fig_5_4_frame_count.*         F1 against the number of photographs
  fig_5_5_cost.*                time, peak RAM and peak VRAM against N
  fig_5_6_iou_pairs.*           voxel IoU against F1 for the 36 method pairs

Method colours are the site's own (--s-blue / --s-orange / --s-aqua /
--s-yellow in _performance_study_page_template.py) so print and dashboard read
as one system. VGGT's yellow is too light on white at print size, so every
marker carries a thin dark edge rather than a different hue.

Usage:  python3 src/registration/build_thesis_figures.py
"""

from __future__ import annotations

import json
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
# Built from the results website's palette so a figure in the thesis and the same
# result on the dashboard read as one system: the site's forest green and its
# terracotta #e16b3e, with a mid teal-green and a plum to fill the four. Cool for
# the correspondence-based family, warm for the feed-forward one. Checked under
# protan/deutan/tritan simulation: worst pair dE2000 17.0 simulated, 32.9 normal,
# against 7.2 and 27.9 for the palette this replaces. Lightness is spread by at
# least 8 units so the set also survives a greyscale print, and each method keeps
# a distinct marker shape on top of that.
METHOD_COLOR = {"colmap": "#0f5c44", "hloc_colmap": "#5fb39a",
                "mast3r_ga": "#e16b3e", "vggt": "#a34a86"}
METHOD_MARKER = {"colmap": "o", "hloc_colmap": "s",
                 "mast3r_ga": "^", "vggt": "D"}

# The workbook's "shape" column carries a size hint ("sign on pole (~3.7m)"),
# which belongs in the object table, not on every axis. These are the names the
# site and Chapter 3 use.
OBJECT_LABEL = {
    "bus_stop_002": "bus shelter", "information_sign_002": "information sign",
    "bench_004": "bench", "bollard_003": "bollard",
    "flashlight_004": "lamp post", "bus_stop_sign_002": "bus stop sign",
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

    Columns are looked up by header name, not by position: the workbook has already
    grown three times (CIs, the two one-sided means, symmetric Chamfer) and every new
    column is appended, so positional indices silently start reading the wrong field.

    The object columns are merged cells, so the object identity carries down until the
    next non-empty object_id - the same shape the workbook has on screen.
    """
    ws = openpyxl.load_workbook(SRC_XLSX, data_only=True)["summary"]
    rows_raw = list(ws.iter_rows(values_only=True))
    col = {name: i for i, name in enumerate(rows_raw[0]) if name}

    def cell(r, name):
        return r[col[name]] if name in col else None

    rows, obj_id, obj_name = [], None, None
    for r in rows_raw[1:]:
        if r[col["object_id"]]:
            obj_id, obj_name = r[col["object_id"]], r[col["shape"]]
        if not cell(r, "method"):
            continue
        rows.append({
            "object_id": obj_id, "object": OBJECT_LABEL.get(obj_id, obj_name),
            "method": cell(r, "method"),
            "acc_median_cm": cell(r, "accuracy median (cm)"),
            "comp_median_cm": cell(r, "completeness median (cm)"),
            "acc3": cell(r, "accuracy@3cm (%)"),
            "comp3": cell(r, "completeness@3cm (%)"),
            "f1_3": cell(r, "F1@3cm (%)"),
            "f1_10": cell(r, "F1@10cm (%)"),
            "df1": cell(r, "ΔF1@10-3cm (pp)"),
            "f1_ci_lo": cell(r, "F1@3cm CI low"),
            "f1_ci_hi": cell(r, "F1@3cm CI high"),
            "acc_ci_lo": cell(r, "accuracy@3cm CI low"),
            "acc_ci_hi": cell(r, "accuracy@3cm CI high"),
            "comp_ci_lo": cell(r, "completeness@3cm CI low"),
            "comp_ci_hi": cell(r, "completeness@3cm CI high"),
            "chamfer_cm": cell(r, "symmetric Chamfer (cm)"),
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


# Bounding-box volume in cubic metres, as Table 6.1 gives it. The y axis of
# fig_5_1 is ordered by it so the figure reads in the same order as the object
# row in the presentation, and so that the answer to RQ1 - size sets the group,
# not a smooth trend - can be read off the axis rather than taken on trust.
OBJECT_VOLUME_M3 = {"bollard": 0.09, "information sign": 0.30, "lamp post": 0.83,
                    "bus stop sign": 1.29, "bench": 3.54, "bus shelter": 25.23}
OBJECT_HEIGHT_M = {"bollard": 1.00, "information sign": 2.50, "lamp post": 6.05,
                   "bus stop sign": 3.60, "bench": 0.75, "bus shelter": 2.70}


def fig_5_1(rows: list[dict], groups: bool = False) -> None:
    """F1@3cm for all 24 runs, objects on the y axis, ordered by their volume.

    A dot per method rather than grouped bars: 24 bars read as a picket fence,
    while dots show both the object's level and the spread between methods on
    it - which on several objects is wider than the spread between objects.
    Smallest object at the top, largest at the bottom, so the axis is read in
    the same direction as the object row in the presentation.
    """
    objects = sorted({r["object"] for r in rows},
                     key=lambda o: -OBJECT_VOLUME_M3[o])
    fig, ax = plt.subplots(figsize=(WIDTH_IN, 0.52 * len(objects) + 1.1))
    if groups:
        # Chapter 6 reads these results as two groups rather than a trend. The
        # tint says so on the slide; the figure in the dissertation stays plain,
        # because the grouping is an interpretation and belongs to Chapter 6.
        n_small = sum(1 for o in objects if OBJECT_VOLUME_M3[o] <= 0.30)
        ax.axhspan(len(objects) - n_small - 0.5, len(objects) - 0.5,
                   color="#d9ece3", zorder=0)
        ax.axhspan(-0.5, len(objects) - n_small - 0.5, color="#f7e6dc", zorder=0)
    for i, obj in enumerate(objects):
        here = [r for r in rows if r["object"] == obj]
        ax.plot([min(r["f1_3"] for r in here), max(r["f1_3"] for r in here)],
                [i, i], color="#d7d4c8", lw=1.2, zorder=1)
        for r in here:
            # The 95 % interval is drawn, not tabulated: several pairs the eye
            # reads as different are inside each other's intervals.
            ax.errorbar(r["f1_3"], i,
                        xerr=[[r["f1_3"] - r["f1_ci_lo"]],
                              [r["f1_ci_hi"] - r["f1_3"]]],
                        fmt="none", ecolor=METHOD_COLOR[r["method"]],
                        elinewidth=1.2, capsize=2.4, capthick=1.2, zorder=2)
            ax.scatter(r["f1_3"], i, s=34, color=METHOD_COLOR[r["method"]],
                       marker=METHOD_MARKER[r["method"]], edgecolor="#181a17",
                       linewidth=0.6, zorder=3,
                       label=METHOD_LABEL[r["method"]] if i == 0 else None)
    ax.set_yticks(range(len(objects)),
                  [f"{o}\n{OBJECT_HEIGHT_M[o]:.2f} m \u00b7 {OBJECT_VOLUME_M3[o]:.2f} m\u00b3"
                   for o in objects])
    ax.set_xlabel("F1 at 3 cm (%)")
    ax.set_xlim(0, 100)
    ax.grid(axis="x", color="#e6e3d9", lw=0.7)
    ax.set_axisbelow(True)
    ax.legend(loc="lower center", bbox_to_anchor=(0.5, 1.01), ncol=4,
              frameon=False, handletextpad=0.3, columnspacing=1.4)
    save(fig, "fig_5_1_f1_by_object" + ("_groups" if groups else ""))


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


# ---------------------------------------------------------------------------
# Sources for the ablation and cost figures. Same rule as above: nothing is
# typed in, every value is read from the workbook or the JSON the site reads.
# ---------------------------------------------------------------------------
CAPTURE_XLSX = TAB_DIR / "capture_comparison_summary.xlsx"
FRAMES_XLSX = TAB_DIR / "frame_count_study_summary.xlsx"
PERF_JSON = TAB_DIR / "performance_study_summary.json"

# The significance sheets carry display labels, the data sheets raw ids.
LABEL_TO_KEY = {v: k for k, v in METHOD_LABEL.items()}
LABEL_TO_KEY["MASt3R-GA (logwin-7)"] = "mast3r_ga_logwin7"
METHOD_LABEL_X = dict(METHOD_LABEL)
METHOD_LABEL_X["mast3r_ga_logwin7"] = "MASt3R-GA (logwin-7)"
METHOD_COLOR_X = dict(METHOD_COLOR)
METHOD_COLOR_X["mast3r_ga_logwin7"] = "#ef9a6e"
METHOD_MARKER_X = dict(METHOD_MARKER)
METHOD_MARKER_X["mast3r_ga_logwin7"] = "v"


def _sheet(path, name):
    return list(openpyxl.load_workbook(path, data_only=True)[name]
                .iter_rows(values_only=True))


def fig_5_3_capture() -> None:
    """Every pairwise difference between capture routes, with its interval.

    Table 5.6 gives three F1 values per row and a count of how many differences
    are resolvable; it cannot show which ones or by how much. A forest plot can:
    the zero line does the test, so the reader is not asked to compare twelve
    pairs of overlapping intervals in their head. All four panels share one x
    axis, which is what makes the bollard's flatness legible - its intervals are
    drawn on the same scale that has to hold the sign's 35-point drop.
    """
    rows = _sheet(CAPTURE_XLSX, "significance")
    head = next(i for i, r in enumerate(rows) if r and r[0] == "object")
    col = {n: i for i, n in enumerate(rows[head]) if n}
    recs = []
    for r in rows[head + 1:]:
        if not r or not r[col["object"]]:
            continue
        recs.append({
            "object": OBJECT_LABEL.get(r[col["object"]], r[col["object"]]),
            "method": LABEL_TO_KEY[r[col["method"]]],
            "pair": r[col["pair"]],
            "d": r[col["\u0394F1@3cm (pp)"]],
            "lo": r[col["95% CI lo"]],
            "hi": r[col["95% CI hi"]],
            "ok": str(r[col["resolvable?"]]).startswith("yes"),
        })

    objects = ["bollard", "information sign"]
    methods = ["colmap", "mast3r_ga"]
    pairs = ["T1\u2212T2", "T1\u2212T3", "T2\u2212T3"]
    fig, axes = plt.subplots(2, 2, figsize=(WIDTH_IN, WIDTH_IN * 0.55),
                             sharex=True, sharey=True)
    for i, obj in enumerate(objects):
        for j, m in enumerate(methods):
            ax = axes[i][j]
            ax.axvline(0, color="#585d54", lw=1.0, zorder=2)
            c = METHOD_COLOR[m]
            for k, pair in enumerate(pairs):
                rec = next(x for x in recs if x["object"] == obj
                           and x["method"] == m and x["pair"] == pair)
                y = len(pairs) - 1 - k
                ax.plot([rec["lo"], rec["hi"]], [y, y], color=c, lw=1.8,
                        solid_capstyle="butt", zorder=3)
                ax.scatter(rec["d"], y, s=40, marker=METHOD_MARKER[m],
                           color=c if rec["ok"] else "white", edgecolor=c,
                           linewidth=1.2, zorder=4)
            ax.set_title(f"{obj} \u00b7 {METHOD_LABEL[m]}", fontsize=8.5)
            ax.set_ylim(-0.65, len(pairs) - 0.35)
            ax.grid(axis="x", color="#e6e3d9", lw=0.7)
            ax.set_axisbelow(True)
            ax.tick_params(axis="y", length=0)
    axes[0][0].set_yticks(range(len(pairs)), list(reversed(pairs)))
    fig.supxlabel("Difference in F1 at 3 cm (percentage points)", fontsize=9)
    handles = [
        plt.Line2D([], [], color="#585d54", marker="o", ls="", mfc="#585d54",
                   mec="#585d54", ms=5.5, label="resolvable"),
        plt.Line2D([], [], color="#585d54", marker="o", ls="", mfc="white",
                   mec="#585d54", ms=5.5, label="interval crosses zero"),
    ]
    fig.legend(handles=handles, loc="lower center", bbox_to_anchor=(0.5, 1.0),
               ncol=2, frameon=False, handletextpad=0.3, columnspacing=1.6)
    fig.tight_layout()
    save(fig, "fig_5_3_capture_routes")


def fig_5_4_frames() -> None:
    """F1 against the number of photographs, one panel per object.

    The bands are the same 95 % intervals the significance sheet tests, drawn
    rather than tabulated: where two bands sit apart the added photographs
    bought something, where they overlap the curve is already flat.
    """
    rows = _sheet(FRAMES_XLSX, "frame_count_study")
    col = {n: i for i, n in enumerate(rows[0]) if n}
    series = {}
    for r in rows[1:]:
        if not r or not r[col["object"]]:
            continue
        key = (OBJECT_LABEL.get(r[col["object"]], r[col["object"]]),
               r[col["method"]])
        series.setdefault(key, []).append(
            (r[col["N"]], r[col["F1@3cm (%)"]],
             r[col["F1@3cm CI lo"]], r[col["F1@3cm CI hi"]]))

    objects = ["bollard", "information sign"]
    fig, axes = plt.subplots(1, 2, figsize=(WIDTH_IN, WIDTH_IN * 0.42),
                             sharey=True)
    for ax, obj in zip(axes, objects):
        here = [(m, sorted(v)) for (o, m), v in series.items() if o == obj]
        here.sort(key=lambda t: list(METHOD_LABEL_X).index(t[0]))
        for m, pts in here:
            ns = [p[0] for p in pts]
            f1 = [p[1] for p in pts]
            lo = [p[2] for p in pts]
            hi = [p[3] for p in pts]
            c = METHOD_COLOR_X[m]
            ax.fill_between(ns, lo, hi, color=c, alpha=0.16, lw=0)
            ax.plot(ns, f1, color=c, lw=1.4,
                    ls="--" if m.endswith("logwin7") else "-",
                    marker=METHOD_MARKER_X[m], ms=4.5, mec="#181a17", mew=0.5,
                    label=METHOD_LABEL_X[m])
        ax.set_title(obj, fontsize=9)
        ax.set_xlabel("photographs")
        ax.set_xticks(ns)
        ax.grid(color="#e6e3d9", lw=0.7)
        ax.set_axisbelow(True)
        ax.legend(loc="lower right", frameon=False, handletextpad=0.4,
                  fontsize=7.5)
    axes[0].set_ylabel("F1 at 3 cm (%)")
    axes[0].set_ylim(30, 100)
    save(fig, "fig_5_4_frame_count")


def _perf_series(obj_title):
    d = __import__("json").loads(PERF_JSON.read_text())
    obj = next(o for o in d["objects"] if o["title"] == obj_title)
    out = []
    for key, s in obj["series"].items():
        by_n = s["stage_by_n"]
        ns = sorted(float(k) for k in by_n)
        tot = [sum(by_n[str(int(n))].values()) for n in ns]
        ram = [v / 1024 for v in s["ram_mib"]]
        vram = [v / 1024 for v in s["vram_mib"]]
        out.append({"key": key, "n": ns, "total_s": tot, "ram": ram,
                    "vram": vram, "stage_by_n": by_n})
    return out


def fig_5_5_cost() -> None:
    """Cost against the number of photographs: time, peak RAM, peak VRAM.

    Time is on a log axis because the four pipelines sit three orders of
    magnitude apart - on a linear axis every curve but COLMAP's is the x axis.
    Memory stays linear: the claim there is about slope, not level.

    Only the four pipelines used for the final reconstructions are drawn. On the
    information sign that means MASt3R-GA with logwin-7, the configuration the
    six final runs use; its swin-8 sweep is in the workbook but is not the
    system being costed.
    """
    panels = [("bollard_003", "bollard", "mast3r_ga"),
              ("information_sign_002", "information sign", "mast3r_ga_logwin7")]
    fig, axes = plt.subplots(2, 3, figsize=(WIDTH_IN, WIDTH_IN * 0.62),
                             sharex="row")
    for row, (title, nice, mast_key) in enumerate(panels):
        series = {s["key"]: s for s in _perf_series(title)}
        keys = ["colmap", "hloc_colmap", mast_key, "vggt"]
        for j, (field, ylab) in enumerate([("total_s", "total time (s)"),
                                           ("ram", "peak RAM (GiB)"),
                                           ("vram", "peak VRAM (GiB)")]):
            ax = axes[row][j]
            for k in keys:
                s = series[k]
                base = k.replace("_logwin7", "")
                ax.plot(s["n"], s[field], color=METHOD_COLOR[base], lw=1.4,
                        marker=METHOD_MARKER[base], ms=4.0, mec="#181a17",
                        mew=0.5, label=METHOD_LABEL[base])
            if field == "total_s":
                ax.set_yscale("log")
            ax.set_ylabel(ylab, fontsize=8)
            ax.set_xticks(series["colmap"]["n"])
            ax.grid(color="#e6e3d9", lw=0.7)
            ax.set_axisbelow(True)
            ax.tick_params(labelsize=7.5)
            if row == 1:
                ax.set_xlabel("photographs")
        axes[row][0].text(-0.42, 0.5, nice, transform=axes[row][0].transAxes,
                          rotation=90, va="center", ha="center", fontsize=9,
                          style="italic", color="#585d54")
    h, l = axes[0][0].get_legend_handles_labels()
    fig.legend(h, l, loc="lower center", bbox_to_anchor=(0.5, 1.0), ncol=4,
               frameon=False, handletextpad=0.3, columnspacing=1.6)
    fig.tight_layout()
    save(fig, "fig_5_5_cost")


def cost_table() -> None:
    """The numbers Table 5.8 quotes, printed so they can be checked by eye.

    The exponent is fitted here rather than read from the JSON: the JSON's
    stored fit counts the one-off model load for MASt3R-GA but not for VGGT, so
    the two are not on the same basis. Fitting on the work stages alone puts all
    four pipelines on one footing and leaves the fixed startup cost out of a
    number that is meant to describe growth.
    """
    import math
    for title, mast_key in [("information_sign_002", "mast3r_ga_logwin7"),
                            ("bollard_003", "mast3r_ga")]:
        print(f"  {title}")
        for s in _perf_series(title):
            if s["key"] not in ("colmap", "hloc_colmap", mast_key, "vggt"):
                continue
            by_n = s["stage_by_n"]
            ns = s["n"]
            work = [sum(v for k, v in by_n[str(int(n))].items()
                        if k != "model_load") for n in ns]
            x = [math.log(v) for v in ns]
            y = [math.log(v) for v in work]
            mx, my = sum(x) / len(x), sum(y) / len(y)
            b = (sum((a - mx) * (c - my) for a, c in zip(x, y))
                 / sum((a - mx) ** 2 for a in x))
            a0 = my - b * mx
            sr = sum((c - (a0 + b * a)) ** 2 for a, c in zip(x, y))
            st = sum((c - my) ** 2 for c in y)
            i = -2 if len(ns) >= 3 else -1          # N=75 / N=45 point
            print(f"    {s['key']:18s} N={int(ns[i]):3d}  "
                  f"total {s['total_s'][i]:8.1f} s  "
                  f"RAM {s['ram'][i]:5.1f} GiB  VRAM {s['vram'][i]:5.1f} GiB  "
                  f"b(work) {b:.2f}  r2 {1 - sr / st:.3f}")


# ---------------------------------------------------------------------------
# Chapter 4 schematics. Unlike everything above, these carry no measurement:
# the point sets are synthetic, drawn to show what each metric asks of the two
# clouds. They live here so that the diagrams and the figures built from real
# data are rebuilt by the same command and share one visual system.
# ---------------------------------------------------------------------------
INK = "#181a17"
REF_C = "#585d54"          # reference: neutral, it is the yardstick
REC_C = "#c15c85"          # reconstruction: the same pink COLMAP carries above
ARROW = "#8b9084"
BAND = "#e6e3d9"


def _scene(rng):
    """One cross-section used by both panels of Figure 4.1.

    The scene is built to contain exactly one failure of each kind, because the
    asymmetry between them is what the chapter goes on to measure: a cluster of
    reconstruction points away from the surface, which accuracy sees and
    completeness cannot, and a stretch of surface with no reconstruction on it,
    which completeness sees and accuracy cannot.
    """
    import numpy as np
    curve = lambda x: 0.42 * np.sin(0.8 * x)

    xg = np.arange(0.30, 7.05, 0.26)
    ref = np.column_stack([xg, curve(xg) + rng.normal(0, 0.030, xg.size)])

    xs = np.arange(0.35, 7.00, 0.22)
    xs = xs[(xs < 4.0) | (xs > 5.8)]                       # the unbuilt stretch
    rec = np.column_stack([xs, curve(xs) + 0.11 + rng.normal(0, 0.045, xs.size)])

    blob = np.column_stack([rng.normal(2.10, 0.22, 12),    # points off the surface
                            rng.normal(1.75, 0.16, 12)])
    return ref, np.vstack([rec, blob]), len(rec)


def fig_4_1() -> None:
    """The two sets of distances every threshold metric is a summary of.

    Accuracy and completeness are one nearest-neighbour search run in opposite
    directions, and a figure can say so where two paragraphs cannot. The scene is
    identical in both panels, so what changes is only the direction of the
    question - and with it, which of the two failures present is counted at all.
    """
    import numpy as np
    rng = np.random.default_rng(7)
    ref, rec, n_on = _scene(rng)
    T = 0.35

    fig, axes = plt.subplots(1, 2, figsize=(WIDTH_IN, WIDTH_IN * 0.44),
                             sharex=True, sharey=True)
    for k, ax in enumerate(axes):
        ax.scatter(ref[:, 0], ref[:, 1], marker="x", s=22, c=REF_C, lw=0.9, zorder=3)
        ax.scatter(rec[:, 0], rec[:, 1], marker="o", s=13, c=REC_C, zorder=3)
        src, dst = (rec, ref) if k == 0 else (ref, rec)
        pick = (list(range(1, n_on, 3)) + [n_on + i for i in (1, 4, 7, 10)]) if k == 0 \
            else list(range(1, len(ref), 2))
        for i in pick:
            p = src[i]
            q = dst[np.argmin(((dst - p) ** 2).sum(1))]
            ax.annotate("", xy=q, xytext=p, zorder=2,
                        arrowprops=dict(arrowstyle="->", color=ARROW, lw=0.7,
                                        shrinkA=1.2, shrinkB=1.2))
        ax.set_title("accuracy: reconstruction \u2192 reference" if k == 0
                     else "completeness: reference \u2192 reconstruction", fontsize=8.5)
        ax.set_aspect("equal")
        ax.set_xlim(-0.15, 7.35); ax.set_ylim(-1.45, 2.35)
        ax.set_xticks([]); ax.set_yticks([])
        for s in ax.spines.values():
            s.set_visible(False)

    # The threshold is drawn rather than stated: one circle that finds no
    # counterpart, on the point the panel is about.
    axes[0].add_patch(plt.Circle(rec[n_on + 1], T, fill=False, ls="--", lw=0.9,
                                 color=INK, zorder=4))
    axes[0].annotate("no reference within t", xy=(3.05, 1.95), fontsize=7,
                     color=INK, ha="left")
    axes[0].annotate("counts against accuracy", xy=(3.05, 1.62), fontsize=7,
                     color=INK, ha="left")
    gap_i = int(np.argmin(np.abs(ref[:, 0] - 4.8)))
    axes[1].add_patch(plt.Circle(ref[gap_i], T, fill=False, ls="--", lw=0.9,
                                 color=INK, zorder=4))
    axes[1].annotate("no reconstruction within t", xy=(4.9, -0.82), fontsize=7,
                     color=INK, ha="center")
    axes[1].annotate("counts against completeness", xy=(4.9, -1.14), fontsize=7,
                     color=INK, ha="center")
    # The positive case as well, so the circle reads as a test and not as a marker
    # of failure: on the surface the counterpart is inside t and the point counts.
    ok_i = int(np.argmin(np.abs(rec[:n_on, 0] - 6.4)))
    axes[0].add_patch(plt.Circle(rec[ok_i], T, fill=False, ls="--", lw=0.9,
                                 color=INK, zorder=4))
    axes[0].annotate("reference within t", xy=(6.4, -0.82), fontsize=7, color=INK,
                     ha="center")
    handles = [plt.Line2D([], [], ls="", marker="x", ms=5, mec=REF_C, mew=0.9,
                          label="reference"),
               plt.Line2D([], [], ls="", marker="o", ms=4, mfc=REC_C, mec=REC_C,
                          label="reconstruction")]
    axes[0].legend(handles=handles, loc="lower left", frameon=False, fontsize=7.5,
                   handletextpad=0.3, borderpad=0.1)
    fig.tight_layout()
    save(fig, "fig_4_1_two_directions")


def fig_4_2() -> None:
    """What M3C2 measures, and why it is not a nearest-neighbour distance.

    Every other measure here asks how far a point lies from the other cloud in
    any direction. M3C2 fixes the direction first - the local surface normal -
    and compares the two clouds only along it. The lower panel shares the upper
    panel's axis, so each cloud's points fall directly beneath the part of the
    cylinder they were taken from.
    """
    import numpy as np
    rng = np.random.default_rng(3)
    R, HALF, GAP, LOD = 3.0, 15.0, 6.0, 2.6          # cm

    yg = np.arange(-7.0, 7.1, 0.9)
    g = np.column_stack([rng.normal(0.0, 0.7, yg.size), yg])
    yr = np.arange(-7.0, 7.1, 0.7)
    r = np.column_stack([rng.normal(GAP, 0.9, yr.size), yr])
    inside = lambda p: (np.abs(p[:, 1]) <= R) & (np.abs(p[:, 0] - GAP) <= HALF)

    fig, (ax, bx) = plt.subplots(2, 1, figsize=(WIDTH_IN, WIDTH_IN * 0.52),
                                 sharex=True, gridspec_kw={"height_ratios": [1.75, 1]})

    ax.add_patch(plt.Rectangle((GAP - HALF, -R), 2 * HALF, 2 * R, facecolor="#f4f2ea",
                               edgecolor=INK, lw=0.9, zorder=1))
    for pts, c, m, s in ((g, REF_C, "x", 22), (r, REC_C, "o", 14)):
        out, inn = pts[~inside(pts)], pts[inside(pts)]
        ax.scatter(out[:, 0], out[:, 1], marker=m, s=s, c=c, alpha=0.25, lw=0.9, zorder=2)
        ax.scatter(inn[:, 0], inn[:, 1], marker=m, s=s, c=c, lw=0.9, zorder=4)
    ax.scatter([GAP], [0], marker="o", s=52, facecolor="white", edgecolor=INK,
               lw=1.2, zorder=5)
    ax.annotate("core point", xy=(GAP, R), xytext=(0, 8), textcoords="offset points",
                fontsize=7.5, color=INK, ha="center")
    ax.annotate("", xy=(GAP + 8.5, 0), xytext=(GAP, 0), zorder=6,
                arrowprops=dict(arrowstyle="->", color=INK, lw=1.3))
    ax.text(GAP + 9.2, 0.4, "n\u0302", fontsize=10, color=INK, style="italic")
    ax.annotate("", xy=(GAP - HALF, -R - 2.4), xytext=(GAP + HALF, -R - 2.4),
                arrowprops=dict(arrowstyle="<->", color=INK, lw=0.8))
    ax.text(GAP, -R - 5.0, "\u00b115 cm along n\u0302", fontsize=7.5, ha="center", color=INK)
    ax.annotate("", xy=(GAP - HALF - 2.4, -R), xytext=(GAP - HALF - 2.4, R),
                arrowprops=dict(arrowstyle="<->", color=INK, lw=0.8))
    ax.text(GAP - HALF - 3.2, 0, "d = 6 cm", fontsize=7.5, rotation=90, va="center",
            ha="right", color=INK)
    ax.set_ylim(-R - 9.5, 12.0); ax.set_aspect("equal")
    ax.set_yticks([])
    ax.tick_params(bottom=False, labelbottom=False)
    for s in ax.spines.values():
        s.set_visible(False)

    gi, ri = g[inside(g), 0], r[inside(r), 0]
    m1, m2 = ri.mean(), gi.mean()
    bx.axvspan(m1 - LOD, m1 + LOD, color=BAND, zorder=0)
    bx.scatter(ri, np.full(ri.size, 0.72), marker="o", s=14, c=REC_C, zorder=3)
    bx.scatter(gi, np.full(gi.size, 0.30), marker="x", s=22, c=REF_C, lw=0.9, zorder=3)
    for x, c in ((m1, REC_C), (m2, REF_C)):
        bx.axvline(x, color=c, lw=1.3, zorder=4)
    bx.annotate("", xy=(m2, 1.02), xytext=(m1, 1.02), zorder=5,
                arrowprops=dict(arrowstyle="<->", color=INK, lw=1.1))
    bx.text((m1 + m2) / 2, 1.10, "M3C2 distance", fontsize=7.5, ha="center", color=INK)
    bx.text(m1 + LOD + 0.4, 0.30, "LoD95, about the reconstruction mean",
            fontsize=7, color="#585d54", va="center")
    handles = [plt.Line2D([], [], color=REC_C, lw=1.3, marker="o", ms=4, mfc=REC_C,
                          mec=REC_C, label="reconstruction points and their mean"),
               plt.Line2D([], [], color=REF_C, lw=1.3, marker="x", ms=5, mec=REF_C,
                          mew=0.9, label="reference points and their mean")]
    bx.legend(handles=handles, loc="lower left", frameon=False, fontsize=7,
              handletextpad=0.4, borderpad=0.1)
    bx.set_ylim(-0.55, 1.35); bx.set_yticks([])
    bx.set_xlabel("position along n\u0302 (cm)", fontsize=8)
    bx.set_xlim(GAP - HALF - 5.5, GAP + HALF + 2.0)
    for s in ("left", "right", "top"):
        bx.spines[s].set_visible(False)
    fig.tight_layout()
    save(fig, "fig_4_2_m3c2")


def fig_4_3() -> None:
    """Voxel IoU, and what moving the grid does to it.

    The measure removes any dependence on point density by construction and
    introduces a dependence on where the grid begins. Both panels contain the
    same points; only the origin of the grid differs, and the score moves by
    twelve points. Section 5.8 measures that sensitivity on the real objects,
    across sixteen origins.
    """
    import numpy as np
    rng = np.random.default_rng(11)
    t = np.linspace(0, 2 * np.pi, 260)
    base = np.column_stack([4.6 * np.cos(t), 3.0 * np.sin(t)])
    G = base + rng.normal(0, 0.30, base.shape)
    R = base * 1.03 + np.array([0.55, 0.30]) + rng.normal(0, 0.42, base.shape)

    V = 2.5
    fig, axes = plt.subplots(1, 2, figsize=(WIDTH_IN, WIDTH_IN * 0.46),
                             sharex=True, sharey=True)
    for ax, off, lab in ((axes[0], 0.0, "one grid origin"),
                         (axes[1], 0.75 * V, "the same points, grid origin moved")):
        occ = lambda P: {tuple(q) for q in np.floor((P - off) / V).astype(int)}
        a, b = occ(R), occ(G)
        iou = len(a & b) / len(a | b)
        for cells, fc in ((b - a, "#cfd6cd"), (a - b, "#f0cfdc"), (a & b, "#8fa79a")):
            for cx, cy in cells:
                ax.add_patch(plt.Rectangle((cx * V + off, cy * V + off), V, V,
                                           facecolor=fc, edgecolor="#ffffff",
                                           lw=0.8, zorder=1))
        ax.scatter(G[:, 0], G[:, 1], marker="x", s=7, c=REF_C, lw=0.5, zorder=3)
        ax.scatter(R[:, 0], R[:, 1], marker="o", s=3.5, c=REC_C, zorder=3)
        ax.set_title(f"{lab}\nIoU = {iou:.2f}", fontsize=8.5)
        ax.set_aspect("equal"); ax.set_xticks([]); ax.set_yticks([])
        for s in ax.spines.values():
            s.set_visible(False)
    handles = [plt.Rectangle((0, 0), 1, 1, fc=c, ec="none", label=l)
               for c, l in (("#8fa79a", "occupied in both"),
                            ("#cfd6cd", "reference only"),
                            ("#f0cfdc", "reconstruction only"))]
    fig.legend(handles=handles, loc="lower center", bbox_to_anchor=(0.5, -0.03),
               ncol=3, frameon=False, fontsize=7.5, handlelength=1.2)
    fig.tight_layout()
    save(fig, "fig_4_3_voxel_iou")


def fig_5_6_iou_pairs() -> None:
    """Voxel IoU against F1 for all 36 method pairs, one point each.

    Section 5.8 compares the two measures one pair of methods at a time, because
    with all four at once a single near-tie rewrites the order for the whole
    object. That comparison is a list of counts in the text; this figure is the
    same comparison as a picture.

    Each pair is oriented so that the F1 difference is positive, which turns
    "do the two measures agree?" into "is the point above zero?" - the reader
    does not have to hold two signs in their head. The vertical bar is the range
    of the IoU difference over the sixteen grid origins, so a pair whose bar
    crosses zero is one the grid alone can reorder. Filled points are separated
    by both measures; open points are ties under at least one.

    IoU is read on the anchored grid, the same value Table 5.10 orders by.
    """
    iou_all, iou_anchored = _iou_by_run()
    recs = _f1_pairs()

    fig, ax = plt.subplots(figsize=(WIDTH_IN, WIDTH_IN * 0.62))
    ax.axhline(0, color="#585d54", lw=1.0, zorder=2)
    ink = "#585d54"
    n_both = n_agree = 0
    for r in recs:
        a, b, obj = r["a"], r["b"], r["object_id"]
        grids = [p - q for p, q in zip(iou_all[(obj, a)], iou_all[(obj, b)])]
        anchored = iou_anchored[(obj, a)] - iou_anchored[(obj, b)]
        f1_separates = not (r["lo"] <= 0 <= r["hi"])
        iou_separates = all(g > 0 for g in grids) or all(g < 0 for g in grids)
        s = 1 if r["d"] >= 0 else -1          # orient the pair by F1
        x, lo, hi = s * r["d"], s * r["lo"], s * r["hi"]
        if lo > hi:
            lo, hi = hi, lo
        y = s * anchored
        ylo, yhi = min(s * g for g in grids), max(s * g for g in grids)
        solid = f1_separates and iou_separates
        if solid:
            n_both += 1
            n_agree += y > 0
        ax.plot([lo, hi], [y, y], color=ink, lw=1.0, alpha=0.55, zorder=3)
        ax.plot([x, x], [ylo, yhi], color=ink, lw=1.0, alpha=0.55, zorder=3)
        ax.scatter(x, y, s=34, marker="o", zorder=4, linewidth=1.1,
                   color=ink if solid else "white", edgecolor=ink)

    ax.set_xlabel("Difference in F1 at 3 cm (percentage points)")
    ax.set_ylabel("Difference in voxel IoU at 5 cm (pp)")
    ax.grid(color="#e6e3d9", lw=0.7)
    ax.set_axisbelow(True)
    handles = [
        plt.Line2D([], [], color=ink, marker="o", ls="", mfc=ink, mec=ink,
                   ms=5.5, label="separated by both measures"),
        plt.Line2D([], [], color=ink, marker="o", ls="", mfc="white", mec=ink,
                   ms=5.5, label="tie under one measure or both"),
    ]
    ax.legend(handles=handles, loc="lower right", frameon=False,
              handletextpad=0.3)
    fig.tight_layout()
    save(fig, "fig_5_6_iou_pairs")
    print(f"  Figure 5.6 check: {n_both} pairs separated by both, "
          f"{n_agree} of them ordered the same way")


def _iou_by_run() -> tuple[dict, dict]:
    """Per-run voxel IoU at 5 cm: the sixteen grids, and the anchored one."""
    data = json.loads((TAB_DIR / "voxel_iou_summary.json").read_text())
    per_grid, anchored = {}, {}
    for r in data["rows"]:
        key = (r["object_id"], r["method"])
        per_grid[key] = r["shift_study"]["iou_all_pct"]
        anchored[key] = r["sweep"]["5cm"]["iou_pct"]
    return per_grid, anchored


def _f1_pairs() -> list[dict]:
    """The 36 pairwise F1 differences with their intervals (Appendix A)."""
    rows = _sheet(SRC_XLSX, "significance")
    head = next(i for i, r in enumerate(rows) if r and r[0] == "object_id")
    col = {n: i for i, n in enumerate(rows[head]) if n}
    out = []
    for r in rows[head + 1:]:
        if not r or not r[col["object_id"]]:
            continue
        out.append({
            "object_id": r[col["object_id"]],
            "a": r[col["method A"]], "b": r[col["method B"]],
            "d": r[col["ΔF1@3cm (pp)"]],
            "lo": r[col["95% CI low"]], "hi": r[col["95% CI high"]],
        })
    return out


def main() -> None:
    rows = load_rows()
    print(f"{len(rows)} runs from {SRC_XLSX.relative_to(ROOT)}")
    fig_4_1()
    fig_4_2()
    fig_4_3()
    table_5_1(rows)
    fig_5_1(rows)
    fig_5_1(rows, groups=True)   # slide-only variant
    fig_5_2(rows)
    fig_5_3_capture()
    fig_5_4_frames()
    fig_5_5_cost()
    fig_5_6_iou_pairs()
    print("Table 5.8 check:")
    cost_table()


if __name__ == "__main__":
    main()
