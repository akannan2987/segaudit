"""Command line for SegAudit.

After ``pip install -e .`` a command called ``segaudit`` exists. Run
``segaudit --help`` to see the subcommands. Every subcommand is a few lines
that call :mod:`segaudit.api` and print the result — no logic lives here.

Commands
--------
``segaudit info``                     version, Python, platform, track, which config would load
``segaudit check-env``                import every dependency and report versions
``segaudit config show``              print the resolved configuration (paths made absolute)
``segaudit init``                     create the data/output/model folders from the config
``segaudit schemas [NAME]``           describe the table schemas both tracks agree on
``segaudit data phantom``             generate the track's synthetic dataset (no download)
``segaudit slide info PATH``          read a whole-slide image's geometry (setup check)

Every command that loads a configuration accepts ``--config/-c`` and
``--track/-t`` (``radiology`` or ``pathology``), the latter overriding the
YAML for one run.

Uses only the standard library's ``argparse`` so the command works before any
optional package is installed.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

from segaudit import api, schemas
from segaudit.config import TRACKS, ConfigError, default_config_path
from segaudit.envcheck import format_report, run_checks, system_summary


def _add_config_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--config",
        "-c",
        type=Path,
        default=None,
        help="YAML configuration file (default: configs/default.yaml in the current folder)",
    )
    parser.add_argument(
        "--track",
        "-t",
        choices=TRACKS,
        default=None,
        help="override the configuration's track for this run",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="segaudit",
        description="Quality control and triage for medical image segmentation — scans and slides.",
    )
    parser.add_argument("--version", action="version", version=f"segaudit {api.version()}")
    sub = parser.add_subparsers(dest="command", required=True)

    p_info = sub.add_parser("info", help="show version, Python, platform and track")
    _add_config_args(p_info)

    sub.add_parser("check-env", help="verify that every dependency imports")

    p_cfg = sub.add_parser("config", help="inspect configuration")
    cfg_sub = p_cfg.add_subparsers(dest="config_command", required=True)
    p_show = cfg_sub.add_parser("show", help="print the resolved configuration as JSON")
    _add_config_args(p_show)

    p_init = sub.add_parser("init", help="create the folders named in the configuration")
    _add_config_args(p_init)

    p_schemas = sub.add_parser("schemas", help="describe the table schemas")
    p_schemas.add_argument("name", nargs="?", help="one table name (default: list all)")

    p_data = sub.add_parser("data", help="datasets: synthetic generation (downloads arrive with Phase 1 / P1)")
    data_sub = p_data.add_subparsers(dest="data_command", required=True)
    p_phantom = data_sub.add_parser("phantom", help="generate the track's synthetic dataset")
    _add_config_args(p_phantom)

    p_slide = sub.add_parser("slide", help="whole-slide image utilities")
    slide_sub = p_slide.add_subparsers(dest="slide_command", required=True)
    p_sinfo = slide_sub.add_parser("info", help="print a slide's dimensions, levels, mpp and magnification")
    p_sinfo.add_argument("path", type=Path, help="slide file (.svs, .tif, .ndpi, ...)")
    p_sinfo.add_argument(
        "--backend", choices=("auto", "openslide", "tiffslide"), default="auto", help="reader to use"
    )

    return parser


# --- subcommand implementations -------------------------------------------


def cmd_info(args: argparse.Namespace) -> int:
    system = system_summary()
    cfg_path = args.config or default_config_path()
    print(f"segaudit {api.version()}")
    for key in ("python", "platform", "machine", "cpu_count"):
        print(f"{key:<11} {system[key]}")
    found = Path(cfg_path).exists()
    print(f"{'config':<11} {cfg_path} ({'found' if found else 'not found'})")
    if found:
        try:
            print(f"{'track':<11} {api.load(cfg_path, track=args.track).track}")
        except ConfigError as exc:
            print(f"{'track':<11} (configuration error: {exc})")
    return 0


def cmd_check_env(_: argparse.Namespace) -> int:
    results = run_checks()
    print(format_report(results, system_summary()))
    missing = [r for r in results if not r.ok and not r.dependency.optional]
    return 1 if missing else 0


def cmd_config_show(args: argparse.Namespace) -> int:
    cfg = api.load(args.config, track=args.track)
    resolved = {
        "source_file": str(cfg.source_file),
        "root": str(cfg.root),
        "project_name": cfg.project_name,
        "run_label": cfg.run_label,
        "track": cfg.track,
        "seed": cfg.seed,
        "storage_backend": cfg.storage_backend,
        "use_synthetic": cfg.use_synthetic,
        "paths": {k: str(v) for k, v in vars(cfg.paths).items()},
    }
    print(json.dumps(resolved, indent=2))
    return 0


def cmd_init(args: argparse.Namespace) -> int:
    cfg = api.load(args.config, track=args.track)
    created = api.initialise_workspace(cfg)
    if created:
        print("Created:")
        for folder in created:
            print(f"  {folder}")
    else:
        print("All folders already exist — nothing to do.")
    return 0


def cmd_schemas(args: argparse.Namespace) -> int:
    names = [args.name] if args.name else list(schemas.REGISTRY)
    try:
        print("\n\n".join(schemas.describe(n) for n in names))
    except schemas.SchemaError as exc:
        print(f"Schema error: {exc}", file=sys.stderr)
        return 2
    return 0


def cmd_data_phantom(args: argparse.Namespace) -> int:
    cfg = api.load(args.config, track=args.track)
    api.initialise_workspace(cfg)
    try:
        summary = api.generate_synthetic(cfg)
    except NotImplementedError as exc:
        print(f"Not available yet: {exc}", file=sys.stderr)
        return 3
    print(f"Synthetic dataset written for track '{cfg.track}':")
    for key, value in summary.items():
        print(f"  {key:<10} {value}")
    return 0


def cmd_slide_info(args: argparse.Namespace) -> int:
    from segaudit.pathology.io_wsi import SlideError  # noqa: PLC0415

    try:
        info = api.slide_info(args.path, backend=args.backend)
    except SlideError as exc:
        print(f"Slide error: {exc}", file=sys.stderr)
        return 4

    def fmt(v: float) -> str:
        return "unknown" if isinstance(v, float) and math.isnan(v) else f"{v:g}"

    print(f"{'file':<14} {info['path']}")
    print(f"{'backend':<14} {info['backend']}")
    print(f"{'size (px)':<14} {info['width_px']} x {info['height_px']}")
    print(f"{'levels':<14} {info['level_count']}: " + ", ".join(f"{w}x{h}" for w, h in info["level_dimensions"]))
    print(f"{'mpp (x, y)':<14} {fmt(info['mpp_x'])}, {fmt(info['mpp_y'])}")
    print(f"{'magnification':<14} {fmt(info['magnification'])}")
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
        if args.command == "schemas":
            return cmd_schemas(args)
        if args.command == "data" and args.data_command == "phantom":
            return cmd_data_phantom(args)
        if args.command == "slide" and args.slide_command == "info":
            return cmd_slide_info(args)
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2
    parser.print_help()
    return 1


if __name__ == "__main__":  # allows `python -m segaudit.cli ...` as well
    sys.exit(main())
