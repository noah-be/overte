#!/usr/bin/env python3
"""Qualification must attest observed trusted executions, never fabricated labels."""

from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
from unittest import mock
import unittest

import execution

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("observed_qualification_producer", ROOT / "tools/sync-test-reuse/qualification.py")
QUALIFICATION = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(QUALIFICATION)
ENVIRONMENT = {"profile": "qualification-producer-fixture-v1"}


class QualificationProducerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="overte-observed-qualification-")
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.root = self.directory / "candidate"
        self.root.mkdir()
        self.receipt = self.directory / "receipt.json"
        self.git("init", "-q", "--initial-branch=main")
        self.git("config", "user.name", "Observed qualification fixture")
        self.git("config", "user.email", "fixture@example.invalid")
        self.write(".gitignore", "__pycache__/\nbuild/\n")
        self.workflow = ".github/workflows/parent-qualification.yml"
        self.write(self.workflow, "# Actual immutable qualification workflow fixture\n")
        self.write("tests/platform-profile.json", '{"schema":1,"platform":"shared","suites":[]}\n')
        self.registry = {"schema": 1, "control_inputs": ["*.py"], "suites": {}}
        for name in ("observed-one", "observed-two"):
            path = f"tests/{name}.py"
            self.write(path, "raise SystemExit(0)\n")
            self.registry["suites"][name] = {
                "command": ["python", path], "layer": "quick", "scope": "content",
                "environment": "host-qt5-qt6", "closure": {"kind": "repository", "inputs": [], "required": [path]},
            }
        self.commit()
        self.source = self.git("rev-parse", "HEAD")
        self.git("update-ref", "refs/remotes/origin/main", self.source)
        self.config = {
            "schema": 1, "repository": "noah-l-frank/overte", "repository_id": 1319052603,
            "parents": ["main"], "qualified_inputs": ["*"], "required_qualified_inputs": [self.workflow],
            "evidence_max_age_hours": 72, "qualification_workflow": self.workflow, "trusted_actions_app_id": 15368,
        }
        self.config_path = self.directory / "policy.json"
        self.config_path.write_text(json.dumps(self.config))
        self.args = SimpleNamespace(config=self.config_path, candidate=self.root, execution_receipt=self.receipt,
                                    repository=self.config["repository"], repository_id=self.config["repository_id"],
                                    parent_branch="main", commit=self.source, run_id=91, run_attempt=2)

    def git(self, *arguments):
        return subprocess.check_output(["git", "-c", "core.hooksPath=/dev/null", "-c", "commit.gpgsign=false", *arguments],
                                       cwd=self.root, text=True, stderr=subprocess.PIPE).strip()

    def write(self, relative, source):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source)

    def commit(self):
        self.git("add", ".")
        self.git("commit", "-qm", "Record immutable qualification fixture")

    def execute(self, names=None, unsupported=False):
        identity = execution.runtime.RuntimeIdentityError("unsupported") if unsupported else None
        with mock.patch.object(execution.inputs, "load_registry", return_value=self.registry), \
                mock.patch.object(execution.runtime, "capture_host_environment", return_value=ENVIRONMENT, side_effect=identity):
            status, receipt = execution.execute(self.root, names, receipt_path=self.receipt, timeout=10, host_timeout=10)
        self.assertEqual(status, 0)
        return receipt

    def qualify(self):
        with mock.patch.object(QUALIFICATION.inputs, "load_registry", return_value=self.registry):
            return QUALIFICATION.create_evidence(self.args)

    def change_receipt(self, receipt):
        receipt.pop("receipt_digest", None)
        receipt["receipt_digest"] = execution.digest(receipt)
        self.receipt.write_bytes(execution.canonical_json(receipt))

    def test_qualifies_actual_observed_shared_suites_and_preserves_provenance(self):
        receipt = self.execute()
        evidence = self.qualify()
        self.assertEqual(evidence["schema"], 2)
        self.assertTrue(evidence["reusable"])
        self.assertEqual(evidence["results"]["suites"], receipt["results"])
        self.assertEqual(set(evidence["results"]["suites"]), set(self.registry["suites"]))
        self.assertEqual(evidence["environment"], ENVIRONMENT)
        self.assertEqual(evidence["execution_receipt_digest"], receipt["receipt_digest"])
        self.assertEqual(evidence["parent_commit"], self.source)
        self.assertEqual(evidence["parent_tree"], self.git("rev-parse", "HEAD^{tree}"))
        self.assertEqual(evidence["workflow"]["run_id"], 91)
        self.assertEqual(evidence["workflow"]["run_attempt"], 2)
        self.assertEqual(evidence["workflow"]["event"], "push")
        self.assertEqual(evidence["qualified_inputs_digest"], QUALIFICATION.entries_digest(evidence["qualified_inputs"]))
        unsigned = dict(evidence)
        claimed = unsigned.pop("evidence_digest")
        self.assertEqual(claimed, execution.digest(unsigned))

    def test_legacy_call_without_observed_receipt_cannot_fabricate_qualification(self):
        del self.args.execution_receipt
        with self.assertRaisesRegex(QUALIFICATION.QualificationError, "execution receipt"):
            self.qualify()

    def test_subset_success_does_not_qualify_unexecuted_shared_suites(self):
        self.execute(["observed-one"])
        with self.assertRaises(QUALIFICATION.QualificationError):
            self.qualify()

    def test_omitted_failed_wrong_input_or_other_candidate_receipt_is_rejected(self):
        original = self.execute()
        mutations = []
        missing = deepcopy(original)
        del missing["results"]["observed-two"]
        mutations.append(missing)
        failed = deepcopy(original)
        failed["results"]["observed-two"]["status"] = "failed"
        mutations.append(failed)
        forged = deepcopy(original)
        forged["results"]["observed-two"]["fingerprint"] = "sha256:" + "0" * 64
        mutations.append(forged)
        other = deepcopy(original)
        other["candidate_commit"] = "0" * 40
        mutations.append(other)
        for receipt in mutations:
            with self.subTest(receipt=receipt):
                self.change_receipt(receipt)
                with self.assertRaises(QUALIFICATION.QualificationError):
                    self.qualify()

    def test_verified_unknown_environment_remains_explicitly_nonreusable(self):
        receipt = self.execute(unsupported=True)
        evidence = self.qualify()
        self.assertFalse(evidence["reusable"])
        self.assertIsNone(evidence["environment"])
        self.assertEqual(evidence["results"]["suites"], receipt["results"])
        self.assertTrue(all(result["fingerprint"] is None for result in evidence["results"]["suites"].values()))

    def test_provenance_cannot_rebind_moved_ref_wrong_repository_or_run_attempt(self):
        self.execute()
        for field, value in (("repository", "overte-org/overte"), ("repository_id", 1),
                             ("parent_branch", "unknown"), ("run_id", 0), ("run_attempt", True)):
            with self.subTest(field=field):
                previous = getattr(self.args, field)
                setattr(self.args, field, value)
                with self.assertRaises(QUALIFICATION.QualificationError):
                    self.qualify()
                setattr(self.args, field, previous)
        self.git("update-ref", "refs/remotes/origin/main", self.source + "^{tree}")
        with self.assertRaises(QUALIFICATION.QualificationError):
            self.qualify()

    def test_legacy_manifest_preserves_gitlink_object_type_and_mode(self):
        self.git("update-index", "--add", "--cacheinfo", "160000," + self.source + ",vendor")
        self.git("commit", "-qm", "Record immutable gitlink fixture")
        entries = QUALIFICATION.tree_entries(self.git("rev-parse", "HEAD"), ["*"], cwd=self.root)
        entry = next(item for item in entries if item["path"] == "vendor")
        self.assertEqual(entry, {"path": "vendor", "mode": "160000", "type": "commit", "sha": self.source})


if __name__ == "__main__":
    unittest.main()
