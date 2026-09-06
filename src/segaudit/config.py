"""Configuration loading for SegAudit.

Why this module exists
----------------------
Everything that could reasonably change between two runs — where the data is,
which seed to use, how many epochs to train — lives in a YAML file under
``configs/``. This module reads that file and hands the rest of the code a
tidy, typed object. The rest of the code never opens YAML files itself.

Three design rules are enforced here:

1. **Paths are resolved relative to the repository root**, i.e. the parent of
   the ``configs/`` folder that the YAML file sits in. That way the same file
   works on Windows, macOS and Linux and does not care which folder you ran
   the command from. Absolute paths in the YAML are left alone.
2. **Unknown keys are tolerated, missing required keys are not.** Later
   phases add sections freely; a typo in ``paths`` fails loudly and early.
3. **Every run belongs to exactly one track.** ``track: radiology`` means 3D
   volumes (scans); ``track: pathology`` means 2D slides. The track decides
   which input door the pipeline uses; the shared core downstream does not
   care. If the YAML omits ``track`` it defaults to ``radiology``, so every
   configuration written before tracks existed keeps working unchanged.

Everyday analogy: the YAML file is the recipe card; this module is the cook
reading it aloud, converting "a cup" into grams for the kitchen you are in.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

# Keys that must exist for the pipeline to make sense at all.
_REQUIRED_TOP_LEVEL = ("project", "paths", "data", "reproducibility", "storage")
_REQUIRED_PATHS = ("data_raw", "data_processed", "outputs", "models")

# The two input doors. Everything after the door is shared.
TRACKS = ("radiology", "pathology")
DEFAULT_TRACK = "radiology"


class ConfigError(ValueError):
    """Raised when a configuration file is missing something essential."""


@dataclass(frozen=True)
class Paths:
    """The four folders every phase reads from or writes to."""

    data_raw: Path
    data_processed: Path
    outputs: Path
    models: Path

    def all(self) -> tuple[Path, ...]:
        """Return every folder, in a fixed order (useful for ``init``)."""
        return (self.data_raw, self.data_processed, self.outputs, self.models)


@dataclass(frozen=True)
class Config:
    """A loaded, validated configuration.

    ``raw`` keeps the complete YAML content as a plain dictionary so that later
    phases can read their own sections (``cfg.raw["training"]``) without this
    file needing to know about them in advance.
    """

    project_name: str
    run_label: str
    track: str
    seed: int
    storage_backend: str
    use_synthetic: bool
    paths: Paths
    root: Path
    source_file: Path
    raw: dict[str, Any] = field(default_factory=dict)

    def section(self, name: str) -> dict[str, Any]:
        """Return one top-level section of the YAML (empty dict if absent)."""
        value = self.raw.get(name, {})
        return dict(value) if isinstance(value, dict) else {}

    @property
    def is_pathology(self) -> bool:
        return self.track == "pathology"

    @property
    def is_radiology(self) -> bool:
        return self.track == "radiology"


def validate_track(value: Any) -> str:
    """Return a valid track name or raise a ConfigError naming the options."""
    if value is None:
        return DEFAULT_TRACK
    name = str(value).strip().lower()
    if name not in TRACKS:
        raise ConfigError(f"Unknown track {value!r}; choose one of: {', '.join(TRACKS)}")
    return name


def _resolve(root: Path, value: str | Path) -> Path:
    """Turn a path from the YAML into an absolute path.

    Relative paths are joined onto ``root``; absolute ones pass through.
    ``expanduser`` lets ``~/scans`` work on every operating system.
    """
    p = Path(value).expanduser()
    return p if p.is_absolute() else (root / p).resolve()


def load_config(
    path: str | Path,
    root: str | Path | None = None,
    track: str | None = None,
) -> Config:
    """Load and validate a YAML configuration file.

    Parameters
    ----------
    path:
        The YAML file, e.g. ``configs/default.yaml``.
    root:
        The repository root used to resolve relative paths. If omitted, it is
        taken to be the parent of the folder containing the YAML file — which
        is the repository root for anything under ``configs/``.
    track:
        Optional override of the YAML's ``track`` (the command line's
        ``--track`` flag lands here). Validated the same way.
    """
    path = Path(path).expanduser().resolve()
    if not path.exists():
        raise ConfigError(f"Configuration file not found: {path}")

    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}

    if not isinstance(data, dict):
        raise ConfigError(f"Top level of {path.name} must be a mapping of sections.")

    missing = [k for k in _REQUIRED_TOP_LEVEL if k not in data]
    if missing:
        raise ConfigError(f"{path.name} is missing required section(s): {', '.join(missing)}")

    missing_paths = [k for k in _REQUIRED_PATHS if k not in data["paths"]]
    if missing_paths:
        raise ConfigError(f"{path.name} 'paths' is missing: {', '.join(missing_paths)}")

    root_path = Path(root).expanduser().resolve() if root is not None else path.parent.parent

    paths = Paths(**{k: _resolve(root_path, data["paths"][k]) for k in _REQUIRED_PATHS})

    try:
        seed = int(data["reproducibility"]["seed"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ConfigError("'reproducibility.seed' must be an integer.") from exc

    chosen_track = validate_track(track if track is not None else data.get("track"))

    return Config(
        project_name=str(data["project"].get("name", "segaudit")),
        run_label=str(data["project"].get("run_label", "default")),
        track=chosen_track,
        seed=seed,
        storage_backend=str(data["storage"].get("backend", "local_parquet")),
        use_synthetic=bool(data["data"].get("use_synthetic", False)),
        paths=paths,
        root=root_path,
        source_file=path,
        raw=data,
    )


def default_config_path() -> Path:
    """Locate ``configs/default.yaml`` relative to the current working directory.

    The command line uses this so that ``segaudit info`` works from the
    repository root without any arguments.
    """
    return Path.cwd() / "configs" / "default.yaml"
