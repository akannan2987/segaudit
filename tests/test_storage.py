"""Tests for segaudit.storage."""

from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd
import pytest

from segaudit.config import load_config
from segaudit.storage import LocalParquetStorage, Storage, StorageError, open_storage


@pytest.fixture
def store(tmp_path: Path) -> LocalParquetStorage:
    return LocalParquetStorage(tmp_path / "tables")


def _cases() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "case_id": ["hip_001", "hip_002", "hip_003"],
            "dice": [0.91, 0.42, 0.88],
            "flagged": [False, True, False],
        }
    )


def test_local_storage_satisfies_the_protocol(store: LocalParquetStorage):
    assert isinstance(store, Storage)


def test_write_then_read_round_trips_types(store: LocalParquetStorage):
    store.write_table("case_metrics", _cases())
    back = store.read_table("case_metrics")
    pd.testing.assert_frame_equal(back, _cases())
    assert back["flagged"].dtype == bool  # Parquet keeps the boolean, CSV would not


def test_exists_and_list_tables(store: LocalParquetStorage):
    assert store.list_tables() == []
    assert not store.exists("case_metrics")
    store.write_table("case_metrics", _cases())
    store.write_table("runs", pd.DataFrame({"run_id": ["r1"]}))
    assert store.exists("case_metrics")
    assert store.list_tables() == ["case_metrics", "runs"]


def test_append_rows_behaves_like_a_ledger(store: LocalParquetStorage):
    first = pd.DataFrame({"case_id": ["hip_001"], "decision": ["accept"]})
    second = pd.DataFrame({"case_id": ["hip_002"], "decision": ["flag"]})
    store.append_rows("review_ledger", first)
    store.append_rows("review_ledger", second)
    ledger = store.read_table("review_ledger")
    assert len(ledger) == 2
    assert list(ledger["decision"]) == ["accept", "flag"]


def test_query_runs_sql_over_tables(store: LocalParquetStorage):
    store.write_table("case_metrics", _cases())
    worst = store.query("SELECT case_id FROM case_metrics ORDER BY dice ASC LIMIT 1")
    assert list(worst["case_id"]) == ["hip_002"]


def test_query_cannot_change_files(store: LocalParquetStorage):
    store.write_table("case_metrics", _cases())
    # A view over a Parquet file is not writable; DuckDB refuses at bind time.
    with pytest.raises(duckdb.BinderException):
        store.query("DELETE FROM case_metrics")
    assert len(store.read_table("case_metrics")) == 3


def test_reading_missing_table_is_a_clear_error(store: LocalParquetStorage):
    with pytest.raises(StorageError, match="not found"):
        store.read_table("nothing_here")


@pytest.mark.parametrize("bad", ["../escape", "Case Metrics", "1abc", "case-metrics", ""])
def test_invalid_table_names_are_rejected(store: LocalParquetStorage, bad: str):
    with pytest.raises(StorageError, match="Invalid table name"):
        store.write_table(bad, _cases())


def test_open_storage_uses_outputs_folder_from_config(config_file: Path):
    cfg = load_config(config_file)
    storage = open_storage(cfg)
    assert isinstance(storage, LocalParquetStorage)
    assert storage.root == (cfg.paths.outputs / "tables").resolve()
