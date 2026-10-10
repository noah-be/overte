"""Exercise real Sphinx rendering and failure behavior in isolated source trees."""

from pathlib import Path
import os
import shutil
import subprocess
import sys
import tempfile
import unittest


HERE = Path(__file__).resolve().parent
HEADER = '''---
last-reviewed: "2026-10-07"
scope: "Fixture scope"
---

'''


class PortalBuildTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="overte-docs-test-")
        self.addCleanup(self.temporary.cleanup)
        self.parent = Path(self.temporary.name)
        self.root = self.parent / "repository"
        self.portal = self.root / "docs/portal"
        self.portal.mkdir(parents=True)
        shutil.copy2(HERE / "conf.py", self.portal / "conf.py")
        for directory in ("_ext", "_static", "_templates"):
            shutil.copytree(HERE / directory, self.portal / directory,
                            ignore=shutil.ignore_patterns("__pycache__"))
        self.write("docs/portal/included.md", HEADER + "# Included page\n\n## Valid anchor\n")
        self.write("REFERENCE.md", "# Excluded reference\n\n## Details\n")
        self.write("examples/example.txt", "Public fixture\n")
        self.write("tests/PROJECT_TESTING.md", "# Legacy guide\n")
        self.index = HEADER + '''# Portal fixture

[Included section](included.md#valid-anchor)
[Excluded reference](../../REFERENCE.md#details)
[Repository directory](../../examples/)

```{toctree}
included
/tests/PROJECT_TESTING
```
'''

    def write(self, path, text):
        destination = self.root / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not destination.exists() or destination.read_text(encoding="utf-8") != text:
            destination.write_text(text, encoding="utf-8")

    def git(self, *arguments, commit_date=None, cwd=None):
        environment = os.environ.copy()
        if commit_date:
            environment.update(GIT_AUTHOR_DATE=commit_date, GIT_COMMITTER_DATE=commit_date)
        return subprocess.run(
            ["git", "-c", "user.name=Portal Test", "-c",
             "user.email=portal-test@example.invalid", *arguments],
            cwd=cwd or self.root, env=environment, capture_output=True,
            text=True, check=True, timeout=10,
        )

    def commit(self, commit_date):
        self.git("add", "--", "docs", "tests", "REFERENCE.md", "examples")
        self.git("commit", "-q", "-m", "Update fixture sources", commit_date=commit_date)

    def initialize_history(self):
        self.write("docs/portal/index.md", self.index)
        self.git("init", "-q", "--initial-branch=main")
        self.commit("2026-09-01T12:00:00+02:00")

    def page(self, name="docs/portal/index"):
        return (self.root / f"build/html/{name}.html").read_text()

    def build(self, index=None, fresh=True):
        self.write("docs/portal/index.md", self.index if index is None else index)
        return subprocess.run(
            [sys.executable, "-m", "sphinx", "-q", *(["-E"] if fresh else []), "-b", "html",
             "-c", str(self.portal), "-W", "--keep-going", "-n",
             str(self.root), str(self.root / "build/html")],
            capture_output=True, text=True, timeout=60, check=False,
        )

    def test_navigation_metadata_and_repository_links_are_rendered(self):
        result = self.build()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        html = (self.root / "build/html/docs/portal/index.html").read_text()
        self.assertIn('class="portal-page-status"', html)
        self.assertIn("Fixture scope", html)
        self.assertIn("<strong>Last reviewed:</strong> 2026-10-07", html)
        self.assertIn('href="included.html#valid-anchor"', html)
        self.assertIn('href="https://github.com/noah-be/overte/blob/main/REFERENCE.md#details"', html)
        self.assertIn('href="https://github.com/noah-be/overte/tree/main/examples"', html)
        legacy = (self.root / "build/html/tests/PROJECT_TESTING.html").read_text()
        self.assertIn("<strong>Last reviewed:</strong> Not recorded", legacy)
        self.assertIn("<strong>Last updated:</strong> Not recorded (Git history unavailable)", legacy)
        self.assertTrue((self.root / "build/html/searchindex.js").is_file())
        homepage = (self.root / "build/html/index.html").read_text()
        self.assertIn('href="docs/portal/index.html"', homepage)

    def test_commit_dates_are_per_source_and_manual_updated_date_is_ignored(self):
        self.index = self.index.replace("---\n", '---\nlast-updated: "2099-01-01"\n', 1)
        self.initialize_history()
        self.write("REFERENCE.md", "# Changed excluded reference\n")
        self.commit("2026-09-05T12:00:00+02:00")
        self.write("tests/PROJECT_TESTING.md", "# Updated legacy guide\n")
        self.commit("2026-09-06T12:00:00+02:00")
        result = self.build()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("<strong>Last updated:</strong> 2026-09-01 (Git history)", self.page())
        self.assertIn("<strong>Last reviewed:</strong> 2026-10-07", self.page())
        self.assertIn("<strong>Last updated:</strong> 2026-09-06 (Git history)",
                      self.page("tests/PROJECT_TESTING"))
        self.assertIn("<strong>Last reviewed:</strong> Not recorded",
                      self.page("tests/PROJECT_TESTING"))

    def test_local_changes_are_marked_and_cached_build_refreshes_after_commit(self):
        self.initialize_history()
        result = self.build()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.index += "\nUpdated portal instructions.\n"
        result = self.build(fresh=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("2026-09-01 (Git history; local changes)", self.page())
        self.commit("2026-09-07T12:00:00+02:00")
        result = self.build(fresh=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("2026-09-07 (Git history)", self.page())
        self.assertNotIn("Git history; local changes", self.page())

    def test_uncommitted_page_does_not_claim_a_date(self):
        self.initialize_history()
        self.write("docs/portal/new.md", HEADER + "# New page\n")
        self.index = self.index.replace("\nincluded\n", "\nincluded\nnew\n")
        result = self.build()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("<strong>Last updated:</strong> Not committed", self.page("docs/portal/new"))

    def test_shallow_checkout_does_not_claim_a_date(self):
        self.initialize_history()
        self.write("REFERENCE.md", "# Later unrelated change\n")
        self.commit("2026-09-08T12:00:00+02:00")
        clone = self.parent / "shallow"
        self.git("clone", "-q", "--depth=1", self.root.as_uri(), str(clone))
        self.root = clone
        self.portal = clone / "docs/portal"
        result = self.build()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("<strong>Last updated:</strong> Not recorded (incomplete Git history)",
                      self.page())

    def test_renamed_page_uses_latest_commit_that_changed_its_source(self):
        self.initialize_history()
        self.git("mv", "docs/portal/included.md", "docs/portal/renamed.md")
        self.index = self.index.replace("included.md", "renamed.md").replace("\nincluded\n", "\nrenamed\n")
        self.write("docs/portal/index.md", self.index)
        self.commit("2026-09-09T12:00:00+02:00")
        self.write("REFERENCE.md", "# Unrelated latest commit\n")
        self.commit("2026-09-10T12:00:00+02:00")
        result = self.build()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("<strong>Last updated:</strong> 2026-09-09 (Git history)",
                      self.page("docs/portal/renamed"))

    def test_missing_repository_document_fails(self):
        result = self.build(self.index + "\n[Missing](../../missing.md)\n")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("myst.xref_missing", result.stderr)

    def test_broken_included_anchor_fails(self):
        result = self.build(self.index.replace("#valid-anchor", "#absent"))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("local id not found", result.stderr)

    def test_reference_outside_repository_is_not_redirected(self):
        (self.parent / "outside.md").write_text("# Outside\n")
        result = self.build(self.index + "\n[Outside](../../../outside.md)\n")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("myst.xref_missing", result.stderr)

    def test_missing_review_date_fails(self):
        result = self.build(self.index.replace('last-reviewed: "2026-10-07"\n', ""))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("last-reviewed must be YYYY-MM-DD", result.stderr)

    def test_invalid_review_date_fails(self):
        result = self.build(self.index.replace('last-reviewed: "2026-10-07"',
                                               'last-reviewed: "2026-02-30"'))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("last-reviewed must be YYYY-MM-DD", result.stderr)

    def test_future_review_date_fails(self):
        result = self.build(self.index.replace('last-reviewed: "2026-10-07"',
                                               'last-reviewed: "9999-01-01"'))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("non-future ISO date", result.stderr)

    def test_missing_scope_fails(self):
        result = self.build(self.index.replace('scope: "Fixture scope"\n', ""))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("document scope is required", result.stderr)


if __name__ == "__main__":
    unittest.main()
