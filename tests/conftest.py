"""Shared test fixtures.

A *fixture* is a piece of setup pytest builds for you before a test runs and
throws away afterwards. The one below creates a throwaway repository root
with a ``configs/test.yaml`` inside it, so every test works on a clean,
temporary folder and never writes into the real ``data/`` or ``outputs/``.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

MINIMAL_CONFIG = {
    "project": {"name": "segaudit", "run_label": "test"},
    "paths": {
        "data_raw": "data/raw",
        "data_processed": "data/processed",
        "outputs": "outputs",
        "models": "models",
    },
    "data": {"source": "synthetic_phantom", "use_synthetic": True},
    "reproducibility": {"seed": 123},
    "storage": {"backend": "local_parquet"},
}


@pytest.fixture
def repo_root(tmp_path: Path) -> Path:
    """A temporary folder shaped like the repository root."""
    (tmp_path / "configs").mkdir()
    return tmp_path


@pytest.fixture
def config_file(repo_root: Path) -> Path:
    """Write a valid minimal config and return its path."""
    path = repo_root / "configs" / "test.yaml"
    path.write_text(yaml.safe_dump(MINIMAL_CONFIG), encoding="utf-8")
    return path
