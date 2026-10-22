"""Tests for check_skill_spec.py."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_skill_spec import check_skill  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
GOOD_DESC = "x" * 700


def make_skill(root, name="demo", description=None, body="Body.\n", refs=None):
    if description is None:
        description = f'"{GOOD_DESC}"'
    skill = Path(root) / name
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {description}\n---\n{body}"
    )
    if refs:
        (skill / "references").mkdir()
        for fname, text in refs.items():
            (skill / "references" / fname).write_text(text)
    return skill


class CheckSkillTest(unittest.TestCase):
    def test_passes_rest_api_design(self):
        skill = REPO / "plugins/rest-api-design/skills/rest-api-design"
        self.assertEqual(check_skill(skill), [])

    def test_passes_minimal_skill_without_references(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(check_skill(make_skill(d)), [])

    def test_fails_inner_double_quote(self):
        with tempfile.TemporaryDirectory() as d:
            desc = '"' + "x" * 350 + ' \\"quoted\\" ' + "y" * 350 + '"'
            failures = check_skill(make_skill(d, description=desc))
            self.assertTrue(any(f.startswith("description-quoted") for f in failures), failures)

    def test_fails_unquoted_description(self):
        with tempfile.TemporaryDirectory() as d:
            failures = check_skill(make_skill(d, description=GOOD_DESC))
            self.assertTrue(any(f.startswith("description-quoted") for f in failures), failures)

    def test_fails_sibling_reference_link(self):
        with tempfile.TemporaryDirectory() as d:
            skill = make_skill(d, refs={"a.md": "See [x](b.md)\n", "b.md": "b\n"})
            failures = check_skill(skill)
            self.assertTrue(any(f.startswith("reference-link") for f in failures), failures)

    def test_fails_bare_url(self):
        with tempfile.TemporaryDirectory() as d:
            failures = check_skill(make_skill(d, body="See https://example.com\n"))
            self.assertTrue(any(f.startswith("bare-url") for f in failures), failures)

    def test_markdown_link_url_is_allowed(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(check_skill(make_skill(d, body="See [x](https://example.com)\n")), [])

    def test_fails_description_too_short(self):
        with tempfile.TemporaryDirectory() as d:
            failures = check_skill(make_skill(d, description='"' + "x" * 100 + '"'))
            self.assertTrue(any(f.startswith("description-length") for f in failures), failures)

    def test_fails_description_too_long(self):
        with tempfile.TemporaryDirectory() as d:
            failures = check_skill(make_skill(d, description='"' + "x" * 951 + '"'))
            self.assertTrue(any(f.startswith("description-length") for f in failures), failures)

    def test_fails_body_too_long(self):
        with tempfile.TemporaryDirectory() as d:
            failures = check_skill(make_skill(d, body="line\n" * 501))
            self.assertTrue(any(f.startswith("body-length") for f in failures), failures)

    def test_fails_name_mismatch(self):
        with tempfile.TemporaryDirectory() as d:
            skill = make_skill(d, name="demo")
            text = (skill / "SKILL.md").read_text().replace("name: demo", "name: other")
            (skill / "SKILL.md").write_text(text)
            failures = check_skill(skill)
            self.assertTrue(any(f.startswith("name-matches-dir") for f in failures), failures)


if __name__ == "__main__":
    unittest.main()
