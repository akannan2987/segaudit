# data/

Nothing in this folder is committed to Git except this note and two empty
`.gitkeep` markers. Everything else is rebuilt by running the pipeline.

| Folder | What goes here | Written by | Edited by |
|---|---|---|---|
| `raw/` | The public datasets exactly as downloaded, plus synthetic data from the built-in generators. Track R: `Task04_Hippocampus/` (the checksummed archive `Task04_Hippocampus.tar` next to it) and `synthetic_phantom/`. Track P: `synthetic_tiles/` (H&E-like tiles, labels and assembled slides); public slide datasets arrive with Phase P1 | `segaudit data download` / `data phantom` (both tracks) | **Nobody.** Raw files are the evidence: if a result is ever questioned, it must be traceable to an untouched source |
| `processed/` | Track R: resampled, reoriented, intensity-normalised volumes and masks. Track P: stain-normalised tiles cut from slides | Phase 2 / Phase P1–P2 | Regenerated, never hand-edited |

Why keep data out of Git: scans are large, some are subject to licence terms
that forbid redistribution, and — most importantly — a repository that
contains code plus instructions to regenerate the data is reproducible; one
that contains a snapshot of somebody's `data/` folder is not.

Where the data comes from and how to fetch it is documented in the data
tutorials: [`phase-01-data.md`](../docs/04-phase-tutorials/phase-01-data.md)
for scans (download, checksum, inventory, QA gates, DICOM conversion), and
`phase-p1-data.md` for slides (arriving with Phase P1); the synthetic
generators are documented in
[`phase-0p-two-track-foundation.md`](../docs/04-phase-tutorials/phase-0p-two-track-foundation.md)
and [`phase-01-data.md`](../docs/04-phase-tutorials/phase-01-data.md).

**De-identified data only.** DICOM headers can identify a person. The
converter records only modality, scanner and geometry tags, and nothing that
identifies anyone belongs under `data/` — the safety script refuses to publish
scan files, but the responsibility is yours before that.
