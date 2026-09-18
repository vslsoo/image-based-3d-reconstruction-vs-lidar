"""R7: the 36 pairwise F1 comparisons with a PAIRED block bootstrap.

Appendix A resamples the two reconstructions independently and justifies it by saying
they share no images. They do: §4.3 states that every method received the same
photographs. More importantly, completeness is measured over the same reference points
for both methods, so drawing those points twice over adds a second, avoidable source of
variation to the difference.

Here one draw of 5 cm cells is shared by the two methods being compared. Cells are
defined by the same grid in the reference frame (floor(p / block)), so a cell means the
same piece of space for both clouds:

  * accuracy - the cell universe is the union of the cells occupied by either method's
    kept points; a cell where one method placed nothing contributes nothing to it.
  * completeness - the reference points are literally the same set, so the same cells
    carry both methods' indicators.

Whatever a cell does to both methods (a hard patch, a gap) now cancels in the
difference, which is the point of pairing. The estimator, the block size, the number of
draws and the seed are the ones Appendix A already uses.

Writes docs/tables/paired_pairwise_bootstrap.json. Changes nothing the thesis reads.

Usage:  python3 src/registration/paired_pairwise_bootstrap.py
"""
from __future__ import annotations

import itertools
import json
import sys
from pathlib import Path

import numpy as np
import open3d as o3d

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src" / "registration"))

from build_object_page import (  # noqa: E402
    MERGED_OBJECTS, METHOD_ORDER, DEFAULT_DBSCAN_SLIDERS,
)
from build_accuracy_f1_summary_table import load_reference, f_score  # noqa: E402

VOXEL_M = 0.01
BLOCK_M = 0.05
THRESHOLD_CM = 3.0
B_BOOT = 2000
SEED = 123
CHUNK_CELLS = 20_000_000
OUT = ROOT / "docs" / "tables" / "paired_pairwise_bootstrap.json"


def cell_ids(points, block_m):
    return np.floor(points / block_m).astype(np.int64)


def pack(rows):
    """One int64 key per cell, so cells can be matched between two clouds."""
    if len(rows) == 0:
        return np.empty(0, dtype=np.int64)
    r = rows - rows.min(0)
    span = r.max(0) + 1
    return (r[:, 0] * span[1] + r[:, 1]) * span[2] + r[:, 2]


def per_cell(keys, universe, indicator):
    """within / total per cell of `universe`, for points carrying `keys`."""
    within = np.zeros(len(universe)); total = np.zeros(len(universe))
    if len(keys):
        pos = np.searchsorted(universe, keys)
        ok = (pos < len(universe)) & (universe[np.minimum(pos, len(universe) - 1)] == keys)
        np.add.at(total, pos[ok], 1.0)
        np.add.at(within, pos[ok], indicator[ok].astype(float))
    return within, total


def paired_draws(parts, nb, rng, B=B_BOOT):
    """One shared draw of cells; returns a ratio array per entry of `parts`."""
    outs = [np.empty(B) for _ in parts]
    chunk = max(1, min(B, CHUNK_CELLS // max(nb, 1)))
    done = 0
    while done < B:
        n = min(chunk, B - done)
        idx = rng.integers(0, nb, size=(n, nb))
        for o, (w, t) in zip(outs, parts):
            s = t[idx].sum(1)
            o[done:done + n] = np.where(s > 0, w[idx].sum(1) / np.maximum(s, 1e-12), 0.0)
        done += n
    return outs


def main() -> None:
    rng = np.random.default_rng(SEED)
    results = []
    for page_id, cfg in MERGED_OBJECTS.items():
        ref = load_reference(ROOT / cfg["ref"])
        rpts = np.asarray(ref.points)
        dbs = {**DEFAULT_DBSCAN_SLIDERS, **cfg.get("dbscan", {})}
        honest = cfg["checkbox_checked"]
        cap = cfg["captures"][0]

        runs = {}
        for m in METHOD_ORDER:
            if m not in cap["methods"]:
                continue
            src = o3d.io.read_point_cloud(str(ROOT / cap["methods"][m][1]))
            matched = src.voxel_down_sample(VOXEL_M)
            pts = np.asarray(matched.points)
            d_s2t = np.asarray(matched.compute_point_cloud_distance(ref)) * 100.0
            d_t2s = np.asarray(ref.compute_point_cloud_distance(matched)) * 100.0
            keep = np.ones(len(pts), bool)
            if not honest:
                gap = np.zeros(len(pts), bool)
                far = np.where(d_s2t > dbs["ft_default"])[0]
                if far.size:
                    p = o3d.geometry.PointCloud()
                    p.points = o3d.utility.Vector3dVector(pts[far])
                    lab = np.array(p.cluster_dbscan(eps=dbs["eps_default"] / 100.0,
                                                    min_points=dbs["mp_default"]))
                    gap[far[lab >= 0]] = True
                keep = ~gap
            runs[m] = {"pts": pts[keep], "acc_ind": d_s2t[keep] <= THRESHOLD_CM,
                       "comp_ind": d_t2s <= THRESHOLD_CM}

        # completeness cells: the same reference points for every method
        ckeys = pack(cell_ids(rpts, BLOCK_M))
        cuni = np.unique(ckeys)

        for a, b in itertools.combinations([m for m in METHOD_ORDER if m in runs], 2):
            A, Bm = runs[a], runs[b]
            akeys_a = pack(cell_ids(np.vstack([A["pts"], Bm["pts"]]), BLOCK_M))
            na = len(A["pts"])
            auni = np.unique(akeys_a)
            aw_a, at_a = per_cell(akeys_a[:na], auni, A["acc_ind"])
            aw_b, at_b = per_cell(akeys_a[na:], auni, Bm["acc_ind"])
            cw_a, ct = per_cell(ckeys, cuni, A["comp_ind"])
            cw_b, _ = per_cell(ckeys, cuni, Bm["comp_ind"])

            acc_a, acc_b = paired_draws([(aw_a, at_a), (aw_b, at_b)], len(auni), rng)
            com_a, com_b = paired_draws([(cw_a, ct), (cw_b, ct)], len(cuni), rng)
            f1a = np.where(acc_a + com_a > 0, 2 * acc_a * com_a / (acc_a + com_a), 0) * 100
            f1b = np.where(acc_b + com_b > 0, 2 * acc_b * com_b / (acc_b + com_b), 0) * 100
            diff = f1a - f1b
            lo, hi = np.percentile(diff, [2.5, 97.5])

            point = (f_score(A["acc_ind"].mean(), A["comp_ind"].mean())
                     - f_score(Bm["acc_ind"].mean(), Bm["comp_ind"].mean())) * 100
            results.append({
                "object": page_id, "a": a, "b": b,
                "delta_f1_3cm": round(float(point), 1),
                "ci_lo": round(float(lo), 1), "ci_hi": round(float(hi), 1),
                "resolvable": not (lo <= 0 <= hi),
                "n_cells_acc": int(len(auni)), "n_cells_comp": int(len(cuni)),
            })
            r = results[-1]
            print(f"[{page_id}] {a} - {b}: {r['delta_f1_3cm']:+6.1f} "
                  f"[{r['ci_lo']:+.1f}, {r['ci_hi']:+.1f}] "
                  f"{'resolvable' if r['resolvable'] else 'TIE'}", flush=True)

    OUT.write_text(json.dumps({
        "what": "R7: paired spatial block bootstrap for the 36 pairwise F1 differences",
        "block_cm": BLOCK_M * 100, "draws": B_BOOT, "seed": SEED,
        "threshold_cm": THRESHOLD_CM,
        "rows": results,
    }, indent=1))
    print(f"\nwrote {OUT.relative_to(ROOT)}  ({len(results)} pairs)")


if __name__ == "__main__":
    main()
