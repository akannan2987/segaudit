"""Synthetic MRI volumes — the radiology twin of the synthetic tiles.

Why this module exists
----------------------
The public hippocampus dataset must be downloaded (a few tens of megabytes,
under a licence) and every real run takes minutes. Tests, continuous
integration and a first walkthrough need volumes that exist in seconds with
nothing fetched. This generator draws small **T1-like** volumes containing a
two-part hippocampus-shaped structure (anterior = label 1, posterior =
label 2, as in the real task), with deliberate failure modes and artefacts,
fully seeded so the same configuration always produces the same voxels.

Everyday analogy: the crash-test dummy again — shaped enough like the real
thing that every seatbelt in the pipeline can be tested, and available with
exactly the injury you want to study.

What a case contains
--------------------
* **Image** — float32 volume: dark background, a brighter "brain" ellipsoid,
  the hippocampus as two abutting ellipsoids of intermediate intensity with
  low contrast against their surroundings (which is what makes the real task
  hard), smooth intensity bias across the field, and Rician-like noise.
* **Mask** — uint8 volume: 0 background, 1 anterior, 2 posterior.
* Geometry: isotropic voxels (1 mm by default) stored in a plain RAS affine.

Failure modes — how to make a *wrong* answer on purpose:
* ``corrupt_mask``: ``missing_part`` (one label dropped), ``undersized`` /
  ``oversized`` (eroded / dilated), ``extra_blob`` (a false structure),
  ``empty`` (nothing at all).
* ``apply_artefact``: ``noise`` (more of it), ``bias`` (stronger intensity
  gradient), ``motion`` (ghosting along one axis), ``low_resolution``
  (down- and up-sampled).

Output layout (mirrors the real dataset)::

    data/raw/synthetic_phantom/
        imagesTr/  phantom_000.nii.gz
        labelsTr/  phantom_000.nii.gz
        dataset.json
"""

from __future__ import annotations

import json
from dataclasses import dataclass

import numpy as np

from segaudit.config import Config
from segaudit.radiology.io_nifti import affine_from_spacing, save_volume

LABEL_NAMES = {1: "anterior", 2: "posterior"}
MASK_FAILURE_MODES = ("missing_part", "undersized", "oversized", "extra_blob", "empty")
IMAGE_ARTEFACTS = ("noise", "bias", "motion", "low_resolution")


@dataclass(frozen=True)
class PhantomSpec:
    shape: tuple[int, int, int] = (40, 56, 40)
    spacing_mm: tuple[float, float, float] = (1.0, 1.0, 1.0)
    noise_sigma: float = 6.0
    contrast: float = 0.18  # hippocampus vs surrounding brain, as a fraction of brain intensity


def _ellipsoid(shape, centre, radii, rotation_deg=0.0) -> np.ndarray:
    zz, yy, xx = np.mgrid[0 : shape[0], 0 : shape[1], 0 : shape[2]]
    x = xx - centre[2]
    y = yy - centre[1]
    z = zz - centre[0]
    # Small rotation in the y–z plane so the structure is not axis-aligned.
    t = np.deg2rad(rotation_deg)
    y2 = y * np.cos(t) - z * np.sin(t)
    z2 = y * np.sin(t) + z * np.cos(t)
    return (x / radii[2]) ** 2 + (y2 / radii[1]) ** 2 + (z2 / radii[0]) ** 2 <= 1.0


def make_case(seed: int, spec: PhantomSpec | None = None) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return (image float32, mask uint8, affine) for one synthetic case."""
    spec = spec or PhantomSpec()
    rng = np.random.default_rng(seed)
    shape = spec.shape
    centre = np.array(shape) / 2.0 + rng.normal(0, 1.5, 3)

    # Brain: a large ellipsoid filling most of the box.
    brain = _ellipsoid(shape, centre, np.array(shape) * 0.42)

    # Hippocampus: two abutting ellipsoids along the y (anterior–posterior) axis.
    length = rng.uniform(9, 13)
    r_ant = np.array([rng.uniform(4.5, 6.0), length * 0.55, rng.uniform(4.0, 5.5)])
    r_post = np.array([rng.uniform(3.5, 5.0), length * 0.5, rng.uniform(3.5, 5.0)])
    tilt = rng.uniform(-12, 12)
    c_ant = centre + np.array([rng.normal(0, 1), -length * 0.35, rng.normal(0, 1)])
    c_post = c_ant + np.array([rng.uniform(-1, 1), length * 0.85, rng.uniform(-1, 1)])
    anterior = _ellipsoid(shape, c_ant, r_ant, tilt) & brain
    posterior = _ellipsoid(shape, c_post, r_post, tilt) & brain & ~anterior

    mask = np.zeros(shape, dtype=np.uint8)
    mask[anterior] = 1
    mask[posterior] = 2

    # Intensities: background ~20, brain ~ 110 with texture, hippocampus slightly brighter.
    image = np.full(shape, 20.0, dtype=np.float32)
    brain_base = 110.0
    texture = rng.normal(0, 4.0, shape).astype(np.float32)
    image[brain] = brain_base + texture[brain]
    image[mask > 0] += brain_base * spec.contrast * (1.0 + 0.3 * (mask[mask > 0] == 2))
    # Smooth bias field across the volume (scanner shading).
    zz, yy, xx = np.mgrid[0 : shape[0], 0 : shape[1], 0 : shape[2]]
    bias = 1.0 + 0.08 * ((xx - shape[2] / 2) / shape[2]) + 0.05 * ((zz - shape[0] / 2) / shape[0])
    image *= bias.astype(np.float32)
    # Rician-like noise: magnitude of Gaussian noise added in two channels.
    n1 = rng.normal(0, spec.noise_sigma, shape)
    n2 = rng.normal(0, spec.noise_sigma, shape)
    image = np.sqrt((image + n1) ** 2 + n2**2).astype(np.float32)

    return image, mask, affine_from_spacing(spec.spacing_mm)


# --- failure modes ----------------------------------------------------------


def corrupt_mask(mask: np.ndarray, mode: str, rng: np.random.Generator, strength: float = 1.0) -> np.ndarray:
    """A deliberately wrong version of a mask. Each mode changes a measurable feature."""
    if mode not in MASK_FAILURE_MODES:
        raise ValueError(f"mode must be one of {MASK_FAILURE_MODES}, got {mode!r}")
    from scipy import ndimage  # noqa: PLC0415

    out = mask.copy()
    if mode == "empty":
        out[:] = 0
    elif mode == "missing_part":
        drop = int(rng.choice([1, 2]))
        out[out == drop] = 0
    elif mode in ("undersized", "oversized"):
        it = max(1, int(round(2 * strength)))
        for label in (1, 2):
            region = mask == label
            changed = ndimage.binary_erosion(region, iterations=it) if mode == "undersized" else ndimage.binary_dilation(region, iterations=it)
            out[region] = 0
            out[changed & (out == 0)] = label
    elif mode == "extra_blob":
        shape = mask.shape
        centre = np.array([rng.uniform(0.25, 0.75) * s for s in shape])
        blob = _ellipsoid(shape, centre, np.array([3, 4, 3]) * strength)
        out[blob & (out == 0)] = int(rng.choice([1, 2]))
    return out


def apply_artefact(image: np.ndarray, mode: str, rng: np.random.Generator, strength: float = 1.0) -> np.ndarray:
    """An image with an acquisition artefact applied."""
    if mode not in IMAGE_ARTEFACTS:
        raise ValueError(f"mode must be one of {IMAGE_ARTEFACTS}, got {mode!r}")
    from scipy import ndimage  # noqa: PLC0415

    img = image.astype(np.float32).copy()
    shape = img.shape
    if mode == "noise":
        img = np.sqrt((img + rng.normal(0, 15 * strength, shape)) ** 2 + rng.normal(0, 15 * strength, shape) ** 2)
    elif mode == "bias":
        zz, yy, xx = np.mgrid[0 : shape[0], 0 : shape[1], 0 : shape[2]]
        img *= 1.0 + 0.35 * strength * ((yy - shape[1] / 2) / shape[1])
    elif mode == "motion":
        # Ghosting: add a shifted, faded copy along axis 1.
        shift = max(2, int(round(4 * strength)))
        img = 0.8 * img + 0.2 * np.roll(img, shift, axis=1)
    elif mode == "low_resolution":
        f = max(2, int(round(2 * strength)))
        small = ndimage.zoom(img, 1.0 / f, order=1)
        img = ndimage.zoom(small, [s / d for s, d in zip(shape, small.shape, strict=True)], order=1)
        img = img[: shape[0], : shape[1], : shape[2]]
    return np.clip(img, 0, None).astype(np.float32)


# --- dataset generation -----------------------------------------------------


def _settings(cfg: Config) -> dict:
    s = cfg.section("data").get("synthetic", {})
    return {
        "n_cases": int(s.get("n_cases", 12)),
        "shape": tuple(int(v) for v in s.get("shape", (40, 56, 40))),
        "spacing": tuple(float(v) for v in s.get("voxel_size_mm", (1.0, 1.0, 1.0))),
    }


def generate_dataset(cfg: Config) -> dict:
    """Write the synthetic MRI dataset in the real dataset's layout. Idempotent.

    Returns a summary for the command line. The inventory (``build_inventory``)
    reads it back exactly as it reads the real dataset, so every later phase
    treats both alike.
    """
    st = _settings(cfg)
    root = cfg.paths.data_raw / "synthetic_phantom"
    (root / "imagesTr").mkdir(parents=True, exist_ok=True)
    (root / "labelsTr").mkdir(parents=True, exist_ok=True)
    spec = PhantomSpec(shape=st["shape"], spacing_mm=st["spacing"])
    training = []
    for i in range(st["n_cases"]):
        image, mask, affine = make_case(cfg.seed * 7919 + i, spec)
        name = f"phantom_{i:03d}.nii.gz"
        save_volume(root / "imagesTr" / name, image, affine)
        save_volume(root / "labelsTr" / name, mask, affine)
        training.append({"image": f"./imagesTr/{name}", "label": f"./labelsTr/{name}"})
    manifest = {
        "name": "SegAudit synthetic phantom",
        "description": "Synthetic T1-like volumes with a two-label hippocampus-shaped structure. SYNTHETIC — not a brain.",
        "modality": {"0": "synthetic-T1"},
        "labels": {"0": "background", **{str(k): v for k, v in LABEL_NAMES.items()}},
        "numTraining": st["n_cases"],
        "training": training,
        "shape": list(st["shape"]),
        "voxel_size_mm": list(st["spacing"]),
        "seed": cfg.seed,
    }
    (root / "dataset.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return {"root": str(root), "n_cases": st["n_cases"], "shape": st["shape"], "spacing_mm": st["spacing"]}
