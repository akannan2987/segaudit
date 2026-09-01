[← README](../README.md) · [All docs in order](../README.md#the-tutorial-in-order) · **Glossary**

# 00 · Glossary — every term, in plain language

**Prerequisites:** none.
**Learning goal:** you can read any page in this repository without meeting a word you don't understand. If a term used anywhere in SegAudit is missing here, that is a documentation bug — please report it.
**How to use this page:** keep it open in a second tab. Terms are grouped by topic and alphabetical within each group. Every entry has a definition and, wherever it helps, an everyday analogy in *italics*.

---

## Contents

1. [The body and the scan](#1-the-body-and-the-scan)
2. [Image files and geometry](#2-image-files-and-geometry)
3. [Image processing](#3-image-processing)
4. [Segmentation and how it is scored](#4-segmentation-and-how-it-is-scored)
5. [Machine learning and deep learning](#5-machine-learning-and-deep-learning)
6. [Uncertainty, quality control and decisions](#6-uncertainty-quality-control-and-decisions)
7. [Biomarkers, statistics and study design](#7-biomarkers-statistics-and-study-design)
8. [Python and packages](#8-python-and-packages)
9. [The project's own building blocks](#9-the-projects-own-building-blocks)
10. [Testing, quality and automation](#10-testing-quality-and-automation)
11. [Git and GitHub](#11-git-and-github)
12. [Agents, tools and generative models](#12-agents-tools-and-generative-models)
13. [Containers, hardware and platforms](#13-containers-hardware-and-platforms)
14. [Licences and data provenance](#14-licences-and-data-provenance)

---

## 1. The body and the scan

**Anterior / posterior.** Front / back. The hippocampus in this project is outlined as two parts, the front (anterior) and the back (posterior). *Bow and stern of a boat.*

**Hippocampus.** A small, curled structure deep in each half of the brain, about the size of your little finger, central to forming memories. It shrinks in several neurological and psychiatric conditions, so its volume is a measurement clinicians care about. *The brain's filing clerk for new memories.*

**MRI (magnetic resonance imaging).** A scanner that uses a strong magnet and radio waves — no X-rays — to take detailed 3D pictures of soft tissue such as the brain. *A camera that photographs the inside of the body one thin slice at a time.*

**Modality.** The kind of scanner: MRI, CT (X-ray based), PET (traces a radioactive marker), ultrasound, and so on. SegAudit's core data is MRI; the pipeline is written so other modalities can be added. *Photograph vs X-ray vs thermal image of the same object.*

**Scan / volume.** One complete 3D picture of a patient's head, stored as a stack of slices. In code it is a 3D grid of numbers. *A loaf of bread: the loaf is the volume, each slice is one 2D image.*

**Slice.** One 2D layer of a 3D scan. *One slice of the loaf.*

**T1-weighted.** One of several MRI "recipes" (settings) that decide which tissues look bright and which look dark. T1-weighted images show anatomy crisply: fat bright, fluid dark. *Different camera filters bring out different features of the same landscape.*

**Voxel.** A 3D pixel: one tiny cube of a scan, holding one brightness value. A hippocampus scan here is roughly 35 × 50 × 35 voxels. *A single sugar cube in a stacked block of sugar cubes.*

## 2. Image files and geometry

**Affine.** A small 4 × 4 table of numbers stored inside every NIfTI file that says how big each voxel is, which way each axis points, and where the scan sits in the scanner's space. Lose it, and every millilitre you compute is wrong. *The scale and compass rose printed in the corner of a map — without them, a map is just a drawing.*

**DICOM.** The standard file format that scanners produce: one file per slice, each stuffed with metadata (patient, scanner, date, settings). *A stack of index cards, one per slice, each with a long label on the back.*

**Header.** The metadata block at the start of an image file: dimensions, voxel size, data type, affine. *The nutrition label on a packet.*

**Metadata.** Data about the data: when it was acquired, on what scanner, with what settings, at what resolution. *The details on the back of a photograph — date, place, camera.*

**NIfTI (`.nii` / `.nii.gz`).** The file format used for research neuroimaging: the whole 3D volume in one file with its affine. `.gz` means compressed. *The whole loaf in one bag, with the recipe card inside.*

**Orientation.** Which way is left/right, front/back, up/down in the stored grid. Different scanners store the same head in different axis orders; SegAudit reorients everything to one canonical order before doing anything else. *Agreeing that "north" means up before comparing two maps.*

**Resampling.** Recomputing a volume on a new grid — for example turning 1.0 × 1.0 × 1.2 mm voxels into 1.0 × 1.0 × 1.0 mm voxels — so that every scan has the same voxel size. *Redrawing two maps at the same scale so distances can be compared.*

**Spacing (voxel size).** The physical size of one voxel in millimetres along each axis, e.g. 1 × 1 × 1 mm. Volume in millilitres = number of voxels × voxel size. *The size of one tile on a tiled floor.*

## 3. Image processing

**Denoising.** Reducing random speckle in an image while keeping edges. SegAudit tests two classical methods and measures what they do to downstream results. *Smoothing the static on an old TV picture without blurring the actors.*

**Intensity normalisation.** Rescaling brightness values so that scans from different scanners live on the same scale (for example, mean 0 and spread 1). Without it, a model learns "bright scanner vs dark scanner" instead of anatomy. *Converting all prices to one currency before comparing them.*

**Morphology (morphological operations).** Simple shape operations on a mask: fill holes, remove specks, keep the largest connected blob. *Tidying a paper cut-out: trimming loose threads and sticking down flaps.*

**Preprocessing.** Everything done to a scan before a model sees it: reorient, resample, normalise, optionally denoise. *Washing, peeling and chopping before cooking.*

**Registration.** Aligning two images of the same object so that corresponding points line up — for example a scan taken today and one taken last month. SegAudit uses *rigid* registration (only rotation and shift, no stretching) in its repeatability study. *Laying two transparent maps on top of each other and sliding one until the roads line up.*

**Thresholding.** The simplest possible segmentation: "every voxel brighter than X belongs to the structure". SegAudit's classical baseline is thresholding plus morphology. *Sorting coins by "heavier than 5 g".*

## 4. Segmentation and how it is scored

**Baseline.** A simple method you compare the clever method against. If the clever method cannot beat the baseline, it has not earned its complexity. *Timing yourself walking before deciding whether the new bicycle is faster.*

**Boundary / surface.** The outer edge of a segmented structure. Two masks can overlap almost perfectly yet have boundaries that differ by a few millimetres in one spot — which is why surface metrics exist alongside overlap metrics.

**Connected component.** A group of voxels in a mask that touch each other. A hippocampus mask should be one or two blobs; ten blobs means the model was confused. *Islands on a map: one big island is expected, an archipelago is suspicious.*

**Dice score (Dice coefficient).** The standard overlap score between two masks: twice the shared volume divided by the sum of both volumes. 1.0 = identical, 0.0 = no overlap. *If two people each colour in a shape, Dice asks: how much of what they coloured is the same?*

**Failure case.** A scan on which the model's segmentation is badly wrong (in this project, Dice below a stated threshold). The whole point of SegAudit is to find these without a reference.

**Ground truth / reference.** The expert-drawn mask treated as "the right answer" for training and scoring. It is the best answer we have, not a perfect one. *The answer key at the back of the textbook — usually right, occasionally not.*

**Hausdorff distance (HD, HD95).** How far apart two boundaries are at their worst point. HD95 uses the 95th percentile instead of the absolute worst voxel so one stray speck does not dominate. Measured in millimetres. *Two people trace the same coastline; HD is the biggest gap between their lines.*

**Label.** The number stored in a mask voxel saying what it belongs to: 0 = background, 1 = anterior hippocampus, 2 = posterior hippocampus. *Colour codes on a colouring page: 1 = blue, 2 = green.*

**Mask (segmentation mask).** A volume the same size as the scan whose voxels hold labels instead of brightness. The mask *is* the segmentation. *A stencil laid over a photo.*

**Normalised surface distance (NSD).** The fraction of one mask's boundary that lies within a tolerance (say 1 mm) of the other's boundary. 1.0 = the boundaries agree everywhere within tolerance. *Two coastlines traced; NSD is the percentage of the coast where the traces are within a pencil width of each other.*

**Overlap metric vs surface metric.** Overlap (Dice) asks "how much shared volume?". Surface (HD95, NSD) asks "how far apart are the edges?". A mask can score well on one and badly on the other; SegAudit reports both.

**Segmentation.** Outlining a structure on a scan voxel by voxel. The verb (to segment) and the result (a segmentation) are both used. *Colouring inside the lines on every slice of the loaf.*

## 5. Machine learning and deep learning

**Augmentation (data augmentation).** Making training data more varied by applying random, realistic changes — small rotations, flips, brightness shifts — so the model learns anatomy rather than one scanner's quirks. *Practising a song in several keys so you can play it in any.*

**Batch (batch size).** How many scans the model looks at before adjusting itself once. *Marking a stack of four homework sheets before updating the mark scheme.*

**Checkpoint (model checkpoint).** The saved state of a model at some point in training — a file of weights. Not to be confused with the "checkpoint" at the end of each tutorial page, which is a test you pass. *A saved game.*

**Classifier.** A model whose answer is a category: "will fail" / "will pass". SegAudit's quality-control model is a classifier. *A sorting hat.*

**Deep learning.** Machine learning using neural networks with many layers. Good at images because it learns which patterns matter instead of being told. *Learning to recognise faces by seeing thousands of them, rather than by memorising a list of rules about noses.*

**Dropout.** During training, randomly switching off a fraction of a network's units each step so no single unit can be relied on. Normally switched off after training; SegAudit deliberately leaves it on for *Monte Carlo dropout* (section 6). *Practising a team sport with random players benched so everyone learns every position.*

**Epoch.** One full pass through all the training scans. Training runs for a set number of epochs. *Reading the whole textbook once.*

**Feature.** A number computed from data that a model can use: volume, sphericity, uncertainty. *Height, weight and age on a medical form.*

**Feature extraction.** Turning raw data (a mask, a probability map) into a short list of features. *Summarising a whole essay as five key facts.*

**Inference.** Using a trained model on new data. *Sitting the exam after studying.*

**Learning rate.** How big a step the model takes when it adjusts itself. Too big and it overshoots; too small and it crawls. *How far you turn the shower tap each time the water is the wrong temperature.*

**Loss function.** The number the model tries to make small during training — a measure of how wrong it currently is. SegAudit uses a Dice-based loss, so "wrong" means "overlaps badly with the expert mask". *The score the coach shouts after each attempt.*

**Machine learning (ML).** Programs that learn patterns from examples instead of following hand-written rules. *Teaching by showing, not by telling.*

**Model.** A program that has learned from data and can now make predictions. In SegAudit: the segmentation model (a 3D U-Net) and the quality-control classifier.

**Model weights (parameters).** The millions of numbers inside a neural network that training adjusts. Saving a model means saving its weights. *The knob settings on a huge mixing desk.*

**Neural network.** A model built from layers of simple units, each combining its inputs and passing a signal on. *A bucket brigade where each person decides how much water to pass along.*

**Overfitting.** When a model memorises its training examples instead of learning the general pattern, so it does well on those and badly on new data. The validation split (below) is how you catch it. *A student who memorised last year's exam answers.*

**Patient-level split.** Making sure every scan from one patient is entirely in one split, never across two — otherwise the model has "seen" the test patient and the score is inflated. Each case in the public dataset is one subject.

**Probability map.** A model's raw output before thresholding: for every voxel, the model's confidence that it belongs to the structure. Thresholding the map at 0.5 gives the mask. *A weather map showing "chance of rain" per region, before you decide where to carry an umbrella.*

**Sliding-window inference.** Running a model over a large volume one window at a time and stitching the results. Needed when the whole scan does not fit in memory. *Reading a huge poster through a magnifying glass, one patch at a time.*

**Train / validation / test split.** Dividing the cases into three groups: *train* teaches the model, *validation* is used to make decisions while developing (when to stop, which threshold), *test* is touched once at the end for the honest score. *Study notes / practice exam / final exam.*

**3D U-Net (U-Net).** The standard neural-network design for segmenting medical images. It squeezes the image down to see the big picture, then expands back up to draw fine outlines, with shortcuts between matching levels so detail is not lost. "3D" means it looks at the whole volume, not slice by slice. *Zooming out to understand the map, then zooming in to trace the road, while remembering what you saw zoomed out.*

## 6. Uncertainty, quality control and decisions

**Auto-accept.** A case the quality-control score rates as safe enough to use without a human looking at it. The residual risk of doing so is stated as a number, not hidden.

**Calibration.** Whether a score means what it says: among cases given "30% chance of failure", roughly 30% should actually fail. SegAudit checks this with a reliability diagram. *A weather forecaster is calibrated if it rains on 3 of every 10 days they said "30%".*

**Entropy (predictive entropy).** A per-voxel measure of how undecided the model is; high entropy means the model is torn between labels. Averaged over a mask, it is one of SegAudit's uncertainty features.

**Monte Carlo dropout (MC dropout).** Running the same scan through the model many times with dropout switched *on*, so each pass gives a slightly different answer. The spread of answers is an uncertainty estimate. *Asking the same expert the same question on twenty different mornings and seeing how much the answers vary.*

**Operating point.** The chosen cut-off on the quality score that separates "review" from "auto-accept". Moving it trades review effort against risk. SegAudit states its operating point and why. *Setting the smoke alarm's sensitivity: too high and it screams at toast, too low and it misses a fire.*

**Precision / recall.** For a "will fail" classifier: *precision* = of the cases flagged, how many really failed; *recall* = of the cases that really failed, how many were flagged. Raising one usually lowers the other.

**Quality control (QC).** Checking outputs before they are used. In SegAudit, a score per case predicting whether the segmentation is trustworthy. *Inspecting each part on the production line before it ships.*

**Quality assurance (QA).** Checking inputs and processes: is this scan the right shape, spacing, orientation, intensity range? SegAudit's input gates refuse bad scans before inference. *Checking the ingredients before cooking, not the dish after.*

**Reference-free.** Working without the ground-truth mask. Essential in real use, where nobody has drawn the answer. *Proof-reading your own essay when no answer key exists.*

**Review budget.** How many cases a human can look at — say 10% of the batch. The operating point is chosen to fit it.

**Test-time augmentation (TTA).** Running the model on several slightly altered versions of the same scan (flipped, shifted, brightness-nudged) and comparing the answers. Disagreement signals uncertainty. *Showing a witness the same photo at three angles and checking whether they still identify the same person.*

**Triage.** Sorting cases by urgency so limited attention goes where it matters most. SegAudit's output is a triage queue ordered by predicted failure risk. *The nurse at the front desk of an emergency department.*

**Uncertainty quantification (UQ).** Putting a number on how sure a model is about each answer. *The error bars on a measurement.*

## 7. Biomarkers, statistics and study design

**Bootstrap.** Estimating how much a statistic (mean Dice, say) would vary by recomputing it many times on random resamples of the data. Gives confidence intervals without heavy assumptions. *Re-drawing your survey sample with replacement a thousand times to see how stable the average is.*

**Confidence interval (CI).** A range that likely contains the true value: "mean Dice 0.89, 95% CI 0.87–0.91". Note the clash with *continuous integration*, also abbreviated CI; context tells them apart.

**Covariate.** A variable you record alongside the measurement of interest because it may influence it: age, sex, scanner. In SegAudit's stratification phase, clinical covariates are simulated and labelled as such.

**Imaging biomarker.** A number derived from a scan that tracks disease or treatment — hippocampal volume in millilitres, for example. Useful only if it is *valid* (measures what it claims) and *repeatable* (gives the same answer when nothing changed). *A bathroom scale is a biomarker for weight — useless if it reads differently every time you step on it.*

**Minimum detectable difference (MDD).** The smallest change in a biomarker that can be distinguished from measurement noise. If re-measuring the same person varies by ±0.1 mL, a 0.05 mL "change" means nothing. *If your scale wobbles by a kilo, a half-kilo loss is not news.*

**Repeatability (test–retest).** How closely repeated measurements of the same thing agree. SegAudit simulates re-acquisition (noise, resolution, rotation) and measures how far the volume moves. *Weighing the same bag of flour five times.*

**Stratification.** Dividing cases into groups (by biomarker tertile, by QC status) to compare them or to balance a study. *Sorting apples into small, medium and large before comparing prices.*

**Synthetic data / phantom.** Data generated by a program to a known recipe. SegAudit's *phantom* is a volume containing hippocampus-like ellipsoids with noise and a matching mask; it runs the pipeline with no download and lets failure modes be manufactured deliberately. Always labelled synthetic. *A crash-test dummy: not a person, but shaped enough like one to test the seatbelt.*

## 8. Python and packages

**Command line / terminal / shell.** A text window where you type commands and read their output. macOS: Terminal (bash or zsh). Windows: PowerShell. Linux: bash. *Talking to the computer by typing sentences instead of clicking.*

**Dependency.** Another package your code needs. SegAudit depends on numpy, MONAI and others. *Ingredients a recipe calls for.*

**Editable install (`pip install -e .`).** Installing the package as a *link* to the source folder, so edits to the code take effect immediately without reinstalling. *Putting a signpost to your workshop in the phone book instead of copying the workshop.*

**Environment marker.** A condition at the end of a requirements line — `; sys_platform == "darwin"` — that pip evaluates on the installing machine and skips the line if false. How one requirements file serves Intel Macs and everything else. *"If raining, bring umbrella" written on the packing list.*

**Import.** The Python statement that loads a package for use: `import numpy`. If it fails, the package is missing or broken; `segaudit check-env` tries every one.

**Package.** Reusable code you install, e.g. numpy. Also: the folder structure of SegAudit's own code (`src/segaudit/`). *A toolkit you buy vs the toolbox you assemble.*

**pip.** Python's package installer: `pip install numpy`. *The shop where you buy toolkits.*

**Pin (pinned version).** Specifying an exact version, `numpy==1.26.4`, instead of "any numpy". Pins are what make an environment reproducible. *Ordering by part number, not "a screw".*

**Python.** The programming language SegAudit is written in. Version 3.11 is used here.

**PyPI.** The Python Package Index — the public catalogue pip downloads from.

**`pyproject.toml`.** The file describing a Python project: name, version, dependencies, tool settings. *The label on the toolbox.*

**`requirements.txt`.** A list of exact package versions for pip to install. *The shopping list with part numbers.*

**src layout.** Keeping code in `src/segaudit/` rather than at the repository root, so it must be *installed* to be imported — which is exactly what a stranger will do. Catches "works on my machine" bugs.

**Virtual environment (venv).** A private, sealed set of Python packages for one project, in a folder called `.venv`. Activating it means "use these packages"; deactivating returns to the machine's default. Prevents two projects from fighting over versions. *A separate toolbox per project so the hammer from one never goes missing into another.*

**Wheel.** A pre-built package file (`.whl`) pip can install without compiling. If no wheel exists for your platform, pip tries to build from source, which often fails — this is why the Intel-Mac lane exists. *Flat-pack furniture already assembled.*

## 9. The project's own building blocks

**API (public API).** The set of Python functions in `src/segaudit/api.py` through which every capability is reached. The command line, the review app and any future service call these and nothing else. *One vault, many counters.*

**Backend.** The code that does the real work, invisible to the user. *The kitchen.*

**Command line interface (CLI).** The `segaudit` command and its subcommands. A thin door onto the API.

**Configuration (config).** The YAML file (`configs/default.yaml`) holding every path, seed and threshold. Code reads it; code never hard-codes those values. *The recipe card.*

**Frontend.** What a person looks at and clicks. In SegAudit, the Streamlit review app (Phase 9). *The dining room.*

**Ledger.** An append-only table: rows are added, never edited or deleted. Review decisions and pipeline runs are ledgers, so history is never lost. *An accountant's bound ledger — you strike a line through a mistake, you never tear out the page.*

**Parquet.** A compact file format for tables that remembers column types. Used for every result table. *A spreadsheet that never forgets a date is a date.*

**Protocol / interface.** A description of *what* something must be able to do (write a table, read a table) without saying *how*. `Storage` is one; any class with the right methods qualifies. *A duty roster for a filing clerk, not the clerk's name.*

**Seed (random seed).** The starting number for a random-number generator. Same seed → same "random" sequence → same result. Every SegAudit run takes its seed from the config. *Shuffling a deck the same way twice.*

**Storage (storage layer).** The one interface through which result tables are written and read. Today: Parquet files queried by DuckDB. Later: possibly a database server or cloud storage — the pipeline would not change. *The pantry.*

**DuckDB.** A small analytics database that runs inside Python and can run SQL directly on Parquet files. No server, no account. *A calculator that speaks spreadsheet.*

**SQL.** The near-universal language for asking questions of tables: `SELECT case_id FROM case_metrics ORDER BY dice LIMIT 10`. *A very polite, very literal way of saying "bring me the ten worst cases".*

**YAML.** A human-readable text format for settings: `seed: 123`. *A neatly indented list.*

## 10. Testing, quality and automation

**Assertion.** A statement in a test that must be true: `assert dice == 1.0`. If it is false, the test fails.

**Checkpoint (tutorial checkpoint).** At the end of each tutorial page: a command you run and the output you must see before continuing. *The "you should now see…" line in assembly instructions.*

**Continuous integration (CI).** Automatically installing and testing the project on fresh machines every time code is pushed. SegAudit's CI runs on Windows, macOS and Linux. *A driving test taken on three different cars every time you change how you drive.*

**Fixture.** Setup that pytest builds before a test and tears down after — a temporary folder, a small config. *Laying out the ingredients before each cooking test.*

**GitHub Actions.** GitHub's CI service. The workflow file `.github/workflows/ci.yml` tells it what to run.

**Linter (ruff).** A program that reads code and flags mistakes and untidiness before the code runs — unused imports, likely bugs, inconsistent style. *A spell-checker for programs.*

**pytest.** The test runner: finds every `test_*.py` file, runs every `test_*` function, reports passed/failed.

**Runner.** The fresh virtual machine CI rents for one job. `ubuntu-latest`, `windows-latest`, `macos-latest`.

**Unit test.** A small automated check of one piece of behaviour: "given this config, the loader resolves this path". Fast, isolated, run in seconds. *Testing one Lego brick's fit rather than the whole castle.*

## 11. Git and GitHub

**Branch.** A named line of development. SegAudit has `master` (stable), `beta` (preview) and `develop` (work). *Parallel drafts of the same document.*

**Clone.** Copying a repository from GitHub to your machine. *Downloading the whole project folder, with its history.*

**Commit.** A saved snapshot of the project with a message. *A save point in a game.*

**Fast-forward.** Updating a branch by simply moving it to a newer commit that already contains it — no merging. `--ff-only` refuses to do anything else. *Turning to a later page in the same book, never splicing in pages from another.*

**Git.** The version-control program: a save-game system for code. Every meaningful change is a snapshot you can return to or compare against.

**`.gitignore`.** A list of files Git must never track: environments, data, secrets. *A "do not pack" list.*

**GitHub.** The website where repositories live, where CI runs, and where others read the code.

**Pull.** Fetching new commits from GitHub and applying them locally.

**Push.** Sending local commits to GitHub.

**Remote (`origin`).** The copy of the repository on GitHub, as seen from your machine.

**Repository (repo).** A project folder tracked by Git, with its whole history.

**Semantic versioning.** Version numbers of the form `MAJOR.MINOR.PATCH`: a new phase bumps MINOR, a fix bumps PATCH, an incompatible change bumps MAJOR. SegAudit is `0.1.0`.

**Tag.** A named, permanent label on one commit: `v0.1.0`. Releases are tags.

**Working tree.** The files as they currently are on disk, committed or not. "Working tree clean" means nothing is uncommitted.

## 12. Agents, tools and generative models

**Agent.** A program that uses a generative model not just to answer but to *act*: it plans steps, calls tools (run a query, launch an audit), reads the results and continues until the task is done. *A chatbot answers your question about the train timetable; an agent books the ticket.*

**Generative model (language model).** A model that produces text (or images) in response to a prompt. SegAudit uses one, in Phase 10, to draft quality reports from computed numbers — and guards it so it cannot state a number it was not given.

**Grounding.** Forcing a generative model's output to rest on supplied facts rather than its own guesses. SegAudit's report drafter is grounded in the results tables. *A journalist who may only print what is in the evidence file.*

**Model Context Protocol (MCP).** An open standard through which an agent discovers and calls a program's tools with validated inputs. SegAudit exposes `segment_case`, `audit_case`, `query_ledger` and `draft_report` this way. *A USB port: any agent with the right plug can use the tools.*

**Tool (in the agent sense).** A function an agent is allowed to call, with a strict description of inputs and outputs. *The buttons on the agent's control panel.*

## 13. Containers, hardware and platforms

**Container.** A sealed package holding the exact operating-system layer, Python and packages an app needs, so it runs identically anywhere. SegAudit ships one in Phase 11. *A shipping container: the contents don't care which ship or truck carries them.*

**Docker / Podman.** Two programs that build and run containers. Podman is the default on RHEL 8; the two are largely command-compatible.

**Image (container image).** The blueprint a container is started from. Not to be confused with a medical image — context tells them apart.

**CPU / GPU.** The general processor every computer has / a graphics processor that accelerates deep learning enormously but is not required here. SegAudit trains on CPU by design.

**HPC / Slurm.** High-performance computing: a shared cluster of machines. Slurm is the scheduler that queues jobs on it. A Slurm script is documented in Phase 11.

**Intel Mac / Apple silicon.** Macs built before ~2020 use Intel processors (x86_64); newer ones use Apple's own (arm64). PyTorch stopped building for Intel Macs at version 2.2.2, which is why SegAudit has two dependency lanes.

**Platform.** The combination of operating system and processor type: Windows x86_64, Linux x86_64, macOS arm64, macOS x86_64.

**RHEL 8.** Red Hat Enterprise Linux 8, a long-support Linux common on institutional servers and virtual machines. Its default `python3` is 3.6; SegAudit uses the separately installed `python3.11`.

**Virtual machine (VM).** A computer simulated inside another computer. RHEL 8 VMs are one of SegAudit's target platforms.

## 14. Licences and data provenance

**CC-BY-SA 4.0.** The licence of the public dataset: free to use and share, must credit the source, derivatives must carry the same licence.

**MIT licence.** SegAudit's own licence: do almost anything with the code, keep the copyright notice, no warranty.

**Provenance.** Where data came from and what was done to it, recorded so any number can be traced back to its source. `data/raw/` is never edited for exactly this reason. *The chain of custody for evidence.*

**Reproducibility.** Rerunning the same code on the same data and getting the same result. SegAudit's guarantee is byte-identical results within a dependency lane and numerically equivalent results across lanes.

---

Next: the setup guide for your operating system —
[`01-setup-windows.md`](01-setup-windows.md) ·
[`01-setup-macos.md`](01-setup-macos.md) ·
[`01-setup-rhel8.md`](01-setup-rhel8.md)
