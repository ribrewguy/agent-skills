#!/usr/bin/env python3
"""Check SKILL.md files against the stricter rules Codex enforces.

Usage: python3 tools/check_skill_spec.py <plugin-dir>...

For each plugin directory, every skills/<name>/SKILL.md is checked.
Prints "OK <skill>" per passing skill and "FAIL <skill>: <rule>: <detail>"
per failure; exits 1 if any skill fails. Stdlib only.

Rules: description-length (600-950 chars), description-quoted (wrapped in
double quotes, none inside), body-length (<= 500 lines after frontmatter),
reference-link (references/*.md must not link to sibling references),
bare-url (SKILL.md only; http(s):// only inside markdown links), name-matches-dir.
A missing references/ directory is not a failure.
"""
import argparse
import re
import sys
from pathlib import Path

MIN_DESC, MAX_DESC, MAX_BODY_LINES = 600, 950, 500
DESC_RE = re.compile(r"^description:[ \t]*(.*)$", re.MULTILINE)
NAME_RE = re.compile(r"^name:[ \t]*(.*)$", re.MULTILINE)
SIBLING_LINK_RE = re.compile(r"\]\((?:\./)?[^/)#\s]+\.md[)#]")
BARE_URL_RE = re.compile(r"(?<!\]\()https?://[A-Za-z0-9]")


def split_frontmatter(text):
    """Return (frontmatter, body) split on the first two '---' lines."""
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        return None, text
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return "\n".join(lines[1:i]), "\n".join(lines[i + 1:])
    return None, text


def check_skill(skill_dir: Path) -> list[str]:
    """Return failure strings for one skill directory (empty means pass)."""
    skill_dir = Path(skill_dir)
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.is_file():
        return ["frontmatter: SKILL.md not found"]
    text = skill_md.read_text(encoding="utf-8")
    front, body = split_frontmatter(text)
    if front is None:
        return ["frontmatter: missing or unterminated --- block"]

    failures = []

    name_m = NAME_RE.search(front)
    name = name_m.group(1).strip().strip("\"'") if name_m else ""
    if name != skill_dir.name:
        failures.append(
            f"name-matches-dir: name '{name}' does not match directory '{skill_dir.name}'"
        )

    desc_m = DESC_RE.search(front)
    if not desc_m:
        failures.append("description-quoted: no description field")
    else:
        raw = desc_m.group(1).strip()
        quoted = len(raw) >= 2 and raw.startswith('"') and raw.endswith('"')
        value = raw[1:-1] if quoted else raw
        if not quoted:
            failures.append("description-quoted: value is not wrapped in double quotes")
        elif '"' in value:
            failures.append("description-quoted: inner double quote in value")
        if not MIN_DESC <= len(value) <= MAX_DESC:
            failures.append(
                f"description-length: {len(value)} chars, need {MIN_DESC}-{MAX_DESC}"
            )

    body_lines = len(body.rstrip("\n").split("\n")) if body.strip() else 0
    if body_lines > MAX_BODY_LINES:
        failures.append(f"body-length: {body_lines} lines, max {MAX_BODY_LINES}")

    refs = skill_dir / "references"
    if refs.is_dir():
        for ref in sorted(refs.glob("*.md")):
            ref_text = ref.read_text(encoding="utf-8")
            for m in SIBLING_LINK_RE.finditer(ref_text):
                failures.append(
                    f"reference-link: {ref.name} links to a sibling reference: {m.group(0)}"
                )

    for m in BARE_URL_RE.finditer(body):
        snippet = body[m.start():m.start() + 40].split("\n")[0]
        failures.append(f"bare-url: SKILL.md: {snippet}")

    return failures


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Check SKILL.md files against the spec rules.")
    parser.add_argument("plugin_dirs", nargs="+", type=Path)
    args = parser.parse_args(argv)

    failed = False
    for plugin in args.plugin_dirs:
        skill_dirs = sorted(p.parent for p in (plugin / "skills").glob("*/SKILL.md"))
        if not skill_dirs:
            print(f"FAIL {plugin.name}: frontmatter: no skills/*/SKILL.md found")
            failed = True
        for skill_dir in skill_dirs:
            failures = check_skill(skill_dir)
            if failures:
                failed = True
                for f in failures:
                    print(f"FAIL {skill_dir.name}: {f}")
            else:
                print(f"OK {skill_dir.name}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
