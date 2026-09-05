# Which table is behind which part of the site

The published pages no longer name repository paths: `site/` is served to readers outside the
project, and `docs/tables/summary_all_objects_accuracy_f1.xlsx` means nothing to them while
telling them how the repository is laid out. The mapping itself is worth keeping, so it lives
here instead of in the page copy.

Nothing here is published — gh-pages carries only `site/*.html`.

## Pages and their sources

| page | numbers on it come from | built by |
|---|---|---|
| `results.html` | `docs/tables/summary_all_objects_accuracy_f1_EN.xlsx` (sheet `summary` for the rows, `significance` for the pairwise method tests) | `build_results_page.py` |
| `results.html` — M3C2 columns | `docs/tables/m3c2_final_six.json` (reconstruction-side run; the LiDAR-side mirror run is in the same file) | `run_m3c2_final_six.py` |
| `results.html` — IoU column and gap chart | `docs/tables/voxel_iou_summary.xlsx` (`summary`, `ranking`, `sensitivity`) and `voxel_iou_summary.json` (`shift_study.iou_all_pct`, the per-grid values the chart plots) | `compute_voxel_iou.py` |
| object pages (`bollard.html`, …) | embedded point pools; the exact at-default figures and the Chamfer number come from `docs/tables/summary_all_objects_accuracy_f1.json`, injected as `<script id="exact-data">` | `build_object_page.py` |
| `capture_comparison.html` | its own embedded payload; the workbook it agrees with is `docs/tables/capture_comparison_summary.xlsx` (+ `capture_comparison_sensitivity.json`) | `build_capture_comparison_page.py` |
| `frame_count_study.html` | its own embedded payload; the workbook it agrees with is `docs/tables/frame_count_study_summary.xlsx` | `build_frame_count_study_page.py` |
| `frame_count_study.html` — cost table | joins the above with `docs/tables/performance_study_summary.json` on `exp_id` | same |
| `performance_study.html` | `docs/tables/experiment_metrics.jsonl` (per-run stage timings, peak RAM and VRAM) | `build_performance_study_page.py` |
| `tuner.html` | embedded subsample of the candidate pools; the exact gap-excluded numbers come from `remove_reference_gap_points.py` on the full data | `build_tuner_page.py` |
| `index.html` | hand-written; its numbers are quoted from the summary workbook and were last checked 2026-09-05 | — (its nav is synced by `_site_nav.py`) |

`docs/tables/FINAL_results.xlsx` is the one workbook the dissertation cites: it copies the
sheets above verbatim (`build_final_results_workbook.py`), so it can never disagree with them.

## If you put a path back on a page

Don't, unless the audience changes. The phrasing the pages use instead — "the figures reported
in the dissertation", "computed over the full clouds" — carries the same guarantee to a reader
who has no repository to look in.
