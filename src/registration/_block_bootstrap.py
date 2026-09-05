"""Spatial block bootstrap - the one copy.

Neighbouring points of a density-matched cloud are not independent: a patch that the
reconstruction got wrong is wrong over several centimetres, not at one point. Resampling
points would therefore treat one mistake as hundreds of independent observations and give an
interval several times too narrow. So the resampling unit is a spatial block (a `block_m`
voxel), and what is resampled are per-block sums.

This was written twice, byte-identically, in build_capture_comparison_page.py and
build_frame_count_study_page.py before build_accuracy_f1_summary_table.py needed it a third
time; all three import it from here now, so the main results table and the two ablations
cannot drift apart in how they compute an interval.

The draws are chunked (see DRAW_CHUNK_CELLS): the fancy-index resample of B x n_blocks is a
dense array, and the main table's largest cloud (bus_stop/vggt, 2.4M points) has enough
blocks to make 2000 draws at once a multi-gigabyte allocation.
"""

from __future__ import annotations

import numpy as np

# Draws are generated in chunks of about this many (draw x block) cells at a time. 20M cells
# is ~160 MB per array, which is comfortable and still large enough that the per-chunk
# overhead is irrelevant.
DRAW_CHUNK_CELLS = 20_000_000


def block_parts(points_m: np.ndarray, indicator: np.ndarray, block_m: float):
    """Per spatial block (a `block_m`-sized voxel): how many points fall in it and how
    many of those satisfy `indicator` (e.g. distance <= 3cm). These per-block sums are
    what the bootstrap resamples, so within-block correlation is preserved."""
    if len(points_m) == 0:
        return np.array([]), np.array([]), 0
    q = np.floor(points_m / block_m).astype(np.int64)
    _, inv = np.unique(q, axis=0, return_inverse=True)
    nb = int(inv.max()) + 1
    within = np.bincount(inv, weights=indicator.astype(float), minlength=nb)
    total = np.bincount(inv, minlength=nb).astype(float)
    return within, total, nb


def _resample_ratio(within: np.ndarray, total: np.ndarray, nb: int, B: int, rng) -> np.ndarray:
    """B bootstrap draws of sum(within)/sum(total) over blocks resampled with replacement."""
    out = np.empty(B, dtype=float)
    chunk = max(1, min(B, DRAW_CHUNK_CELLS // max(nb, 1)))
    done = 0
    while done < B:
        n = min(chunk, B - done)
        idx = rng.integers(0, nb, size=(n, nb))
        out[done:done + n] = within[idx].sum(1) / total[idx].sum(1)
        done += n
    return out


def bootstrap_draws(acc_pts, acc_ind, comp_pts, comp_ind, block_m, B, rng):
    """B block-bootstrap draws each of Accuracy, Completeness and F1 (%), at whatever
    threshold the two indicators were built with.

    Accuracy blocks (kept source points) and completeness blocks (target points) are
    resampled independently each iteration - they are different point sets over the same
    object, and a source block has no counterpart among the target blocks to pair with.

    Returns (acc_draws, comp_draws, f1_draws, n_blocks_acc, n_blocks_comp); the three draw
    arrays are None when either side has no points at all.
    """
    aw, at, anb = block_parts(acc_pts, acc_ind, block_m)
    cw, ct, cnb = block_parts(comp_pts, comp_ind, block_m)
    if anb == 0 or cnb == 0:
        return None, None, None, anb, cnb
    acc_b = _resample_ratio(aw, at, anb, B, rng)
    comp_b = _resample_ratio(cw, ct, cnb, B, rng)
    denom = acc_b + comp_b
    f1_b = np.where(denom > 0, 2 * acc_b * comp_b / denom, 0.0) * 100.0
    return acc_b * 100.0, comp_b * 100.0, f1_b, anb, cnb


def bootstrap_f1_draws(acc_pts, acc_ind, comp_pts, comp_ind, block_m, B, rng):
    """bootstrap_draws() for callers that only want F1: (f1_draws, n_blocks_acc, n_blocks_comp)."""
    _, _, f1_b, anb, cnb = bootstrap_draws(acc_pts, acc_ind, comp_pts, comp_ind, block_m, B, rng)
    return f1_b, anb, cnb


def ci95(draws) -> tuple[float, float]:
    """The 2.5/97.5 percentiles of a draw array, or (nan, nan) when there are none."""
    if draws is None:
        return float("nan"), float("nan")
    lo, hi = np.percentile(draws, [2.5, 97.5])
    return float(lo), float(hi)


def diff_ci95(draws_a, draws_b) -> tuple[float, float, bool]:
    """95% CI of the difference a - b, and whether it includes 0.

    This is the test for "is A better than B", not the overlap of their two individual
    intervals - that eyeball test is far too conservative and rejects real differences.
    Both sides are resampled independently here, which is right when the two clouds share no
    input frames (two methods on the same object, two capture routes around it). Where the
    designs are nested the draws can be paired instead, which is a stronger test - see
    build_frame_count_study_page.py.
    """
    d = np.asarray(draws_a) - np.asarray(draws_b)
    lo, hi = (float(x) for x in np.percentile(d, [2.5, 97.5]))
    return lo, hi, bool(lo <= 0.0 <= hi)
