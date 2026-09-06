"""Input quality-assurance gates for scans.

Why this module exists
----------------------
Quality *control* (later phases) judges outputs. Quality *assurance* judges
inputs: is this file even a sane scan? A volume with negative spacing, a mask
with a label the task does not define, an image full of NaNs — none of these
should ever reach a model, because the model will happily produce a
confident, meaningless answer. The gates here refuse such inputs with a
plain-language reason, and the inventory records the reasons in the
``qa_issues`` table so a whole dataset can be audited at a glance.

Everyday analogy: checking the ingredients before cooking (QA) versus tasting
the dish before it leaves the kitchen (QC).

Every check is a pure function returning a list of :class:`Issue`; an empty
list means "passes". Limits come from the configuration's ``qa`` section so
they are visible and adjustable, never hidden in code.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from segaudit.config import Config
from segaudit.radiology.io_nifti import Volume


@dataclass(frozen=True)
class Issue:
    check: str  # short machine name, e.g. "spacing_range"
    severity: str  # "error" (refuse) or "warning" (record, continue)
    message: str  # plain-language explanation


class QAError(ValueError):
    """Raised by :func:`gate` when any error-severity issue is present."""


@dataclass(frozen=True)
class QALimits:
    spacing_min_mm: float = 0.2
    spacing_max_mm: float = 5.0
    min_shape: int = 8
    max_shape: int = 1024
    allowed_labels: tuple[int, ...] = (0, 1, 2)
    min_foreground_voxels: int = 10
    intensity_max: float = 1.0e5

    @classmethod
    def from_config(cls, cfg: Config) -> QALimits:
        q = cfg.section("qa")
        return cls(
            spacing_min_mm=float(q.get("spacing_min_mm", cls.spacing_min_mm)),
            spacing_max_mm=float(q.get("spacing_max_mm", cls.spacing_max_mm)),
            min_shape=int(q.get("min_shape", cls.min_shape)),
            max_shape=int(q.get("max_shape", cls.max_shape)),
            allowed_labels=tuple(int(v) for v in q.get("allowed_labels", cls.allowed_labels)),
            min_foreground_voxels=int(q.get("min_foreground_voxels", cls.min_foreground_voxels)),
            intensity_max=float(q.get("intensity_max", cls.intensity_max)),
        )


def check_image(vol: Volume, limits: QALimits | None = None) -> list[Issue]:
    """Gates for an image volume."""
    limits = limits or QALimits()
    issues: list[Issue] = []
    if vol.data.ndim != 3:
        issues.append(Issue("ndim", "error", f"expected a 3D volume, got {vol.data.ndim} dimensions"))
        return issues  # nothing else is meaningful
    for axis, n in enumerate(vol.shape):
        if n < limits.min_shape or n > limits.max_shape:
            issues.append(Issue("shape_range", "error", f"axis {axis} has {n} voxels; allowed {limits.min_shape}–{limits.max_shape}"))
    for axis, s in enumerate(vol.spacing_mm):
        if not (limits.spacing_min_mm <= s <= limits.spacing_max_mm):
            issues.append(Issue("spacing_range", "error", f"voxel spacing on axis {axis} is {s:.3f} mm; allowed {limits.spacing_min_mm}–{limits.spacing_max_mm} mm"))
    if not np.isfinite(vol.data).all():
        issues.append(Issue("finite", "error", "image contains NaN or infinite values"))
    else:
        if float(np.ptp(vol.data)) == 0.0:
            issues.append(Issue("constant", "error", "image is constant (every voxel has the same value)"))
        if float(np.abs(vol.data).max()) > limits.intensity_max:
            issues.append(Issue("intensity_range", "warning", f"intensities exceed {limits.intensity_max:g}; check scaling"))
    if abs(np.linalg.det(vol.affine[:3, :3])) < 1e-9:
        issues.append(Issue("affine", "error", "affine is singular; geometry cannot be trusted"))
    return issues


def check_mask(mask: Volume, image: Volume | None = None, limits: QALimits | None = None) -> list[Issue]:
    """Gates for a label mask, optionally against its image."""
    limits = limits or QALimits()
    issues: list[Issue] = []
    if mask.data.ndim != 3:
        issues.append(Issue("ndim", "error", f"expected a 3D mask, got {mask.data.ndim} dimensions"))
        return issues
    labels = set(int(v) for v in np.unique(mask.data))
    bad = sorted(labels - set(limits.allowed_labels))
    if bad:
        issues.append(Issue("labels", "error", f"mask contains labels {bad}; allowed {list(limits.allowed_labels)}"))
    fg = int((mask.data != 0).sum())
    if fg < limits.min_foreground_voxels:
        issues.append(Issue("foreground", "error", f"mask has only {fg} labelled voxels (minimum {limits.min_foreground_voxels})"))
    if image is not None:
        if image.shape != mask.shape:
            issues.append(Issue("shape_match", "error", f"mask shape {mask.shape} differs from image shape {image.shape}"))
        if not np.allclose(image.affine, mask.affine, atol=1e-3):
            issues.append(Issue("affine_match", "error", "mask and image affines differ; they are not in the same space"))
    return issues


def gate(issues: list[Issue], what: str) -> None:
    """Raise :class:`QAError` if any issue is an error; warnings pass."""
    errors = [i for i in issues if i.severity == "error"]
    if errors:
        raise QAError(f"{what} failed input QA: " + "; ".join(f"[{i.check}] {i.message}" for i in errors))
