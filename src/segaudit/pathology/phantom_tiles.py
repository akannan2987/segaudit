"""Synthetic H&E-like tiles — the pathology twin of the MRI phantom.

Why this module exists
----------------------
Real slides are gigabytes, licensed, and slow to download. Tests, continuous
integration and a first walkthrough need something that runs in seconds with
nothing fetched. This generator draws small **tiles** that look enough like
haematoxylin-and-eosin (H&E) stained tissue to exercise every pathology code
path — nuclei with instance labels and phenotype classes, controllable
spatial arrangements, and deliberate failure modes — while being fully
seeded, so the same configuration always produces the same pixels.

Everyday analogy: a crash-test dummy. Not a person, but shaped enough like
one that the seatbelt can be tested; and unlike a person, you can order one
with exactly the injury you want to study.

What a tile contains
--------------------
* **Image** — RGB, eosin-pink background with faint fibre texture (stroma),
  nuclei drawn as dark blue–purple ellipses (haematoxylin).
* **Instance label** — an integer image: 0 background, 1..N one value per
  nucleus. This is what an instance-segmentation model is trained to
  reproduce.
* **Class label** — an integer image with the phenotype of each nucleus:
  1 tumour (large, irregular, pale-centred), 2 lymphocyte (small, round,
  dark), 3 stroma (elongated, sparse).
* **Cells table rows** — centroid, area and class per nucleus.

Spatial patterns (the thing spatial statistics later have to detect):
* ``clustered``   — tumour nuclei packed in one or two clusters, lymphocytes
  scattered elsewhere (a tumour nest with excluded immune cells).
* ``dispersed``   — everything uniformly scattered.
* ``infiltrating`` — a tumour cluster with lymphocytes concentrated at and
  inside its boundary (an "inflamed" tumour). The tumour–immune interaction
  score of a later phase should rank this pattern highest.

Failure modes — how to make a *wrong* answer on purpose. Two kinds:
* **Label corruption** (``corrupt_labels``): missing nuclei, merged
  neighbours, false positives, shifted boundaries. These simulate a model's
  mistakes so the quality-control layer has something to catch.
* **Image artefacts** (``apply_artefact``): blur (out of focus), stain shift
  (a different lab), a dark fold band, a pen-mark stroke. These simulate the
  acquisition problems slide-level QC must flag.

Output layout (mirrors the radiology dataset layout so downstream code treats
both sources the same way)::

    data/raw/synthetic_tiles/
        imagesTr/          tile_<slide>_<n>.png       RGB image
        labelsTr/          tile_<slide>_<n>_inst.png  uint16 instance labels
                           tile_<slide>_<n>_cls.png   uint8 class labels
        slides/            <slide>.tif                assembled pyramidal slide
        dataset.json       what is in here

Plus three tables written through storage: ``slides``, ``tiles``, ``cells``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from PIL import Image

from segaudit import schemas
from segaudit.config import Config
from segaudit.pathology.io_wsi import write_pyramidal_tiff
from segaudit.storage import Storage

CLASS_NAMES = {1: "tumour", 2: "lymphocyte", 3: "stroma"}
PATTERNS = ("clustered", "dispersed", "infiltrating")
LABEL_FAILURE_MODES = ("missing_nuclei", "merged_nuclei", "false_positives", "shifted_boundaries")
IMAGE_ARTEFACTS = ("blur", "stain_shift", "fold", "pen_mark")

# H&E-like colours, RGB 0-255. Eosin stains cytoplasm/stroma pink; haematoxylin
# stains nuclei blue-purple. These are caricatures, chosen to look right, not
# measured from real slides.
_EOSIN_BG = np.array([232, 196, 210], dtype=np.float32)
_FIBRE = np.array([214, 160, 188], dtype=np.float32)
_NUCLEUS = {
    1: np.array([96, 62, 140], dtype=np.float32),  # tumour: purple, paler centre
    2: np.array([48, 40, 110], dtype=np.float32),  # lymphocyte: dark, compact
    3: np.array([110, 80, 150], dtype=np.float32),  # stroma: muted, elongated
}


@dataclass(frozen=True)
class TileSpec:
    """Everything that decides what one tile looks like."""

    size: int = 256
    mpp: float = 0.5
    n_tumour: int = 45
    n_lymphocyte: int = 35
    n_stroma: int = 20
    pattern: str = "clustered"

    def __post_init__(self) -> None:
        if self.pattern not in PATTERNS:
            raise ValueError(f"pattern must be one of {PATTERNS}, got {self.pattern!r}")


@dataclass
class Tile:
    image: np.ndarray  # (H, W, 3) uint8
    instances: np.ndarray  # (H, W) uint16, 0 = background
    classes: np.ndarray  # (H, W) uint8, 0 = background
    cells: pd.DataFrame  # one row per nucleus
    pattern: str
    mpp: float
    meta: dict = field(default_factory=dict)


# --- drawing primitives -----------------------------------------------------


def _ellipse_mask(size: int, cx: float, cy: float, rx: float, ry: float, angle: float) -> np.ndarray:
    yy, xx = np.mgrid[0:size, 0:size]
    x = xx - cx
    y = yy - cy
    c, s = np.cos(angle), np.sin(angle)
    xr = x * c + y * s
    yr = -x * s + y * c
    return (xr / rx) ** 2 + (yr / ry) ** 2 <= 1.0


def _place_centres(rng: np.random.Generator, spec: TileSpec) -> list[tuple[float, float, int]]:
    """Choose nucleus centres (x, y, class) according to the spatial pattern."""
    size = spec.size
    centres: list[tuple[float, float, int]] = []

    def uniform(n: int, cls: int) -> None:
        for _ in range(n):
            centres.append((rng.uniform(8, size - 8), rng.uniform(8, size - 8), cls))

    def cluster(n: int, cls: int, cx: float, cy: float, spread: float) -> None:
        for _ in range(n):
            x = np.clip(rng.normal(cx, spread), 8, size - 8)
            y = np.clip(rng.normal(cy, spread), 8, size - 8)
            centres.append((float(x), float(y), cls))

    if spec.pattern == "dispersed":
        uniform(spec.n_tumour, 1)
        uniform(spec.n_lymphocyte, 2)
        uniform(spec.n_stroma, 3)
        return centres

    # One tumour nest (occasionally two) somewhere off-centre.
    cx, cy = rng.uniform(size * 0.3, size * 0.7, size=2)
    spread = size * 0.13
    cluster(spec.n_tumour, 1, cx, cy, spread)
    if spec.pattern == "clustered":
        # Lymphocytes kept away from the nest: sample uniformly, reject inside 2 sd.
        placed = 0
        while placed < spec.n_lymphocyte:
            x, y = rng.uniform(8, size - 8, size=2)
            if np.hypot(x - cx, y - cy) > 2.2 * spread:
                centres.append((float(x), float(y), 2))
                placed += 1
    else:  # infiltrating: lymphocytes on a ring at the nest boundary and inside it
        for _ in range(spec.n_lymphocyte):
            r = rng.normal(1.6 * spread, 0.5 * spread)
            theta = rng.uniform(0, 2 * np.pi)
            x = np.clip(cx + r * np.cos(theta), 8, size - 8)
            y = np.clip(cy + r * np.sin(theta), 8, size - 8)
            centres.append((float(x), float(y), 2))
    uniform(spec.n_stroma, 3)
    return centres


def _background(rng: np.random.Generator, size: int) -> np.ndarray:
    """Eosin-pink background with faint, slightly oriented fibre texture."""
    img = np.empty((size, size, 3), dtype=np.float32)
    img[:] = _EOSIN_BG
    noise = rng.normal(0, 1, (size, size)).astype(np.float32)
    # Smooth the noise along a random direction to suggest fibres.
    k = 9
    kernel = np.ones(k, dtype=np.float32) / k
    axis = int(rng.integers(0, 2))
    smoothed = np.apply_along_axis(lambda v: np.convolve(v, kernel, mode="same"), axis, noise)
    smoothed = (smoothed - smoothed.min()) / (np.ptp(smoothed) + 1e-6)
    fibre = smoothed[..., None] * (_FIBRE - _EOSIN_BG)[None, None, :]
    return img + 0.9 * fibre


def make_tile(seed: int, spec: TileSpec) -> Tile:
    """Draw one tile deterministically from ``seed`` and ``spec``."""
    rng = np.random.default_rng(seed)
    size = spec.size
    image = _background(rng, size)
    instances = np.zeros((size, size), dtype=np.uint16)
    classes = np.zeros((size, size), dtype=np.uint8)
    rows: list[dict] = []

    # Draw large nuclei first so small lymphocytes can sit on top of edges.
    centres = sorted(_place_centres(rng, spec), key=lambda c: c[2] != 1)
    label = 0
    for cx, cy, cls in centres:
        if cls == 1:  # tumour: large, irregular ellipse
            rx, ry = rng.uniform(6.5, 10.5), rng.uniform(5.0, 8.5)
        elif cls == 2:  # lymphocyte: small, round
            rx = ry = rng.uniform(3.2, 4.6)
        else:  # stroma: thin and long
            rx, ry = rng.uniform(7.0, 11.0), rng.uniform(1.8, 3.0)
        mask = _ellipse_mask(size, cx, cy, rx, ry, rng.uniform(0, np.pi))
        mask &= instances == 0  # do not overwrite an existing nucleus
        area = int(mask.sum())
        if area < 12:
            continue
        label += 1
        instances[mask] = label
        classes[mask] = cls
        colour = _NUCLEUS[cls]
        if cls == 1:
            # Paler centre: vesicular chromatin look.
            yy, xx = np.nonzero(mask)
            d = np.hypot(xx - cx, yy - cy) / max(rx, ry)
            shade = (0.55 + 0.45 * d)[:, None]
            image[yy, xx] = colour * shade + _EOSIN_BG * (1 - shade) * 0.35
        else:
            image[mask] = colour
        yy, xx = np.nonzero(mask)
        rows.append(
            {
                "cell_id": label,
                "cx": float(xx.mean()),
                "cy": float(yy.mean()),
                "area_px": area,
                "class_id": int(cls),
                "class_name": CLASS_NAMES[cls],
            }
        )

    image += rng.normal(0, 3.0, image.shape).astype(np.float32)  # sensor noise
    image = np.clip(image, 0, 255).astype(np.uint8)
    cells = pd.DataFrame(
        rows, columns=["cell_id", "cx", "cy", "area_px", "class_id", "class_name"]
    )
    return Tile(image, instances, classes, cells, spec.pattern, spec.mpp, {"seed": seed})


# --- failure modes ----------------------------------------------------------


def _relabel(instances: np.ndarray) -> np.ndarray:
    """Renumber instance labels 1..N contiguously (after deletions)."""
    values = np.unique(instances)
    values = values[values != 0]
    out = np.zeros_like(instances)
    for new, old in enumerate(values, start=1):
        out[instances == old] = new
    return out


def corrupt_labels(
    instances: np.ndarray,
    classes: np.ndarray,
    mode: str,
    rng: np.random.Generator,
    fraction: float = 0.3,
) -> tuple[np.ndarray, np.ndarray]:
    """Return a deliberately wrong version of an instance/class label pair.

    ``fraction`` scales how bad: the share of nuclei removed, merged or
    added. Every mode changes a measurable feature that later phases must
    detect (count, area distribution, boundary agreement).
    """
    if mode not in LABEL_FAILURE_MODES:
        raise ValueError(f"mode must be one of {LABEL_FAILURE_MODES}, got {mode!r}")
    inst = instances.copy()
    cls = classes.copy()
    ids = np.unique(inst)
    ids = ids[ids != 0]
    if ids.size == 0:
        return inst, cls

    if mode == "missing_nuclei":
        drop = rng.choice(ids, size=max(1, int(fraction * ids.size)), replace=False)
        gone = np.isin(inst, drop)
        inst[gone] = 0
        cls[gone] = 0
        inst = _relabel(inst)

    elif mode == "merged_nuclei":
        # Grow every nucleus by a few pixels so neighbours touch, then relabel
        # connected blobs — touching nuclei become one instance.
        from scipy import ndimage  # noqa: PLC0415

        grown = ndimage.binary_dilation(inst > 0, iterations=max(1, int(6 * fraction)))
        merged, _ = ndimage.label(grown)
        merged = merged.astype(np.uint16)
        merged[inst == 0] = 0  # keep original pixels only, but with merged ids
        inst = _relabel(merged)
        # Class of a merged blob: the majority class of the pixels it covers.
        new_cls = np.zeros_like(cls)
        for i in np.unique(inst):
            if i == 0:
                continue
            region = inst == i
            vals = cls[region]
            new_cls[region] = np.bincount(vals[vals > 0]).argmax() if (vals > 0).any() else 0
        cls = new_cls

    elif mode == "false_positives":
        size = inst.shape[0]
        n_add = max(1, int(fraction * ids.size))
        next_id = int(inst.max()) + 1
        for _ in range(n_add):
            cx, cy = rng.uniform(8, size - 8, size=2)
            r = rng.uniform(3.5, 7.0)
            m = _ellipse_mask(size, cx, cy, r, r, 0.0) & (inst == 0)
            if m.sum() < 12:
                continue
            inst[m] = next_id
            cls[m] = int(rng.choice([1, 2, 3]))
            next_id += 1

    elif mode == "shifted_boundaries":
        from scipy import ndimage  # noqa: PLC0415

        # Erode or dilate each nucleus: areas systematically wrong.
        shrink = rng.random() < 0.5
        fg = inst > 0
        it = max(1, int(4 * fraction))
        new_fg = ndimage.binary_erosion(fg, iterations=it) if shrink else ndimage.binary_dilation(fg, iterations=it)
        if shrink:
            inst[~new_fg] = 0
            cls[~new_fg] = 0
            inst = _relabel(inst)
        else:
            # Assign grown pixels to the nearest existing instance.
            _, (iy, ix) = ndimage.distance_transform_edt(inst == 0, return_indices=True)
            grown = new_fg & (inst == 0)
            inst[grown] = inst[iy[grown], ix[grown]]
            cls[grown] = cls[iy[grown], ix[grown]]
    return inst, cls


def apply_artefact(image: np.ndarray, mode: str, rng: np.random.Generator, strength: float = 1.0) -> np.ndarray:
    """Return an image with an acquisition artefact applied."""
    if mode not in IMAGE_ARTEFACTS:
        raise ValueError(f"mode must be one of {IMAGE_ARTEFACTS}, got {mode!r}")
    img = image.astype(np.float32)
    size = img.shape[0]

    if mode == "blur":
        from scipy import ndimage  # noqa: PLC0415

        img = ndimage.gaussian_filter(img, sigma=(2.5 * strength, 2.5 * strength, 0))

    elif mode == "stain_shift":
        # Multiply channels differently: a "different lab" look.
        gain = np.array([1.0 + 0.15 * strength, 1.0 - 0.12 * strength, 1.0 + 0.08 * strength])
        img = img * gain[None, None, :] + np.array([0, 8, -6]) * strength

    elif mode == "fold":
        # A dark diagonal band: tissue folded over itself.
        yy, xx = np.mgrid[0:size, 0:size]
        offset = rng.uniform(-0.3, 0.3) * size
        band = np.abs((xx - yy) - offset) < 10 * strength
        img[band] *= 0.45

    elif mode == "pen_mark":
        # A thick blue-green stroke across part of the tile.
        yy, xx = np.mgrid[0:size, 0:size]
        y0 = rng.uniform(0.2, 0.8) * size
        slope = rng.uniform(-0.4, 0.4)
        stroke = np.abs(yy - (y0 + slope * (xx - size / 2))) < 6 * strength
        stroke &= xx > size * rng.uniform(0.0, 0.5)
        img[stroke] = np.array([40, 110, 90], dtype=np.float32)

    return np.clip(img, 0, 255).astype(np.uint8)


# --- dataset generation -----------------------------------------------------


def _synthetic_settings(cfg: Config) -> dict:
    path = cfg.section("pathology").get("synthetic", {})
    return {
        "n_slides": int(path.get("n_slides", 3)),
        "tiles_per_slide": int(path.get("tiles_per_slide", 6)),
        "tile_size": int(path.get("tile_size", 256)),
        "mpp": float(path.get("mpp", 0.5)),
        "magnification": float(path.get("magnification", 20)),
        "patterns": tuple(path.get("patterns", PATTERNS)),
        "grid": int(path.get("grid", 3)),  # tiles per side in the assembled slide
    }


def generate_dataset(cfg: Config, storage: Storage) -> dict:
    """Write a complete synthetic tile dataset and its tables. Idempotent.

    Returns a summary dict (paths and counts) for the command line to print.
    The layout mirrors the radiology dataset so both tracks are inventoried
    the same way; the assembled slide per synthetic "slide id" lets the slide
    reader, tiling and tissue detection run without any download.
    """
    st = _synthetic_settings(cfg)
    root = cfg.paths.data_raw / "synthetic_tiles"
    images_dir = root / "imagesTr"
    labels_dir = root / "labelsTr"
    slides_dir = root / "slides"
    for d in (images_dir, labels_dir, slides_dir):
        d.mkdir(parents=True, exist_ok=True)

    slide_rows: list[dict] = []
    tile_rows: list[dict] = []
    cell_frames: list[pd.DataFrame] = []
    grid = st["grid"]
    per_slide = min(st["tiles_per_slide"], grid * grid)

    for s_idx in range(st["n_slides"]):
        slide_id = f"synth_{s_idx:03d}"
        pattern = st["patterns"][s_idx % len(st["patterns"])]
        mosaic = np.full((grid * st["tile_size"], grid * st["tile_size"], 3), 235, dtype=np.uint8)
        for t_idx in range(per_slide):
            seed = cfg.seed * 100_003 + s_idx * 1_009 + t_idx
            spec = TileSpec(size=st["tile_size"], mpp=st["mpp"], pattern=pattern)
            tile = make_tile(seed, spec)
            tile_id = f"tile_{slide_id}_{t_idx:02d}"
            img_rel = f"synthetic_tiles/imagesTr/{tile_id}.png"
            inst_rel = f"synthetic_tiles/labelsTr/{tile_id}_inst.png"
            cls_rel = f"synthetic_tiles/labelsTr/{tile_id}_cls.png"
            Image.fromarray(tile.image).save(images_dir / f"{tile_id}.png")
            Image.fromarray(tile.instances.astype(np.uint16)).save(labels_dir / f"{tile_id}_inst.png")
            Image.fromarray(tile.classes).save(labels_dir / f"{tile_id}_cls.png")

            gy, gx = divmod(t_idx, grid)
            x0, y0 = gx * st["tile_size"], gy * st["tile_size"]
            mosaic[y0 : y0 + st["tile_size"], x0 : x0 + st["tile_size"]] = tile.image
            tile_rows.append(
                {
                    "tile_id": tile_id,
                    "slide_id": slide_id,
                    "x": x0,
                    "y": y0,
                    "size_px": st["tile_size"],
                    "mpp": st["mpp"],
                    "tissue_fraction": 1.0,
                    "image_path": img_rel,
                    "label_instance_path": inst_rel,
                    "label_class_path": cls_rel,
                    "pattern": pattern,
                }
            )
            cells = tile.cells.copy()
            cells.insert(0, "tile_id", tile_id)
            cell_frames.append(cells)

        slide_path = slides_dir / f"{slide_id}.tif"
        write_pyramidal_tiff(slide_path, mosaic, mpp=st["mpp"], magnification=st["magnification"], tile_size=st["tile_size"])
        slide_rows.append(
            {
                "slide_id": slide_id,
                "source": "synthetic_tiles",
                "path": f"synthetic_tiles/slides/{slide_id}.tif",
                "width_px": mosaic.shape[1],
                "height_px": mosaic.shape[0],
                "mpp_x": st["mpp"],
                "mpp_y": st["mpp"],
                "magnification": st["magnification"],
                "level_count": 0,  # filled by the inventory (Phase P1) from the file itself
                "stain": "synthetic",
                "split": "unassigned",
            }
        )

    slides = schemas.check("slides", pd.DataFrame(slide_rows))
    tiles = schemas.check("tiles", pd.DataFrame(tile_rows))
    cells = schemas.check("cells", pd.concat(cell_frames, ignore_index=True))
    storage.write_table("slides", slides)
    storage.write_table("tiles", tiles)
    storage.write_table("cells", cells)

    manifest = {
        "name": "SegAudit synthetic tiles",
        "description": "Synthetic H&E-like tiles with nuclei instance and class labels. SYNTHETIC — not tissue.",
        "labels": {"0": "background", **{str(k): v for k, v in CLASS_NAMES.items()}},
        "patterns": list(st["patterns"]),
        "mpp": st["mpp"],
        "magnification": st["magnification"],
        "tile_size": st["tile_size"],
        "n_slides": st["n_slides"],
        "tiles_per_slide": per_slide,
        "seed": cfg.seed,
    }
    (root / "dataset.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    return {
        "root": str(root),
        "n_slides": len(slide_rows),
        "n_tiles": len(tile_rows),
        "n_cells": int(len(cells)),
        "tables": ["slides", "tiles", "cells"],
    }
