[← README](../../README.md) · [Handbook](../HANDBOOK.md) · [Glossary](../00-glossary.md) · [← Phase 0](phase-00-skeleton.md) · [Architecture](../02-architecture.md)

# Phase 0P · The two-track foundation — one core, two doors

**Prerequisites:** the setup guide for your OS completed (`segaudit check-env` says ready, with the slide-reader rows present), `phase-00-skeleton.md` done, and [`02-architecture.md` section 2b](../02-architecture.md#2b-two-tracks-one-core) read once.
**Learning goal:** after this phase you understand what a *track* is and why shared code lives outside both; how a whole-slide image is stored and read with its geometry intact; what a synthetic slide dataset contains and why it exists; and how the same storage and SQL serve scans and slides — by using all of it, not by reading about it.
**Checkpoint:** you have generated a synthetic slide dataset, read one slide through two independent readers and seen them agree, queried the `cells` table with SQL, watched a failure mode change a measurable number, and the git block at the end has been pushed with three green CI runs.
**Time:** about two hours. A natural place to stop is after section 5.

---

## Contents

1. [Why this phase exists](#1-why-this-phase-exists)
2. [What was built — the map](#2-what-was-built--the-map)
3. [Walk 1: the track setting](#3-walk-1-the-track-setting)
4. [Walk 2: one set of column names for both tracks](#4-walk-2-one-set-of-column-names-for-both-tracks)
5. [Walk 3: the synthetic slide dataset](#5-walk-3-the-synthetic-slide-dataset)
6. [Walk 4: reading a whole-slide image, twice](#6-walk-4-reading-a-whole-slide-image-twice)
7. [Walk 5: failure modes on purpose](#7-walk-5-failure-modes-on-purpose)
8. [Walk 6: the same storage, the same SQL](#8-walk-6-the-same-storage-the-same-sql)
9. [What could go wrong](#9-what-could-go-wrong)
10. [What you learned](#10-what-you-learned)
11. [Commit and push](#11-commit-and-push)

---

## 1. Why this phase exists

Phase 0 built a workshop for scans. This phase adds a second delivery door — slides — **without building a second workshop.** The temptation is to copy the project and adapt it; the cost of that is two of everything: two quality-control classifiers, two review apps, two report drafters, drifting apart from the first week. SegAudit's product statement is that the audit method is the same whatever the picture, so the architecture has to say the same thing: track-specific code in two side packages, the audit core once in the middle, and a rule that a shared component is finished only when it runs on both tracks.

Doing this *before* any pipeline phase is deliberate. Retrofitting a track concept after the 3D model, the QC classifier and the app exist would mean touching every one of them; doing it now touches four small files and adds two packages.

*Everyday version:* a restaurant that starts serving fish as well as vegetables does not build a second kitchen. It adds a fish-prep station at a second door and keeps the same cooks, pans and quality checks for everything past the doors.

## 2. What was built — the map

```
src/segaudit/
├── config.py                 ~ the `track` setting (radiology | pathology), default radiology
├── schemas.py                + column names both tracks agree on
├── api.py                    ~ track-neutral; generate_synthetic(), slide_info(), tracks()
├── cli.py                    ~ --track on every command; `schemas`, `data phantom`, `slide info`
├── envcheck.py               ~ slide-reader rows
├── radiology/__init__.py     + Track R package (Phase 1 fills it)
└── pathology/
    ├── __init__.py           + Track P package
    ├── io_wsi.py             + SlideReader: OpenSlide + tiffslide backends, pyramid writer
    └── phantom_tiles.py      + synthetic H&E tiles: labels, patterns, failure modes, artefacts, slides
configs/quick-pathology.yaml  + the two-minute pathology run
tests/                        + 44 tests (73 at the time; 103 after Phase 1)
.github/workflows/ci.yml      ~ reads a synthetic slide through both backends on all three runners
```

Have VS Code open on the project and a terminal with `(.venv)` showing.

## 3. Walk 1: the track setting

Open `configs/default.yaml` and `configs/quick-pathology.yaml` side by side. The first line of each that matters:

```yaml
track: radiology      # default.yaml
track: pathology      # quick-pathology.yaml
```

**Exercise 3a — see the track, override it, break it.**

```
$ segaudit info -c configs/quick.yaml
...
track       radiology
$ segaudit info -c configs/quick.yaml --track pathology
...
track       pathology
```

The YAML says radiology; `--track` wins for one run. Now the loud failure: edit `configs/quick.yaml`, change `track: radiology` to `track: histology`, and run:

```
$ segaudit config show -c configs/quick.yaml
Configuration error: Unknown track 'histology'; choose one of: radiology, pathology
```

Put it back. Find `validate_track` in `src/segaudit/config.py`: the whole rule is ten lines, and the message names the options — a beginner who mistypes learns the right word from the error.

**Why the default is radiology.** Every configuration written before tracks existed has no `track` key. Defaulting to radiology means none of them changed meaning — which is why all 29 Phase 0 tests still pass untouched (rule: refactor without breaking).

## 4. Walk 2: one set of column names for both tracks

Open `src/segaudit/schemas.py` and run:

```
$ segaudit schemas
cases  (track: radiology; key: case_id)
  case_id               str     unique scan identifier (also the subject id here)
  ...
slides  (track: pathology; key: slide_id)
  ...
qc_scores  (track: shared; key: unit_id, run_label)
  unit_id               str     case_id / tile_id / slide_id
  unit_kind             str     case / tile / slide
  ...
```

Two kinds of table: **track tables** describe each track's own units (`cases`; `slides`, `tiles`, `cells`), and **shared tables** look identical on both tracks, keyed by `unit_id` plus `unit_kind`. That second design decision is what lets one review app and one report drafter serve both doors: they read `qc_scores` and never ask which track filled it.

**Exercise 4a — the schema check is a floor, not a ceiling.**

```
$ python
>>> import pandas as pd
>>> from segaudit import schemas
>>> schemas.check("qc_scores", pd.DataFrame({"unit_id": ["a"], "run_label": ["x"]}))
Traceback (most recent call last):
  ...
segaudit.schemas.SchemaError: Table 'qc_scores' is missing required column(s): unit_kind, qc_score, decision
>>> ok = pd.DataFrame({"unit_id": ["a"], "unit_kind": ["tile"], "run_label": ["x"], "qc_score": [0.8], "decision": ["review"], "extra": [1]})
>>> schemas.check("qc_scores", ok) is ok
True
>>> exit()
```

Missing columns fail loudly; extra columns are fine (a phase may add its own). Storage itself does not enforce this — tests and ad-hoc tables would suffer — the pipeline code calls it before writing. Find the call in `phantom_tiles.generate_dataset`.

## 5. Walk 3: the synthetic slide dataset

**The idea.** Real slides are gigabytes, licensed and slow. The generator draws small **tiles** that look enough like H&E-stained tissue to exercise every pathology code path — nuclei with **instance labels** (one number per nucleus) and **phenotype classes** (tumour, lymphocyte, stroma), three spatial arrangements, and failure modes on demand — then assembles tiles into a small **pyramidal slide** so the slide reader has something real-shaped to read. Seeded, so the same config gives the same pixels forever. Always labelled synthetic.

**Exercise 5a — generate it.**

```
$ segaudit data phantom -c configs/quick-pathology.yaml
Synthetic dataset written for track 'pathology':
  root       /Users/<you>/projects/segaudit/data/raw/synthetic_tiles
  n_slides   2
  n_tiles    8
  n_cells    600
  tables     ['slides', 'tiles', 'cells']
```

Look inside `data/raw/synthetic_tiles/`: `imagesTr/` holds the RGB tiles, `labelsTr/` the instance (`_inst.png`, 16-bit) and class (`_cls.png`) images, `slides/` the assembled `.tif` pyramids, and `dataset.json` says what is there — the same layout the radiology dataset will use, so Phase P1's inventory treats real and synthetic data alike.

Open `imagesTr/tile_synth_000_00.png` in any image viewer: pink background, purple nuclei, a cluster. Open the matching `_cls.png` — it looks black because the values are 0–3; that is correct for a label image.

**Exercise 5b — the three spatial patterns, measured.** Run this once; it is the seed of Phase P8's spatial statistics.

```
$ python
>>> import numpy as np
>>> from segaudit.pathology import phantom_tiles as pt
>>> def lymphocyte_to_tumour(pattern, seed=1):
...     t = pt.make_tile(seed, pt.TileSpec(pattern=pattern))
...     tum = t.cells[t.cells.class_name == "tumour"][["cx", "cy"]].to_numpy()
...     lym = t.cells[t.cells.class_name == "lymphocyte"][["cx", "cy"]].to_numpy()
...     d = np.sqrt(((lym[:, None] - tum[None]) ** 2).sum(-1)).min(axis=1)
...     return round(float(d.mean()), 1)
...
>>> {p: lymphocyte_to_tumour(p) for p in pt.PATTERNS}
{'clustered': 55.3, 'dispersed': 20.3, 'infiltrating': 14.4}
```

(Your numbers differ slightly by seed; the *order* is the point.) In a **clustered** tile lymphocytes are kept away from the tumour nest; in an **infiltrating** tile they sit on and inside its boundary. The mean distance from each lymphocyte to its nearest tumour cell ranks the patterns exactly as a pathologist would describe "excluded" versus "inflamed". A test pins this ordering.

## 6. Walk 4: reading a whole-slide image, twice

**The idea.** A whole-slide image is stored as a **pyramid** of zoom levels, read region by region; its most important number is **microns per pixel (mpp)** — the scale bar. SegAudit reads slides through one interface with two independent backends: **OpenSlide** (the native library, installed as a pip wheel) and **tiffslide** (pure Python). If they disagree, something is wrong with a file or a reader; if they agree, you can trust the geometry.

**Exercise 6a — same file, two readers.**

```
$ segaudit slide info data/raw/synthetic_tiles/slides/synth_000.tif --backend openslide
file           data/raw/synthetic_tiles/slides/synth_000.tif
backend        openslide
size (px)      256 x 256
levels         2: 256x256, 128x128
mpp (x, y)     0.5, 0.5
magnification  20
$ segaudit slide info data/raw/synthetic_tiles/slides/synth_000.tif --backend tiffslide
...
backend        tiffslide
size (px)      256 x 256
levels         2: 256x256, 128x128
mpp (x, y)     0.5, 0.5
magnification  20
```

Identical geometry from two code bases that share nothing. Without `--backend`, `auto` tries OpenSlide first and falls back to tiffslide — so a machine where the native library cannot load still reads slides.

**Exercise 6b — read a region, at two levels.**

```
$ python
>>> from segaudit.pathology.io_wsi import open_slide
>>> r = open_slide("data/raw/synthetic_tiles/slides/synth_000.tif")
>>> r.info.level_dimensions
((256, 256), (128, 128))
>>> r.read_region(0, 0, 0, 64, 64).shape      # level 0: 64 px = 32 µm across
(64, 64, 3)
>>> r.read_region(0, 0, 1, 64, 64).shape      # level 1: 64 px = 64 µm across — same pixels, twice the ground
(64, 64, 3)
>>> r.info.voxel = None  # frozen dataclass: geometry cannot be edited by accident
Traceback (most recent call last):
  ...
dataclasses.FrozenInstanceError: cannot assign to field 'voxel'
>>> r.close(); exit()
```

Coordinates for `read_region` are always in **level-0 pixels**, whichever level you read — both libraries' convention, kept as-is so their documentation applies. The frozen `SlideInfo` is the slide twin of the frozen `Volume` in Track R: nothing downstream can "fix" the geometry in passing.

**Why the writer exists.** `write_pyramidal_tiff` turns an RGB array into a multi-page pyramid with mpp in three places (TIFF resolution tags, JSON metadata, an Aperio-style description) — because OpenSlide and tiffslide each read a different one. That is how tests and CI prove both readers on every platform with nothing downloaded. Real datasets arrive in Phase P1.

## 7. Walk 5: failure modes on purpose

The quality-control layer (Phase P5) has to catch wrong segmentations. Wrong segmentations must therefore be manufactured, with known truth. Two kinds:

- **Label corruption** — what a model gets wrong: `missing_nuclei`, `merged_nuclei`, `false_positives`, `shifted_boundaries`.
- **Image artefacts** — what acquisition gets wrong: `blur`, `stain_shift`, `fold`, `pen_mark`.

**Exercise 7a — each corruption changes what it claims.**

```
$ python
>>> import numpy as np
>>> from segaudit.pathology import phantom_tiles as pt
>>> t = pt.make_tile(9, pt.TileSpec()); rng = np.random.default_rng(0)
>>> n0, fg0 = int(t.instances.max()), int((t.instances > 0).sum())
>>> for mode in pt.LABEL_FAILURE_MODES:
...     inst, cls = pt.corrupt_labels(t.instances, t.classes, mode, rng)
...     print(f"{mode:<20} nuclei {n0:>3} -> {int(inst.max()):>3}   labelled pixels {fg0:>5} -> {int((inst > 0).sum()):>5}")
...
missing_nuclei       nuclei  94 ->  66   labelled pixels  8493 ->  5535
merged_nuclei        nuclei  94 ->  31   labelled pixels  8493 ->  8493
false_positives      nuclei  94 -> 120   labelled pixels  8493 -> 10622
shifted_boundaries   nuclei  94 ->  94   labelled pixels  8493 ->  6513
>>> exit()
```

Read the table as a QC engineer would: *missing* drops the count and the area; *merged* keeps every pixel but collapses the count (touching nuclei drawn as one — the classic instance-segmentation failure); *false positives* inflate both; *shifted boundaries* keep the count and change the areas. Each mode moves a different measurable feature, which is exactly what a failure predictor has to learn to read.

**Exercise 7b — see the artefacts.** Save a strip and open it:

```
$ python -c "
import numpy as np; from PIL import Image
from segaudit.pathology import phantom_tiles as pt
t = pt.make_tile(7, pt.TileSpec(pattern='infiltrating')); rng = np.random.default_rng(1)
strip = np.concatenate([t.image] + [pt.apply_artefact(t.image, m, rng) for m in pt.IMAGE_ARTEFACTS], axis=1)
Image.fromarray(strip).save('outputs/artefacts.png'); print('wrote outputs/artefacts.png')"
```

Five panels: clean, blurred (out of focus), stain-shifted (another lab), a dark diagonal fold, a pen stroke. Phase P1's slide-level QC must flag the last four; this is its test bed.

## 8. Walk 6: the same storage, the same SQL

Nothing new to learn here — that is the lesson. The tables you wrote in Phase 0 exercise 5b and the `cells` table you just generated go through the same `Storage` interface and answer the same SQL.

```
$ python
>>> from segaudit import api
>>> cfg = api.load("configs/quick-pathology.yaml"); store = api.storage_for(cfg)
>>> store.list_tables()
['cells', 'slides', 'tiles']
>>> store.query("""
...     SELECT t.pattern,
...            COUNT(DISTINCT t.tile_id)                          AS tiles,
...            COUNT(c.cell_id)                                   AS cells,
...            ROUND(AVG(CASE WHEN c.class_name = 'lymphocyte' THEN 1.0 ELSE 0 END), 2) AS lymphocyte_share
...     FROM tiles t JOIN cells c USING (tile_id)
...     GROUP BY t.pattern ORDER BY t.pattern
... """)
       pattern  tiles  cells  lymphocyte_share
0    clustered      4    339              0.39
1 infiltrating      4    261              0.22
>>> exit()
```

A join across two pathology tables in a few lines of the same SQL that will later join `qc_scores` to `cells`. Phase P8 turns queries like this into TIL density per square millimetre — by multiplying counts with `mpp`² from the `tiles` table. That is why mpp is stored next to every tile.

## 9. What could go wrong

- **`segaudit slide info` says `OpenSlide is not available`** but tiffslide works. The native library failed to load on this machine — see your setup guide's troubleshooting T13. Nothing is blocked; `auto` already fell back.
- **`data phantom` on `configs/quick.yaml` prints "Not available yet: … arrives with Phase 1".** Correct and deliberate: the radiology phantom is Phase 1's; the pathology one exists today. Exit code 3, on purpose, so a script cannot mistake "not yet" for "done".
- **Tests take much longer than before.** The tile generator draws ~100 nuclei per tile with NumPy; on a slow disk the first run can take 20–30 s. Subsequent runs are faster.
- **A test in `test_io_wsi.py` fails only on one operating system.** Both backends are compiled or platform-dependent; paste the failing assertion — the fixture writes a tiny synthetic pyramid, so the failure is in a reader, not in your data.
- **The `_cls.png` label image "looks black".** Values 0–3 on a 0–255 scale. Multiply by 60 in Python to see it, or trust the `cells` table.

## 10. What you learned

- What a track is, why the default is radiology, and why shared code lives outside both packages.
- One set of column names (`schemas.py`) is what lets one app and one report serve two very different pictures.
- How a whole-slide image is stored (pyramid, mpp, level-0 coordinates) and why two independent readers agreeing is worth more than one.
- What a synthetic slide dataset contains, how spatial patterns are measurable, and how failure modes are manufactured with known truth.
- That storage and SQL did not change at all — the strongest evidence that the shared core is genuinely shared.

Next: Phase 1 (real scans) and Phase P1 (real slides), in that order — the same foundations, both doors.

## 11. Commit and push

The three checks, then the sequence. (If you followed this page without changing any file, `git status` is clean and there is nothing to commit; the generated data and `outputs/artefacts.png` are git-ignored.)

```bash
ruff check .
pytest
python scripts/check_public_safe.py     # must print "SAFE TO PUSH"

git switch develop
git add -A
git commit -m "phase 0P: two-track foundation — documentation, glossary §15, roadmaps, tutorial"
git push origin develop develop:beta develop:master
# add --tags only when a release tag was created in this phase

git switch master
git pull --ff-only origin master
git switch develop
```

reply `continue` for the next phase
