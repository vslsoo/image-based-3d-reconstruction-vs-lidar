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
from _site_nav import NAV_CSS, SITE_CREDIT, nav_html  # noqa: E402
from build_object_page import METHOD_ORDER  # noqa: E402  (the one place method order is decided)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_XLSX = PROJECT_ROOT / "docs" / "tables" / "summary_all_objects_accuracy_f1_EN.xlsx"
M3C2_JSON = PROJECT_ROOT / "docs" / "tables" / "m3c2_final_six.json"
IOU_XLSX = PROJECT_ROOT / "docs" / "tables" / "voxel_iou_summary.xlsx"
IOU_JSON = PROJECT_ROOT / "docs" / "tables" / "voxel_iou_summary.json"
# the `significance` block: 95% block-bootstrap CI on the F1@3cm gap of every method pair
F1_JSON = PROJECT_ROOT / "docs" / "tables" / "summary_all_objects_accuracy_f1.json"
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


def read_iou() -> dict:
    """(object_id, method) -> IoU@5cm, from the `summary` sheet of voxel_iou_summary.xlsx.

    The value only; what may be concluded from it is decided pair by pair in
    read_iou_pairs(). Missing file = the column and the chart are simply left out.
    """
    if not IOU_XLSX.exists():
        print(f"  ! {IOU_XLSX.name} not found - building the page without IoU")
        return {}
    ws = load_workbook(IOU_XLSX)["summary"]
    hdr = [c.value for c in ws[1]]
    per_row, cur = {}, None
    for raw in ws.iter_rows(min_row=2, values_only=True):
        d = dict(zip(hdr, raw))
        if d.get("object_id"):
            cur = d["object_id"]
        if cur and d.get("method"):
            per_row[(cur, d["method"])] = d["IoU@5cm (%)"]
    return per_row


def read_iou_pairs() -> list[dict]:
    """One record per pair of methods on one object: how far apart F1@3cm puts the two, how
    far apart IoU@5cm puts them, and whether either metric can separate them at all.

    This is the comparison the section exists to make, and the pair - not the object - is the
    unit that can carry it. IoU's job here is not to produce a second ranking: it is to check
    the F1 ranking with a metric that point density cannot flatter, since a voxel is occupied
    by one point and by ten thousand alike. An ordering cannot answer that, because an
    ordering throws away how far apart the methods were - a 0.3 pp swap between two tied
    methods comes out looking exactly like a real reversal.

    Each pair therefore gets both gaps together with the uncertainty already computed for each
    elsewhere in the project:
      - dF1@3cm with its 95% spatial block-bootstrap CI (the `significance` block of
        summary_all_objects_accuracy_f1.json). CI crosses zero -> F1 does not separate the pair.
      - dIoU@5cm recomputed on each of the 16 grid origins of the shift study. The gap, not
        the value, is the quantity that survives a shift: an origin shift moves every method
        on an object in the same direction, so each method's own spread overstates the doubt
        (on the lamppost every method moves up to 7.2 pp while the COLMAP-hloc gap never falls
        below 3.9) whereas the gap does not. Sign not constant over the 16 -> IoU does not
        separate the pair.

    Every pair is oriented so dF1 >= 0: the method F1 prefers is named first, so a positive
    dIoU means IoU agrees, and the chart's y = 0 line is the entire verdict.
    """
    if not (IOU_JSON.exists() and F1_JSON.exists()):
        missing = [p.name for p in (IOU_JSON, F1_JSON) if not p.exists()]
        print(f"  ! {', '.join(missing)} not found - building the page without the IoU chart")
        return []

    iou_rows: dict[str, dict[str, dict]] = {}
    for r in json.loads(IOU_JSON.read_text()).get("rows", []):
        if (r.get("shift_study") or {}).get("iou_all_pct"):
            iou_rows.setdefault(r["object_id"], {})[r["method"]] = r
    sig = {(s["object_id"], s["method_a"], s["method_b"]): s
           for s in json.loads(F1_JSON.read_text()).get("significance", [])}

    out = []
    for obj_id, methods in iou_rows.items():
        for i, a in enumerate(sorted(methods)):
            for b in sorted(methods)[i + 1:]:
                s = sig.get((obj_id, a, b)) or sig.get((obj_id, b, a))
                if s is None:
                    continue
                # the significance block stores one direction per pair; flip it onto (a, b)
                flip = s["method_a"] != a
                d_f1 = -s["delta"] if flip else s["delta"]
                lo, hi = (-s["ci_hi"], -s["ci_lo"]) if flip else (s["ci_lo"], s["ci_hi"])
                ga = methods[a]["shift_study"]["iou_all_pct"]
                gb = methods[b]["shift_study"]["iou_all_pct"]
                gaps = [x - y for x, y in zip(ga, gb)]
                d_iou = methods[a]["iou_pct"] - methods[b]["iou_pct"]
                d_f1_5 = methods[a]["f1_5cm_pct"] - methods[b]["f1_5cm_pct"]
                better, worse = a, b
                if d_f1 < 0:      # orient on F1, so the chart's upper half means "IoU agrees"
                    d_f1, lo, hi = -d_f1, -hi, -lo
                    gaps = [-g for g in gaps]
                    d_iou, d_f1_5, better, worse = -d_iou, -d_f1_5, b, a
                out.append({
                    "object": OBJECT_PAGE.get(obj_id, ("", obj_id))[1],
                    "better": METHOD_LABEL.get(better, better),
                    "worse": METHOD_LABEL.get(worse, worse),
                    "df1": round(d_f1, 2), "f1_lo": round(lo, 2), "f1_hi": round(hi, 2),
                    "diou": round(d_iou, 2),
                    "iou_lo": round(min(gaps), 2), "iou_hi": round(max(gaps), 2),
                    "n_grids": len(gaps),
                    # "tie" = this metric cannot say which of the two is better
                    "f1_tie": bool(s["includes_zero"]),
                    "iou_tie": not (all(g > 0 for g in gaps) or all(g < 0 for g in gaps)),
                    # F1's own ordering of this pair at the next threshold up: the yardstick the
                    # note uses, since IoU has to be judged against how steady F1 itself is
                    "f1_5cm_flips": d_f1_5 < 0,
                })
    order = {name: i for i, (_, name) in enumerate(OBJECT_PAGE.values())}
    out.sort(key=lambda p: (order.get(p["object"], len(order)), -p["df1"]))
    return out


def iou_object_summary(pairs: list[dict]) -> dict[str, dict]:
    """Per object: of its 6 method pairs, how many IoU confirms, and how many it contradicts.

    "Confirms" is deliberately strict - both metrics have to separate the pair before their
    agreement counts as anything. The rest are ties in one metric or the other, and a tie is
    not a disagreement; keeping the two apart is the whole point of the section.
    """
    summary: dict[str, dict] = {}
    for p in pairs:
        d = summary.setdefault(p["object"], {"total": 0, "confirmed": 0, "contradicted": 0})
        d["total"] += 1
        if not p["f1_tie"] and not p["iou_tie"]:
            d["confirmed" if p["diou"] > 0 else "contradicted"] += 1
    return summary


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
    iou_row = read_iou()
    iou_pairs = read_iou_pairs()
    iou_by_object = iou_object_summary(iou_pairs)
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
            "iou_pairs": iou_by_object.get(
                OBJECT_PAGE.get(r["object_id"], ("", r["object_id"]))[1]),
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
            "has_iou": bool(iou_row), "iou_pairs": iou_pairs}


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
    <h2>Voxel IoU: a second opinion on the F1 ranking</h2>
    <div class="subtitle" style="max-width:96ch">
      F1 is point-wise, so point density can flatter it; IoU cannot be flattered that way, because a voxel
      counts as occupied whether one point or ten thousand landed in it. That makes IoU useful here not as
      a second ranking — it has no natural scale, and it depends on a voxel size and on where the grid
      starts — but as a <b>check on the ranking F1 already gives</b>. The question is therefore asked one
      pair of methods at a time: on this object, does the density-free metric put these two in the same
      order, and can either metric separate them at all? Each dot is one such pair, 6 objects × 6 pairs.
      The further right a dot sits, the wider the gap F1 puts between the two methods; a dot above
      zero is one the two measures order in the same way.
    </div>
    <div class="panel" style="max-width:760px;">
      <svg id="iou-chart" viewBox="0 0 700 430" style="width:100%; height:auto;"></svg>
      <div id="iou-legend" style="font-size:11px; color:var(--text-dim); margin-top:8px;"></div>
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

// IoU is reported per method, but what can be read out of one such number is a pair-level fact,
// so the flag under it counts pairs: of this object's six method pairs, how many both metrics
// separate and order the same way. The rest are ties - in F1, in IoU, or in both - and a tie is
// not a disagreement. A bare number would be read as a ranking that, on the objects whose
// reference is incomplete, it cannot support on its own.
function iouCell(obj, m) {
  const iou = m.iou_5cm;
  if (iou == null) return '<td class="colsep">—</td>';
  const p = obj.iou_pairs;
  if (!p) return `<td class="colsep">${fmt(iou)}</td>`;
  const ties = p.total - p.confirmed - p.contradicted;
  const title = `${p.confirmed} of this object's ${p.total} method pairs are separated by both metrics and `
    + `ordered the same way by each`
    + (p.contradicted ? `; ${p.contradicted} are separated by both and ordered differently` : '')
    + (ties ? `; the remaining ${ties} are a tie in F1, in IoU, or in both` : '');
  return `<td class="colsep" title="${title}">${fmt(iou)}`
    + `<span class="iou-flag ${p.contradicted ? 'weak' : 'ok'}">${p.confirmed}/${p.total} pairs confirm F1</span></td>`;
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
          + '<th class="colsep" title="voxel IoU at 5 cm against the reference - a check on the F1 '
          + 'ranking by a metric point density cannot flatter, not a ranking of its own. The line under '
          + 'each value counts how many of the six method pairs on this object IoU separates and orders '
          + 'the same way F1 does; the section below the table plots all 36.">IoU@5cm (%)</th>'
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
// One dot per PAIR of methods, not per object. An ordering throws away how far apart the two
// methods were, and that distance is the whole question here: a 0.3 pp swap between two tied
// methods would otherwise read exactly like a real reversal. Every pair is oriented so the method
// F1 prefers lies in the positive x direction, which puts the verdict on a single line - above
// y = 0 IoU agrees with F1, below it does not. Both uncertainties are drawn rather than asserted:
// the horizontal bar is F1's 95% block-bootstrap CI, the vertical one the range of the same IoU
// gap over the 16 grid origins. The gap is the right quantity for the vertical bar and a method's
// own spread is not - a grid shift moves every method on an object in the same direction, so on
// the lamppost each method travels up to 7.2 pp across origins while the COLMAP-hloc gap never
// falls below 3.9. A bar that crosses zero means that metric cannot separate the pair; a dot is
// filled only when neither bar does.
function renderIouChart() {
  const pairs = DATA.iou_pairs || [];
  const sec = document.getElementById('iou-section'), sep = document.getElementById('iou-sep');
  if (!pairs.length) return;
  sec.hidden = false; sep.hidden = false;

  const W = 700, H = 430, padL = 66, padR = 16, padT = 14, padB = 56;
  const plotW = W - padL - padR, plotH = H - padT - padB;
  const xv = pairs.flatMap(p => [p.df1, p.f1_lo, p.f1_hi]);
  const yv = pairs.flatMap(p => [p.diou, p.iou_lo, p.iou_hi]);
  const x0 = Math.min(0, ...xv) - 2, x1 = Math.max(...xv) + 3;
  const y0 = Math.min(...yv) - 3, y1 = Math.max(...yv) + 4;
  const X = v => (padL + (v - x0) / (x1 - x0) * plotW).toFixed(1);
  const Y = v => (padT + plotH - (v - y0) / (y1 - y0) * plotH).toFixed(1);
  const ink = cssvar('--text-dim'), faint = cssvar('--text-faint'), surf = cssvar('--panel');
  const ok = cssvar('--best');
  const ticks = (lo, hi) => { const t = []; for (let v = Math.ceil(lo / 10) * 10; v <= hi; v += 10) t.push(v); return t; };
  const sign = v => (v > 0 ? '+' : '') + v;

  let s = '';
  for (const t of ticks(x0, x1)) {
    s += `<line x1="${X(t)}" y1="${padT}" x2="${X(t)}" y2="${padT + plotH}" stroke="${faint}" stroke-opacity="0.14"/>`;
    s += `<text x="${X(t)}" y="${padT + plotH + 16}" font-size="9.5" fill="${faint}" text-anchor="middle">${t}</text>`;
  }
  for (const t of ticks(y0, y1)) {
    if (t === 0) continue;
    s += `<line x1="${padL}" y1="${Y(t)}" x2="${padL + plotW}" y2="${Y(t)}" stroke="${faint}" stroke-opacity="0.14"/>`;
    s += `<text x="${padL - 8}" y="${(+Y(t) + 3.5).toFixed(1)}" font-size="9.5" fill="${faint}" text-anchor="end">${sign(t)}</text>`;
  }
  // y = 0 carries the verdict, so it is drawn as a mark and not as one more gridline
  s += `<line x1="${padL}" y1="${Y(0)}" x2="${padL + plotW}" y2="${Y(0)}" stroke="${ink}" stroke-width="1.2" stroke-opacity="0.5"/>`;
  s += `<text x="${padL - 8}" y="${(+Y(0) + 3.5).toFixed(1)}" font-size="9.5" fill="${ink}" text-anchor="end">0</text>`;
  s += `<text x="${padL + plotW}" y="${(+Y(0) - 7).toFixed(1)}" font-size="10" fill="${ok}" text-anchor="end">IoU agrees with F1 ↑</text>`;
  s += `<text x="${padL + plotW}" y="${(+Y(0) + 16).toFixed(1)}" font-size="10" fill="${ink}" text-anchor="end">↓ IoU puts them the other way round</text>`;

  // bars first, dots over them, so a dot is never cut by its neighbour's whisker
  for (const p of pairs) {
    const both = !p.f1_tie && !p.iou_tie;
    const col = both ? ok : faint;
    s += `<line x1="${X(p.f1_lo)}" y1="${Y(p.diou)}" x2="${X(p.f1_hi)}" y2="${Y(p.diou)}" stroke="${col}" stroke-width="1" stroke-opacity="0.4"/>`;
    s += `<line x1="${X(p.df1)}" y1="${Y(p.iou_lo)}" x2="${X(p.df1)}" y2="${Y(p.iou_hi)}" stroke="${col}" stroke-width="1" stroke-opacity="0.4"/>`;
  }
  for (const p of pairs) {
    const both = !p.f1_tie && !p.iou_tie;
    const col = both ? ok : faint;
    const tip = `${p.object} — ${p.better} vs ${p.worse}\n`
      + `F1@3cm: ${p.better} ahead by ${p.df1} pp (95% CI ${p.f1_lo} to ${p.f1_hi})`
      + `${p.f1_tie ? ' — F1 cannot separate them' : ''}\n`
      + `IoU@5cm: ${sign(p.diou)} pp (${p.iou_lo} to ${p.iou_hi} across ${p.n_grids} grid origins)`
      + `${p.iou_tie ? ' — IoU cannot separate them' : ''}`;
    s += `<circle cx="${X(p.df1)}" cy="${Y(p.diou)}" r="4.5" fill="${both ? col : surf}" `
      + `stroke="${both ? surf : col}" stroke-width="${both ? 2 : 1.4}"><title>${tip}</title></circle>`;
  }

  // one direct label, on the pair that most deserves a second look: the widest F1 gap that IoU
  // does not reproduce. Labelling all five below the line would only crowd them together.
  const below = pairs.filter(p => p.diou < 0);
  if (below.length) {
    const worst = below.reduce((a, b) => (a.df1 >= b.df1 ? a : b));
    const lx = +X(worst.df1), ly = +Y(worst.diou);
    // a leader, because the label sits inside the crowd of ties and would otherwise look like
    // it belonged to whichever dot it happens to be nearest
    s += `<path d="M ${(lx + 5).toFixed(1)} ${(ly + 2).toFixed(1)} L ${(lx + 10).toFixed(1)} ${(ly + 11).toFixed(1)} `
      + `h 4" fill="none" stroke="${faint}" stroke-width="1"/>`;
    s += `<text x="${(lx + 17).toFixed(1)}" y="${(ly + 14.5).toFixed(1)}" font-size="9.5" fill="${ink}">`
      + `${worst.object}: ${worst.better} vs ${worst.worse}</text>`;
  }

  s += `<text x="${padL + plotW / 2}" y="${H - 10}" font-size="10.5" fill="${ink}" text-anchor="middle">`
    + `how far apart F1@3cm puts the two methods (percentage points)</text>`;
  s += `<text transform="translate(15,${padT + plotH / 2}) rotate(-90)" font-size="10.5" fill="${ink}" text-anchor="middle">`
    + `the same pair, by IoU@5cm (pp)</text>`;
  document.getElementById('iou-chart').innerHTML = s;

  const both = pairs.filter(p => !p.f1_tie && !p.iou_tie);
  const contra = both.filter(p => p.diou < 0);
  // the two tie sets overlap, so they are reported as overlapping and not summed
  const f1Ties = pairs.filter(p => p.f1_tie).length, iouTies = pairs.filter(p => p.iou_tie).length;
  const bothTies = pairs.filter(p => p.f1_tie && p.iou_tie).length;
  const thrFlips = pairs.filter(p => p.f1_5cm_flips).length;
  const dot = (fill, stroke, sw) => `<svg width="11" height="11" style="vertical-align:-1px">`
    + `<circle cx="5.5" cy="5.5" r="4" fill="${fill}" stroke="${stroke}" stroke-width="${sw}"/></svg>`;
  document.getElementById('iou-legend').innerHTML =
    `${dot(cssvar('--best'), cssvar('--panel'), 1.5)} both metrics separate the pair (${both.length} of ${pairs.length}) &nbsp;·&nbsp; `
    + `${dot(cssvar('--panel'), cssvar('--text-faint'), 1.4)} a tie in F1, in IoU, or in both (${pairs.length - both.length})`
    + `<br>bars: 95% CI on the F1 gap (horizontal) · the same IoU gap across ${pairs[0].n_grids} grid origins (vertical)`;

  const worstBelow = below.length ? below.reduce((a, b) => (a.df1 >= b.df1 ? a : b)) : null;
  document.getElementById('iou-note').innerHTML =
    `<b>${contra.length ? contra.length + ' of the ' + both.length + ' resolvable pairs come out the other way round.'
                        : 'Nothing contradicts.'}</b> `
    + `Of the ${pairs.length} method pairs, ${both.length} are separated by both metrics${contra.length ? '' : ', and every one of those is ordered the same way by F1 and by IoU'}: `
    + `a metric that point density cannot flatter reproduces the F1 ranking wherever it has the resolution to speak. `
    + `The other ${pairs.length - both.length} are pairs at least one metric calls a tie: IoU cannot separate ${iouTies} of `
    + `them — its gap changes sign from one grid origin to the next — F1 cannot separate ${f1Ties}, its interval crossing `
    + `zero, and ${bothTies} defeat both. A tie is not a disagreement. `
    + (worstBelow ? `${below.length} dots sit below the line and every one of them is such a tie; the one worth naming is the `
        + `<b>${worstBelow.object}</b>, where F1@3cm puts ${worstBelow.better} ${worstBelow.df1} pp above ${worstBelow.worse} `
        + `while IoU calls the pair even (${sign(worstBelow.diou)} pp, and the sign does not hold across the `
        + `${worstBelow.n_grids} origins) — read that one as a caution rather than as a confirmation. ` : '')
    + `For scale, F1's own ordering is not perfectly steady either: moving the threshold from 3 cm to 5 cm turns `
    + `${thrFlips} of these same ${pairs.length} pairs around, ${thrFlips >= below.length ? 'as many as' : 'fewer than'} `
    + `the ${below.length} on which IoU differs from it. `
    + `Two caveats hold throughout. IoU has no natural scale — each object's IoU roughly doubles from a 2 cm voxel to a `
    + `10 cm one, so the number means nothing without its voxel size. And on the four objects whose reference is `
    + `incomplete, the unscanned volume counts against every method, which is why the column sits under `
    + `<i>diagnostics</i> and reports how many pairs it confirms rather than a ranking of its own.`;
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
__SITE_CREDIT__
</body>
</html>
"""


def main() -> None:
    rows = read_rows()
    data = page_data(rows)
    html = (HTML.replace("__NAV_CSS__", NAV_CSS)
                .replace("__SITE_NAV__", nav_html("results"))
                .replace("__PAYLOAD__", json.dumps(data).replace("</", "<\\/"))
                .replace("__SITE_CREDIT__", SITE_CREDIT))
    OUT_HTML.write_text(html, encoding="utf-8")
    n = sum(len(o["methods"]) for o in data["objects"])
    print(f"Wrote {OUT_HTML.relative_to(PROJECT_ROOT)} "
          f"({len(data['objects'])} objects, {n} rows, {OUT_HTML.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    sys.exit(main())