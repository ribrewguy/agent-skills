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


# --------------------------------------------------------------------- write
GITIGNORE_LINES = [".worktrees/", ".DS_Store", ".env", ".env.*", "!.env.example", "__pycache__/", "*.pyc", ".beadroad/"]
CHECKER_FILES = ("check_docs.py", "test_check_docs.py")


def _write_file(root: Path, rel: str, content: bytes, report: Report, dry_run: bool) -> None:
    report.add("WRITE", rel)
    if not dry_run:
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)


def _resolve_parent(root: Path, parent: str, report: Report) -> Optional[Path]:
    if parent == "no":
        return None
    found = detect_parent(root)
    if parent == "yes" and found is None:
        report.add("FAIL", "--parent yes but no AGENTS.md or CLAUDE.md exists in the enclosing directory")
    return found


def write(root: Path, name: str, purpose: str, parent: str, dry_run: bool) -> Report:
    report = Report()
    if _name_error(name, report):
        return report
    root = root.resolve()
    parent_file = _resolve_parent(root, parent, report)
    if report.status == 1:
        return report
    parent_section = render("parent-section.md", parent_file=parent_file.name) if parent_file else ""
    values = dict(name=name, title=title(name), purpose=purpose, parent=parent_section)

    # Instruction files: one rendering, two identical files.
    claude, agents = root / "CLAUDE.md", root / "AGENTS.md"
    if not claude.exists() and not agents.exists():
        content = render("CLAUDE.md", **values).encode()
        _write_file(root, "CLAUDE.md", content, report, dry_run)
        _write_file(root, "AGENTS.md", content, report, dry_run)
    elif claude.is_file() and agents.is_file() and claude.read_bytes() == agents.read_bytes():
        report.add("KEEP", "CLAUDE.md and AGENTS.md (identical, left as they are)")
    else:
        present = [p.name for p in (claude, agents) if p.is_file()]
        missing = [p.name for p in (claude, agents) if not p.is_file()]
        detail = f"{' and '.join(present)} present" + (f", {' and '.join(missing)} missing" if missing else " and they differ")
        counts = ", ".join(f"{p.name} {len(p.read_text().splitlines())} lines" for p in (claude, agents) if p.is_file())
        report.add("ASK", f"instruction files: {detail} ({counts}); propose a merged file and write both copies after the owner agrees")

    # Documentation tree.
    for rel in DOC_PATHS(name):
        if (root / rel).is_file():
            report.add("KEEP", rel)
            continue
        template = "docs/prds/project.md" if rel.startswith("docs/prds/") else rel
        _write_file(root, rel, render(template, **values).encode(), report, dry_run)

    # Checker and its tests.
    for script in CHECKER_FILES:
        rel, source = f"scripts/{script}", ASSETS / script
        target = root / rel
        if not target.exists():
            _write_file(root, rel, source.read_bytes(), report, dry_run)
        elif target.read_bytes() == source.read_bytes():
            report.add("KEEP", rel)
        else:
            report.add("KEEP", f"{rel} (differs from the skill's copy; left as it is)")

    # Gitignore.
    ignore = root / ".gitignore"
    existing = ignore.read_text().splitlines() if ignore.is_file() else []
    needed = [line for line in GITIGNORE_LINES if line not in existing]
    if needed:
        report.add("WRITE", f".gitignore (+{len(needed)} lines)")
        if not dry_run:
            prefix = "" if not existing else ("\n" if existing[-1].strip() else "")
            ignore.write_text(("\n".join(existing) + "\n" if existing else "") + prefix
                              + "# project-kickoff\n" + "\n".join(needed) + "\n")
    else:
        report.add("KEEP", ".gitignore")
    return report


# ---------------------------------------------------------------------- gate
GATE_MARKER = "# --- BEGIN PROJECT KICKOFF DOCUMENTATION GATE ---"
HOOK = ".beads/hooks/pre-commit"


def _checker_findings(root: Path, dry_run: bool = False) -> list:
    if (root / "scripts/check_docs.py").is_file():
        result = run(["python3", "scripts/check_docs.py"], root)
    else:
        result = run(["python3", str(ASSETS / "check_docs.py"), "--root", str(root)], root)
    if result.returncode == 0:
        return []
    findings = [line[len("FAIL: "):] for line in result.stderr.splitlines() if line.startswith("FAIL: ")]
    if dry_run:
        # A dry run reports gaps in what exists; files the run itself would write are not gaps.
        findings = [f for f in findings if not f.endswith(" is missing")]
    return findings or ([] if dry_run else [_tail(result.stderr or result.stdout)])


def gate(root: Path, dry_run: bool) -> Report:
    report = Report()
    root = root.resolve()
    hook = root / HOOK
    if not (root / "scripts/check_docs.py").is_file() and not dry_run:
        report.add("FAIL", "scripts/check_docs.py is missing; run write first")
        return report
    findings = _checker_findings(root, dry_run)
    if findings:
        for finding in findings:
            report.add("FAIL", f"check_docs: {finding}")
        report.add("SKIP", "gate not installed while the checker fails; fix the findings and rerun gate")
        return report
    report.add("OK", "check_docs passes")
    if not hook.is_file():
        if (root / ".beads/config.yaml").is_file():
            report.add("FAIL", f"{HOOK} is missing although .beads exists; run bd hooks install, then gate")
        elif dry_run:
            report.add("RUN", f"gate into {HOOK} once bd init has created it")
        else:
            report.add("SKIP", ".beads not initialised (bd absent or init skipped); documentation gate not installed")
        return report
    if GATE_MARKER in hook.read_text():
        report.add("KEEP", f"{HOOK} already carries the documentation gate")
        return report
    report.add("WRITE", f"{HOOK} (+documentation gate after the beads markers)")
    if not dry_run:
        with hook.open("a") as handle:
            handle.write((ASSETS / "pre-commit-gate.sh").read_text())
        hook.chmod(hook.stat().st_mode | 0o111)
    return report


# ---------------------------------------------------------------------- seed
EPIC_TITLE = "Open decisions"
EPIC_DESCRIPTION = ("Every unresolved technical or product decision is a child of this epic. "
                    "When a decision is made, record it with its status in the register or owning "
                    "document and close the child.")
REGISTER = "docs/policies/development/technical-decisions.md"
PLACEHOLDER_FILES = ("CLAUDE.md", "AGENTS.md", "README.md")


def unresolved_rows(register_text: str) -> list:
    rows = []
    for line in register_text.splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) >= 3 and cells[2] == "unresolved":
            rows.append(cells[0])
    return rows


def _bd_json(root: Path, args: list) -> list:
    result = run(["bd", *args, "--json"], root)
    if result.returncode != 0:
        raise RuntimeError(_tail(result.stderr or result.stdout))
    import json
    try:
        data = json.loads(result.stdout or "[]")
    except ValueError:
        raise RuntimeError(f"unexpected non-JSON output: {_tail(result.stdout)}")
    if data is None:
        return []
    return data if isinstance(data, list) else [data]


def _bd_create(root: Path, title_text: str, issue_type: str, report: Report, dry_run: bool,
               parent: Optional[str] = None, description: str = "") -> Optional[str]:
    cmd = ["bd", "create", "--title", title_text, "--type", issue_type, "--priority", "2"]
    if parent:
        cmd += ["--parent", parent]
    if description:
        cmd += ["--description", description]
    report.add("RUN", " ".join(cmd[:8]) + (f" --parent {parent}" if parent else ""))
    if dry_run:
        return None
    created = _bd_json(root, cmd[1:])
    return created[0]["id"]


def seed(root: Path, name: str, dry_run: bool) -> Report:
    report = Report()
    root = root.resolve()
    if not which("bd"):
        report.add("SKIP", f"bd not on PATH; no open-decisions epic created and {PLACEHOLDER} stays in the instruction files and README")
        return report
    if not (root / ".beads/config.yaml").is_file():
        report.add("SKIP", ".beads not initialised; run init first")
        return report
    try:
        epics = [e for e in _bd_json(root, ["list", "--type", "epic"]) if e.get("title") == EPIC_TITLE]
        if epics:
            epic_id = epics[0]["id"]
            report.add("KEEP", f"epic {epic_id} ({EPIC_TITLE})")
        else:
            epic_id = _bd_create(root, EPIC_TITLE, "epic", report, dry_run, description=EPIC_DESCRIPTION)
            if epic_id:
                report.add("OK", f"epic {epic_id} created")
        register = root / REGISTER
        concerns = unresolved_rows(register.read_text()) if register.is_file() else []
        existing = {c.get("title") for c in _bd_json(root, ["list", "--parent", epic_id])} if epic_id else set()
        for concern in concerns:
            child_title = f"Decide: {concern}"
            if child_title in existing:
                report.add("KEEP", f"child {child_title!r}")
            else:
                _bd_create(root, child_title, "task", report, dry_run, parent=epic_id,
                           description=f"Resolve the {concern} row of {REGISTER} and record its status.")
    except RuntimeError as error:
        report.add("FAIL", f"bd: {error}")
        return report
    if not epic_id:
        return report
    for rel in PLACEHOLDER_FILES:
        path = root / rel
        if path.is_file() and PLACEHOLDER in path.read_text():
            report.add("WRITE", f"{rel} ({PLACEHOLDER} -> {epic_id})")
            if not dry_run:
                path.write_text(path.read_text().replace(PLACEHOLDER, epic_id))
    return report


# -------------------------------------------------------------------- commit
def owned_paths(root: Path, name: str) -> list:
    """Paths the kickoff is responsible for; nothing else is staged."""
    candidates = ["CLAUDE.md", "AGENTS.md", ".gitignore", "scripts/check_docs.py", "scripts/test_check_docs.py",
                  ".beads", ".cass"] + DOC_PATHS(name)
    return [rel for rel in candidates if (root / rel).exists()]


def commit(root: Path, name: str, trailers: list, dry_run: bool) -> Report:
    report = Report()
    if _name_error(name, report):
        return report
    root = root.resolve()
    if not inventory(root, Path.home(), name)["is_git"]:
        if dry_run:
            report.add("RUN", f"git commit -m 'chore: kick off {name}' once init has created the repository")
        else:
            report.add("FAIL", "not a git repository here (a parent repository does not count); run init first")
        return report
    findings = _checker_findings(root, dry_run)
    if findings:
        for finding in findings:
            report.add("FAIL", f"check_docs: {finding}")
        return report
    report.add("OK", "check_docs passes")
    if (root / "scripts/test_check_docs.py").is_file():
        tests = run(["python3", "-m", "unittest", "discover", "-s", "scripts", "-p", "test_*.py"], root)
        if tests.returncode != 0:
            report.add("FAIL", f"checker tests: {_tail(tests.stderr or tests.stdout)}")
            return report
        report.add("OK", "checker tests pass")
    owned = owned_paths(root, name)
    pending = run(["git", "status", "--porcelain", "--untracked-files=all", "--"] + owned, root).stdout.splitlines()
    if not pending:
        report.add("OK", "nothing to commit")
        return report
    message = f"chore: kick off {name}\n" + ("\n" + "\n".join(trailers) + "\n" if trailers else "")
    report.add("RUN", f"git add -- {' '.join(owned)}")
    report.add("RUN", f"git commit -m 'chore: kick off {name}'" + (f" (+{len(trailers)} trailer lines)" if trailers else ""))
    if dry_run:
        return report
    run(["git", "add", "--"] + owned, root)
    result = run(["git", "commit", "-q", "-F", "-", "--only", "--"] + owned, root, stdin=message)
    if result.returncode != 0:
        report.add("FAIL", f"git commit: {_tail(result.stderr or result.stdout)}")
        return report
    report.add("OK", f"committed {run(['git', 'rev-parse', '--short', 'HEAD'], root).stdout.strip()}")
    others = [line[3:] for line in run(["git", "status", "--porcelain"], root).stdout.splitlines()]
    if others:
        report.add("SKIP", f"left alone, not part of the kickoff: {', '.join(others)}")
    leftover = [rel for rel in PLACEHOLDER_FILES if (root / rel).is_file() and PLACEHOLDER in (root / rel).read_text()]
    if leftover:
        report.add("SKIP", f"{PLACEHOLDER} remains in {', '.join(leftover)}; run seed once bd is available, then commit again")
    return report


# ----------------------------------------------------------------------- all
def all_steps(root: Path, home: Path, name: str, purpose: str, parent: str, trailers: list, dry_run: bool) -> Report:
    report = Report()
    steps = [
        lambda: preflight(root, home, dry_run),
        lambda: init(root, name, dry_run),
        lambda: write(root, name, purpose, parent, dry_run),
        lambda: gate(root, dry_run),
        lambda: seed(root, name, dry_run),
        lambda: commit(root, name, trailers, dry_run),
    ]
    for step in steps:
        part = step()
        report.extend(part)
        if part.status != 0 and not dry_run:
            break
    return report


# ----------------------------------------------------------------------- cli
def main(argv: list) -> int:
    import argparse

    parser = argparse.ArgumentParser(prog="project-kickoff",
                                     description="Stand up a project: git, Beads, cass-memory, identical instruction files, the documentation tree, checker and gate.")
    parser.add_argument("step", choices=["preflight", "init", "write", "gate", "seed", "commit", "all"])
    parser.add_argument("--dir", default=".", help="project directory (default: current directory)")
    parser.add_argument("--name", help="project name and Beads prefix (default: slug of the directory name)")
    parser.add_argument("--purpose", help="one sentence for README.md and the PRD (required by write and all)")
    parser.add_argument("--parent", choices=["auto", "yes", "no"], default="auto",
                        help="parent instructions one level up: auto-detect, require, or ignore")
    parser.add_argument("--trailer", action="append", default=[], metavar="LINE", help="trailer line for the kickoff commit (repeatable)")
    parser.add_argument("--home", default=str(Path.home()), help=argparse.SUPPRESS)
    parser.add_argument("--dry-run", action="store_true", help="report what would happen; write nothing")
    args = parser.parse_args(argv)

    root = Path(args.dir).resolve()
    name = args.name or slug(root.name)
    if args.step in ("write", "all") and not args.purpose:
        parser.error(f"{args.step} requires --purpose")
    home = Path(args.home)
    dispatch = {
        "preflight": lambda: preflight(root, home, args.dry_run),
        "init": lambda: init(root, name, args.dry_run),
        "write": lambda: write(root, name, args.purpose, args.parent, args.dry_run),
        "gate": lambda: gate(root, args.dry_run),
        "seed": lambda: seed(root, name, args.dry_run),
        "commit": lambda: commit(root, name, args.trailer, args.dry_run),
        "all": lambda: all_steps(root, home, name, args.purpose, args.parent, args.trailer, args.dry_run),
    }
    report = dispatch[args.step]()
    print("\n".join(report.lines))
    return report.status
