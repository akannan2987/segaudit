"""Track R — radiology: 3D volumes (MRI now; CT and PET on the roadmap).

Everything that only makes sense for *scans* lives here: reading NIfTI and
DICOM with their geometry, the MRI phantom generator, volume preprocessing,
the 3D segmentation model. Everything that works on *any* segmentation —
uncertainty, quality control, triage, repeatability, biomarker tables — lives
one level up, in the shared core, and is deliberately kept out of this
package.

Phase 1 (data) fills this package; at the two-track foundation it declares
the track and nothing else.
"""

TRACK = "radiology"
UNIT_KIND = "case"  # the unit a metric or decision refers to on this track
