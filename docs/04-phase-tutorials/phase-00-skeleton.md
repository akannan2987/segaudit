[← README](../../README.md) · [All docs in order](../../README.md#the-tutorial-in-order) · [Glossary](../00-glossary.md) · [← Architecture](../02-architecture.md)

# Phase 0 · The skeleton — foundations before features

**Prerequisites:** the setup guide for your OS completed (`segaudit check-env` says ready), `02-architecture.md` read once.
**Learning goal:** after this phase you understand every file in the repository, why each exists, how a Python package is put together, what a test is and how to read one, and how the configuration and storage layers work — by using them, not by reading about them.
**Checkpoint:** you have changed a setting and seen the change appear; written a table and queried it with SQL; run and *read* one test; and the git block at the end has been pushed with three green CI runs.
**Time:** about two hours. A natural place to stop is after section 5.

---

## Contents

1. [Why this phase exists](#1-why-this-phase-exists)
2. [What was built — the map](#2-what-was-built--the-map)
3. [Walk 1: the package and its identity card](#3-walk-1-the-package-and-its-identity-card)
4. [Walk 2: configuration — the recipe card](#4-walk-2-configuration--the-recipe-card)
5. [Walk 3: storage — the pantry, with SQL](#5-walk-3-storage--the-pantry-with-sql)
6. [Walk 4: the API and the command line](#6-walk-4-the-api-and-the-command-line)
7. [Walk 5: tests — promises that check themselves](#7-walk-5-tests--promises-that-check-themselves)
8. [Walk 6: the guard and the driving test (safety script and CI)](#8-walk-6-the-guard-and-the-driving-test)
9. [What could go wrong](#9-what-could-go-wrong)
10. [What you learned](#10-what-you-learned)
11. [Commit and push](#11-commit-and-push)

---

## 1. Why this phase exists

It is tempting to start by downloading scans and training a model. Every project that does so ends up with a folder of scripts nobody can rerun: paths typed into code, results overwritten, no way to tell which run produced which number. Phase 0 builds the workshop before any furniture goes in:

- a **package** that installs, so code can be imported from anywhere;
- a **configuration** layer, so no setting ever lives in code;
- a **storage** layer, so every result table is written one way and can be queried;
- a **command line** that only calls the API, so the API stays the single source of truth;
- **tests** that prove those promises, and **CI** that proves them on three operating systems;
- a **safety guard** so nothing private is ever published.

*Everyday version:* before cooking for a restaurant you install the counters, label the pantry shelves and write the recipe cards. It looks like nothing happened — no food yet — but every later day is faster and nothing gets lost.

## 2. What was built — the map

```
segaudit/
├── pyproject.toml                    the package's identity card (name, version, dependencies, tool settings)
├── requirements-torch-cpu.txt        PyTorch pin, CPU index, with the Intel-Mac marker
├── requirements.txt                  exact pins for everything else
├── requirements-dev.txt              pytest + ruff
├── configs/default.yaml              settings for a real run
├── configs/quick.yaml                settings for a two-minute synthetic run
├── src/segaudit/                     the package
│   ├── __init__.py                   version
│   ├── config.py                     YAML → typed Config, paths made absolute
│   ├── storage.py                    Storage interface + Parquet/DuckDB implementation
│   ├── envcheck.py                   "did the install work?"
│   ├── api.py                        THE public functions
│   └── cli.py                        segaudit info | check-env | config show | init
├── tests/                            29 automated checks
├── scripts/check_public_safe.py      pre-push guard
├── .github/workflows/ci.yml          CI on Windows, macOS, Linux
├── .gitignore · LICENSE · CHANGELOG.md · CONTRIBUTING.md · README.md
├── data/ (README + empty raw/, processed/) · outputs/ · models/    git-ignored work folders
└── docs/                             this tutorial series
```

Every walk below opens one or two of these. Have VS Code open on the project folder and a terminal with `(.venv)` showing.

## 3. Walk 1: the package and its identity card

Open `pyproject.toml`. Read the comments; they explain each block. Three ideas to take away:

**A package is a folder Python can import.** `src/segaudit/` is one because it contains `__init__.py`. After `pip install -e .`, `import segaudit` works from any folder on your machine — try it:

```
$ python -c "import segaudit; print(segaudit.__version__)"
0.1.0
```

**The "src layout".** The code sits in `src/`, not at the repository root. Why: if it sat at the root, `import segaudit` would work *only* when you happen to be standing in that folder, and tests could pass for the wrong reason. Forcing an install makes your machine behave like a stranger's.

**Two kinds of dependency list.** `pyproject.toml` says what the package is *compatible with* (`numpy>=1.26,<3`); `requirements.txt` says the *exact versions verified today* (`numpy==2.4.6`). The first is a promise to future users; the second is a reproducibility record. Both are needed.

Look at the `[project.scripts]` block: `segaudit = "segaudit.cli:main"`. That one line is why typing `segaudit` in the terminal runs the `main` function in `cli.py`.

## 4. Walk 2: configuration — the recipe card

Open `configs/quick.yaml` and `src/segaudit/config.py` side by side.

**The idea.** YAML is a plain text format for settings — indented `key: value` pairs. The loader reads it, checks the essential sections exist, and hands the rest of the code a tidy object called `Config`. Nothing else in the project opens a YAML file.

**Exercise 4a — change a setting, see it change.**

1. In `configs/quick.yaml`, change `seed: 7` to `seed: 42`.
2. Run:

```
$ segaudit config show -c configs/quick.yaml
{
  ...
  "seed": 42,
  ...
}
```

3. Change it back to `7` (the tests expect the shipped file to load; they do not check the seed's value, but keep the repo tidy).

**Exercise 4b — break it on purpose, watch it fail loudly.**

1. Temporarily delete the whole `storage:` block (two lines) from `configs/quick.yaml`.
2. Run the same command:

```
$ segaudit config show -c configs/quick.yaml
Configuration error: quick.yaml is missing required section(s): storage
```

3. Put the block back.

That message comes from `load_config` in `config.py` — find the line `missing = [k for k in _REQUIRED_TOP_LEVEL if k not in data]`. Failing early with a plain sentence is a deliberate design: a typo in a config should never become a silent wrong result three hours into a run.

**Why paths become absolute.** Find `_resolve` in `config.py`. It joins a relative path from the YAML onto the repository root and calls `.resolve()`. That is why `outputs/quick` (forward slash, in the YAML) prints as `C:\Users\<you>\...\outputs\quick` on Windows and `/Users/<you>/.../outputs/quick` on a Mac. `pathlib` does the translation; the project never builds a path by gluing strings together.

## 5. Walk 3: storage — the pantry, with SQL

Open `src/segaudit/storage.py`.

**The interface.** The class `Storage` is a *Protocol*: a list of methods any storage backend must provide — `write_table`, `append_rows`, `read_table`, `exists`, `list_tables`, `query`. It has no code of its own. *A duty roster for a filing clerk, not the name of a clerk.*

**The one implementation.** `LocalParquetStorage` fulfils the roster with Parquet files in a folder and DuckDB for SQL. Later a `PostgresStorage` could fulfil it with a database server; the pipeline would not change one line — that is what the interface buys.

**Exercise 5a — write, list, read.**

```
$ python
>>> import pandas as pd
>>> from segaudit import api
>>> cfg = api.load("configs/quick.yaml")
>>> store = api.storage_for(cfg)
>>> store.root
PosixPath('/Users/<you>/projects/segaudit/outputs/quick/tables')     # WindowsPath(...) on Windows
>>> cases = pd.DataFrame({
...     "case_id": ["c01", "c02", "c03", "c04", "c05"],
...     "dice":    [0.91, 0.42, 0.88, 0.79, 0.95],
...     "flagged": [False, True, False, True, False],
... })
>>> store.write_table("demo_cases", cases)
>>> store.list_tables()
['demo_cases']
>>> store.read_table("demo_cases")
  case_id  dice  flagged
0     c01  0.91    False
1     c02  0.42     True
2     c03  0.88    False
3     c04  0.79     True
4     c05  0.95    False
```

**Exercise 5b — SQL, including a multi-line query.**

SQL is the language for asking questions of tables. Three words carry most of it: `SELECT` (which columns), `FROM` (which table), `WHERE` (which rows). Still in the same Python session:

```python
>>> store.query("SELECT count(*) AS n FROM demo_cases")
   n
0  5
>>> store.query("""
...     SELECT case_id,
...            dice,
...            CASE WHEN dice < 0.80 THEN 'review' ELSE 'accept' END AS decision
...     FROM demo_cases
...     ORDER BY dice ASC
... """)
  case_id  dice decision
0     c02  0.42   review
1     c04  0.79   review
2     c03  0.88   accept
3     c01  0.91   accept
4     c05  0.95   accept
```

You just wrote, in four lines of SQL, the shape of what the whole project computes: a per-case score and a decision derived from a threshold. Phase 6 replaces `dice < 0.80` with a learned, reference-free score — the SQL stays this simple.

**Exercise 5c — the ledger, and why SQL cannot damage it.**

```python
>>> store.append_rows("demo_ledger", pd.DataFrame({"case_id": ["c02"], "decision": ["flag"]}))
>>> store.append_rows("demo_ledger", pd.DataFrame({"case_id": ["c04"], "decision": ["accept"]}))
>>> store.read_table("demo_ledger")
  case_id decision
0     c02     flag
1     c04   accept
>>> store.query("DELETE FROM demo_ledger")
Traceback (most recent call last):
  ...
duckdb.BinderException: Binder Error: Can only delete from base table
>>> exit()
```

`append_rows` only ever adds. `query` registers each Parquet file as a read-only *view*, so `DELETE`, `UPDATE` and `DROP` are refused by the database engine itself — not by a rule in our code that someone could forget. A test (`test_query_cannot_change_files`) pins this behaviour.

**Clean up** the demo tables:

```
$ rm outputs/quick/tables/demo_cases.parquet outputs/quick/tables/demo_ledger.parquet
```
(Windows PowerShell: `Remove-Item outputs\quick\tables\demo_*.parquet`.)

## 6. Walk 4: the API and the command line

Open `src/segaudit/api.py`, then `src/segaudit/cli.py`.

**`api.py` is short on purpose.** Four functions today. Every later phase adds its capabilities *here* — `segment_case`, `audit_case`, `run_repeatability` — and lists them in `__all__`. Rule 2 of the architecture: one vault, many doors.

**`cli.py` is a door.** Find `cmd_init`. It is five lines: load the config through `api`, call `api.initialise_workspace`, print what came back. No folder logic lives in the command line; if the review app needs to create folders it calls the same `api` function. Compare with `cmd_config_show` — same shape.

**Exercise 6a — trace one command end to end.**

```
$ segaudit init -c configs/quick.yaml
Created:
  /Users/<you>/projects/segaudit/outputs/quick
  /Users/<you>/projects/segaudit/models/quick
$ segaudit init -c configs/quick.yaml
All folders already exist — nothing to do.
```

Follow it in the code: `pyproject.toml` maps `segaudit` → `cli.main` → `build_parser` reads `init` and `-c` → `cmd_init` → `api.load` → `config.load_config` → `api.initialise_workspace` → `Path.mkdir`. Six hops, each one line to read. The second run is *idempotent* — doing it again changes nothing and says so — which every pipeline command in later phases will also be.

**Exercise 6b — the environment check is also a door.** `segaudit check-env` calls `envcheck.run_checks` and prints `envcheck.format_report`. Open `envcheck.py` and find the `DEPENDENCIES` tuple: it is the single list that says which phase first needs each package. When Phase 10 adds the MCP library, it is added there, and the check knows.

## 7. Walk 5: tests — promises that check themselves

A **test** is a small function that sets something up, does one thing, and *asserts* what must be true afterwards. If the assertion holds, the test passes silently; if not, it fails with a message. `pytest` finds every function whose name starts with `test_` in every file whose name starts with `test_`, runs them all, and counts.

Open `tests/test_config.py` and read `test_missing_section_raises_config_error`:

```python
def test_missing_section_raises_config_error(repo_root: Path):
    path = repo_root / "configs" / "broken.yaml"
    path.write_text(yaml.safe_dump({"project": {"name": "x"}}), encoding="utf-8")
    with pytest.raises(ConfigError, match="missing required section"):
        load_config(path)
```

Line by line: get a temporary repository root (`repo_root` is a *fixture* — setup pytest builds before the test and throws away after; see `tests/conftest.py`); write a deliberately incomplete YAML file into it; assert that loading it raises `ConfigError` with a message containing "missing required section". That is exercise 4b, automated, and run on every push forever.

**Exercise 7a — run one file, then one test, verbosely.**

```
$ pytest tests/test_config.py -v
tests/test_config.py::test_loads_minimal_config_and_resolves_paths_under_root PASSED
tests/test_config.py::test_absolute_paths_in_yaml_are_left_alone PASSED
...
9 passed in 0.12s

$ pytest tests/test_storage.py::test_append_rows_behaves_like_a_ledger -v
tests/test_storage.py::test_append_rows_behaves_like_a_ledger PASSED
1 passed in 0.31s
```

Test names are sentences on purpose: when one fails in six months, the name says which promise broke.

**Exercise 7b — see a failure.**

1. In `src/segaudit/storage.py`, in `append_rows`, swap the order inside `pd.concat([existing, rows], ...)` to `pd.concat([rows, existing], ...)` — new rows now go *before* old ones, which is not what a ledger does.
2. `pytest tests/test_storage.py` → `FAILED tests/test_storage.py::test_append_rows_behaves_like_a_ledger - AssertionError`, showing `['flag', 'accept']` where `['accept', 'flag']` was expected.
3. Change it back; `pytest` → `29 passed`.

That is the whole point: you changed something, and a promise you did not think about caught it.

**Why tests use a temporary folder.** Every test writes into `tmp_path`, a throwaway directory pytest creates and deletes. Tests never touch `data/`, `outputs/` or your real configs. Look at `conftest.py` — twenty lines — to see how.

## 8. Walk 6: the guard and the driving test

**The guard — `scripts/check_public_safe.py`.** Run it:

```
$ python scripts/check_public_safe.py
SAFE TO PUSH
```

Open it. It asks Git for every tracked file and checks three things: forbidden names (`.env`, `credentials.json`), forbidden suffixes (`.nii.gz`, `.parquet`, `.pt`), and text patterns that look like a secret or a personal path (`/Users/somebody/`). Lines containing a `<placeholder>` are skipped — that is why docs write `<you>`. It exits with `1` (failure) on any finding, which is what makes it usable as a gate in CI.

**The driving test — `.github/workflows/ci.yml`.** Open it. Read it as a checklist: check out the code, install Python 3.11, install PyTorch (CPU), install the rest, install SegAudit, lint, environment check, tests, safety script. The `matrix` block runs that checklist on three fresh machines. Every step is a command you have already run by hand — CI is nothing more than "what I did, done by a robot, on every push".

## 9. What could go wrong

- **`import segaudit` fails with `ModuleNotFoundError`.** The editable install was skipped or the venv is inactive. `python -m pip install -e . --no-deps` with `(.venv)` showing.
- **`segaudit config show` says the file is not found.** You are not in the project folder, or the path has a typo. `pwd`, then use the path exactly as written.
- **`store.query(...)` says a table does not exist.** `list_tables()` shows what is there; names are the file stems under `outputs/<run_label>/tables/`. You may be looking at a different config's `outputs` folder.
- **A test fails after you edited code.** Good — that is its job. Read the assertion message; undo or fix; rerun.
- **`pytest` collects 0 tests.** You ran it from a different folder. Run from the project root.
- **`rm` or `Remove-Item` refuses because a file is "in use".** Close the Python session that wrote it first.

## 10. What you learned

- What a Python package is and why the code lives in `src/`.
- Configuration as data: every setting in YAML, validated on load, paths resolved per machine.
- An interface versus an implementation, and why one interface for storage lets the backend change later.
- Parquet, DuckDB and enough SQL to ask real questions of a results table — including multi-line queries — and why SQL here is read-only.
- The API-first rule and how to trace a command through six one-line hops.
- What a test is, how to read one, how to run one, and what a failure looks like.
- That the safety script and CI are the same checks you run by hand, automated.

Phase 1 puts real scans through these foundations: download and inventory the public dataset, generate the synthetic phantom, read NIfTI with geometry intact, add the input quality gates, and open a `segaudit sql` console over the first real tables.

## 11. Commit and push

The three checks, then the sequence. (If you followed this page without changing any file, `git status` is clean and there is nothing to commit — that is fine; the block below is the habit for every phase.)

```bash
ruff check .
pytest
python scripts/check_public_safe.py     # must print SAFE TO PUSH

git switch develop
git add -A
git commit -m "phase 0: architecture, git workflow and phase 0 tutorial"
git push origin develop develop:beta develop:master
# add --tags only when a release tag was created in this phase
git switch master
git pull --ff-only origin master
git switch develop
```

Then GitHub → Actions: three green runs.

Next: [`phase-01-data.md`](phase-01-data.md) — real scans, the phantom, and the SQL console.
