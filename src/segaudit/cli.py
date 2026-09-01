"""Command line for SegAudit.

After ``pip install -e .`` a command called ``segaudit`` exists. Run
``segaudit --help`` to see the subcommands. Every subcommand is a few lines
that call :mod:`segaudit.api` and print the result — no logic lives here.

Phase 0 commands
----------------
``segaudit info``          version, Python, platform, which config would load
``segaudit check-env``     import every dependency and report versions
``segaudit config show``   print the resolved configuration (paths made absolute)
``segaudit init``          create the data/output/model folders from the config

Uses only the standard library's ``argparse`` so the command works before any
optional package is installed.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from segaudit import api
from segaudit.config import ConfigError, default_config_path
from segaudit.envcheck import format_report, run_checks, system_summary


def _add_config_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--config",
        "-c",
        type=Path,
        default=None,
        help="YAML configuration file (default: configs/default.yaml in the current folder)",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="segaudit",
        description="Quality control and triage for medical image segmentation.",
    )
    parser.add_argument("--version", action="version", version=f"segaudit {api.version()}")
    sub = parser.add_subparsers(dest="command", required=True)

    p_info = sub.add_parser("info", help="show version, Python and platform facts")
    _add_config_arg(p_info)

    sub.add_parser("check-env", help="verify that every dependency imports")

    p_cfg = sub.add_parser("config", help="inspect configuration")
    cfg_sub = p_cfg.add_subparsers(dest="config_command", required=True)
    p_show = cfg_sub.add_parser("show", help="print the resolved configuration as JSON")
    _add_config_arg(p_show)

    p_init = sub.add_parser("init", help="create the folders named in the configuration")
    _add_config_arg(p_init)

    return parser


# --- subcommand implementations -------------------------------------------


def cmd_info(args: argparse.Namespace) -> int:
    system = system_summary()
    cfg_path = args.config or default_config_path()
    print(f"segaudit {api.version()}")
    for key in ("python", "platform", "machine", "cpu_count"):
        print(f"{key:<11} {system[key]}")
    print(f"{'config':<11} {cfg_path} ({'found' if Path(cfg_path).exists() else 'not found'})")
    return 0


def cmd_check_env(_: argparse.Namespace) -> int:
    results = run_checks()
    print(format_report(results, system_summary()))
    missing = [r for r in results if not r.ok and not r.dependency.optional]
    return 1 if missing else 0


def cmd_config_show(args: argparse.Namespace) -> int:
    cfg = api.load(args.config)
    resolved = {
        "source_file": str(cfg.source_file),
        "root": str(cfg.root),
        "project_name": cfg.project_name,
        "run_label": cfg.run_label,
        "seed": cfg.seed,
        "storage_backend": cfg.storage_backend,
        "use_synthetic": cfg.use_synthetic,
        "paths": {k: str(v) for k, v in vars(cfg.paths).items()},
    }
    print(json.dumps(resolved, indent=2))
    return 0


def cmd_init(args: argparse.Namespace) -> int:
    cfg = api.load(args.config)
    created = api.initialise_workspace(cfg)
    if created:
        print("Created:")
        for folder in created:
            print(f"  {folder}")
    else:
        print("All folders already exist — nothing to do.")
    return 0


def main(argv: list[str] | None = None) -> int:
    """Entry point registered in pyproject.toml. Returns the process exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "info":
            return cmd_info(args)
        if args.command == "check-env":
            return cmd_check_env(args)
        if args.command == "config" and args.config_command == "show":
            return cmd_config_show(args)
        if args.command == "init":
            return cmd_init(args)
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2
    parser.print_help()
    return 1


if __name__ == "__main__":  # allows `python -m segaudit.cli ...` as well
    sys.exit(main())
