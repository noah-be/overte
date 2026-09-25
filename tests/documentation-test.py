#!/usr/bin/env python3
"""Regression checks for workspace link and anchor validation."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("documentation", ROOT / "tests/check-documentation.py")
DOC = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(DOC)


class DocumentationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        subprocess.run(["git", "init", "--quiet", str(self.root)], check=True)

    def write(self, relative, text=""):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def validate(self, text, relative="README.md", generated=None):
        return DOC.validate(self.write(relative, text), self.root, generated)

    def test_missing_local_target_is_reported_with_line_number(self):
        self.assertEqual(self.validate("Heading\n\n[x](missing.md)"), ["line 3: local link target does not exist: missing.md"])

    def test_root_relative_percent_encoded_and_balanced_destinations(self):
        self.write("docs/file (1).md", "# Heading")
        self.write("docs/part(two).md")
        self.assertEqual(self.validate('[one](</docs/file (1).md#heading> "Title")\n[two](docs/part(two).md)\n[three](/docs/file%20%281%29.md#heading)'), [])

    def test_fences_inline_code_indented_code_and_comments_are_not_links(self):
        text = ('# Real\n````markdown\n```\n[missing](no.md)\n````\n'
                '~~~\n[missing](no.md)\n~~~\n`[missing](no.md)`\n'
                '`` [missing](no.md) ` ``\n    [missing](no.md)\n'
                '<!-- [missing](no.md) -->\n[valid](#real)')
        self.assertEqual(self.validate(text), [])

    def test_fenced_heading_does_not_create_anchor(self):
        self.assertTrue(self.validate('```\n# Fake\n```\n[x](#fake)'))

    def test_atx_setext_duplicate_unicode_and_inline_formatting_headings(self):
        text = '# Hello `world`!\n# Hello `world`!\nÜberblick\n========\n## API_value - ready\n'
        text += '[one](#hello-world) [two](#hello-world-1) [three](#überblick) [four](#api_value---ready)'
        self.assertEqual(self.validate(text), [])

    def test_html_anchors_in_markdown_and_html_destinations(self):
        self.write("page.html", '<h2 id="chapter">Chapter</h2><a name="old"></a>')
        self.assertEqual(self.validate('<a id="local"></a>\n[x](#local) [x](page.html#chapter) <a href="page.html#old">x</a>'), [])
        self.assertTrue(self.validate('[x](page.html#absent)'))

    def test_full_collapsed_shortcut_references_and_images(self):
        self.write("image.png")
        self.write("target.md", "# Target")
        text = ('[first][ID]\n[id][]\n[id]\n![image][picture]\n'
                '[id]: target.md#target "title"\n[picture]: image.png\n')
        self.assertEqual(self.validate(text), [])
        self.assertEqual(len(DOC.links(text)), 4)
        self.assertTrue(self.validate('[x][id]\n[id]: missing.md'))

    def test_nested_image_is_checked_even_when_wrapped_in_remote_link(self):
        self.assertTrue(self.validate('[![badge](missing.png)](https://example.org)'))

    def test_unmatched_literal_bracket_does_not_hide_later_links(self):
        self.assertTrue(self.validate('[not a link\n\n[x](missing.md)'))

    def test_parenthesized_title_is_supported(self):
        self.assertTrue(self.validate('[x](missing.md (Readable title))'))

    def test_checker_cli_returns_failure_for_untracked_workspace_error(self):
        self.write("tests/check-documentation.py", (ROOT / "tests/check-documentation.py").read_text())
        self.write("untracked.md", "[missing](missing.md)")
        result = subprocess.run([__import__("sys").executable, str(self.root / "tests/check-documentation.py"), "--all"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn("untracked.md", result.stdout)

    def test_first_reference_definition_wins(self):
        self.write("exists.md")
        self.assertTrue(self.validate('[x][id]\n[id]: missing.md\n[id]: exists.md\n'))

    def test_nested_lists_keep_links_but_nested_code_fences_do_not(self):
        self.assertTrue(self.validate('- Parent\n    - [broken](missing.md)\n'))
        self.assertTrue(self.validate('- Parent\n  [broken](missing.md)\n'))
        self.assertEqual(self.validate('- Parent\n  ```\n  [example](missing.md)\n  ```\n'), [])
        self.assertEqual(self.validate('> ```\n> [example](missing.md)\n> ```\n'), [])

    def test_source_line_fragments_require_existing_ordered_line_range(self):
        self.write("code.py", "pass\n")
        self.assertEqual(self.validate('[x](code.py#L1)'), [])
        self.assertTrue(self.validate('[x](code.py#L999999)'))
        self.assertTrue(self.validate('[x](code.py#L2-L1)'))

    def test_reference_link_heading_uses_rendered_label_only(self):
        self.write("exists.md")
        self.assertEqual(self.validate('# [Hello][id]\n[id]: exists.md\n\n[x](#hello)'), [])
        self.assertTrue(self.validate('# [Hello][id]\n[id]: exists.md\n\n[x](#helloid)'))

    def test_escaped_link_is_literal(self):
        self.assertEqual(self.validate(r'\[x](missing.md)'), [])

    def test_remote_including_other_branch_is_not_reinterpreted_locally(self):
        self.assertEqual(self.validate('[branch](https://github.com/noah-be/overte/blob/apple-ios/ios/README.md#build) [mail](mailto:example@example.org)'), [])

    def test_links_cannot_escape_repository_including_symlinks(self):
        self.assertTrue(self.validate('[escape](../outside.md)'))
        (self.root / "escape.md").symlink_to(Path(__file__).resolve())
        self.assertTrue(self.validate('[escape](escape.md)'))

    def test_setext_is_not_a_merge_conflict_but_real_conflict_is(self):
        self.assertEqual(self.validate("Heading\n=======\n"), [])
        self.assertTrue(self.validate("<<<<<<< HEAD\nours\n=======\ntheirs\n>>>>>>> topic\n"))

    def test_generated_api_context_requires_known_symbol_and_exact_source(self):
        self.assertEqual(self.validate('[x](Entities.html)', "tools/jsdoc/api-mainpage.md", {"Entities.html"}), [])
        self.assertTrue(self.validate('[x](Invented.html)', "tools/jsdoc/api-mainpage.md", {"Entities.html"}))
        self.assertTrue(self.validate('[x](Entities.html)', "other.md", {"Entities.html"}))

    def test_generated_symbol_is_derived_from_generator_input(self):
        self.write("tools/jsdoc/plugins/hifi.js", "const dirList = [\n '../../libraries/example/src',\n];")
        self.write("libraries/example/src/Api.h", "/*@jsdoc\n * @namespace Example\n */")
        self.assertEqual(DOC.jsdoc_outputs(self.root), {"Example.html"})

    def test_workspace_includes_untracked_and_modified_but_excludes_ignored_files(self):
        tracked = self.write("tracked.md", "# Old")
        subprocess.run(["git", "-C", str(self.root), "add", "tracked.md"], check=True)
        tracked.write_text("[missing](missing.md)")
        untracked = self.write("new.md", "# New")
        self.write(".gitignore", "ignored/\n")
        self.write("ignored/README.md", "[bad](bad.md)")
        self.assertEqual(DOC.documents(self.root), [untracked, tracked])
        self.assertTrue(DOC.validate(tracked, self.root))

    def test_deleted_target_breaks_unchanged_incoming_document(self):
        target = self.write("target.md", "# Existing")
        incoming = self.write("unchanged.md", "[target](target.md#existing)")
        subprocess.run(["git", "-C", str(self.root), "add", "."], check=True)
        target.unlink()
        self.assertEqual(DOC.documents(self.root), [incoming])
        self.assertTrue(DOC.validate(incoming, self.root))

    def test_changed_heading_breaks_incoming_anchor(self):
        target = self.write("target.md", "# New heading")
        incoming = self.write("unchanged.md", "[target](target.md#old-heading)")
        self.assertTrue(DOC.validate(incoming, self.root))


if __name__ == "__main__":
    unittest.main(verbosity=2)
