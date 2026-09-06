"""Tests for Track R's data layer: NIfTI I/O, phantom, QA gates, inventory, download logic, DICOM."""

from __future__ import annotations

import hashlib
import io
import tarfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml

from segaudit import api
from segaudit.config import load_config
from segaudit.radiology import dataset, io_nifti, qa
from segaudit.radiology import phantom_volume as pv

# --- fixtures ---------------------------------------------------------------


@pytest.fixture
def rad_cfg(repo_root: Path, minimal_config: dict):
    data = {
        **minimal_config,
        "data": {
            "source": "synthetic_phantom",
            "use_synthetic": True,
            "synthetic": {"n_cases": 4, "shape": [24, 32, 24], "voxel_size_mm": [1.0, 1.0, 1.0]},
            "msd": {"url": "https://example.invalid/x.tar", "md5": "", "archive": "x.tar", "dirname": "X"},
        },
    }
    path = repo_root / "configs" / "rad.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    cfg = load_config(path)
    api.initialise_workspace(cfg)
    return cfg


# --- io_nifti ---------------------------------------------------------------


def test_nifti_round_trip_preserves_geometry(tmp_path: Path):
    affine = io_nifti.affine_from_spacing((0.8, 1.0, 1.2), origin_mm=(-10, 5, 3))
    data = np.random.default_rng(0).random((8, 9, 10)).astype(np.float32)
    p = io_nifti.save_volume(tmp_path / "v.nii.gz", data, affine)
    vol = io_nifti.load_image(p)
    assert vol.shape == (8, 9, 10)
    assert vol.spacing_mm == pytest.approx((0.8, 1.0, 1.2))
    assert vol.orientation == "RAS"
    assert np.allclose(vol.affine, affine)
    assert np.allclose(vol.data, data)
    hdr = io_nifti.read_header(p)
    assert hdr["shape"] == (8, 9, 10) and hdr["orientation"] == "RAS"


def test_mask_round_trip_and_volume_ml(tmp_path: Path):
    affine = io_nifti.affine_from_spacing((2.0, 2.0, 2.0))  # 8 mm3 per voxel
    m = np.zeros((6, 6, 6), np.uint8)
    m[1:3, 1:3, 1:3] = 1  # 8 voxels
    m[4, 4, 4] = 2  # 1 voxel
    p = io_nifti.save_volume(tmp_path / "m.nii.gz", m, affine)
    mask = io_nifti.load_mask(p)
    assert mask.data.dtype == np.uint8
    assert mask.volume_ml(1) == pytest.approx(8 * 8 / 1000)
    assert mask.volume_ml(2) == pytest.approx(8 / 1000)
    assert mask.volume_ml() == pytest.approx(9 * 8 / 1000)


def test_missing_and_unreadable_files_are_clear_errors(tmp_path: Path):
    with pytest.raises(io_nifti.NiftiError, match="not found"):
        io_nifti.load_image(tmp_path / "nope.nii.gz")
    bad = tmp_path / "bad.nii.gz"
    bad.write_bytes(b"not a nifti")
    with pytest.raises(io_nifti.NiftiError, match="Not readable"):
        io_nifti.load_image(bad)


def test_volume_is_frozen():
    v = io_nifti.Volume(np.zeros((2, 2, 2)), np.eye(4), Path("x"))
    import dataclasses

    with pytest.raises(dataclasses.FrozenInstanceError):
        v.affine = np.eye(4)  # type: ignore[misc]


# --- phantom ----------------------------------------------------------------


def test_phantom_case_is_deterministic_and_well_formed():
    a_img, a_mask, a_aff = pv.make_case(3)
    b_img, b_mask, _ = pv.make_case(3)
    c_img, _, _ = pv.make_case(4)
    assert np.array_equal(a_img, b_img) and np.array_equal(a_mask, b_mask)
    assert not np.array_equal(a_img, c_img)
    assert a_img.dtype == np.float32 and a_mask.dtype == np.uint8
    assert set(np.unique(a_mask)) == {0, 1, 2}
    assert a_aff.shape == (4, 4)
    # Hippocampus is brighter than surrounding brain on average, but not by much (low contrast).
    brain = (a_img > 60) & (a_mask == 0)
    assert a_img[a_mask > 0].mean() > a_img[brain].mean()
    assert (a_img[a_mask > 0].mean() - a_img[brain].mean()) < 60


@pytest.mark.parametrize("mode", pv.MASK_FAILURE_MODES)
def test_each_mask_failure_mode_changes_what_it_claims(mode):
    _, mask, _ = pv.make_case(5)
    rng = np.random.default_rng(0)
    out = pv.corrupt_mask(mask, mode, rng)
    fg0, fg1 = int((mask > 0).sum()), int((out > 0).sum())
    if mode == "empty":
        assert fg1 == 0
    elif mode == "missing_part":
        assert len(set(np.unique(out)) - {0}) == 1
    elif mode == "undersized":
        assert 0 < fg1 < fg0
    elif mode == "oversized":
        assert fg1 > fg0
    elif mode == "extra_blob":
        assert fg1 > fg0 and set(np.unique(out)) <= {0, 1, 2}


@pytest.mark.parametrize("mode", pv.IMAGE_ARTEFACTS)
def test_each_image_artefact_changes_the_image_not_the_shape(mode):
    img, _, _ = pv.make_case(6)
    out = pv.apply_artefact(img, mode, np.random.default_rng(1))
    assert out.shape == img.shape and out.dtype == np.float32
    assert not np.array_equal(out, img)


def test_unknown_modes_are_rejected():
    _, mask, _ = pv.make_case(1)
    with pytest.raises(ValueError):
        pv.corrupt_mask(mask, "vanish", np.random.default_rng(0))
    with pytest.raises(ValueError):
        pv.apply_artefact(np.zeros((4, 4, 4), np.float32), "sparkle", np.random.default_rng(0))


# --- QA gates ---------------------------------------------------------------


def _vol(data, spacing=(1, 1, 1)):
    return io_nifti.Volume(np.asarray(data), io_nifti.affine_from_spacing(spacing), Path("mem"))


def test_good_phantom_passes_qa():
    img, mask, aff = pv.make_case(2)
    image = io_nifti.Volume(img, aff, Path("i"))
    m = io_nifti.Volume(mask, aff, Path("m"))
    assert qa.check_image(image) == []
    assert qa.check_mask(m, image) == []


def test_qa_catches_bad_spacing_nan_constant_and_labels():
    img, mask, aff = pv.make_case(2)
    checks = {i.check for i in qa.check_image(_vol(img, spacing=(0.05, 1, 1)))}
    assert "spacing_range" in checks
    nan = img.copy()
    nan[0, 0, 0] = np.nan
    assert "finite" in {i.check for i in qa.check_image(_vol(nan))}
    assert "constant" in {i.check for i in qa.check_image(_vol(np.zeros_like(img)))}
    bad = mask.copy()
    bad[0, 0, 0] = 7
    assert "labels" in {i.check for i in qa.check_mask(_vol(bad))}
    assert "foreground" in {i.check for i in qa.check_mask(_vol(np.zeros_like(mask)))}
    small = _vol(mask[:-1])
    assert "shape_match" in {i.check for i in qa.check_mask(small, _vol(img))}


def test_gate_raises_on_errors_only():
    qa.gate([qa.Issue("x", "warning", "meh")], "thing")  # no raise
    with pytest.raises(qa.QAError, match="failed input QA"):
        qa.gate([qa.Issue("x", "error", "bad")], "thing")


# --- generate + inventory ---------------------------------------------------


def test_generate_and_inventory_end_to_end(rad_cfg):
    summary = api.generate_synthetic(rad_cfg)
    assert summary["n_cases"] == 4
    root = Path(summary["root"])
    assert (root / "dataset.json").exists()
    assert len(list((root / "imagesTr").glob("*.nii.gz"))) == 4

    inv = api.build_inventory(rad_cfg)
    assert inv["n_cases"] == 4 and inv["n_with_labels"] == 4 and inv["n_qa_errors"] == 0
    store = api.storage_for(rad_cfg)
    cases = store.read_table("cases")
    assert set(cases.case_id) == {f"phantom_{i:03d}" for i in range(4)}
    assert (cases.orientation == "RAS").all()
    assert (cases.volume_label1_ml > 0).all() and (cases.volume_label2_ml > 0).all()
    assert store.exists("qa_issues")
    # SQL over the new tables through the API
    top = api.query(rad_cfg, "SELECT case_id FROM cases ORDER BY volume_label1_ml DESC LIMIT 1")
    assert len(top) == 1
    # idempotent
    assert api.generate_synthetic(rad_cfg) == summary


def test_inventory_records_qa_failures_instead_of_dropping_cases(rad_cfg):
    api.generate_synthetic(rad_cfg)
    root = dataset.dataset_root(rad_cfg)
    # Corrupt one label file with an illegal label value.
    p = root / "labelsTr" / "phantom_001.nii.gz"
    m = io_nifti.load_mask(p)
    bad = m.data.copy()
    bad[0, 0, 0] = 9
    io_nifti.save_volume(p, bad, m.affine)
    # And drop a ._ resource-fork file into imagesTr like the real archive has.
    (root / "imagesTr" / "._phantom_000.nii.gz").write_bytes(b"\x00\x05\x16\x07")

    inv = api.build_inventory(rad_cfg)
    assert inv["n_cases"] == 4  # the ._ file was skipped, no case dropped
    assert inv["n_qa_errors"] == 1
    issues = api.query(rad_cfg, "SELECT * FROM qa_issues WHERE severity = 'error'")
    assert list(issues.case_id) == ["phantom_001"] and issues.check.iloc[0] == "labels"


def test_inventory_without_data_is_a_clear_error(rad_cfg):
    with pytest.raises(dataset.DatasetError, match="imagesTr"):
        api.build_inventory(rad_cfg)


# --- download logic without a network --------------------------------------


def _fake_archive(dirname: str, escape: bool = False) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        payload = b"{}"
        name = "../escape.json" if escape else f"{dirname}/dataset.json"
        info = tarfile.TarInfo(name)
        info.size = len(payload)
        tar.addfile(info, io.BytesIO(payload))
    return buf.getvalue()


def _cfg_with_msd(repo_root: Path, minimal_config: dict, md5: str, dirname="X") -> object:
    data = {**minimal_config, "data": {"use_synthetic": False, "msd": {"url": "https://example.invalid/x.tar", "md5": md5, "archive": "x.tar", "dirname": dirname}}}
    path = repo_root / "configs" / "dl.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    cfg = load_config(path)
    api.initialise_workspace(cfg)
    return cfg


def test_download_verifies_checksum_extracts_and_is_idempotent(repo_root, minimal_config):
    blob = _fake_archive("X")
    cfg = _cfg_with_msd(repo_root, minimal_config, hashlib.md5(blob).hexdigest())
    calls = []

    def fetch(url, target):
        calls.append(url)
        Path(target).write_bytes(blob)

    first = dataset.download_dataset(cfg, fetch=fetch)
    assert first["skipped"] is False and first["members"] == 1
    assert (cfg.paths.data_raw / "X" / "dataset.json").exists()
    second = dataset.download_dataset(cfg, fetch=fetch)
    assert second["skipped"] is True and calls == ["https://example.invalid/x.tar"]


def test_download_refuses_bad_checksum_and_renames_file(repo_root, minimal_config):
    blob = _fake_archive("X")
    cfg = _cfg_with_msd(repo_root, minimal_config, "0" * 32)
    with pytest.raises(dataset.DatasetError, match="Checksum mismatch"):
        dataset.download_dataset(cfg, fetch=lambda u, t: Path(t).write_bytes(blob))
    assert (cfg.paths.data_raw / "x.tar.corrupt").exists()


def test_extract_refuses_path_traversal(repo_root, minimal_config):
    blob = _fake_archive("X", escape=True)
    cfg = _cfg_with_msd(repo_root, minimal_config, hashlib.md5(blob).hexdigest())
    with pytest.raises(dataset.DatasetError, match="escapes"):
        dataset.download_dataset(cfg, fetch=lambda u, t: Path(t).write_bytes(blob))


def test_download_on_pathology_track_is_explicitly_not_ready(config_file):
    cfg = load_config(config_file, track="pathology")
    with pytest.raises(NotImplementedError, match="P1"):
        api.download_dataset(cfg)


# --- runs ledger ------------------------------------------------------------


def test_record_run_appends_to_runs(rad_cfg):
    a = api.record_run(rad_cfg, "test one")
    b = api.record_run(rad_cfg, "test two")
    runs = api.storage_for(rad_cfg).read_table("runs")
    assert len(runs) == 2 and set(runs.run_id) == {a, b}
    assert (runs.track == "radiology").all() and (runs.segaudit_version == api.version()).all()


# --- DICOM ------------------------------------------------------------------


def _write_dicom_series(folder: Path, n_slices: int = 5, spacing=(0.7, 0.7, 2.5)) -> None:
    """A tiny synthetic DICOM series written with pydicom (no real patient data)."""
    import pydicom
    from pydicom.dataset import FileDataset, FileMetaDataset
    from pydicom.uid import ExplicitVRLittleEndian, generate_uid

    folder.mkdir(parents=True, exist_ok=True)
    study, series, frame = generate_uid(), generate_uid(), generate_uid()
    rng = np.random.default_rng(0)
    for i in range(n_slices):
        meta = FileMetaDataset()
        meta.MediaStorageSOPClassUID = pydicom.uid.MRImageStorage
        meta.MediaStorageSOPInstanceUID = generate_uid()
        meta.TransferSyntaxUID = ExplicitVRLittleEndian
        ds = FileDataset(str(folder / f"slice_{i:03d}.dcm"), {}, file_meta=meta, preamble=b"\0" * 128)
        ds.SOPClassUID = meta.MediaStorageSOPClassUID
        ds.SOPInstanceUID = meta.MediaStorageSOPInstanceUID
        ds.StudyInstanceUID, ds.SeriesInstanceUID, ds.FrameOfReferenceUID = study, series, frame
        ds.Modality = "MR"
        ds.Manufacturer = "SegAudit synthetic"
        ds.PatientName, ds.PatientID = "SYNTHETIC^PHANTOM", "SYNTH000"
        ds.Rows = ds.Columns = 16
        ds.PixelSpacing = [spacing[0], spacing[1]]
        ds.SliceThickness = spacing[2]
        ds.ImageOrientationPatient = [1, 0, 0, 0, 1, 0]
        ds.ImagePositionPatient = [0, 0, i * spacing[2]]
        ds.InstanceNumber = i + 1
        ds.SamplesPerPixel, ds.PhotometricInterpretation = 1, "MONOCHROME2"
        ds.BitsAllocated = ds.BitsStored = 16
        ds.HighBit, ds.PixelRepresentation = 15, 0
        ds.PixelData = rng.integers(0, 1000, (16, 16), dtype=np.uint16).tobytes()
        ds.save_as(str(folder / f"slice_{i:03d}.dcm"), enforce_file_format=True)


def test_dicom_series_to_nifti_keeps_spacing_and_drops_identity(tmp_path: Path):
    _write_dicom_series(tmp_path / "series", n_slices=5, spacing=(0.7, 0.7, 2.5))
    out = tmp_path / "out.nii.gz"
    summary = api.convert_dicom_series(tmp_path / "series", out)
    assert summary["n_files"] == 5 and summary["size_voxels"] == [16, 16, 5]
    assert summary["spacing_mm"] == pytest.approx([0.7, 0.7, 2.5])
    assert summary["modality"] == "MR"
    assert "SYNTH" not in " ".join(str(v) for v in summary.values())  # no patient fields
    vol = io_nifti.load_image(out)
    assert vol.shape == (16, 16, 5)
    assert vol.spacing_mm == pytest.approx((0.7, 0.7, 2.5))


def test_dicom_errors_are_clear(tmp_path: Path):
    from segaudit.radiology.dicom import DicomError

    (tmp_path / "empty").mkdir()
    with pytest.raises(DicomError, match="No DICOM series"):
        api.convert_dicom_series(tmp_path / "empty", tmp_path / "o.nii.gz")
    with pytest.raises(DicomError, match="Not a folder"):
        api.convert_dicom_series(tmp_path / "missing", tmp_path / "o.nii.gz")


# --- CLI -----------------------------------------------------------------------


def test_cli_radiology_data_commands_and_sql(capsys, repo_root, minimal_config, tmp_path):
    from segaudit.cli import main

    data = {**minimal_config, "data": {"source": "synthetic_phantom", "use_synthetic": True, "synthetic": {"n_cases": 3, "shape": [24, 32, 24]}, "msd": {"url": "u", "md5": "m", "archive": "a.tar", "dirname": "D"}}}
    cfg_path = repo_root / "configs" / "r.yaml"
    cfg_path.write_text(yaml.safe_dump(data), encoding="utf-8")

    assert main(["data", "phantom", "-c", str(cfg_path)]) == 0
    assert "track 'radiology'" in capsys.readouterr().out
    assert main(["data", "inventory", "-c", str(cfg_path)]) == 0
    out = capsys.readouterr().out
    assert "n_cases" in out and "3" in out

    assert main(["sql", "-c", str(cfg_path), "SELECT COUNT(*) AS n FROM cases"]) == 0
    assert "3" in capsys.readouterr().out
    q = tmp_path / "q.sql"
    q.write_text("SELECT case_id\nFROM cases\nORDER BY case_id\nLIMIT 2", encoding="utf-8")
    csv = tmp_path / "out.csv"
    assert main(["sql", "-c", str(cfg_path), "-f", str(q), "--csv", str(csv)]) == 0
    assert list(pd.read_csv(csv).case_id) == ["phantom_000", "phantom_001"]
    assert main(["sql", "-c", str(cfg_path), "DELETE FROM cases"]) == 7  # read-only
    assert "SQL error" in capsys.readouterr().err
    assert main(["sql", "-c", str(cfg_path), "SELECT 1", "-f", str(q)]) == 2

    runs = api.query(load_config(cfg_path), "SELECT command FROM runs ORDER BY started_at")
    assert list(runs.command) == ["data phantom", "data inventory"]
