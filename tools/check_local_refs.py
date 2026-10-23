#!/usr/bin/env python3
"""Refuse content that identifies one machine: home paths, scratch paths, local settings.

Usage: python3 tools/check_local_refs.py [--staged] [path ...]

Without arguments, every tracked file is checked. With --staged, exactly the
index snapshot Git is about to commit is checked (added, copied, modified and
renamed paths), so unstaged edits do not count. Explicit paths check those
working-tree files. Also requires AGENTS.md and CLAUDE.md to be identical when
both exist in the checked set. Prints "FAIL: <path>:<line>: <why>" per finding
and exits 1 if there are any. Stdlib only; runs on the macOS system python3.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLACEHOLDER = r"(?!user\b|example\b|<|\$|\{)"
PATTERNS = [
    (re.compile(r"/Users/" + PLACEHOLDER + r"[A-Za-z0-9_.-]+"), "macOS home path"),
    (re.compile(r"/home/" + PLACEHOLDER + r"[A-Za-z0-9_.-]+/"), "Linux home path"),
    (re.compile(r"[A-Za-z]:\\Users\\" + PLACEHOLDER + r"[A-Za-z0-9_.-]+"), "Windows home path"),
    (re.compile(r"/private/tmp/claude-\d+/|(?:/private)?/var/folders/"), "per-machine temp path"),
    (re.compile(r"/Volumes/[A-Za-z0-9_.-]+"), "mounted volume path"),
]
LOCAL_BASENAMES = {"settings.local.json", ".env", ".env.local", ".mcp.local.json", ".DS_Store"}


def is_local_file(path: str) -> str | None:
    name = Path(path).name
    if name in LOCAL_BASENAMES or (name.startswith(".env.") and name != ".env.example"):
        return f"local settings file {name} must not be committed"
    return None


def content_findings(path: str, text: str) -> list[str]:
    findings = []
    for number, line in enumerate(text.splitlines(), 1):
        for pattern, why in PATTERNS:
            match = pattern.search(line)
            if match:
                findings.append(f"{path}:{number}: {why} {match.group(0)!r}")
                break
    return findings


def _text(blob: bytes) -> str | None:
    if b"\0" in blob[:8000]:
        return None
    return blob.decode("utf-8", errors="replace")


def check(files: dict[str, bytes]) -> list[str]:
    """files maps repo-relative path to content."""
    errors = []
    for path in sorted(files):
        reason = is_local_file(path)
        if reason:
            errors.append(f"{path}: {reason}")
            continue
        if path in ("tools/check_local_refs.py", "tools/test_check_local_refs.py"):
            continue  # the checker and its tests spell the patterns on purpose
        text = _text(files[path])
        if text is not None:
            errors.extend(content_findings(path, text))
    if "AGENTS.md" in files and "CLAUDE.md" in files and files["AGENTS.md"] != files["CLAUDE.md"]:
        errors.append("AGENTS.md and CLAUDE.md differ")
    return errors


def staged_files(repo: Path) -> dict[str, bytes]:
    names = subprocess.check_output(
        ["git", "diff", "--cached", "--name-only", "-z", "--diff-filter=ACMR"], cwd=repo
    ).decode().split("\0")
    files = {n: subprocess.check_output(["git", "show", f":{n}"], cwd=repo) for n in names if n}
    # Parity needs both instruction files even when only one is staged.
    for name in ("AGENTS.md", "CLAUDE.md"):
        if name not in files and any(n in files for n in ("AGENTS.md", "CLAUDE.md")):
            try:
                files[name] = subprocess.check_output(["git", "show", f":{name}"], cwd=repo,
                                                      stderr=subprocess.DEVNULL)
            except subprocess.CalledProcessError:
                pass
    return files


def tracked_files(repo: Path) -> dict[str, bytes]:
    names = subprocess.check_output(["git", "ls-files", "-z"], cwd=repo).decode().split("\0")
    return {n: (repo / n).read_bytes() for n in names if n and (repo / n).is_file()}


def main(argv: list[str]) -> int:
    if argv[:1] == ["--staged"]:
        files = staged_files(ROOT)
    elif argv:
        files = {a: Path(a).read_bytes() for a in argv}
    else:
        files = tracked_files(ROOT)
    findings = check(files)
    for finding in findings:
        print(f"FAIL: {finding}", file=sys.stderr)
    if findings:
        return 1
    print(f"PASS: no machine-local paths or local settings in {len(files)} files")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
