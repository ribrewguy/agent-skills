"""project-kickoff: stand up a project's tracker, memory, instruction files and documentation tree.

Every step checks before it writes and reports one line per fact or action:
OK, KEEP, WRITE, RUN, SKIP, ASK or FAIL. The agent reads ASK lines and decides;
the tool never overwrites or renames existing tracked content. Stdlib only, runs
on the macOS system python3 (3.9).
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Optional

ASSETS = Path(__file__).resolve().parents[2] / "skills/project-kickoff/assets"
NAME_RE = re.compile(r"^[a-z][a-z0-9-]*$")
KINDS = ("OK", "KEEP", "WRITE", "RUN", "SKIP", "ASK", "FAIL")
PLACEHOLDER = "<open-decisions-epic>"
TEMPLATES = (
    "CLAUDE.md", "README.md", "docs/prds/project.md", "docs/architecture/overview.md",
    "docs/policies/development/README.md", "docs/policies/development/technical-decisions.md",
    "docs/design/features/README.md", "docs/research/README.md",
)
ENV: Optional[dict] = None  # tests inject an isolated environment; None means inherit


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def title(name: str) -> str:
    words = name.replace("-", " ")
    return words[:1].upper() + words[1:]


def DOC_PATHS(name: str) -> list:
    return [
        "README.md", f"docs/prds/{name}.md", "docs/architecture/overview.md",
        "docs/policies/development/README.md", "docs/policies/development/technical-decisions.md",
        "docs/design/features/README.md", "docs/research/README.md",
    ]


class Report:
    def __init__(self) -> None:
        self.lines: list = []

    def add(self, kind: str, message: str) -> None:
        if kind not in KINDS:
            raise ValueError(kind)
        self.lines.append(f"{kind} {message}")

    def extend(self, other: "Report") -> None:
        self.lines.extend(other.lines)

    def kinds(self) -> set:
        return {line.split(" ", 1)[0] for line in self.lines}

    @property
    def status(self) -> int:
        kinds = self.kinds()
        if "FAIL" in kinds:
            return 1
        if "ASK" in kinds:
            return 2
        return 0


def render(template: str, **values: str) -> str:
    text = (ASSETS / "templates" / template).read_text()
    for key, value in values.items():
        text = text.replace("{{" + key + "}}", value)
    leftover = re.search(r"\{\{([a-z_]+)\}\}", text)
    if leftover:
        raise KeyError(f"{template}: no value for {{{{{leftover.group(1)}}}}}")
    return text


def detect_parent(root: Path) -> Optional[Path]:
    for name in ("AGENTS.md", "CLAUDE.md"):
        candidate = root.resolve().parent / name
        if candidate.is_file():
            return candidate
    return None


def run(cmd: list, cwd: Path, env: Optional[dict] = None, stdin: Optional[str] = None) -> subprocess.CompletedProcess:
    merged = dict(os.environ) if ENV is None else dict(ENV)
    if env:
        merged.update(env)
    return subprocess.run(cmd, cwd=str(cwd), env=merged, capture_output=True, text=True, input=stdin)


def which(tool: str) -> Optional[str]:
    path = (ENV or os.environ).get("PATH")
    return shutil.which(tool, path=path)


def inventory(root: Path, home: Path, name: Optional[str] = None) -> dict:
    root = root.resolve()
    toplevel = run(["git", "rev-parse", "--show-toplevel"], root)
    is_git = toplevel.returncode == 0 and Path(toplevel.stdout.strip()).resolve() == root
    claude, agents = root / "CLAUDE.md", root / "AGENTS.md"
    hook = root / ".beads/hooks/pre-commit"
    hooks_path = run(["git", "config", "core.hooksPath"], root).stdout.strip() if is_git else ""
    doc_paths = DOC_PATHS(name) if name else DOC_PATHS("*")
    missing = []
    for rel in doc_paths:
        if "*" in rel:
            if not list(root.glob(rel)):
                missing.append(rel)
        elif not (root / rel).is_file():
            missing.append(rel)
    return {
        "is_git": is_git,
        "has_beads": (root / ".beads/config.yaml").is_file(),
        "has_cass": (root / ".cass/playbook.yaml").is_file(),
        "claude": claude.is_file(),
        "agents": agents.is_file(),
        "instructions_identical": claude.is_file() and agents.is_file() and claude.read_bytes() == agents.read_bytes(),
        "docs_missing": missing,
        "has_checker": (root / "scripts/check_docs.py").is_file(),
        "hooks_path": hooks_path or None,
        "has_git_hook": (root / ".git/hooks/pre-commit").exists(),
        "has_gate": hook.is_file() and "# --- BEGIN PROJECT KICKOFF DOCUMENTATION GATE ---" in hook.read_text(),
        "beads_skill": (Path(home) / ".agents/skills/beads/SKILL.md").is_file(),
        "tools": {tool: which(tool) for tool in ("git", "bd", "cm", "python3", "npx")},
    }
