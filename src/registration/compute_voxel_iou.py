"""Surface-voxel IoU between every aligned reconstruction and its LiDAR reference -
the density-independent counterpart to the accuracy/completeness/F1 table.

WHY THIS METRIC EXISTS AT ALL
-----------------------------
Accuracy/completeness/F1 are point-wise, so they inherit whatever point density each
method happens to produce. The project already handles that, but by *preprocessing*:
every reconstruction is thinned onto a fixed 1 cm voxel grid before any distance is
measured (VOXEL_M in build_accuracy_f1_summary_table.py). That works, but it is itself
a methodological choice that has to be defended, and the raw/matched ratios show how
much is riding on it - they run from 1.92 (vggt on the lamppost) to 129 (vggt on the
bollard), a two-order-of-magnitude spread in delivered density.

IoU removes the dependency structurally instead: a voxel is either occupied or it is
not, whether one point or ten thousand landed in it. The property is built into the
metric rather than established by a preparation step. Secondarily, IoU is the standard
metric in occupancy/segmentation work, so it reads immediately to a reviewer from that
field.

DECISION 1 - VOXEL SIZE (primary 5 cm, swept over 2/3/5/10 cm)
--------------------------------------------------------------
The size is clamped from both sides.

Lower bound A, reference sampling. Median NN-spacing of the references (the "ref.
spacing" column of summary_all_objects_accuracy_f1_EN.xlsx): bollard 1.00, lamppost
1.00, bus_stop_sign 1.00, bus_stop 1.41, information_sign 1.73, bench 2.00 cm. With a
voxel side equal to the sampling interval a surface voxel holds ~1 point on average, so
scatter alone leaves a large share of on-surface voxels empty - holes produced by how
the reference was scanned, not by geometry, and they hit recall. For ~4 points per
surface voxel the side has to be ~2x the worst interval: >= 4 cm.

Lower bound B, residual alignment error. registration_rmse_from_aligned_clouds.json
gives inlier RMSE 11.6-21.7 mm across its 24 rows. If the voxel side is comparable to
that, a rigid 2 cm shift moves occupancy by a whole voxel and IoU starts measuring
registration quality instead of shape. Same bound: >= ~4 cm (2x the worst RMSE).

Upper bound, thin objects. Bounding boxes from the same table: lamppost 15.5 x 15.0 x
582.9 cm, bus_stop_sign 63.4 x 39.4 x 347.4, information_sign 47.9 x 31.9 x 260.9. The
lamppost is the narrowest: at 10 cm that is one and a half voxels across and the object
effectively dissolves into the discretisation; at 5 cm it is three, the minimum that
still resolves a cross-section. Rule: at least three voxels across the narrowest
dimension -> <= 5 cm.

The corridor closes at 5 cm, and 5 cm is already one of the three F1 thresholds
(3/5/10 cm), so voxel IoU at 5 cm is directly comparable to F1@5cm.

The sweep is reported, not just the primary value, and two of its points are known to be
outside the corridor - stated here so the numbers are not over-read:
  - 2 cm is below both lower bounds. Recall drops for every method at once; that is an
    artefact of reference sampling, not a difference between methods.
  - 10 cm stops resolving the lamppost and the bus_stop_sign's pole. IoU there measures
    the bounding volume, not the shape.
If the method ordering survives 3, 5 and 10 cm, that is a result in itself and is
reported as one (see the "ranking" sheet / "verdict" block).

DECISION 2 - THIS IS A SHELL, NOT A VOLUME
------------------------------------------
Both clouds are surface samples, not solids, so what is computed is the IoU of occupied
*surface* voxels - surface-voxel IoU, never "volumetric IoU". No morphological closing,
no flood fill, no interior filling of any kind: the references are scanned from outside
and four of the six are incomplete, so filling would invent volume exactly where the
scan simply stopped. The bench and the bus shelter are open structures whose "interior"
is not defined in the first place.

DECISION 3 - GRID ORIGIN
------------------------
Voxelisation is not shift-invariant: the same two clouds on a grid moved by half a voxel
give a different IoU. The origin is therefore pinned at the minimum corner of the
*reference* bounding box - deterministic, reproducible, and identical for both clouds of
a pair. The sensitivity of that choice is measured rather than assumed: the primary
voxel size is recomputed on 15 further grids (the 7 non-zero half-voxel corner shifts,
plus N_RANDOM_SHIFTS uniform sub-voxel offsets).

Two details worth stating before the numbers are quoted. First, the origin is the true
min of the reference, not the 0.5-percentile robust bbox the F1 table uses for reported
dimensions: a stray point can therefore move it, but the origin only sets the grid's
phase, which is arbitrary to begin with and is exactly what the shift study samples.
Second, the per-method spread on its own overstates the problem. A grid shift moves every
method on an object in the same direction, so the honest question is not how far one IoU
travels but whether the *ordering* and the gaps between methods survive - which is why
the analysis reports order stability across all grids alongside the raw spread, and the
defence line is "the ordering holds on all N grids", not just "the spread is X pp".

DECISION 4 - OCCUPANCY THRESHOLD k = 1
--------------------------------------
A voxel counts as occupied if it contains at least one point. A threshold of k >= 2
would reintroduce precisely the density confound IoU is here to remove - a denser cloud
is likelier to reach k points in a voxel - so k >= 2 is computed only as a sensitivity
check, and is reported beside the raw/matched ratios so the confound stays visible.

A useful consequence of k = 1, verified per row rather than asserted: the result should
not depend on whether the raw aligned cloud or the 1 cm density-matched one is
voxelised, since any 5 cm voxel that held a point still holds one after 1 cm thinning.
(Not exactly guaranteed - open3d replaces each 1 cm cell by its centroid on a grid that
is not aligned to ours, so a centroid can cross a 5 cm boundary - hence "iou_raw_vs_
matched_delta_pp" in the output.) For k >= 2 the equivalence genuinely fails, so those
rows are computed on the raw cloud only.

DECISION 5 - INCOMPLETE REFERENCES
----------------------------------
IoU charges reconstruction voxels sitting where the reference was never scanned to the
false positives, and four of the six references are incomplete - so without handling,
the metric would mostly measure scan coverage. The primary numbers therefore reuse
find_gap_point_mask() from remove_reference_gap_points.py with each object's own tuned
settings (the "dbscan" key in MERGED_OBJECTS), the same convention as every other metric
in the thesis, applied to points *before* voxelisation.

The mask is computed on the 1 cm density-matched cloud, not the raw one, because that is
the density its DBSCAN parameters were tuned against - min_points is a density-dependent
quantity, and the raw clouds run up to 129x denser. The lamppost and the bus_stop_sign
have complete references ("no DBSCAN" on their pages), so they carry no mask at all and
are reported as the uncontaminated result.

WHAT IS COMPARED
----------------
The same 24 (object x method) combinations as everywhere else, read straight from
MERGED_OBJECTS. References are read through load_reference(), which drops exact
duplicates (up to 29% of the delivered points) - irrelevant at k = 1, critical at k >= 2.

SANITY ANCHOR
-------------
The lamppost reference is 16690 points in a 15.5 x 15.0 x 582.9 cm box. At 5 cm that is
a column roughly 3 x 3 voxels in section and ~117 tall, so on the order of a thousand
occupied voxels. An order of magnitude either way means the grid is wrong - almost
certainly metres/centimetres, or the origin. The check runs per object (see
sanity_check()) and prints a WARN rather than failing.

Usage:
    python -u src/registration/compute_voxel_iou.py
    python -u src/registration/compute_voxel_iou.py --objects flashlight bus_stop_sign
"""

from __future__ import annotations

import argparse
import itertools
import json
import sys
from pathlib import Path

import numpy as np
import open3d as o3d

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_object_page import MERGED_OBJECTS, METHOD_ORDER, DEFAULT_DBSCAN_SLIDERS  # noqa: E402
from build_accuracy_f1_summary_table import (  # noqa: E402
    SHAPE_EN, SHAPE_RU, REF_NOTE_EN, dbscan_mode_str, load_reference,
)
from remove_reference_gap_points import find_gap_point_mask  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUT_JSON = PROJECT_ROOT / "docs" / "tables" / "voxel_iou_summary.json"
OUT_XLSX = PROJECT_ROOT / "docs" / "tables" / "voxel_iou_summary.xlsx"
F1_JSON = PROJECT_ROOT / "docs" / "tables" / "summary_all_objects_accuracy_f1.json"

VOXEL_M = 0.01
# The 1 cm density-match grid, identical to build_accuracy_f1_summary_table.py's - not
# because IoU needs it (it does not, that is the point), but because the gap mask must be
# computed on the same cloud its DBSCAN settings were tuned against. See DECISION 5.

VOXEL_SIZES_M = [0.02, 0.03, 0.05, 0.10]
PRIMARY_V = 0.05
# See DECISION 1. 5 cm is the primary; 2 cm sits below both lower bounds and 10 cm above
# the thin-object bound - both are reported to show what happens there, not as results.

K_SENSITIVITY = [1, 2, 3]
# Occupancy thresholds for the sensitivity check only; k = 1 is the metric. See DECISION 4.

N_RANDOM_SHIFTS = 8
SHIFT_SEED = 42
# Grid-origin sensitivity: 7 half-voxel corner shifts + this many uniform sub-voxel
# offsets, all at PRIMARY_V. See DECISION 3.

GAP_FLOOR_CM = 3.0
# Only used to mirror build_accuracy_f1_summary_table.py's accounting of how many points
# the mask removed; the mask itself is driven by each object's far_threshold.


# --- voxel primitives -------------------------------------------------------------

def _void_view(idx: np.ndarray) -> np.ndarray:
    """View an (n, 3) int64 index array as an (n,) array of opaque 3-field records, so
    np.unique / np.intersect1d work on whole voxel coordinates at C speed. Same trick
    np.unique(axis=0) uses internally, hoisted out so the key domain can be reused for
    both the uniquing and the set intersection."""
    idx = np.ascontiguousarray(idx)
    if idx.size == 0:
        return np.empty(0, dtype=[("f0", idx.dtype), ("f1", idx.dtype), ("f2", idx.dtype)])
    return idx.view([("f0", idx.dtype), ("f1", idx.dtype), ("f2", idx.dtype)]).ravel()


def occupied_keys(pts: np.ndarray, origin: np.ndarray, v: float, min_points: int = 1) -> np.ndarray:
    """Sorted unique voxel keys for `pts` on the grid anchored at `origin` with pitch `v`.

    min_points is the k of DECISION 4 - k = 1 (the default) is the metric itself; higher
    k is a sensitivity check that reintroduces a density dependence on purpose."""
    keys = _void_view(np.floor((pts - origin) / v).astype(np.int64))
    if min_points <= 1:
        return np.unique(keys)
    uniq, counts = np.unique(keys, return_counts=True)
    return uniq[counts >= min_points]


def voxel_iou(src_keys: np.ndarray, ref_keys: np.ndarray) -> dict:
    """Surface-voxel IoU plus the two one-sided rates.

    precision_vox = |A n B| / |A| and recall_vox = |A n B| / |B| (A = reconstruction,
    B = reference) are reported alongside IoU because IoU alone cannot say *which way* it
    broke - a reconstruction that invents volume and one that misses half the object can
    land on the same IoU."""
    n_a, n_b = int(len(src_keys)), int(len(ref_keys))
    inter = int(np.intersect1d(src_keys, ref_keys, assume_unique=True).size) if n_a and n_b else 0
    union = n_a + n_b - inter
    return {
        "iou_pct": round(100.0 * inter / union, 2) if union else 0.0,
        "precision_vox_pct": round(100.0 * inter / n_a, 2) if n_a else 0.0,
        "recall_vox_pct": round(100.0 * inter / n_b, 2) if n_b else 0.0,
        "n_vox_source": n_a,
        "n_vox_ref": n_b,
        "n_vox_inter": inter,
    }


def iou_delta_10_3(row: dict) -> float:
    """ΔIoU(10-3) for a row, derived from its sweep rather than stored twice - so
    --from-json renders a JSON written before the field existed."""
    return round(row["sweep"]["10cm"]["iou_pct"] - row["sweep"]["3cm"]["iou_pct"], 2)


def shift_offsets(v: float, rng: np.random.Generator) -> list[np.ndarray]:
    """The grid origins to re-measure on: the true origin, the 7 non-zero half-voxel
    corner shifts, and N_RANDOM_SHIFTS uniform sub-voxel offsets. See DECISION 3."""
    offsets = [np.zeros(3)]
    offsets += [np.array(c, dtype=float) for c in itertools.product([0.0, v / 2.0], repeat=3) if any(c)]
    offsets += [rng.uniform(0.0, v, 3) for _ in range(N_RANDOM_SHIFTS)]
    return offsets


def sanity_check(page_id: str, ref_pts: np.ndarray, n_vox_ref: int, v: float) -> str:
    """Catch a wrong grid (units confused, origin misplaced) before any number is trusted.

    A surface sample must occupy far fewer voxels than its bounding box holds, but not
    vanishingly fewer. The anchor from the module docstring: the lamppost's reference
    should come out around a thousand voxels at 5 cm."""
    extent = ref_pts.max(axis=0) - ref_pts.min(axis=0)
    bbox_vox = int(np.prod(np.maximum(np.ceil(extent / v), 1)))
    fill = n_vox_ref / bbox_vox if bbox_vox else float("nan")
    status = "OK" if 0.002 <= fill <= 0.9 else "WARN"
    msg = (f"[sanity] {page_id}: ref bbox {extent[0]*100:.0f}x{extent[1]*100:.0f}x{extent[2]*100:.0f} cm "
           f"= {bbox_vox} voxels @ {v*100:g} cm, occupied {n_vox_ref} (fill {fill:.3f}) -> {status}")
    print(msg, flush=True)
    return status


# --- per-row computation ----------------------------------------------------------

def gap_kept_mask(matched: o3d.geometry.PointCloud, ref: o3d.geometry.PointCloud,
                  dbscan_cfg: dict, checkbox_checked: bool) -> tuple[np.ndarray, np.ndarray]:
    """(kept_mask, source->target distances in cm) for the density-matched cloud.

    Delegates to find_gap_point_mask() rather than re-deriving the clustering, so this
    table cannot drift from remove_reference_gap_points.py. Note the deliberate unit mix
    inherited from that function's callers: accuracy distances and far_threshold are both
    in cm, while eps is in metres because it is handed to open3d's clusterer, which works
    in the cloud's own units. That is exactly how build_accuracy_f1_summary_table.py calls
    the equivalent inline code, so the two agree row for row."""
    d_s2t_cm = np.asarray(matched.compute_point_cloud_distance(ref)) * 100.0
    if checkbox_checked:  # complete reference - honest mode, nothing excluded
        return np.ones(len(d_s2t_cm), dtype=bool), d_s2t_cm
    gap_mask, _clusters = find_gap_point_mask(
        matched, d_s2t_cm,
        far_threshold=dbscan_cfg["ft_default"],
        eps=dbscan_cfg["eps_default"] / 100.0,
        min_points=dbscan_cfg["mp_default"],
    )
    return ~gap_mask, d_s2t_cm


def compute_rows(page_ids: list[str]) -> list[dict]:
    rng = np.random.default_rng(SHIFT_SEED)
    f1_pages = json.loads(F1_JSON.read_text())["pages"] if F1_JSON.exists() else {}
    rows: list[dict] = []

    for page_id in page_ids:
        cfg = MERGED_OBJECTS[page_id]
        ref_path = PROJECT_ROOT / cfg["ref"]
        print(f"\n[ref] {page_id}: loading {ref_path.name}", flush=True)
        ref = load_reference(ref_path)
        rpts = np.asarray(ref.points)

        # Grid origin: the reference bbox minimum. Both clouds of every pair on this
        # object share it, and it does not move when a method changes. See DECISION 3.
        origin = rpts.min(axis=0)

        ref_keys = {v: occupied_keys(rpts, origin, v) for v in VOXEL_SIZES_M}
        sanity = sanity_check(page_id, rpts, len(ref_keys[PRIMARY_V]), PRIMARY_V)

        dbscan_cfg = {**DEFAULT_DBSCAN_SLIDERS, **cfg.get("dbscan", {})}
        checkbox_checked = cfg["checkbox_checked"]
        dbscan_mode = dbscan_mode_str(dbscan_cfg, checkbox_checked)

        # Grids for the origin-sensitivity study, built once per object (the reference
        # side of each shifted pair is the same for all four methods).
        offsets = shift_offsets(PRIMARY_V, rng)
        shifted_ref_keys = [occupied_keys(rpts, origin - off, PRIMARY_V) for off in offsets]

        capture = cfg["captures"][0]  # exactly one capture per object
        f1_panels = f1_pages.get(page_id, {}).get("panels", {})

        for method_id in METHOD_ORDER:
            if method_id not in capture["methods"]:
                continue
            exp_id, rel_path = capture["methods"][method_id]
            src_path = PROJECT_ROOT / rel_path
            print(f"  [{page_id}/{method_id}] {exp_id} <- {src_path.name}", flush=True)

            src = o3d.io.read_point_cloud(str(src_path))
            raw_pts = np.asarray(src.points)
            matched = src.voxel_down_sample(VOXEL_M)
            mpts = np.asarray(matched.points)

            kept_mask, d_s2t_cm = gap_kept_mask(matched, ref, dbscan_cfg, checkbox_checked)
            kept_pts = mpts[kept_mask]
            n_excluded = int((~kept_mask).sum())

            panel_key = f'{capture["id"]}__{method_id}'
            row = {
                "page_id": page_id,
                "object_id": capture["id"],
                "shape_en": SHAPE_EN[page_id], "shape_ru": SHAPE_RU[page_id],
                "ref_note_en": REF_NOTE_EN[page_id],
                "method": method_id,
                "exp_id": exp_id,
                "panel_key": panel_key,
                "dbscan_mode": dbscan_mode,
                "gap_mask_applied": not checkbox_checked,
                "clean_reference": checkbox_checked,  # complete reference -> uncontaminated row
                "n_excluded_gap_points": n_excluded,
                "raw_points": int(len(raw_pts)),
                "matched_points": int(len(mpts)),
                "kept_points": int(len(kept_pts)),
                "raw_to_matched_ratio": round(len(raw_pts) / len(mpts), 2) if len(mpts) else None,
                "ref_points": int(len(rpts)),
                "sanity": sanity,
                "f1_3cm_pct": f1_panels.get(panel_key, {}).get("f1_3cm"),
                "f1_5cm_pct": f1_panels.get(panel_key, {}).get("f1_5cm"),
                "f1_10cm_pct": f1_panels.get(panel_key, {}).get("f1_10cm"),
                "sweep": {},
            }

            # --- the sweep (DECISION 1): primary metric at every voxel size ---
            for v in VOXEL_SIZES_M:
                stats = voxel_iou(occupied_keys(kept_pts, origin, v), ref_keys[v])
                row["sweep"][f"{v*100:g}cm"] = stats
            # ΔIoU(10-3), the direct counterpart of the F1 table's ΔF1@10-3 column: a pure
            # offset closes as the voxel widens (large delta), a real coverage hole does not.
            row["iou_delta_10_3_pp"] = iou_delta_10_3(row)
            row["iou_pct"] = row["sweep"][f"{PRIMARY_V*100:g}cm"]["iou_pct"]
            row["precision_vox_pct"] = row["sweep"][f"{PRIMARY_V*100:g}cm"]["precision_vox_pct"]
            row["recall_vox_pct"] = row["sweep"][f"{PRIMARY_V*100:g}cm"]["recall_vox_pct"]

            # --- grid-origin sensitivity (DECISION 3), at the primary size only ---
            shift_ious = [
                voxel_iou(occupied_keys(kept_pts, origin - off, PRIMARY_V), rk)["iou_pct"]
                for off, rk in zip(offsets, shifted_ref_keys)
            ]
            row["shift_study"] = {
                "n_grids": len(shift_ious),
                "iou_min_pct": round(float(np.min(shift_ious)), 2),
                "iou_max_pct": round(float(np.max(shift_ious)), 2),
                "iou_mean_pct": round(float(np.mean(shift_ious)), 2),
                "iou_std_pp": round(float(np.std(shift_ious)), 2),
                "iou_spread_pp": round(float(np.max(shift_ious) - np.min(shift_ious)), 2),
                "iou_all_pct": [round(x, 2) for x in shift_ious],
            }

            # --- occupancy threshold k (DECISION 4), raw cloud, no gap mask ---
            # Raw and unmasked on purpose: k >= 2 is a check on the density confound, so it
            # has to see the density the method actually delivered, and it must not be
            # entangled with the gap mask at the same time.
            row["k_study"] = {
                f"k{k}": voxel_iou(occupied_keys(raw_pts, origin, PRIMARY_V, k),
                                   occupied_keys(rpts, origin, PRIMARY_V, k))
                for k in K_SENSITIVITY
            }

            # --- raw vs 1cm-matched invariance at k = 1 (DECISION 4) ---
            iou_raw = row["k_study"]["k1"]["iou_pct"]
            iou_matched_nogap = voxel_iou(occupied_keys(mpts, origin, PRIMARY_V), ref_keys[PRIMARY_V])["iou_pct"]
            row["invariance"] = {
                "iou_raw_cloud_pct": iou_raw,
                "iou_matched_cloud_pct": iou_matched_nogap,
                "delta_pp": round(iou_matched_nogap - iou_raw, 2),
            }

            sweep_str = "  ".join(f"IoU@{k}={row['sweep'][k]['iou_pct']:.1f}%" for k in row["sweep"])
            print(f"          {sweep_str}   prec_vox={row['precision_vox_pct']:.1f}% "
                  f"rec_vox={row['recall_vox_pct']:.1f}%  "
                  f"shift spread={row['shift_study']['iou_spread_pp']:.2f}pp  "
                  f"raw/matched delta={row['invariance']['delta_pp']:+.2f}pp  "
                  f"F1@3cm={row['f1_3cm_pct']}", flush=True)

            rows.append(row)
    return rows


# --- ranking analysis -------------------------------------------------------------

RANK_SWEEP_KEYS = ["3cm", "5cm", "10cm"]
# 2 cm is deliberately excluded from the ordering-stability check: it sits below both
# lower bounds of DECISION 1, so a reordering there says something about reference
# sampling, not about the methods.


def _order(rows: list[dict], key) -> list[str]:
    """Method ids best-first by `key` (a callable on a row)."""
    return [r["method"] for r in sorted(rows, key=lambda r: -(key(r) if key(r) is not None else -1e9))]


def _swapped_pairs(order_a: list[str], order_b: list[str]) -> list[tuple[str, str]]:
    """Method pairs whose relative order differs between two rankings.

    Comparing whole orderings answers "do they disagree"; comparing pairs answers "about
    which two methods", which is the only form the disagreement can be checked against the
    metric's own resolution."""
    pos_a = {m: i for i, m in enumerate(order_a)}
    pos_b = {m: i for i, m in enumerate(order_b)}
    return [(m1, m2) for m1, m2 in itertools.combinations(order_a, 2)
            if (pos_a[m1] < pos_a[m2]) != (pos_b[m1] < pos_b[m2])]


def _spearman(a: list[float], b: list[float]):
    from scipy.stats import spearmanr
    if len(a) < 3 or len(set(a)) < 2 or len(set(b)) < 2:
        return None, None
    rho, p = spearmanr(a, b)
    return round(float(rho), 3), round(float(p), 4)


def analyse(rows: list[dict]) -> dict:
    """Everything section 8 of the brief asks to decide *before* the numbers arrive:
    does IoU reorder anything relative to F1@3cm, does the sweep expose a method that is
    good at only one scale, and is the grid-origin wobble small next to the gaps between
    methods."""
    by_object: dict[str, list[dict]] = {}
    for r in rows:
        by_object.setdefault(r["object_id"], []).append(r)

    per_object = []
    for object_id, group in by_object.items():
        iou_order = _order(group, lambda r: r["iou_pct"])
        f1_order = _order(group, lambda r: r["f1_3cm_pct"])
        rho, p = _spearman([r["iou_pct"] for r in group], [r["f1_3cm_pct"] for r in group])

        # ordering stability across the sweep (criterion b): does the ranking at 3/5/10 cm
        # ever disagree with itself?
        sweep_orders = {k: _order(group, lambda r, k=k: r["sweep"][k]["iou_pct"]) for k in RANK_SWEEP_KEYS}
        sweep_stable = len({tuple(o) for o in sweep_orders.values()}) == 1

        # how far apart the methods actually are, against what the grid origin does to
        # them (DECISION 3's defence line)
        ious = sorted((r["iou_pct"] for r in group), reverse=True)
        adjacent_gaps = [round(ious[i] - ious[i + 1], 2) for i in range(len(ious) - 1)]
        max_shift_spread = round(max(r["shift_study"]["iou_spread_pp"] for r in group), 2)

        # The per-method spread above is the pessimistic reading: a grid shift moves all
        # four methods of an object the same way, so what decides whether the choice of
        # origin matters is whether the ORDER holds, not how far one IoU travelled. The
        # offsets are drawn once per object, so grid i is the same grid for all four rows
        # and they can be compared column-wise.
        n_grids = group[0]["shift_study"]["n_grids"]
        grid_orders, grid_min_gaps = [], []
        for i in range(n_grids):
            ranked = sorted(((r["shift_study"]["iou_all_pct"][i], r["method"]) for r in group), reverse=True)
            grid_orders.append(tuple(m for _, m in ranked))
            vals = [v for v, _ in ranked]
            if len(vals) > 1:
                grid_min_gaps.append(round(min(vals[j] - vals[j + 1] for j in range(len(vals) - 1)), 2))
        order_stable_across_grids = len(set(grid_orders)) == 1

        # A reordering only counts if it survives the metric's own resolution. Without a
        # gate, a 0.3 pp swap sitting inside a 1.5 pp grid band sails straight into "IoU
        # disagrees with F1, so it belongs in chapter 5" - which is how a noise floor gets
        # written up as a finding. Two gates follow, and they are deliberately different:
        # the IoU-vs-F1 swaps get the sharp pair-wise test (does this pair ever flip across
        # the grid ensemble), the sweep swaps get a blunt magnitude test, because only the
        # primary voxel size has a grid ensemble to test against.
        iou_by_method = {r["method"]: r["iou_pct"] for r in group}
        f1_by_method = {r["method"]: r["f1_3cm_pct"] for r in group}
        grid_series = {r["method"]: r["shift_study"]["iou_all_pct"] for r in group}
        f1_swaps = []
        for m1, m2 in _swapped_pairs(iou_order, f1_order):
            gap = abs(iou_by_method[m1] - iou_by_method[m2])
            # The sharp test, and the reason the whole grid ensemble is kept per row rather
            # than collapsed to a spread: re-measure THIS PAIR on all 16 grids and ask
            # whether the sign of their difference ever flips. Comparing the pair's gap to
            # the largest per-method spread is the blunt version - it charges the pair for
            # a wobble that moved both methods together, and on the bollard that spread is
            # 14 pp, which would veto every comparison on the object. A pair that keeps its
            # sign on every grid is genuinely ordered, whatever the absolute values did.
            diffs = [a - b for a, b in zip(grid_series[m1], grid_series[m2])]
            sign_consistent = min(diffs) > 0 or max(diffs) < 0
            f1_swaps.append({
                "pair": [m1, m2],
                "iou_gap_pp": round(gap, 2),
                "f1_gap_pp": round(abs(f1_by_method[m1] - f1_by_method[m2]), 2),
                "min_abs_gap_across_grids_pp": round(min(abs(d) for d in diffs), 2),
                "grid_sign_consistent": bool(sign_consistent),
                "exceeds_max_per_method_spread": bool(gap > max_shift_spread),
                "robust": bool(sign_consistent),
            })
        sweep_swaps = []
        for ka, kb in itertools.combinations(RANK_SWEEP_KEYS, 2):
            va = {r["method"]: r["sweep"][ka]["iou_pct"] for r in group}
            vb = {r["method"]: r["sweep"][kb]["iou_pct"] for r in group}
            for m1, m2 in _swapped_pairs(sweep_orders[ka], sweep_orders[kb]):
                ga, gb = abs(va[m1] - va[m2]), abs(vb[m1] - vb[m2])
                # No grid ensemble exists at 3 and 10 cm (the shift study runs at the
                # primary size only), so this one keeps the blunt gate: the pair must be
                # further apart than the object's largest per-method grid spread at BOTH
                # sizes. Conservative in the safe direction - it can dismiss a real
                # reordering, it cannot manufacture one.
                sweep_swaps.append({
                    "sizes": [ka, kb], "pair": [m1, m2],
                    "gap_pp": [round(ga, 2), round(gb, 2)],
                    "robust": bool(ga > max_shift_spread and gb > max_shift_spread),
                })

        # The question section 8 really asks about the sweep is not "does it reorder
        # anything" but "does it reorder anything F1 had not already noticed". F1 carries
        # its own scale-sensitivity column, ΔF1@10-3, built for exactly this: a method
        # whose score jumps between the tight and loose threshold. If ΔIoU(10-3) singles
        # out the same method as ΔF1(10-3), the sweep is restating a conclusion the
        # existing table already reached, and a restatement is not a reason for a chapter.
        d_iou = {r["method"]: r["sweep"]["10cm"]["iou_pct"] - r["sweep"]["3cm"]["iou_pct"] for r in group}
        d_f1 = {r["method"]: (r["f1_10cm_pct"] - r["f1_3cm_pct"])
                for r in group if r["f1_10cm_pct"] is not None and r["f1_3cm_pct"] is not None}
        if len(d_f1) == len(d_iou):
            top_iou, top_f1 = max(d_iou, key=d_iou.get), max(d_f1, key=d_f1.get)
            ms = list(d_iou)
            rho_delta, _ = _spearman([d_iou[m] for m in ms], [d_f1[m] for m in ms])
            sweep_already_in_delta_f1 = top_iou == top_f1
        else:
            top_iou = max(d_iou, key=d_iou.get)
            top_f1, rho_delta, sweep_already_in_delta_f1 = None, None, None

        per_object.append({
            "object_id": object_id,
            "page_id": group[0]["page_id"],
            "clean_reference": group[0]["clean_reference"],
            "iou_order_5cm": iou_order,
            "f1_3cm_order": f1_order,
            "order_agrees": iou_order == f1_order,
            "spearman_rho_iou_vs_f1_3cm": rho,
            "spearman_p": p,
            "sweep_orders": sweep_orders,
            "sweep_order_stable_3_5_10cm": sweep_stable,
            "iou_adjacent_gaps_pp": adjacent_gaps,
            "iou_min_adjacent_gap_pp": min(adjacent_gaps) if adjacent_gaps else None,
            "max_grid_shift_spread_pp": max_shift_spread,
            "shift_smaller_than_gaps": (min(adjacent_gaps) > max_shift_spread) if adjacent_gaps else None,
            "n_grids": n_grids,
            "order_stable_across_grids": order_stable_across_grids,
            "distinct_orders_across_grids": [list(o) for o in dict.fromkeys(grid_orders)],
            "min_adjacent_gap_across_grids_pp": min(grid_min_gaps) if grid_min_gaps else None,
            "f1_swaps": f1_swaps,
            "has_robust_f1_swap": any(sw["robust"] for sw in f1_swaps),
            "sweep_swaps": sweep_swaps,
            "has_robust_sweep_swap": any(sw["robust"] for sw in sweep_swaps),
            "most_threshold_sensitive_by_delta_iou": top_iou,
            "most_threshold_sensitive_by_delta_f1": top_f1,
            "spearman_delta_iou_vs_delta_f1": rho_delta,
            "sweep_story_already_in_delta_f1": sweep_already_in_delta_f1,
        })

    overall_rho, overall_p = _spearman([r["iou_pct"] for r in rows], [r["f1_3cm_pct"] for r in rows])

    disagreeing = [o["object_id"] for o in per_object if not o["order_agrees"]]
    unstable = [o["object_id"] for o in per_object if not o["sweep_order_stable_3_5_10cm"]]
    grid_unstable = [o["object_id"] for o in per_object if not o["order_stable_across_grids"]]
    # Only reorderings wider than the grid noise count towards the verdict; the rest are
    # recorded so they are visible, but they decide nothing.
    robust_a = [o["object_id"] for o in per_object if o["has_robust_f1_swap"]]
    # A robust sweep reordering only counts if it is not already told by ΔF1@10-3.
    robust_b = [o["object_id"] for o in per_object
                if o["has_robust_sweep_swap"] and not o["sweep_story_already_in_delta_f1"]]
    echoes_f1 = [o["object_id"] for o in per_object
                 if o["has_robust_sweep_swap"] and o["sweep_story_already_in_delta_f1"]]
    noise_a = [o for o in disagreeing if o not in robust_a]
    noise_b = [o for o in unstable if o not in robust_b and o not in echoes_f1]
    criterion_a = bool(robust_a)
    criterion_b = bool(robust_b)
    deserves = criterion_a or criterion_b

    if deserves:
        parts = []
        if criterion_a:
            parts.append(f"IoU reorders the methods on {', '.join(robust_a)} relative to F1@3cm, "
                         f"by more than the grid-origin noise")
        if criterion_b:
            parts.append(f"the voxel sweep reorders them on {', '.join(robust_b)} between 3, 5 and "
                         f"10 cm, by more than the grid-origin noise")
        headline = "Belongs in chapter 5: " + "; ".join(parts) + "."
    else:
        n_obj = len(per_object)
        n_same = sum(1 for o in per_object if o["order_agrees"])
        tail = ("Mention it in the methodology as an alternative that was considered, and leave "
                "it out of the results.")
        if disagreeing or unstable:
            # "It agreed with F1 everywhere" would be false here - it disagreed, the
            # disagreements just did not survive. Say which, or the verdict overstates itself.
            headline = (f"Does not belong in chapter 5: IoU matches the F1@3cm ordering exactly on "
                        f"{n_same} of {n_obj} objects, and every reordering it produces on the "
                        f"other {n_obj - n_same} fails on inspection - see below. No new "
                        f"conclusion. {tail}")
        else:
            headline = (f"Does not belong in chapter 5: IoU reproduces the F1@3cm ordering on "
                        f"{'both' if n_obj == 2 else f'all {n_obj}'} "
                        f"object{'' if n_obj == 1 else 's'} and the sweep is flat. {tail}")
    if echoes_f1:
        headline += (" The voxel sweep does reorder methods beyond the grid noise on "
                     f"{', '.join(echoes_f1)}, but singles out the same method ΔF1@10-3 already "
                     "singles out there, so it restates the existing table rather than adding to it.")
    if noise_a or noise_b:
        headline += (" Reorderings that were found but are smaller than the grid-origin noise, and "
                     "so decide nothing: " + ", ".join(sorted(set(noise_a + noise_b))) + ".")
    if grid_unstable:
        headline += (" Caveat to state either way: the method ordering does not survive the "
                     f"grid-origin shift on {', '.join(grid_unstable)}, so IoU cannot separate "
                     "those methods at this voxel size.")

    return {
        "criteria": {
            "a_ranking_differs_from_f1_3cm": criterion_a,
            "a_objects": robust_a,
            "a_objects_within_grid_noise": noise_a,
            "b_sweep_reorders_methods": criterion_b,
            "b_objects": robust_b,
            "b_objects_within_grid_noise": noise_b,
            "b_objects_restating_delta_f1": echoes_f1,
            "grid_origin_reorders_methods": bool(grid_unstable),
            "grid_origin_unstable_objects": grid_unstable,
            "deserves_chapter_5": deserves,
        },
        "headline": headline,
        "spearman_rho_iou_vs_f1_3cm_all_rows": overall_rho,
        "spearman_p_all_rows": overall_p,
        "n_rows": len(rows),
        "per_object": per_object,
    }


# --- output -----------------------------------------------------------------------

def write_json(rows: list[dict], analysis: dict, path: Path) -> None:
    for r in rows:  # derived, so it is present whether the rows were just computed or reloaded
        r["iou_delta_10_3_pp"] = iou_delta_10_3(r)
    payload = {
        "source": "compute_voxel_iou.py",
        "metric": "surface-voxel IoU (occupied surface voxels; not volumetric - both clouds "
                  "are surface samples and no interior filling is applied)",
        "definition": {
            "primary_voxel_m": PRIMARY_V,
            "voxel_sweep_m": VOXEL_SIZES_M,
            "voxel_sweep_note": "2 cm is below the reference-sampling and alignment-RMSE lower "
                                "bounds; 10 cm no longer resolves the lamppost or the sign pole. "
                                "Both are reported to show what happens there, not as results.",
            "occupancy_threshold_k": 1,
            "k_sensitivity": K_SENSITIVITY,
            "grid_origin": "minimum corner of the reference bounding box; identical for both "
                           "clouds of every pair",
            "grid_shift_study": f"7 half-voxel corner shifts + {N_RANDOM_SHIFTS} uniform "
                                f"sub-voxel offsets, at the primary voxel size",
            "source_cloud": "final aligned .ply from MERGED_OBJECTS, thinned onto the 1 cm grid "
                            "(VOXEL_M), gap-cluster points removed where the reference is "
                            "incomplete",
            "reference_cloud": "as delivered, exact duplicates dropped (load_reference)",
            "gap_exclusion": "find_gap_point_mask() from remove_reference_gap_points.py at each "
                             "object's tuned ft/eps/mp; none for the two complete references",
            "precision_vox": "|A n B| / |A|, A = reconstruction",
            "recall_vox": "|A n B| / |B|, B = reference",
        },
        "analysis": analysis,
        "rows": rows,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2))
    print(f"Wrote {path.relative_to(PROJECT_ROOT)}")


HEADER_FILL = "1F3864"


def _style_header(ws) -> None:
    from openpyxl.styles import Font, PatternFill, Alignment
    fill = PatternFill("solid", fgColor=HEADER_FILL)
    font = Font(bold=True, color="FFFFFF")
    for c in ws[1]:
        c.font, c.fill = font, fill
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    ws.freeze_panes = "A2"
    ws.row_dimensions[1].height = 32


def _set_widths(ws, widths) -> None:
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[ws.cell(row=1, column=i).column_letter].width = w


def write_xlsx(rows: list[dict], analysis: dict, path: Path) -> None:
    from openpyxl import Workbook
    from openpyxl.styles import Font, Alignment, Border, Side

    wb = Workbook()
    best_font = Font(bold=True)
    top_border = Border(top=Side(style="medium", color="9AA07A"))
    pk = f"{PRIMARY_V*100:g}cm"

    obj_groups: dict[str, list[int]] = {}
    for i, r in enumerate(rows):
        obj_groups.setdefault(r["object_id"], []).append(i)

    # --- sheet 1: the metric, at the primary voxel size -----------------------------
    ws = wb.active
    ws.title = "summary"
    ws.append(["object_id", "shape", "method", f"IoU@{pk} (%)", f"voxel precision@{pk} (%)",
               f"voxel recall@{pk} (%)", "ΔIoU@10−3cm (pp)", "source voxels", "reference voxels",
               "shared voxels", "F1@3cm (%)", "IoU rank", "F1@3cm rank", "grid-origin spread (pp)",
               "raw/matched ratio", "DBSCAN mode", "reference note"])
    _style_header(ws)
    for object_id, idxs in obj_groups.items():
        group = [rows[i] for i in idxs]
        iou_rank = {m: n + 1 for n, m in enumerate(_order(group, lambda r: r["iou_pct"]))}
        f1_rank = {m: n + 1 for n, m in enumerate(_order(group, lambda r: r["f1_3cm_pct"]))}
        for r in group:
            ws.append([r["object_id"], r["shape_en"], r["method"], r["iou_pct"],
                       r["precision_vox_pct"], r["recall_vox_pct"], iou_delta_10_3(r),
                       r["sweep"][pk]["n_vox_source"], r["sweep"][pk]["n_vox_ref"],
                       r["sweep"][pk]["n_vox_inter"], r["f1_3cm_pct"],
                       iou_rank[r["method"]], f1_rank[r["method"]],
                       r["shift_study"]["iou_spread_pp"], r["raw_to_matched_ratio"],
                       r["dbscan_mode"], r["ref_note_en"]])
    # bold the best IoU per object, and merge the columns that repeat down each block
    for object_id, idxs in obj_groups.items():
        best_i = max(idxs, key=lambda i: rows[i]["iou_pct"])
        ws.cell(row=best_i + 2, column=4).font = best_font
        first_row, last_row = idxs[0] + 2, idxs[-1] + 2
        for col in (1, 2, 9, 16, 17):
            ws.merge_cells(start_row=first_row, start_column=col, end_row=last_row, end_column=col)
            ws.cell(row=first_row, column=col).alignment = Alignment(
                vertical="center", wrap_text=(col == 17),
                horizontal=("left" if col in (1, 2, 17) else "center"))
        for col in range(1, 18):
            ws.cell(row=first_row, column=col).border = top_border
    _set_widths(ws, [20, 18, 13, 12, 16, 14, 15, 13, 15, 13, 12, 10, 12, 16, 14, 14, 60])

    # --- sheet 2: the voxel-size sweep ----------------------------------------------
    ws = wb.create_sheet("sweep")
    ws.append(["object_id", "shape", "method", "voxel (cm)", "IoU (%)", "voxel precision (%)",
               "voxel recall (%)", "source voxels", "reference voxels", "shared voxels", "note"])
    _style_header(ws)
    sweep_note = {
        "2cm": "below both lower bounds (reference spacing, alignment RMSE) - artefact, not a result",
        "3cm": "",
        "5cm": "primary",
        "10cm": "lamppost and sign pole no longer resolved - measures bounding volume, not shape",
    }
    for r in rows:
        for k, s in r["sweep"].items():
            ws.append([r["object_id"], r["shape_en"], r["method"], float(k.rstrip("cm")),
                       s["iou_pct"], s["precision_vox_pct"], s["recall_vox_pct"],
                       s["n_vox_source"], s["n_vox_ref"], s["n_vox_inter"], sweep_note.get(k, "")])
    _set_widths(ws, [20, 18, 13, 11, 10, 16, 14, 13, 15, 13, 74])

    # --- sheet 3: everything the metric was stress-tested against --------------------
    ws = wb.create_sheet("sensitivity")
    ws.append(["object_id", "method", f"IoU@{pk} (%)", "grid shift: min (%)", "grid shift: max (%)",
               "grid shift: spread (pp)", "grid shift: std (pp)", "grids tested",
               "k=1 IoU, raw cloud (%)", "k=2 IoU, raw cloud (%)", "k=3 IoU, raw cloud (%)",
               "raw/matched ratio", "IoU on 1cm cloud (%)", "raw->1cm delta (pp)",
               "gap points excluded", "DBSCAN mode"])
    _style_header(ws)
    for r in rows:
        ws.append([r["object_id"], r["method"], r["iou_pct"],
                   r["shift_study"]["iou_min_pct"], r["shift_study"]["iou_max_pct"],
                   r["shift_study"]["iou_spread_pp"], r["shift_study"]["iou_std_pp"],
                   r["shift_study"]["n_grids"],
                   r["k_study"]["k1"]["iou_pct"], r["k_study"]["k2"]["iou_pct"],
                   r["k_study"]["k3"]["iou_pct"], r["raw_to_matched_ratio"],
                   r["invariance"]["iou_matched_cloud_pct"], r["invariance"]["delta_pp"],
                   r["n_excluded_gap_points"], r["dbscan_mode"]])
    _set_widths(ws, [20, 13, 12, 15, 15, 16, 15, 12, 17, 17, 17, 14, 17, 15, 15, 14])

    # --- sheet 4: does IoU say anything F1 did not? ----------------------------------
    ws = wb.create_sheet("ranking")
    n_cols = 15
    ws.append(["object_id", "reference", f"IoU@{pk} order (best first)", "F1@3cm order (best first)",
               "orders agree", "Spearman rho", "IoU order stable at 3/5/10 cm",
               "IoU order stable on every grid", "grids tested",
               "smallest gap between methods (pp)", "smallest gap on any grid (pp)",
               "largest per-method grid spread (pp)", "most threshold-sensitive by ΔIoU@10−3",
               "most threshold-sensitive by ΔF1@10−3", "sweep adds what ΔF1 lacked"])
    _style_header(ws)
    for o in analysis["per_object"]:
        ws.append([o["object_id"], "complete" if o["clean_reference"] else "incomplete (gap mask)",
                   " > ".join(o["iou_order_5cm"]), " > ".join(o["f1_3cm_order"]),
                   "yes" if o["order_agrees"] else "NO", o["spearman_rho_iou_vs_f1_3cm"],
                   "yes" if o["sweep_order_stable_3_5_10cm"] else "NO",
                   "yes" if o["order_stable_across_grids"] else "NO", o["n_grids"],
                   o["iou_min_adjacent_gap_pp"], o["min_adjacent_gap_across_grids_pp"],
                   o["max_grid_shift_spread_pp"],
                   o["most_threshold_sensitive_by_delta_iou"], o["most_threshold_sensitive_by_delta_f1"],
                   (("n/a - sweep does not reorder" if not o["sweep_swaps"]
                     else "n/a - sweep reorderings all within grid noise")
                    if not o["has_robust_sweep_swap"]
                    else ("NO - restates ΔF1" if o["sweep_story_already_in_delta_f1"] else "yes"))])
    ws.append([])
    row_vals = [""] * n_cols
    row_vals[0], row_vals[1] = "ALL ROWS", f"n = {analysis['n_rows']}"
    row_vals[5] = analysis["spearman_rho_iou_vs_f1_3cm_all_rows"]
    ws.append(row_vals)
    ws.cell(row=ws.max_row, column=1).font = best_font
    ws.append([])
    ws.append(["VERDICT", analysis["headline"]])
    ws.cell(row=ws.max_row, column=1).font = best_font
    ws.cell(row=ws.max_row, column=2).alignment = Alignment(wrap_text=True, vertical="top")
    ws.merge_cells(start_row=ws.max_row, start_column=2, end_row=ws.max_row, end_column=n_cols)
    ws.row_dimensions[ws.max_row].height = 46
    # "largest per-method grid spread" is the pessimistic number and is deliberately the
    # LAST column: it moves all four methods together, so the two stability columns to its
    # left are what actually decide whether the grid choice changes a conclusion.
    _set_widths(ws, [20, 24, 34, 34, 13, 13, 16, 17, 11, 17, 17, 18, 20, 18, 24])

    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    print(f"Wrote {path.relative_to(PROJECT_ROOT)}")


# --- main -------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--objects", nargs="*", default=None,
                        help="page ids to run (default: all of MERGED_OBJECTS)")
    parser.add_argument("--no-write", action="store_true", help="compute and print, write nothing")
    parser.add_argument("--from-json", action="store_true",
                        help="skip the point clouds entirely and re-run the ranking analysis and "
                             "both writers over the rows already in voxel_iou_summary.json. The "
                             "IoU numbers cost minutes of Chamfer distances and DBSCAN; the "
                             "analysis on top of them costs nothing, so iterating on how the "
                             "result is READ should not mean recomputing WHAT was measured.")
    args = parser.parse_args()

    if args.from_json:
        if not OUT_JSON.exists():
            parser.error(f"--from-json needs {OUT_JSON.relative_to(PROJECT_ROOT)}; run without it first")
        rows = json.loads(OUT_JSON.read_text())["rows"]
        if args.objects:
            rows = [r for r in rows if r["page_id"] in args.objects]
        print(f"Re-analysing {len(rows)} rows from {OUT_JSON.relative_to(PROJECT_ROOT)}", flush=True)
    else:
        page_ids = args.objects or list(MERGED_OBJECTS)
        unknown = [p for p in page_ids if p not in MERGED_OBJECTS]
        if unknown:
            parser.error(f"unknown page id(s): {unknown}; known: {list(MERGED_OBJECTS)}")
        rows = compute_rows(page_ids)

    analysis = analyse(rows)

    print("\n=== ranking: IoU@5cm vs F1@3cm ===", flush=True)
    for o in analysis["per_object"]:
        if o["order_agrees"]:
            flag = "same order"
        elif o["has_robust_f1_swap"]:
            flag = "*** DIFFERENT ORDER (beyond grid noise) ***"
        else:
            flag = "different order, but within grid noise"
        print(f"  {o['object_id']:22s} IoU: {' > '.join(o['iou_order_5cm']):<48s} "
              f"F1: {' > '.join(o['f1_3cm_order']):<48s} {flag}"
              f"  rho={o['spearman_rho_iou_vs_f1_3cm']}", flush=True)
        print(f"  {'':22s} order stable at 3/5/10cm: "
              f"{'yes' if o['sweep_order_stable_3_5_10cm'] else 'NO'}; "
              f"order stable on all {o['n_grids']} grid origins: "
              f"{'yes' if o['order_stable_across_grids'] else 'NO'}; "
              f"smallest method gap {o['iou_min_adjacent_gap_pp']} pp "
              f"({o['min_adjacent_gap_across_grids_pp']} pp at its worst grid), "
              f"per-method grid spread up to {o['max_grid_shift_spread_pp']} pp", flush=True)
    print(f"\n  Spearman rho over all {analysis['n_rows']} rows: "
          f"{analysis['spearman_rho_iou_vs_f1_3cm_all_rows']} (p={analysis['spearman_p_all_rows']})", flush=True)
    print(f"\n=== VERDICT ===\n  {analysis['headline']}\n", flush=True)

    if not args.no_write:
        write_json(rows, analysis, OUT_JSON)
        write_xlsx(rows, analysis, OUT_XLSX)


if __name__ == "__main__":
    main()
