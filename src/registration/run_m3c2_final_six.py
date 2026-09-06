"""Run M3C2 over the final six objects x four methods (24 comparisons), giving each
its OWN registration error instead of one assumed constant for all of them.

Why this script exists at all: compute_m3c2.py takes --registration-error as a single
number (default 1 cm), which is what every earlier, non-final M3C2 run used. That
number is not a detail - it goes straight into the Level of Detection
(LoD95 = 1.96 * (sqrt(spread1^2/n1 + spread2^2/n2) + registration_error)), i.e. it sets
how large a difference has to be before this comparison calls it real. Note the bracket:
the 1.96 covers the registration error too, so the threshold has a hard floor of
1.96 * registration_error. Verified numerically rather than read off py4dgeo's Python
fallback, since this script uses the compiled path: recomputing LoD95 from the stored
per-point spreads reproduces it to 3e-17 with the bracket here and misses by 0.96 *
registration_error without it, and the lowest LoD95 on bench/mast3r_ga is 3.84 cm
against the 3.83 cm floor its 1.96 cm alignment error implies. The alignment
these clouds actually have was measured per object x method and runs 1.16-2.17 cm, so
a flat 10 mm was optimistic for most of the 24 and generous for none of them.

Where each number comes from:
  * paths + exp ids - MERGED_OBJECTS in build_object_page.py: the same final aligned
    .ply files and the same reference the object pages and the Accuracy/F1 workbook
    use (exp_111/126/129-150). NOT the August M3C2 runs under
    outputs/metrics/*_m3c2*, which predate the final six and point at exp_058/063/071
    era clouds.
  * registration_error - docs/tables/registration_rmse_from_aligned_clouds.json,
    field rows[exp_id].rmse_inlier_mm (mm -> m), the inlier RMSE measured on those
    same aligned clouds against that same reference. Deliberately not the
    inlier_rmse in each registration's report.json: those describe a cloud that was
    overwritten after the report was saved (and 9 of the 24 report.json files are
    empty).

Caveat worth one sentence in the thesis: rmse_inlier_mm is not a pure registration
error in the strict M3C2 sense - it also contains part of the reconstruction's own
noise at points near the surface, which LoD95 already accounts for separately via
spread1/spread2. The threshold is therefore slightly conservative (too high), never
too low.

Fixed for all 24 (the settings the most recent per-object runs used):
D = 10 cm, d = 6 cm, core points voxel-downsampled to 3 cm, max_distance = 15 cm.

Both directions are computed for every combination, because "no pair in the cylinder"
means opposite things on the two sides and each is worth having:
  * core points on the SOURCE (the reconstruction) - the headline direction, the one the
    site and the results table use. Unpaired here = reconstruction surface sitting where
    the reference's surface is not, the M3C2 counterpart of an accuracy failure.
  * core points on the TARGET (the LiDAR reference) - unpaired here = reference surface
    the reconstruction never covered, the counterpart of a completeness failure. It is
    also the direction that is stable across methods, since the core points are the same
    reference points every time rather than each method's own cloud.
The sign flips between them: with core points on the reconstruction, epoch2 is the
reference, so a positive distance means the reference is further out (the reconstruction
sits inside it); with core points on the reference the roles swap and positive means the
reconstruction is outside. Each report states its own convention, and the summary's
outside_pct already accounts for it, so the two directions are directly comparable.

Normals are oriented outward from each object's LiDAR centre rather than towards +Z
(py4dgeo's default), so that the sign of the distance means "the reconstruction sits
outside / inside the reference surface" on a pole or a sign face too, not only on a
bench seat - see run_m3c2() in compute_m3c2.py. Distances' magnitudes, the spreads and
the LoD are unchanged by this; only the sign is.

How reproducible the numbers are: py4dgeo's multiscale normal estimation is not
bit-reproducible on this data - repeating the identical computation re-orients ~2.7% of
the core points' normals (measured on bus_stop/colmap: 648 of 23768, by more than 10
degrees). Those are the core points whose neighbourhood has no well-defined plane, where
the two smallest covariance eigenvalues are nearly equal and the normal is genuinely
ambiguous, so it is a property of the geometry, not of a setting here. Re-running moves
the medians by up to ~0.04 cm and the significant share by up to ~0.2 pp: read these
columns to the precision they are printed at, not beyond it. The outward orientation is
unaffected - a normal that wobbles still points away from the object's centre.

The three summaries are the same 24 rows three times over: docs/tables/m3c2_final_six.json
is what the site reads, docs/tables/m3c2_final_six.xlsx is what FINAL_results.xlsx copies its
"M3C2" sheet from, and docs/m3c2_final_six.md is the readable one - the numbers plus how to
read them, so the result survives without opening a spreadsheet or a web page. All three are
rewritten on every run (including --summary-only), so none of them can drift from the
reports on disk.

Outputs (two runs per combination, each with its per-point distances beside it):
    outputs/metrics/<page_id>_m3c2_final/<method>.json                    (core points: source)
    outputs/metrics/<page_id>_m3c2_final/<method>_corepoints_target.json  (core points: target)
plus one aggregate for the site/thesis:
    docs/tables/m3c2_final_six.json

Usage:
    python -u src/registration/run_m3c2_final_six.py                 # all 24, skipping finished ones
    python -u src/registration/run_m3c2_final_six.py --only bench flashlight
    python -u src/registration/run_m3c2_final_six.py --force         # recompute everything
    python -u src/registration/run_m3c2_final_six.py --summary-only  # just rebuild the aggregate JSON
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from build_object_page import MERGED_OBJECTS, METHOD_ORDER  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RMSE_JSON = PROJECT_ROOT / "docs" / "tables" / "registration_rmse_from_aligned_clouds.json"
SUMMARY_JSON = PROJECT_ROOT / "docs" / "tables" / "m3c2_final_six.json"
SUMMARY_XLSX = PROJECT_ROOT / "docs" / "tables" / "m3c2_final_six.xlsx"
SUMMARY_MD = PROJECT_ROOT / "docs" / "m3c2_final_six.md"
OUT_ROOT = PROJECT_ROOT / "outputs" / "metrics"

# One setting for all 24 - the comparison is between methods and objects, so the metric's
# own parameters must not vary along either axis. See compute_m3c2.py's module docstring
# for where D and d come from.
NORMAL_SCALE = 0.10        # D
PROJECTION_SCALE = 0.06    # d
COREPOINT_VOXEL = 0.03     # core point spacing
MAX_DISTANCE = 0.15        # cylinder half-length along the normal
ORIENT_NORMALS = "outward"  # sign = outside/inside the reference, not above/below it


def combinations() -> list[dict]:
    """The 24 rows, in page/capture/method order, with everything needed to run one."""
    rmse_rows = json.loads(RMSE_JSON.read_text())["rows"]
    out = []
    for page_id, cfg in MERGED_OBJECTS.items():
        ref_rel = cfg["ref"]
        # output paths below are <page_id>/<method>, which a second capture on the same page
        # would silently overwrite. All six pages have exactly one capture today; if that ever
        # changes, put the capture id in the filename rather than losing half the runs.
        if len(cfg["captures"]) > 1:
            raise SystemExit(f"{page_id} has {len(cfg['captures'])} captures - the output paths "
                             "here assume one per page; add the capture id to them first")
        for capture in cfg["captures"]:
            for method in METHOD_ORDER:
                if method not in capture["methods"]:
                    continue
                exp_id, src_rel = capture["methods"][method]
                row = rmse_rows.get(exp_id)
                if row is None:
                    raise SystemExit(
                        f"{exp_id} ({page_id}/{method}) has no row in {RMSE_JSON.name} - "
                        "cannot pick a registration error for it"
                    )
                # the RMSE was measured against a reference; if that is not the one this
                # page uses, the two numbers describe different comparisons
                if Path(row["reference"]).name != Path(ref_rel).name:
                    raise SystemExit(
                        f"{exp_id}: RMSE was measured against {Path(row['reference']).name}, "
                        f"but {page_id} uses {Path(ref_rel).name}"
                    )
                out.append({
                    "page_id": page_id,
                    "object_name": cfg.get("display_name", page_id),
                    "capture_id": capture["id"],
                    "method": method,
                    "exp_id": exp_id,
                    "source": PROJECT_ROOT / src_rel,
                    "target": PROJECT_ROOT / ref_rel,
                    "rmse_inlier_mm": row["rmse_inlier_mm"],
                    "registration_error": row["rmse_inlier_mm"] / 1000.0,
                    # the source direction keeps the plain name: it is the one the object
                    # pages and results.html read
                    "output": OUT_ROOT / f"{page_id}_m3c2_final" / f"{method}.json",
                    "output_target": OUT_ROOT / f"{page_id}_m3c2_final" / f"{method}_corepoints_target.json",
                })
    return out


def _outside_pct(report_path: Path, corepoints_from: str) -> float | None:
    """Share of the paired core points where the reconstruction sits OUTSIDE the reference.
    One number for "this method inflates the object" vs "this method eats into it" - a bias
    the unsigned Accuracy median cannot show at all.

    Which sign means "outside" depends on which cloud holds the core points (see the module
    docstring): outside is distance < 0 from the reconstruction's side, distance > 0 from the
    reference's."""
    import numpy as np  # local: keeps --summary-only free of a numpy import at module load

    npz = report_path.with_suffix(".distances.npz")
    if not npz.exists():
        return None
    with np.load(npz) as z:
        d = z["distances"]
    valid = np.isfinite(d)
    if not valid.any():
        return None
    outside = d[valid] < 0 if corepoints_from == "source" else d[valid] > 0
    return float(100.0 * outside.mean())


def _figures(report_path: Path, corepoints_from: str) -> dict | None:
    """The figures one direction contributes: the three the site shows, plus the signed and
    spread statistics that only make sense per direction."""
    if not report_path.exists():
        return None
    r = json.loads(report_path.read_text())
    st = r["distance_stats"] or {}
    n_core, n_valid = r["num_corepoints"], r["num_valid"]
    return {
        "num_corepoints": n_core,
        "num_valid": n_valid,
        "unpaired_pct": 100.0 * (1 - n_valid / n_core) if n_core else None,
        "median_abs_cm": 100.0 * st["median_abs"] if st else None,
        "mean_abs_cm": 100.0 * st["mean_abs"] if st else None,
        "mean_signed_cm": 100.0 * st["mean_signed"] if st else None,
        "p95_abs_cm": 100.0 * st["p95_abs"] if st else None,
        "outside_pct": _outside_pct(report_path, corepoints_from),
        "num_with_defined_lod": r["num_with_defined_lod"],
        "num_significant_at_lod95": r["num_significant_at_lod95"],
        "significant_pct": (100.0 * r["fraction_significant_at_lod95"]
                            if r["fraction_significant_at_lod95"] is not None else None),
        "report": str(report_path.relative_to(PROJECT_ROOT)),
        "distances_npz": r["per_point_distances_file"],
    }


def summarize(combos: list[dict]) -> dict:
    """Collect the 24 reports into one file the site and the thesis can read.

    unpaired_pct is the diagnostic the raw report does not spell out: core points whose
    search cylinder found no reference points at all, as a share of all core points. It
    is what separates "this method is off by x cm" from "this method put its points
    somewhere the reference surface isn't" - 71% for vggt on the lamppost in the earlier
    runs, 2-12% for the other three methods.
    """
    rows, missing = {}, []
    for c in combos:
        source = _figures(c["output"], "source")
        if source is None:
            missing.append(f"{c['page_id']}/{c['method']}")
            continue
        target = _figures(c["output_target"], "target")
        if target is None:
            missing.append(f"{c['page_id']}/{c['method']} (target direction)")
        rows[c["exp_id"]] = {
            "page_id": c["page_id"],
            "object_name": c["object_name"],
            "capture_id": c["capture_id"],
            "method": c["method"],
            "registration_error_m": c["registration_error"],
            "rmse_inlier_mm": c["rmse_inlier_mm"],
            # reported in cm like every other distance in this table; the sidecar and the
            # py4dgeo parameter above both stay in their own units, which their names give
            "rmse_inlier_cm": round(c["rmse_inlier_mm"] / 10.0, 2),
            # the source direction stays at the top level: it is what results.html and the
            # object pages read, and what "M3C2" means without further qualification here
            **source,
            "corepoints_target": target,
        }
    if missing:
        print(f"  ! summary is incomplete - no report yet for: {', '.join(missing)}")
    return {
        "description": (
            "M3C2 (py4dgeo) for the final six objects x four methods, core points on the "
            "reconstruction, measured against each object's LiDAR reference."
        ),
        "registration_error_source": (
            "docs/tables/registration_rmse_from_aligned_clouds.json - rows[exp_id].rmse_inlier_mm, "
            "per object x method, converted to metres. Not a constant."
        ),
        "params": {
            "normal_scale_D_m": NORMAL_SCALE,
            "projection_scale_d_m": PROJECTION_SCALE,
            "corepoint_voxel_m": COREPOINT_VOXEL,
            "max_distance_m": MAX_DISTANCE,
            "corepoints_from": "source (the reconstruction); the mirror run is under corepoints_target",
            "normal_orientation": ORIENT_NORMALS,
            "target_deduplicated": True,
        },
        "generated": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "rows": rows,
    }


# (header, which direction it comes from, key, decimals) - one flat row per object x method,
# because that is what the workbook's copy_sheet() can carry and what a thesis table needs
XLSX_COLUMNS = [
    ("object", None, "object_name", None),
    ("capture", None, "capture_id", None),
    ("method", None, "method", None),
    ("exp_id", None, "_exp_id", None),
    ("registration error (cm)", None, "rmse_inlier_cm", 2),
    ("recon: core points", "source", "num_corepoints", 0),
    ("recon: no pair (%)", "source", "unpaired_pct", 1),
    ("recon: |M3C2| median (cm)", "source", "median_abs_cm", 2),
    ("recon: |M3C2| p95 (cm)", "source", "p95_abs_cm", 2),
    ("recon: beyond LoD95 (%)", "source", "significant_pct", 1),
    ("recon: outside the reference (%)", "source", "outside_pct", 1),
    ("ref: core points", "target", "num_corepoints", 0),
    ("ref: no pair (%)", "target", "unpaired_pct", 1),
    ("ref: |M3C2| median (cm)", "target", "median_abs_cm", 2),
    ("ref: |M3C2| p95 (cm)", "target", "p95_abs_cm", 2),
    ("ref: beyond LoD95 (%)", "target", "significant_pct", 1),
    ("ref: outside the reference (%)", "target", "outside_pct", 1),
]


def write_xlsx(summary: dict) -> None:
    """The same rows as the .json, flat, for the FINAL_results workbook to copy."""
    from openpyxl import Workbook  # local: --summary-only should not need openpyxl either

    wb = Workbook()
    ws = wb.active
    ws.title = "m3c2"
    ws.append([c[0] for c in XLSX_COLUMNS])
    for exp_id, r in summary["rows"].items():
        row = []
        for _, side, key, digits in XLSX_COLUMNS:
            src = r if side in (None, "source") else (r.get("corepoints_target") or {})
            v = exp_id if key == "_exp_id" else src.get(key)
            row.append(round(v, digits) if isinstance(v, (int, float)) and digits is not None else v)
        ws.append(row)
    ws.freeze_panes = "A2"
    wb.save(SUMMARY_XLSX)
    print(f"Wrote {SUMMARY_XLSX.relative_to(PROJECT_ROOT)} ({len(summary['rows'])} rows)")


MD_COLUMNS = [
    ("core points", "num_corepoints", "{:,}"),
    ("no pair %", "unpaired_pct", "{:.1f}"),
    ("median (cm)", "median_abs_cm", "{:.2f}"),
    ("p95 (cm)", "p95_abs_cm", "{:.2f}"),
    ("> LoD95 %", "significant_pct", "{:.1f}"),
    ("outside %", "outside_pct", "{:.1f}"),
]


def _md_table(summary: dict, side: str) -> str:
    """One direction as a markdown table. `side` is None for the source direction (whose
    figures sit at the top level of each row) or "corepoints_target"."""
    head = "| object | method | exp | reg.err (mm) | " + " | ".join(c[0] for c in MD_COLUMNS) + " |"
    rule = "|" + "---|" * (4 + len(MD_COLUMNS))
    lines = [head, rule]
    for exp_id, r in summary["rows"].items():
        src = r if side is None else (r.get(side) or {})
        cells = []
        for _, key, fmt in MD_COLUMNS:
            v = src.get(key)
            cells.append(fmt.format(v) if v is not None else "—")
        lines.append(f"| {r['object_name']} | {r['method']} | {exp_id} | {r['rmse_inlier_mm'] / 10:.2f} | "
                     + " | ".join(cells) + " |")
    return "\n".join(lines)


def write_markdown(summary: dict) -> None:
    """The readable copy of the result, regenerated from the same reports as the other two."""
    p = summary["params"]
    text = f"""# M3C2 on the final six objects

Six objects x four methods against their LiDAR references, measured along each core point's
own local surface normal (py4dgeo) rather than to the nearest point in any direction. This
file is generated by `src/registration/run_m3c2_final_six.py` - do not edit it by hand; re-run
that script (`--summary-only` is enough) to refresh it.

Generated: {summary['generated']}

## What was computed

- **Clouds**: the final aligned reconstructions and references from `MERGED_OBJECTS` in
  `build_object_page.py` (exp_111/126/129-150) - the same ones behind
  `summary_all_objects_accuracy_f1.xlsx`. Not the August `outputs/metrics/*_m3c2*` runs, which
  predate the final six.
- **`registration_error` is per row**, from `docs/tables/registration_rmse_from_aligned_clouds.json`
  (`rows[exp_id].rmse_inlier_mm`, 1.16-2.17 cm), not one assumed constant. It goes into
  LoD95 = 1.96 * (sqrt(spread1²/n1 + spread2²/n2) + registration_error), i.e. it sets how large a
  difference has to be before M3C2 calls it real. The 1.96 applies to the registration error too,
  so LoD95 has a floor of 1.96 × registration_error - 2.3-4.3 cm across these rows - which no
  amount of local surface smoothness gets below. "Beyond LoD95" therefore means "offset larger
  than roughly 2-4 cm", not "larger than roughly 1-2 cm".
- **Parameters**, identical for all 24: D = {p['normal_scale_D_m'] * 100:.0f} cm,
  d = {p['projection_scale_d_m'] * 100:.0f} cm, core points thinned to
  {p['corepoint_voxel_m'] * 100:.0f} cm, max_distance = {p['max_distance_m'] * 100:.0f} cm,
  duplicate reference points dropped, normals oriented outward from the object's centre.
- **Both directions**, because "no pair in the cylinder" means opposite things on the two sides.

## How to read it

- **no pair %** - core points whose search cylinder held nothing from the other cloud. This is
  why M3C2 needs no DBSCAN gap exclusion: a hole in the reference removes itself. On the
  reconstruction's side it means reconstruction surface where the reference's surface is not
  (the accuracy side); on the reference's side, reference the reconstruction never covered
  (the completeness side). The median beside it only describes the points that *did* pair.
- **> LoD95 %** - share of paired core points whose offset is larger than the local roughness of
  both clouds plus that row's alignment error. Everything below it is not distinguishable
  from noise.
- **outside %** - share of paired core points where the reconstruction's surface sits further
  from the object's centre than the reference's, i.e. the reconstruction bulges out rather
  than cutting in. Accuracy has no sign and cannot show this at all.
- **Precision**: py4dgeo's normal estimation is not bit-reproducible on this data (~2.7% of core
  points sit in neighbourhoods with no well-defined plane). Re-running moves the medians by up
  to ~0.04 cm and the significant share by up to ~0.2 pp - read these to the printed precision,
  no further.
- The inlier RMSE used as `registration_error` is not a pure registration error: it also carries
  part of the reconstruction's own near-surface noise, which LoD95 already handles separately
  through spread1/spread2. The threshold is therefore slightly conservative, never too low.

## Core points on the reconstruction (the accuracy side)

{_md_table(summary, None)}

## Core points on the reference (the completeness side)

{_md_table(summary, 'corepoints_target')}

Note the core point counts: on this side they are identical for the four methods of an object
(it is the same reference every time), so the four rows are strictly comparable; on the
reconstruction's side they vary up to 15x, because each is that method's own cloud.

## Where the rest lives

| what | where |
|---|---|
| machine-readable summary (what the site reads) | `docs/tables/m3c2_final_six.json` |
| the same rows as a sheet | `docs/tables/m3c2_final_six.xlsx`, and the **M3C2** sheet of `docs/tables/FINAL_results.xlsx` |
| per-comparison reports + per-point distances | `outputs/metrics/<object>_m3c2_final/` (regenerable; `outputs/` is not tracked) |
| method, parameter choices, the caveats in full | `docs/methodology_notes.md` |
| on the site | three columns on `site/results.html`, and the **M3C2** tab on each of the six object pages |

Regenerate: `python -u src/registration/run_m3c2_final_six.py` (add `--force` to recompute
reports that already exist).
"""
    SUMMARY_MD.write_text(text)
    print(f"Wrote {SUMMARY_MD.relative_to(PROJECT_ROOT)}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", nargs="+", metavar="PAGE_ID", choices=sorted(MERGED_OBJECTS),
                    help="restrict to these object pages (default: all six)")
    ap.add_argument("--force", action="store_true", help="recompute combinations that already have a report")
    ap.add_argument("--summary-only", action="store_true",
                    help="do not run M3C2, only rebuild docs/tables/m3c2_final_six.json from existing reports")
    args = ap.parse_args()

    combos = combinations()
    if args.only:
        combos = [c for c in combos if c["page_id"] in set(args.only)]

    if not args.summary_only:
        # imported here, not at module import time: compute_m3c2 pulls in open3d and
        # py4dgeo, ~2 min in this venv, which --summary-only has no use for
        from compute_m3c2 import compute_m3c2_report  # noqa: PLC0415

        # one entry per (combination, direction), so --force-less reruns resume at the
        # granularity things actually failed at
        todo = [(c, side, key) for c in combos for side, key in (("source", "output"), ("target", "output_target"))
                if args.force or not c[key].exists()]
        print(f"{len(combos)} combinations selected ({2 * len(combos)} runs, both directions), "
              f"{len(todo)} to run ({2 * len(combos) - len(todo)} already have a report; "
              f"--force to redo them)\n", flush=True)
        for i, (c, side, key) in enumerate(todo, 1):
            print("=" * 100)
            print(f"[{i}/{len(todo)}] {c['page_id']} · {c['method']} · {c['exp_id']} · core points: {side}  "
                  f"registration_error = {c['rmse_inlier_mm'] / 10:.2f} cm", flush=True)
            if not c["source"].exists():
                print(f"  ! source cloud missing: {c['source']} - skipped", flush=True)
                continue
            t0 = time.time()
            compute_m3c2_report(
                c["source"], c["target"], c[key],
                corepoints_from=side,
                corepoint_voxel_size=COREPOINT_VOXEL,
                normal_scale=NORMAL_SCALE,
                projection_scale=PROJECTION_SCALE,
                registration_error=c["registration_error"],
                max_distance=MAX_DISTANCE,
                dedupe_target=True,
                orient_normals=ORIENT_NORMALS,
            )
            print(f"  took {time.time() - t0:.1f}s", flush=True)

    summary = summarize(combinations())
    SUMMARY_JSON.write_text(json.dumps(summary, indent=2))
    print(f"\nWrote {SUMMARY_JSON.relative_to(PROJECT_ROOT)} ({len(summary['rows'])}/24 rows)")
    write_xlsx(summary)
    write_markdown(summary)

    def cell(d, field, fmt, width):
        v = (d or {}).get(field)
        return f"{v:{fmt}}" if v is not None else "-".rjust(width)

    print("\n" + " " * 33 + "core points on the RECONSTRUCTION".center(38) + " | "
          + "core points on the REFERENCE".center(38))
    hdr = (f"{'object':17s} {'method':12s} {'reg.err':>7s} | {'core pts':>9s} {'unpaired':>9s} "
           f"{'|d| med':>9s} {'signif':>7s} | {'core pts':>9s} {'unpaired':>9s} {'|d| med':>9s} {'signif':>7s}")
    print(hdr)
    print("-" * len(hdr))
    for r in summary["rows"].values():
        tgt = r.get("corepoints_target")
        print(f"{r['page_id']:17s} {r['method']:12s} {r['rmse_inlier_mm'] / 10:5.2f}cm | "
              f"{r['num_corepoints']:9,d} {cell(r, 'unpaired_pct', '8.1f', 9)}% "
              f"{cell(r, 'median_abs_cm', '7.2f', 9)}cm {cell(r, 'significant_pct', '6.1f', 7)}% | "
              f"{cell(tgt, 'num_corepoints', '9,d', 9)} {cell(tgt, 'unpaired_pct', '8.1f', 9)}% "
              f"{cell(tgt, 'median_abs_cm', '7.2f', 9)}cm {cell(tgt, 'significant_pct', '6.1f', 7)}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
