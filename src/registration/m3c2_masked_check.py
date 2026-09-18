"""R2: M3C2 recomputed over the same core points that accuracy keeps.

§4.4 computes M3C2 over every core point, with no gap exclusion, on the grounds
that "where there is no reference there is nothing to pair with". Review point
R1-W6 objects that this fails on a thin plate: with a 15 cm cylinder half-length
and a plate no more than 20 cm deep, a reconstruction point on the sign's
unscanned face finds the opposite, scanned face inside its cylinder and is paired
with it. The pairing is real, so the point is not "unpaired" - it is simply
measured against the wrong surface, and it reports a displacement of about the
plate's thickness.

No M3C2 is recomputed here. run_m3c2_final_six.py already stores every core
point with its distance, its LoD95 and its spreads, so the §4.5 mask can be
applied to those stored points directly. Each core point inherits the kept /
excluded flag of its nearest point in the density-matched cloud the accuracy
table is built from (the two clouds share a frame; the median core-point-to-cloud
distance is about 0.2 cm).

Reported per run, published against masked: the unpaired share, the median |d|
over paired points, the share beyond LoD95, and the median SIGNED d - the last
one because the failure R1-W6 describes has a sign: pairing with the far face
puts the reference systematically on one side.

Writes docs/tables/m3c2_masked_check.json. Changes nothing the thesis reads.

Usage:  python3 src/registration/m3c2_masked_check.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import open3d as o3d
from scipy.spatial import cKDTree

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src" / "registration"))

from build_object_page import (  # noqa: E402
    MERGED_OBJECTS, METHOD_ORDER, DEFAULT_DBSCAN_SLIDERS,
)

VOXEL_M = 0.01
OUT = ROOT / "docs" / "tables" / "m3c2_masked_check.json"


def kept_flags(rel_path, ref, dbs, honest):
    """The §4.5 keep/drop flag for every point of the density-matched cloud."""
    src = o3d.io.read_point_cloud(str(ROOT / rel_path))
    matched = src.voxel_down_sample(VOXEL_M)
    pts = np.asarray(matched.points)
    if honest:
        return pts, np.ones(len(pts), dtype=bool)
    d = np.asarray(matched.compute_point_cloud_distance(ref)) * 100.0
    gap = np.zeros(len(pts), dtype=bool)
    far = np.where(d > dbs["ft_default"])[0]
    if far.size:
        p = o3d.geometry.PointCloud()
        p.points = o3d.utility.Vector3dVector(pts[far])
        lab = np.array(p.cluster_dbscan(eps=dbs["eps_default"] / 100.0,
                                        min_points=dbs["mp_default"]))
        gap[far[lab >= 0]] = True
    return pts, ~gap


def stats(dist, lod, sel):
    """The three columns of Table 5.9 plus the median signed distance."""
    d, l = dist[sel], lod[sel]
    paired = ~np.isnan(d)
    n = int(sel.sum())
    if n == 0 or paired.sum() == 0:
        return {"n_corepoints": n, "unpaired_pct": None, "median_abs_cm": None,
                "median_signed_cm": None, "beyond_lod95_pct": None}
    dp = d[paired]
    has_lod = paired & ~np.isnan(l)
    beyond = (np.abs(d[has_lod]) > l[has_lod]).mean() * 100 if has_lod.sum() else None
    return {
        "n_corepoints": n,
        "unpaired_pct": round(100.0 * (~paired).sum() / n, 1),
        "median_abs_cm": round(float(np.median(np.abs(dp))) * 100, 2),
        "median_signed_cm": round(float(np.median(dp)) * 100, 2),
        "beyond_lod95_pct": round(float(beyond), 1) if beyond is not None else None,
    }


def main() -> None:
    rows = []
    for page_id, cfg in MERGED_OBJECTS.items():
        ref = o3d.io.read_point_cloud(str(ROOT / cfg["ref"]))
        dbs = {**DEFAULT_DBSCAN_SLIDERS, **cfg.get("dbscan", {})}
        honest = cfg["checkbox_checked"]
        cap = cfg["captures"][0]
        for method_id in METHOD_ORDER:
            if method_id not in cap["methods"]:
                continue
            npz = ROOT / "outputs" / "metrics" / f"{page_id}_m3c2_final" / f"{method_id}.distances.npz"
            if not npz.exists():
                print(f"  ! missing {npz.relative_to(ROOT)}")
                continue
            z = np.load(npz)
            cp, dist, lod = z["corepoints"], z["distances"], z["lodetection"]

            pts, keep = kept_flags(cap["methods"][method_id][1], ref, dbs, honest)
            _, nn = cKDTree(pts).query(cp, k=1, workers=-1)
            cp_keep = keep[nn]

            published = stats(dist, lod, np.ones(len(cp), dtype=bool))
            masked = stats(dist, lod, cp_keep)
            rows.append({
                "object": page_id, "method": method_id,
                "thesis_applies_exclusion": not honest,
                "corepoints_excluded_pct": round(100.0 * (~cp_keep).sum() / len(cp), 1),
                "published": published, "masked": masked,
            })
            print(f"[{page_id}/{method_id}] excluded {rows[-1]['corepoints_excluded_pct']:>5}% "
                  f"| unpaired {published['unpaired_pct']} -> {masked['unpaired_pct']} "
                  f"| beyond LoD95 {published['beyond_lod95_pct']} -> {masked['beyond_lod95_pct']}",
                  flush=True)

    OUT.write_text(json.dumps({
        "what": "R2: M3C2 over the core points the §4.5 accuracy mask keeps",
        "note": ("No M3C2 recomputed; the stored per-core-point distances are "
                 "re-aggregated over the kept subset. Core points inherit the flag "
                 "of their nearest density-matched point."),
        "rows": rows,
    }, indent=1))
    print(f"\nwrote {OUT.relative_to(ROOT)}  ({len(rows)} rows)")


if __name__ == "__main__":
    main()
