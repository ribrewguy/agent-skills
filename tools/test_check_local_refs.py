"""Tests for check_local_refs.py."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_local_refs import check, staged_files  # noqa: E402

REPO = Path(__file__).resolve().parents[1]


class ContentTests(unittest.TestCase):
    def test_home_paths_are_rejected(self):
        for text in ["see /Users/someone/Projects/x", "cd /home/someone/src/", r"C:\Users\someone\x",
                     "/private/tmp/claude-501/-Users-someone-Projects/x", "/Volumes/Work/x",
                     "/private/var/folders/ab/T/x", "logsPath /var/folders/ab/cd/T/x"]:
            with self.subTest(text=text):
                self.assertEqual(1, len(check({"doc.md": text.encode()})), text)

    def test_placeholders_and_variables_pass(self):
        for text in ["/Users/user/Projects/x", "/Users/example/x", "/Users/<name>/x", "/Users/$USER/x",
                     "/home/user/src/", "/tmp/jvm-quality/mvnw", "git checkout -b user/PROJ-1"]:
            with self.subTest(text=text):
                self.assertEqual([], check({"doc.md": text.encode()}), text)

    def test_local_settings_files_are_rejected(self):
        for name in [".claude/settings.local.json", ".env", ".env.local", ".env.production", "a/.DS_Store"]:
            with self.subTest(name=name):
                self.assertEqual(1, len(check({name: b""})), name)
        self.assertEqual([], check({".env.example": b"KEY=value\n"}))

    def test_binary_is_skipped(self):
        self.assertEqual([], check({"img.png": b"\x89PNG\0/Users/someone"}))

    def test_instruction_parity(self):
        self.assertIn("AGENTS.md and CLAUDE.md differ", check({"AGENTS.md": b"a", "CLAUDE.md": b"b"}))
        self.assertEqual([], check({"AGENTS.md": b"a", "CLAUDE.md": b"a"}))

    def test_this_repo_is_clean(self):
        self.assertEqual(0, subprocess.run([sys.executable, str(REPO / "tools/check_local_refs.py")],
                                           cwd=REPO, capture_output=True).returncode)


class StagedTests(unittest.TestCase):
    def test_staged_mode_sees_the_index_not_the_working_tree(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            git = lambda *a: subprocess.run(["git", *a], cwd=root, check=True, capture_output=True)
            git("init", "-q")
            (root / "AGENTS.md").write_text("same\n"); (root / "CLAUDE.md").write_text("same\n")
            (root / "notes.md").write_text("clean\n")
            git("add", "-A")
            self.assertEqual([], check(staged_files(root)))
            (root / "notes.md").write_text("/Users/someone/x\n")       # unstaged: not seen
            self.assertEqual([], check(staged_files(root)))
            git("add", "notes.md")
            self.assertEqual(1, len(check(staged_files(root))))
            (root / "notes.md").write_text("clean\n"); git("add", "notes.md")
            (root / "CLAUDE.md").write_text("drift\n"); git("add", "CLAUDE.md")  # AGENTS.md pulled in for parity
            self.assertIn("AGENTS.md and CLAUDE.md differ", check(staged_files(root)))


if __name__ == "__main__":
    unittest.main()
