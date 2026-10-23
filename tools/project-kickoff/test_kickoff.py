"""Behaviour tests for plugins/project-kickoff/scripts/lib/kickoff.py.

Every test runs in a temporary directory with an isolated HOME and a PATH that
holds stub bd, cm and npx executables, so nothing here touches the machine's
tracker, memory or installed skills.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "plugins/project-kickoff/scripts/lib"))
import kickoff  # noqa: E402


class Sandbox:
    """Temp HOME, temp project root, stub tools on PATH, a git identity."""

    def __init__(self, with_bd: bool = True, with_npx: bool = True, beads_skill: bool = True,
                 git_identity: bool = True):
        self.temp = Path(tempfile.mkdtemp()).resolve()
        self.home = self.temp / "home"
        self.bin = self.temp / "bin"
        self.log = self.temp / "log"
        self.parent = self.temp / "projects"
        self.root = self.parent / "demo-app"
        for d in (self.home, self.bin, self.log, self.root):
            d.mkdir(parents=True)
        if beads_skill:
            skill = self.home / ".agents/skills/beads/SKILL.md"
            skill.parent.mkdir(parents=True)
            skill.write_text("---\nname: beads\n---\n")
        gitconfig = self.temp / "gitconfig"
        gitconfig.write_text("[user]\n\tname = Demo Person\n\temail = demo@example.com\n" if git_identity else "")
        self.env = {
            "PATH": f"{self.bin}:/usr/bin:/bin",
            "HOME": str(self.home),
            "GIT_CONFIG_GLOBAL": str(gitconfig),
            "GIT_CONFIG_NOSYSTEM": "1",
            "STUB_LOG": str(self.log),
            "LANG": "C.UTF-8",
        }
        if with_bd:
            self._stub("bd", BD_STUB)
        self._stub("cm", CM_STUB)
        if with_npx:
            self._stub("npx", NPX_STUB)
        kickoff.ENV = self.env

    def _stub(self, name: str, body: str) -> None:
        path = self.bin / name
        path.write_text(body)
        path.chmod(0o755)

    def git(self, *args: str, cwd: Path | None = None) -> str:
        return subprocess.run(["git", *args], cwd=cwd or self.root, env=self.env, check=True,
                              capture_output=True, text=True).stdout

    def logged(self, tool: str) -> str:
        path = self.log / f"{tool}.log"
        return path.read_text() if path.exists() else ""

    def cleanup(self) -> None:
        shutil.rmtree(self.temp, ignore_errors=True)


BD_STUB = r'''#!/bin/sh
echo "$@" >> "$STUB_LOG/bd.log"
case "$1" in
  --version) echo "bd version 1.3.1" ;;
  init)
    mkdir -p .beads/hooks
    printf 'issue-prefix: demo-app\n' > .beads/config.yaml
    printf '{"backend":"dolt"}\n' > .beads/metadata.json
    printf '#!/usr/bin/env sh\n# --- BEGIN BEADS INTEGRATION v1.3.1 ---\n# managed\n# --- END BEADS INTEGRATION v1.3.1 ---\n' > .beads/hooks/pre-commit
    chmod +x .beads/hooks/pre-commit
    printf '\n# Beads / Dolt files (added by bd init)\n.dolt/\n*.gate.lock*\n' >> .gitignore
    git config core.hooksPath .beads/hooks
    echo "bd initialized" ;;
  list)
    if [ -f "$STUB_LOG/issues.json" ]; then cat "$STUB_LOG/issues.json"; else echo "[]"; fi ;;
  create)
    title=""; parent="null"; type="task"
    while [ $# -gt 0 ]; do
      case "$1" in
        --title) title=$2; shift ;;
        --title=*) title=${1#--title=} ;;
        --parent) parent="\"$2\""; shift ;;
        --parent=*) parent="\"${1#--parent=}\"" ;;
        --type) type=$2; shift ;;
        --type=*) type=${1#--type=} ;;
      esac; shift
    done
    n=$(grep -c '^' "$STUB_LOG/created" 2>/dev/null || echo 0); n=$((n + 1))
    echo "$title" >> "$STUB_LOG/created"
    obj="{\"id\": \"demo-$n\", \"title\": \"$title\", \"parent\": $parent, \"issue_type\": \"$type\"}"
    if [ -f "$STUB_LOG/issues.json" ]; then
      python3 -c "import json,sys; d=json.load(open(sys.argv[1])); d.append(json.loads(sys.argv[2])); json.dump(d, open(sys.argv[1],'w'))" "$STUB_LOG/issues.json" "$obj"
    else
      echo "[$obj]" > "$STUB_LOG/issues.json"
    fi
    echo "$obj" ;;
  *) echo "stub bd: unhandled $*" >&2; exit 1 ;;
esac
'''

CM_STUB = r'''#!/bin/sh
echo "$@" >> "$STUB_LOG/cm.log"
case "$1" in
  --version) echo "0.2.5" ;;
  init) mkdir -p .cass && : > .cass/blocked.log && printf 'schema_version: 2\nbullets: []\n' > .cass/playbook.yaml ;;
  *) echo "stub cm: unhandled $*" >&2; exit 1 ;;
esac
'''

NPX_STUB = r'''#!/bin/sh
echo "$@" >> "$STUB_LOG/npx.log"
mkdir -p "$HOME/.agents/skills/beads" && printf -- '---\nname: beads\n---\n' > "$HOME/.agents/skills/beads/SKILL.md"
'''


class SlugTests(unittest.TestCase):
    def test_slug_and_title(self):
        self.assertEqual(kickoff.slug("My App.v2"), "my-app-v2")
        self.assertEqual(kickoff.slug("--demo--"), "demo")
        self.assertEqual(kickoff.title("demo-app"), "Demo app")
        self.assertTrue(kickoff.NAME_RE.match("demo-app"))
        self.assertFalse(kickoff.NAME_RE.match("Demo App"))


class RenderTests(unittest.TestCase):
    def test_render_replaces_every_placeholder(self):
        text = kickoff.render("CLAUDE.md", name="demo-app", title="Demo app", purpose="A demo.", parent="")
        self.assertIn("# Demo app agent instructions", text)
        self.assertNotIn("{{", text)
        self.assertIn("<open-decisions-epic>", text)
        self.assertNotIn("## Parent instructions", text)

    def test_render_with_parent_section(self):
        parent = kickoff.render("parent-section.md", parent_file="AGENTS.md")
        text = kickoff.render("CLAUDE.md", name="demo-app", title="Demo app", purpose="A demo.", parent=parent)
        self.assertIn("## Parent instructions", text)
        self.assertIn("../../../AGENTS.md", text)

    def test_render_rejects_missing_value(self):
        with self.assertRaises(KeyError):
            kickoff.render("CLAUDE.md", name="demo-app")

    def test_every_template_renders_without_leftovers(self):
        values = dict(name="demo-app", title="Demo app", purpose="A demo.", parent="")
        for template in kickoff.TEMPLATES:
            with self.subTest(template=template):
                self.assertNotIn("{{", kickoff.render(template, **values))


class InventoryTests(unittest.TestCase):
    def setUp(self):
        self.sb = Sandbox()
        self.addCleanup(self.sb.cleanup)

    def test_empty_dir(self):
        inv = kickoff.inventory(self.sb.root, self.sb.home)
        self.assertFalse(inv["is_git"])
        self.assertFalse(inv["has_beads"])
        self.assertTrue(inv["beads_skill"])
        self.assertEqual(7, len(inv["docs_missing"]))
        self.assertEqual("bd", Path(inv["tools"]["bd"]).name)

    def test_nested_in_parent_repo_is_not_a_repo(self):
        self.sb.git("init", "-q", cwd=self.sb.parent)
        self.assertFalse(kickoff.inventory(self.sb.root, self.sb.home)["is_git"])
        self.sb.git("init", "-q")
        self.assertTrue(kickoff.inventory(self.sb.root, self.sb.home)["is_git"])

    def test_instruction_files_and_docs(self):
        (self.sb.root / "CLAUDE.md").write_text("same")
        (self.sb.root / "AGENTS.md").write_text("same")
        (self.sb.root / "docs/prds").mkdir(parents=True)
        (self.sb.root / "docs/prds/demo-app.md").write_text("# rules")
        inv = kickoff.inventory(self.sb.root, self.sb.home, name="demo-app")
        self.assertTrue(inv["instructions_identical"])
        self.assertNotIn("docs/prds/demo-app.md", inv["docs_missing"])
        self.assertEqual(6, len(inv["docs_missing"]))

    def test_detect_parent(self):
        self.assertIsNone(kickoff.detect_parent(self.sb.root))
        (self.sb.parent / "AGENTS.md").write_text("# parent")
        self.assertEqual(self.sb.parent / "AGENTS.md", kickoff.detect_parent(self.sb.root))


class PreflightTests(unittest.TestCase):
    def test_installs_missing_beads_skill(self):
        sb = Sandbox(beads_skill=False); self.addCleanup(sb.cleanup)
        report = kickoff.preflight(sb.root, sb.home, dry_run=False)
        self.assertIn("RUN", report.kinds())
        self.assertIn("skills add steveyegge/beads --skill beads --global -y", sb.logged("npx"))
        self.assertTrue((sb.home / ".agents/skills/beads/SKILL.md").is_file())
        self.assertEqual(0, report.status)

    def test_keeps_present_beads_skill(self):
        sb = Sandbox(); self.addCleanup(sb.cleanup)
        report = kickoff.preflight(sb.root, sb.home, dry_run=False)
        self.assertEqual("", sb.logged("npx"))
        self.assertTrue(any(line.startswith("OK ") and "beads skill" in line.lower() for line in report.lines), report.lines)

    def test_dry_run_does_not_install(self):
        sb = Sandbox(beads_skill=False); self.addCleanup(sb.cleanup)
        report = kickoff.preflight(sb.root, sb.home, dry_run=True)
        self.assertTrue(any(line.startswith("RUN npx skills add") for line in report.lines), report.lines)
        self.assertEqual("", sb.logged("npx"))
        self.assertFalse((sb.home / ".agents/skills/beads/SKILL.md").exists())

    def test_fails_without_git_identity(self):
        sb = Sandbox(git_identity=False); self.addCleanup(sb.cleanup)
        report = kickoff.preflight(sb.root, sb.home, dry_run=False)
        self.assertEqual(1, report.status)
        self.assertTrue(any(line.startswith("FAIL") and "user.name" in line for line in report.lines), report.lines)

    def test_skips_when_bd_missing(self):
        sb = Sandbox(with_bd=False); self.addCleanup(sb.cleanup)
        report = kickoff.preflight(sb.root, sb.home, dry_run=False)
        self.assertEqual(0, report.status)
        self.assertTrue(any(line.startswith("SKIP") and "bd" in line for line in report.lines), report.lines)

    def test_skips_skill_install_when_npx_missing(self):
        sb = Sandbox(beads_skill=False, with_npx=False); self.addCleanup(sb.cleanup)
        report = kickoff.preflight(sb.root, sb.home, dry_run=False)
        self.assertEqual(0, report.status)
        self.assertTrue(any(line.startswith("SKIP") and "npx" in line for line in report.lines), report.lines)


class InitTests(unittest.TestCase):
    def setUp(self):
        self.sb = Sandbox()
        self.addCleanup(self.sb.cleanup)

    def test_fresh_dir_gets_git_beads_cass(self):
        report = kickoff.init(self.sb.root, "demo-app", dry_run=False)
        self.assertEqual(0, report.status, report.lines)
        self.assertTrue((self.sb.root / ".git").is_dir())
        self.assertEqual("refs/heads/main\n", self.sb.git("symbolic-ref", "HEAD"))
        self.assertTrue((self.sb.root / ".beads/config.yaml").is_file())
        self.assertTrue((self.sb.root / ".cass/playbook.yaml").is_file())
        log = self.sb.logged("bd")
        for flag in ("--skip-agents", "--prefix demo-app", "--non-interactive"):
            self.assertIn(flag, log)
        self.assertIn("init --repo --no-interactive", self.sb.logged("cm"))

    def test_init_is_idempotent(self):
        kickoff.init(self.sb.root, "demo-app", dry_run=False)
        before = self.sb.logged("bd")
        report = kickoff.init(self.sb.root, "demo-app", dry_run=False)
        self.assertEqual({"KEEP"}, report.kinds(), report.lines)
        self.assertEqual(before, self.sb.logged("bd"))

    def test_dry_run_creates_nothing(self):
        report = kickoff.init(self.sb.root, "demo-app", dry_run=True)
        self.assertEqual([], list(self.sb.root.iterdir()))
        self.assertTrue(any(line.startswith("RUN git init") for line in report.lines), report.lines)
        self.assertTrue(any(line.startswith("RUN bd init --skip-agents") for line in report.lines), report.lines)

    def test_asks_when_git_hook_exists(self):
        self.sb.git("init", "-q")
        hook = self.sb.root / ".git/hooks/pre-commit"
        hook.write_text("#!/bin/sh\nexit 0\n")
        report = kickoff.init(self.sb.root, "demo-app", dry_run=False)
        self.assertEqual(2, report.status, report.lines)
        self.assertFalse((self.sb.root / ".beads").exists())

    def test_asks_when_hooks_path_foreign(self):
        self.sb.git("init", "-q")
        self.sb.git("config", "core.hooksPath", ".husky")
        report = kickoff.init(self.sb.root, "demo-app", dry_run=False)
        self.assertEqual(2, report.status, report.lines)
        self.assertFalse((self.sb.root / ".beads").exists())

    def test_rejects_invalid_name(self):
        report = kickoff.init(self.sb.root, "Demo App", dry_run=False)
        self.assertEqual(1, report.status)
        self.assertEqual([], list(self.sb.root.iterdir()))

    def test_nested_in_parent_repo_runs_git_init(self):
        self.sb.git("init", "-q", cwd=self.sb.parent)
        kickoff.init(self.sb.root, "demo-app", dry_run=False)
        self.assertTrue((self.sb.root / ".git").is_dir())


if __name__ == "__main__":
    unittest.main()
