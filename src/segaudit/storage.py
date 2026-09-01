"""Storage layer for SegAudit result tables.

Why this module exists
----------------------
Every phase produces tables: per-case metrics, uncertainty scores, quality
flags, review decisions. If each phase wrote its own CSV wherever it liked,
the review app, the report drafter and any future service would all have to
know those private details. Instead, all tables go through one small
interface, :class:`Storage`, with one implementation today
(:class:`LocalParquetStorage`) and room for others (a database server, cloud
object storage) later. The pipeline code only ever calls the interface.

Everyday analogy: the pipeline hands finished paperwork to a filing clerk and
says "file this under *case_metrics*". It does not care whether the clerk uses
a cabinet in the office or a warehouse across town — and if the clerk moves to
the warehouse next year, the paperwork does not change.

Concepts
--------
* **Parquet** — a compact file format for tables that remembers column types
  (a date stays a date). Faster and safer than CSV for anything numeric.
* **DuckDB** — an analytics database that runs inside the Python process and
  can query Parquet files directly with SQL. No server, no account.
* **Ledger** — an append-only table: rows are added, never edited. Review
  decisions and pipeline runs are ledgers, so the history is never lost.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Protocol, runtime_checkable

import duckdb
import pandas as pd

from segaudit.config import Config

# Table names are used as file names, so keep them boring and safe.
_TABLE_NAME = re.compile(r"^[a-z][a-z0-9_]*$")


class StorageError(RuntimeError):
    """Raised for invalid table names or missing tables."""


def validate_table_name(name: str) -> str:
    """Accept ``case_metrics``; reject ``../secrets`` and friends."""
    if not _TABLE_NAME.match(name):
        raise StorageError(
            f"Invalid table name {name!r}: use lowercase letters, digits and underscores, "
            "starting with a letter."
        )
    return name


@runtime_checkable
class Storage(Protocol):
    """What every storage backend must be able to do.

    A ``Protocol`` is Python's way of saying "anything with these methods
    counts" — no inheritance required. Tests use this to swap in fakes.
    """

    def write_table(self, name: str, table: pd.DataFrame) -> None:
        """Replace ``name`` with ``table`` (create if absent)."""

    def append_rows(self, name: str, rows: pd.DataFrame) -> None:
        """Add rows to ``name``, creating it if absent (ledger behaviour)."""

    def read_table(self, name: str) -> pd.DataFrame:
        """Return the whole table."""

    def exists(self, name: str) -> bool:
        """True if ``name`` has been written."""

    def list_tables(self) -> list[str]:
        """Names of all tables, sorted."""

    def query(self, sql: str) -> pd.DataFrame:
        """Run read-only SQL where each table name is usable as a relation."""


class LocalParquetStorage:
    """Tables as ``<root>/<name>.parquet`` files, queried through DuckDB.

    Parameters
    ----------
    root:
        Folder in which the Parquet files live. Created on first write.
    """

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).expanduser().resolve()

    # -- helpers -----------------------------------------------------------
    def _path(self, name: str) -> Path:
        return self.root / f"{validate_table_name(name)}.parquet"

    # -- Storage interface -------------------------------------------------
    def write_table(self, name: str, table: pd.DataFrame) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        # index=False: the row index is an artefact of pandas, not data.
        table.to_parquet(self._path(name), index=False)

    def append_rows(self, name: str, rows: pd.DataFrame) -> None:
        if self.exists(name):
            existing = self.read_table(name)
            combined = pd.concat([existing, rows], ignore_index=True)
        else:
            combined = rows.reset_index(drop=True)
        self.write_table(name, combined)

    def read_table(self, name: str) -> pd.DataFrame:
        path = self._path(name)
        if not path.exists():
            raise StorageError(f"Table {name!r} not found under {self.root}")
        return pd.read_parquet(path)

    def exists(self, name: str) -> bool:
        return self._path(name).exists()

    def list_tables(self) -> list[str]:
        if not self.root.exists():
            return []
        return sorted(p.stem for p in self.root.glob("*.parquet"))

    def query(self, sql: str) -> pd.DataFrame:
        """Run SQL against the Parquet files.

        Each table is registered as a DuckDB *view* so ``SELECT * FROM
        case_metrics`` just works. The connection is in-memory and read-only
        with respect to the files: SQL here can never modify a Parquet file.
        """
        con = duckdb.connect(database=":memory:")
        try:
            for name in self.list_tables():
                # as_posix(): DuckDB wants forward slashes even on Windows.
                con.execute(
                    f"CREATE VIEW {name} AS SELECT * FROM read_parquet('{self._path(name).as_posix()}')"
                )
            return con.execute(sql).df()
        finally:
            con.close()


def open_storage(cfg: Config) -> Storage:
    """Build the storage backend named in the configuration.

    Today only ``local_parquet`` exists. Adding a backend means adding a class
    above and one ``elif`` here — the pipeline does not change.
    """
    backend = cfg.storage_backend
    if backend == "local_parquet":
        return LocalParquetStorage(cfg.paths.outputs / "tables")
    raise StorageError(f"Unknown storage backend {backend!r} (known: local_parquet)")
