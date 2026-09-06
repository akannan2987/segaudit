"""Tests for whole-slide reading through both backends, with no download."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from segaudit.pathology import io_wsi


@pytest.fixture(scope="module")
def synthetic_slide(tmp_path_factory) -> tuple[Path, np.ndarray]:
    rng = np.random.default_rng(0)
    img = rng.integers(0, 255, (700, 900, 3), dtype=np.uint8)
    path = tmp_path_factory.mktemp("wsi") / "synthetic.tif"
    io_wsi.write_pyramidal_tiff(path, img, mpp=0.5, magnification=20, tile_size=128)
    return path, img


@pytest.mark.parametrize("backend", ["openslide", "tiffslide"])
def test_each_backend_reads_geometry_and_pixels(synthetic_slide, backend):
    path, img = synthetic_slide
    reader = io_wsi.open_slide(path, backend=backend)
    try:
        info = reader.info
        assert isinstance(reader, io_wsi.SlideReader)
        assert info.backend == backend
        assert (info.width_px, info.height_px) == (900, 700)
        assert info.level_count >= 3
        assert info.level_dimensions[0] == (900, 700)
        assert info.has_mpp and info.mpp_x == pytest.approx(0.5) and info.mpp_y == pytest.approx(0.5)
        assert info.magnification == pytest.approx(20)
        region = reader.read_region(100, 50, 0, 64, 32)
        assert region.shape == (32, 64, 3) and region.dtype == np.uint8
        assert np.array_equal(region, img[50:82, 100:164])
        thumb = reader.thumbnail(128)
        assert max(thumb.shape[:2]) <= 128
    finally:
        reader.close()


def test_both_backends_agree_on_every_level(synthetic_slide):
    path, _ = synthetic_slide
    a = io_wsi.open_slide(path, "openslide")
    b = io_wsi.open_slide(path, "tiffslide")
    try:
        assert a.info.level_dimensions == b.info.level_dimensions
        for level in range(a.info.level_count):
            ra = a.read_region(0, 0, level, 32, 32)
            rb = b.read_region(0, 0, level, 32, 32)
            assert np.array_equal(ra, rb), f"level {level} differs between backends"
    finally:
        a.close()
        b.close()


def test_auto_picks_openslide_first(synthetic_slide):
    path, _ = synthetic_slide
    reader = io_wsi.open_slide(path)
    assert reader.info.backend == "openslide"
    reader.close()


def test_missing_file_and_unknown_backend_are_clear_errors(tmp_path: Path, synthetic_slide):
    with pytest.raises(io_wsi.SlideError, match="not found"):
        io_wsi.open_slide(tmp_path / "nope.svs")
    with pytest.raises(io_wsi.SlideError, match="Unknown backend"):
        io_wsi.open_slide(synthetic_slide[0], backend="magic")


def test_writer_rejects_non_rgb(tmp_path: Path):
    with pytest.raises(io_wsi.SlideError, match="RGB"):
        io_wsi.write_pyramidal_tiff(tmp_path / "x.tif", np.zeros((10, 10), np.uint8), mpp=0.5)


def test_description_parser_handles_aperio_and_json_styles():
    aperio = {"openslide.comment": "Aperio Image Library|MPP = 0.2520|AppMag = 40"}
    assert io_wsi._from_description(aperio, "MPP") == pytest.approx(0.252)
    assert io_wsi._from_description(aperio, "AppMag") == pytest.approx(40)
    js = {"tiff.ImageDescription": '{"shape": [1, 2, 3], "MPP": 0.5, "AppMag": 20}'}
    assert io_wsi._from_description(js, "MPP") == pytest.approx(0.5)
    assert np.isnan(io_wsi._from_description({}, "MPP"))
