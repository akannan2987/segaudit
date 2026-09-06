"""NIfTI input/output with geometry preserved — Track R's reader.

Why this module exists
----------------------
A scan file is not just a 3D block of numbers. It carries an **affine** — a
small 4x4 matrix saying how big each voxel is (spacing), which way each axis
points (orientation), and where the volume sits in scanner space. Every
millilitre SegAudit ever reports is `count of voxels x voxel volume`, so if
the affine is mishandled once, every downstream number is wrong. All reading
and writing of volumes therefore happens here, and nowhere else, so the
geometry rules live in exactly one place — exactly as microns-per-pixel lives
in :mod:`segaudit.pathology.io_wsi` for slides.

Everyday analogy: the affine is the scale and compass rose printed on a map.
This module is the clerk who never hands out a map without them.

Design choices, stated:

* **nibabel** reads and writes NIfTI (the research-neuroimaging standard).
  SimpleITK handles DICOM series (see :mod:`segaudit.radiology.dicom`).
* Images come back as ``float32`` (models want floats), masks as ``uint8``
  (labels are small integers); both keep the file's affine untouched.
* A loaded volume is a small frozen dataclass, so nothing downstream can
  accidentally "fix" the affine in passing.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import nibabel as nib
import numpy as np


class NiftiError(RuntimeError):
    """Raised when a file cannot be read or written as a NIfTI volume."""


@dataclass(frozen=True)
class Volume:
    """One loaded 3D volume plus its geometry.

    Attributes
    ----------
    data:
        The voxel values, shape ``(X, Y, Z)``.
    affine:
        The 4x4 matrix mapping voxel indices to millimetre positions.
    path:
        Where it came from (kept for error messages and provenance).
    """

    data: np.ndarray
    affine: np.ndarray
    path: Path

    @property
    def shape(self) -> tuple[int, int, int]:
        return tuple(int(s) for s in self.data.shape[:3])

    @property
    def spacing_mm(self) -> tuple[float, float, float]:
        """Voxel size along each axis in millimetres: the length of each affine column."""
        cols = self.affine[:3, :3]
        return tuple(float(np.linalg.norm(cols[:, i])) for i in range(3))

    @property
    def orientation(self) -> str:
        """Three letters such as ``'RAS'``: the anatomical direction each stored
        axis points to (Right/Left, Anterior/Posterior, Superior/Inferior)."""
        return "".join(nib.orientations.aff2axcodes(self.affine))

    @property
    def voxel_volume_mm3(self) -> float:
        sx, sy, sz = self.spacing_mm
        return sx * sy * sz

    def volume_ml(self, label: int | None = None) -> float:
        """Volume in millilitres of all non-zero voxels, or of one label."""
        mask = (self.data != 0) if label is None else (self.data == label)
        return float(mask.sum()) * self.voxel_volume_mm3 / 1000.0


def _load(path: str | Path) -> nib.Nifti1Image:
    path = Path(path)
    if not path.exists():
        raise NiftiError(f"File not found: {path}")
    try:
        return nib.load(str(path))
    except Exception as exc:  # nibabel raises several types; unify the message
        raise NiftiError(f"Not readable as NIfTI: {path} ({type(exc).__name__}: {exc})") from exc


def read_header(path: str | Path) -> dict:
    """Shape, spacing and orientation without loading the voxel data.

    Inventorying hundreds of scans only needs the header; reading the whole
    file each time would be slow for no reason.
    """
    img = _load(path)
    affine = np.asarray(img.affine, dtype=np.float64)
    shape = tuple(int(s) for s in img.shape[:3])
    spacing = tuple(float(np.linalg.norm(affine[:3, :3][:, i])) for i in range(3))
    return {
        "shape": shape,
        "spacing_mm": spacing,
        "orientation": "".join(nib.orientations.aff2axcodes(affine)),
        "ndim": int(len(img.shape)),
        "dtype": str(img.get_data_dtype()),
    }


def load_image(path: str | Path) -> Volume:
    """Load a scan as float32, geometry intact."""
    img = _load(path)
    data = np.asarray(img.get_fdata(dtype=np.float32))
    if data.ndim > 3:
        data = data[..., 0] if data.shape[-1] == 1 else data
    return Volume(data=data, affine=np.asarray(img.affine, dtype=np.float64), path=Path(path))


def load_mask(path: str | Path) -> Volume:
    """Load a label mask as uint8, geometry intact.

    ``np.rint`` before casting: some tools save integer labels in float files;
    rounding first means 1.0000001 stays label 1 instead of becoming garbage
    on truncation.
    """
    img = _load(path)
    data = np.rint(np.asarray(img.get_fdata())).astype(np.uint8)
    return Volume(data=data, affine=np.asarray(img.affine, dtype=np.float64), path=Path(path))


def save_volume(path: str | Path, data: np.ndarray, affine: np.ndarray) -> Path:
    """Write a volume with its affine. Creates parent folders. Returns the path.

    The dtype is whatever ``data`` carries — callers decide (float32 images,
    uint8 masks); this function's only job is to never lose the affine.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        nib.save(nib.Nifti1Image(np.asarray(data), np.asarray(affine, dtype=np.float64)), str(path))
    except Exception as exc:
        raise NiftiError(f"Cannot write {path}: {type(exc).__name__}: {exc}") from exc
    return path


def affine_from_spacing(spacing_mm: tuple[float, float, float], origin_mm=(0.0, 0.0, 0.0)) -> np.ndarray:
    """A plain RAS affine with the given voxel size — what the phantom uses."""
    a = np.eye(4, dtype=np.float64)
    a[0, 0], a[1, 1], a[2, 2] = spacing_mm
    a[:3, 3] = origin_mm
    return a
