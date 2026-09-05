# Image-Based 3D Reconstruction vs LiDAR

The project evaluates whether image-based 3D reconstruction methods can reproduce LiDAR-derived object geometry for urban street-level assets.

## Methods

- COLMAP
- hloc (SuperPoint + LightGlue) + COLMAP
- MASt3R with global alignment
- VGGT

## Data

Raw data and large outputs are not stored in this repository.

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

COLMAP is used through the `pycolmap-cuda12` wheel rather than the command-line build. The
reported results were produced with COLMAP 4.1.1 and Ceres 2.2.0, as returned by
`pycolmap.COLMAP_version`.

## Structure

- `src/` — source code
- `notebooks/` — exploratory notebooks
- `scripts/` — command-line scripts
- `config/` — configuration files
- `docs/` — notes and experiment logs
- `docs/tables/` — finalized summary tables (xlsx). `outputs/` is gitignored and
  regenerable, so once a summary table (e.g. `outputs/metrics/*_summary_table.xlsx`)
  is ready to keep as a result, copy it here so it's tracked in git.
