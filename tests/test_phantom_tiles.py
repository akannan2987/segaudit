"""Tests for the synthetic H&E-like tile generator."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import yaml

from segaudit import api
from segaudit.config import load_config
from segaudit.pathology import phantom_tiles as pt


def test_make_tile_is_deterministic():
    a = pt.make_tile(42, pt.TileSpec())
    b = pt.make_tile(42, pt.TileSpec())
    assert np.array_equal(a.image, b.image)
    assert np.array_equal(a.instances, b.instances)
    assert a.cells.equals(b.cells)
    c = pt.make_tile(43, pt.TileSpec())
    assert not np.array_equal(a.instances, c.instances)


def test_tile_shapes_dtypes_and_label_consistency():
    t = pt.make_tile(1, pt.TileSpec(size=128))
    assert t.image.shape == (128, 128, 3) and t.image.dtype == np.uint8
    assert t.instances.shape == (128, 128) and t.instances.dtype == np.uint16
    assert t.classes.shape == (128, 128) and t.classes.dtype == np.uint8
    # Every instance has exactly one class, and background matches.
    assert np.array_equal(t.instances == 0, t.classes == 0)
    n = int(t.instances.max())
    assert set(np.unique(t.instances)) == set(range(n + 1))
    assert len(t.cells) == n
    for _, row in t.cells.iterrows():
        region = t.instances == row.cell_id
        assert int(region.sum()) == row.area_px
        assert set(np.unique(t.classes[region])) == {row.class_id}


@pytest.mark.parametrize("pattern", pt.PATTERNS)
def test_every_pattern_draws_all_three_phenotypes(pattern):
    t = pt.make_tile(5, pt.TileSpec(pattern=pattern))
    assert set(t.cells.class_name) == {"tumour", "lymphocyte", "stroma"}


def test_spatial_patterns_differ_in_lymphocyte_to_tumour_distance():
    """Infiltrating tiles put lymphocytes near tumour; clustered tiles keep them away."""

    def mean_nn(t):
        tum = t.cells[t.cells.class_name == "tumour"][["cx", "cy"]].to_numpy()
        lym = t.cells[t.cells.class_name == "lymphocyte"][["cx", "cy"]].to_numpy()
        d = np.sqrt(((lym[:, None, :] - tum[None, :, :]) ** 2).sum(-1))
        return float(d.min(axis=1).mean())

    seeds = range(3)
    clustered = np.mean([mean_nn(pt.make_tile(s, pt.TileSpec(pattern="clustered"))) for s in seeds])
    infiltrating = np.mean([mean_nn(pt.make_tile(s, pt.TileSpec(pattern="infiltrating"))) for s in seeds])
    assert infiltrating < clustered


def test_unknown_pattern_is_rejected():
    with pytest.raises(ValueError, match="pattern"):
        pt.TileSpec(pattern="random")


def test_each_label_failure_mode_changes_what_it_claims():
    t = pt.make_tile(9, pt.TileSpec())
    rng = np.random.default_rng(0)
    n0 = int(t.instances.max())
    fg0 = int((t.instances > 0).sum())

    inst, cls = pt.corrupt_labels(t.instances, t.classes, "missing_nuclei", rng)
    assert int(inst.max()) < n0 and np.array_equal(inst == 0, cls == 0)

    inst, _ = pt.corrupt_labels(t.instances, t.classes, "merged_nuclei", rng)
    assert int(inst.max()) < n0 and int((inst > 0).sum()) == fg0  # same pixels, fewer objects

    inst, _ = pt.corrupt_labels(t.instances, t.classes, "false_positives", rng)
    assert int(inst.max()) > n0 and int((inst > 0).sum()) > fg0

    inst, _ = pt.corrupt_labels(t.instances, t.classes, "shifted_boundaries", rng)
    assert int((inst > 0).sum()) != fg0


def test_unknown_failure_mode_is_rejected():
    t = pt.make_tile(9, pt.TileSpec())
    with pytest.raises(ValueError):
        pt.corrupt_labels(t.instances, t.classes, "explode", np.random.default_rng(0))


@pytest.mark.parametrize("mode", pt.IMAGE_ARTEFACTS)
def test_artefacts_change_the_image_but_not_its_shape(mode):
    t = pt.make_tile(3, pt.TileSpec(size=96))
    out = pt.apply_artefact(t.image, mode, np.random.default_rng(1))
    assert out.shape == t.image.shape and out.dtype == np.uint8
    assert not np.array_equal(out, t.image)


def test_generate_dataset_writes_files_tables_and_manifest(repo_root: Path, minimal_config):
    data = {
        **minimal_config,
        "track": "pathology",
        "pathology": {
            "synthetic": {"n_slides": 2, "tiles_per_slide": 3, "grid": 2, "tile_size": 64, "mpp": 0.5, "magnification": 20}
        },
    }
    path = repo_root / "configs" / "p.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    cfg = load_config(path)
    api.initialise_workspace(cfg)

    summary = api.generate_synthetic(cfg)
    assert summary["n_slides"] == 2 and summary["n_tiles"] == 6 and summary["n_cells"] > 0

    root = cfg.paths.data_raw / "synthetic_tiles"
    assert (root / "dataset.json").exists()
    assert len(list((root / "imagesTr").glob("*.png"))) == 6
    assert len(list((root / "labelsTr").glob("*_inst.png"))) == 6
    assert len(list((root / "slides").glob("*.tif"))) == 2

    store = api.storage_for(cfg)
    assert set(store.list_tables()) >= {"slides", "tiles", "cells"}
    tiles = store.read_table("tiles")
    assert set(tiles.pattern) <= set(pt.PATTERNS)
    cells = store.read_table("cells")
    assert set(cells.tile_id) == set(tiles.tile_id)
    # Rerunning is idempotent: same tables, same files.
    again = api.generate_synthetic(cfg)
    assert again == summary
