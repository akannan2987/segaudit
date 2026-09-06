"""DICOM series → NIfTI, with geometry and a metadata summary.

Why this module exists
----------------------
Research archives ship NIfTI: one file per volume. Scanners ship **DICOM**:
one file per slice, each stuffed with metadata (patient, scanner, date,
settings). Before SegAudit can audit a scan straight from a scanner, the
slices must be stacked into one volume *in the right order and with the right
spacing* — get the slice order wrong and the anatomy is scrambled; get the
slice gap wrong and every volume is scaled.

SimpleITK's series reader does exactly that stacking, using the geometry tags
every slice carries. pydicom reads the human-facing tags (modality, scanner
model, dates) for the provenance record. Nothing here touches pixel values.

Everyday analogy: a stack of index cards (one per slice), each with the page
number on the back; SimpleITK sorts and binds them into one book.

Everyday caution: DICOM headers may contain patient identity. The summary
returned here deliberately excludes name, birth date and IDs — SegAudit's
data folders are for de-identified research data only, as stated in
``data/README.md``.
"""

from __future__ import annotations

from pathlib import Path

import SimpleITK as sitk

# Tags worth recording for provenance; none of them identify a person.
_SUMMARY_TAGS = {
    "0008|0060": "modality",
    "0008|0070": "manufacturer",
    "0008|1090": "scanner_model",
    "0018|0050": "slice_thickness_mm",
    "0018|0088": "spacing_between_slices_mm",
    "0018|0087": "field_strength_t",
    "0020|000d": "study_instance_uid",
    "0020|000e": "series_instance_uid",
}


class DicomError(RuntimeError):
    pass


def find_series(folder: str | Path) -> list[str]:
    """Series IDs found in a folder (a folder may hold several series)."""
    folder = Path(folder)
    if not folder.is_dir():
        raise DicomError(f"Not a folder: {folder}")
    ids = sitk.ImageSeriesReader.GetGDCMSeriesIDs(str(folder))
    if not ids:
        raise DicomError(f"No DICOM series found in {folder}")
    return list(ids)


def convert_series(folder: str | Path, output: str | Path, series_id: str | None = None) -> dict:
    """Stack one DICOM series into a NIfTI file. Returns a metadata summary.

    Geometry (spacing, orientation, origin) is carried from the DICOM tags
    into the NIfTI header by SimpleITK; nothing is resampled.
    """
    folder = Path(folder)
    output = Path(output)
    ids = find_series(folder)
    sid = series_id or ids[0]
    if sid not in ids:
        raise DicomError(f"Series {sid!r} not in folder; available: {ids}")

    reader = sitk.ImageSeriesReader()
    files = reader.GetGDCMSeriesFileNames(str(folder), sid)
    reader.SetFileNames(files)
    reader.MetaDataDictionaryArrayUpdateOn()
    reader.LoadPrivateTagsOff()
    try:
        image = reader.Execute()
    except Exception as exc:
        raise DicomError(f"SimpleITK could not read series {sid!r}: {type(exc).__name__}: {exc}") from exc

    output.parent.mkdir(parents=True, exist_ok=True)
    sitk.WriteImage(image, str(output))

    summary = {
        "series_id": sid,
        "n_files": len(files),
        "output": str(output),
        "size_voxels": list(image.GetSize()),
        "spacing_mm": [float(s) for s in image.GetSpacing()],
    }
    for tag, name in _SUMMARY_TAGS.items():
        try:
            if reader.HasMetaDataKey(0, tag):
                summary[name] = reader.GetMetaData(0, tag).strip()
        except RuntimeError:
            pass
    return summary
