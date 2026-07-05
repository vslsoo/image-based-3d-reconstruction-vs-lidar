# Experiment log

## bollard_001 (exp_001-exp_008: COLMAP, MASt3R+SfM, hloc+COLMAP)

Date: 2026-07-05
Object: bollard_001
Methods: COLMAP (SIFT), MASt3R+SfM, SuperPoint+LightGlue+COLMAP (hloc)
Images: data/raw/bollard_001/images/jpg (39 total)
LiDAR reference: no (not yet collected)

### Input data checks

- Number of images: 39
- Image resolution: 3024x4032
- Are images sharp?: yes, no notable blur issues
- Is the full object visible?: yes
- Is there enough overlap?: yes for most of the object - increasing from 15 to
  all 39 images only marginally improved reconstruction completeness (see
  exp_003 vs exp_005/006/007/008), so overlap/image count is not the limiting
  factor
- Are there strong reflections / moving objects / occlusions?: **yes** - the
  bollard's surface is highly reflective. This turned out to be the actual
  cause of incomplete reconstructions, not insufficient overlap.

### Reconstruction output

- Sparse reconstruction: see config/experiments.yaml (exp_001, 002, 003, 005,
  006, 007, 008) for per-run point counts/reprojection error
- Dense reconstruction: exp_005 (COLMAP MVS, 696,713 points), exp_008 (hloc+
  COLMAP MVS, 132,520 points); exp_006/007 (MASt3R+SfM) are semi-dense, no MVS
- Output point cloud: see each exp_XXX output_dir in config/experiments.yaml
- Main issues: COLMAP (SIFT) and hloc (SuperPoint+LightGlue) both reconstruct
  the bollard incompletely / poorly in the same region. MASt3R+SfM reconstructs
  the same region far better.

### Notes

**Key finding**: the object's high reflectivity breaks the core assumption
that local feature-matching methods (SIFT, SuperPoint) rely on - that the
same 3D point looks the same from different viewpoints. Specular highlights
shift and distort with viewing angle, so both classical (SIFT/COLMAP) and
learned-but-local (SuperPoint+LightGlue/hloc) descriptor matching produce
weak or wrong matches on the reflective surface, leaving that part of the
object poorly reconstructed regardless of image count or overlap. MASt3R
doesn't share this weakness because it regresses dense 3D correspondences
directly (end-to-end) rather than matching invariant local descriptors, so
it's far more robust to view-dependent appearance changes. This is a known
failure mode for feature-based SfM on reflective/specular objects, not
specific to this capture.

Practical implication: for reflective objects, prefer MASt3R-based
reconstruction over COLMAP(SIFT)/hloc(SuperPoint+LightGlue); the latter two
are not reliable baselines for this object class.

### Next steps

- Test video-based capture (up to ~30s per object) with automatic keyframe
  selection (blur filtering + even temporal sampling), instead of requiring
  ~40 individual photos per object - motivated by the diploma's practical
  use case (limited time on-site) rather than by the reflectivity finding.
- Once LiDAR reference data is available, register photogrammetry point
  clouds against it (src/registration/register_point_clouds.py) to get a
  ground-truth accuracy comparison across methods.