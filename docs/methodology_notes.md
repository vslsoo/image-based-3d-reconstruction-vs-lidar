# Methodology notes

Lessons below are consolidated from experiments on objects other than
bench_001 (bollard_001, bollard_001_video, chair_001, chair_001_video2,
bus_stop_001, bollard_002, flashlight_001/002, information_sign_001,
traffic_sign_001) before their raw captures and outputs were deleted to save
space. bench_001 is the only object whose experiment data (raw captures,
outputs/experiments/exp_023-026, crops, registrations, metrics) is still
kept in full.

## Reflective surfaces break local-feature matching (bollard_001, exp_001-008)

The bollard's surface is highly reflective. COLMAP (SIFT) and hloc
(SuperPoint+LightGlue) both reconstructed the same region of it incompletely
regardless of image count/overlap (going from 15 to all 39 images only
marginally helped). MASt3R (both mast3r_sfm and mast3r_ga) reconstructed the
same region far better.

Why: local-feature matching (SIFT, SuperPoint+LightGlue) assumes the same 3D
point looks the same from different viewpoints. Specular highlights shift
and distort with viewing angle, producing weak/wrong matches on reflective
surfaces. MASt3R regresses dense 3D correspondences directly (end-to-end)
rather than matching invariant local descriptors, so it's far more robust to
view-dependent appearance changes.

Practical implication: for reflective objects, prefer MASt3R-based
reconstruction over COLMAP(SIFT)/hloc(SuperPoint+LightGlue) - they are not
reliable baselines for this object class.

## Method speed/density comparison on a shared 53-image set (bollard_001_video, exp_009-014)

Same image set run through all methods, for a direct comparison:

- COLMAP (SIFT): ~45-50min, 955k-1.16M dense points
- MASt3R+SfM (incremental COLMAP bundle adjustment on MASt3R matches):
  ~2h33m, 395k points - by far the slowest, despite swin-8 windowed pairing
  (vs. an earlier "complete" scenegraph attempt that was worse still)
- MASt3R-GA (joint global alignment, no COLMAP): ~6min, 2.4M points - avoids
  both COLMAP's dense MVS runtime and mast3r_sfm's incremental-bundle-
  adjustment bottleneck entirely
- hloc+COLMAP (SuperPoint+LightGlue sparse, COLMAP dense MVS): ~46min, 1.32M
  points - sparse stage finds far fewer points than SIFT (SuperPoint
  keypoints are sparser), but dense MVS reuses COLMAP's own MVS stage on the
  registered poses regardless, giving a comparable dense count to plain
  COLMAP
- VGGT (single feed-forward pass, no optimization/COLMAP at all): well under
  1 minute, 10.7M points - by far the fastest AND densest, since its
  point_head predicts a dense per-pixel world-space point map directly in
  one transformer pass

## COLMAP (SIFT) registration failures on small image subsets (exp_031-050 batch)

Across bollard_002/flashlight_001/flashlight_002/information_sign_001/
traffic_sign_001 (each run as: plain COLMAP on a 15-image subset, hloc+COLMAP
on a 50-image subset, MASt3R-GA and VGGT on the same 15-image subset), plain
COLMAP with only 15 images repeatedly failed to register most images on
thin/geometrically-simple or texture-poor objects:

- flashlight_001: 4/15 registered (65 sparse points)
- flashlight_002: 4/15 registered (115 sparse points)
- traffic_sign_001: 8/15 registered (652 sparse points)
- bollard_002/information_sign_001: 15/15 registered (these two held up fine)

hloc+COLMAP (50 images) and MASt3R-GA/VGGT (same 15 images) registered all
images in every one of these cases. Takeaway: COLMAP(SIFT)'s reliability
degrades sharply with fewer images on thin or texture-poor objects in a way
the other three methods don't share - don't trust a small COLMAP-only image
subset as a fair baseline for such objects; either give it more images (like
hloc's 50) or compare against MASt3R-GA/VGGT instead.

Registration also wasn't always complete on richer-feature methods: hloc+
COLMAP registered only 40/61 images for chair_001_video2, and plain COLMAP
registered only 33/64 for bus_stop_001 - sparse or awkward-overlap captures
can still hurt classical matching even outside the "few images" case above.

## VGGT vs MASt3R-GA point density (chair_001, exp_015 vs exp_016)

Same 52-image set: VGGT produced ~4.8x more points than MASt3R-GA
(10.46M vs 2.18M) - consistent with the density gap seen in the exp_009-014
comparison above; VGGT's per-pixel dense prediction generally yields far
denser output than MASt3R-GA's optimization-based point cloud.

## LiDAR processing pitfalls

These recurred across bollard_002/flashlight_001/flashlight_002/
information_sign_001/traffic_sign_001 while preparing LiDAR reference crops
(cropped from the Sensat-Euston-Track2/3 street scan, same source as
bench_001's LiDAR reference):

1. **CloudCompare's interactive polygon-crop can silently lose points.** An
   interactively-cropped .laz made from a big street crop lost ~27% of its
   points versus cropping the same bbox directly from the original file -
   almost certainly viewport LOD thinning during the interactive crop.
   Always re-crop the final bbox directly from the original file with pdal
   rather than trusting an interactively-exported subset.
2. **PLY silently truncates large absolute coordinates to whole meters.**
   The source data's X/Y are ~291000/287000-scale UTM-like values. Both
   pdal's writers.ply and Open3D's write_point_cloud store x/y/z as 32-bit
   float; at that magnitude the round-trip collapsed every point onto an
   exact 1.0m grid (confirmed by dumping the .ply back out and measuring
   nearest-neighbor XY distance = exactly 1.000 with zero variance) - easy
   to misdiagnose as "the source is only sampled on a 1m grid here" (a false
   path this project went down once). Fix: always recenter LiDAR points to
   a small local origin (subtract the crop's own bbox min corner) BEFORE
   writing/reading any .ply for Open3D-based scripts - never feed UTM-scale
   absolute coordinates through a .ply round-trip. If a LiDAR crop looks
   like sparse disconnected vertical lines/dots in CloudCompare after any
   Open3D processing, suspect this truncation bug first.
3. **RANSAC largest-plane floor removal can pick the object itself instead
   of the floor**, on objects that are themselves largely flat (e.g.
   information_sign_001's sign face - the "removed" plane's normal came out
   near-vertical instead of horizontal). A direct Z-histogram cutoff (find
   the dominant low-elevation density peak) avoided this failure mode.
   `remove_ground_plane.py`'s default RANSAC mode has no notion of "floor"
   specifically - it removes the single largest flat surface, whatever it
   is - so always check the saved `removed_plane.ply` to confirm what
   actually got removed before trusting the result on largely-flat objects.
4. **DBSCAN largest-cluster filtering can visibly thin/chop thin
   structures.** An initial `--keep-largest-cluster` pass dropped up to 29%
   of points on some of these objects (worst case: flashlight_001's curved
   lamp-post arm was visibly chopped in CloudCompare). Not applied to any of
   the saved `_no_floor.ply` files in this batch - prefer no clustering, or
   a gentler cutoff, for thin/complex-topology objects.

## Known-size scale reference (from exp_034 onward)

Starting with **exp_034** (`vggt`, `bollard_002`) and in every reconstruction
from that point on, the captured scene includes a physical reference object
of known size: a **9.5cm x 9.5cm square**. These are the results being used
going forward for the diploma (earlier experiments, exp_001-033, don't have
this marker in-frame).

Why this matters: COLMAP and hloc+COLMAP (classical/local-feature SfM)
recover geometry only up to an unknown scale - `register_point_clouds.py`
currently estimates that scale by fitting a similarity transform against the
LiDAR reference (see its docstring and `extract_scale()`/the
`--scale-sanity-factor` fallback check), which is itself an imperfect,
data-dependent estimate. MASt3R-GA's checkpoint
(`MASt3R_ViTLarge_BaseDecoder_512_catmlpdpt_metric.pth`) and VGGT both claim
to predict *metric* scale natively, without any LiDAR involved.

Having a physical object of known size in-frame gives an independent way to
check/derive scale that doesn't depend on LiDAR registration at all:

1. **Cross-check the LiDAR-ICP scale estimate.** Measure the marker's size
   in a reconstruction's raw point cloud (e.g. by picking its two opposite
   corners in CloudCompare/Open3D and reading off the distance), compute
   `scale_factor = 0.095 / measured_size`, and compare that to whatever
   scale `register_point_clouds.py` fitted for the same reconstruction. If
   they disagree noticeably, that's a flag the LiDAR-based registration for
   that experiment may have converged on a wrong scale (fitness alone
   doesn't always catch this - see the file's own comments on why the
   sanity-factor check exists).
2. **Standalone per-method metric-accuracy measure, independent of LiDAR.**
   Since COLMAP/hloc are arbitrary-scale by construction while MASt3R-GA/
   VGGT claim metric output natively, measuring the marker directly in each
   method's *raw, unregistered* point cloud (before any LiDAR alignment) and
   comparing to the true 9.5cm answers "how metrically accurate is this
   method's own native scale claim?" - a comparison axis the LiDAR
   registration pipeline can't isolate on its own, since it always forces
   photogrammetry clouds to LiDAR scale regardless of whether the method's
   own scale claim was any good to begin with.
