# Contributing to SegAudit

Thanks for reading this far. SegAudit is built in public and documented so that
a complete beginner can rebuild it from scratch; contributions that keep that
promise are the most valuable kind. This page covers how the repository is
organised, how changes flow from an idea to a release, and the norms I hold
myself to.

## Contents

1. [Ways to contribute](#1-ways-to-contribute)
2. [Branch model](#2-branch-model)
3. [The day-to-day loop](#3-the-day-to-day-loop)
4. [The push sequence (verbatim)](#4-the-push-sequence-verbatim)
5. [Release flow](#5-release-flow)
6. [Code norms](#6-code-norms)
7. [Documentation norms](#7-documentation-norms)
8. [Review norms](#8-review-norms)

## 1. Ways to contribute

- **Report a bump.** If a setup step did not work on your machine, open an
  issue with your operating system, Python version and the exact error. Setup
  bugs are documentation bugs and get fixed first.
- **Improve a tutorial.** If a sentence confused you, it will confuse the next
  reader. A pull request that adds one clarifying sentence is welcome.
- **Add a phase or a feature.** Check `docs/05-roadmap.md` first; the planned
  approach for each item is written there so work is not duplicated.

## 2. Branch model

Three long-lived branches:

| Branch | Role | Who pushes |
|---|---|---|
| `master` | The stable, released version. What a stranger should clone. | Only via the push sequence below |
| `beta` | A preview of the next release; kept identical to `master` between releases | Same |
| `develop` | Where all day-to-day work happens | Me, and pull requests |

All work happens on **`develop`**. `beta` and `master` are never edited
directly; they are fast-forwarded from `develop` in one push. A `--ff-only`
pull afterwards keeps the local `master` honest. There is no `main` branch.

Why three branches when one person is working? Because the habit costs
nothing and the moment a second person appears — or a release must be
patched while new work is half-done — the structure is already there.

## 3. The day-to-day loop

Setup happens once (see `docs/01-setup-<your-os>.md`). After that, every
working session is the same short loop:

```bash
# 1. activate the environment (see the setup guide for your OS)
# 2. make sure you are on develop and up to date
git switch develop
git pull --ff-only origin develop

# 3. edit code or docs

# 4. check your work — the same three commands CI runs
ruff check .
pytest
python scripts/check_public_safe.py     # must print SAFE TO PUSH

# 5. commit and push (section 4)
```

Windows PowerShell users: the commands are identical; only the environment
activation line differs (`.\.venv\Scripts\Activate.ps1`).

## 4. The push sequence (verbatim)

Every phase, and every meaningful change, ends with exactly this block:

```bash
git switch develop
git add -A
git commit -m "<phase-specific message>"
git push origin develop develop:beta develop:master
# add --tags only when a release tag was created in this phase
git switch master
git pull --ff-only origin master
git switch develop
```

What each line does:

- `git switch develop` — make sure work is committed to the working branch.
- `git add -A` — stage every change (new, modified and deleted files).
- `git commit -m "..."` — take the snapshot with a message that says *what* and
  *why* (see commit message style below).
- `git push origin develop develop:beta develop:master` — one command sends
  local `develop` to remote `develop`, and fast-forwards remote `beta` and
  `master` to the same commit. Three branches, one push, always in step.
- `git switch master` / `git pull --ff-only origin master` — bring the local
  `master` in line with what was just pushed. `--ff-only` means "only if it is a
  clean fast-forward; otherwise stop and tell me" — it can never create a
  surprise merge.
- `git switch develop` — back to work.

**Commit message style.** Imperative mood, under 72 characters on the first
line, phase-prefixed while a phase is in progress:

```
phase 0: add configuration loader with cross-platform path resolution
phase 1: download and inventory the public dataset
docs: fix macOS activation command in setup guide
fix: handle empty ledger in append_rows
```

## 5. Release flow

A release is cut when a phase is complete and its tutorial is written.

1. On `develop`, update `CHANGELOG.md`: rename `[Unreleased]` to
   `[X.Y.Z] — YYYY-MM-DD` and add a fresh empty `[Unreleased]` above it.
2. Bump the version in **two** places, and only these two:
   `pyproject.toml` (`version = "X.Y.Z"`) and `src/segaudit/__init__.py`
   (`__version__ = "X.Y.Z"`). A test will fail if they disagree once the
   version test lands in Phase 1.
3. Run the full check loop (`ruff check .`, `pytest`, the safety script).
4. Commit: `release: vX.Y.Z`.
5. Tag: `git tag -a vX.Y.Z -m "SegAudit vX.Y.Z — <one line>"`.
6. Push with tags: the standard push sequence, adding `--tags` to the push
   line. CI runs on the tag; a green run is the release.
7. On GitHub, create a Release from the tag and paste the changelog section.

Version meaning: `0.Y.0` while phases are landing (one minor per phase);
`1.0.0` when the full pipeline described in `docs/05-roadmap.md` runs end to
end; patch versions for fixes and documentation.

## 6. Code norms

- **Pure Python, cross-platform.** Paths are `pathlib.Path`, never string
  concatenation; no shell-specific commands inside Python; tests pass on
  Windows, macOS and Linux (CI enforces it).
- **Config-driven.** No path, seed, threshold or size in code. It goes in
  `configs/*.yaml` and is read through `segaudit.config`.
- **API first.** Every capability is a function in `src/segaudit/api.py`. The
  command line, the review app and any service call the API; they contain no
  pipeline logic.
- **Storage through the interface.** Tables are written and read through
  `segaudit.storage.Storage`, never by opening files directly in pipeline
  code.
- **Deterministic.** Anything random takes its seed from the configuration.
  Two runs with the same config and code must produce identical tables.
- **Tested.** New behaviour comes with a test in `tests/`; tests run on the
  synthetic phantom so they need no download and finish in seconds. Mark
  anything that trains a model with `@pytest.mark.slow`.
- **Linted.** `ruff check .` is clean before every commit.
- **Comments explain why.** The code already says what it does.

## 7. Documentation norms

- Every tutorial in `docs/` opens with its **prerequisites**, a **learning
  goal**, and a **checkpoint**, and shows every command with its expected
  output and a "if it fails" note.
- Every term — medical, statistical or technical — is defined in
  `docs/00-glossary.md` with an everyday analogy. If a word is used and not in
  the glossary, that is a documentation bug; please report it.
- Every file in the repository is referenced and explained somewhere in the
  docs (the README's repository map is the index). No undocumented magic.
- `docs/HANDBOOK.md` is the single guided entry point and is updated **in the
  same commit** as any change that alters a status, adds a document, or changes
  a step. Before every push, ask: does the Handbook still tell the truth?
- **Illustrations.** Concepts that are spatial, structural or sequential get a
  picture, not just prose. Prefer **Mermaid** diagrams (text-based: they render
  on GitHub, diff like code, and never go stale in a binary blob); use **SVG**
  files in `docs/img/` (named `fig_*.svg`, white background, an `aria-label`
  describing the content) for figures Mermaid cannot draw. Every image is
  embedded with meaningful alt text, and every file in `docs/img/` is
  referenced by at least one document. Screenshots enter only from Phase 9
  (the review app) onward. Truly interactive figures are out of scope for
  repository pages — the interactive layer of this project is the review app
  itself.
- Honesty over polish: limitations, synthetic data and known bumps are stated
  where a reader would otherwise be misled.

## 8. Review norms

Pull requests are reviewed against the norms above, kindly and specifically:
what to change, why, and an example if it helps. Questions are welcome at any
level; "I do not understand this sentence" is a valid, useful review comment
and usually results in a better sentence.
