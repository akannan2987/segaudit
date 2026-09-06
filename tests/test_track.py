"""Tests for the track concept in configuration and API (two-track foundation)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from segaudit import api
from segaudit.config import TRACKS, ConfigError, load_config, validate_track


def _write(repo_root: Path, name: str, data: dict) -> Path:
    path = repo_root / "configs" / name
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


def test_track_defaults_to_radiology_when_absent(config_file: Path):
    cfg = load_config(config_file)
    assert cfg.track == "radiology"
    assert cfg.is_radiology and not cfg.is_pathology


def test_track_read_from_yaml(repo_root: Path, minimal_config):
    path = _write(repo_root, "p.yaml", {**minimal_config, "track": "pathology"})
    cfg = load_config(path)
    assert cfg.track == "pathology"
    assert cfg.is_pathology


def test_track_override_wins_over_yaml(repo_root: Path, minimal_config):
    path = _write(repo_root, "p.yaml", {**minimal_config, "track": "pathology"})
    assert load_config(path, track="radiology").track == "radiology"


def test_track_is_case_insensitive_and_trimmed(repo_root: Path, minimal_config):
    path = _write(repo_root, "p.yaml", {**minimal_config, "track": "  Pathology "})
    assert load_config(path).track == "pathology"


@pytest.mark.parametrize("bad", ["histology", "ct", "", 3])
def test_unknown_track_raises(repo_root: Path, bad, minimal_config):
    path = _write(repo_root, "bad.yaml", {**minimal_config, "track": bad})
    with pytest.raises(ConfigError, match="Unknown track"):
        load_config(path)


def test_validate_track_lists_options():
    assert validate_track(None) == "radiology"
    with pytest.raises(ConfigError, match="radiology, pathology"):
        validate_track("nope")


def test_api_exposes_both_tracks():
    assert api.tracks() == TRACKS == ("radiology", "pathology")


def test_shipped_configs_declare_their_track():
    here = Path(__file__).resolve().parent.parent / "configs"
    assert load_config(here / "default.yaml").track == "radiology"
    assert load_config(here / "quick.yaml").track == "radiology"
    assert load_config(here / "quick-pathology.yaml").track == "pathology"


def test_generate_synthetic_dispatches_on_track(config_file: Path):
    cfg = load_config(config_file)  # radiology by default; minimal config -> generator defaults
    api.initialise_workspace(cfg)
    summary = api.generate_synthetic(cfg)
    assert summary["n_cases"] == 12 and "synthetic_phantom" in summary["root"]
    # Slide downloads and inventory are still Phase P1's, and say so explicitly.
    with pytest.raises(NotImplementedError, match="P1"):
        api.build_inventory(load_config(config_file, track="pathology"))
