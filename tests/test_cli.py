"""Tests for segaudit.cli and segaudit.envcheck."""

from __future__ import annotations

import json
from pathlib import Path

from segaudit import __version__
from segaudit.cli import main
from segaudit.envcheck import Dependency, check_dependency, format_report, system_summary


def test_info_prints_version_and_config_status(capsys, config_file: Path):
    code = main(["info", "--config", str(config_file)])
    out = capsys.readouterr().out
    assert code == 0
    assert f"segaudit {__version__}" in out
    assert "found" in out


def test_config_show_emits_json_with_absolute_paths(capsys, config_file: Path, repo_root: Path):
    code = main(["config", "show", "--config", str(config_file)])
    out = capsys.readouterr().out
    assert code == 0
    payload = json.loads(out)
    assert payload["seed"] == 123
    assert Path(payload["paths"]["outputs"]).is_absolute()
    assert Path(payload["root"]) == repo_root.resolve()


def test_init_creates_folders_then_is_idempotent(capsys, config_file: Path, repo_root: Path):
    assert main(["init", "--config", str(config_file)]) == 0
    assert "Created:" in capsys.readouterr().out
    for sub in ("data/raw", "data/processed", "outputs", "models"):
        assert (repo_root / sub).is_dir()
    # Running again changes nothing and says so.
    assert main(["init", "--config", str(config_file)]) == 0
    assert "nothing to do" in capsys.readouterr().out


def test_missing_config_gives_exit_code_2(capsys, tmp_path: Path):
    code = main(["config", "show", "--config", str(tmp_path / "missing.yaml")])
    assert code == 2
    assert "Configuration error" in capsys.readouterr().err


def test_check_env_runs_and_reports_phase0_packages(capsys):
    main(["check-env"])
    out = capsys.readouterr().out
    assert "SegAudit environment check" in out
    for name in ("numpy", "pandas", "duckdb", "PyYAML"):
        assert name in out


def test_check_dependency_reports_missing_module_gracefully():
    result = check_dependency(Dependency("no_such_module_xyz", "no-such", "Phase 9"))
    assert result.ok is False
    assert "ModuleNotFoundError" in result.detail


def test_format_report_lists_missing_required_packages():
    from segaudit.envcheck import CheckResult

    results = [
        CheckResult(Dependency("numpy", "numpy", "Phase 0"), True, "1.0"),
        CheckResult(Dependency("ghost", "ghost", "Phase 3"), False, "-", "ModuleNotFoundError"),
    ]
    text = format_report(results, system_summary())
    assert "Missing required packages: ghost" in text


# --- two-track foundation ----------------------------------------------------


def test_info_prints_track(capsys, config_file: Path):
    main(["info", "--config", str(config_file)])
    assert "track       radiology" in capsys.readouterr().out
    main(["info", "--config", str(config_file), "--track", "pathology"])
    assert "track       pathology" in capsys.readouterr().out


def test_config_show_reports_track_override(capsys, config_file: Path):
    main(["config", "show", "--config", str(config_file), "-t", "pathology"])
    assert json.loads(capsys.readouterr().out)["track"] == "pathology"


def test_schemas_command_lists_and_describes(capsys):
    assert main(["schemas"]) == 0
    out = capsys.readouterr().out
    assert "slides" in out and "case_metrics" in out
    assert main(["schemas", "cells"]) == 0
    assert "class_name" in capsys.readouterr().out
    assert main(["schemas", "nothing"]) == 2


def test_data_inventory_on_pathology_reports_not_ready(capsys, config_file: Path):
    assert main(["data", "inventory", "--config", str(config_file), "--track", "pathology"]) == 3
    assert "P1" in capsys.readouterr().err


def test_data_phantom_then_slide_info_end_to_end(capsys, repo_root: Path, minimal_config: dict):
    import yaml

    data = {
        **minimal_config,
        "track": "pathology",
        "pathology": {"synthetic": {"n_slides": 1, "tiles_per_slide": 2, "grid": 2, "tile_size": 64}},
    }
    cfg_path = repo_root / "configs" / "p.yaml"
    cfg_path.write_text(yaml.safe_dump(data), encoding="utf-8")

    assert main(["data", "phantom", "--config", str(cfg_path)]) == 0
    out = capsys.readouterr().out
    assert "track 'pathology'" in out and "n_tiles" in out

    slide = repo_root / "data" / "raw" / "synthetic_tiles" / "slides" / "synth_000.tif"
    for backend in ("openslide", "tiffslide", "auto"):
        assert main(["slide", "info", str(slide), "--backend", backend]) == 0
        out = capsys.readouterr().out
        assert "mpp (x, y)     0.5, 0.5" in out and "magnification  20" in out

    assert main(["slide", "info", str(repo_root / "missing.svs")]) == 4
