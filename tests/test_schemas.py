"""Tests for the table schema registry."""

from __future__ import annotations

import pandas as pd
import pytest

from segaudit import schemas


def test_registry_covers_both_tracks_and_shared_tables():
    tracks = {s.track for s in schemas.REGISTRY.values()}
    assert tracks == {"radiology", "pathology", "shared"}
    assert {"cases", "slides", "tiles", "cells", "case_metrics", "qc_scores", "review_ledger", "runs"} <= set(
        schemas.REGISTRY
    )


def test_shared_tables_key_on_unit_id_and_unit_kind():
    for name in ("case_metrics", "qc_scores", "review_ledger"):
        cols = schemas.schema(name).required
        assert "unit_id" in cols and "unit_kind" in cols


def test_check_passes_with_extra_columns():
    df = pd.DataFrame({c: [1] for c in schemas.schema("qc_scores").required} | {"extra": [1]})
    assert schemas.check("qc_scores", df) is df


def test_check_raises_naming_the_missing_columns():
    df = pd.DataFrame({"unit_id": ["a"], "run_label": ["x"]})
    with pytest.raises(schemas.SchemaError, match="unit_kind"):
        schemas.check("qc_scores", df)


def test_unknown_table_is_an_error():
    with pytest.raises(schemas.SchemaError, match="No schema"):
        schemas.schema("nothing")


def test_describe_is_human_readable():
    text = schemas.describe("cells")
    assert "cells" in text and "class_name" in text and "tile_id" in text
