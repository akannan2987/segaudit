[← README](../README.md) · **Handbook** · [Glossary](00-glossary.md)

# The SegAudit Handbook — one document from day 0 to finished product

**Who this is for:** anyone opening this repository for the first time — and anyone returning after a break. This is the *only* document you need to keep open; every other document is linked from here, at the moment you need it, with a sentence on why.
**What it is:** a living, ordered walkthrough of the whole journey: learn the ideas → set up a machine → understand the design → build the pipeline phase by phase → release → grow it into a product. It is updated **in the same commit** as any change it describes, so it is never out of date. If it ever disagrees with reality, that is a bug — please report it.
**What it is not:** a copy of the other documents. Details live in the specialised pages; this page tells you which one to read, when, and why.

**Status legend used throughout:** ✅ done and verified · 🔨 in progress · 🔜 planned (approach written, not built).

---

## The journey at a glance

| Stage | What you get out of it | Time | Status |
|---|---|---|---|
| [0. Orient](#stage-0--orient) | You know what SegAudit is, why it matters, and the words to talk about it | 30–45 min | ✅ |
| [1. Set up your machine](#stage-1--set-up-your-machine) | Every tool installed, once, with proof it works | ~45 min | ✅ |
| [2. Understand the design](#stage-2--understand-the-design) | You can explain the architecture and use Git confidently | 1–2 h | ✅ |
| [3. Build the pipeline, phase by phase](#stage-3--build-the-pipeline-phase-by-phase) | The working system, built and understood step by step | ~8–10 weekends total | 🔨 Phase 0 ✅, Phases 1–11 🔜 |
| [4. Releases](#stage-4--releases) | Versioned, tagged, changelogged milestones | minutes per release | 🔨 v0.1.0 in preparation |
| [5. From pipeline to product](#stage-5--from-pipeline-to-product) | The evaluated path to a hosted, usable product | reading: 1 h | 🔜 documents land with Phase 0c |
| [6. Contribute and extend](#stage-6--contribute-and-extend) | You can improve SegAudit and keep its promises intact | ongoing | ✅ rules written |

If you only have **10 minutes**: read the README top section and [What is a segmentation?](../README.md#what-is-a-segmentation-start-here). **One hour**: add Stage 0 in full. **One day**: through Stage 2, ending with the hands-on exercises. After that, Stage 3 is one phase per session.

---

## Stage 0 · Orient

**Goal:** understand the problem and the vocabulary before touching a computer.
**Why this comes first:** every later page uses the same small set of terms (voxel, mask, Dice, uncertainty…). Twenty minutes here removes a hundred small confusions later.

1. Read the README from the top through [The problem this project tackles](../README.md#the-problem-this-project-tackles). *Why:* it states, in plain language, the one question the whole project answers — *which automatic outlines can be trusted, without the right answer in hand* — and why averages hide failures.
2. Skim [`00-glossary.md`](00-glossary.md) — don't memorise it; learn where things are. Keep it open in a second tab from now on. *Why:* the project's promise is that no page uses a word this file doesn't explain.
3. Read [About the data (honesty notes)](../README.md#about-the-data-honesty-notes). *Why:* knowing what this project does **not** claim (clinical performance, real trial data) is part of understanding it.

**You are done when** you can tell a friend, in your own words, what a segmentation is and why "91% average accuracy" is not a safe thing to act on.

## Stage 1 · Set up your machine

**Goal:** a fully working environment, installed once, with the same proof of success the automated tests use.
**Why one-time setup is worth 45 careful minutes:** everything afterwards — every phase, every fix, every rerun — is a short repeatable loop on top of this foundation. Rushed setup is the single biggest source of "it doesn't work on my machine".

Pick the guide for your operating system and follow it top to bottom — each explains every tool (what it is, why we use it), shows every command **with its expected output**, and ends with a checkpoint:

- [`01-setup-windows.md`](01-setup-windows.md) — PowerShell, from a blank PC.
- [`01-setup-macos.md`](01-setup-macos.md) — Terminal, from a blank Mac. Intel Macs are fully supported; the guide explains the one consequence (an older PyTorch lane) honestly.
- [`01-setup-rhel8.md`](01-setup-rhel8.md) — bash, from a fresh VM, including the no-`sudo` path.

Optional, arrives with Phase 7: `01b-setup-r.md` — R, RStudio and `renv` for the R companion (🔜).

**Exact environment rebuilds (lock files).** `requirements.txt` pins the packages we name; a *lock file* additionally pins everything they pull in. After a successful setup you can record your machine's exact environment with `python scripts/freeze_lock.py` — see [`../locks/README.md`](../locks/README.md) for what locks are for and when to use one instead of the requirements files.

**You are done when** `segaudit check-env` ends with `All required packages import. You are ready.`, `pytest` says `29 passed`, and `ruff check .` says `All checks passed!` — the checkpoint at the bottom of your guide.

## Stage 2 · Understand the design

**Goal:** know how the pieces fit *before* building them, and be fluent in the Git rhythm every phase ends with.
**Why design before building:** each phase tutorial says "add this to the analysis engine" or "this goes through the storage interface". Those sentences only carry meaning once the map is in your head.

1. [`02-architecture.md`](02-architecture.md) — the kitchen/dining-room/pantry mental model, the full diagram, what every box does and **why it exists**, and the five design rules (one-way data flow, API-first, config-driven, storage interface, seeded randomness) with what each buys. Do the hands-on section 8: you will write a real table and query it with multi-line SQL in ten minutes.
2. [`03-git-workflow.md`](03-git-workflow.md) — what Git is, the three-branch model (`master`/`beta`/`develop`), the three checks before every commit, and the per-phase push sequence explained line by line, plus every common "it went wrong" case. *Why now:* Stage 3 ends every session with exactly this sequence; it should be boring by then.

**You are done when** you can name the boxes of the diagram from memory and explain what `develop:beta` means in the push line.

## Stage 3 · Build the pipeline, phase by phase

**Goal:** the working system — data in, audited biomarkers and a review queue out — built by you, one understood step at a time.
**How each phase works, every time:** open its tutorial → read *why this phase exists* → follow the numbered steps, comparing your output with the expected output printed there → pass the checkpoint → run the three checks → commit and push with the standard sequence (printed at the end of every tutorial). Each phase is sized for one session (1.5–3 h); tutorials mark a natural mid-way stopping point.

| Phase | One line: what and why | Tutorial | Status |
|---|---|---|---|
| 0 | Foundations before features: package, config, storage+SQL, CLI, tests, CI, safety guard — so nothing later is a loose script | [`04-phase-tutorials/phase-00-skeleton.md`](04-phase-tutorials/phase-00-skeleton.md) | ✅ |
| 1 | Real data in: download + inventory the public MRI set, synthetic phantom fallback, NIfTI/DICOM I/O with geometry intact, input QA gates, the `segaudit sql` console | `phase-01-data.md` | 🔜 v0.2 |
| 2 | Make scans comparable (reorient, resample, normalise, denoise) and set the classical baseline the model must beat | `phase-02-preprocessing-baseline.md` | 🔜 v0.2 |
| 3 | Train the 3D U-Net on CPU, seeded, on patient-level splits — honestly scoreable | `phase-03-model.md` | 🔜 v0.2 |
| 4 | Score it properly: overlap *and* surface metrics, per case, worst-case gallery, failure taxonomy | `phase-04-validation.md` | 🔜 v0.3 |
| 5 | Measure the model's self-doubt: test-time augmentation + Monte Carlo dropout, calibrated | `phase-05-uncertainty.md` | 🔜 v0.3 |
| 6 | **The heart:** a reference-free quality score → triage queue with a stated operating point | `phase-06-quality-control.md` | 🔜 v0.4 |
| 7 | Would the number survive a re-scan? Perturbations, registration, minimum detectable difference | `phase-07-repeatability.md` | 🔜 v0.5 |
| 7R | Optional R companion: the same statistics independently in R over the same tables — two languages checking each other | `phase-07r-r-companion.md` | 🔜 v0.5 |
| 8 | The deliverable table: biomarkers with confidence intervals, metadata join, stratification | `phase-08-biomarkers.md` | 🔜 v0.5 |
| 8R | Optional R companion: bootstrap and stratified comparison in R, cross-checked; Quarto report | `phase-08r-r-companion.md` | 🔜 v0.5 |
| 9 | A door for humans: the Streamlit review app, review ledger, import-external-mask path, 3D Slicer/Napari guide | `phase-09-review-app.md` | 🔜 v0.6 |
| 10 | A door for programs: MCP server exposing the pipeline as agent-callable tools; grounded report drafter | `phase-10-agent-tools.md` | 🔜 v0.7 |
| 11 | Seal and ship: Docker/Podman container, HPC (Slurm) and GPU paths, release 1.0 | `phase-11-container-release.md` | 🔜 v1.0 |

**Returning after a break?** Read this table's status column, open the first 🔜 tutorial, and its *Prerequisites* line tells you if anything needs refreshing. Your local state is always recoverable: `git switch develop && git pull --ff-only origin develop`, then `segaudit check-env`.

## Stage 4 · Releases

**Goal:** every finished phase becomes a named, permanent, documented version anyone can install and cite.
**Why:** "the version on my laptop last Tuesday" is not something a reader can reproduce; `v0.3.0` is.

- The release procedure (changelog → version bump in two files → checks → tag → push with `--tags`) is in [`../CONTRIBUTING.md`](../CONTRIBUTING.md#5-release-flow), with the same steps summarised in [`03-git-workflow.md`](03-git-workflow.md#6-releases-and-tags).
- What changed in every version: [`../CHANGELOG.md`](../CHANGELOG.md).
- Current release: **v0.1.0 (foundation) — in preparation**; tagged as part of Phase 0c. 🔨

## Stage 5 · From pipeline to product

**Goal:** understand — before building any of it — what it would take to turn SegAudit into an industrialised, hosted, usable product, and in what order.
**Why a written evaluation instead of just adding tools:** every technology is a cost (setup, maintenance, complexity). The rule of this repository is *justify, don't accumulate*: each option gets a verdict — Required now / Recommended later / Optional / Not needed — **and the trigger that would change it**.

- [`05-roadmap.md`](05-roadmap.md) — the near roadmap: everything extracted-but-not-yet-built, each with its planned approach and trigger. 🔜 lands with Phase 0c.
- [`06-product-and-technology-roadmap.md`](06-product-and-technology-roadmap.md) — the product evaluation: web front end, data platform, AI components, cloud and operations, regulatory constraints of medical data, discoverability, pricing — every term explained for a newcomer, plus the end-to-end product pipeline and which pieces of today's MVP already form part of it. 🔜 lands with Phase 0c.

## Stage 6 · Contribute and extend

**Goal:** change SegAudit — fix, improve, add — without breaking its promises.

- [`../CONTRIBUTING.md`](../CONTRIBUTING.md) — the branch model, the day-to-day loop, code norms (config-driven, API-first, storage through the interface, seeded, tested, linted) and documentation norms (prerequisites, learning goal, expected output, checkpoint, glossary rule).
- The five design rules you must not break are in [`02-architecture.md`](02-architecture.md#5-the-five-design-rules), each with what it buys.
- Found a confusing sentence? That is a documentation bug and a welcome contribution by itself.

---

## The rules that keep this handbook true

1. **Same-commit updates.** Any change that alters a status, adds a document, or changes a step updates this page in the *same commit*. The pre-push habit is: three checks, then "does the Handbook still tell the truth?"
2. **Statuses are earned.** ✅ means the checkpoint was actually run and its output matched — on this project, on a real machine.
3. **No duplication.** This page links; it does not copy. If an explanation is needed, it belongs in the specialised page, and this page points at it.
4. **One entry door.** The README stays the shop window (what and why); this Handbook is the guided tour (how, in what order). Every other document assumes you arrived from here.
