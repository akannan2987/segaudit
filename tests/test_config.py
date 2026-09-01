"""Tests for segaudit.config.

Each test states, in its name, the behaviour it protects. If one of these
fails later, the name tells you which promise was broken.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from segaudit.config import ConfigError, load_config


def test_loads_minimal_config_and_resolves_paths_under_root(config_file: Path, repo_root: Path):
    cfg = load_config(config_file)

    assert cfg.project_name == "segaudit"
    assert cfg.run_label == "test"
    assert cfg.seed == 123
    assert cfg.storage_backend == "local_parquet"
    assert cfg.use_synthetic is True
    # Relative paths in YAML become absolute paths under the repo root.
    assert cfg.root == repo_root.resolve()
    assert cfg.paths.data_raw == (repo_root / "data" / "raw").resolve()
    assert cfg.paths.outputs == (repo_root / "outputs").resolve()
    assert all(p.is_absolute() for p in cfg.paths.all())


def test_absolute_paths_in_yaml_are_left_alone(repo_root: Path, tmp_path: Path):
    elsewhere = tmp_path / "somewhere_else"
    data = {
        "project": {"name": "x"},
        "paths": {
            "data_raw": str(elsewhere),
            "data_processed": "data/processed",
            "outputs": "outputs",
            "models": "models",
        },
        "data": {},
        "reproducibility": {"seed": 1},
        "storage": {},
    }
    path = repo_root / "configs" / "abs.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")

    cfg = load_config(path)
    assert cfg.paths.data_raw == elsewhere.resolve()


def test_explicit_root_overrides_inferred_root(config_file: Path, tmp_path: Path):
    other_root = tmp_path / "other"
    cfg = load_config(config_file, root=other_root)
    assert cfg.root == other_root.resolve()
    assert cfg.paths.models == (other_root / "models").resolve()


def test_missing_file_raises_config_error(tmp_path: Path):
    with pytest.raises(ConfigError, match="not found"):
        load_config(tmp_path / "nope.yaml")


def test_missing_section_raises_config_error(repo_root: Path):
    path = repo_root / "configs" / "broken.yaml"
    path.write_text(yaml.safe_dump({"project": {"name": "x"}}), encoding="utf-8")
    with pytest.raises(ConfigError, match="missing required section"):
        load_config(path)


def test_missing_path_key_raises_config_error(repo_root: Path):
    data = {
        "project": {},
        "paths": {"data_raw": "a", "outputs": "b", "models": "c"},  # no data_processed
        "data": {},
        "reproducibility": {"seed": 1},
        "storage": {},
    }
    path = repo_root / "configs" / "broken.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    with pytest.raises(ConfigError, match="data_processed"):
        load_config(path)


def test_non_integer_seed_raises_config_error(repo_root: Path):
    data = {
        "project": {},
        "paths": {"data_raw": "a", "data_processed": "d", "outputs": "b", "models": "c"},
        "data": {},
        "reproducibility": {"seed": "lots"},
        "storage": {},
    }
    path = repo_root / "configs" / "broken.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    with pytest.raises(ConfigError, match="seed"):
        load_config(path)


def test_section_returns_extra_yaml_sections(config_file: Path):
    cfg = load_config(config_file)
    assert cfg.section("training") == {}  # absent -> empty, never an error
    assert cfg.section("paths")["outputs"] == "outputs"  # raw YAML value, unresolved


def test_repository_default_configs_load():
    """The two shipped configs must always be valid."""
    here = Path(__file__).resolve().parent.parent
    for name in ("default.yaml", "quick.yaml"):
        cfg = load_config(here / "configs" / name)
        assert cfg.root == here
        assert cfg.seed > 0
