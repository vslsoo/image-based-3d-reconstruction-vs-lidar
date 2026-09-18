"""R1: one coverage mask per object, identical for all four methods.

The thesis table builds its gap mask from each method's OWN far points
(build_accuracy_f1_summary_table.py): candidates are that method's points more
than ft cm from the reference, DBSCAN keeps the clustered ones, and those are
dropped before accuracy is counted. The mask therefore differs by method, and so
does the share dropped - which is what review point R1 objects to: the two
objects where COLMAP beats the feed-forward models are exactly the two with no
exclusion at all.

Here the same clustering only LOCATES the uncovered regions, and the regions are
then pooled: the union of every method's clustered gap points, voxelised at
MASK_VOXEL_CM, is one spatial mask per object and is applied to all four clouds.
Completeness is untouched in every regime, exactly as in the thesis table - the
mask marks space the scanner never reached, and reference points are by
definition not in it.

Reported per run: "none" (no exclusion), "per_method" (what the thesis does now)
and "shared" (one mask), each at the object's own far threshold, plus a sweep of
the far threshold at 5 / 7.5 / 10 cm.

Writes docs/tables/coverage_mask_sensitivity.json. Changes nothing the thesis
already reads.

Usage:  python3 src/registration/coverage_mask_sensitivity.py
"""
from __future__ import annotations

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

VOXEL_M = 0.01          # same 1 cm grid the thesis density-matches on
MASK_VOXEL_CM = 5.0     # resolution of the pooled mask
THRESHOLDS_CM = [3.0, 5.0, 10.0]
FT_SWEEP_CM = [5.0, 7.5, 10.0]
OUT = ROOT / "docs" / "tables" / "coverage_mask_sensitivity.json"


def gap_point_mask(mpts, d_s2t_cm, ft_cm, eps_cm, min_points):
    """The thesis rule: far points that DBSCAN puts in a cluster."""
    mask = np.zeros(len(mpts), dtype=bool)
    far_idx = np.where(d_s2t_cm > ft_cm)[0]
    if far_idx.size:
        pcd = o3d.geometry.PointCloud()
        pcd.points = o3d.utility.Vector3dVector(mpts[far_idx])
        labels = np.array(pcd.cluster_dbscan(eps=eps_cm / 100.0,
                                             min_points=min_points))
        mask[far_idx[labels >= 0]] = True
    return mask


def voxel_keys(points, voxel_cm):
    return set(map(tuple, np.floor(points / (voxel_cm / 100.0)).astype(np.int64)))


def in_voxels(points, keys, voxel_cm):
    if not keys:
        return np.zeros(len(points), dtype=bool)
    idx = np.floor(points / (voxel_cm / 100.0)).astype(np.int64)
    return np.fromiter((tuple(k) in keys for k in idx), dtype=bool, count=len(idx))


def scores(d_kept_cm, d_t2s_cm):
    out = {}
    for t in THRESHOLDS_CM:
        acc = float(np.mean(d_kept_cm <= t)) if d_kept_cm.size else 0.0
        comp = float(np.mean(d_t2s_cm <= t)) if d_t2s_cm.size else 0.0
        out[f"acc_{t:g}"] = round(acc * 100, 1)
        out[f"comp_{t:g}"] = round(comp * 100, 1)
        out[f"f1_{t:g}"] = round(f_score(acc, comp) * 100, 1)
    out["df1_10_3"] = round(out["f1_10"] - out["f1_3"], 1)
    return out


def main() -> None:
    results = []
    for page_id, cfg in MERGED_OBJECTS.items():
        ref = load_reference(ROOT / cfg["ref"])
        rpts = np.asarray(ref.points)
        dbs = {**DEFAULT_DBSCAN_SLIDERS, **cfg.get("dbscan", {})}
        capture = cfg["captures"][0]
        print(f"[{page_id}] ft={dbs['ft_default']} eps={dbs['eps_default']} "
              f"mp={dbs['mp_default']} honest={cfg['checkbox_checked']}", flush=True)

        runs = {}
        for method_id in METHOD_ORDER:
            if method_id not in capture["methods"]:
                continue
            exp_id, rel = capture["methods"][method_id]
            src = o3d.io.read_point_cloud(str(ROOT / rel))
            matched = src.voxel_down_sample(VOXEL_M)
            mpts = np.asarray(matched.points)
            runs[method_id] = {
                "exp_id": exp_id,
                "mpts": mpts,
                "d_s2t": np.asarray(matched.compute_point_cloud_distance(ref)) * 100.0,
                "d_t2s": np.asarray(ref.compute_point_cloud_distance(matched)) * 100.0,
            }

        for ft in sorted({dbs["ft_default"], *FT_SWEEP_CM}):
            own = {m: gap_point_mask(r["mpts"], r["d_s2t"], ft,
                                     dbs["eps_default"], dbs["mp_default"])
                   for m, r in runs.items()}
            pooled = set()
            for m, r in runs.items():
                pooled |= voxel_keys(r["mpts"][own[m]], MASK_VOXEL_CM)

            for m, r in runs.items():
                shared = in_voxels(r["mpts"], pooled, MASK_VOXEL_CM)
                for regime, keep in (("none", np.ones(len(r["mpts"]), bool)),
                                     ("per_method", ~own[m]),
                                     ("shared", ~shared)):
                    row = {
                        "object": page_id, "method": m, "exp_id": r["exp_id"],
                        "far_threshold_cm": ft, "regime": regime,
                        "is_object_default_ft": ft == dbs["ft_default"],
                        "thesis_regime": ("none" if cfg["checkbox_checked"]
                                          else "per_method"),
                        "excluded_pct": round(100.0 * (~keep).sum() / len(keep), 1),
                        **scores(r["d_s2t"][keep], r["d_t2s"]),
                    }
                    results.append(row)
            print(f"   ft={ft:>4}: pooled mask {len(pooled)} voxels of "
                  f"{MASK_VOXEL_CM:g} cm", flush=True)

    OUT.write_text(json.dumps({
        "what": "R1 sensitivity: per-method vs one shared coverage mask vs none",
        "mask_voxel_cm": MASK_VOXEL_CM,
        "note": ("Completeness is computed against the full reference in every "
                 "regime, as in the thesis table; the mask only removes "
                 "reconstruction points from the accuracy side."),
        "rows": results,
    }, indent=1))
    print(f"\nwrote {OUT.relative_to(ROOT)}  ({len(results)} rows)")


if __name__ == "__main__":
    main()
