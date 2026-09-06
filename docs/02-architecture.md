[← README](../README.md) · [All docs in order](../README.md#the-tutorial-in-order) · [Glossary](00-glossary.md)

# 02 · Architecture, explained from scratch

**Prerequisites:** none to read; the setup guide for your OS to run the commands in section 8.
**Learning goal:** after this page you can explain what every part of SegAudit does, why it exists, how data flows from a downloaded scan *or slide* to a reviewed decision, why there are two **tracks** and one **shared core**, and why the code is arranged the way it is — even if you have never built software before.
**Checkpoint:** you can explain, in your own words, the difference between a *backend*, a *frontend* and *storage*; name the boxes in the diagram; say what a *track* is and which code is shared; and state the six design rules and what each one buys.

---

## Contents

1. [What SegAudit is, in one honest sentence](#1-what-segaudit-is-in-one-honest-sentence)
2. [The three words you must know first](#2-the-three-words-you-must-know-first)
2b. [Two tracks, one core](#2b-two-tracks-one-core)
3. [The diagram](#3-the-diagram)
4. [What each box does, and why it exists](#4-what-each-box-does-and-why-it-exists)
5. [The six design rules](#5-the-six-design-rules)
6. [The code as it stands today](#6-the-code-as-it-stands-today)
7. [How future doors plug into the same vault](#7-how-future-doors-plug-into-the-same-vault)
8. [See the architecture with your own hands](#8-see-the-architecture-with-your-own-hands)
9. [Where each phase lives](#9-where-each-phase-lives)
10. [Checkpoint](#10-checkpoint)

---

## 1. What SegAudit is, in one honest sentence

SegAudit takes a medical picture — a 3D brain scan, or a 2D tumour slide — outlines structures on it automatically, and then — the part that matters — works out *how much to trust those outlines* without being told the right answer, so that a human only has to check the ones most likely to be wrong.

That's it. Everything below is *how*, one plain step at a time.

If you know nothing about medicine or software, here is the everyday version:

> A factory has a machine that stamps out parts. Nearly all are fine; a few are warped. Checking every part by hand would be as slow as making them by hand — but shipping warped parts is worse. SegAudit is the inspector who, without a reference part in hand, looks at each one and says: "these fourteen look suspicious, pull them; the rest are fine." Then it keeps a ledger of what was pulled and why.

## 2. The three words you must know first

Almost every confusing software conversation becomes clear once you know these three words. We use a restaurant as the running analogy, because it maps perfectly.

**Backend — "the kitchen."** Everything that happens behind the scenes: preparing, cooking, plating. Customers never enter the kitchen. In software, the backend is the code that does the real work — reading scans, training the model, computing scores. In SegAudit, the backend is the whole pipeline in `src/segaudit/`.

**Frontend — "the dining room."** The part a person sits in and interacts with: the menu, the table, the plate. In software, it is the screen someone looks at and clicks. In SegAudit, the frontend is the **review app** (Phase 9): a reviewer scrolls the triage queue, looks at slices, and clicks accept or flag.

**Storage — "the pantry."** Where finished things are put so they can be found again quickly and precisely. In SegAudit, storage is a folder of **Parquet** tables (a compact, typed table format) that can be questioned in **SQL** through **DuckDB** — think of SQL as a very polite, very literal way of saying "bring me the ten cases with the lowest quality score."

The three words, and the counter between them, as one picture:

```mermaid
flowchart LR
    subgraph K["backend — the kitchen"]
        P["pipeline code<br/>src/segaudit/"]
    end
    P --- API["api.py<br/>the counter"]
    API -.-> D1["command line"]
    API -.-> D2["review app"]
    API -.-> D3["agent tools"]
    P --> S[("storage — the pantry<br/>Parquet + SQL")]
    S -.-> D1
    S -.-> D2
    S -.-> D3
```

One more, because it appears constantly:

**API — "the counter between kitchen and dining room."** The fixed set of things you can ask the kitchen for. In SegAudit it is one Python file, `src/segaudit/api.py`. The command line, the review app and (later) the agent tools all order through that counter. None of them cook.

## 2b. Two tracks, one core

![Two input doors, radiology and pathology, feed one shared core](img/fig_two_tracks.svg)

A **track** is an input door. There are two:

- **Track R — radiology.** 3D volumes (MRI now; CT and PET on the roadmap). A
  file carries voxel spacing, orientation and an affine; the unit of work is a
  *case* (one scan).
- **Track P — pathology.** 2D whole-slide images and the tiles cut from them
  (H&E, IHC, multiplex immunofluorescence, spatial transcriptomics aligned to
  H&E). A file carries microns per pixel, magnification and a pyramid of zoom
  levels; models work on *tiles*, reviewers decide about *slides*.

Everything that depends on *which kind of picture* lives inside a track's
package (`src/segaudit/radiology/`, `src/segaudit/pathology/`): reading files
with their geometry, the synthetic test data, preprocessing, the segmentation
models, and — on Track P only — stain handling, foundation-model embeddings,
cell graphs and spatial statistics. Everything that works on *any*
segmentation — uncertainty, the quality-control score, triage, repeatability,
biomarker tables, the benchmark harness, storage, the review app, the agent
tools — lives once, at the top level of the package, outside both.

Three consequences you will meet everywhere:

1. **The configuration names the track** (`track: radiology` or `pathology`;
   `--track` overrides it for one run). Only track-specific code reads it; the
   shared core never does.
2. **Shared tables have shared column names.** `schemas.py` fixes them:
   `unit_id` + `unit_kind` (`case` / `tile` / `slide`) instead of `case_id`
   here and `tile_id` there, so one review app and one report drafter serve
   both tracks.
3. **A shared component counts as finished only when demonstrated on both
   tracks.** A QC method that works on brain MRI and on tumour slides is a
   method; one that works on one is a trick.

*Everyday version:* one kitchen with two delivery doors. Vegetables arrive at
one, fish at the other; each door has its own prep station (peel vs fillet).
Past the prep stations, the same cooks, pans and quality checks handle
everything — and a dish is only on the menu once it has been cooked from both.

## 3. The diagram

GitHub renders this automatically. Data flows top to bottom; dashed boxes are the doors people and programs use.

```mermaid
flowchart TD
    subgraph R["Track R — scans (src/segaudit/radiology/)"]
        A1["Public MRI dataset<br/>NIfTI volumes + expert masks"] -->|Phase 1| B1["data/raw/"]
        S1["MRI phantom generator"] --> B1
        B1 -->|Phase 2: reorient, resample,<br/>normalise, denoise| C1["data/processed/"]
        C1 --> D1["Classical baseline"]
        C1 --> E1["3D U-Net (MONAI)"]
    end
    subgraph P["Track P — slides (src/segaudit/pathology/)"]
        A2["Public slide datasets<br/>WSI + tile labels"] -->|Phase P1| B2["data/raw/"]
        S2["Synthetic H&E tiles<br/>+ assembled slides"] --> B2
        B2 -->|Phase P1–P2: tissue detection,<br/>tiling, stain normalisation| C2["tiles"]
        C2 --> D2["Classical baselines<br/>(watershed nuclei, tissue)"]
        C2 --> E2["Nuclei + tissue models,<br/>foundation-model embeddings"]
    end
    D1 & E1 & D2 & E2 --> F["SHARED · validation + benchmark harness<br/>Dice · HD95 · NSD · AJI · PQ · F1"]
    F --> U["SHARED · uncertainty<br/>TTA · MC dropout · calibration"]
    U --> G["SHARED · reference-free QC classifier<br/>triage + operating point (tile → slide)"]
    F --> H["SHARED · repeatability → MDD<br/>biomarker table with CIs"]
    G --> ST[("SHARED · storage<br/>Parquet + DuckDB SQL")]
    H --> ST
    ST --> API["api.py — the counter"]
    API -.-> CLI["command line<br/>incl. SQL console"]
    API -.-> APP["review app<br/>slices · tiles · slides"]
    API -.-> MCP["agent tools (MCP)<br/>+ grounded report drafter"]
    ST -.-> RC["R companion (optional)"]
```

## 4. What each box does, and why it exists

**Public MRI dataset (the source).** 394 brain scans with expert-drawn outlines of the hippocampus, published for research under a licence that lets anyone use them. Why this one: the scans are tiny, so everything runs on a laptop; and the target is genuinely hard, so real failures exist to detect. *A practice exam with the answer key attached.*

**Synthetic phantom generator.** A program that draws hippocampus-like blobs into a noisy volume and writes the matching mask. Why it exists: the tests and the first walkthrough must run with no download, and we need failure modes *on demand* — "make this case with half the structure missing" — to prove the quality-control layer catches them. Always labelled synthetic. *A crash-test dummy.*

**Public slide datasets and synthetic H&E tiles (Track P sources).** Tissue and nuclei datasets with expert labels, one real gigapixel slide for the end-to-end demo, and — for tests, CI and the first walkthrough — a synthetic tile generator that draws H&E-like nuclei with instance and phenotype labels, three spatial arrangements, and failure modes and artefacts on demand, then assembles tiles into synthetic pyramidal slides. *The same crash-test dummy, in the other department.*

**`data/raw/` (the evidence locker).** Exactly what was downloaded or generated. Never edited by code. Why: if a number is ever questioned, we must be able to walk it back to an untouched source. This is **provenance**, and in regulated analytics it is non-negotiable. *The sealed evidence bag.*

**`tiles` (Track P's processed layer).** Whole-slide images are far too big to load; the pipeline detects tissue, cuts square tiles at a chosen microns-per-pixel, and normalises stain colours so different labs look alike. Every tile row remembers its slide and its position, so tile-level results can be aggregated back to the slide. *Cutting the loaf into slices you can actually hold.*

**`data/processed/`.** The same scans after preprocessing: reoriented to one axis convention, resampled to one voxel size, brightness normalised, optionally denoised. Why a separate folder: preprocessing is a set of decisions, and decisions must be visible and reversible. Delete this folder, rerun, and it comes back identical. *The washed and chopped ingredients, kept apart from the raw ones.*

**Classical baseline.** Thresholding plus shape clean-up — the simplest segmentation that could work. Why: a deep model that cannot beat this has not earned its complexity, and the baseline's failures are easy to understand, which helps interpret the model's. *Timing yourself on foot before judging the bicycle.*

**3D U-Net.** The neural network that draws the outline. Trained on CPU with a fixed seed, on a patient-level split, so the score on unseen cases is honest. Why MONAI: it keeps scan and mask in step through every transform, which is exactly where hand-written code goes silently wrong.

**Validation + uncertainty.** Two jobs in one box. *Validation* scores the model against the expert masks it has never seen, with overlap (Dice) *and* surface metrics (HD95, NSD), per case — not just an average. *Uncertainty* asks the model the same question many times (test-time augmentation, Monte Carlo dropout) and measures how much it disagrees with itself. Why together: the uncertainty numbers are the raw material the next box learns from.

**Reference-free QC classifier.** A small, interpretable model that learns, from uncertainty and shape features alone, to predict "this outline is probably wrong" — *without seeing the expert mask*. Calibrated, then turned into a triage queue with a chosen operating point: "review these N; auto-accept the rest, with this residual risk." Why this is the heart of the project: in real use nobody has drawn the answer, so this is the only kind of QC that can exist.

**Repeatability study + biomarker table.** Re-acquires each scan in simulation (noise, resolution, head rotation with re-registration), re-measures the volume, and reports the smallest change distinguishable from noise — the *minimum detectable difference*. Produces the final biomarker table with confidence intervals and a QC flag per case. Why: a measurement without a repeatability figure cannot support a decision.

**Storage.** Every table the pipeline produces — metrics, uncertainty, QC scores, biomarkers, review decisions, run records, and on Track P the `slides`, `tiles` and `cells` tables — as Parquet files behind one interface, queryable in SQL. Shared tables use the same column names on both tracks (`schemas.py`). Why one interface: so the pipeline never knows *where* tables live, and swapping in a database server later is one new class, not a rewrite.

**`api.py` — the counter.** Every capability as a plain Python function. Why one place: if logic lived in the command line, the app would copy it; if in the app, a service could not reuse it. One vault, many doors.

**The doors.** *Command line* — for you, today, including a read-only SQL console. *Review app* — for a reviewer, Phase 9. *Agent tools* — for a program, Phase 10: an MCP server that lets an agent run an audit, query the ledger and draft a report grounded in computed numbers. *R companion* — optional, Phases 7 and 8: independent implementations of the statistics reading the very same Parquet tables, so two languages checking each other's arithmetic becomes a validation step.

## 5. The six design rules

Each rule is a sentence, an analogy, and what it buys.

```mermaid
flowchart TD
    R1["1 · one-way data flow"] --> BUY["what they buy together:<br/>delete everything but data/raw/ + code,<br/>rerun, get identical results —<br/>and add new doors without rewrites"]
    R2["2 · API-first"] --> BUY
    R3["3 · config, not code"] --> BUY
    R4["4 · storage via interface"] --> BUY
    R5["5 · seeded randomness"] --> BUY
    R6["6 · shared core outside both tracks"] --> BUY
```

**1. Data flows one way, and no step edits its own input.** Top to bottom in the diagram; `raw/` feeds `processed/`, never the reverse. *A recipe where you never put chopped onions back in the onion bag.* **Buys:** delete everything except `data/raw/` and the code, rerun, get identical results. That property — reproducibility — is the baseline expectation in regulated analytics.

**2. Every capability is a function in `api.py`; doors contain no logic.** *One kitchen, many counters.* **Buys:** a future web front end, cloud service or agent calls the same functions the command line calls today, with no rewrite.

**3. No path, seed, threshold or size lives in code — only in `configs/*.yaml`.** *The recipe card, not scribbles on the pan.* **Buys:** the same pipeline runs on a laptop, a server or a cloud machine by swapping one file; and every run records which file it used.

**4. Tables are written and read only through the `Storage` interface.** *Hand paperwork to the filing clerk; never open the cabinet yourself.* **Buys:** Parquet today, a database server tomorrow, without touching the pipeline. Also: read-only SQL for humans and agents, enforced in one place.

**5. Anything random takes its seed from the config; same config + same code = same tables.** *Shuffling the deck the same way twice.* **Buys:** two people on two machines get the same numbers (within a dependency lane), so a disagreement is always a real bug, never "randomness".

**6. Track-specific code lives in its track's package; shared code lives once, outside both, and is demonstrated on both.** *One kitchen, two delivery doors.* **Buys:** the audit layer is provably modality-agnostic, nothing is implemented twice, and adding a third door (CT, ultrasound) means one new package, not a fork.

## 6. The code as it stands today

Phase 0 built the foundations only. Here is every file in `src/segaudit/` and what it is for; open each alongside this page.

| File | Job | Read it for |
|---|---|---|
| `__init__.py` | Holds the version string and a one-paragraph statement of purpose | How a package announces itself |
| `config.py` | Reads a YAML file, checks the essentials are present, turns relative paths into absolute ones for your operating system | Why paths in the YAML use forward slashes and still work on Windows |
| `storage.py` | The `Storage` interface and its one implementation, `LocalParquetStorage`, plus `open_storage(cfg)` | How an *interface* lets the backend change without the pipeline noticing; how `query()` makes SQL read-only |
| `envcheck.py` | Imports every dependency and reports versions and which phase needs it | Why "missing" is only alarming from that phase on |
| `schemas.py` | The column names every table agrees on: `cases`, `slides`, `tiles`, `cells`, and the shared `case_metrics`, `qc_scores`, `review_ledger`, `runs` | Why one review app can serve both tracks |
| `api.py` | `version`, `tracks`, `load`, `storage_for`, `initialise_workspace`, `generate_synthetic`, `slide_info` | Rule 2 made concrete — later phases add functions here and nowhere else; track-specific ones dispatch on `cfg.track` |
| `radiology/` | Track R package — declares the track; Phase 1 fills it | Where scan-only code will live |
| `pathology/io_wsi.py` | One `SlideReader` interface, two backends (OpenSlide, tiffslide), a pyramid writer | How geometry (mpp, magnification, levels) is preserved, and why two readers |
| `pathology/phantom_tiles.py` | Synthetic H&E tiles with labels, spatial patterns, failure modes, artefacts; tables and assembled slides | The pathology crash-test dummy |
| `cli.py` | `segaudit info / check-env / config show / init / schemas / data phantom / slide info`, all with `--track` — each a few lines calling `api` | What "a thin door" looks like in practice |

And the files around the code:

| File | Job |
|---|---|
| `configs/default.yaml`, `configs/quick.yaml`, `configs/quick-pathology.yaml` | The real run and the two-minute synthetic runs, one per track. Later phases add their sections here |
| `tests/` | 73 checks that the modules keep their promises; run on a temporary folder with synthetic data so nothing real is ever touched or downloaded |
| `scripts/check_public_safe.py` | Refuses the push if a secret, a data file or a personal path would be published |
| `.github/workflows/ci.yml` | Runs lint, environment check, both slide readers on a synthetic slide, tests and the safety script on Windows, macOS and Linux for every push |

## 7. How future doors plug into the same vault

Nothing below exists yet; this is the shape they will take, so you can see why today's rules matter.

- **A web front end** (evaluated in `06-product-and-technology-roadmap.md`) would call `api.audit_case(...)` over a thin web layer. It would not import `storage.py` directly; it would ask the API.
- **A hosted service** would run the same `api` functions on a server with a different `Storage` class (a database) selected in the config — rule 3 and rule 4 together.
- **The MCP server** (Phase 10) is literally a list of `api` functions with input/output schemas attached. Nothing to invent.
- **The R companion** never calls Python; it reads the Parquet files that rule 4 guarantees exist in a known place, with known column types.

## 8. See the architecture with your own hands

Ten minutes, with the venv active, in the project folder. This exercises rules 3 and 4 before any real data exists.

**8a. Watch the config become absolute paths for your machine.**

```
$ segaudit config show -c configs/quick.yaml
```

Compare the `paths` block with `configs/quick.yaml`: `outputs/quick` became a full path in your operating system's style. That is `config.py` doing rule 3.

**8b. Put a table into storage and question it with SQL — including a multi-line query.**

Start Python:

```
$ python
```

Type (or paste) the following; lines starting with `>>>` are the prompt:

```python
>>> import pandas as pd
>>> from segaudit import api
>>> cfg = api.load("configs/quick.yaml")
>>> store = api.storage_for(cfg)
>>> store.write_table("demo_cases", pd.DataFrame({
...     "case_id": ["c01", "c02", "c03", "c04"],
...     "dice":    [0.91, 0.42, 0.88, 0.79],
...     "flagged": [False, True, False, True],
... }))
>>> store.list_tables()
['demo_cases']
>>> store.query("""
...     SELECT case_id, dice
...     FROM demo_cases
...     WHERE flagged
...     ORDER BY dice ASC
... """)
  case_id  dice
0     c02  0.42
1     c04  0.79
>>> store.query("DELETE FROM demo_cases")
Traceback (most recent call last):
  ...
duckdb.BinderException: Binder Error: Can only delete from base table
>>> exit()
```

What you just saw: a table written through the interface (rule 4), found again by name, questioned with a multi-line SQL statement, and protected from being modified by SQL. The file itself is `outputs/quick/tables/demo_cases.parquet`; you can delete it, and nothing else in the project knows or cares.

**8c. The other door, in one minute.**

```
$ segaudit data phantom -c configs/quick-pathology.yaml
Synthetic dataset written for track 'pathology':
  root       .../data/raw/synthetic_tiles
  n_slides   2
  n_tiles    8
  n_cells    600
  tables     ['slides', 'tiles', 'cells']
$ segaudit slide info data/raw/synthetic_tiles/slides/synth_000.tif
file           data/raw/synthetic_tiles/slides/synth_000.tif
backend        openslide
size (px)      256 x 256
levels         2: 256x256, 128x128
mpp (x, y)     0.5, 0.5
magnification  20
```

Same storage, same SQL, other track: `store.query("SELECT pattern, COUNT(*) FROM tiles GROUP BY pattern")` in a Python session with `cfg = api.load("configs/quick-pathology.yaml")`. The full walkthrough is [`04-phase-tutorials/phase-0p-two-track-foundation.md`](04-phase-tutorials/phase-0p-two-track-foundation.md).

**8d. Clean up.**

```
$ rm outputs/quick/tables/demo_cases.parquet        # Windows: del outputs\quick\tables\demo_cases.parquet
```

## 9. Where each phase lives

| Phase | Guide | Layer of the diagram |
|---|---|---|
| 0 | `04-phase-tutorials/phase-00-skeleton.md` | Foundations: api, config, storage, CLI, tests, CI |
| 0P | `04-phase-tutorials/phase-0p-two-track-foundation.md` | Track setting, schemas, both subpackages, slide reader, synthetic tiles |
| 1 / P1 | `phase-01-data.md` / `phase-p1-data.md` | Sources → `data/raw/`, phantoms, tiling, input QA, SQL console |
| 2 / P2 | `phase-02-preprocessing-baseline.md` / `phase-p2-stain-baselines.md` | `data/processed/` and tiles; classical baselines |
| 3 / P3 | `phase-03-model.md` / `phase-p3-models.md` | 3D U-Net; nuclei + tissue models |
| 4 / P4 | `phase-04-validation.md` / `phase-p4-validation-benchmark.md` | Validation; shared benchmark harness |
| 5 | `phase-05-uncertainty.md` | Uncertainty (shared code, first on scans) |
| 6 / P5 / P6 | `phase-06-quality-control.md` / `phase-p5-quality-control.md` / `phase-p6-representation.md` | QC classifier, triage on both; foundation-model embeddings |
| 7 / P10 | `phase-07-repeatability.md` (+ R twin) / `phase-p10-repeatability.md` | Repeatability, minimum detectable difference, both tracks |
| 8 / P7 / P8 | `phase-08-biomarkers.md` (+ R twin) / `phase-p7-cell-graphs.md` / `phase-p8-spatial-biomarkers.md` | Biomarker tables; cell graphs; spatial statistics |
| 9 / P9 | `phase-09-review-app.md` / `phase-p9-multimodal.md` | Review app door (both tracks); multimodal |
| 10 | `phase-10-agent-tools.md` | Agent tools door |
| 11 / P11 | `phase-11-container-release.md` / `phase-p11-technical-report.md` | Container, HPC/GPU paths; technical report; 1.0 |

## 10. Checkpoint

You can say, without looking: the kitchen is `src/segaudit/` with two delivery doors (`radiology/`, `pathology/`) and one shared core outside both, the counter is `api.py`, the pantry is Parquet-plus-DuckDB behind `Storage` with column names fixed in `schemas.py`, the doors for people and programs are the command line, the review app, the agent tools and the R companion; data flows one way; every setting is in YAML; every table goes through the interface; every random thing is seeded; every shared component is shown on both tracks. If any of those is fuzzy, reread the matching part of section 4 or 5 — then move on to [`03-git-workflow.md`](03-git-workflow.md).
