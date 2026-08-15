# Image-Based 3D Reconstruction vs LiDAR

The project evaluates whether image-based 3D reconstruction methods can reproduce LiDAR-derived object geometry for urban street-level assets.

## Methods

- COLMAP
- SuperPoint/SuperGlue + COLMAP
- MASt3R
- VGGT

## Data

Raw data and large outputs are not stored in this repository.

## Structure

- `src/` — source code
- `notebooks/` — exploratory notebooks
- `scripts/` — command-line scripts
- `config/` — configuration files
- `docs/` — notes and experiment logs
- `docs/tables/` — finalized summary tables (xlsx). `outputs/` is gitignored and
  regenerable, so once a summary table (e.g. `outputs/metrics/*_summary_table.xlsx`)
  is ready to keep as a result, copy it here so it's tracked in git.
