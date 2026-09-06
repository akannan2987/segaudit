# data/

Nothing in this folder is committed to Git except this note and two empty
`.gitkeep` markers. Everything else is rebuilt by running the pipeline.

| Folder | What goes here | Written by | Edited by |
|---|---|---|---|
| `raw/` | The public datasets exactly as downloaded (both tracks), plus synthetic data from the built-in generators: `synthetic_tiles/` (H&E-like tiles, labels and assembled slides — `segaudit data phantom -c configs/quick-pathology.yaml`, today) and the MRI phantom (Phase 1) | Phase 0P / Phase 1 / Phase P1 | **Nobody.** Raw files are the evidence: if a result is ever questioned, it must be traceable to an untouched source |
| `processed/` | Track R: resampled, reoriented, intensity-normalised volumes and masks. Track P: stain-normalised tiles cut from slides | Phase 2 / Phase P1–P2 | Regenerated, never hand-edited |

Why keep data out of Git: scans are large, some are subject to licence terms
that forbid redistribution, and — most importantly — a repository that
contains code plus instructions to regenerate the data is reproducible; one
that contains a snapshot of somebody's `data/` folder is not.

Where the data comes from and how to fetch it is documented in the data
tutorials (`phase-01-data.md` for scans, `phase-p1-data.md` for slides, both
arriving with their phases); the synthetic generators are documented in
`docs/04-phase-tutorials/phase-0p-two-track-foundation.md`.
