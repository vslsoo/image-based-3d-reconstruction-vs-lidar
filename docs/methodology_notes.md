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

## Ground Sampling Distance (GSD) for bollard_002 (`compute_gsd.py`)

GSD (real-world size represented by one image pixel) is a property of the
*capture* - camera + distance to the subject - not of the reconstruction
method, so it only needs to be computed once per object, from whichever
experiment has calibrated camera poses/intrinsics saved. All 4 bollard_002
experiments (exp_027 vggt, exp_029 mast3r_ga, exp_030 colmap, exp_032
hloc_colmap) share the same 50 source frames, so a COLMAP-family GSD answers
the question for the whole object.

Method (`src/registration/compute_gsd.py`): for each registered image,
average the distance from its camera center to every sparse 3D point it
observes (COLMAP's raw SfM units), convert to meters using the scale
`register_point_clouds.py` already fit against the LiDAR reference
(`report.json`'s `estimated_scale`, times `manual_extra_scale_correction` if
present), then divide by the camera's calibrated focal length in pixels
(already in true pixel units - no scale conversion needed). Only works for
COLMAP-family experiments that persist `cameras.bin`/`images.bin` - VGGT and
MASt3R-GA here only saved the output `.ply`, no poses/intrinsics, so GSD
can't be computed this way for them directly.

Results:
- exp_030 (colmap): f=1654.3px, mean camera-object distance 1.836m ->
  **GSD ~1.11mm/px** (median 1.08mm/px).
  `outputs/metrics/reg_030_to_lidar_bollard_002/gsd.json`
- exp_032 (hloc_colmap): f=1651.0px, mean camera-object distance 2.048m ->
  **GSD ~1.24mm/px** (median 1.19mm/px).
  `outputs/metrics/reg_032_to_lidar_bollard_002/gsd.json`

The two independently-calibrated focal lengths (1654.3px vs 1651.0px, same
physical camera) and resulting GSDs agree within ~12%, a reasonable mutual
sanity check. Cross-checked with a third, LiDAR-independent method: manually
measuring the in-scene 9.5cm reference marker's pixel size on one frame
(`outputs/experiments/exp_030_colmap_bollard_002/images/frame_0000.jpg`)
gave ~0.9mm/px - same order of magnitude, though lower precision since the
marker is seen at a steep oblique angle and partly in shadow.

## Motion blur characterization for bollard_002 (`compute_motion_blur.py`)

Same "property of the capture, not the method" logic as GSD above - a
single number per object, from the raw frames, applies to all 4 methods
since they share the same source video. Unlike GSD, this needs no
reconstruction/registration data at all, just the images themselves.

Method (`src/data_preparation/compute_motion_blur.py`): Laplacian variance
per image (the same no-reference sharpness score `extract_video_frames.py`
already uses internally to discard blurry frames when picking candidates
from raw video - lower variance = less high-frequency edge content = more
blur), reported as summary stats over an image set. It's a *relative*
indicator (also responds to scene texture/contrast), not a physical blur
radius in pixels - only meaningful compared across frames/objects scored
the same way (same `--max-size`, similar content).

Results for bollard_002 (frames resized to max side 1600px before scoring):
- The 50-frame subset actually used in exp_027/029/030/032:
  mean **553.2**, median 447.1, std 315.7, range 138.2-1455.6.
  `outputs/metrics/bollard_002_motion_blur_selected50.csv`
- Full 97-frame candidate pool (`data/video/bollard_002/images/jpg`, already
  sharpest-per-window filtered by `extract_video_frames.py`): mean 544.0,
  median 430.4, std 312.7, range 115.2-1596.9.
  `outputs/metrics/bollard_002_motion_blur_full_pool97.csv`

The selected 50 and the full 97-frame pool land on nearly the same
distribution, confirming the "even" subset selection didn't bias toward
sharper or blurrier frames. The relatively wide spread (std ~57% of the
mean) reflects real variation in the handheld orbit capture - some frames
(e.g. `frame_0051.jpg`, `frame_0053.jpg`) are visibly more motion-blurred
than others (e.g. `frame_0000.jpg`, `frame_0084.jpg`), worth checking
against those frames' registration/reprojection-error behavior if a given
method struggled with specific viewpoints.

**Caveat, found by comparing across objects (not just within one video):**
this metric conflates real motion blur with scene texture, and isn't a
reliable cross-video ranking. Ran it on all 5 objects with raw frames still
local:

| object | mean | median | std |
|---|---|---|---|
| bench_001 | 452.1 | 475.9 | 124.6 |
| bollard_002 | 544.0 | 430.4 | 312.7 |
| flashlight_001 | 370.9 | 347.8 | 197.2 |
| information_sign_001 | 737.1 | 758.3 | 161.8 |
| traffic_sign_001 | 414.4 | 356.9 | 224.7 |

(full pool per-image scores: `outputs/metrics/<object>_motion_blur_full_pool*.csv`)

information_sign_001 scores *highest* of all five, despite being the object
with the documented worst capture problems (`exp_033_failed`/`exp_034_failed`:
camera moved too fast, too little frame-to-frame overlap, pedestrian
ghosting). Two reasons: (1) `extract_video_frames.py` already keeps only the
sharpest frame per time window before this metric ever runs, so cross-video
comparison is scoring "best-of-window" pools, not raw footage; (2) printed
sign text is inherently high-frequency/high-contrast content, inflating the
Laplacian variance regardless of capture quality. The actual problem with
information_sign_001/traffic_sign_001 was inter-frame *coverage* (spatial
gaps from fast panning), which `compute_image_overlap.py` catches and this
metric does not. Conclusion: use this metric only for within-one-video
relative ranking or same-object before/after checks - not for cross-object
"which capture is worse" comparisons.

## GSD for information_sign_001 (marker-only estimate)

Unlike bollard_002, no COLMAP-intrinsics+LiDAR-scale GSD could be computed
for information_sign_001 yet: exp_039 (colmap, 100 images)'s `sparse/`
model initially existed only on the remote GPU pod (only the merged dense
`.ply` had been synced locally - see [[workflow_pod_split]]), and even
after pulling `sparse/0/` down, there is no LiDAR registration for exp_039
yet (`crop_point_cloud.py` is an interactive Open3D tool, can't be run
non-interactively). The one existing registration for this object
(`reg_036_to_lidar_information_sign_001`, vggt) is a rough manual
placement only (`icp_registration: null`, suspicious `estimated_scale: 5.0`)
- not trustworthy as a scale source.

Fallback: same marker-pixel-area method as bollard_002's cross-check,
standalone (`outputs/metrics/information_sign_001_gsd_marker.json`). Found
the 9.5cm marker at the base of the sign post in
`data/video/information_sign_001/images/jpg/frame_0000.jpg`, viewed closer
to fronto-parallel than bollard_002's (less oblique skew). Picked its 4
corners by hand on a 6x-upscaled crop, iteratively checked by overlaying
the polygon back on the image, and computed GSD from the marker's known
9.5x9.5cm area vs. its pixel-space area (shoelace formula):

    marker pixel area: 2123 px^2
    GSD = sqrt(0.095^2 / 2123) ~= 2.06 mm/px

About 2x bollard_002's ~1.1mm/px, consistent with the sign being shot from
further back than the low bollard. Same precision caveat as bollard_002's
marker cross-check (manual corner-picking, not calibrated - expect ~15-20%
uncertainty). If exp_039 gets a proper LiDAR registration later, redo this
with `compute_gsd.py` for a more precise, cross-checked number - note that
information_sign_001's background (buildings, vans, pedestrians) means the
sparse-point depth averaging would first need to be restricted to
object-only points (unlike bollard_002, where the object filled the frame),
to avoid background points inflating the estimated camera-object distance.

## GSD for bus_stop_001 (known real-world edge, no marker/pod needed)

bus_stop_001 (48 individually-shot photos, not a walk-around video - see
[[objects.yaml]]) has no in-scene calibration marker (checked 3 frames,
none found - unlike bollard_002/information_sign_001). Its COLMAP-family
experiments (exp_058 colmap, exp_059 hloc_colmap) do have solid LiDAR
registrations already (`reg_058_to_lidar_bus_stop_001`,
`reg_059_to_lidar_bus_stop_001`: ICP fitness ~0.81-0.82, inlier RMSE
~0.0054 - notably better than information_sign_001's rough one), but their
`sparse/` models exist only on the remote GPU pod, which was unreachable
(`connection refused`) when this was computed. Recomputing sparse locally
(`colmap`/`pycolmap` are installed locally, no GPU needed for the sparse
stage) would give an accurate focal length - focal length is independent of
COLMAP's arbitrary per-run coordinate gauge - but NOT a usable
camera-object distance, since that requires a scale tied to that specific
run's gauge, which would mean re-registering to LiDAR, which needs
`crop_point_cloud.py`'s interactive Open3D step.

Instead: used the LiDAR reference point cloud directly (already true
metric) as the source of a known real-world length, the same role the
9.5cm marker plays elsewhere. Picked two points in CloudCompare on the
back/left wall's roofline-to-ground edge (2.470183m raw distance; 2.5m
used as the reference value) - see
`outputs/metrics/bus_stop_001_gsd_reference_edge.json`. That same edge is
close to vertical (minimal foreshortening) in `IMG_7147.jpg`, running
almost straight down alongside the support pole - measured its pixel
extent directly (top=(760,545), bottom=(760,3195) in the full 3024x4032
image), verified by drawing the measured segment back onto the photo and
confirming it lands exactly on that edge:

    pixel height: 2650 px
    GSD = 2.5 / 2650 ~= 0.943 mm/px

About 0.85-0.9x bollard_002's ~1.1mm/px - consistent with these photos
being shot close enough to fit the whole ~2.5m-tall shelter in frame.
Since this is a single near-vertical edge (not an oblique 4-corner area
like the marker method), foreshortening ambiguity is lower than the
bollard_002/information_sign_001 marker estimates, but it's still a manual
pixel-pick with no independent cross-check.

## Reference-density cleanup and cross-method summary table (bus_stop_001, exp_055/056/058/059)

`bus_stop_001_no_floor_centered.ply` (83290 pts) turned out to have 38319
points (46%) at exact-duplicate coordinates (zero nearest-neighbor
distance) - overlapping LiDAR scan passes, not noise to filter case-by-case
but a systematic artifact worth fixing once for the whole reference. Took
`np.unique` on the raw points (83290 -> 58933 unique), which alone didn't
change the nearest-neighbor spacing distribution's shape - the remaining
non-uniformity (median NN spacing 1.00cm, but a long tail out to 37.9cm) is
real scan-geometry variation (closer/more perpendicular surfaces got denser
coverage), not near-duplicate clutter, confirmed by voxel-downsampling the
deduped cloud at the median spacing (1.00cm) and getting 58933 -> 58933
points back (no-op).

Consulted the actual DTU and Tanks-and-Temples eval code (not just the
paper text) on how reference density should be handled:
- DTU (`downsample_to_reference_density.py`'s existing rationale) only
  density-matches the reconstruction (source) to the reference, never
  touches the reference itself.
- T&T's `evaluation.py` (github.com/isl-org/TanksAndTemples) actually
  voxel-downsamples *both* clouds to the same `voxel_size = dTau/2` before
  computing precision/recall, where `dTau` is a hand-picked per-scene
  constant (0.003m-0.025m in their `config.py`, scaled to object size) -
  and separately, T&T's published ground-truth clouds are themselves
  voxel-downsampled once at dataset-construction time specifically to
  normalize density in scan-overlap regions, independent of whatever
  reconstruction is being scored against them.

Given bus_stop_001's overlap-duplicate issue is exactly the failure mode
T&T's GT-construction step targets, deduped + saved a canonical downsampled
reference once (median-NN voxel = 1.00cm, matches the project's own
`median_nearest_neighbor_spacing()` convention) for reuse across all
methods, rather than per-method downsampling:
`data/lidar/bus_stop_001/bus_stop_001_no_floor_centered_downsampled.ply`
(58933 pts - unchanged from dedup, since the voxel is a no-op at native
resolution; the fix was the dedup, not the voxelization).

Then ran `downsample_to_reference_density.py` (voxel = reference's median
NN spacing, 1.00cm) on all 4 registered image-based reconstructions against
that cleaned reference, output in `outputs/density_matched/bus_stop_001/`:
mast3r_ga (exp_055) 352450->247630, vggt (exp_056) 3608344->1640253, colmap
(exp_058) 389309->132319, hloc_colmap (exp_059) 401967->139014 pts. Even
after matching voxel size, vggt stays 6-12x denser than the others in
point count - real geometric coverage difference, not just a density
artifact, per the no-op check above.

Summary table (`outputs/metrics/bus_stop_001_summary_table.xlsx`) computed
from these density-matched clouds against the cleaned reference:
- accuracy/completeness: mean/median/RMSE of unthresholded
  `compute_point_cloud_distance` in both directions (no clamping).
- F1 threshold: 2cm, following the T&T `dTau` logic above (this object's
  scale + 1cm native spacing -> dTau=2cm, voxel=dTau/2=1cm already used).
- point density uniformity score: coefficient of variation (std/mean) of
  each cloud's own NN-distance distribution - lower = more uniform.
  mast3r_ga/vggt ~0.40 vs colmap/hloc_colmap ~0.77-0.84, i.e. the
  MASt3R-GA/VGGT clouds are considerably more uniformly sampled than the
  COLMAP-family dense-MVS outputs.
- M3C2 (`py4dgeo.M3C2`, normal_radii=[0.03m], cyl_radius=0.02m, corepoints
  = the cleaned reference): only 39429-57183 of 58933 core points got a
  valid distance per method (COLMAP-family worst, ~2/3 valid) - the
  remainder had no source point within the search cylinder, i.e. real
  coverage gaps rather than a parameter/tuning artifact.
- runtime/peak memory/estimated cost: left blank - nothing in the repo
  (`config/experiments.yaml`, `outputs/`) logs these. The only residual
  signal is local sync-file mtimes (pod runs finish -> immediate rsync,
  per the project's sequential-pod-run workflow), which give rough
  inter-experiment deltas (mast3r_ga ~14min, vggt ~1.6min, colmap ~2h32min,
  hloc_colmap ~48min) - not used in the table since they can't be
  disentangled from sync/idle overhead, but noted here in case a more
  precise source turns up later.
