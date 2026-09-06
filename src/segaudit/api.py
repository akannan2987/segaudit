"""The public API of SegAudit.

Rule of the project: **all capabilities are functions in this module.** The
command line (``cli.py``), the review app, the Model Context Protocol server
and any future web service are thin wrappers that call these functions and
present the result. None of them implement pipeline logic themselves.

Why: if the logic lived in the command line, the app would have to copy it;
if it lived in the app, a service could not reuse it. One place, many doors.

Everyday analogy: a bank has one vault and many counters — the branch, the
website, the phone line. Each counter takes your request to the same vault.

Two tracks, one API
-------------------
Every function takes a :class:`~segaudit.config.Config`, and the config says
which **track** it belongs to: ``radiology`` (3D scans) or ``pathology``
(2D slides). Functions that differ per track dispatch on ``cfg.track`` and
call the matching subpackage; functions of the shared core do not look at the
track at all. That is the whole two-track design in one sentence.

Phase 0 exposed the foundations; the two-track foundation adds the synthetic
data generators and slide reading. Each later phase adds its functions here
and lists them in ``__all__`` so the surface stays discoverable.
"""

from __future__ import annotations

from pathlib import Path

from segaudit import __version__
from segaudit.config import TRACKS, Config, default_config_path, load_config
from segaudit.storage import Storage, open_storage

__all__ = [
    "version",
    "tracks",
    "load",
    "storage_for",
    "initialise_workspace",
    "generate_synthetic",
    "download_dataset",
    "build_inventory",
    "query",
    "convert_dicom_series",
    "write_demo_dicom_series",
    "record_run",
    "slide_info",
]


def version() -> str:
    """The installed SegAudit version."""
    return __version__


def tracks() -> tuple[str, ...]:
    """The input doors this build knows: ``('radiology', 'pathology')``."""
    return TRACKS


def load(config_path: str | Path | None = None, track: str | None = None) -> Config:
    """Load a configuration (``configs/default.yaml`` if none is given).

    ``track`` overrides the YAML's track — the command line's ``--track``.
    """
    return load_config(config_path or default_config_path(), track=track)


def storage_for(cfg: Config) -> Storage:
    """Open the storage backend named in ``cfg``."""
    return open_storage(cfg)


def initialise_workspace(cfg: Config) -> list[Path]:
    """Create every folder the configuration refers to.

    Returns the folders that were created (already-existing ones are skipped),
    so callers can report exactly what changed.
    """
    created: list[Path] = []
    for folder in cfg.paths.all():
        if not folder.exists():
            folder.mkdir(parents=True, exist_ok=True)
            created.append(folder)
    return created


def generate_synthetic(cfg: Config) -> dict:
    """Generate the track's synthetic dataset (no download).

    Track R: T1-like volumes with a two-label hippocampus-shaped structure,
    in the public dataset's layout — see :mod:`segaudit.radiology.phantom_volume`.
    Inventory it afterwards with :func:`build_inventory`.
    Track P: H&E-like tiles with nuclei instance/class labels, three spatial
    patterns, and an assembled pyramidal slide per synthetic slide id, plus
    the ``slides``/``tiles``/``cells`` tables — see
    :mod:`segaudit.pathology.phantom_tiles`.
    """
    storage = open_storage(cfg)
    if cfg.is_pathology:
        from segaudit.pathology import phantom_tiles  # noqa: PLC0415

        return phantom_tiles.generate_dataset(cfg, storage)
    from segaudit.radiology import phantom_volume  # noqa: PLC0415

    return phantom_volume.generate_dataset(cfg)


def download_dataset(cfg: Config, progress=None) -> dict:
    """Fetch, verify and extract the track's public dataset. Idempotent.

    Track R today (Medical Segmentation Decathlon, hippocampus); Track P's
    downloads arrive with Phase P1 and raise ``NotImplementedError`` until then.
    """
    if cfg.is_pathology:
        raise NotImplementedError("Slide dataset downloads arrive with Phase P1 (data).")
    from segaudit.radiology import dataset  # noqa: PLC0415

    return dataset.download_dataset(cfg, progress=progress)


def build_inventory(cfg: Config) -> dict:
    """Walk the configured dataset into its tables (``cases`` + ``qa_issues`` on Track R)."""
    if cfg.is_pathology:
        raise NotImplementedError("The slide inventory arrives with Phase P1 (data).")
    from segaudit.radiology import dataset  # noqa: PLC0415

    return dataset.build_inventory(cfg, open_storage(cfg))


def query(cfg: Config, sql: str):
    """Run read-only SQL over the run's tables and return a DataFrame.

    Tables are registered as views, so ``SELECT`` works and anything that
    would modify data is refused by the engine — see
    :meth:`segaudit.storage.LocalParquetStorage.query`.
    """
    return open_storage(cfg).query(sql)


def convert_dicom_series(folder: str | Path, output: str | Path, series_id: str | None = None) -> dict:
    """Stack a DICOM series into one NIfTI file with its geometry; return a metadata summary."""
    from segaudit.radiology import dicom  # noqa: PLC0415

    return dicom.convert_series(folder, output, series_id)


def write_demo_dicom_series(folder: str | Path) -> Path:
    """Write a tiny synthetic DICOM series (no download) to try the converter on."""
    from segaudit.radiology import dicom  # noqa: PLC0415

    return dicom.write_demo_series(folder)


def record_run(cfg: Config, command: str, run_id: str | None = None) -> str:
    """Append one row to the ``runs`` ledger and return its id.

    Every command that writes tables calls this first, so any table row can be
    traced to the command, configuration, seed and version that produced it.
    """
    import datetime as _dt  # noqa: PLC0415
    import uuid  # noqa: PLC0415

    import pandas as pd  # noqa: PLC0415

    from segaudit import schemas  # noqa: PLC0415

    rid = run_id or uuid.uuid4().hex[:12]
    row = pd.DataFrame([{
        "run_id": rid,
        "run_label": cfg.run_label,
        "track": cfg.track,
        "command": command,
        "config_file": str(cfg.source_file),
        "seed": cfg.seed,
        "started_at": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
        "segaudit_version": __version__,
    }])
    open_storage(cfg).append_rows("runs", schemas.check("runs", row))
    return rid


def slide_info(path: str | Path, backend: str = "auto") -> dict:
    """Open a whole-slide image and return its geometry as a plain dict.

    Track P only by nature (a slide is a slide), but it needs no config: the
    command line uses it as the setup check "can this machine read slides?".
    """
    from segaudit.pathology.io_wsi import open_slide  # noqa: PLC0415

    reader = open_slide(path, backend=backend)
    try:
        info = reader.info
        return {
            "path": str(info.path),
            "backend": info.backend,
            "width_px": info.width_px,
            "height_px": info.height_px,
            "level_count": info.level_count,
            "level_dimensions": [list(d) for d in info.level_dimensions],
            "mpp_x": info.mpp_x,
            "mpp_y": info.mpp_y,
            "magnification": info.magnification,
        }
    finally:
        reader.close()
