"""Whole-slide image (WSI) reading, with geometry preserved.

Why this module exists
----------------------
A whole-slide image is a photograph of a glass slide at microscope
resolution: typically 50 000 x 50 000 pixels or more — far too big to load
at once. Scanners therefore store it as a **pyramid**: level 0 is full
resolution, level 1 is half the size, level 2 a quarter, and so on, and any
rectangle at any level can be read on its own. Alongside the pixels sits
the one number every later measurement depends on: **microns per pixel
(mpp)**, the physical size of one pixel. Nuclear area, cell density and
distance between cells are all `pixels x mpp`; get mpp wrong and every
pathology biomarker is wrong — exactly as voxel spacing is for scans.

Everyday analogy: an online map. You never download the whole planet; you
ask for a small tile at a chosen zoom level, and the map's scale bar tells
you how many metres a pixel covers. The pyramid is the zoom levels; mpp is
the scale bar.

Two backends, one interface
---------------------------
* :class:`OpenSlideBackend` uses OpenSlide (through ``openslide-python`` and
  the pip-installable ``openslide-bin`` binaries): the standard reader for
  vendor formats (Aperio SVS, Hamamatsu NDPI, Leica SCN, MIRAX, ...).
* :class:`TiffSlideBackend` uses ``tiffslide``, a pure-Python reader for
  tiled TIFF and SVS. It needs no native binary, so it is the fallback if
  OpenSlide cannot be installed on a machine.

Both expose the same :class:`SlideReader` interface, so pipeline code never
knows which one it got. :func:`open_slide` picks automatically.

Writing
-------
:func:`write_pyramidal_tiff` turns an RGB array into a tiled, multi-level
TIFF that both backends can open. It is how the synthetic slide is made, and
how tests prove the readers work with no download at all.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

import numpy as np

# Property keys. OpenSlide names them ``openslide.*``; tiffslide names its own
# ``tiffslide.*``. We look for both, then fall back to parsing the slide's
# description text (Aperio-style ``MPP = 0.5|AppMag = 20``), which is what
# generic TIFF readers leave unparsed.
_MPP_X = ("openslide.mpp-x", "tiffslide.mpp-x")
_MPP_Y = ("openslide.mpp-y", "tiffslide.mpp-y")
_MAG = ("openslide.objective-power", "tiffslide.objective-power")
_DESCRIPTION = ("openslide.comment", "tiff.ImageDescription", "tiffslide.comment")


class SlideError(RuntimeError):
    """Raised when a slide cannot be opened or read."""


@dataclass(frozen=True)
class SlideInfo:
    """The facts about a slide that the ``slides`` table records."""

    path: Path
    backend: str
    width_px: int
    height_px: int
    level_count: int
    level_dimensions: tuple[tuple[int, int], ...]
    mpp_x: float  # NaN if the file does not say
    mpp_y: float
    magnification: float  # NaN if the file does not say

    @property
    def has_mpp(self) -> bool:
        return not (math.isnan(self.mpp_x) or math.isnan(self.mpp_y))


@runtime_checkable
class SlideReader(Protocol):
    """What every slide backend must be able to do."""

    @property
    def info(self) -> SlideInfo: ...

    def read_region(self, x: int, y: int, level: int, width: int, height: int) -> np.ndarray:
        """Return an RGB uint8 array of shape (height, width, 3).

        ``x``/``y`` are **level-0** coordinates of the top-left corner (the
        convention both libraries use); ``width``/``height`` are in pixels
        *at the requested level*.
        """

    def thumbnail(self, max_size: int = 512) -> np.ndarray:
        """A small RGB overview whose longer side is at most ``max_size``."""

    def close(self) -> None: ...


def _float_prop(props, keys: tuple[str, ...]) -> float:
    """First parsable float among ``keys`` in ``props``; NaN if none."""
    for key in keys:
        value = props.get(key)
        if value is None:
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return float("nan")


def _from_description(props, field: str) -> float:
    """Parse ``field`` out of a description string.

    Two shapes are understood: Aperio-style ``...|MPP = 0.5|AppMag = 20`` and
    JSON ``{"MPP": 0.5, "AppMag": 20, ...}`` (what our own writer stores).
    """
    for key in _DESCRIPTION:
        text = props.get(key)
        if not text:
            continue
        text = str(text)
        if text.lstrip().startswith("{"):
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                payload = {}
            for k, v in payload.items():
                if str(k).lower() == field.lower():
                    try:
                        return float(v)
                    except (TypeError, ValueError):
                        return float("nan")
            continue
        for part in text.replace("\n", "|").split("|"):
            name, sep, value = part.partition("=")
            if sep and name.strip().lower() == field.lower():
                try:
                    return float(value.strip())
                except ValueError:
                    return float("nan")
    return float("nan")


def _geometry(props) -> tuple[float, float, float]:
    """(mpp_x, mpp_y, magnification) from properties, description as fallback."""
    mpp_x = _float_prop(props, _MPP_X)
    mpp_y = _float_prop(props, _MPP_Y)
    if math.isnan(mpp_x) or math.isnan(mpp_y):
        mpp = _from_description(props, "MPP")
        mpp_x = mpp if math.isnan(mpp_x) else mpp_x
        mpp_y = mpp if math.isnan(mpp_y) else mpp_y
    mag = _float_prop(props, _MAG)
    if math.isnan(mag):
        mag = _from_description(props, "AppMag")
    return mpp_x, mpp_y, mag


def _to_rgb(image) -> np.ndarray:
    """PIL image (RGBA from OpenSlide, RGB from tiffslide) -> RGB uint8 array."""
    return np.asarray(image.convert("RGB"), dtype=np.uint8)


class OpenSlideBackend:
    """Slide reading through OpenSlide."""

    name = "openslide"

    def __init__(self, path: str | Path) -> None:
        try:
            import openslide  # noqa: PLC0415 — imported lazily so the fallback works without it
        except Exception as exc:  # ImportError or a broken native library
            raise SlideError(f"OpenSlide is not available: {type(exc).__name__}: {exc}") from exc
        path = Path(path)
        try:
            self._slide = openslide.OpenSlide(str(path))
        except Exception as exc:
            raise SlideError(f"OpenSlide cannot open {path}: {type(exc).__name__}: {exc}") from exc
        props = self._slide.properties
        mpp_x, mpp_y, mag = _geometry(props)
        w, h = self._slide.dimensions
        self._info = SlideInfo(
            path=path,
            backend=self.name,
            width_px=int(w),
            height_px=int(h),
            level_count=int(self._slide.level_count),
            level_dimensions=tuple((int(a), int(b)) for a, b in self._slide.level_dimensions),
            mpp_x=mpp_x,
            mpp_y=mpp_y,
            magnification=mag,
        )

    @property
    def info(self) -> SlideInfo:
        return self._info

    def read_region(self, x: int, y: int, level: int, width: int, height: int) -> np.ndarray:
        return _to_rgb(self._slide.read_region((int(x), int(y)), int(level), (int(width), int(height))))

    def thumbnail(self, max_size: int = 512) -> np.ndarray:
        return _to_rgb(self._slide.get_thumbnail((max_size, max_size)))

    def close(self) -> None:
        self._slide.close()


class TiffSlideBackend:
    """Slide reading through tiffslide (pure Python)."""

    name = "tiffslide"

    def __init__(self, path: str | Path) -> None:
        try:
            import tiffslide  # noqa: PLC0415
        except Exception as exc:
            raise SlideError(f"tiffslide is not available: {type(exc).__name__}: {exc}") from exc
        path = Path(path)
        try:
            self._slide = tiffslide.TiffSlide(str(path))
        except Exception as exc:
            raise SlideError(f"tiffslide cannot open {path}: {type(exc).__name__}: {exc}") from exc
        props = self._slide.properties
        mpp_x, mpp_y, mag = _geometry(props)
        w, h = self._slide.dimensions
        self._info = SlideInfo(
            path=path,
            backend=self.name,
            width_px=int(w),
            height_px=int(h),
            level_count=int(self._slide.level_count),
            level_dimensions=tuple((int(a), int(b)) for a, b in self._slide.level_dimensions),
            mpp_x=mpp_x,
            mpp_y=mpp_y,
            magnification=mag,
        )

    @property
    def info(self) -> SlideInfo:
        return self._info

    def read_region(self, x: int, y: int, level: int, width: int, height: int) -> np.ndarray:
        return _to_rgb(self._slide.read_region((int(x), int(y)), int(level), (int(width), int(height))))

    def thumbnail(self, max_size: int = 512) -> np.ndarray:
        return _to_rgb(self._slide.get_thumbnail((max_size, max_size)))

    def close(self) -> None:
        self._slide.close()


BACKENDS = {"openslide": OpenSlideBackend, "tiffslide": TiffSlideBackend}


def open_slide(path: str | Path, backend: str = "auto") -> SlideReader:
    """Open a slide with the requested backend, or the first one that works.

    ``backend="auto"`` tries OpenSlide first (widest format support), then
    tiffslide. The chosen backend is recorded in ``reader.info.backend`` so a
    run table can say which library produced the pixels.
    """
    path = Path(path)
    if not path.exists():
        raise SlideError(f"Slide file not found: {path}")
    order = ("openslide", "tiffslide") if backend == "auto" else (backend,)
    errors: list[str] = []
    for name in order:
        try:
            cls = BACKENDS[name]
        except KeyError as exc:
            raise SlideError(f"Unknown backend {name!r}; known: {', '.join(BACKENDS)}") from exc
        try:
            return cls(path)
        except SlideError as exc:
            errors.append(str(exc))
    raise SlideError("No backend could open the slide:\n  " + "\n  ".join(errors))


def write_pyramidal_tiff(
    path: str | Path,
    image: np.ndarray,
    mpp: float,
    magnification: float | None = None,
    tile_size: int = 256,
    levels: int | None = None,
) -> Path:
    """Write an RGB uint8 array as a tiled, multi-level TIFF readable by both backends.

    Layout: one TIFF *page* per pyramid level, level 0 first, each tagged as a
    reduced-resolution image after the first. This is the layout OpenSlide's
    generic-TIFF driver and tiffslide both recognise as a pyramid (SubIFD
    pyramids are read by tiffslide only). Microns-per-pixel goes into the TIFF
    resolution tags (read by OpenSlide), into tifffile's JSON metadata and into
    an Aperio-style description (read by tiffslide), so both backends report
    the same mpp and magnification.

    The pyramid is built by halving until the longer side fits one tile, or
    ``levels`` levels are written.
    """
    import tifffile  # noqa: PLC0415 — the writer is only needed when creating slides

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    img = np.ascontiguousarray(image, dtype=np.uint8)
    if img.ndim != 3 or img.shape[2] != 3:
        raise SlideError("write_pyramidal_tiff expects an RGB array of shape (H, W, 3)")

    h, w = img.shape[:2]
    if levels is None:
        levels = 1
        while max(h, w) / (2**levels) > tile_size and levels < 8:
            levels += 1
        levels += 1  # include the level that fits in one tile

    px_per_cm = 10_000.0 / float(mpp)  # resolution tags are pixels per centimetre
    # Two descriptions are written on page 0: tifffile's JSON metadata (first
    # tag; OpenSlide and our fallback read it) and an Aperio-style string
    # (second tag; tiffslide's vendor detection reads it). Both carry MPP and
    # AppMag so every reader reports the same geometry.
    description = f"Aperio Image Library|SegAudit synthetic slide|MPP = {mpp:.6f}"
    metadata = {"MPP": float(mpp)}
    if magnification is not None:
        description += f"|AppMag = {magnification:g}"
        metadata["AppMag"] = float(magnification)

    with tifffile.TiffWriter(str(path), bigtiff=False) as tif:
        current = img
        for level in range(levels):
            tif.write(
                current,
                tile=(tile_size, tile_size),
                photometric="rgb",
                compression="deflate",
                resolution=(px_per_cm / (2**level), px_per_cm / (2**level)),
                resolutionunit="CENTIMETER",
                subfiletype=0 if level == 0 else 1,
                description=description if level == 0 else None,
                # Reduced pages get tifffile's default (empty) shaped metadata so
                # it recognises the pages as one series and stays quiet.
                metadata=metadata if level == 0 else {},
            )
            hh, ww = (current.shape[0] // 2) * 2, (current.shape[1] // 2) * 2
            if hh < 2 or ww < 2:
                break
            block = current[:hh, :ww].astype(np.uint16)
            current = (
                (block[0::2, 0::2] + block[1::2, 0::2] + block[0::2, 1::2] + block[1::2, 1::2]) // 4
            ).astype(np.uint8)
    return path
