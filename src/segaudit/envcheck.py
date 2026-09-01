"""Environment self-check.

``segaudit check-env`` runs this. It answers the first question anyone has
after installing: *did it actually work?* Each dependency is imported, its
version printed, and — if the import fails — the phase that first needs it,
so a missing package is only alarming if you have reached that phase.

Kept free of any heavy imports at module level so that ``segaudit info``
stays instant even when PyTorch is not installed.
"""

from __future__ import annotations

import importlib
import os
import platform
import sys
from dataclasses import dataclass


@dataclass(frozen=True)
class Dependency:
    module: str  # what you `import`
    dist: str  # what you `pip install`
    first_needed: str  # phase that first uses it
    optional: bool = False


# Order matters only for the printout. "Phase 0" = needed right now.
DEPENDENCIES: tuple[Dependency, ...] = (
    Dependency("numpy", "numpy", "Phase 0"),
    Dependency("pandas", "pandas", "Phase 0"),
    Dependency("pyarrow", "pyarrow", "Phase 0"),
    Dependency("duckdb", "duckdb", "Phase 0"),
    Dependency("yaml", "PyYAML", "Phase 0"),
    Dependency("nibabel", "nibabel", "Phase 1"),
    Dependency("SimpleITK", "SimpleITK", "Phase 1"),
    Dependency("pydicom", "pydicom", "Phase 1"),
    Dependency("skimage", "scikit-image", "Phase 2"),
    Dependency("sklearn", "scikit-learn", "Phase 6"),
    Dependency("torch", "torch", "Phase 3"),
    Dependency("monai", "monai", "Phase 3"),
    Dependency("pytest", "pytest", "Phase 0 (dev)", optional=True),
    Dependency("ruff", "ruff", "Phase 0 (dev)", optional=True),
)


@dataclass(frozen=True)
class CheckResult:
    dependency: Dependency
    ok: bool
    version: str
    detail: str = ""


def _version_of(module: object) -> str:
    for attr in ("__version__", "version", "VERSION"):
        value = getattr(module, attr, None)
        if value is not None:
            return str(value() if callable(value) else value)
    return "?"


def check_dependency(dep: Dependency) -> CheckResult:
    try:
        module = importlib.import_module(dep.module)
    except Exception as exc:  # ImportError, but also OSError for broken binaries
        return CheckResult(dep, False, "-", f"{type(exc).__name__}: {exc}")
    return CheckResult(dep, True, _version_of(module))


def system_summary() -> dict[str, str]:
    """Facts about the machine that matter for reproducibility."""
    return {
        "python": sys.version.split()[0],
        "executable": sys.executable,
        "platform": platform.platform(),
        "machine": platform.machine(),
        "cpu_count": str(os.cpu_count() or "?"),
    }


def run_checks() -> list[CheckResult]:
    return [check_dependency(d) for d in DEPENDENCIES]


def format_report(results: list[CheckResult], system: dict[str, str]) -> str:
    """Render a plain-text report; the CLI prints exactly this."""
    lines = ["SegAudit environment check", "=" * 27, ""]
    for key, value in system.items():
        lines.append(f"{key:<11} {value}")
    lines += ["", f"{'package':<14}{'status':<9}{'version':<12}first needed", "-" * 55]
    for r in results:
        status = "ok" if r.ok else ("missing" if r.dependency.optional else "MISSING")
        lines.append(
            f"{r.dependency.dist:<14}{status:<9}{r.version:<12}{r.dependency.first_needed}"
        )
        if not r.ok and r.detail:
            lines.append(f"{'':<14}  -> {r.detail}")
    required_missing = [r for r in results if not r.ok and not r.dependency.optional]
    lines.append("")
    if required_missing:
        names = ", ".join(r.dependency.dist for r in required_missing)
        lines.append(f"Missing required packages: {names}")
        lines.append("See docs/01-setup-<your-os>.md, section 'Troubleshooting'.")
    else:
        lines.append("All required packages import. You are ready.")
    return "\n".join(lines)
