# Image Based 3D Reconstruction and Rendering

## Submission information

Group number: **TO BE FILLED BY THE GROUP**  
Group members and individual contributions: **TO BE FILLED BY THE GROUP**  
GitHub repository: https://github.com/wzw26919/assignment2-3d-reconstruction

## Task and data

The assignment requires a complete image-to-3D reconstruction and rendering pipeline for ten objects retained by Assignment 1, point-matching results for every object, one reconstructed GIF per object, implementation code, prompts and analysis of the stages affecting reconstruction. This implementation uses Nerfstudio's Splatfacto implementation of 3D Gaussian Splatting.

The source dataset is the course Objaverse collection in SenseCore AFS. Its GLBs are read from `/mnt/afs/260010017/data/objaverse/glbs`; `/afs/260010017/data/objaverse/glbs` is the alternate mount. A real GLB was read from the user's account's container and its `glTF` magic, v2 header and file length are recorded by the access probe. Reading the shared dataset does not modify its assets or permissions.

The selected objects are drawn from the final Assignment 1 `keep_uids.txt`, resolved from `cleaning/FINAL_OUTPUT_CURRENT.txt`. That manifest contains 48,824 UIDs. Its SHA-256 hash and the ten original cleaning rows are stored in `configs/objects.json`. Selection requires complete cleaning features, successful mesh loading, a base-color texture, no animation or Draco compression, 2,000 to 150,000 faces, sufficient three-dimensional extent and GLB size below 25 MB. Ten predefined name categories are ranked by Assignment 1's CLIP object score, then texture variation and UID, before viewing reconstruction results. Categories are name-based selection groups, not independently verified semantic labels.

## Multi view image generation

Blender loads each GLB, freezes it at frame 1 and removes imported cameras and lights. It preserves relative object transforms, centers the world-space bounding box and scales its longest side to 2 units. Three rings at elevations −20°, 15° and 50° each contain 24 azimuths, yielding 72 images of 512 × 512 pixels. The perspective camera uses a 50 mm lens, 36 mm sensor and radius 4. The RGB background is white, and three area lights remain fixed in the world. Cycles uses 32 samples and seed 42.

`capture.json` records the normalization and actual Blender camera-to-world matrices. The source GLB is used to generate observations. Reconstruction training receives images and camera information according to the selected protocol; it does not receive source mesh surfaces or a source mesh turntable as its reconstruction result.

## Feature matching and camera estimation

COLMAP extracts SIFT features, exhaustively matches image pairs and geometrically verifies correspondences. CPU SIFT is selected for compatibility with the Ubuntu COLMAP binary. For 72 images, exhaustive matching considers up to 2,556 distinct unordered pairs. All pair counts and verified feature-index pairs are exported, with corresponding keypoint coordinates and image IDs. Matching figures sample low, medium and high inlier-count pairs; they do not show only the best pair.

The estimated-pose pipeline runs incremental structure from motion and bundle adjustment through `ns-process-data`. It requires at least 80 percent camera registration and a sparse point cloud before Splatfacto training. A failure is saved with logs rather than silently bypassed. This matters for weakly textured, repetitive and symmetric objects: visually plausible isolated matches do not guarantee a globally consistent camera solution.

## Camera protocols and evaluation

**Estimated poses:** COLMAP estimates cameras and sparse geometry from all input images. Evaluation images are excluded from the reconstruction loss, but participate in camera estimation and sparse-point color estimation. Their information can therefore affect Gaussian initialization. These are transductive diagnostic metrics, not an independent held-out appearance or unseen-camera test.

**Known synthetic poses:** The controlled protocol uses the calibrated cameras saved during Blender capture. Gaussians are initialized randomly in a 2-unit range; source mesh points are not used. Twelve views at azimuth indices divisible by six, across all three elevations, are reserved for evaluation. Their pixels do not enter optimization or initialization. These results isolate reconstruction and rendering with known cameras and must not be presented as evidence that image-based pose estimation succeeded.

Nerfstudio reports PSNR, SSIM and LPIPS against the saved evaluation images. A supplementary foreground PSNR uses target pixels whose maximum absolute RGB difference from white exceeds 0.08. Full-frame scores can be dominated by the white background. The foreground approximation can omit white object regions, so it complements visual inspection rather than defining a complete silhouette metric.

## Gaussian reconstruction and rendering

Splatfacto optimizes 3D Gaussian positions, covariance parameters, opacity and appearance using differentiable splatting. The main baseline uses 15,000 iterations, seed 42 and white background. Its default progressive schedule starts at 128 pixels, changes to 256 after 3,000 steps, and reaches the native 512 pixels after 6,000 steps. Estimated-pose runs initialize from COLMAP's sparse points; known-pose runs initialize 20,000 random Gaussians. Training configurations, command lines, logs, timings and resolved dependency versions are retained.

After training, `ns-eval` and the foreground evaluator render held-out views. Known-pose runs render a continuous 120-frame orbit at 15° elevation through `ns-render camera-path`; estimated-pose runs interpolate the registered evaluation cameras. The trained Gaussian renderer produces the MP4, which is converted into an animated GIF with a shared palette. Inputs rendered directly by Blender remain in the capture folder and are not substituted for reconstructed GIFs.

## Ablation design

| Variant | Captured input resolution | Candidate views | Training steps | Purpose |
|---|---:|---:|---:|---|
| Baseline | 512 × 512 | 72 | 15,000 | Main reconstruction |
| Fixed resolution reference | 512 × 512 | 72 | 15,000 | Controlled ablation reference |
| Fewer views | 512 × 512 | 36 | 15,000 | View coverage and overlap |
| Lower resolution | 256 × 256 | 72 | 15,000 | Image detail and feature quality |
| Shorter training | 512 × 512 | 72 | 3,000 | Optimization budget |

Known-pose ablations disable progressive downscaling and use a separate fixed-resolution reference. Otherwise a 3,000-step run would also remain at a lower effective training resolution, confounding the duration comparison. All variants share the same twelve evaluation views. The fewer-view variant has 24 training views rather than the reference's 60. The supplementary evaluator resamples predicted images to the original 512 × 512 target grid, so foreground and reference full-image PSNR compare the same target pixels across resolution variants. Native Nerfstudio scores remain at each experiment's own resolution and must be labeled accordingly. Camera protocol comparisons must report their different initialization and evaluation protocols alongside numerical results.

The chair, armored car and cake were selected for the ablations before checking their reconstruction scores. The analysis reports per-object differences and means. All ten camera-recovery attempts remain in the success-rate denominator, including incomplete reconstructions.

## Results and findings

Ten known-pose baseline reconstructions have completed training, held-out evaluation and GIF export. Each main GIF contains 75 frames and loops continuously. The saved angle sheets inspect four orbit angles per object. The complete measured results are supplied by `results.csv`, per-object `metrics.json` and saved target-versus-rendered images. `docs/experimental_findings.md` reports the measured camera-recovery outcomes and controlled ablations.

## Reproducibility and AI assistance

The repository contains the complete orchestration and analysis code. Nerfstudio, COLMAP and Blender are external dependencies, identified by versions and source links. `result.json` contains the commands and timings actually executed for each object. Assignment-specific user requests and the implementation's prompt inventory are retained under `prompts/`. The reconstruction pipeline does not call an image generator or language model to create object views or experimental measurements.

Codex assisted with pipeline implementation, environment setup, tests and documentation. The report cover contains fields for the group to provide each member's name and actual contributions.

## References

- [Nerfstudio Splatfacto](https://docs.nerf.studio/nerfology/methods/splat.html)
- [Nerfstudio 1.1.5 source and CLI implementation](https://github.com/nerfstudio-project/nerfstudio/tree/v1.1.5)
- [COLMAP documentation](https://colmap.github.io/)
- [3D Gaussian Splatting for Real Time Radiance Field Rendering](https://repo-sam.inria.fr/fungraph/3d-gaussian-splatting/)

Object attribution is stored in `artifacts/object_attribution.json`, including source authors, licenses and source URLs.
