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

    # For the chart: one line per object, IoU averaged over its four methods at each voxel
    # size, with the grid-shift spread as a whisker. The spread is only measured at 5 cm (the
    # sensitivity sheet's grid sweep runs there), so the whisker is drawn at that point alone
    # rather than implied across the curve.
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
            "m3c2_reg_err_mm": m.get("rmse_inlier_mm"),
            "m3c2_corepoints": m.get("num_corepoints"),
            "iou_5cm": iou_row.get((r["object_id"], r["method"])),
            "acc_median_cm": r["accuracy median (cm)"],
            "comp_median_cm": r["completeness median (cm)"],
            # the symmetric Chamfer distance: half-sum of the two one-sided MEANS, which are
            # in the workbook beside it. Not derivable from the two medians shown here - the
            # note under the table says so, because a reader will otherwise try.
            "chamfer_sym_cm": r.get("symmetric Chamfer (cm)"),
            "rmse_mm": r["alignment RMSE (mm)"],
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
  table.summary { border-collapse:collapse; font-size:11.5px; min-width:1430px; }  /* 15 columns incl. M3C2 */
  table.summary th, table.summary td { padding:6px 8px; border-bottom:1px solid var(--panel-border); text-align:right; white-space:nowrap; }
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
  .bar { display:inline-block; height:7px; border-radius:3px; background:var(--accent); opacity:.75; vertical-align:1px; }
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
      clouds — identical to <span class="mono">docs/tables/summary_all_objects_accuracy_f1.xlsx</span> and to
      the “Main results” sheet of <span class="mono">FINAL_results.xlsx</span>.
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
            comparison from the reconstruction's side; the mirror run — core points on the LiDAR, where “no
            pair” instead means reference surface the reconstruction never covered — is in
            <span class="mono">docs/tables/m3c2_final_six.json</span>.
          </div>
        </details>
      </div>
    </div>
  </section>

  <hr class="sep" id="iou-sep" hidden>
  <section id="iou-section" hidden>
    <h2>Voxel IoU, and where it can be read</h2>
    <div class="subtitle" style="max-width:96ch">
      IoU asks a different question from F1 — how much of the occupied volume the two clouds share,
      rather than how far apart their surfaces are — and it depends on a voxel size and a grid origin
      that nothing in the data chooses for you. The curve below is that dependence: IoU per object,
      averaged over its four methods, at 2, 3, 5 and 10&nbsp;cm.
    </div>
    <div class="panel" style="max-width:760px;">
      <svg id="iou-chart" viewBox="0 0 700 330" style="width:100%; height:auto;"></svg>
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
    + `<th id="th-f1">F1@${thr}</th><th></th><th>95% CI</th><th id="th-acc">Acc@${thr}</th><th id="th-comp">Comp@${thr}</th>`
    + '<th>ΔF1@10−3</th>'
    + (diag
        ? '<th class="colsep">Acc med (cm)</th><th>Comp med (cm)</th>'
          + '<th title="symmetric Chamfer distance: the mean of the two one-sided MEANS (reconstruction'
          + ' to reference, and reference back), unsquared, in cm. Not the mean of the two medians in the'
          + ' columns to the left.">Chamfer (cm)</th>'
          + '<th>align RMSE (mm)</th>'
          + '<th class="colsep" title="voxel IoU at 5 cm against the reference. Read the stability note '
          + 'beside it: on the four objects with an incomplete reference the ranking it gives is not '
          + 'reproducible across grid offsets.">IoU@5cm (%)</th>'
        : '')
    + (DATA.has_m3c2
        ? '<th class="m3c2 colsep" title="median |M3C2| over the core points that found a counterpart">M3C2 |d| med (cm)</th>'
          + (diag
             ? '<th class="m3c2" title="core points whose |M3C2| exceeds their own LoD95 — a difference larger than '
               + 'the local roughness of both clouds plus the alignment error of that row">&gt; LoD95 (%)</th>'
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
        + `<td class="txt">${i === 0 ? `<a href="${obj.page}">${obj.name}</a>`
             + `<div class="note">${obj.size_cm.map(v => (v / 100).toFixed(2)).join(' × ')} m · ${obj.dbscan_mode}</div>` : ''}</td>`
        + `<td class="txt">${m.method}</td>`
        + `<td class="f1cell${isBest ? ' best-cell' : ''}">${fmt(f1)}</td>`
        + `<td style="width:78px; text-align:left;"><span class="bar" style="width:${Math.max(0, (f1 ?? 0)) * 0.7}px"></span></td>`
        + `<td class="mono ci-cell">${thr === '3cm' && m.f1_ci_lo != null
             ? `[${fmt(m.f1_ci_lo)}, ${fmt(m.f1_ci_hi)}]` : '—'}</td>`
        + `<td>${fmt(m[`acc_${thr}`])}</td><td>${fmt(m[`comp_${thr}`])}</td>`
        + `<td>${fmt(m.delta_10_3)}</td>`
        + (diag
            ? `<td class="colsep">${fmt(m.acc_median_cm, 2)}</td><td>${fmt(m.comp_median_cm, 2)}</td>`
              + `<td>${fmt(m.chamfer_sym_cm, 2)}</td><td>${fmt(m.rmse_mm)}</td>`
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

// IoU vs voxel size. One line per object - solid where the reference is complete and the
// ranking survives a grid shift, dashed where it does not - with the grid-shift spread as a
// whisker at 5 cm, the one size that sweep was run at. The point of the picture is that the
// metric has no natural scale: every object's IoU roughly doubles from 2 to 10 cm, so an IoU
// figure means nothing without the voxel it was measured at.
const IOU_COLORS = ['#c15c85', '#0d8054', '#5d63c7', '#1aacb3', '#e16b3e', '#8b9084'];

function renderIouChart() {
  const sweep = DATA.iou_sweep || {};
  const objects = DATA.objects.filter(o => sweep[o.id] && sweep[o.id].points.length);
  const sec = document.getElementById('iou-section'), sep = document.getElementById('iou-sep');
  if (!objects.length) return;
  sec.hidden = false; sep.hidden = false;

  const W = 700, H = 330, padL = 46, padR = 158, padT = 14, padB = 44;
  const plotW = W - padL - padR, plotH = H - padT - padB;
  const xs = [2, 3, 5, 10];
  const X = v => padL + (Math.log(v) - Math.log(2)) / (Math.log(10) - Math.log(2)) * plotW;
  const allY = objects.flatMap(o => sweep[o.id].points.map(p => p.iou_mean));
  const yHi = Math.min(100, Math.ceil((Math.max(...allY) + 6) / 10) * 10), yLo = 0;
  const Y = v => padT + plotH - (v - yLo) / (yHi - yLo) * plotH;
  const tick = cssvar('--text-faint'), dim = cssvar('--text-dim');

  let s = '';
  for (let y = yLo; y <= yHi; y += 10) {
    s += `<line x1="${padL}" y1="${Y(y)}" x2="${padL + plotW}" y2="${Y(y)}" stroke="${tick}" stroke-opacity="0.15"/>`;
    s += `<text x="${padL - 6}" y="${Y(y) + 3}" font-size="9.5" fill="${tick}" text-anchor="end">${y}</text>`;
  }
  for (const v of xs) {
    s += `<text x="${X(v).toFixed(1)}" y="${padT + plotH + 15}" font-size="9.5" fill="${dim}" text-anchor="middle">${v}</text>`;
  }
  s += `<text x="${(padL + plotW / 2).toFixed(1)}" y="${H - 8}" font-size="10" fill="${dim}" text-anchor="middle">voxel size (cm, log scale)</text>`;
  s += `<text x="12" y="${padT + plotH / 2}" font-size="10" fill="${dim}" transform="rotate(-90 12 ${padT + plotH / 2})" text-anchor="middle">IoU (%), mean over the four methods</text>`;

  objects.forEach((o, i) => {
    const d = sweep[o.id], col = IOU_COLORS[i % IOU_COLORS.length];
    const path = d.points.map((p, k) => `${k === 0 ? 'M' : 'L'}${X(p.voxel_cm).toFixed(1)},${Y(p.iou_mean).toFixed(1)}`).join(' ');
    s += `<path d="${path}" fill="none" stroke="${col}" stroke-width="1.6"`
      + `${d.complete_reference ? '' : ' stroke-dasharray="4,3"'}/>`;
    for (const p of d.points) {
      s += `<circle cx="${X(p.voxel_cm).toFixed(1)}" cy="${Y(p.iou_mean).toFixed(1)}" r="2.8" fill="${col}">`
        + `<title>${o.name} · ${p.voxel_cm} cm: IoU ${p.iou_mean.toFixed(1)}% (mean of ${p.n_methods} methods)</title></circle>`;
    }
    // grid-shift whisker, at the one voxel size the shift sweep was run at
    const five = d.points.find(p => p.voxel_cm === 5);
    if (five && d.grid_spread_pp) {
      const x = X(5), half = d.grid_spread_pp / 2;
      const yA = Y(five.iou_mean - half), yB = Y(five.iou_mean + half);
      s += `<line x1="${x.toFixed(1)}" y1="${yA.toFixed(1)}" x2="${x.toFixed(1)}" y2="${yB.toFixed(1)}" stroke="${col}" stroke-width="1.4" stroke-opacity="0.65"/>`;
      for (const yy of [yA, yB]) s += `<line x1="${(x-3).toFixed(1)}" y1="${yy.toFixed(1)}" x2="${(x+3).toFixed(1)}" y2="${yy.toFixed(1)}" stroke="${col}" stroke-width="1.4" stroke-opacity="0.65"/>`;
    }
  });

  // end-of-line labels, nudged apart: four of the six curves finish within a few points of
  // each other at 10 cm and their names landed on top of one another
  const labels = objects.map((o, i) => {
    const last = sweep[o.id].points[sweep[o.id].points.length - 1];
    return { name: o.name, col: IOU_COLORS[i % IOU_COLORS.length], x: X(last.voxel_cm) + 7, y: Y(last.iou_mean) + 3 };
  }).sort((a, b) => a.y - b.y);
  for (let i = 1; i < labels.length; i++) {
    if (labels[i].y - labels[i - 1].y < 11) labels[i].y = labels[i - 1].y + 11;
  }
  for (const l of labels) {
    s += `<text x="${l.x.toFixed(1)}" y="${l.y.toFixed(1)}" font-size="9.5" fill="${l.col}">${l.name}</text>`;
  }
  document.getElementById('iou-chart').innerHTML = s;

  const stable = objects.filter(o => sweep[o.id].order_stable).map(o => o.name);
  const shaky = objects.filter(o => !sweep[o.id].order_stable).map(o => o.name);
  document.getElementById('iou-legend').innerHTML =
    `solid = complete reference · dashed = incomplete · whisker at 5 cm = spread across 16 grid offsets`;
  document.getElementById('iou-note').innerHTML =
    `<b>Where IoU can be read as a ranking: ${stable.join(' and ')}.</b> There the reference is complete, `
    + `the IoU order matches the F1 order exactly (Spearman 1) and it holds at 3, 5 and 10 cm and on all 16 `
    + `grid offsets, with 2–5 points between methods. <b>On ${shaky.join(', ')} it cannot.</b> Those references `
    + `are incomplete, so the unscanned volume counts against every method; the orders disagree with F1 `
    + `(Spearman 0.4–0.8), the smallest gap between two methods falls to 0.03–0.2 points on some grids, and one `
    + `method moves up to 14 points across offsets on the bollard. That is why the column sits under `
    + `<i>diagnostics</i> with a per-object flag rather than beside F1. Full sweep: `
    + `<span class="mono">docs/tables/voxel_iou_summary.xlsx</span>.`;
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