# Changelog

All notable changes to SegAudit are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/): `MAJOR.MINOR.PATCH`, where a new
MINOR version means a new phase landed and a new PATCH means a fix or a
documentation improvement.

## [Unreleased]

Nothing yet. Next up: Phase 1 (data layer) → v0.2.0 — see
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

[Unreleased]: https://github.com/akannan2987/segaudit/compare/v0.1.0...develop
[0.1.0]: https://github.com/akannan2987/segaudit/releases/tag/v0.1.0
