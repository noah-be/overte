#!/usr/bin/env python3
"""Negative tests for derived displays and duplicated topology contracts."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("repository_policy", ROOT / "tools/repository-policy/check.py")
POLICY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(POLICY)


class PolicyDisplayTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.branches = {
            "main": SimpleNamespace(name="main", parent=None, scope="main"),
            "child": SimpleNamespace(name="child", parent="main", scope="product"),
        }
        self.write(".github/branch-cleanup.json", {"permanent_branches": ["main", "child"]})
        self.write(".github/rulesets/permanent-branches.json", {"conditions": {"ref_name": {"include": ["refs/heads/main", "refs/heads/child"], "exclude": []}}})
        self.write(".github/sync-test-reuse.json", {"parents": ["main"], "edges": {"child": {"parent": "main", "scope": "product"}}})

    def write(self, path, value):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(value))

    def test_consistent_topology_passes(self):
        self.assertEqual(POLICY.topology_errors(self.root, self.branches), [])

    def test_cleanup_missing_or_duplicate_branch_fails(self):
        for names in (["main"], ["main", "child", "child"]):
            with self.subTest(names=names):
                self.write(".github/branch-cleanup.json", {"permanent_branches": names})
                self.assertTrue(POLICY.topology_errors(self.root, self.branches))

    def test_new_canonical_branch_requires_every_consumer_to_update(self):
        self.branches["new"] = SimpleNamespace(name="new", parent="child", scope="new")
        errors = POLICY.topology_errors(self.root, self.branches)
        self.assertEqual(len(errors), 4)

    def test_scope_change_breaks_reuse_contract(self):
        self.branches["child"].scope = "renamed"
        self.assertIn("edges/scopes", POLICY.topology_errors(self.root, self.branches)[0])

    def test_protected_branch_exclusion_is_not_silently_accepted(self):
        self.write(".github/rulesets/permanent-branches.json", {"conditions": {"ref_name": {"include": ["refs/heads/main", "refs/heads/child"], "exclude": ["refs/heads/child"]}}})
        self.assertTrue(POLICY.topology_errors(self.root, self.branches))

    def test_duplicate_protected_refs_and_parents_fail(self):
        self.write(".github/rulesets/permanent-branches.json", {"conditions": {"ref_name": {"include": ["refs/heads/main", "refs/heads/child", "refs/heads/child"], "exclude": []}}})
        self.write(".github/sync-test-reuse.json", {"parents": ["main", "main"], "edges": {"child": {"parent": "main", "scope": "product"}}})
        self.assertEqual(len(POLICY.topology_errors(self.root, self.branches)), 2)

    def test_duplicate_json_keys_fail(self):
        path = self.root / ".github/branch-cleanup.json"
        path.write_text('{"permanent_branches": [], "permanent_branches": ["main", "child"]}')
        with self.assertRaisesRegex(ValueError, "duplicate JSON key"):
            POLICY.topology_errors(self.root, self.branches)

    def test_generated_document_symlinks_are_rejected_without_modification(self):
        external = Path(self.temporary.name).parent / (self.root.name + "-outside")
        external.write_text("preserve")
        self.addCleanup(external.unlink)
        (self.root / "linked.md").symlink_to(external)
        with self.assertRaises(ValueError):
            POLICY.display_path(self.root, "linked.md")
        self.assertEqual(external.read_text(), "preserve")
        target = self.root / "real.md"
        target.write_text("preserve internal")
        (self.root / "inside.md").symlink_to(target)
        with self.assertRaises(ValueError):
            POLICY.display_path(self.root, "inside.md")

    def test_generated_blocks_preserve_surrounding_handwritten_content(self):
        before = "# Title\n\n<!-- generated:branch-table:start -->\nold\n<!-- generated:branch-table:end -->\n\nHandwritten.\n"
        table = POLICY.branch_table(self.branches)
        result = POLICY.replace_block(before, "branch-table", table)
        self.assertTrue(result.startswith("# Title\n\n"))
        self.assertTrue(result.endswith("\n\nHandwritten.\n"))
        self.assertIn("| `child` | `main` | `product` |", result)
        self.assertNotEqual(before, result)
        self.assertEqual(POLICY.replace_block(result, "branch-table", table), result)

    def test_missing_duplicate_or_reversed_markers_fail_closed(self):
        start = "<!-- generated:test-suites:start -->"
        end = "<!-- generated:test-suites:end -->"
        for source in ("missing", start, start + end + start, end + start):
            with self.subTest(source=source):
                with self.assertRaises(ValueError):
                    POLICY.replace_block(source, "test-suites", "generated")

    def test_platform_additions_do_not_change_shared_document(self):
        common = SimpleNamespace(name="shared", layer="quick")
        product = SimpleNamespace(name="android-host", layer="quick")
        parent = SimpleNamespace(SUITES=(common,), PLATFORM_SUITES=())
        child = SimpleNamespace(SUITES=(common, product), PLATFORM_SUITES=(product,))
        self.assertEqual(POLICY.suite_table(POLICY.shared_suites(parent)), POLICY.suite_table(POLICY.shared_suites(child)))

    def test_suite_names_layers_and_individual_commands_come_from_registry(self):
        suites = [SimpleNamespace(name="one", layer="quick"), SimpleNamespace(name="native", layer="native")]
        table = POLICY.suite_table(suites)
        self.assertIn("| `one` | `quick` |", table)
        self.assertIn("--suite native", table)
        suites.append(SimpleNamespace(name="added", layer="quick"))
        self.assertNotEqual(POLICY.suite_table(suites), table)


if __name__ == "__main__":
    unittest.main(verbosity=2)
