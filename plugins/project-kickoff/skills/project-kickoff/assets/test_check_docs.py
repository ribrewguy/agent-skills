"""Regression fixtures for check_docs.py: filename dates, link portability, indexes and design structure."""

from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from check_docs import ROOT, check, check_staged, date_in_name, link_error


class DateFilenameTests(unittest.TestCase):
    def test_date_forms_are_rejected(self):
        examples = [
            "review-2026-10-21.md", "review_2026_10_21.md", "2026.10.21.md",
            "review-20261021.md", "review-202610.md", "review-2026-10.md",
            "10-21-2026.md", "21-10-2026.md", "1-9-2026.md",
            "report_21_10_2026.md", "oct-2026.md", "October-2026.md",
            "oct-21-2026.md", "21-October-2026.md", "2026-October-21.md",
            "2026Q3.md", "2026-Q3.md", "q3-2026.md", "Q32026.md",
        ]
        for name in examples:
            with self.subTest(name=name):
                self.assertTrue(date_in_name(name), name)

    def test_non_date_names_remain_valid(self):
        for name in ["README.md", "architecture.md", "policy-v2.md",
                     "migration-001.sql", "oauth2.md", "sha256.md",
                     "jvm-21.md", "q3.md", "may-policy.md", "schema-1.0.md",
                     "report-2026Q5.md", "review-2026-13-40.md"]:
            with self.subTest(name=name):
                self.assertFalse(date_in_name(name), name)


class PortabilityTests(unittest.TestCase):
    def test_links_do_not_depend_on_machine_paths(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            document = root / "README.md"
            document.write_text("# Example\n")
            for target in [str(document), f"<{document}>", "file:///tmp/README.md",
                           r"C:\Users\user\README.md", "C:/docs/README.md",
                           r"\\server\share\README.md", "%2Ftmp%2FREADME.md"]:
                with self.subTest(target=target):
                    self.assertIn("absolute local link", link_error(document, target, root))
            self.assertIn("leaves the repository", link_error(document, "../AGENTS.md", root))
            for target in ["README.md", "README.md#example", "#example",
                           "https://example.com/docs", "mailto:team@example.com"]:
                with self.subTest(target=target):
                    self.assertIsNone(link_error(document, target, root))
            self.assertIn("missing local link", link_error(document, "absent.md", root))

    @unittest.skipUnless((ROOT / "docs").is_dir(), "no project docs beside this checker")
    def test_current_docs_in_standalone_checkout_and_injected_failures(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "community"
            root.mkdir()
            subprocess.run(["git", "init", "--quiet", str(root)], check=True)
            # Exercise the portable checkout, including module docs and published contracts.
            # Git's file list excludes local credentials, build output and dependencies.
            names = subprocess.check_output(
                ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
                cwd=ROOT,
            ).decode().split("\0")
            for name in names:
                source = ROOT / name
                if not name or not source.is_file():
                    continue
                destination = root / name
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)
            self.assertEqual([], check(root))
            # A path that exists on this machine must still be rejected.
            with (root / "README.md").open("a") as handle:
                handle.write(f"\n[nonportable]({root / 'AGENTS.md'})\n")
            self.assertTrue(any("absolute local link" in e for e in check(root)))
            (root / "10-21-2026.md").write_text("fixture")
            self.assertTrue(any("date-bearing filename" in e for e in check(root)))
            (root / "CLAUDE.md").write_text("different")
            self.assertIn("AGENTS.md and CLAUDE.md differ", check(root))


class StructureTests(unittest.TestCase):
    DESIGN = ("# Example\n\nBusiness authority: PRD.\n\n"
              "Status: draft.\n\n## Behaviour\n\nWhat it does.\n\n"
              "## Open decisions\n\nSomething.\n\nTracking: `demo-abc.1`.\n")

    def fixture(self, temp: str) -> Path:
        root = Path(temp) / "community"
        for directory in ["docs/design/features", "docs/policies/development", "docs/research"]:
            (root / directory).mkdir(parents=True)
            (root / directory / "README.md").write_text("# Index\n\n- [Example](example.md)\n")
            (root / directory / "example.md").write_text(self.DESIGN)
        for name in ["AGENTS.md", "CLAUDE.md", "README.md"]:
            (root / name).write_text("# Instructions\n")
        subprocess.run(["git", "init", "--quiet", str(root)], check=True)
        return root

    def test_valid_fixture_passes(self):
        with tempfile.TemporaryDirectory() as temp:
            self.assertEqual([], check(self.fixture(temp)))

    def test_unindexed_documents_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = self.fixture(temp)
            for directory in ["docs/policies/development", "docs/research"]:
                (root / directory / "orphan.md").write_text("# Orphan\n")
                self.assertIn(f"{directory}/README.md: does not index orphan.md", check(root))
            (root / "docs/research/README.md").unlink()
            self.assertIn("docs/research: missing README.md index", check(root))

    def test_design_structure_is_enforced(self):
        with tempfile.TemporaryDirectory() as temp:
            root = self.fixture(temp)
            design = root / "docs/design/features/example.md"
            prefix = "docs/design/features/example.md"
            cases = {
                "Business authority: PRD.": (
                    "References: PRD.", f"{prefix}: missing 'Business authority:' line"),
                "Tracking: `demo-abc.1`.": (
                    "Tracked somewhere.", f"{prefix}: open decisions lack a 'Tracking:' issue reference"),
                "\nTracking: `demo-abc.1`.\n": (
                    "\nTracking: `demo-abc.1`.\n\n## Appendix\n\nLate.\n",
                    f"{prefix}: must end with '## Open decisions' section"),
            }
            for old, (new, error) in cases.items():
                with self.subTest(error=error):
                    design.write_text(self.DESIGN.replace(old, new))
                    self.assertIn(error, check(root))

    def test_staged_mode_checks_the_index_not_the_working_tree(self):
        with tempfile.TemporaryDirectory() as temp:
            root = self.fixture(temp)
            git = lambda *args: subprocess.run(["git", *args], cwd=root, check=True)
            git("add", "-A")
            self.assertEqual([], check_staged(root))
            (root / "CLAUDE.md").write_text("unstaged drift\n")
            self.assertEqual([], check_staged(root))
            self.assertIn("AGENTS.md and CLAUDE.md differ", check(root))
            git("add", "CLAUDE.md")
            self.assertIn("AGENTS.md and CLAUDE.md differ", check_staged(root))
            # An unstaged new document is neither indexed nor checked yet.
            (root / "docs/research/orphan.md").write_text("# Orphan\n")
            self.assertEqual(["AGENTS.md and CLAUDE.md differ"], check_staged(root))
            git("add", "docs/research/orphan.md")
            self.assertIn("docs/research/README.md: does not index orphan.md", check_staged(root))

    def test_heading_anchors_are_validated(self):
        with tempfile.TemporaryDirectory() as temp:
            root = self.fixture(temp)
            document = root / "README.md"
            target = root / "docs/research/example.md"
            self.assertIsNone(link_error(document, "docs/research/example.md#behaviour", root))
            self.assertIsNone(link_error(document, "docs/research/example.md#open-decisions", root))
            self.assertIn("missing heading anchor",
                          link_error(document, "docs/research/example.md#absent", root))
            target.write_text("# Escalation, notification and provisioning\n")
            self.assertIsNone(link_error(
                document, "docs/research/example.md#escalation-notification-and-provisioning", root))


if __name__ == "__main__":
    unittest.main()
