#!/usr/bin/env python3
"""Tests for the fail-closed workflow and composite-action pin inventory."""

from __future__ import annotations

from pathlib import Path
import importlib.util
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
CHECKER = ROOT / "tools/workflow-security/check-action-pins.py"
SPEC = importlib.util.spec_from_file_location("action_pin_audit", CHECKER)
assert SPEC and SPEC.loader
PIN_AUDIT = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = PIN_AUDIT
SPEC.loader.exec_module(PIN_AUDIT)


class ActionPinAuditTests(unittest.TestCase):
    def fixture(self, workflow: str, composite: str | None = None):
        temporary = tempfile.TemporaryDirectory()
        root = Path(temporary.name)
        workflows = root / ".github/workflows"
        workflows.mkdir(parents=True)
        (workflows / "test.yml").write_text(workflow, encoding="utf-8")
        if composite is not None:
            action = root / ".github/actions/example"
            action.mkdir(parents=True)
            (action / "action.yaml").write_text(composite, encoding="utf-8")
        return temporary, root

    def test_repository_inventory_is_complete_and_pinned(self):
        uses = PIN_AUDIT.inventory(ROOT)
        self.assertGreater(len(uses), 0)
        self.assertTrue(any(item.kind == "remote" for item in uses))
        self.assertEqual(
            sorted({item.path for item in uses}),
            sorted(
                path.relative_to(ROOT).as_posix()
                for path in PIN_AUDIT.source_files(ROOT)
                if "uses:" in path.read_text(encoding="utf-8")
            ),
        )

    def test_full_sha_local_action_and_digest_container_are_allowed(self):
        workflow = """jobs:\n  audit:\n    steps:\n      - uses: actions/checkout@1111111111111111111111111111111111111111\n      - uses: ./.github/actions/example\n      - uses: docker://alpine@sha256:2222222222222222222222222222222222222222222222222222222222222222\n+"""
        composite = """runs:\n  using: composite\n  steps:\n    - shell: bash\n      run: true\n+"""
        temporary, root = self.fixture(workflow, composite)
        self.addCleanup(temporary.cleanup)
        self.assertEqual(
            [item.kind for item in PIN_AUDIT.inventory(root)],
            ["remote", "local", "container"],
        )

    def test_tags_branches_short_shas_and_expressions_fail_closed(self):
        invalid = (
            "actions/checkout@v4",
            "actions/checkout@1234567",
            "actions/checkout@${{ inputs.ref }}",
            "docker://alpine:latest",
        )
        for reference in invalid:
            with self.subTest(reference=reference):
                temporary, root = self.fixture(f"steps:\n  - uses: {reference}\n")
                self.addCleanup(temporary.cleanup)
                with self.assertRaises(PIN_AUDIT.PinError):
                    PIN_AUDIT.inventory(root)

    def test_missing_or_escaping_local_actions_fail_closed(self):
        for reference in ("./.github/actions/missing", "./../outside"):
            with self.subTest(reference=reference):
                temporary, root = self.fixture(f"steps:\n  - uses: {reference}\n")
                self.addCleanup(temporary.cleanup)
                with self.assertRaises(PIN_AUDIT.PinError):
                    PIN_AUDIT.inventory(root)

    def test_referenced_composite_outside_standard_root_is_scanned_transitively(self):
        temporary, root = self.fixture("steps:\n  - uses: ./vendor/local-action\n")
        self.addCleanup(temporary.cleanup)
        action = root / "vendor/local-action"
        action.mkdir(parents=True)
        (action / "action.yml").write_text(
            "runs:\n  using: composite\n  steps:\n    - uses: actions/checkout@v4\n",
            encoding="utf-8",
        )
        with self.assertRaises(PIN_AUDIT.PinError):
            PIN_AUDIT.inventory(root)

    def test_transitive_local_action_cycles_are_duplicate_safe(self):
        temporary, root = self.fixture("steps:\n  - uses: ./vendor/one\n")
        self.addCleanup(temporary.cleanup)
        for name, target in (("one", "two"), ("two", "one")):
            action = root / "vendor" / name
            action.mkdir(parents=True)
            (action / "action.yaml").write_text(
                "runs:\n  using: composite\n  steps:\n"
                f"    - uses: ./vendor/{target}\n",
                encoding="utf-8",
            )
        uses = PIN_AUDIT.inventory(root)
        self.assertEqual([item.kind for item in uses], ["local", "local", "local"])
        self.assertEqual(len({item.path for item in uses}), 3)

    @unittest.skipUnless(hasattr(Path, "symlink_to"), "symlinks unavailable")
    def test_symlinked_local_action_manifest_fails_closed(self):
        temporary, root = self.fixture("steps:\n  - uses: ./vendor/local-action\n")
        self.addCleanup(temporary.cleanup)
        action = root / "vendor/local-action"
        action.mkdir(parents=True)
        real = root / "real-action.yml"
        real.write_text("runs:\n  using: composite\n  steps: []\n", encoding="utf-8")
        try:
            (action / "action.yml").symlink_to(real)
        except OSError:
            self.skipTest("symlinks unavailable")
        with self.assertRaises(PIN_AUDIT.PinError):
            PIN_AUDIT.inventory(root)

    def test_inline_or_malformed_uses_fails_closed(self):
        for workflow in (
            "steps:\n  - uses: actions/checkout@1111111111111111111111111111111111111111\n  - {uses: owner/action@main}\n",
            "steps:\n  - uses: actions/checkout@1111111111111111111111111111111111111111\n  - \"uses\": owner/action@main\n",
            "steps:\n  - uses: actions/checkout@1111111111111111111111111111111111111111\n  - ? uses\n    : actions/checkout@v4\n",
            "steps:\n  - uses: actions/checkout@1111111111111111111111111111111111111111\n  - ? !!str \"uses\"\n    : actions/checkout@v4\n",
            "steps:\n  - uses:\n",
            "steps:\n  - uses: 'actions/checkout@1111111111111111111111111111111111111111\n",
        ):
            with self.subTest(workflow=workflow):
                temporary, root = self.fixture(workflow)
                self.addCleanup(temporary.cleanup)
                with self.assertRaises(PIN_AUDIT.PinError):
                    PIN_AUDIT.inventory(root)

    def test_yaml_key_indirection_fails_closed(self):
        pinned = "actions/checkout@" + "1" * 40
        for workflow in (
            f'steps:\n  - uses: {pinned}\n  - "us\\x65s": actions/checkout@v4\n',
            f'name: &action_key uses\nsteps:\n  - uses: {pinned}\n  - *action_key: actions/checkout@v4\n',
            f'name: &action_key uses\nsteps:\n  - uses: {pinned}\n  - ? *action_key\n    : actions/checkout@v4\n',
            f'steps:\n  - uses: {pinned}\n  - ? |-\n      uses\n    : actions/checkout@v4\n',
            f'steps:\n  - uses: {pinned}\n  - ?\n      uses\n    : actions/checkout@v4\n',
            f'steps:\n  - uses: {pinned}\n  - {{ ?\n      uses\n    : actions/checkout@v4 }}\n',
            f'steps:\n  - uses: {pinned}\n  - {{"us\\x65s": actions/checkout@v4}}\n',
        ):
            with self.subTest(workflow=workflow):
                temporary, root = self.fixture(workflow)
                self.addCleanup(temporary.cleanup)
                with self.assertRaises(PIN_AUDIT.PinError):
                    PIN_AUDIT.inventory(root)

    def test_cli_returns_nonzero_without_printing_an_unsafe_reference_inventory(self):
        temporary, root = self.fixture("steps:\n  - uses: owner/action@main\n")
        self.addCleanup(temporary.cleanup)
        result = subprocess.run(
            [sys.executable, str(CHECKER), "--root", str(root)],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("action pin audit failed", result.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
