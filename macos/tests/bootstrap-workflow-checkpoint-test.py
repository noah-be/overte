#!/usr/bin/env python3
"""Source contracts for efficient, recoverable macOS bootstrap milestones."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/macos-bootstrap.yml"


class BootstrapWorkflowCheckpointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.workflow = WORKFLOW.read_text(encoding="utf-8")

    def section(self, start: str, end: str) -> str:
        return self.workflow.split(start, 1)[1].split(end, 1)[0]

    def test_durable_restore_is_a_fallback_after_dependencies(self) -> None:
        restore = "- name: Restore durable build-tree checkpoint fallback"
        self.assertLess(
            self.workflow.index("- name: Require resolved dependencies"),
            self.workflow.index(restore),
        )
        self.assertLess(
            self.workflow.index(restore),
            self.workflow.index("- name: Configure client build graph"),
        )
        restore_section = self.section(restore, "- name: Normalize durable Ninja source timestamps")
        self.assertIn("tier != 'exact-complete'", restore_section)
        self.assertIn("tier != 'compatible-complete'", restore_section)
        self.assertIn("build-tree-artifact.py restore-remote", restore_section)

    def test_every_safe_progress_boundary_is_persisted(self) -> None:
        for contract in (
            "SCCACHE_MULTILEVEL_CHAIN: disk,gha",
            "Save partial build-tree checkpoint after build failure",
            "Save complete build-tree checkpoint",
            "Package durable build-tree checkpoint",
            "Upload durable build-tree checkpoint",
            "Verify durable build-tree checkpoint upload",
            "Prune superseded durable build-tree checkpoints",
            "Require durable build-tree checkpoint",
        ):
            self.assertIn(contract, self.workflow)
        self.assertLess(
            self.workflow.index("- name: Upload application bundle immediately"),
            self.workflow.index("- name: Package durable build-tree checkpoint"),
        )
        self.assertLess(
            self.workflow.index("- name: Package durable build-tree checkpoint"),
            self.workflow.index("- name: Run application startup preflight"),
        )

    def test_only_a_successful_compile_can_mark_a_tree_complete(self) -> None:
        configured = self.section(
            "- name: Record configured build-tree checkpoint metadata",
            "- name: Save configured build-tree checkpoint",
        )
        completed = self.section(
            "- name: Record Ninja build-tree checkpoint metadata",
            "- name: Save complete compiler cache",
        )
        self.assertIn("clear-complete", configured)
        self.assertNotIn("mark-complete", configured)
        self.assertIn("steps.build-client.outcome", completed)
        self.assertIn("mark-complete", completed)

    def test_pruning_requires_a_verified_durable_replacement(self) -> None:
        prune = self.section(
            "- name: Prune superseded macOS bootstrap caches",
            "- name: Require durable build-tree checkpoint",
        )
        self.assertIn("steps.build-tree-checkpoint-verify.outcome == 'success'", prune)
        self.assertIn("bootstrap-cache-prune.py", prune)


if __name__ == "__main__":
    unittest.main()
