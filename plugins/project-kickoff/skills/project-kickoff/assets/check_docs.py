"""Check project documentation: instruction parity, portable links, undated filenames, indexes, design structure.

Installed by the project-kickoff skill; runs standalone with the macOS system python3.
"""

from __future__ import annotations  # Python 3.9 (macOS system python3) runs the hook

from pathlib import Path
import re
import subprocess
import sys
import tempfile
from urllib.parse import unquote


ROOT = Path(__file__).resolve().parents[1]


def date_in_name(name: str) -> bool:
    """Recognize common numeric, named-month and quarter date conventions."""
    year = r"(?:19|20)\d{2}"
    month_number = r"(?:0?[1-9]|1[0-2])"
    day = r"(?:0?[1-9]|[12]\d|3[01])"
    separator = r"[-_. ]"
    month = r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
    patterns = [
        rf"(?<!\d){year}{separator}{month_number}(?:{separator}{day})?(?!\d)",
        rf"(?<!\d){year}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])?(?!\d)",
        rf"(?<!\d)(?:{month_number}{separator}{day}|{day}{separator}{month_number}){separator}{year}(?!\d)",
        rf"(?<![a-z]){month}{separator}(?:{day}{separator})?{year}(?!\d)",
        rf"(?<!\d){day}{separator}{month}{separator}{year}(?!\d)",
        rf"(?<!\d){year}{separator}{month}(?:{separator}{day})?(?![a-z\d])",
        rf"(?<!\d){year}{separator}?q[1-4](?!\d)",
        rf"(?<![a-z\d])q[1-4]{separator}?{year}(?!\d)",
    ]
    return any(re.search(pattern, name, re.IGNORECASE) for pattern in patterns)


def link_error(document: Path, target: str, root: Path) -> str | None:
    """Validate a Markdown destination; local links must stay in the checkout."""
    target = target.strip().removeprefix("<").removesuffix(">")
    decoded = unquote(target)
    if (decoded.startswith(("/", "\\", "~"))
            or re.match(r"^[a-zA-Z]:[/\\]", decoded)
            or decoded.lower().startswith("file:")):
        return f"absolute local link is not portable: {target}"
    if re.match(r"[a-zA-Z][a-zA-Z0-9+.-]*:", target) or target.startswith("#"):
        return None
    path, _, fragment = unquote(target).partition("#")
    resolved = (document.parent / path).resolve()
    if not resolved.is_relative_to(root.resolve()):
        return f"local link leaves the repository: {target}"
    if not resolved.exists():
        return f"missing local link {target}"
    if fragment and path and resolved.suffix == ".md" and fragment not in anchors(resolved):
        return f"missing heading anchor {target}"
    return None


def anchors(document: Path) -> set[str]:
    """Approximate GitHub heading slugs: lowercase, punctuation dropped, spaces hyphenated."""
    headings = re.findall(r"^#{1,6}\s+(.+?)\s*$", document.read_text(), re.MULTILINE)
    return {re.sub(r"[^\w\- ]", "", heading.lower()).replace(" ", "-") for heading in headings}


# Each directory's README.md must link every sibling document.
INDEXED_DIRECTORIES = ("docs/design/features", "docs/policies/development", "docs/research")
DESIGN_HEADER_LINES = ("Business authority:", "Status:")


def index_errors(root: Path) -> list[str]:
    errors = []
    for directory in INDEXED_DIRECTORIES:
        index = root / directory / "README.md"
        if not index.exists():
            errors.append(f"{directory}: missing README.md index")
            continue
        linked = {unquote(target.split("#", 1)[0])
                  for target in re.findall(r"\]\(([^)]+)\)", index.read_text())}
        for document in sorted((root / directory).glob("*.md")):
            if document.name != "README.md" and document.name not in linked:
                errors.append(f"{directory}/README.md: does not index {document.name}")
    return errors


def design_errors(root: Path) -> list[str]:
    """Feature designs share header lines and end with tracked open decisions."""
    errors = []
    for design in sorted((root / "docs/design/features").glob("*.md")):
        if design.name == "README.md":
            continue
        name = design.relative_to(root)
        text = design.read_text()
        for prefix in DESIGN_HEADER_LINES:
            if not re.search(rf"^{re.escape(prefix)} \S", text, re.MULTILINE):
                errors.append(f"{name}: missing '{prefix}' line")
        headings = re.findall(r"^## (.+?)\s*$", text, re.MULTILINE)
        if not headings or headings[-1] != "Open decisions":
            errors.append(f"{name}: must end with '## Open decisions' section")
        elif not re.search(r"^Tracking: `[\w.-]+`", text.rsplit("## Open decisions", 1)[1], re.MULTILINE):
            errors.append(f"{name}: open decisions lack a 'Tracking:' issue reference")
    return errors


def check(root: Path = ROOT, names: list[str] | None = None) -> list[str]:
    """Check documents under root; names defaults to its tracked and unignored files."""
    errors = []
    if (root / "AGENTS.md").read_bytes() != (root / "CLAUDE.md").read_bytes():
        errors.append("AGENTS.md and CLAUDE.md differ")

    if names is None:
        names = subprocess.check_output(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
            cwd=root,
        ).decode().split("\0")
    for name in sorted(set(filter(None, names))):
        if date_in_name(Path(name).name):
            errors.append(f"date-bearing filename: {name}")

    documents = [root / name for name in ("README.md", "AGENTS.md", "CLAUDE.md")]
    documents += sorted((root / "docs").rglob("*.md"))
    for document in documents:
        for target in re.findall(r"\]\(([^)]+)\)", document.read_text()):
            error = link_error(document, target, root)
            if error:
                errors.append(f"{document.relative_to(root)}: {error}")
    return errors + index_errors(root) + design_errors(root)


def check_staged(repo: Path = ROOT) -> list[str]:
    """Check exactly the index snapshot that Git will commit, ignoring unstaged edits.

    Git commands inherit GIT_INDEX_FILE, so partial commits (git commit <path>)
    are checked against the temporary index Git prepares for them.
    """
    names = subprocess.check_output(["git", "ls-files", "--cached", "-z"], cwd=repo)
    with tempfile.TemporaryDirectory() as snapshot:
        subprocess.run(["git", "checkout-index", "--all", f"--prefix={snapshot}/"],
                       cwd=repo, check=True)
        return check(Path(snapshot), names.decode().split("\0"))


if __name__ == "__main__":
    staged = sys.argv[1:] == ["--staged"]
    if sys.argv[1:] and not staged:
        sys.exit("Usage: python3 scripts/check_docs.py [--staged]")
    findings = check_staged() if staged else check()
    for finding in findings:
        print(f"FAIL: {finding}", file=sys.stderr)
    if findings:
        sys.exit(1)
    print("PASS: instruction parity, portable local Markdown links and anchors, "
          "common date-bearing filenames, index coverage and feature-design structure")
