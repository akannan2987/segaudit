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
``segaudit data download``            fetch, verify and extract the track's public dataset
``segaudit data inventory``           walk the dataset into its tables (cases + qa_issues)
``segaudit data convert-dicom``       stack a DICOM series into one NIfTI file
``segaudit sql [SQL | -f FILE]``      read-only SQL over the run's tables; interactive if neither
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

    p_data = sub.add_parser("data", help="datasets: download, synthetic generation, inventory, conversion")
    data_sub = p_data.add_subparsers(dest="data_command", required=True)
    p_phantom = data_sub.add_parser("phantom", help="generate the track's synthetic dataset")
    _add_config_args(p_phantom)
    p_dl = data_sub.add_parser("download", help="fetch, verify and extract the public dataset (idempotent)")
    _add_config_args(p_dl)
    p_inv = data_sub.add_parser("inventory", help="walk the dataset into its tables, running input QA")
    _add_config_args(p_inv)
    p_dcm = data_sub.add_parser("convert-dicom", help="stack a DICOM series folder into one NIfTI file")
    p_dcm.add_argument("folder", type=Path, help="folder containing the DICOM slices")
    p_dcm.add_argument("output", type=Path, help="output .nii.gz path")
    p_dcm.add_argument("--series", default=None, help="series id if the folder holds several")

    p_sql = sub.add_parser("sql", help="read-only SQL over the run's tables")
    _add_config_args(p_sql)
    p_sql.add_argument("statement", nargs="?", default=None, help="one SQL statement (quote it)")
    p_sql.add_argument("--file", "-f", type=Path, default=None, help="read the statement from a .sql file")
    p_sql.add_argument("--csv", type=Path, default=None, help="also write the result to this CSV file")

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


def _print_summary(title: str, summary: dict) -> None:
    print(title)
    width = max(len(k) for k in summary) + 2
    for key, value in summary.items():
        print(f"  {key:<{width}}{value}")


def cmd_data_phantom(args: argparse.Namespace) -> int:
    cfg = api.load(args.config, track=args.track)
    api.initialise_workspace(cfg)
    api.record_run(cfg, "data phantom")
    summary = api.generate_synthetic(cfg)
    _print_summary(f"Synthetic dataset written for track '{cfg.track}':", summary)
    if cfg.is_radiology:
        print("Next: `segaudit data inventory` with the same config to build the cases table.")
    return 0


def cmd_data_download(args: argparse.Namespace) -> int:
    from segaudit.radiology.dataset import DatasetError  # noqa: PLC0415

    cfg = api.load(args.config, track=args.track)
    api.initialise_workspace(cfg)

    def progress(done: int, total: int) -> None:
        pct = f"{100 * done / total:5.1f}%" if total else "   ?"
        print(f"\r  downloading {done / 1e6:8.1f} MB {pct}", end="", flush=True)

    try:
        summary = api.download_dataset(cfg, progress=progress)
    except NotImplementedError as exc:
        print(f"Not available yet: {exc}", file=sys.stderr)
        return 3
    except DatasetError as exc:
        print(f"\nDataset error: {exc}", file=sys.stderr)
        return 5
    except OSError as exc:  # URLError/HTTPError are OSErrors: no network, proxy, 403, DNS
        print(f"\nDownload failed: {exc}\nCheck your connection or proxy, then run the same command again — "
              "a partial download resumes where it stopped.", file=sys.stderr)
        return 5
    print()
    _print_summary("Dataset ready:" if not summary.get("skipped") else "Dataset already present:", summary)
    return 0


def cmd_data_inventory(args: argparse.Namespace) -> int:
    from segaudit.radiology.dataset import DatasetError  # noqa: PLC0415

    cfg = api.load(args.config, track=args.track)
    api.initialise_workspace(cfg)
    try:
        api.record_run(cfg, "data inventory")
        summary = api.build_inventory(cfg)
    except NotImplementedError as exc:
        print(f"Not available yet: {exc}", file=sys.stderr)
        return 3
    except DatasetError as exc:
        print(f"Dataset error: {exc}", file=sys.stderr)
        return 5
    _print_summary("Inventory written:", summary)
    if summary.get("n_qa_errors"):
        print(f"  {summary['n_qa_errors']} case(s) failed input QA — see: segaudit sql \"SELECT * FROM qa_issues WHERE severity='error'\"")
    return 0


def cmd_data_convert_dicom(args: argparse.Namespace) -> int:
    from segaudit.radiology.dicom import DicomError  # noqa: PLC0415

    try:
        summary = api.convert_dicom_series(args.folder, args.output, args.series)
    except DicomError as exc:
        print(f"DICOM error: {exc}", file=sys.stderr)
        return 6
    _print_summary("Converted:", summary)
    return 0


def cmd_sql(args: argparse.Namespace) -> int:
    import duckdb  # noqa: PLC0415
    import pandas as pd  # noqa: PLC0415

    cfg = api.load(args.config, track=args.track)
    if args.statement and args.file:
        print("Give either a statement or --file, not both.", file=sys.stderr)
        return 2
    statement = args.file.read_text(encoding="utf-8") if args.file else args.statement

    def run(sql: str) -> int:
        try:
            frame = api.query(cfg, sql)
        except duckdb.Error as exc:
            print(f"SQL error: {exc}", file=sys.stderr)
            return 7
        with pd.option_context("display.max_columns", None, "display.width", 160, "display.max_rows", 200):
            print(frame.to_string(index=False) if len(frame) else "(no rows)")
        if args.csv:
            frame.to_csv(args.csv, index=False)
            print(f"wrote {args.csv}")
        return 0

    if statement:
        return run(statement)

    tables = api.storage_for(cfg).list_tables()
    print(f"SegAudit SQL console — track {cfg.track}, run '{cfg.run_label}'. Read-only.")
    print("Tables: " + (", ".join(tables) if tables else "(none yet)"))
    print("Type a statement (multi-line allowed; end with ';'), or 'quit'.")
    buffer: list[str] = []
    while True:
        try:
            line = input("sql> " if not buffer else "...> ")
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not buffer and line.strip().lower() in ("quit", "exit", "\\q"):
            return 0
        buffer.append(line)
        if line.rstrip().endswith(";"):
            run("\n".join(buffer).rstrip(";"))
            buffer = []


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
        if args.command == "data" and args.data_command == "download":
            return cmd_data_download(args)
        if args.command == "data" and args.data_command == "inventory":
            return cmd_data_inventory(args)
        if args.command == "data" and args.data_command == "convert-dicom":
            return cmd_data_convert_dicom(args)
        if args.command == "sql":
            return cmd_sql(args)
        if args.command == "slide" and args.slide_command == "info":
            return cmd_slide_info(args)
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2
    parser.print_help()
    return 1


if __name__ == "__main__":  # allows `python -m segaudit.cli ...` as well
    sys.exit(main())
