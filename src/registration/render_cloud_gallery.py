"""Appendix C figures: every final reconstruction over its lidar reference.

One figure per object, one panel per method. The reconstruction is the
registered cloud that the final metrics were computed on (the `source` of
outputs/metrics/<object>_m3c2_final/<method>.json), the reference its
`target`. The reconstruction is prepared exactly as in build_accuracy_f1_summary_table.py
(1 cm voxel downsample; reference deduplicated) and the 4.5 reference-gap
exclusion is recomputed with the object's own DBSCAN setting, so the three
colours of the reconstruction are the three classes the metrics see: within
3 cm of the reference (teal), farther but kept as an error (orange), and set
aside as a reference gap (violet). Accuracy is teal / (teal + orange). The
reference itself is not drawn. The values under each panel are Table 5.1's;
the script checks its own recomputation against them and stops on a mismatch.

The view is an oblique orthographic projection: the reference's principal
horizontal axis is turned AZIMUTH degrees towards the viewer and the view is
tilted ELEVATION degrees down. Points are drawn far-to-near.

    python src/registration/render_cloud_gallery.py [object ...]
"""
import json, os, sys
import numpy as np
from scipy.spatial import cKDTree
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(ROOT, "docs", "figures")
THR = 0.03
AZIMUTH, ELEVATION = 35.0, 20.0
MAX_FIG_H = 8.9        # inches; the page allows 9.7 before the caption
MAX_PTS = 150_000
SEED = 123

# thesis order and names; metrics key = page key in the summary json
OBJECTS = [
    ("bollard",          "Bollard",          "C.1"),
    ("flashlight",       "Lamp post",        "C.2"),
    ("information_sign", "Information sign", "C.3"),
    ("bench",            "Bench",            "C.4"),
    ("bus_stop_sign",    "Bus stop sign",    "C.5"),
    ("bus_stop",         "Bus shelter",      "C.6"),
]
METHODS = [("colmap", "COLMAP"), ("hloc_colmap", "hloc + COLMAP"),
           ("mast3r_ga", "MASt3R-GA"), ("vggt", "VGGT")]

C_REF_HIT, C_REF_MISS = "#6f6f6f", "#000000"
# Status tones taken from the results website (site/*.html): teal #1aacb3 for
# "within the threshold", orange #e16b3e for "beyond it". The third class, the
# 4.5 reference gap, has no counterpart there; #6f42c1 was picked to sit far
# from both under normal vision and under protan/deutan/tritan simulation
# (worst pairwise CIEDE2000: 43 normal, 25 simulated).
C_IN, C_OUT, C_GAP = "#1aacb3", "#e16b3e", "#6f42c1"
VOXEL_M = 0.01          # as VOXEL_M in build_accuracy_f1_summary_table.py

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_object_page import MERGED_OBJECTS, DEFAULT_DBSCAN_SLIDERS  # noqa: E402


def dedupe(p):
    _, idx = np.unique(p, axis=0, return_index=True)
    return p[np.sort(idx)]


def voxel_down(p, v):
    """Open3D VoxelDownSample: one point per occupied voxel, at the mean of its points;
    the grid is anchored at min_bound - v/2 as Open3D does."""
    origin = p.min(0) - v * 0.5
    key = np.floor((p - origin) / v).astype(np.int64)
    _, inv = np.unique(key, axis=0, return_inverse=True)
    inv = inv.ravel()
    n = inv.max() + 1
    sums = np.zeros((n, 3)); cnt = np.zeros(n)
    np.add.at(sums, inv, p); np.add.at(cnt, inv, 1)
    return sums / cnt[:, None]


def gap_mask(pts, d_cm, ft_cm, eps_cm, min_pts):
    """The 4.5 exclusion: far points (d > ft) that DBSCAN(eps, min_pts) puts in a
    cluster. Membership only - a point is in a cluster iff it is a core point or lies
    within eps of one - which is what open3d.cluster_dbscan's label >= 0 means."""
    far = np.where(d_cm > ft_cm)[0]
    out = np.zeros(len(pts), dtype=bool)
    if len(far) == 0:
        return out
    fp = pts[far]
    tree = cKDTree(fp)
    pairs = tree.query_pairs(eps_cm / 100.0, output_type="ndarray")
    deg = np.bincount(pairs.ravel(), minlength=len(fp)) if len(pairs) else np.zeros(len(fp), int)
    core = (deg + 1) >= min_pts
    member = core.copy()
    if len(pairs):
        a, b = pairs[:, 0], pairs[:, 1]
        member[a[core[b]]] = True
        member[b[core[a]]] = True
    out[far[member]] = True
    return out


def read_ply_xyz(path):
    with open(path, "rb") as f:
        hdr = []
        while True:
            line = f.readline().decode("ascii", "replace").strip()
            hdr.append(line)
            if line == "end_header":
                break
        if not any(h.startswith("format binary_little_endian") for h in hdr):
            raise RuntimeError(f"not binary_little_endian: {path}")
        n = int(next(h for h in hdr if h.startswith("element vertex")).split()[-1])
        tmap = {"double": "f8", "float": "f4", "uchar": "u1", "char": "i1",
                "ushort": "u2", "short": "i2", "uint": "u4", "int": "i4"}
        props = [h.split()[1:] for h in hdr if h.startswith("property")]
        dt = np.dtype([(nm, tmap[t]) for t, nm in props])
        a = np.frombuffer(f.read(n * dt.itemsize), dtype=dt, count=n)
    return np.column_stack([a["x"], a["y"], a["z"]]).astype(np.float64)


def subsample(p, n, rng):
    if len(p) <= n:
        return p
    return p[rng.choice(len(p), n, replace=False)]


def render(obj_key, obj_name, fig_no, metrics):
    rng = np.random.default_rng(SEED)
    mismatches = []
    cfg = MERGED_OBJECTS[obj_key]
    cap = cfg["captures"][0]
    dbs = {**DEFAULT_DBSCAN_SLIDERS, **cfg.get("dbscan", {})}
    honest = cfg["checkbox_checked"]
    ref = dedupe(read_ply_xyz(os.path.join(ROOT, cfg["ref"])))
    tree_ref = cKDTree(ref)
    panels = []
    for mkey, mname in METHODS:
        rec = voxel_down(read_ply_xyz(os.path.join(ROOT, cap["methods"][mkey][1])), VOXEL_M)
        d_rec, _ = tree_ref.query(rec, k=1, workers=-1)
        gap = np.zeros(len(rec), dtype=bool) if honest else gap_mask(rec, d_rec * 100, dbs["ft_default"], dbs["eps_default"], dbs["mp_default"])
        d_ref, _ = cKDTree(rec).query(ref, k=1, workers=-1)
        kept = ~gap
        acc = 100 * np.mean(d_rec[kept] <= THR); comp = 100 * np.mean(d_ref <= THR)
        m = metrics[mkey]
        ok = abs(acc - m["acc_3cm"]) < 0.15 and abs(comp - m["comp_3cm"]) < 0.15
        flag = "" if ok else "   <-- MISMATCH"
        if not ok:
            mismatches.append((obj_key, mkey))
        print(f"  {obj_key:16s} {mkey:12s} acc {acc:5.1f} (table {m['acc_3cm']:5.1f})  comp {comp:5.1f} (table {m['comp_3cm']:5.1f})  excluded {100*gap.mean():4.1f}%{flag}")
        panels.append((mkey, mname, rec, ref, d_rec, d_ref, gap))

    if mismatches:
        raise SystemExit(f"recomputed accuracy/completeness differ from Table 5.1 for {mismatches}; "
                         "the figure would not match the table, so nothing was written")

    ref = panels[0][3]
    # Oblique orthographic view. The horizontal principal axis of the
    # reference is turned AZIMUTH degrees towards the viewer and the view is
    # tilted ELEVATION degrees down, so a long bench or a shelter shows its
    # front and its top, and a pole still reads as a pole.
    xy = ref[:, :2] - ref[:, :2].mean(0)
    w, v = np.linalg.eigh(xy.T @ xy)
    u = v[:, np.argmax(w)]
    if u[0] < 0:
        u = -u
    n = np.array([-u[1], u[0]])                   # horizontal normal to the major axis
    az, el = np.radians(AZIMUTH), np.radians(ELEVATION)
    # view direction (from the object towards the camera), in world coordinates
    d_h = np.cos(az) * n + np.sin(az) * u
    d = np.array([d_h[0] * np.cos(el), d_h[1] * np.cos(el), np.sin(el)])
    right = np.array([-d_h[1], d_h[0], 0.0])
    right /= np.linalg.norm(right)
    up = np.cross(d, right)
    up /= np.linalg.norm(up)
    if up[2] < 0:
        up, right = -up, -right

    def proj(p):
        return p @ right, p @ up, p @ d

    hx, hz, _ = proj(ref)
    width, height = np.ptp(hx), np.ptp(hz)
    # One frame for all four panels, large enough to hold the reference and
    # every reconstruction, so that geometry a method invented outside the
    # object - a second lamp head, a flag drawn twice - is shown at the same
    # scale as the rest instead of being cut off or given a panel of its own.
    x0, x1, z0, z1 = hx.min(), hx.max(), hz.min(), hz.max()
    projected = []
    for mkey, mname, rec, ref_m, d_rec, d_ref, gap in panels:
        gx, gz, gd = proj(rec)
        projected.append((gx, gz, gd))
        x0, x1 = min(x0, gx.min()), max(x1, gx.max())
        z0, z1 = min(z0, gz.min()), max(z1, gz.max())
    pad = 0.03 * max(x1 - x0, z1 - z0)
    frame = (x0 - pad, x1 + pad, z0 - pad, z1 + pad)
    extras = []
    fw, fh = frame[1] - frame[0], frame[3] - frame[2]
    aspect = fh / max(fw, 1e-6)
    n_panels = 4

    # Layout by shape: a pole gets its panels in a row, a bench in a column,
    # anything squarish a grid.
    if aspect > 1.6:
        layout, ncol = "row", 4
    elif aspect < 0.6:
        layout, ncol = "column", 1
    else:
        layout, ncol = "grid", 2
    nrow = int(np.ceil(n_panels / ncol))
    label_h = {"row": 0.95, "column": 0.42, "grid": 0.62}[layout]

    if layout == "row":
        # One vertical scale for all four panels, and each panel only as wide
        # as its own cloud needs. A method that built geometry far to the side
        # gets a wider panel rather than forcing empty margins on the other
        # three, so every object is drawn as large as the page allows.
        z0 = min(hz.min(), *[gz.min() for gx, gz, gd in projected])
        z1 = max(hz.max(), *[gz.max() for gx, gz, gd in projected])
        zpad = 0.03 * (z1 - z0)
        z0, z1 = z0 - zpad, z1 + zpad
        frames = []
        for gx, gz, gd in projected:
            a = min(hx.min(), gx.min()); b = max(hx.max(), gx.max())
            xpad = 0.06 * (b - a)
            frames.append((a - xpad, b + xpad, z0, z1))
        widths = [f[1] - f[0] for f in frames]
        span = sum(widths)
        avail_w = 6.3 - 0.12 * (ncol - 1)
        avail_h = MAX_FIG_H - 0.8 - (label_h + 0.28)
        scale = min(avail_w / span, avail_h / (z1 - z0))
        fig_w, fig_h = 6.3, scale * (z1 - z0) + 0.8 + label_h + 0.28
        fig, axes = plt.subplots(1, 4, figsize=(fig_w, fig_h), layout="constrained",
                                 gridspec_kw={"width_ratios": widths})
    else:
        panel_w = (6.3 - 0.12 * (ncol - 1)) / ncol
        fig_h = min(MAX_FIG_H, nrow * (panel_w * aspect + label_h + 0.28) + 0.8)
        frames = [frame] * 4
        fig, axes = plt.subplots(nrow, ncol, figsize=(6.3, fig_h), layout="constrained")
    fig.get_layout_engine().set(w_pad=0.04, h_pad=0.06, wspace=0.02, hspace=0.04)
    axes = np.ravel(np.atleast_1d(axes))
    tall = layout == "row"

    # every panel: (axis, method key, name, points, distances, gap mask, frame, is_extra)
    jobs = []
    for ax, (mkey, mname, rec, ref_m, d_rec, d_ref, gap), (gx, gz, gd), fr in zip(axes, panels, projected, frames):
        jobs.append((ax, mkey, mname, gx, gz, gd, d_rec, gap, fr, False))

    for ax, mkey, mname, gx, gz, gd, d_rec, gap, fr, is_extra in jobs:
        excl = 100 * gap.mean()                  # on the full cloud, before any subsampling
        if len(gx) > MAX_PTS:
            sel = rng.choice(len(gx), MAX_PTS, replace=False)
            gx, gz, gd, d_rec, gap = gx[sel], gz[sel], gd[sel], d_rec[sel], gap[sel]
        o = np.argsort(gd)                      # painter's order: far points first
        gx, gz, d_rec, gap = gx[o], gz[o], d_rec[o], gap[o]
        s_rec = float(np.clip(90000.0 / len(gx), 0.3, 6.0))
        if is_extra:
            s_rec *= 0.6
        near = (d_rec <= THR) & ~gap
        err = (d_rec > THR) & ~gap
        ax.scatter(gx[gap], gz[gap], s=s_rec, c=C_GAP, marker=".", linewidths=0, rasterized=True)
        ax.scatter(gx[near], gz[near], s=s_rec, c=C_IN, marker=".", linewidths=0, rasterized=True)
        ax.scatter(gx[err], gz[err], s=s_rec, c=C_OUT, marker=".", linewidths=0, rasterized=True)
        m = metrics[mkey]
        if is_extra:
            ax.set_title(f"{mname},\nwhole cloud", fontsize=9, pad=3)
            ax.set_xlabel("same cloud,\nsmaller scale", fontsize=8, labelpad=3, color="#555555")
        else:
            ax.set_title(mname, fontsize=10, pad=3)
            if layout == "column":
                lab = f"Acc {m['acc_3cm']:.1f} · Comp {m['comp_3cm']:.1f} · F1 {m['f1_3cm']:.1f} · set aside {excl:.1f}%"
            elif layout == "grid":
                lab = f"Acc {m['acc_3cm']:.1f} · Comp {m['comp_3cm']:.1f} · F1 {m['f1_3cm']:.1f}\nset aside {excl:.1f}%"
            else:
                lab = f"Acc {m['acc_3cm']:.1f}\nComp {m['comp_3cm']:.1f}\nF1 {m['f1_3cm']:.1f}\nset aside {excl:.1f}%"
            ax.set_xlabel(lab, fontsize=8.5 if tall else 9, labelpad=3)
        ax.set_xlim(fr[0], fr[1])
        ax.set_ylim(fr[2], fr[3])
        ax.set_aspect("equal")
        ax.set_xticks([]); ax.set_yticks([])
        for sp in ax.spines.values():
            sp.set_linewidth(0.4); sp.set_color("#999999")

    handles = [
        Line2D([], [], marker="o", ls="", ms=4, color=C_IN, label="reconstruction within 3 cm of the reference"),
        Line2D([], [], marker="o", ls="", ms=4, color=C_OUT, label="reconstruction farther than 3 cm, counted as error"),
        Line2D([], [], marker="o", ls="", ms=4, color=C_GAP, label="reconstruction set aside as a reference gap (§4.5)"),
    ]
    fig.legend(handles=handles, loc="outside lower center", ncol=1, fontsize=8.5, frameon=False,
               handletextpad=0.4, columnspacing=1.2)
    fig.suptitle(f"{obj_name} — the four final reconstructions against the lidar reference", fontsize=10)
    base = os.path.join(OUT, f"fig_{fig_no.replace('.', '_')}_{obj_key}_clouds")
    fig.savefig(base + ".png", dpi=220)
    fig.savefig(base + ".pdf")
    plt.close(fig)
    print("wrote", base + ".png/.pdf", "| view width", round(width, 2), "height", round(height, 2))


def main(argv):
    summary = json.load(open(os.path.join(ROOT, "docs", "tables", "summary_all_objects_accuracy_f1.json")))
    want = set(argv) or {o[0] for o in OBJECTS}
    for key, name, no in OBJECTS:
        if key not in want:
            continue
        page = summary["pages"][key]["panels"]
        metrics = {k.split("__", 1)[1]: v for k, v in page.items()}
        render(key, name, no, metrics)


if __name__ == "__main__":
    main(sys.argv[1:])
