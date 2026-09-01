"""Pre-push safety check.

Run from the repository root, on any operating system:

    python scripts/check_public_safe.py

It inspects everything Git currently tracks and refuses the all-clear if any
of the following would be published:

* secrets — API keys, tokens, ``.env`` files;
* data or model files that must stay local (scans, Parquet tables, weights);
* hard-coded personal paths (``/Users/name``, ``C:\\Users\\name``, ``/home/name``)
  that betray a laptop and break on everyone else's machine.

``.gitignore`` is the lock on the door; this script is the guard checking the
bag on the way out. It prints ``SAFE TO PUSH`` and exits 0, or lists every
finding and exits 1.

Placeholders are allowed: a path containing ``<you>`` or ``<name>`` is
documentation, not a leak.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

# File names / suffixes that should never be tracked.
FORBIDDEN_NAMES = {".env", ".env.local", "secrets.yaml", "secrets.yml", "credentials.json"}
FORBIDDEN_SUFFIXES = {
    ".nii",
    ".nii.gz",
    ".dcm",
    ".parquet",
    ".duckdb",
    ".db",
    ".pt",
    ".pth",
    ".ckpt",
    ".tar",
    ".zip",
}

# Text patterns that look like secrets or personal paths.
SECRET_PATTERNS = [
    re.compile(r"AKIA[0-9A-Z]{16}"),  # AWS access key id
    re.compile(r"sk-[A-Za-z0-9]{20,}"),  # generic provider secret key
    re.compile(r"ghp_[A-Za-z0-9]{30,}"),  # GitHub personal token
    re.compile(r"(?i)(api[_-]?key|secret|token|password)\s*[:=]\s*['\"][^'\"<]{8,}['\"]"),
]
LOCAL_PATH_PATTERNS = [
    re.compile(r"/Users/[A-Za-z0-9._-]+/"),
    re.compile(r"/home/[A-Za-z0-9._-]+/"),
    re.compile(r"[A-Z]:\\Users\\[A-Za-z0-9._-]+\\"),
]
PLACEHOLDER = re.compile(r"<[a-z_ -]+>")

# Binary-ish files are skipped for text scanning.
TEXT_SUFFIXES = {".py", ".md", ".txt", ".yaml", ".yml", ".toml", ".cfg", ".ini", ".json", ".sh", ".ps1"}


def tracked_files() -> list[Path]:
    out = subprocess.run(
        ["git", "ls-files", "-z"], check=True, capture_output=True, text=True
    ).stdout
    return [Path(p) for p in out.split("\0") if p]


def has_forbidden_suffix(path: Path) -> bool:
    name = path.name.lower()
    return any(name.endswith(s) for s in FORBIDDEN_SUFFIXES)


def scan_text(path: Path) -> list[str]:
    findings: list[str] = []
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return findings
    for lineno, line in enumerate(text.splitlines(), start=1):
        if PLACEHOLDER.search(line):
            continue  # documentation placeholder, e.g. C:\Users\<you>\
        for pat in SECRET_PATTERNS:
            if pat.search(line):
                findings.append(f"{path}:{lineno}: looks like a secret")
                break
        for pat in LOCAL_PATH_PATTERNS:
            if pat.search(line):
                findings.append(f"{path}:{lineno}: hard-coded personal path")
                break
    return findings


def main() -> int:
    findings: list[str] = []
    for path in tracked_files():
        if path.name in FORBIDDEN_NAMES:
            findings.append(f"{path}: secrets file must not be tracked")
        if has_forbidden_suffix(path):
            findings.append(f"{path}: data/model file must not be tracked")
        if path.suffix.lower() in TEXT_SUFFIXES and path.name != Path(__file__).name:
            findings.extend(scan_text(path))

    if findings:
        print("NOT SAFE — fix these before pushing:")
        for f in findings:
            print(f"  {f}")
        return 1
    print("SAFE TO PUSH")
    return 0


if __name__ == "__main__":
    sys.exit(main())
