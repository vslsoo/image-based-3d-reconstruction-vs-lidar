"""Build site/results.html - the main result of the dissertation on one page.

Six objects x four methods, Accuracy / Completeness / F1 at 3, 5 and 10 cm against the LiDAR
reference. The site had three study pages and six per-object pages, but nowhere to see the
headline table: those numbers existed only as prose on the index cards and scattered one
object at a time across the object pages.

Nothing is recomputed here. The rows are read straight out of
docs/tables/summary_all_objects_accuracy_f1_EN.xlsx (written by
build_accuracy_f1_summary_table.py, which computes them over the full clouds), so this page
cannot drift from the workbook the thesis cites - and it needs no open3d, so it rebuilds in
under a second.

The three M3C2 columns come the same way, from docs/tables/m3c2_final_six.json
(run_m3c2_final_six.py). M3C2 lives on this page and nowhere else on the site: it is
computed only on these six final objects, and on the two study pages - capture comparison,
frame count - a second metric would double the surface without answering the question those
pages ask. Missing file = the columns are simply left out.

Usage:
    python src/registration/build_results_page.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from openpyxl import load_workbook

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _site_nav import NAV_CSS, nav_html  # noqa: E402
from build_object_page import METHOD_ORDER  # noqa: E402  (the one place method order is decided)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_XLSX = PROJECT_ROOT / "docs" / "tables" / "summary_all_objects_accuracy_f1_EN.xlsx"
M3C2_JSON = PROJECT_ROOT / "docs" / "tables" / "m3c2_final_six.json"
IOU_XLSX = PROJECT_ROOT / "docs" / "tables" / "voxel_iou_summary.xlsx"
IOU_JSON = PROJECT_ROOT / "docs" / "tables" / "voxel_iou_summary.json"
OUT_HTML = PROJECT_ROOT / "site" / "results.html"

THRESHOLDS = ["3cm", "5cm", "10cm"]

# the labels the rest of the site uses; the workbook stores the internal ids
METHOD_LABEL = {"colmap": "COLMAP", "hloc_colmap": "hloc + COLMAP",
                "mast3r_ga": "MASt3R-GA", "vggt": "VGGT"}

# object_id -> the page it has on this site, and the name the index uses for it
OBJECT_PAGE = {
    "bus_stop_002": ("bus_stop.html", "bus shelter"),
    "information_sign_002": ("information_sign.html", "information sign"),
    "bench_004": ("bench.html", "bench"),
    "bollard_003": ("bollard.html", "bollard"),
    "flashlight_004": ("flashlight.html", "lamppost"),
    "bus_stop_sign_002": ("bus_stop_sign.html", "bus-stop sign"),
}


def read_rows() -> list[dict]:
    ws = load_workbook(SRC_XLSX)["summary"]
    hdr = [c.value for c in ws[1]]
    rows, current = [], None
    for raw in ws.iter_rows(min_row=2, values_only=True):
        r = dict(zip(hdr, raw))
        # the workbook writes the object id, shape and size once per group, on its first row
        if r["object_id"]:
            current = {k: r[k] for k in ("object_id", "shape", "ref. spacing (cm)", "length (cm)",
                                         "width (cm)", "height (cm)", "DBSCAN mode", "reference note")}
        row = {**current, **{k: v for k, v in r.items() if v is not None or k not in current}}
        row["object_id"] = current["object_id"]
        rows.append(row)
    return rows


def read_iou() -> tuple[dict, dict, dict]:
    """(per-row IoU@5cm, per-object stability, per-object sweep) from voxel_iou_summary.xlsx.

    IoU is reported here but kept out of the default view, and never without its stability
    flag: on the four objects whose reference is incomplete the ranking it produces does not
    survive a grid shift (see the `ranking` sheet - orders disagree with F1 at rho 0.4-0.8 and
    the smallest gap between two methods falls to 0.03-0.2 pp while one method moves up to
    14 pp across offsets). Missing file = the columns and the chart are simply left out.
    """
    if not IOU_XLSX.exists():
        print(f"  ! {IOU_XLSX.name} not found - building the page without IoU")
        return {}, {}, {}
    wb = load_workbook(IOU_XLSX)

    def rows(sheet):
        ws = wb[sheet]
        hdr = [c.value for c in ws[1]]
        out, cur = [], None
        for raw in ws.iter_rows(min_row=2, values_only=True):
            d = dict(zip(hdr, raw))
            if d.get("object_id"):
                cur = d["object_id"]
            if cur is None:
                continue
            d["object_id"] = cur
            out.append(d)
        return out

    per_row = {(r["object_id"], r["method"]): r["IoU@5cm (%)"] for r in rows("summary") if r.get("method")}

    stability = {}
    for r in rows("ranking"):
        # the sheet ends with free-text footer rows; they inherit the last object_id through
        # the carry-forward above and would otherwise overwrite that object's real verdict
        if r["object_id"] in stability or not r.get("IoU@5cm order (best first)"):
            continue
        stable = str(r.get("IoU order stable on every grid", "")).lower() == "yes" and \
                 str(r.get("orders agree", "")).lower() == "yes"
        stability[r["object_id"]] = {
            "stable": stable,
            "reference": r.get("reference"),
            "note": (f'reference {r.get("reference")}; IoU vs F1 order '
                     f'{"agrees" if str(r.get("orders agree","")).lower() == "yes" else "disagrees"} '
                     f'(Spearman {r.get("Spearman rho")}); smallest gap between methods on any grid '
                     f'{r.get("smallest gap on any grid (pp)")} pp; largest per-method spread across grids '
                     f'{r.get("largest per-method grid spread (pp)")} pp'),
        }

    # For the chart: the smallest gap between two adjacent methods, on each of the 16 grid
    # origins. This is the quantity the IoU verdict actually rests on, and the only honest way
    # to draw it. Two obvious alternatives both mislead. Averaging the methods (what this chart
    # showed at first) plots IoU against voxel size, which only says that bigger voxels overlap
    # more - it averages away the dimension the finding lives in. Drawing the four methods with
    # per-method grid-shift whiskers misleads the other way: on the lamppost the COLMAP-hloc gap
    # is 5.0 pp while each method's own spread across grids is 7.2, so the whiskers overlap and
    # the order looks unresolvable - but a grid shift moves every method together, so the order
    # holds on all 16 grids and the gap never falls below 3.91. Only the per-grid GAP shows that.
    per_grid_gaps: dict[str, dict] = {}
    if IOU_JSON.exists():
        by_obj: dict[str, dict[str, list]] = {}
        for r in json.loads(IOU_JSON.read_text()).get("rows", []):
            vals = (r.get("shift_study") or {}).get("iou_all_pct")
            if vals:
                by_obj.setdefault(r["object_id"], {})[r["method"]] = vals
        for obj_id, methods in by_obj.items():
            n = min(len(v) for v in methods.values())
            gaps = []
            for g in range(n):
                vals = sorted(m[g] for m in methods.values())
                gaps.append(round(min(b - a for a, b in zip(vals, vals[1:])), 3))
            per_grid_gaps[obj_id] = {
                "gaps": gaps,                     # index 0 is the true grid origin
                "nominal": gaps[0] if gaps else None,
                "min": min(gaps) if gaps else None,
                "n_grids": n,
                "n_methods": len(methods),
            }
    else:
        print(f"  ! {IOU_JSON.name} not found - the per-grid gap chart is left out")

    # kept for the note under the chart: the grid-shift spread of a single method

    spread = [r.get("grid shift: spread (pp)") for r in rows("sensitivity")]
    spread_by_obj: dict[str, list[float]] = {}
    for r in rows("sensitivity"):
        v = r.get("grid shift: spread (pp)")
        if v is not None:
            spread_by_obj.setdefault(r["object_id"], []).append(float(v))
    acc: dict[str, dict[float, list[float]]] = {}
    for r in rows("sweep"):
        if r.get("voxel (cm)") is None or r.get("IoU (%)") is None:
            continue
        acc.setdefault(r["object_id"], {}).setdefault(float(r["voxel (cm)"]), []).append(float(r["IoU (%)"]))
    sweep = {}
    for obj_id, by_voxel in acc.items():
        sp = spread_by_obj.get(obj_id, [])
        sweep[obj_id] = {
            "points": [{"voxel_cm": v, "iou_mean": round(sum(xs) / len(xs), 2), "n_methods": len(xs)}
                       for v, xs in sorted(by_voxel.items())],
            "grid_spread_pp": round(max(sp), 2) if sp else None,
            "complete_reference": str(stability.get(obj_id, {}).get("reference", "")).startswith("complete"),
            "order_stable": bool(stability.get(obj_id, {}).get("stable")),
            **(per_grid_gaps.get(obj_id, {})),
        }
    return per_row, stability, sweep


def read_m3c2() -> tuple[dict, dict]:
    """(object_id, method) -> that row's M3C2 figures, plus the run's parameters.

    Keyed on the capture id (bus_stop_002, ...) and the internal method id, which is what
    the workbook rows carry too. An absent file is not an error: the page then renders
    without the M3C2 columns rather than with empty ones."""
    if not M3C2_JSON.exists():
        print(f"  ! {M3C2_JSON.name} not found - building the page without the M3C2 columns")
        return {}, {}
    data = json.loads(M3C2_JSON.read_text())
    return {(r["capture_id"], r["method"]): r for r in data["rows"].values()}, data.get("params", {})


def page_data(rows: list[dict]) -> dict:
    m3c2, m3c2_params = read_m3c2()
    iou_row, iou_stability, iou_sweep = read_iou()
    objects: dict[str, dict] = {}
    for r in rows:
        obj = objects.setdefault(r["object_id"], {
            "id": r["object_id"],
            "page": OBJECT_PAGE.get(r["object_id"], ("", r["object_id"]))[0],
            "name": OBJECT_PAGE.get(r["object_id"], ("", r["object_id"]))[1],
            "shape": r["shape"],
            "size_cm": [r["length (cm)"], r["width (cm)"], r["height (cm)"]],
            "dbscan_mode": r["DBSCAN mode"],
            "ref_note": r["reference note"],
            "iou_order_stable": iou_stability.get(r["object_id"], {}).get("stable"),
            "iou_note": iou_stability.get(r["object_id"], {}).get("note"),
            "iou_reference": iou_stability.get(r["object_id"], {}).get("reference"),
            "methods": [],
        })
        m = m3c2.get((r["object_id"], r["method"]), {})
        obj["methods"].append({
            "method": METHOD_LABEL.get(r["method"], r["method"]),
            # M3C2, from docs/tables/m3c2_final_six.json - see read_m3c2()
            "m3c2_median_cm": m.get("median_abs_cm"),
            "m3c2_signif_pct": m.get("significant_pct"),
            "m3c2_unpaired_pct": m.get("unpaired_pct"),
            "m3c2_outside_pct": m.get("outside_pct"),
            "m3c2_reg_err_cm": (None if m.get("rmse_inlier_mm") is None
                                else round(m["rmse_inlier_mm"] / 10.0, 2)),
            "m3c2_corepoints": m.get("num_corepoints"),
            "iou_5cm": iou_row.get((r["object_id"], r["method"])),
            "acc_median_cm": r["accuracy median (cm)"],
            "comp_median_cm": r["completeness median (cm)"],
            # the symmetric Chamfer distance: half-sum of the two one-sided MEANS, which are
            # in the workbook beside it. Not derivable from the two medians shown here - the
            # note under the table says so, because a reader will otherwise try.
            "chamfer_sym_cm": r.get("symmetric Chamfer (cm)"),
            "rmse_cm": r["alignment RMSE (cm)"],
            "raw_points": r["raw points"],
            "matched_points": r["matched points (1cm voxel)"],
            "delta_10_3": r["ΔF1@10-3cm (pp)"],
            # 95% spatial block-bootstrap CIs, 3 cm only - the threshold the thesis quotes.
            # acc/comp intervals ride along for the accuracy x completeness figure.
            "f1_ci_lo": r.get("F1@3cm CI low"), "f1_ci_hi": r.get("F1@3cm CI high"),
            "acc_ci_lo": r.get("accuracy@3cm CI low"), "acc_ci_hi": r.get("accuracy@3cm CI high"),
            "comp_ci_lo": r.get("completeness@3cm CI low"), "comp_ci_hi": r.get("completeness@3cm CI high"),
            **{f"{m}_{t}": r[f"{name}@{t} (%)"]
               for t in THRESHOLDS
               for m, name in (("acc", "accuracy"), ("comp", "completeness"), ("f1", "F1"))},
        })
    # the workbook's rows already follow METHOD_ORDER, but sorting here keeps the page right
    # even when it is rebuilt against a workbook written before that order changed
    order = {METHOD_LABEL.get(m, m): i for i, m in enumerate(METHOD_ORDER)}
    for obj in objects.values():
        obj["methods"].sort(key=lambda m: order.get(m["method"], len(order)))
    return {"objects": list(objects.values()), "thresholds": THRESHOLDS,
            "has_m3c2": bool(m3c2), "m3c2_params": m3c2_params,
            "has_iou": bool(iou_row), "iou_sweep": iou_sweep}


HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Main results — 6 objects × 4 methods vs LiDAR</title>
</head>
<body>
<style>
  :root {
    --bg:#ffffff; --panel:#ffffff; --panel-border:#d7d4c8; --text:#181a17; --text-dim:#585d54; --text-faint:#8b9084;
    --accent:#17805f; --accent-soft:#d9ece3; --code-bg:#f5f4ef; --best:#0d8054; --best-soft:#e3f1ea; --red:#e16b3e;
  }
  @media (prefers-color-scheme: dark) {
    :root { --bg:#ffffff; --panel:#ffffff; --panel-border:#d7d4c8; --text:#181a17; --text-dim:#585d54;
            --text-faint:#8b9084; --accent:#17805f; --accent-soft:#d9ece3; --code-bg:#f5f4ef; --best:#0d8054;
            --best-soft:#e3f1ea; --red:#e16b3e; }
  }
  * { box-sizing:border-box; }
  body { margin:0; background:var(--bg); color:var(--text); line-height:1.45;
         font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif; }
  .page { max-width:1560px; margin:0 auto; padding:28px 24px 72px; display:flex; flex-direction:column; gap:22px; }
  a { color:var(--accent); }
  .eyebrow { font-size:11.5px; font-weight:600; letter-spacing:.09em; text-transform:uppercase; color:var(--accent); }
  h1 { font-size:23px; font-weight:650; margin:4px 0 2px; letter-spacing:-.01em; }
  h2 { font-size:19px; font-weight:650; margin:0 0 2px; }
  .subtitle { color:var(--text-dim); font-size:13.5px; max-width:92ch; }
  b, strong { color:var(--text); font-weight:600; }
  .mono { font-family:ui-monospace,"SF Mono","Cascadia Code",Menlo,Consolas,monospace; font-variant-numeric:tabular-nums; }
  section { display:flex; flex-direction:column; gap:12px; }
  hr.sep { border:none; border-top:1px solid var(--panel-border); margin:2px 0; }
  .tabs { display:flex; flex-wrap:wrap; gap:5px; }
  .tab-btn { font-family:inherit; font-size:10.5px; padding:3px 9px; border-radius:6px; border:1px solid var(--panel-border);
             background:transparent; color:var(--text-dim); cursor:pointer; }
  .tab-btn:hover { border-color:var(--accent); color:var(--text); }
  .tab-btn.active { background:var(--accent-soft); border-color:var(--accent); color:var(--text); font-weight:600; }
  .grid-wrap { overflow-x:auto; }
  /* Was pinned at 1430px for the widest layout, which held the compact view that wide too and
     pushed "no pair" off a 1440px screen. The compact view needs ~1050; the diagnostics view is
     wider than any laptop and scrolls inside .grid-wrap, which is what that wrapper is for. */
  table.summary { border-collapse:collapse; font-size:11.5px; min-width:1050px; }
  table.summary th, table.summary td { padding:6px 8px; border-bottom:1px solid var(--panel-border); text-align:right; white-space:nowrap; }
  /* headers wrap instead of forcing their column wide: "M3C2 |d| med (cm)" on one line cost
     184 px and pushed "no pair" off a 1440 px screen */
  table.summary th { white-space:normal; line-height:1.25; }
  table.summary td.obj { white-space:normal; max-width:170px; overflow-wrap:anywhere; }
  table.summary th { font-weight:650; color:var(--text-dim); position:sticky; top:0; background:var(--panel); }
  table.summary td.txt, table.summary th.txt { text-align:left; }
  table.summary td.f1cell { font-weight:700; font-variant-numeric:tabular-nums; }
  table.summary tr.best td.f1cell { color:var(--best); }
  table.summary td.best-cell { background:var(--best-soft); border-radius:4px; }
  table.summary tbody tr:hover { background:color-mix(in srgb, var(--accent-soft) 40%, transparent); }
  .grouprule td { border-top:2px solid var(--panel-border); }
  .note { font-size:11.5px; color:var(--text-faint); }
  .ci-cell { color:var(--text-faint); font-size:11px; }
  .iou-flag { display:block; font-size:9.5px; font-weight:600; letter-spacing:.02em; }
  .iou-flag.ok { color:var(--best); }
  .iou-flag.weak { color:var(--red); font-weight:500; }
  /* the F1 cell carries its own bar as a background, so the chart costs no column. The best
     value per object is then marked by colour rather than by a background, which the bar now
     occupies. */
  :root { --bar-soft:#dcece5; }
  table.summary td.f1cell { background-size:100% 62%; background-position:left center; }
  table.summary td.f1cell.best-cell { color:var(--best); font-weight:800; }
  .chip { display:inline-block; font-size:11px; color:var(--text-dim); background:var(--code-bg);
          border:1px solid var(--panel-border); border-radius:20px; padding:2px 10px; }
  /* the M3C2 block: separated because, unlike everything to its left, it does not move with t */
  table.summary th.colsep, table.summary td.colsep { border-left:1px solid var(--panel-border); }
  table.summary th.m3c2, table.summary td.m3c2 { background:color-mix(in srgb, var(--code-bg) 60%, transparent); }
  table.summary td.warn { color:var(--red); font-weight:600; }
  .legend { display:flex; flex-wrap:wrap; gap:6px 16px; align-items:baseline; }
__NAV_CSS__
</style>

<div class="page">
  __SITE_NAV__
  <div>
    <div class="eyebrow">Main results · gap-aware Chamfer vs the LiDAR reference</div>
    <h1>Six objects, four methods, one table</h1>
    <div class="subtitle">
      Every reconstruction on this site, scored the same way: density-matched onto the reference's
      1&nbsp;cm grid, source↔target Chamfer distances, gap-aware Accuracy / Completeness / F1. Each object
      uses the gap-detection setting its own page defaults to, and the numbers are computed over the full
      clouds, and identical to the figures reported in the dissertation.
    </div>
  </div>

  <hr class="sep">
  <section>
    <div style="display:flex; align-items:baseline; gap:14px; flex-wrap:wrap;">
      <h2 id="table-title">Accuracy, Completeness and F1 at 3&nbsp;cm</h2>
      <div class="tabs" id="thr-toggle">
        <button class="tab-btn active" data-thr="3cm">3 cm</button>
        <button class="tab-btn" data-thr="5cm">5 cm</button>
        <button class="tab-btn" data-thr="10cm">10 cm</button>
      </div>
      <div class="tabs"><button class="tab-btn" id="diag-toggle">+ diagnostics</button></div>
    </div>
    <div class="subtitle">
      Best F1 per object is highlighted. <b>ΔF1@10−3</b> is how much F1 recovers when the threshold widens
      from 3 to 10&nbsp;cm: small means the surface is already where it should be, large means it is there
      but displaced — and a row that stays low even at 10&nbsp;cm never reconstructed that geometry at all.
    </div>
    <div class="grid-wrap"><div id="table-wrap"></div></div>
    <div class="note" id="table-note"></div>
    <div class="note" style="max-width:104ch;">
      <b>On the Chamfer column.</b> Accuracy and completeness are the two one-sided halves of the
      Chamfer distance, so the metric was here all along, split in two; the <b>Chamfer</b> column is
      the mean of those two one-sided <i>means</i>, in centimetres and unsquared.
      <details style="margin-top:5px;">
        <summary style="cursor:pointer;">Why the thresholded figures stay primary, and one caution before quoting it</summary>
        <div style="margin-top:6px;">
          It is the mean of the two one-sided means, not of the two medians beside it. Where the reference
          itself is incomplete, a raw symmetric distance is dominated by the regions the scanner never
          reached rather than by the quality of the reconstruction — which is exactly what the gap-aware
          thresholds to its left are for, so those stay the primary result. And papers on learned
          reconstruction, VGGT and MASt3R among them, usually report a <i>squared</i> Chamfer: those
          figures do not line up with these.
        </div>
      </details>
    </div>
    <div class="note" id="m3c2-note" hidden>
      <span class="chip" id="m3c2-chip"></span>
      <div style="margin-top:7px; max-width:104ch;">
        <b>M3C2 measures along each point's own surface normal, has no threshold and uses no gap exclusion</b>,
        so the three columns do not follow the 3/5/10&nbsp;cm toggle. The one to read is <b>no pair</b>: the
        share of core points that found nothing to measure against, which is where a method that put its
        points off the reference surface shows up and nowhere else in this table.
        <details style="margin-top:5px;">
          <summary style="cursor:pointer;">How the pairing works, and which side the numbers are read from</summary>
          <div style="margin-top:6px;">
            A core point beside a hole in the reference finds nothing inside its search cylinder and leaves
            the statistics rather than being scored — so the median distance is a median over the points that
            <i>did</i> pair, and two rows with different “no pair” shares are medians over different parts of
            the object. <span class="mono">registration_error</span> is not one constant for all rows: each
            row is given its own alignment RMSE, the column immediately to the left. These three read the
            comparison from the reconstruction's side. The mirror run — core points on the LiDAR, where “no
            pair” instead means reference surface the reconstruction never covered — was computed as well and
            is reported in the dissertation.
          </div>
        </details>
      </div>
    </div>
  </section>

  <hr class="sep" id="iou-sep" hidden>
  <section id="iou-section" hidden>
    <h2>Voxel IoU, and where it can be read</h2>
    <div class="subtitle" style="max-width:96ch">
      IoU asks a different question from F1 — how much of the occupied volume the two clouds share, rather
      than how far apart their surfaces are — but it depends on a voxel size and on where the grid happens
      to start, and nothing in the data chooses either. The question that decides whether it can be used
      as a ranking is therefore: <b>how far apart are two neighbouring methods, compared with how much a
      grid shift moves them?</b> Each row below is one object, each dot one of 16 grid origins, and the
      value is the smallest gap between two adjacent methods on that grid.
    </div>
    <div class="panel" style="max-width:760px;">
      <svg id="iou-chart" viewBox="0 0 700 280" style="width:100%; height:auto;"></svg>
      <div id="iou-legend" style="font-size:11px; color:var(--text-dim); margin-top:6px;"></div>
    </div>
    <div class="note" id="iou-note" style="max-width:96ch;"></div>
  </section>
</div>

<script type="application/json" id="page-data">__PAYLOAD__</script>
<script>
const DATA = JSON.parse(document.getElementById('page-data').textContent);
let thr = '3cm';

function fmt(v, d = 1) { return v == null ? '—' : (+v).toFixed(d); }

// The three M3C2 cells. "no pair" is flagged once it passes half the core points: at that
// point the row is no longer "off by x cm", it is a cloud whose surface is largely somewhere
// the reference's surface is not, and the median beside it only describes the half that did
// find a counterpart.
// median and "no pair" always travel together - see buildTable()'s note. Only "> LoD95" is
// diagnostics-only.
function m3c2Cells(m, diag) {
  const unpaired = m.m3c2_unpaired_pct;
  return `<td class="m3c2 colsep">${fmt(m.m3c2_median_cm, 2)}</td>`
    + (diag ? `<td class="m3c2">${fmt(m.m3c2_signif_pct)}</td>` : '')
    + `<td class="m3c2${unpaired != null && unpaired >= 50 ? ' warn' : ''}" title="${
        m.m3c2_corepoints ? Math.round(m.m3c2_corepoints * (unpaired ?? 0) / 100).toLocaleString('en-US')
          + ' of ' + m.m3c2_corepoints.toLocaleString('en-US') + ' core points' : ''}">${fmt(unpaired)}</td>`;
}

// IoU with the one thing that has to be read with it: whether the ranking it gives is stable.
// On the four objects whose reference is incomplete it is not - orders disagree with F1
// (Spearman 0.4-0.8) and the gap between methods drops to 0.03-0.2 pp on some grid offsets,
// while a single method moves up to 14 pp across offsets. A bare number would be read as a
// ranking it cannot support.
function iouCell(obj, m) {
  const iou = m.iou_5cm;
  if (iou == null) return '<td class="colsep">—</td>';
  const stable = obj.iou_order_stable;
  return `<td class="colsep" title="${obj.iou_note || ''}">${fmt(iou)}`
    + `<span class="iou-flag ${stable ? 'ok' : 'weak'}">${stable ? 'order stable' : 'order not resolvable'}</span></td>`;
}

// Sixteen columns did not fit a laptop screen, and "no pair" - the most diagnostic of them -
// was the one that fell off the right edge. Two views instead: the scores by default, the rest
// behind a toggle. The two M3C2 columns that must not be separated stay together in BOTH: a
// median over paired points only, read without the share that paired, ranks COLMAP worst on the
// bus-stop sign (3.66 cm over 90% of its points) where it is in fact the best method there.
let showDiagnostics = false;

function buildTable() {
  const diag = showDiagnostics;
  let h = '<table class="summary"><thead><tr>'
    + '<th class="txt">Object</th><th class="txt">Method</th>'
    + `<th id="th-f1">F1@${thr}</th><th>95% CI</th><th id="th-acc">Acc@${thr}</th><th id="th-comp">Comp@${thr}</th>`
    + '<th>ΔF1@10−3</th>'
    // Chamfer is the metric people arrive looking for by name, and the paragraph explaining it
    // is printed unconditionally - so the column belongs in the default view, next to ΔF1.
    // align RMSE went the other way: it describes the registration, not the reconstruction,
    // and the chapter does not quote it.
    + '<th title="symmetric Chamfer distance: the mean of the two one-sided MEANS (reconstruction'
    + ' to reference, and reference back), unsquared, in cm. Not the mean of the two medians.">Chamfer<br>(cm)</th>'
    + (diag
        ? '<th class="colsep">Acc med (cm)</th><th>Comp med (cm)</th>'
          + '<th>align RMSE (cm)</th>'
          + '<th class="colsep" title="voxel IoU at 5 cm against the reference. Read the stability note '
          + 'beside it: on the four objects with an incomplete reference the ranking it gives is not '
          + 'reproducible across grid offsets.">IoU@5cm (%)</th>'
        : '')
    + (DATA.has_m3c2
        ? '<th class="m3c2 colsep" title="median |M3C2| over the core points that found a counterpart">M3C2 |d|<br>med (cm)</th>'
          + (diag
             ? '<th class="m3c2" title="core points whose |M3C2| exceeds their own LoD95 — a difference larger than '
               + '1.96 × (local roughness of both clouds + the alignment error of that row). The 95% factor '
               + 'covers the alignment error too, so with the alignment RMSE in the column to the left this '
               + 'threshold cannot drop below about 2.3–4.3 cm however smooth the surface is.">&gt; LoD95 (%)</th>'
             : '')
          + '<th class="m3c2" title="core points with no reference point inside their search cylinder at all — '
          + 'reconstruction surface that is not where the reference surface is. Always shown beside the median: '
          + 'the median is taken over the points that DID pair, so two rows with different shares here are '
          + 'medians over different parts of the object.">no pair (%)</th>'
        : '')
    + (diag ? '<th class="colsep">#pts raw→matched</th>' : '')
    + '</tr></thead><tbody>';
  for (const obj of DATA.objects) {
    const best = Math.max(...obj.methods.map(m => m[`f1_${thr}`] ?? 0));
    obj.methods.forEach((m, i) => {
      const isBest = (m[`f1_${thr}`] ?? 0) === best;
      const f1 = m[`f1_${thr}`];
      h += `<tr${i === 0 ? ' class="grouprule"' : ''}${isBest ? ' style="font-weight:500"' : ''}>`
        + `<td class="txt obj">${i === 0 ? `<a href="${obj.page}">${obj.name}</a>`
             + `<div class="note">${obj.size_cm.map(v => (v / 100).toFixed(2)).join(' × ')} m · ${obj.dbscan_mode}</div>` : ''}</td>`
        + `<td class="txt">${m.method}</td>`
        // the bar was its own column; as a background of the F1 cell it costs no width at all
        + `<td class="f1cell${isBest ? ' best-cell' : ''}" style="background-image:linear-gradient(to right,`
        + ` var(--bar-soft) ${Math.max(0, Math.min(100, f1 ?? 0)).toFixed(0)}%, transparent 0);`
        + ` background-repeat:no-repeat;">${fmt(f1)}</td>`
        + `<td class="mono ci-cell">${thr === '3cm' && m.f1_ci_lo != null
             ? `[${fmt(m.f1_ci_lo)}, ${fmt(m.f1_ci_hi)}]` : '—'}</td>`
        + `<td>${fmt(m[`acc_${thr}`])}</td><td>${fmt(m[`comp_${thr}`])}</td>`
        + `<td>${fmt(m.delta_10_3)}</td>`
        + `<td>${fmt(m.chamfer_sym_cm, 2)}</td>`
        + (diag
            ? `<td class="colsep">${fmt(m.acc_median_cm, 2)}</td><td>${fmt(m.comp_median_cm, 2)}</td>`
              + `<td>${fmt(m.rmse_cm)}</td>`
              + iouCell(obj, m)
            : '')
        + (DATA.has_m3c2 ? m3c2Cells(m, diag) : '')
        + (diag ? `<td class="mono colsep">${(m.raw_points ?? 0).toLocaleString('en-US')}→${(m.matched_points ?? 0).toLocaleString('en-US')}</td>` : '')
        + '</tr>';
    });
  }
  h += '</tbody></table>';
  document.getElementById('table-wrap').innerHTML = h;
  document.getElementById('table-title').innerHTML =
    `Accuracy, Completeness and F1 at ${thr.replace('cm', '&nbsp;cm')}`;

  // one line of context that follows the threshold, rather than a paragraph that cannot
  const rows = DATA.objects.flatMap(o => o.methods.map(m => ({ obj: o, m })));
  const top = rows.reduce((a, b) => (b.m[`f1_${thr}`] ?? 0) > (a.m[`f1_${thr}`] ?? 0) ? b : a);
  const bottom = rows.reduce((a, b) => (b.m[`f1_${thr}`] ?? 0) < (a.m[`f1_${thr}`] ?? 0) ? b : a);
  document.getElementById('table-note').innerHTML =
    `At ${thr}: best is <b>${top.obj.name} · ${top.m.method}</b> at ${fmt(top.m[`f1_${thr}`])}%, `
    + `worst is <b>${bottom.obj.name} · ${bottom.m.method}</b> at ${fmt(bottom.m[`f1_${thr}`])}%. `
    + `Four of the six references are incomplete (parts were never scanned); those gaps are excluded by `
    + `DBSCAN at each object's own setting, shown under its name — see the `
    + `<a href="tuner.html">gap tuner</a> for what that line depends on.`;
}

// What the IoU verdict actually rests on: the smallest gap between two adjacent methods,
// measured on each of the 16 grid origins. One row per object, 16 dots.
//
// The two charts this replaced would both have misled. IoU averaged over the methods only
// shows that bigger voxels overlap more, and averages away the ranking entirely. Four
// per-method lines with grid-shift whiskers mislead the other way: on the lamppost each
// method moves 7.2 pp across grids while the COLMAP-hloc gap is 5.0, so the whiskers overlap
// and the order looks unresolvable - but the shift moves every method together, and the order
// in fact holds on all 16 grids. The gap between methods is what survives that common shift,
// so it is the thing to plot.
const IOU_OK = '--best', IOU_WEAK = '--red';

function renderIouChart() {
  const sweep = DATA.iou_sweep || {};
  const objects = DATA.objects.filter(o => (sweep[o.id] || {}).gaps && sweep[o.id].gaps.length);
  const sec = document.getElementById('iou-section'), sep = document.getElementById('iou-sep');
  if (!objects.length) return;
  sec.hidden = false; sep.hidden = false;

  const rowH = 34, padL = 118, padR = 74, padT = 22;
  const W = 700, H = padT + objects.length * rowH + 46, plotW = W - padL - padR;
  const all = objects.flatMap(o => sweep[o.id].gaps);
  const lo = Math.min(...all) * 0.6, hi = Math.max(...all) * 1.5;
  const X = v => padL + (Math.log(Math.max(v, lo)) - Math.log(lo)) / (Math.log(hi) - Math.log(lo)) * plotW;
  const tick = cssvar('--text-faint'), dim = cssvar('--text-dim');

  let s = '';
  for (const t of [0.05, 0.1, 0.5, 1, 5, 10]) {
    if (t < lo || t > hi) continue;
    s += `<line x1="${X(t).toFixed(1)}" y1="${padT - 8}" x2="${X(t).toFixed(1)}" y2="${padT + objects.length * rowH - 8}" stroke="${tick}" stroke-opacity="0.16"/>`;
    s += `<text x="${X(t).toFixed(1)}" y="${padT + objects.length * rowH + 8}" font-size="9.5" fill="${tick}" text-anchor="middle">${t}</text>`;
  }
  s += `<text x="${(padL + plotW / 2).toFixed(1)}" y="${H - 8}" font-size="10" fill="${dim}" text-anchor="middle">smallest gap between two adjacent methods (percentage points, log scale)</text>`;

  objects.forEach((o, i) => {
    const d = sweep[o.id];
    const y = padT + i * rowH + 6;
    const col = cssvar(d.order_stable ? IOU_OK : IOU_WEAK);
    s += `<text x="${padL - 10}" y="${y + 3.5}" font-size="10.5" fill="${dim}" text-anchor="end">${o.name}</text>`;
    s += `<line x1="${X(Math.min(...d.gaps)).toFixed(1)}" y1="${y}" x2="${X(Math.max(...d.gaps)).toFixed(1)}" y2="${y}" stroke="${col}" stroke-width="1.2" stroke-opacity="0.35"/>`;
    d.gaps.forEach((g, k) => {
      // a touch of vertical jitter so 16 dots do not stack into one
      const jy = y + ((k % 5) - 2) * 1.9;
      s += `<circle cx="${X(g).toFixed(1)}" cy="${jy.toFixed(1)}" r="2.5" fill="${col}" fill-opacity="0.5">`
        + `<title>${o.name} · grid ${k + 1} of ${d.n_grids}: smallest gap ${g.toFixed(2)} pp</title></circle>`;
    });
    const worst = Math.min(...d.gaps);
    s += `<circle cx="${X(worst).toFixed(1)}" cy="${y}" r="3.6" fill="none" stroke="${col}" stroke-width="1.6"/>`;
    s += `<text x="${(padL + plotW + 8).toFixed(1)}" y="${y + 3.5}" font-size="9.5" fill="${col}" font-weight="${d.order_stable ? 650 : 400}">min ${worst.toFixed(2)}</text>`;
  });
  document.getElementById('iou-chart').innerHTML = s;

  const stable = objects.filter(o => sweep[o.id].order_stable);
  const shaky = objects.filter(o => !sweep[o.id].order_stable);
  const fmtList = arr => arr.map(o => `${o.name} (${Math.min(...sweep[o.id].gaps).toFixed(2)})`).join(', ');
  document.getElementById('iou-legend').innerHTML =
    `each dot is one of the ${objects[0] ? sweep[objects[0].id].n_grids : 16} grid origins · ring = the worst of them · `
    + `<span style="color:${cssvar(IOU_OK)}">green</span> = the IoU order holds on every grid, `
    + `<span style="color:${cssvar(IOU_WEAK)}">red</span> = it does not`;
  document.getElementById('iou-note').innerHTML =
    `<b>The two groups separate by an order of magnitude.</b> On ${fmtList(stable)} — the objects whose reference `
    + `is complete — two methods are never closer than about a point, the IoU order matches the F1 order exactly `
    + `(Spearman 1) and it survives every grid origin, so IoU can be read as a ranking there. On ${fmtList(shaky)} `
    + `the smallest gap collapses to hundredths of a point on some grids: the ranking those objects produce is an `
    + `artefact of where the grid happens to start, and their references are incomplete as well, so the unscanned `
    + `volume counts against every method. That is why the column sits under <i>diagnostics</i> with a per-object `
    + `flag rather than beside F1. A caveat that applies everywhere: IoU has no natural scale — each object's IoU `
    + `roughly doubles from a 2 cm voxel to a 10 cm one, so the number means nothing without its voxel size.`;
}

function cssvar(v) { return getComputedStyle(document.documentElement).getPropertyValue(v).trim(); }

const diagBtn = document.getElementById('diag-toggle');
diagBtn.addEventListener('click', () => {
  showDiagnostics = !showDiagnostics;
  diagBtn.classList.toggle('active', showDiagnostics);
  diagBtn.textContent = showDiagnostics ? '− diagnostics' : '+ diagnostics';
  buildTable();
});

document.querySelectorAll('#thr-toggle .tab-btn').forEach(b => b.addEventListener('click', () => {
  document.querySelectorAll('#thr-toggle .tab-btn').forEach(x => x.classList.remove('active'));
  b.classList.add('active');
  thr = b.dataset.thr;
  buildTable();
}));

// the parameters the M3C2 columns were computed at, in the same chip style the study pages use
if (DATA.has_m3c2) {
  const p = DATA.m3c2_params || {};
  document.getElementById('m3c2-chip').textContent =
    `M3C2: D=${((p.normal_scale_D_m ?? 0) * 100).toFixed(0)} cm · d=${((p.projection_scale_d_m ?? 0) * 100).toFixed(0)} cm`
    + ` · core points ${((p.corepoint_voxel_m ?? 0) * 100).toFixed(0)} cm · reg.err = each row's own alignment RMSE`;
  document.getElementById('m3c2-note').hidden = false;
}

buildTable();
renderIouChart();
</script>
</body>
</html>
"""


def main() -> None:
    rows = read_rows()
    data = page_data(rows)
    html = (HTML.replace("__NAV_CSS__", NAV_CSS)
                .replace("__SITE_NAV__", nav_html("results"))
                .replace("__PAYLOAD__", json.dumps(data).replace("</", "<\\/")))
    OUT_HTML.write_text(html, encoding="utf-8")
    n = sum(len(o["methods"]) for o in data["objects"])
    print(f"Wrote {OUT_HTML.relative_to(PROJECT_ROOT)} "
          f"({len(data['objects'])} objects, {n} rows, {OUT_HTML.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    sys.exit(main())