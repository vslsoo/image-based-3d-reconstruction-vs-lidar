# Image-Based 3D Reconstruction vs LiDAR

Code and results for the MSc dissertation *Photo-based reconstruction of street infrastructure
against a laser scanning reference: A comparison of correspondence-based and feed-forward methods
on six street objects* (UCL, Department of Civil, Environmental and Geomatic Engineering, 2026).

Six street objects were photographed with one smartphone and reconstructed with four open-source
methods from two families, then compared against a mobile laser scanning reference. Scale is set
independently of that reference, so the comparison measures metric correctness rather than shape.

**Results dashboard:** https://vslsoo.github.io/image-based-3d-reconstruction-vs-lidar/

## Methods

| Method | Family | Front end | Config |
|---|---|---|---|
| COLMAP | correspondence-based | SIFT, exhaustive matching | `config/reconstruction_busstop.yaml` |
| hloc + COLMAP | correspondence-based | SuperPoint + LightGlue, exhaustive pairing | `config/hloc_colmap_busstop.yaml` |
| MASt3R-GA | feed-forward | pointmap regression at 512 px, global alignment | `config/mast3r_ga_logwin.yaml` |
| VGGT | feed-forward | pointmap regression at 518 px, single pass | `config/vggt.yaml` |

The final reconstructions use the `_busstop` variants (exhaustive matching) and MASt3R-GA's
`logwin-7` scene graph; the image-count ablation uses `swin-8`.

## Object names

Two objects carry a working name in the code, the configs, `outputs/` and the dashboard URLs that
the dissertation does not use. When cross-referencing the thesis with this repository:

| In the dissertation | In this repository | Object id of the final run |
|---|---|---|
| Bollard | `bollard` | `bollard_003_test_1_pool69` |
| Bench | `bench` | `bench_004` |
| Information sign | `information_sign` | `information_sign_002_test_1_manual_n75` |
| Bus stop sign | `bus_stop_sign` | `bus_stop_sign_002` |
| **Bus shelter** | **`bus_stop`** | `bus_stop_002` |
| **Lamp post** | **`flashlight`** | `flashlight_004` |

## Results in this repository

`docs/tables/FINAL_results.xlsx` holds every reported result in one workbook, one sheet per table
of the dissertation. The individual sources are alongside it:

| Dissertation | File |
|---|---|
| Table 5.1 | `docs/tables/T5_1_main_results.csv` / `.md`, `summary_all_objects_accuracy_f1_EN.xlsx` |
| Table 5.5, Figure 5.9 | `docs/tables/capture_comparison_summary.xlsx` |
| Table 5.6, Figure 5.10 | `docs/tables/frame_count_study_summary.xlsx` |
| Table 5.7, Figure 5.11 | `docs/tables/performance_study_summary.json` |
| Table 5.8 | `docs/tables/m3c2_final_six.xlsx` |
| Table 5.9, Figure 5.12 | `docs/tables/voxel_iou_summary.xlsx` / `.json` |
| Table A.1 | `docs/tables/paired_pairwise_bootstrap.json` |
| §5.7 M3C2 over the kept core points | `docs/tables/m3c2_masked_check.json` |
| §6.6 exclusion threshold at 5 / 7.5 / 10 cm | `docs/tables/coverage_mask_sensitivity.json` |

`docs/figures/` carries the figures under the numbers the dissertation prints them with:
`fig_4_1`–`fig_4_3` are the three schematics, `fig_5_1`–`fig_5_6` the per-object cloud galleries
(`render_cloud_gallery.py`), `fig_5_7`–`fig_5_12` the charts (`build_thesis_figures.py`).
`fig_5_7_f1_by_object_groups` is a slide-only variant and appears in no chapter.

## Data

Raw data and large outputs are not stored here. The images are the author's; the laser scanning
reference was provided by Sensat and is not redistributed. `outputs/` is gitignored and
regenerable. `config/paths.example.yaml` shows the paths the scripts expect.

## External dependencies

`external/` is gitignored, so these are not vendored here. Clone each at the commit the reported
results were produced with:

| Component | Source | Commit |
|---|---|---|
| hloc 1.5 | https://github.com/cvg/Hierarchical-Localization.git | `c13273b` |
| MASt3R | https://github.com/naver/mast3r.git | `f5209af` |
| VGGT | https://github.com/facebookresearch/vggt.git | `a288dd0` |

```bash
git clone https://github.com/cvg/Hierarchical-Localization.git external/hloc
git -C external/hloc checkout c13273b

git clone https://github.com/naver/mast3r.git external/mast3r
git -C external/mast3r checkout f5209af

git clone https://github.com/facebookresearch/vggt.git external/vggt
git -C external/vggt checkout a288dd0
```

MASt3R and VGGT publish no versioned releases: MASt3R has no `setup.py`, `pyproject.toml` or
`__version__`, and VGGT's `pyproject.toml` has declared `0.0.1` since publication. The commit is
therefore the only identifier that pins the code actually used.

COLMAP is used through the `pycolmap-cuda12` 4.1.0 wheel rather than the command-line build.
All reconstructions were run on a single GPU pod with an NVIDIA L40S (45 GiB of video memory).

## Reproducing a run

Three things are easy to get wrong:

- **Pass `--num-images N` explicitly.** The configs carry `image_selection.num_images: 50`; without
  the flag a run of the full set is silently subsampled to 50 images.
- **Dense fusion is photometric-only.** `geom_consistency` is `false` in the `_busstop` configs:
  pycolmap-cuda12 4.1.0 reproducibly SIGSEGV'd at the geometric-consistency pass, 3/3, regardless
  of matching method or worker count. The reasoning is in `config/reconstruction_busstop.yaml`.
- **VGGT runs in `crop`, the upstream default.** `pad` was tried on the lamp post and the bollard
  (exp_171, exp_172) and was visibly worse; it is not what the reported results used.

## Structure

- `src/` — source code (`reconstruction/`, `registration/`, `evaluation/`, `data_preparation/`)
- `config/` — object, experiment and per-method configuration
- `docs/` — methodology notes, the result tables and the thesis figures
- `site/` — the dashboard, gitignored; the builders in `src/registration/` emit it and
  `deploy_site.sh` publishes it to the `gh-pages` branch
