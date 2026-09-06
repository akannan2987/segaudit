"""Table schemas: the column names every table in SegAudit agrees on.

Why this module exists
----------------------
Two tracks write into one storage layer. If the radiology code called a
column ``dice`` and the pathology code called it ``dice_score``, every shared
component downstream — the quality-control classifier, the review app, the
report drafter — would need two code paths. This registry is the contract:
one name per concept, declared once, checked by the code that writes tables.

Everyday analogy: a shared filing system where every department must use the
same form fields. "Patient ID" is always in the same box, whatever ward filled
the form in.

Two kinds of table
------------------
* **Track tables** describe the *units* each track works with.
  Radiology: ``cases`` (one row per scan). Pathology: ``slides`` (one row per
  whole-slide image), ``tiles`` (one row per tile cut from a slide), ``cells``
  (one row per nucleus/cell found in a tile).
* **Shared tables** are written by the shared core and look identical on both
  tracks: ``case_metrics``, ``qc_scores``, ``review_ledger``, ``runs``. Their
  key column is ``unit_id`` — a case id on Track R, a tile or slide id on
  Track P — plus ``unit_kind`` saying which.

Usage
-----
``schemas.check("cells", df)`` raises :class:`SchemaError` if a required
column is missing. Extra columns are allowed (a phase may add its own), so the
check is a floor, not a ceiling. Storage itself does not enforce this — tests
and ad-hoc tables would suffer — the pipeline code calls it before writing.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


class SchemaError(ValueError):
    """Raised when a table lacks a required column."""


@dataclass(frozen=True)
class Column:
    name: str
    kind: str  # human description of the type; not enforced, documented
    meaning: str


@dataclass(frozen=True)
class TableSchema:
    name: str
    track: str  # "radiology", "pathology" or "shared"
    key: tuple[str, ...]
    columns: tuple[Column, ...]

    @property
    def required(self) -> tuple[str, ...]:
        return tuple(c.name for c in self.columns)


# --- Track R: one row per scan ---------------------------------------------
CASES = TableSchema(
    name="cases",
    track="radiology",
    key=("case_id",),
    columns=(
        Column("case_id", "str", "unique scan identifier (also the subject id here)"),
        Column("source", "str", "dataset name, e.g. msd_task04_hippocampus or synthetic_phantom"),
        Column("image_path", "str", "NIfTI image file, relative to data_raw"),
        Column("label_path", "str", "NIfTI mask file, relative to data_raw ('' if none)"),
        Column("shape_x", "int", "voxels along axis 0"),
        Column("shape_y", "int", "voxels along axis 1"),
        Column("shape_z", "int", "voxels along axis 2"),
        Column("spacing_x_mm", "float", "voxel size along axis 0 in mm"),
        Column("spacing_y_mm", "float", "voxel size along axis 1 in mm"),
        Column("spacing_z_mm", "float", "voxel size along axis 2 in mm"),
        Column("orientation", "str", "axis codes, e.g. RAS"),
        Column("split", "str", "train / val / test / unassigned"),
    ),
)

# --- Track P: slides, tiles, cells -----------------------------------------
SLIDES = TableSchema(
    name="slides",
    track="pathology",
    key=("slide_id",),
    columns=(
        Column("slide_id", "str", "unique slide identifier"),
        Column("source", "str", "dataset name, e.g. camelyon16 or synthetic_tiles"),
        Column("path", "str", "slide file (or tile folder) relative to data_raw"),
        Column("width_px", "int", "level-0 width in pixels"),
        Column("height_px", "int", "level-0 height in pixels"),
        Column("mpp_x", "float", "microns per pixel along x at level 0 (NaN if unknown)"),
        Column("mpp_y", "float", "microns per pixel along y at level 0 (NaN if unknown)"),
        Column("magnification", "float", "nominal objective magnification, e.g. 20 or 40 (NaN if unknown)"),
        Column("level_count", "int", "number of pyramid levels"),
        Column("stain", "str", "H&E, IHC, mIF, ... or 'synthetic'"),
        Column("split", "str", "train / val / test / unassigned"),
    ),
)

TILES = TableSchema(
    name="tiles",
    track="pathology",
    key=("tile_id",),
    columns=(
        Column("tile_id", "str", "unique tile identifier"),
        Column("slide_id", "str", "slide the tile was cut from"),
        Column("x", "int", "level-0 x of the tile's top-left corner"),
        Column("y", "int", "level-0 y of the tile's top-left corner"),
        Column("size_px", "int", "tile edge length in pixels (square tiles)"),
        Column("mpp", "float", "microns per pixel at which the tile was extracted"),
        Column("tissue_fraction", "float", "fraction of the tile covered by tissue (0-1)"),
        Column("image_path", "str", "tile image file relative to data_raw"),
        Column("label_instance_path", "str", "instance-label image ('' if none)"),
        Column("label_class_path", "str", "class-label image ('' if none)"),
        Column("pattern", "str", "spatial pattern label for synthetic tiles ('' otherwise)"),
    ),
)

CELLS = TableSchema(
    name="cells",
    track="pathology",
    key=("tile_id", "cell_id"),
    columns=(
        Column("tile_id", "str", "tile the cell was found in"),
        Column("cell_id", "int", "instance label value within the tile"),
        Column("cx", "float", "centroid x in tile pixels"),
        Column("cy", "float", "centroid y in tile pixels"),
        Column("area_px", "int", "number of pixels in the instance"),
        Column("class_id", "int", "phenotype class (0 background is never a row)"),
        Column("class_name", "str", "phenotype name, e.g. tumour / lymphocyte / stroma"),
    ),
)

# --- Shared tables (identical on both tracks) ------------------------------
CASE_METRICS = TableSchema(
    name="case_metrics",
    track="shared",
    key=("unit_id", "model", "run_label"),
    columns=(
        Column("unit_id", "str", "case_id on Track R; tile_id or slide_id on Track P"),
        Column("unit_kind", "str", "case / tile / slide"),
        Column("model", "str", "which model produced the segmentation"),
        Column("run_label", "str", "configuration run label"),
        Column("dice", "float", "overlap with the reference (NaN when no reference)"),
    ),
)

QC_SCORES = TableSchema(
    name="qc_scores",
    track="shared",
    key=("unit_id", "run_label"),
    columns=(
        Column("unit_id", "str", "case_id / tile_id / slide_id"),
        Column("unit_kind", "str", "case / tile / slide"),
        Column("run_label", "str", "configuration run label"),
        Column("qc_score", "float", "predicted probability of failure (0-1)"),
        Column("decision", "str", "review / auto_accept"),
    ),
)

REVIEW_LEDGER = TableSchema(
    name="review_ledger",
    track="shared",
    key=("unit_id", "reviewed_at"),
    columns=(
        Column("unit_id", "str", "case_id / tile_id / slide_id"),
        Column("unit_kind", "str", "case / tile / slide"),
        Column("decision", "str", "accept / flag"),
        Column("reviewer", "str", "who decided"),
        Column("reviewed_at", "str", "ISO-8601 timestamp"),
        Column("note", "str", "free text ('' if none)"),
    ),
)

RUNS = TableSchema(
    name="runs",
    track="shared",
    key=("run_id",),
    columns=(
        Column("run_id", "str", "unique run identifier"),
        Column("run_label", "str", "configuration run label"),
        Column("track", "str", "radiology / pathology"),
        Column("command", "str", "what was run"),
        Column("config_file", "str", "configuration file used"),
        Column("seed", "int", "seed used"),
        Column("started_at", "str", "ISO-8601 timestamp"),
        Column("segaudit_version", "str", "package version"),
    ),
)

REGISTRY: dict[str, TableSchema] = {
    s.name: s
    for s in (CASES, SLIDES, TILES, CELLS, CASE_METRICS, QC_SCORES, REVIEW_LEDGER, RUNS)
}


def schema(name: str) -> TableSchema:
    try:
        return REGISTRY[name]
    except KeyError as exc:
        raise SchemaError(f"No schema registered for table {name!r}") from exc


def check(name: str, table: pd.DataFrame) -> pd.DataFrame:
    """Raise if ``table`` lacks any required column of ``name``; else return it.

    Column order is not enforced and extra columns are fine.
    """
    missing = [c for c in schema(name).required if c not in table.columns]
    if missing:
        raise SchemaError(f"Table {name!r} is missing required column(s): {', '.join(missing)}")
    return table


def describe(name: str) -> str:
    """A plain-text description of one schema, used by ``segaudit schemas``."""
    s = schema(name)
    lines = [f"{s.name}  (track: {s.track}; key: {', '.join(s.key)})"]
    for c in s.columns:
        lines.append(f"  {c.name:<22}{c.kind:<8}{c.meaning}")
    return "\n".join(lines)
