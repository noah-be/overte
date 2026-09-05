#!/usr/bin/env python3
"""Security and contract tests for parent qualification reuse."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock
import hashlib
import importlib.util
import io
import json
import sys
import unittest
import zipfile


HERE = Path(__file__).resolve().parent


def load(name: str):
    spec = importlib.util.spec_from_file_location(name, HERE / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    assert spec.loader
    spec.loader.exec_module(module)
    return module


qualification = load("qualification")
gate = load("gate")
differential = load("differential")

REPOSITORY = "noah-be/overte"
REPOSITORY_ID = 1319052603
BASE = "1" * 40
PARENT = "2" * 40
HEAD = "3" * 40
MERGE = "4" * 40
TREE = "5" * 40
WORKFLOW_BLOB = "6" * 40


class MappingApi:
    def __init__(self, documents=None, binary=b""):
        self.documents = documents or {}
        self.binary = binary

    def json(self, endpoint, **_kwargs):
        value = self.documents.get(endpoint)
        if isinstance(value, Exception):
            raise value
        if value is None:
            raise AssertionError(f"unexpected endpoint: {endpoint}")
        return value

    def bytes(self, _endpoint):
        return self.binary


def config():
    return gate.load_config()


def entry(path, sha=WORKFLOW_BLOB):
    return {"path": path, "mode": "100644", "type": "blob", "sha": sha}


def evidence_fixture(now=None):
    now = now or datetime.now(timezone.utc).replace(microsecond=0)
    entries = sorted(
        [entry(path, hashlib.sha256(path.encode()).hexdigest()[:40]) for path in config()["required_qualified_inputs"]],
        key=lambda item: item["path"],
    )
    workflow_entry = next(item for item in entries if item["path"] == config()["qualification_workflow"])
    document = {
        "schema": 1,
        "repository": REPOSITORY,
        "repository_id": REPOSITORY_ID,
        "parent_branch": "main",
        "parent_commit": PARENT,
        "parent_tree": TREE,
        "qualified_inputs": entries,
        "qualified_inputs_digest": gate.digest_entries(entries),
        "workflow": {
            "path": config()["qualification_workflow"],
            "blob_sha": workflow_entry["sha"],
            "ref": "refs/heads/main",
            "run_id": 99,
            "run_attempt": 1,
            "event": "push",
            "trusted_app_id": 15368,
        },
        "results": {"conclusion": "success", "suites": ["project-quick", "device-control-plane-full"]},
        "qualified_at": now.isoformat().replace("+00:00", "Z"),
        "expires_at": (now + timedelta(hours=72)).isoformat().replace("+00:00", "Z"),
    }
    document["evidence_digest"] = "sha256:" + hashlib.sha256(gate.canonical_json(document)).hexdigest()
    tree = {item["path"]: item for item in entries}
    return document, tree


def request(parent="main", parent_sha=PARENT, base="android-main"):
    return gate.SyncRequest(
        repository=REPOSITORY, repository_id=REPOSITORY_ID, number=610,
        base=base, base_sha=BASE, head=parent, head_sha=parent_sha,
        head_repository_id=REPOSITORY_ID, merge_sha=MERGE,
        classification="direct", parent=parent, parent_sha=parent_sha,
        profile="android-family", changed_paths=("interface/example.cpp",),
    )


class QualificationContracts(unittest.TestCase):
    def test_manifest_digest_is_order_and_content_addressed(self):
        one = [entry("a"), entry("b")]
        self.assertEqual(qualification.entries_digest(one), qualification.entries_digest(list(one)))
        self.assertNotEqual(qualification.entries_digest(one), qualification.entries_digest([entry("a")]))

    def test_required_workflow_lock_toolchain_and_test_patterns_exist(self):
        patterns = config()["qualified_inputs"]
        for path in (
            ".github/workflows/sync-test-reuse.yml",
            "tests/run-project-tests.py",
            "android/phone/build.gradle.kts",
            "android/gradle/wrapper/gradle-wrapper.properties",
            "ios/versions.env",
            "cmake/init.cmake",
        ):
            self.assertTrue(qualification.selected(path, patterns), path)


class EvidenceContracts(unittest.TestCase):
    def verify(self, document=None, parent_tree=None, merge_tree=None, now=None):
        evidence, tree = evidence_fixture(now)
        if document:
            evidence.update(document)
            unsigned = dict(evidence)
            unsigned.pop("evidence_digest", None)
            evidence["evidence_digest"] = "sha256:" + hashlib.sha256(gate.canonical_json(unsigned)).hexdigest()
        parent_tree = tree if parent_tree is None else parent_tree
        merge_tree = tree if merge_tree is None else merge_tree
        with mock.patch.object(gate, "artifact_evidence", return_value=({"id": 99, "run_attempt": 1}, evidence)), \
             mock.patch.object(gate, "recursive_tree", side_effect=[(TREE, parent_tree), ("7" * 40, merge_tree)]), \
             mock.patch.object(gate, "branch_sha", side_effect=[BASE, PARENT]):
            return gate.verify_evidence(object(), config(), request(), now=now)

    def test_exact_valid_evidence_is_accepted(self):
        self.assertEqual(self.verify()["parent_commit"], PARENT)

    def test_wrong_repository_parent_tree_and_target_are_rejected(self):
        for mutation in (
            {"repository": "attacker/fork"},
            {"repository_id": 7},
            {"parent_commit": HEAD},
            {"parent_tree": HEAD},
            {"parent_branch": "android-vr"},
        ):
            with self.subTest(mutation=mutation), self.assertRaises(gate.EvidenceError):
                self.verify(mutation)

    def test_changed_workflow_lock_toolchain_or_test_input_is_rejected(self):
        evidence, tree = evidence_fixture()
        for path in (
            ".github/workflows/parent-qualification.yml",
            "tests/run-project-tests.py",
            ".github/sync-test-reuse.json",
        ):
            changed = dict(tree)
            changed[path] = dict(changed[path], sha="f" * 40)
            with self.subTest(path=path), self.assertRaises(gate.EvidenceError):
                self.verify(merge_tree=changed)

    def test_stale_and_replayed_evidence_is_rejected(self):
        now = datetime.now(timezone.utc).replace(microsecond=0)
        stale, _ = evidence_fixture(now - timedelta(hours=80))
        _, tree = evidence_fixture(now - timedelta(hours=80))
        with mock.patch.object(gate, "artifact_evidence", return_value=({"id": 99, "run_attempt": 1}, stale)), \
             mock.patch.object(gate, "recursive_tree", side_effect=[(TREE, tree)]):
            with self.assertRaises(gate.EvidenceError):
                gate.verify_evidence(object(), config(), request(), now=now)
        with self.assertRaises(gate.EvidenceError):
            self.verify({"parent_commit": HEAD})

    def test_incomplete_result_and_bad_digest_are_rejected(self):
        with self.assertRaises(gate.EvidenceError):
            self.verify({"results": {"conclusion": "success", "suites": []}})
        evidence, tree = evidence_fixture()
        evidence["evidence_digest"] = "sha256:" + "0" * 64
        with mock.patch.object(gate, "artifact_evidence", return_value=({"id": 99, "run_attempt": 1}, evidence)), \
             mock.patch.object(gate, "recursive_tree", return_value=(TREE, tree)):
            with self.assertRaises(gate.EvidenceError):
                gate.verify_evidence(object(), config(), request())

    def test_untrusted_app_workflow_and_ambiguous_artifact_fail(self):
        run = {
            "id": 99, "run_attempt": 1, "head_sha": PARENT, "conclusion": "success",
            "event": "push", "path": config()["qualification_workflow"], "check_suite_url": "suite",
        }
        endpoint = (
            f"repos/{REPOSITORY}/actions/workflows/"
            f".github%2Fworkflows%2Fparent-qualification.yml/runs?branch=main&event=push&status=success&per_page=100"
        )
        documents = {
            endpoint: {"workflow_runs": [run]},
            "suite": {"app": {"id": 7}, "conclusion": "success"},
        }
        with self.assertRaises(gate.EvidenceError):
            gate.artifact_evidence(MappingApi(documents), config(), request())
        documents["suite"] = {"app": {"id": 15368}, "conclusion": "success"}
        documents[f"repos/{REPOSITORY}/actions/runs/99/artifacts"] = {
            "artifacts": [
                {"id": 1, "name": "parent-qualification-" + PARENT, "expired": False},
                {"id": 2, "name": "parent-qualification-" + PARENT, "expired": False},
            ]
        }
        with self.assertRaises(gate.EvidenceError):
            gate.artifact_evidence(MappingApi(documents), config(), request())


class TopologyContracts(unittest.TestCase):
    def event(self, base, head, base_sha=BASE, head_sha=PARENT, repo_id=REPOSITORY_ID):
        return {
            "repository": {"full_name": REPOSITORY, "id": REPOSITORY_ID},
            "pull_request": {
                "number": 610,
                "base": {"ref": base, "sha": base_sha},
                "head": {"ref": head, "sha": head_sha, "repo": {"id": repo_id}},
            },
        }

    def test_all_eight_edges_classify_with_the_configured_differential(self):
        for base, edge in config()["edges"].items():
            with self.subTest(base=base), \
                 mock.patch.object(gate, "branch_sha", side_effect=[BASE, PARENT, BASE, PARENT]), \
                 mock.patch.object(gate, "commit", side_effect=[{"sha": PARENT}, {"sha": MERGE, "parents": [{"sha": BASE}, {"sha": PARENT}]}]), \
                 mock.patch.object(gate, "compare_files", side_effect=[(HEAD, set()), (HEAD, {"docs/change.md"})]), \
                 mock.patch.object(gate, "paginate_pull_files", return_value=[{"filename": "docs/change.md"}]):
                api = MappingApi({f"repos/{REPOSITORY}/pulls/610": {"state": "open", "mergeable": True, "merge_commit_sha": MERGE}})
                result = gate.classify_event(self.event(base, edge["parent"]), config(), api)
                self.assertEqual(result.parent, edge["parent"])
                self.assertEqual(result.profile, "documentation")

    def test_ordinary_development_dependabot_fork_and_promotion_stay_ordinary(self):
        for head, repo_id in (
            ("task/main/610-change", REPOSITORY_ID),
            ("dependabot/npm_and_yarn/example", REPOSITORY_ID),
            ("feature/android/example", 44),
            ("promote/android/example", REPOSITORY_ID),
        ):
            self.assertIsNone(gate.classify_event(self.event("android-main", head, repo_id=repo_id), config(), MappingApi()))

    def test_wrong_target_or_foreign_sync_fails_closed(self):
        self.assertIsNone(gate.classify_event(self.event("main", "android-main"), config(), MappingApi()))
        with self.assertRaises(gate.GateError):
            gate.classify_event(self.event("android-main", "main", repo_id=44), config(), MappingApi())


class DifferentialContracts(unittest.TestCase):
    def test_documentation_never_selects_an_android_suite(self):
        self.assertEqual(differential.PROFILES["documentation"], ())
        with self.assertRaises(ValueError):
            differential.required_roots(Path("."), "documentation", ["android/source.cpp"])

    def test_each_non_documentation_profile_has_a_minimal_owned_root(self):
        self.assertEqual(set(differential.PROFILES) - {"documentation"}, {
            "android-family", "android-phone", "android-vr", "android-pico",
            "apple-family", "apple-ios", "linux-desktop", "windows-desktop",
        })
        self.assertTrue(all(differential.PROFILES[name] for name in differential.PROFILES if name != "documentation"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
