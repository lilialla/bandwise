#!/usr/bin/env python3
"""Bandwise skill repository validator / CI hardening gate.

Validates the cluster of IELTS-prep Claude Code skills (one directory per
skill, each containing a SKILL.md with YAML frontmatter). Runs four groups
of checks and exits non-zero if any FAIL is found:

  1. Skill frontmatter   - name matches dir, description/version/license OK
  2. Personal-data leaks  - mac home paths, GoogleDrive, emails, CN dirs,
                            upstream identifiers
  3. Path convention      - SKILL.md that write files should reference
                            IELTS_COACH_HOME or ~/ielts-coach (WARN only)
  4. Summary              - counts of files scanned, skills, leaks, warns

Zero dependencies: Python 3 standard library only.

Usage:
    python3 scripts/validate_skills.py [--repo PATH] [--no-color]

The repo root defaults to the parent of the directory holding this script.
"""

from __future__ import annotations

import argparse
import os
import re
import sys

# The 10 canonical skill directories. Each must contain a SKILL.md.
SKILL_DIRS = [
    "ielts",
    "ielts-writing",
    "ielts-reading",
    "ielts-speaking",
    "ielts-listening",
    "ielts-mock",
    "ielts-status",
    "ielts-vocab",
    "ielts-question-bank",
    "ielts-plan",
]

# File extensions scanned for personal-data leaks.
TEXT_EXTENSIONS = {".md", ".py", ".yml", ".yaml", ".json", ".txt", ".svg"}

# Directories skipped while globbing the repo.
SKIP_DIRS = {".git", "scripts", "node_modules"}

# Literal upstream / personal identifiers that must not ship publicly.
FORBIDDEN_LITERALS = [
    "victorbyyyv",
    "neillai",
    "YANZHANLIN",
    "ielts-claude-skills",
]

# Pre-compiled leak patterns (label, compiled regex).
MAC_HOME_RE = re.compile(r"/Users/[A-Za-z0-9_.-]+/")
GOOGLE_DRIVE_RE = re.compile(r"GoogleDrive")
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
CN_DIR_RE = re.compile(r"0\d_[一-鿿]+")
# Documented Chinese data-folder names the dashboard intentionally supports.
# These are a public feature, not leaked private paths, so they are allowed to
# appear in docs/code. Any OTHER 0N_中文 token is still flagged as a leak.
CN_DIR_ALLOW = {"03_写作批改", "04_听力精听", "02_模考记录", "03_阅读精读"}

# Email allow-list: substrings that make a matched email a benign placeholder,
# plus the maintainer's intentional public contact address.
EMAIL_ALLOW_SUBSTRINGS = (
    "noreply@", "me@example", "example.com", "example.org",
    "1733970552@qq.com",  # maintainer's public commercial-licensing contact
)

# Path-convention markers a writing SKILL.md should reference.
PATH_CONVENTION_RE = re.compile(r"IELTS_COACH_HOME|~/ielts-coach|\$HOME/ielts-coach")

# Phrases indicating a skill writes / archives files (so it should reference
# the data root convention).
WRITE_HINT_RE = re.compile(r"写入|归档|写云盘|存档|archive|append-only|写新文件|写文件")


# --------------------------------------------------------------------------
# Output helpers
# --------------------------------------------------------------------------
class Printer:
    """Tiny colorized printer that degrades to plain text when disabled."""

    def __init__(self, color: bool) -> None:
        self.color = color

    def _wrap(self, text: str, code: str) -> str:
        if not self.color:
            return text
        return f"\033[{code}m{text}\033[0m"

    def passed(self, msg: str) -> None:
        print(f"{self._wrap('PASS', '32')} {msg}")

    def failed(self, msg: str) -> None:
        print(f"{self._wrap('FAIL', '31')} {msg}")

    def warn(self, msg: str) -> None:
        print(f"{self._wrap('WARN', '33')} {msg}")

    def info(self, msg: str) -> None:
        print(msg)

    def header(self, msg: str) -> None:
        print()
        print(self._wrap(msg, "1"))


# --------------------------------------------------------------------------
# Minimal frontmatter reader (stdlib only)
# --------------------------------------------------------------------------
def read_frontmatter(text: str) -> dict | None:
    """Parse a minimal YAML frontmatter block delimited by --- fences.

    Supports the only shapes Bandwise SKILL.md files use:
      * top-level `key: value`
      * top-level `key: |` block scalars (collected as joined lines)
      * a single one-level-nested mapping `metadata:` with `  key: value`

    Returns a dict where `metadata` (if present) maps to a nested dict, or
    None if no frontmatter block is found.
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None

    # Find the closing fence.
    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break
    if end is None:
        return None

    body = lines[1:end]
    data: dict = {}
    i = 0
    while i < len(body):
        raw = body[i]
        # Skip blank lines at the top level.
        if not raw.strip():
            i += 1
            continue

        # Nested mapping (e.g. metadata:) — collect indented child keys.
        m = re.match(r"^([A-Za-z0-9_]+):\s*$", raw)
        if m and i + 1 < len(body) and re.match(r"^\s+\S", body[i + 1]):
            key = m.group(1)
            nested: dict = {}
            i += 1
            while i < len(body) and (not body[i].strip() or body[i].startswith((" ", "\t"))):
                child = re.match(r"^\s+([A-Za-z0-9_]+):\s*(.*)$", body[i])
                if child:
                    nested[child.group(1)] = child.group(2).strip()
                i += 1
            data[key] = nested
            continue

        # Block scalar: `key: |` or `key: >` — collect indented continuation.
        block = re.match(r"^([A-Za-z0-9_]+):\s*[|>]\s*$", raw)
        if block:
            key = block.group(1)
            collected = []
            i += 1
            while i < len(body) and (not body[i].strip() or body[i].startswith((" ", "\t"))):
                collected.append(body[i].strip())
                i += 1
            data[key] = "\n".join(c for c in collected if c)
            continue

        # Plain `key: value`.
        kv = re.match(r"^([A-Za-z0-9_]+):\s*(.*)$", raw)
        if kv:
            data[kv.group(1)] = kv.group(2).strip()
        i += 1

    return data


# --------------------------------------------------------------------------
# File discovery
# --------------------------------------------------------------------------
def iter_text_files(repo: str):
    """Yield absolute paths of scannable text files, skipping SKIP_DIRS."""
    for dirpath, dirnames, filenames in os.walk(repo):
        # Prune skip dirs in place so os.walk does not descend into them.
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fname in filenames:
            ext = os.path.splitext(fname)[1].lower()
            if ext in TEXT_EXTENSIONS:
                yield os.path.join(dirpath, fname)


def read_file(path: str) -> str:
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        return fh.read()


# --------------------------------------------------------------------------
# Check 1: frontmatter
# --------------------------------------------------------------------------
def check_frontmatter(repo: str, p: Printer) -> tuple[int, int]:
    """Validate each skill's SKILL.md frontmatter.

    Returns (fail_count, skills_validated).
    """
    p.header("[1] Skill frontmatter")
    fails = 0
    validated = 0

    for skill in SKILL_DIRS:
        skill_md = os.path.join(repo, skill, "SKILL.md")
        rel = os.path.relpath(skill_md, repo)
        if not os.path.isfile(skill_md):
            p.failed(f"{rel}: SKILL.md missing")
            fails += 1
            continue

        fm = read_frontmatter(read_file(skill_md))
        if fm is None:
            p.failed(f"{rel}: no YAML frontmatter block")
            fails += 1
            continue

        ok = True

        name = fm.get("name", "")
        if not name:
            p.failed(f"{rel}: 'name:' missing")
            ok = False
        elif name != skill:
            p.failed(f"{rel}: name '{name}' != dir '{skill}'")
            ok = False

        desc = fm.get("description", "")
        if not (isinstance(desc, str) and desc.strip()):
            p.failed(f"{rel}: 'description:' missing or empty")
            ok = False

        meta = fm.get("metadata")
        if not isinstance(meta, dict):
            p.failed(f"{rel}: 'metadata:' block missing")
            ok = False
        else:
            if not meta.get("version"):
                p.failed(f"{rel}: 'metadata.version' missing")
                ok = False
            license_val = meta.get("license", "")
            if not license_val:
                p.failed(f"{rel}: 'metadata.license' missing")
                ok = False
            elif license_val != "PolyForm-Noncommercial-1.0.0":
                p.failed(f"{rel}: 'metadata.license' is '{license_val}', expected 'PolyForm-Noncommercial-1.0.0'")
                ok = False

        if ok:
            p.passed(f"{rel}: frontmatter OK (name={name})")
            validated += 1
        else:
            fails += 1

    return fails, validated


# --------------------------------------------------------------------------
# Check 2: personal-data leaks
# --------------------------------------------------------------------------
def scan_line_for_leaks(line: str) -> list[str]:
    """Return a list of human-readable leak descriptions found in a line."""
    hits: list[str] = []

    if MAC_HOME_RE.search(line):
        hits.append("mac home path (/Users/.../)")
    if GOOGLE_DRIVE_RE.search(line):
        hits.append("GoogleDrive reference")
    for cn_dir in CN_DIR_RE.findall(line):
        if cn_dir in CN_DIR_ALLOW:
            continue
        hits.append(f"Chinese numbered dir '{cn_dir}'")

    for email in EMAIL_RE.findall(line):
        if any(allowed in email for allowed in EMAIL_ALLOW_SUBSTRINGS):
            continue
        hits.append(f"email '{email}'")

    for literal in FORBIDDEN_LITERALS:
        if literal in line:
            hits.append(f"forbidden literal '{literal}'")

    return hits


def check_leaks(repo: str, p: Printer) -> tuple[int, int]:
    """Scan every tracked text file for leaks.

    Returns (leak_count, files_scanned).
    """
    p.header("[2] Personal-data leaks")
    leaks = 0
    files_scanned = 0

    for path in iter_text_files(repo):
        files_scanned += 1
        rel = os.path.relpath(path, repo)
        try:
            content = read_file(path)
        except OSError as exc:
            p.failed(f"{rel}: unreadable ({exc})")
            leaks += 1
            continue

        for lineno, line in enumerate(content.splitlines(), start=1):
            for hit in scan_line_for_leaks(line):
                p.failed(f"{rel}:{lineno}: {hit}")
                leaks += 1

    if leaks == 0:
        p.passed(f"no leaks in {files_scanned} scanned file(s)")

    return leaks, files_scanned


# --------------------------------------------------------------------------
# Check 3: configurable-path convention (WARN only)
# --------------------------------------------------------------------------
def check_path_convention(repo: str, p: Printer) -> int:
    """WARN when a writing SKILL.md does not reference the data-root convention.

    Returns the number of warnings.
    """
    p.header("[3] Configurable-path convention")
    warns = 0

    for skill in SKILL_DIRS:
        skill_md = os.path.join(repo, skill, "SKILL.md")
        rel = os.path.relpath(skill_md, repo)
        if not os.path.isfile(skill_md):
            continue
        content = read_file(skill_md)
        writes = bool(WRITE_HINT_RE.search(content))
        references = bool(PATH_CONVENTION_RE.search(content))
        if writes and not references:
            p.warn(f"{rel}: mentions writing/archiving but no IELTS_COACH_HOME / ~/ielts-coach")
            warns += 1
        else:
            p.passed(f"{rel}: path convention OK")

    return warns


# --------------------------------------------------------------------------
# Summary
# --------------------------------------------------------------------------
def print_summary(p: Printer, files_scanned: int, skills_validated: int,
                   leaks: int, warns: int, total_fails: int) -> None:
    p.header("[4] Summary")
    rows = [
        ("Files scanned", files_scanned),
        ("Skills validated", f"{skills_validated}/{len(SKILL_DIRS)}"),
        ("Leaks found", leaks),
        ("Warnings", warns),
        ("Total FAILs", total_fails),
    ]
    width = max(len(label) for label, _ in rows)
    for label, value in rows:
        p.info(f"  {label.ljust(width)} : {value}")

    print()
    if total_fails == 0:
        p.passed("All hard checks passed.")
    else:
        p.failed(f"{total_fails} check(s) failed.")


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------
def default_repo_root() -> str:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.dirname(script_dir)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="validate_skills.py",
        description="Bandwise skill repository validator / CI hardening gate.",
    )
    parser.add_argument(
        "--repo",
        default=default_repo_root(),
        help="repo root to scan (default: parent of this script's dir)",
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        help="disable colorized output (CI-safe plain text)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    repo = os.path.abspath(args.repo)
    color = not args.no_color and sys.stdout.isatty()
    p = Printer(color)

    if not os.path.isdir(repo):
        p.failed(f"repo path not found: {repo}")
        return 1

    p.info(f"Validating Bandwise repo: {repo}")

    fm_fails, skills_validated = check_frontmatter(repo, p)
    leaks, files_scanned = check_leaks(repo, p)
    warns = check_path_convention(repo, p)

    total_fails = fm_fails + leaks
    print_summary(p, files_scanned, skills_validated, leaks, warns, total_fails)

    return 0 if total_fails == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
