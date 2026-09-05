"""Concatenate every Git-tracked text file in the repository into one Markdown snapshot.

Why this exists: a single file holding the whole repository (paths + contents)
is the easiest way to review the project as one document, share its exact
state, or archive what a release looked like. Pure Python, pathlib only; runs
identically on Windows, macOS and Linux.

Only files tracked by Git are included (``git ls-files``), so ignored folders
such as ``.venv/``, ``*.egg-info/``, ``data/`` and ``outputs/`` can never leak
into a snapshot. Run it from anywhere inside the repository:

    python scripts/make_repo_snapshot.py --out ../segaudit-repo-snapshot.md
    python scripts/make_repo_snapshot.py --out ../snap.md --max-bytes 400000

If the snapshot exceeds --max-bytes it is split into <name>-part1.md,
<name>-part2.md, ... so each part stays within a comfortable upload size.
Snapshot files themselves are git-ignored (``*repo-snapshot*.md``).
"""


from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

SKIP_DIRS = {
    ".git", ".venv", "venv", "env", "__pycache__", ".pytest_cache",
    ".ruff_cache", ".mypy_cache", "node_modules", ".idea", ".vscode",
    "data", "outputs", "models", "build", "dist", "site",
}
SKIP_SUFFIXES = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".pdf",
    ".nii", ".gz", ".zip", ".tar", ".7z", ".whl", ".pt", ".pth",
    ".ckpt", ".onnx", ".parquet", ".duckdb", ".db", ".pkl", ".npy",
    ".npz", ".svs", ".tif", ".tiff", ".ndpi", ".mrxs", ".pyc", ".so",
    ".dylib", ".dll", ".exe",
}
SKIP_FILES: set[str] = set()
# SVG figures are text but large and low-value for the model; keep only a stub.
STUB_SUFFIXES = {".svg"}
FENCE_BY_SUFFIX = {
    ".py": "python", ".yaml": "yaml", ".yml": "yaml", ".toml": "toml",
    ".md": "markdown", ".txt": "text", ".cfg": "ini", ".ini": "ini",
    ".json": "json", ".sh": "bash", ".ps1": "powershell", ".r": "r",
    ".R": "r", ".qmd": "markdown", ".cff": "yaml",
}


def is_text(path: Path) -> bool:
    if path.suffix.lower() in SKIP_SUFFIXES:
        return False
    try:
        with path.open("rb") as fh:
            chunk = fh.read(4096)
    except OSError:
        return False
    return b"\x00" not in chunk


def collect(repo: Path) -> list[Path]:
    """Every Git-tracked text file, sorted by path."""
    out = subprocess.run(
        ["git", "-C", str(repo), "ls-files", "-z"],
        check=True, capture_output=True, text=True,
    ).stdout
    files: list[Path] = []
    for rel in sorted(p for p in out.split("\0") if p):
        path = repo / rel
        if not path.is_file() or path.name in SKIP_FILES:
            continue
        if any(part in SKIP_DIRS for part in Path(rel).parts[:-1]):
            continue
        if not is_text(path):
            continue
        files.append(path)
    return files


def render(repo: Path, files: list[Path]) -> str:
    out: list[str] = []
    out.append(f"# Repository snapshot: {repo.resolve().name}\n")
    out.append("Every text file at the current commit, with its path. "
               "Binary files, data, outputs, models and environments are omitted.\n")
    out.append("## File list\n")
    for path in files:
        out.append(f"- `{path.relative_to(repo).as_posix()}`")
    out.append("\n---\n")
    for path in files:
        rel = path.relative_to(repo).as_posix()
        out.append(f"\n## `{rel}`\n")
        if path.suffix.lower() in STUB_SUFFIXES:
            out.append(f"_(SVG figure, {path.stat().st_size} bytes, content omitted)_\n")
            continue
        fence = FENCE_BY_SUFFIX.get(path.suffix, "")
        body = path.read_text(encoding="utf-8", errors="replace").rstrip("\n")
        # Protect against files that themselves contain a triple backtick.
        marker = "````" if "```" in body else "```"
        out.append(f"{marker}{fence}\n{body}\n{marker}\n")
    return "\n".join(out)


def write_parts(text: str, out: Path, max_bytes: int) -> list[Path]:
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        out.write_text(text, encoding="utf-8")
        return [out]
    # Split on file boundaries so no file is cut in half.
    sections = text.split("\n## `")
    parts: list[Path] = []
    buffer = sections[0]
    index = 1
    for section in sections[1:]:
        candidate = buffer + "\n## `" + section
        if len(candidate.encode("utf-8")) > max_bytes and buffer:
            part = out.with_name(f"{out.stem}-part{index}{out.suffix}")
            part.write_text(buffer, encoding="utf-8")
            parts.append(part)
            index += 1
            buffer = f"# (continued, part {index})\n\n## `" + section
        else:
            buffer = candidate
    part = out.with_name(f"{out.stem}-part{index}{out.suffix}")
    part.write_text(buffer, encoding="utf-8")
    parts.append(part)
    return parts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parent.parent,
                        help="repository root (default: the folder above scripts/)")
    parser.add_argument("--out", type=Path, required=True, help="output .md path")
    parser.add_argument("--max-bytes", type=int, default=600_000,
                        help="split into parts above this size (default 600 kB)")
    args = parser.parse_args()

    repo = args.repo.resolve()
    if not (repo / ".git").exists():
        raise SystemExit(f"{repo} does not look like a Git repository (no .git folder)")

    files = collect(repo)
    text = render(repo, files)
    parts = write_parts(text, args.out.resolve(), args.max_bytes)
    print(f"{len(files)} files captured")
    for part in parts:
        print(f"  wrote {part} ({part.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
