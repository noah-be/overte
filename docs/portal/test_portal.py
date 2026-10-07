"""Exercise real Sphinx rendering and failure behavior in isolated source trees."""

from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


HERE = Path(__file__).resolve().parent
HEADER = '''---
last-updated: "2026-10-07"
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
        destination.write_text(text, encoding="utf-8")

    def build(self, index=None):
        self.write("docs/portal/index.md", self.index if index is None else index)
        return subprocess.run(
            [sys.executable, "-m", "sphinx", "-q", "-E", "-b", "html",
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
        self.assertIn("<strong>Last updated:</strong> Not recorded", legacy)
        self.assertTrue((self.root / "build/html/searchindex.js").is_file())
        homepage = (self.root / "build/html/index.html").read_text()
        self.assertIn('href="docs/portal/index.html"', homepage)

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
