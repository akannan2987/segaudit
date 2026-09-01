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
