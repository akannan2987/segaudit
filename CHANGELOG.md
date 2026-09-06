# Changelog

All notable changes to SegAudit are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/): `MAJOR.MINOR.PATCH`, where a new
MINOR version means a new phase landed and a new PATCH means a fix or a
documentation improvement.

## [Unreleased]

### Added
- **Phase 1 — data, Track R (code).** *Track R:* NIfTI I/O with geometry
  preserved (`radiology/io_nifti.py`: frozen `Volume`, spacing, orientation,
  volumes in ml, header-only reads); the MRI phantom generator
  (`radiology/phantom_volume.py`: seeded T1-like volumes with a two-label
  hippocampus-shaped structure, five mask failure modes, four image
  artefacts, written in the public dataset's layout); input QA gates
  (`radiology/qa.py`: spacing, shape, finiteness, constant images, labels,
  foreground, image–mask geometry match; limits from the `qa` config section);
  dataset download that verifies the published MD5, resumes partial
  downloads, refuses path traversal and is idempotent, plus an inventory that
  writes `cases` (geometry, intensity statistics, label volumes) and
  `qa_issues` without ever dropping a case (`radiology/dataset.py`); DICOM
  series → NIfTI conversion with a de-identified metadata summary
  (`radiology/dicom.py`). *Shared:* the `segaudit sql` read-only console
  (one-shot, `-f file.sql`, `--csv`, or interactive multi-line), the
  `queries/` folder with four documented statements, and the `runs` ledger
  written by every table-producing command (`api.record_run`). Commands:
  `segaudit data download | inventory | convert-dicom`, `segaudit sql`;
  `segaudit data phantom` now works on both tracks. Configs gain `data.msd`
  (URL, MD5, archive, folder) and `qa` sections. CI runs the Track R data
  door on all three runners. 29 new tests (102 total; the two 0P tests that
  pinned "radiology phantom not yet" now assert the delivered behaviour).
  *Track P:* unchanged; its downloads and inventory arrive with Phase P1 and
  say so explicitly.
- **Phase 1 — data, Track R (documentation + hardening).** The Phase 1
  tutorial written from a real run (28.4 MB download, published checksum
  matched, 260 cases, 0 QA errors, 33 informational intensity warnings);
  the downloader now verifies HTTPS with the `certifi` root bundle, so a
  fresh python.org install on macOS works without the manual certificate
  step (that step is nevertheless promoted to "do not skip" in the macOS
  setup guide, with the real error message in troubleshooting);
  `segaudit data demo-dicom` writes a synthetic DICOM series so the
  converter is runnable without any download; `fig_qa_vs_qc.svg`; glossary
  terms (DICOM series, bias field, Rician noise, motion artefact, root
  certificate, idempotent, checksum, path traversal, runs ledger); README,
  Handbook, roadmap, architecture and data notes updated. 103 tests.

Next up: Phase P1 (slides: data) → then Phases 2/P2, 3/P3 → v0.2.0 — see
[`docs/05-roadmap.md`](docs/05-roadmap.md).

## [0.2.0-alpha.1] — 2026-09-06 — pre-release

The two-track foundation. SegAudit now has two input doors — scans and
slides — onto one shared audit core, with the pathology door opened by a
synthetic slide dataset and a two-backend slide reader, and the documentation
rewritten so a radiologist can follow the pathology track and a pathologist
the radiology track. A *pre-release* because v0.2.0 is defined as "both
tracks have data, baselines and a first model" ([`docs/05-roadmap.md`](docs/05-roadmap.md)).

### Added
- **Two-track foundation (Phase 0P, code).** SegAudit now has two input doors
  onto one shared core. *Shared:* a `track` setting (`radiology` | `pathology`,
  default `radiology` so every earlier configuration keeps working), a
  `--track` flag on every command, a table-schema registry (`schemas.py`)
  fixing the column names both tracks write into shared tables
  (`case_metrics`, `qc_scores`, `review_ledger`, `runs`), a `segaudit schemas`
  command, and symmetric subpackages `segaudit/radiology/` and
  `segaudit/pathology/`. *Track P (new):* whole-slide image reading through one
  interface with two backends (OpenSlide via `openslide-bin`, `tiffslide` as the
  pure-Python fallback) preserving microns-per-pixel, magnification and
  pyramid levels; a pyramidal TIFF writer both backends read identically; a
  synthetic H&E-like tile generator with nuclei instance and phenotype labels,
  three spatial patterns (clustered, dispersed, infiltrating), four label
  failure modes and four image artefacts; `segaudit data phantom` and
  `segaudit slide info`; the `slides`, `tiles` and `cells` tables;
  `configs/quick-pathology.yaml`. *Track R:* unchanged; its phantom arrives
  with Phase 1 and the API says so explicitly. New dependencies pinned for
  all platforms: `openslide-bin`, `openslide-python`, `tiffslide`,
  `tifffile`, `Pillow`, `scipy`. CI reads a synthetic slide through both
  backends on all three runners. 44 new tests (73 total).
- **Two-track foundation (Phase 0P, documentation).** README rewritten for
  two tracks (paired figures, two-branch architecture diagram, interleaved
  build log, data table with licences and non-commercial flags); Handbook
  walking both tracks; glossary section 15 "Slides and stains" (34 terms);
  architecture with the two-doors-one-core section and design rule 6; slide
  reader section and troubleshooting in all three setup guides; roadmap
  rewritten as the interleaved two-track plan with approach and effort per
  phase; product roadmap extended with the slide pipeline and nine pathology
  options (WSI tiling service, DICOM-WSI, OMERO, deep-zoom viewer, GPU
  inference service, generative augmentation / virtual staining, image–text
  models, cell and tissue ontologies, spatial-omics platforms); the Phase 0P
  tutorial; two figures (`fig_slide_pyramid.svg`, `fig_two_tracks.svg`);
  CONTRIBUTING's two-track self-check and equal-weight norm.
- Illustrations across the documentation (from v0.1.0's follow-up): SVG
  figures and Mermaid diagrams, plus an illustration standard in
  `CONTRIBUTING.md`.

### Changed
- Package version `0.2.0a1`. `segaudit --version` reports it.
- Illustrations across the documentation: SVG figures (voxel/volume, Dice
  overlap, the mean-hides-failures problem, virtual-environment toolboxes) in
  `docs/img/`, plus Mermaid diagrams in the setup guides, architecture, Git
  workflow, Phase 0 tutorial, Handbook, roadmap and lock-file guide; an
  illustration standard added to `CONTRIBUTING.md`.

Next up: Phase 1 (data layer) → v0.2.0 — see
[`docs/05-roadmap.md`](docs/05-roadmap.md).

## [0.1.0] — 2026-09-02

The foundation release. No pipeline phases yet — deliberately: this release is
the workshop every later phase is built in, verified on Windows, macOS and
Linux. See [`docs/HANDBOOK.md`](docs/HANDBOOK.md) for the guided tour.

### Added
- **Phase 0 — skeleton.** Installable `segaudit` package (src layout), YAML
  configuration with cross-platform path resolution, a storage interface with a
  local Parquet + DuckDB implementation (read-only SQL included), a command
  line (`info`, `check-env`, `config show`, `init`), an environment self-check,
  pinned dependency files with a CPU-only PyTorch install path and per-platform
  environment markers (Intel Macs run the last PyTorch/MONAI built for that
  hardware), a 29-test pytest suite, ruff configuration, a pre-push safety
  script, and a CI workflow that runs on Windows, macOS and Linux.
- **Documentation set.** README; contribution guide (branch model, push
  sequence, release flow, code and documentation norms); glossary with an
  everyday analogy for every term; blank-machine setup guides for Windows,
  macOS and RHEL 8 written from real sessions with expected output and
  troubleshooting; architecture walkthrough with hands-on exercises; Git
  workflow guide; the Phase 0 tutorial; the Handbook — a single living
  day-0-to-product walkthrough; the roadmap
  ([`docs/05-roadmap.md`](docs/05-roadmap.md)) and the product & technology
  roadmap ([`docs/06-product-and-technology-roadmap.md`](docs/06-product-and-technology-roadmap.md)).
- **Reproducibility tooling.** Per-platform environment lock files
  (`locks/`, `scripts/freeze_lock.py`) with a verified rebuild-and-clean-up
  drill; deterministic seeds in configuration; `.gitignore` covering any
  `.venv*` folder, data, models and secrets.

### Notes
- Dependency pins are resolved for Python 3.11 on Windows, Linux,
  Apple-silicon macOS and Intel macOS. Results across the two dependency lanes
  match to numerical tolerance; byte-identical reproducibility holds within a
  lane.
- The pipeline phases (data, preprocessing, model, validation, uncertainty,
  quality control, repeatability, biomarkers, review app, agent tools,
  container) arrive as minor versions 0.2 → 1.0 per
  [`docs/05-roadmap.md`](docs/05-roadmap.md).

[Unreleased]: https://github.com/akannan2987/segaudit/compare/v0.2.0-alpha.1...develop
[0.2.0-alpha.1]: https://github.com/akannan2987/segaudit/releases/tag/v0.2.0-alpha.1
[0.1.0]: https://github.com/akannan2987/segaudit/releases/tag/v0.1.0
