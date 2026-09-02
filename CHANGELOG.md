# Changelog

All notable changes to SegAudit are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/): `MAJOR.MINOR.PATCH`, where a new
MINOR version means a new phase landed and a new PATCH means a fix or a
documentation improvement.

## [Unreleased]

### Added
- **Phase 0 — skeleton.** Installable `segaudit` package (src layout), YAML
  configuration with cross-platform path resolution, a storage interface with a
  local Parquet + DuckDB implementation, a command line (`info`, `check-env`,
  `config show`, `init`), an environment self-check, pinned dependency files
  with a CPU-only PyTorch install path, a pytest suite, ruff configuration,
  a pre-push safety script, and a CI workflow that runs on Windows, macOS and
  Linux.
- Repository documentation: README, contribution guide (branch model and release
  flow), licence, this changelog, glossary, and setup guides for Windows, macOS
  and RHEL 8 written from real sessions with expected output and troubleshooting,
  architecture walkthrough, Git workflow guide, and the Phase 0 tutorial.

### Notes
- Dependency pins are resolved for Python 3.11 on Windows, Linux, Apple-silicon
  macOS and Intel macOS. Intel Macs receive `torch 2.2.2 / monai 1.4.0 /
  numpy 1.26` through environment markers because PyTorch no longer builds
  for that hardware; all other platforms receive the current versions.
- Version 0.1.0 is a foundation release: the pipeline phases (data, preprocessing,
  model, validation, uncertainty, quality control, repeatability, biomarkers,
  review app, agent tools, container) are planned in `docs/05-roadmap.md` and
  arrive as minor versions 0.2 → 1.0.

[Unreleased]: https://github.com/akannan2987/segaudit/compare/master...develop
