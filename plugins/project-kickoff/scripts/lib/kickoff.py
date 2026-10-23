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


# ----------------------------------------------------------------- preflight
BEADS_SKILL_INSTALL = ["npx", "skills", "add", "steveyegge/beads", "--skill", "beads", "--global", "-y"]
INSTALL_HINTS = {
    "bd": "install bd (the Beads CLI); Beads steps will be skipped",
    "cm": "install cm (cass-memory); the cass step will be skipped",
}


def _tail(text: str, lines: int = 3) -> str:
    return " | ".join(line for line in text.strip().splitlines()[-lines:])


def preflight(root: Path, home: Path, dry_run: bool) -> Report:
    report = Report()
    inv = inventory(root, home)
    tools = inv["tools"]
    for tool in ("git", "python3"):
        if not tools[tool]:
            report.add("FAIL", f"{tool} is not on PATH")
    if tools["git"]:
        for key in ("user.name", "user.email"):
            value = run(["git", "config", "--get", key], root).stdout.strip()
            if value:
                report.add("OK", f"git {key} is set")
            else:
                report.add("FAIL", f"git {key} is not set; set it before the kickoff commit")
    for tool, hint in INSTALL_HINTS.items():
        if tools[tool]:
            version = run([tool, "--version"], root).stdout.strip().splitlines()
            report.add("OK", f"{tool} on PATH ({version[0] if version else 'version unknown'})")
        else:
            report.add("SKIP", f"{tool} not on PATH: {hint}")
    if inv["beads_skill"]:
        report.add("OK", "Beads skill installed at ~/.agents/skills/beads")
    elif not tools["npx"]:
        report.add("SKIP", f"Beads skill missing and npx not on PATH; install it with: {' '.join(BEADS_SKILL_INSTALL)}")
    else:
        report.add("RUN", " ".join(BEADS_SKILL_INSTALL))
        if not dry_run:
            result = run(BEADS_SKILL_INSTALL, root)
            if result.returncode != 0 or not inventory(root, home)["beads_skill"]:
                report.add("FAIL", f"Beads skill install did not land: {_tail(result.stderr or result.stdout)}")
            else:
                report.add("OK", "Beads skill installed")
    report.add("OK" if inv["is_git"] else "KEEP", "git repository" if inv["is_git"] else "no git repository yet")
    for key, label in (("has_beads", ".beads"), ("has_cass", ".cass"), ("has_checker", "scripts/check_docs.py"), ("has_gate", "pre-commit documentation gate")):
        report.add("OK", f"{label}: {'present' if inv[key] else 'absent'}")
    if inv["claude"] or inv["agents"]:
        state = "identical" if inv["instructions_identical"] else "differ or one is missing"
        report.add("OK", f"instruction files: {state}")
    else:
        report.add("OK", "instruction files: absent")
    report.add("OK", f"documents missing: {len(inv['docs_missing'])} of 7")
    return report


# ---------------------------------------------------------------------- init
def _name_error(name: str, report: Report) -> bool:
    if NAME_RE.match(name):
        return False
    report.add("FAIL", f"name {name!r} is not a valid prefix; use lowercase letters, digits and hyphens, e.g. {slug(name) or 'demo-app'!r}")
    return True


def init(root: Path, name: str, dry_run: bool) -> Report:
    report = Report()
    if _name_error(name, report):
        return report
    inv = inventory(root, Path.home(), name)
    if inv["is_git"]:
        report.add("KEEP", "git repository")
    else:
        report.add("RUN", "git init && git symbolic-ref HEAD refs/heads/main")
        if not dry_run:
            result = run(["git", "init", "-q"], root)
            if result.returncode != 0:
                report.add("FAIL", f"git init: {_tail(result.stderr)}")
                return report
            run(["git", "symbolic-ref", "HEAD", "refs/heads/main"], root)
            inv = inventory(root, Path.home(), name)
    if inv["has_beads"]:
        report.add("KEEP", ".beads (already initialised)")
    else:
        foreign_hooks = inv["has_git_hook"] or (inv["hooks_path"] and not inv["hooks_path"].rstrip("/").endswith(".beads/hooks"))
        if foreign_hooks:
            where = ".git/hooks/pre-commit" if inv["has_git_hook"] else f"core.hooksPath={inv['hooks_path']}"
            report.add("ASK", f"existing hook setup ({where}); bd init would displace it. Chain it from the Beads hook or remove it, then rerun init")
        elif not which("bd"):
            report.add("SKIP", "bd not on PATH; .beads not initialised")
        else:
            cmd = ["bd", "init", "--skip-agents", "--prefix", name, "--non-interactive"]
            report.add("RUN", " ".join(cmd))
            if not dry_run:
                result = run(cmd, root)
                if result.returncode != 0 or not (root / ".beads/config.yaml").is_file():
                    report.add("FAIL", f"bd init: {_tail(result.stderr or result.stdout)}")
    if inv["has_cass"]:
        report.add("KEEP", ".cass (already initialised)")
    elif not which("cm"):
        report.add("SKIP", "cm not on PATH; .cass not initialised")
    else:
        cmd = ["cm", "init", "--repo", "--no-interactive"]
        report.add("RUN", " ".join(cmd))
        if not dry_run:
            result = run(cmd, root)
            if result.returncode != 0 or not (root / ".cass/playbook.yaml").is_file():
                report.add("FAIL", f"cm init: {_tail(result.stderr or result.stdout)}")
    return report
