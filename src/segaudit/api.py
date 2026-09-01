"""The public API of SegAudit.

Rule of the project: **all capabilities are functions in this module.** The
command line (``cli.py``), the review app, the Model Context Protocol server
and any future web service are thin wrappers that call these functions and
present the result. None of them implement pipeline logic themselves.

Why: if the logic lived in the command line, the app would have to copy it;
if it lived in the app, a service could not reuse it. One place, many doors.

Everyday analogy: a bank has one vault and many counters — the branch, the
website, the phone line. Each counter takes your request to the same vault.

Phase 0 exposes only the foundations. Each later phase adds its functions
here and lists them in ``__all__`` so the surface stays discoverable.
"""

from __future__ import annotations

from pathlib import Path

from segaudit import __version__
from segaudit.config import Config, default_config_path, load_config
from segaudit.storage import Storage, open_storage

__all__ = [
    "version",
    "load",
    "storage_for",
    "initialise_workspace",
]


def version() -> str:
    """The installed SegAudit version."""
    return __version__


def load(config_path: str | Path | None = None) -> Config:
    """Load a configuration (``configs/default.yaml`` if none is given)."""
    return load_config(config_path or default_config_path())


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
