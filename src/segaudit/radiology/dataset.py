"""Track R datasets: download the public hippocampus data, inventory any dataset.

Why this module exists
----------------------
Two jobs, kept apart on purpose:

1. **Download** the public dataset once, verify it byte for byte against a
   published checksum, unpack it safely, and never do any of that again if it
   is already there (idempotent). What lands in ``data/raw/`` is the evidence
   locker: never edited by code.
2. **Inventory** whatever dataset folder the configuration points at — real
   or synthetic, same layout — into the ``cases`` table (geometry per scan)
   and the ``qa_issues`` table (every input-QA finding), so the whole dataset
   can be questioned with SQL before a single model runs.

Everyday analogy: receiving a delivery. Check the seal (checksum), unpack it
into the store room (extract), then walk the shelves with a clipboard writing
down what is there and what looks damaged (inventory + QA).

The public dataset
------------------
Medical Segmentation Decathlon, Task 04 (Hippocampus): 394 T1-weighted MRI
volumes, 263 with labels (1 = anterior, 2 = posterior), CC-BY-SA 4.0. The
archive is served from the maintainers' public mirror; its MD5 is the one the
MONAI project publishes for the same file. Both live in the configuration,
not here, so a mirror change is a config edit.
"""

from __future__ import annotations

import hashlib
import json
import tarfile
import urllib.request
from collections.abc import Callable
from pathlib import Path

import numpy as np
import pandas as pd

from segaudit import schemas
from segaudit.config import Config
from segaudit.radiology import io_nifti, qa
from segaudit.storage import Storage


class DatasetError(RuntimeError):
    pass


# --- download ---------------------------------------------------------------


def _md5(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.md5()
    with path.open("rb") as fh:
        while True:
            block = fh.read(chunk)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def _fetch(url: str, target: Path, progress: Callable[[int, int], None] | None = None) -> None:
    """Stream ``url`` to ``target`` (a ``.part`` file first, renamed on success).

    Resumable: if a ``.part`` file exists, the request asks the server to
    continue from its length (HTTP Range). Servers that ignore Range simply
    restart, which is safe.
    """
    part = target.with_suffix(target.suffix + ".part")
    start = part.stat().st_size if part.exists() else 0
    req = urllib.request.Request(url, headers={"Range": f"bytes={start}-"} if start else {})
    with urllib.request.urlopen(req) as resp:  # noqa: S310 — https URL from config
        status = getattr(resp, "status", 200)
        resumed = status == 206
        total = int(resp.headers.get("Content-Length") or 0) + (start if resumed else 0)
        mode = "ab" if resumed else "wb"
        done = start if resumed else 0
        with part.open(mode) as fh:
            while True:
                block = resp.read(1 << 20)
                if not block:
                    break
                fh.write(block)
                done += len(block)
                if progress:
                    progress(done, total)
    part.replace(target)


def _safe_extract(archive: Path, dest: Path) -> list[str]:
    """Extract a tar archive, refusing members that would land outside ``dest``.

    A malicious or corrupt archive can contain names like ``../../etc/passwd``;
    Python 3.12+ has a built-in filter for this, but Python 3.11 (the project's
    baseline) does not, so the check is written out.
    """
    dest = dest.resolve()
    names: list[str] = []
    with tarfile.open(archive) as tar:
        for member in tar.getmembers():
            target = (dest / member.name).resolve()
            if dest != target and dest not in target.parents:
                raise DatasetError(f"Archive member escapes the destination folder: {member.name!r}")
            if member.issym() or member.islnk():
                raise DatasetError(f"Archive contains a link, refusing: {member.name!r}")
            names.append(member.name)
        # Python >= 3.12 offers an extraction filter; pass it when present so
        # the interpreter's own checks run too (3.11 falls back to ours above).
        if hasattr(tarfile, "data_filter"):
            tar.extractall(dest, filter="data")
        else:  # pragma: no cover — Python 3.11 path
            tar.extractall(dest)  # noqa: S202 — members validated above
    return names


def download_dataset(cfg: Config, fetch: Callable[[str, Path], None] | None = None, progress=None) -> dict:
    """Fetch, verify and extract the configured public dataset. Idempotent.

    ``fetch`` is injectable so tests can supply a fake archive without a network.
    Returns a summary; ``summary["skipped"]`` is True when nothing needed doing.
    """
    d = cfg.section("data").get("msd", {})
    for key in ("url", "md5", "archive", "dirname"):
        if key not in d:
            raise DatasetError(f"configuration data.msd is missing {key!r}")
    raw = cfg.paths.data_raw
    raw.mkdir(parents=True, exist_ok=True)
    extracted = raw / d["dirname"]
    archive = raw / d["archive"]

    if (extracted / "dataset.json").exists():
        return {"root": str(extracted), "skipped": True, "reason": "already extracted"}

    if not archive.exists():
        (fetch or (lambda url, target: _fetch(url, target, progress)))(d["url"], archive)

    digest = _md5(archive)
    if digest.lower() != str(d["md5"]).lower():
        archive.rename(archive.with_suffix(archive.suffix + ".corrupt"))
        raise DatasetError(
            f"Checksum mismatch for {archive.name}: expected {d['md5']}, got {digest}. "
            "The download is incomplete or the mirror changed; the file was renamed *.corrupt. Run the command again."
        )
    names = _safe_extract(archive, raw)
    if not (extracted / "dataset.json").exists():
        raise DatasetError(f"Archive extracted but {extracted / 'dataset.json'} is missing; unexpected layout: {names[:5]}")
    return {"root": str(extracted), "skipped": False, "archive_md5": digest, "members": len(names)}


# --- inventory --------------------------------------------------------------


def dataset_root(cfg: Config) -> Path:
    """Where the configured dataset lives (synthetic or public)."""
    if cfg.use_synthetic:
        return cfg.paths.data_raw / "synthetic_phantom"
    return cfg.paths.data_raw / cfg.section("data").get("msd", {}).get("dirname", "Task04_Hippocampus")


def _pairs(root: Path) -> list[tuple[str, Path, Path | None]]:
    """(case_id, image, label-or-None) for every image in imagesTr/.

    Skips macOS ``._`` resource-fork files, which the public archive contains
    and which are not scans — a classic first-run surprise.
    """
    images = sorted(p for p in (root / "imagesTr").glob("*.nii*") if not p.name.startswith("."))
    out = []
    for img in images:
        case_id = img.name.split(".nii")[0]
        lbl = root / "labelsTr" / img.name
        out.append((case_id, img, lbl if lbl.exists() else None))
    return out


def build_inventory(cfg: Config, storage: Storage, limits: qa.QALimits | None = None) -> dict:
    """Walk the dataset, write ``cases`` and ``qa_issues``, return a summary.

    Every case is recorded even if it fails QA; the ``qa_issues`` table says
    why, and later phases exclude failed cases by joining on it. Nothing is
    silently dropped.
    """
    root = dataset_root(cfg)
    if not (root / "imagesTr").exists():
        raise DatasetError(f"No imagesTr/ under {root}. Run `segaudit data download` or `segaudit data phantom` first.")
    limits = limits or qa.QALimits.from_config(cfg)
    source = "synthetic_phantom" if cfg.use_synthetic else cfg.section("data").get("source", "msd_task04_hippocampus")

    case_rows, issue_rows = [], []
    for case_id, img_path, lbl_path in _pairs(root):
        hdr = io_nifti.read_header(img_path)
        row = {
            "case_id": case_id,
            "source": source,
            "image_path": img_path.relative_to(cfg.paths.data_raw).as_posix(),
            "label_path": lbl_path.relative_to(cfg.paths.data_raw).as_posix() if lbl_path else "",
            "shape_x": hdr["shape"][0], "shape_y": hdr["shape"][1], "shape_z": hdr["shape"][2],
            "spacing_x_mm": hdr["spacing_mm"][0], "spacing_y_mm": hdr["spacing_mm"][1], "spacing_z_mm": hdr["spacing_mm"][2],
            "orientation": hdr["orientation"],
            "split": "unassigned",
        }
        image = io_nifti.load_image(img_path)
        issues = qa.check_image(image, limits)
        stats = {
            "intensity_mean": float(image.data.mean()),
            "intensity_std": float(image.data.std()),
            "intensity_p01": float(np.percentile(image.data, 1)),
            "intensity_p99": float(np.percentile(image.data, 99)),
        }
        row.update(stats)
        if lbl_path:
            mask = io_nifti.load_mask(lbl_path)
            issues += qa.check_mask(mask, image, limits)
            row["volume_label1_ml"] = mask.volume_ml(1)
            row["volume_label2_ml"] = mask.volume_ml(2)
        else:
            row["volume_label1_ml"] = float("nan")
            row["volume_label2_ml"] = float("nan")
        row["qa_errors"] = sum(1 for i in issues if i.severity == "error")
        row["qa_warnings"] = sum(1 for i in issues if i.severity == "warning")
        case_rows.append(row)
        issue_rows += [{"case_id": case_id, "check": i.check, "severity": i.severity, "message": i.message} for i in issues]

    cases = schemas.check("cases", pd.DataFrame(case_rows))
    storage.write_table("cases", cases)
    storage.write_table("qa_issues", pd.DataFrame(issue_rows, columns=["case_id", "check", "severity", "message"]))
    manifest = json.loads((root / "dataset.json").read_text(encoding="utf-8")) if (root / "dataset.json").exists() else {}
    return {
        "root": str(root),
        "source": source,
        "n_cases": len(case_rows),
        "n_with_labels": int(sum(1 for r in case_rows if r["label_path"])),
        "n_qa_errors": int(sum(r["qa_errors"] for r in case_rows)),
        "n_qa_warnings": int(sum(r["qa_warnings"] for r in case_rows)),
        "dataset_name": manifest.get("name", ""),
        "tables": ["cases", "qa_issues"],
    }
