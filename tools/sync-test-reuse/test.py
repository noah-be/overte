#!/usr/bin/env python3
"""Security and contract tests for parent qualification reuse."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace
from pathlib import Path
from unittest import mock
import hashlib
import importlib.util
import io
import json
import subprocess
import sys
import tempfile
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

REPOSITORY = "noah-l-frank/overte"
REPOSITORY_ID = 1319052603
BASE = "1" * 40
PARENT = "2" * 40
HEAD = "3" * 40
MERGE = "4" * 40
TREE = "5" * 40
WORKFLOW_BLOB = "6" * 40
CODEQL_BASE_TREE = "7" * 40
RETARGET_WORKFLOW_BLOB = "8" * 40
PINNED_WORKFLOW_BLOB = "9" * 40
METADATA_WORKFLOW_BLOB = "a" * 40
METADATA_SOURCE_BLOB = "b" * 40


class GitHubApiDiagnosticsTests(unittest.TestCase):
    def test_command_failures_report_only_exit_and_http_status(self):
        for status in (401, 403, 404, 429, 500, 502, 503):
            with self.subTest(status=status):
                private = "synthetic-private-field-never-log"
                error = subprocess.CalledProcessError(
                    1, ["gh", "api", "-f", private], output=private,
                    stderr=f"gh: {private} (HTTP {status})\n")
                with mock.patch.object(gate.subprocess, "run", side_effect=error) as run:
                    with self.assertRaises(gate.GateError) as caught:
                        gate.GitHubApi().json("repos/noah-l-frank/overte/git/ref/heads/android-vr")
                self.assertIn(f"command exit=1 http={status}", str(caught.exception))
                self.assertNotIn(private, str(caught.exception))
                self.assertIs(caught.exception.__cause__, error)
                self.assertEqual(run.call_count, 1, "diagnosis must not add automatic retries")

    def test_transport_error_does_not_invent_an_http_status(self):
        error = subprocess.CalledProcessError(1, ["gh"], stderr="synthetic-sensitive-dns-message")
        with mock.patch.object(gate.subprocess, "run", side_effect=error):
            with self.assertRaises(gate.GateError) as caught:
                gate.GitHubApi().json("repos/noah-l-frank/overte")
        self.assertIn("command exit=1 http=unknown", str(caught.exception))
        self.assertNotIn("synthetic-sensitive-dns-message", str(caught.exception))

    def test_invalid_json_is_distinct_without_response_text(self):
        private = "synthetic-private-response"
        with mock.patch.object(gate.subprocess, "run", return_value=SimpleNamespace(stdout=private)):
            with self.assertRaises(gate.GateError) as caught:
                gate.GitHubApi().json("repos/noah-l-frank/overte")
        self.assertIn("invalid-json", str(caught.exception))
        self.assertNotIn(private, str(caught.exception))

    def test_os_failure_has_errno_without_private_path(self):
        with mock.patch.object(gate.subprocess, "run", side_effect=OSError(2, "synthetic-private-path")):
            with self.assertRaises(gate.GateError) as caught:
                gate.GitHubApi().json("repos/noah-l-frank/overte")
        self.assertIn("os-error errno=2", str(caught.exception))
        self.assertNotIn("synthetic-private-path", str(caught.exception))

    def test_binary_failure_preserves_evidence_error_and_safe_diagnosis(self):
        error = subprocess.CalledProcessError(1, ["gh"], stderr=b"synthetic-private-body (HTTP 404)")
        with mock.patch.object(gate.subprocess, "run", side_effect=error):
            with self.assertRaises(gate.EvidenceError) as caught:
                gate.GitHubApi().bytes("repos/noah-l-frank/overte/actions/artifacts/123/zip")
        self.assertIn("command exit=1 http=404", str(caught.exception))
        self.assertNotIn("synthetic-private-body", str(caught.exception))

    def test_success_and_empty_success_preserve_existing_values(self):
        for stdout, expected in (("{\"ok\": true}", {"ok": True}), ("", {})):
            with mock.patch.object(gate.subprocess, "run", return_value=SimpleNamespace(stdout=stdout)):
                self.assertEqual(gate.GitHubApi().json("repos/noah-l-frank/overte"), expected)


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


@contextmanager
def trusted_codeql_policy(targets):
    """Inject explicit trusted policy data; keep the real validator executable."""
    with tempfile.TemporaryDirectory(prefix='overte-sync-codeql-policy-') as directory:
        root = Path(directory)
        (root / '.github').mkdir()
        (root / '.github/repository-checks.json').write_text(json.dumps({
            'schema': 1, 'repository': REPOSITORY, 'repository_id': REPOSITORY_ID,
            'codeql_results_required_branches': targets,
        }))
        validator = gate.validate_required_codeql_workflow
        previous = validator.__defaults__
        validator.__defaults__ = (root,)
        try:
            yield root
        finally:
            validator.__defaults__ = previous


def test_registry():
    return {"schema": 1, "control_inputs": ["tests/run-project-tests.py"], "suites": {
        "fixture-host": {
            "command": ["python", "tests/run-project-tests.py"], "layer": "host",
            "scope": "content", "environment": "fixture-host",
            "closure": {"kind": "repository", "inputs": [], "required": []},
        },
    }}


def bind_suite_proofs(document, tree, registry=None):
    registry = registry or test_registry()
    document["environment"] = {"schema": 1, "runtime": "fixture-host"}
    document["reusable"] = True
    document["results"] = {"conclusion": "success", "suites": {
        name: {"status": "passed", "fingerprint": gate.suite_inputs.suite_fingerprint(
            registry, name, gate.input_tree(tree), document["environment"])}
        for name in registry["suites"]}}


def evidence_fixture(now=None):
    now = now or datetime.now(timezone.utc).replace(microsecond=0)
    entries = sorted(
        [entry(path, hashlib.sha256(path.encode()).hexdigest()[:40]) for path in config()["required_qualified_inputs"]],
        key=lambda item: item["path"],
    )
    workflow_entry = next(item for item in entries if item["path"] == config()["qualification_workflow"])
    document = {
        "schema": 2,
        "repository": REPOSITORY,
        "repository_id": REPOSITORY_ID,
        "parent_branch": "main",
        "parent_commit": PARENT,
        "parent_tree": TREE,
        "execution_receipt_digest": "sha256:" + "a" * 64,
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
        "qualified_at": now.isoformat().replace("+00:00", "Z"),
        "expires_at": (now + timedelta(hours=72)).isoformat().replace("+00:00", "Z"),
    }
    tree = {item["path"]: item for item in entries}
    bind_suite_proofs(document, tree)
    document["evidence_digest"] = "sha256:" + hashlib.sha256(gate.canonical_json(document)).hexdigest()
    return document, tree


def request(parent="main", parent_sha=PARENT, base="android-main", parent_changed_paths=None):
    if parent_changed_paths is None:
        parent_changed_paths = tuple(config()["required_qualified_inputs"])
    return gate.SyncRequest(
        repository=REPOSITORY, repository_id=REPOSITORY_ID, number=610,
        base=base, base_sha=BASE, head=parent, head_sha=parent_sha,
        head_repository_id=REPOSITORY_ID, merge_sha=MERGE,
        classification="direct", parent=parent, parent_sha=parent_sha,
        profile="android-family", changed_paths=("interface/example.cpp",),
        parent_changed_paths=tuple(parent_changed_paths),
    )


class QualificationContracts(unittest.TestCase):
    def setUp(self):
        patch = mock.patch.object(gate, "input_registry", side_effect=test_registry)
        patch.start()
        self.addCleanup(patch.stop)

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

    def test_new_host_suite_inputs_change_git_tree_digest_and_prevent_candidate_reuse(self):
        paths = (
            "server-console/src/modules/open-url.js",
            "server-console/test/open-url.test.js",
            "interface/src/metrics/NativeMetrics.cpp",
            "interface/src/metrics/NativeMetrics.h",
            "interface/src/RefreshRateManager.cpp",
            "provenance/artifact_identity.py",
            "provenance/sbom_validation.py",
            "tools/sbom/verify-sbom-pair.py",
            "tools/sbom/requirements-validation.txt",
            "tests/requirements-host.txt",
            "ios/ci/evidence/verify-shared-evidence.py",
            "scripts/developer/libraries/virtualBaton.js",
            "unpublishedScripts/DomainContent/Home/virtualBaton.js",
            "scripts/+android_phoneInterface/defaultScripts.js",
            "scripts/system/+android_phoneInterface/mobileActionBar.js",
            "scripts/system/+android_phoneInterface/mobileTabletApps.js",
            "scripts/system/+android_phoneInterface/phoneEmote.js",
            "scripts/system/places/places.js",
            "scripts/system/places/portal.js",
            "scripts/system/quickGoto.js",
        )
        settings = config()
        with tempfile.TemporaryDirectory(prefix="sync-qualified-inputs-") as directory:
            root = Path(directory)

            def git(*arguments):
                return subprocess.run(
                    ["git", "-C", str(root), *arguments], check=True,
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                ).stdout.strip()

            git("init", "--quiet")
            git("config", "user.name", "Regression Test")
            git("config", "user.email", "regression@example.invalid")
            for relative in (*settings["required_qualified_inputs"], *paths):
                self.assertTrue((HERE.parents[1] / relative).is_file(), relative)
                target = root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("original fixture content\n", encoding="utf-8")
            git("add", ".")
            git("commit", "--quiet", "-m", "Qualified fixture")
            entries = qualification.tree_entries(git("rev-parse", "HEAD"), settings["qualified_inputs"], cwd=root)
            parent_tree = {item["path"]: item for item in entries}
            self.assertTrue(set(paths).issubset(parent_tree), set(paths) - parent_tree.keys())
            document, _ = evidence_fixture()
            document["qualified_inputs"] = entries
            document["qualified_inputs_digest"] = qualification.entries_digest(entries)
            document["workflow"]["blob_sha"] = parent_tree[settings["qualification_workflow"]]["sha"]
            bind_suite_proofs(document, parent_tree)
            document.pop("evidence_digest")
            document["evidence_digest"] = "sha256:" + hashlib.sha256(gate.canonical_json(document)).hexdigest()

            # An unrelated file is deliberately outside the manifest; source inputs below are not.
            (root / "unrelated.txt").write_text("unqualified content\n", encoding="utf-8")
            git("add", "unrelated.txt")
            git("commit", "--quiet", "-m", "Unrelated fixture change")
            unchanged = qualification.tree_entries(git("rev-parse", "HEAD"), settings["qualified_inputs"], cwd=root)
            self.assertEqual(qualification.entries_digest(unchanged), document["qualified_inputs_digest"])
            for relative in paths:
                with self.subTest(path=relative):
                    before = qualification.entries_digest(unchanged)
                    (root / relative).write_text("changed fixture content\n", encoding="utf-8")
                    git("add", relative)
                    git("commit", "--quiet", "-m", "Changed qualified fixture input")
                    changed = qualification.tree_entries(git("rev-parse", "HEAD"), settings["qualified_inputs"], cwd=root)
                    self.assertNotEqual(before, qualification.entries_digest(changed))
                    merge_tree = {item["path"]: item for item in changed}
                    self.assertEqual(gate.digest_entries(gate.select_entries(merge_tree, settings["qualified_inputs"])),
                                     qualification.entries_digest(changed))
                    with mock.patch.object(gate, "artifact_evidence", return_value=({"id": 99, "run_attempt": 1}, document)), \
                         mock.patch.object(gate, "recursive_tree", side_effect=[(TREE, parent_tree), ("7" * 40, merge_tree)]):
                        with self.assertRaisesRegex(gate.EvidenceError, "complete candidate inputs"):
                            gate.verify_evidence(object(), settings, request(parent_changed_paths=(relative,)))
                    unchanged = changed


class EvidenceContracts(unittest.TestCase):
    def setUp(self):
        patch = mock.patch.object(gate, "input_registry", side_effect=test_registry)
        patch.start()
        self.addCleanup(patch.stop)

    def verify(self, document=None, parent_tree=None, merge_tree=None, now=None, sync_request=None):
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
            return gate.verify_evidence(object(), config(), sync_request or request(), now=now)

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

    def test_historical_target_input_outside_parent_delta_requires_candidate_execution(self):
        _, tree = evidence_fixture()
        path = "tests/run-project-tests.py"
        changed = dict(tree)
        changed[path] = dict(changed[path], sha="f" * 40)
        with self.assertRaisesRegex(gate.EvidenceError, "complete candidate inputs"):
            self.verify(
                merge_tree=changed,
                sync_request=request(parent_changed_paths=("interface/example.cpp",)),
            )

    def test_historical_child_difference_selects_only_affected_complete_suite_inputs(self):
        registry = test_registry()
        definition = registry["suites"].pop("fixture-host")
        for name in ("alpha", "beta"):
            registry["suites"][name] = deepcopy(definition)
            registry["suites"][name]["closure"] = {
                "kind": "patterns", "inputs": [f"libraries/{name}/**"],
                "required": [f"libraries/{name}/Source.cpp"],
            }
        document, tree = evidence_fixture()
        for name in registry["suites"]:
            path = f"libraries/{name}/Source.cpp"
            tree[path] = entry(path)
        bind_suite_proofs(document, tree, registry)
        changed = deepcopy(tree)
        changed["libraries/alpha/Source.cpp"]["sha"] = "f" * 40
        with mock.patch.object(gate, "input_registry", return_value=registry):
            verified = self.verify(document, tree, changed,
                                   sync_request=request(parent_changed_paths=("interface/unrelated.cpp",)))
        self.assertEqual(verified["candidate_plan"]["reused"], ["beta"])
        self.assertEqual(verified["candidate_plan"]["required"], ["alpha"])
        self.assertEqual(verified["candidate_inputs"]["libraries/alpha/Source.cpp"]["sha"], "f" * 40)

    def test_legacy_and_unidentified_runtime_evidence_cannot_authorize_reuse(self):
        for mutation in ({"schema": 1}, {"reusable": False}, {"environment": None},
                         {"results": {"conclusion": "success", "suites": {}}}):
            with self.subTest(mutation=mutation), self.assertRaises(gate.EvidenceError):
                self.verify(mutation)

    def test_parent_delta_deletion_must_be_absent_from_candidate(self):
        _, tree = evidence_fixture()
        path = "tests/obsolete-parent-input.py"
        retained = dict(tree)
        retained[path] = entry(path, "f" * 40)
        with self.assertRaises(gate.EvidenceError):
            self.verify(
                merge_tree=retained,
                sync_request=request(parent_changed_paths=(path,)),
            )

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
                "base": {"ref": base, "sha": base_sha,
                         "repo": {"full_name": REPOSITORY, "id": REPOSITORY_ID}},
                "head": {"ref": head, "sha": head_sha, "repo": {"id": repo_id}},
            },
        }

    def test_all_six_edges_classify_with_the_configured_differential(self):
        self.assertEqual(len(config()["edges"]), 6)
        for base, edge in config()["edges"].items():
            with self.subTest(base=base), \
                 mock.patch.object(gate, "branch_sha", side_effect=[BASE, PARENT, BASE, PARENT]), \
                 mock.patch.object(gate, "commit", side_effect=[{"sha": PARENT}, {"sha": MERGE, "parents": [{"sha": BASE}, {"sha": PARENT}]}]), \
                 mock.patch.object(gate, "compare_merge_base", return_value=HEAD), \
                 mock.patch.object(gate, "compare_files", return_value=(HEAD, {"docs/change.md"})), \
                 mock.patch.object(gate, "paginate_pull_files", return_value=[{"filename": "docs/change.md"}]):
                api = MappingApi({f"repos/{REPOSITORY}/pulls/610": {"state": "open", "mergeable": True, "merge_commit_sha": MERGE}})
                result = gate.classify_event(self.event(base, edge["parent"]), config(), api)
                self.assertEqual(result.parent, edge["parent"])
                self.assertEqual(result.profile, "documentation")

    def test_renamed_account_keeps_exact_identity_before_ordinary_classification(self):
        candidate = self.event('main', 'fix/main/example')
        self.assertEqual(config()['repository'], 'noah-l-frank/overte')
        self.assertEqual(config()['repository_id'], 1319052603)
        self.assertIsNone(gate.classify_event(candidate, config(), MappingApi()))
        for identity in ({'full_name': 'noah-be/overte', 'id': 1319052603},
                         {'full_name': 'noah-l-frank/overte', 'id': 42}):
            with self.subTest(identity=identity), self.assertRaisesRegex(gate.GateError, 'repository'):
                gate.classify_event({**candidate, 'repository': identity}, config(), MappingApi())

    def test_retired_desktop_targets_and_scopes_cannot_receive_sync_reuse(self):
        for platform in ("linux", "windows"):
            for base, head in ((platform + "-main", "main"),
                               (platform + "-main", f"reconcile/{platform}/refresh"),
                               ("android-main", platform + "-main"),
                               ("android-main", f"reconcile/{platform}/refresh")):
                with self.subTest(base=base, head=head):
                    self.assertIsNone(gate.classify_event(self.event(base, head), config(), MappingApi()))

    def test_only_regular_tool_manifests_receive_bounded_sync_checks(self):
        manifest = 'tools/jsdoc/package-lock.json'
        cases = [(manifest, None, '100644', 'tool-dependencies'),
                 (manifest, None, '120000', 'android-family'),
                 (manifest, 'native.cpp', '100644', 'android-family'),
                 ('tools/jsdoc/CMakeLists.txt', None, '100644', 'android-family')]
        for filename, previous, mode, profile in cases:
            change = {'filename': filename}
            if previous:
                change['previous_filename'] = previous
            paths = {filename, previous} - {None}
            tree = {filename: {**entry(filename), 'mode': mode}}
            with self.subTest(change=change, mode=mode), \
                 mock.patch.object(gate, 'branch_sha', side_effect=[BASE, PARENT] * 3), \
                 mock.patch.object(gate, 'commit', side_effect=[{'sha': PARENT}, {'sha': MERGE, 'parents': [{'sha': BASE}, {'sha': PARENT}]}]), \
                 mock.patch.object(gate, 'compare_merge_base', return_value=HEAD), \
                 mock.patch.object(gate, 'compare_files', return_value=(HEAD, paths)), \
                 mock.patch.object(gate, 'paginate_pull_files', return_value=[change]), \
                 mock.patch.object(gate, 'recursive_tree', return_value=(TREE, tree)):
                api = MappingApi({f'repos/{REPOSITORY}/pulls/610': {'state': 'open', 'mergeable': True, 'merge_commit_sha': MERGE}})
                result = gate.classify_event(self.event('android-main', 'main'), config(), api)
                self.assertEqual(result.profile, profile)

    def test_s3_bounded_sync_requires_trusted_activation_and_both_exact_workflow_trees(self):
        package = gate.package_checks
        filename = package.S3 + '/package-lock.json'
        approved = {filename: entry(filename)}
        for name in ('project-tests.yml', 'parent-qualification.yml', 'sync-validation.yml', 'repository-checks.yml'):
            data = (package.TEMPLATES / name).read_bytes()
            approved['.github/workflows/' + name] = {'mode': '100644', 'type': 'blob',
                'sha': hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()}
        for enabled, invalid_side, mode in ((False, None, '100644'), (True, None, '100644'),
                                           (True, 0, '100644'), (True, 1, '100644'),
                                           (True, None, '120000')):
            trees = [deepcopy(approved), deepcopy(approved)]
            for tree in trees: tree[filename]['mode'] = mode
            if invalid_side is not None:
                trees[invalid_side]['.github/workflows/project-tests.yml']['sha'] = '0' * 40
            with self.subTest(enabled=enabled, invalid_side=invalid_side, mode=mode), \
                 mock.patch.object(package, 'activated', return_value=enabled), \
                 mock.patch.object(gate, 'branch_sha', side_effect=[BASE, PARENT] * 3), \
                 mock.patch.object(gate, 'commit', side_effect=[{'sha': PARENT}, {'sha': MERGE, 'parents': [{'sha': BASE}, {'sha': PARENT}]}]), \
                 mock.patch.object(gate, 'compare_merge_base', return_value=HEAD), \
                 mock.patch.object(gate, 'compare_files', return_value=(HEAD, {filename})), \
                 mock.patch.object(gate, 'paginate_pull_files', return_value=[{'filename': filename}]), \
                 mock.patch.object(gate, 'recursive_tree', side_effect=[(TREE, tree) for tree in trees]) as reads:
                api = MappingApi({f'repos/{REPOSITORY}/pulls/610': {'state': 'open', 'mergeable': True, 'merge_commit_sha': MERGE}})
                if invalid_side is not None:
                    with self.assertRaises(gate.GateError):
                        gate.classify_event(self.event('android-main', 'main'), config(), api)
                else:
                    result = gate.classify_event(self.event('android-main', 'main'), config(), api)
                    self.assertEqual(result.profile, 'tool-dependencies' if enabled and mode == '100644' else 'android-family')
                    self.assertEqual(reads.call_count, 2 if enabled else 0)

    def test_executable_docs_and_code_renames_keep_full_qualification(self):
        for change in ({"filename": "docs/helper.py"},
                       {"filename": "docs/helper.md", "previous_filename": "tools/helper.py"}):
            with self.subTest(change=change), \
                 mock.patch.object(gate, "branch_sha", side_effect=[BASE, PARENT, BASE, PARENT]), \
                 mock.patch.object(gate, "commit", side_effect=[{"sha": PARENT}, {"sha": MERGE, "parents": [{"sha": BASE}, {"sha": PARENT}]}]), \
                 mock.patch.object(gate, "compare_merge_base", return_value=HEAD), \
                 mock.patch.object(gate, "compare_files", return_value=(HEAD, {change["filename"], change.get("previous_filename", change["filename"])})), \
                 mock.patch.object(gate, "paginate_pull_files", return_value=[change]):
                api = MappingApi({f"repos/{REPOSITORY}/pulls/610": {"state": "open", "mergeable": True, "merge_commit_sha": MERGE}})
                result = gate.classify_event(self.event("android-main", "main"), config(), api)
                self.assertEqual(result.profile, "android-family")

    def test_merge_base_lookup_ignores_only_the_unneeded_capped_file_list(self):
        endpoint = f"repos/{REPOSITORY}/compare/{PARENT}...{BASE}"
        document = {
            "base_commit": {"sha": PARENT},
            "merge_base_commit": {"sha": HEAD},
            "files": [{"filename": f"historical/{index}"} for index in range(300)],
        }
        self.assertEqual(gate.compare_merge_base(MappingApi({endpoint: document}), REPOSITORY, PARENT, BASE), HEAD)
        with self.assertRaises(gate.GateError):
            gate.compare_files(MappingApi({endpoint: document, f"repos/{REPOSITORY}/git/commits/{HEAD}": {}}), REPOSITORY, PARENT, BASE)

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


class ProductRepairContracts(unittest.TestCase):
    """Exercise real gate and branch attestation code against fake GET responses."""

    def setUp(self):
        # Pure fake-GET contracts must not inherit a hosting job's native role.
        environment = mock.patch.dict('os.environ', {'GITHUB_ACTIONS': 'false'})
        self.addCleanup(environment.stop)
        environment.start()

    def fixture(self, changes=None, target="android-vr-pico"):
        settings = config()
        paths = settings["reconciliation_repair_paths"].get(target, [])
        edge = settings["edges"][target]
        parent = edge["parent"]
        scope = edge["scope"]
        repo = {"id": REPOSITORY_ID, "full_name": REPOSITORY}
        pr = {
            "number": 610, "state": "open", "mergeable": True, "merge_commit_sha": MERGE,
            "base": {"ref": target, "sha": BASE, "repo": deepcopy(repo)},
            "head": {"ref": f"reconcile/{scope}/tablet-repair", "sha": HEAD, "repo": deepcopy(repo)},
        }
        event = {"repository": deepcopy(repo), "pull_request": deepcopy(pr)}
        privileged = [entry(".github/sync-test-reuse.json"), entry("tools/branch-policy/check.py")]
        tree = {"truncated": False, "tree": privileged}
        old = "8" * 40
        documents = {
            f"repos/{REPOSITORY}/git/ref/heads/{target}": {"object": {"sha": BASE}},
            f"repos/{REPOSITORY}/git/ref/heads/{parent}": {"object": {"sha": PARENT}},
            f"repos/{REPOSITORY}/git/commits/{HEAD}": {
                "sha": HEAD, "parents": [{"sha": BASE}, {"sha": PARENT}]},
            f"repos/{REPOSITORY}/git/commits/{MERGE}": {
                "sha": MERGE, "parents": [{"sha": BASE}, {"sha": HEAD}]},
            f"repos/{REPOSITORY}/pulls/610": pr,
            f"repos/{REPOSITORY}/pulls/610/files?per_page=100&page=1": changes if changes is not None else [
                {"filename": path, "status": "modified"} for path in paths
            ],
            f"repos/{REPOSITORY}/compare/{PARENT}...{BASE}": {
                "base_commit": {"sha": PARENT}, "merge_base_commit": {"sha": old}},
            f"repos/{REPOSITORY}/compare/{old}...{PARENT}": {
                "base_commit": {"sha": old}, "merge_base_commit": {"sha": old},
                "files": [{"filename": paths[index]} for index in (1, 3) if index < len(paths)]
                         + [{"filename": ".github/sync-test-reuse.json"}]},
        }
        for ancestor in (BASE, PARENT):
            documents[f"repos/{REPOSITORY}/compare/{ancestor}...{HEAD}"] = {
                "status": "ahead", "behind_by": 0, "base_commit": {"sha": ancestor},
                "merge_base_commit": {"sha": ancestor},
            }
        for sha in (PARENT, HEAD, MERGE):
            documents[f"repos/{REPOSITORY}/git/trees/{sha}?recursive=1"] = deepcopy(tree)

        class Api(MappingApi):
            def __init__(self):
                super().__init__(documents)
                self.calls = []

            def json(self, endpoint, **kwargs):
                if kwargs.get("method", "GET") != "GET":
                    raise AssertionError("repair attestation must be read-only")
                self.calls.append(endpoint)
                value = super().json(endpoint)
                return value() if callable(value) else value

        return event, settings, Api()

    def classify(self, event, settings, api):
        return gate.classify_event(event, settings, api)

    def inspect(self, event, settings, api):
        source = mock.Mock()
        source.read_text.return_value = json.dumps(event)
        with mock.patch.object(gate, "load_config", return_value=settings), \
             mock.patch.object(gate, "GitHubApi", return_value=api), \
             trusted_codeql_policy([]), \
             mock.patch.object(gate, "verify_evidence", side_effect=AssertionError("repair must never reuse evidence")), \
             mock.patch.object(gate, "write_outputs") as output:
            self.assertEqual(gate.inspect(SimpleNamespace(config=None, event=source, output=None)), 0)
            result = output.call_args.args[1]
            self.assertEqual(result["mode"], "fallback")
            self.assertEqual(result["profile"], settings["edges"][event["pull_request"]["base"]["ref"]]["differential"])
            self.assertEqual(result["evidence_run_id"], "")
            self.assertEqual(result["merge_sha"], MERGE)
            return result

    def test_each_owned_ios_repair_requires_full_qualification(self):
        paths = config()["reconciliation_repair_paths"]["apple-ios"]
        for path in paths:
            with self.subTest(path=path):
                self.inspect(*self.fixture([{"filename": path, "status": "modified"}], target="apple-ios"))

    def test_phone_clock_repairs_require_full_qualification(self):
        paths = (
            "android/phone/tests/phone-voice-clock-fixture.cpp",
            "android/phone/tests/phone-voice-clock-test.py",
        )
        self.assertEqual(config()["reconciliation_repair_paths"]["android-phone"], list(paths))
        event, settings, api = self.fixture(target="android-phone")
        sync = self.classify(event, settings, api)
        self.assertEqual(sync.repair_paths, tuple(sorted(paths)))
        self.assertNotIn(paths[0], sync.parent_changed_paths)
        self.assertIn(paths[1], sync.parent_changed_paths)
        self.inspect(event, settings, api)
        for path in paths:
            with self.subTest(path=path):
                self.inspect(*self.fixture([{"filename": path, "status": "modified"}],
                                          target="android-phone"))

    def test_android_owner_handoff_repairs_require_full_fallback(self):
        transfer = json.loads((HERE.parents[1] / ".github/android-owner-transfer.json").read_text())
        paths = set(transfer["legacy_workflows"]) | set(transfer["source_contracts"])
        self.assertEqual(len(paths), 6)
        self.assertEqual(gate.allowed_repair_paths(config(), "android-main"), paths)
        event, settings, api = self.fixture(target="android-main")
        request = self.classify(event, settings, api)
        self.assertEqual(set(request.repair_paths), paths)
        self.assertTrue(paths - set(request.parent_changed_paths))
        self.inspect(event, settings, api)
        # Even one registered path inherited from the parent keeps full fallback.
        for path in sorted(paths):
            with self.subTest(path=path):
                self.inspect(*self.fixture([{"filename": path, "status": "modified"}],
                                          target="android-main"))

    def test_android_owner_handoff_does_not_admit_neighbors_or_other_targets(self):
        paths = config()["reconciliation_repair_paths"]["android-main"]
        repairs = [{"filename": path, "status": "modified"} for path in paths]
        for path in ("android/common/tests/ci/extra.py", "android/phone/tests/extra.py",
                     ".github/workflows/android-required.yml", ".github/workflows/project-tests.yml",
                     "tools/repository-checks/android_gate.py", "libraries/audio-client/src/AudioClient.cpp"):
            with self.subTest(path=path), self.assertRaises(gate.GateError):
                self.classify(*self.fixture(repairs + [{"filename": path, "status": "modified"}],
                                            target="android-main"))
        for target in ("android-phone", "android-vr", "android-vr-pico", "apple-main", "apple-ios"):
            with self.subTest(target=target), self.assertRaises(gate.GateError):
                self.classify(*self.fixture(repairs, target=target))

    def test_android_owner_handoff_preserves_exact_reconciliation_attestation(self):
        for mutation in ("parents", "head-tree", "merge-tree", "parent-ref", "foreign-head"):
            event, settings, api = self.fixture(target="android-main")
            if mutation == "parents":
                api.documents[f"repos/{REPOSITORY}/git/commits/{HEAD}"]["parents"].reverse()
            elif mutation in ("head-tree", "merge-tree"):
                sha = HEAD if mutation == "head-tree" else MERGE
                api.documents[f"repos/{REPOSITORY}/git/trees/{sha}?recursive=1"]["tree"][0]["sha"] = "9" * 40
            elif mutation == "parent-ref":
                api.documents[f"repos/{REPOSITORY}/git/ref/heads/main"]["object"]["sha"] = "9" * 40
            else:
                for pr in (event["pull_request"], api.documents[f"repos/{REPOSITORY}/pulls/610"]):
                    pr["head"]["repo"]["id"] = REPOSITORY_ID + 1
            with self.subTest(mutation=mutation), self.assertRaises(gate.GateError):
                self.classify(event, settings, api)

    def test_phone_clock_repairs_cannot_carry_neighbor_or_shared_changes(self):
        for path in (
                "android/phone/tests/phone-voice-clock-extra.cpp",
                "android/phone/apps/phoneInterface/src/PhoneAudio.cpp",
                "android/common/src/AndroidAudioAdapter.cpp",
                "libraries/audio-client/src/AudioClient.cpp",
                "tests/device/run_control_plane_tests.py",
                "scripts/+android_phoneInterface/defaultScripts.js",
                ".github/workflows/project-tests.yml",
                "tools/sync-test-reuse/gate.py"):
            event, settings, api = self.fixture(target="android-phone")
            api.documents[f"repos/{REPOSITORY}/pulls/610/files?per_page=100&page=1"].append(
                {"filename": path, "status": "modified"})
            with self.subTest(path=path), self.assertRaises(gate.GateError):
                self.classify(event, settings, api)

    def test_phone_repair_attestation_rejects_wrong_parents_and_privileged_drift(self):
        for mutation in ("parents", "head-tree", "merge-tree", "parent-ref", "foreign-head"):
            event, settings, api = self.fixture(target="android-phone")
            if mutation == "parents":
                api.documents[f"repos/{REPOSITORY}/git/commits/{HEAD}"]["parents"].reverse()
            elif mutation in ("head-tree", "merge-tree"):
                sha = HEAD if mutation == "head-tree" else MERGE
                api.documents[f"repos/{REPOSITORY}/git/trees/{sha}?recursive=1"]["tree"][0]["sha"] = "9" * 40
            elif mutation == "parent-ref":
                api.documents[f"repos/{REPOSITORY}/git/ref/heads/android-main"]["object"]["sha"] = "9" * 40
            else:
                for pr in (event["pull_request"], api.documents[f"repos/{REPOSITORY}/pulls/610"]):
                    pr["head"]["repo"]["id"] = REPOSITORY_ID + 1
            with self.subTest(mutation=mutation), self.assertRaises(gate.GateError):
                self.classify(event, settings, api)

    def test_ios_repairs_cannot_modify_shared_or_unlisted_product_paths(self):
        for path in ("tests/device/probe/overte_e2e_probe.js", "tests/device/run_control_plane_tests.py",
                     "tests/device/ios/adapters/unknown.py", ".github/workflows/project-tests.yml"):
            event, settings, api = self.fixture(target="apple-ios")
            api.documents[f"repos/{REPOSITORY}/pulls/610/files?per_page=100&page=1"].append(
                {"filename": path, "status": "modified"})
            with self.subTest(path=path), self.assertRaises(gate.GateError):
                self.classify(event, settings, api)

    def test_ios_parent_contract_fixture_repairs_require_full_fallback(self):
        paths = (
            "ios/tests/ios-touch-ui-adapter-contract-test.py",
            "ios/tests/native_contracts/mute-caller-test.cpp",
            "ios/tests/native_contracts/test_mute_caller.py",
        )
        changes = [{"filename": path, "status": "modified"} for path in paths]
        event, settings, api = self.fixture(changes, target="apple-ios")
        request = self.classify(event, settings, api)
        self.assertEqual(request.repair_paths, tuple(sorted(paths)))
        self.inspect(event, settings, api)

    def test_ios_kit_fetch_fixture_repair_requires_complete_fallback(self):
        path = "tests/device/self_tests/test_ios_personal_team_fetch.py"
        event, settings, api = self.fixture(
            [{"filename": path, "status": "modified"}], target="apple-ios")
        request = self.classify(event, settings, api)
        self.assertEqual(request.repair_paths, (path,))
        self.assertNotIn(path, request.parent_changed_paths)
        # inspect() rejects evidence reuse and requires the complete leaf profile.
        self.inspect(event, settings, api)

    def test_ios_kit_fetch_fixture_repair_does_not_admit_neighbors(self):
        repair = {"filename": "tests/device/self_tests/test_ios_personal_team_fetch.py",
                  "status": "modified"}
        for path in (
                "tests/device/self_tests/test_ios_personal_team_fetch_extra.py",
                "tests/device/self_tests/test_ios_personal_team_artifacts.py",
                "tests/device/ios/fetch_personal_team_kit.py",
                "tools/sync-test-reuse/gate.py"):
            changes = [repair, {"filename": path, "status": "modified"}]
            with self.subTest(path=path), self.assertRaises(gate.GateError):
                self.classify(*self.fixture(changes, target="apple-ios"))

    def test_ios_kit_fetch_fixture_repair_is_not_cross_platform(self):
        changes = [{"filename": "tests/device/self_tests/test_ios_personal_team_fetch.py",
                    "status": "modified"}]
        for target in ("android-phone", "android-vr", "android-vr-pico", "apple-main"):
            with self.subTest(target=target), self.assertRaises(gate.GateError):
                self.classify(*self.fixture(changes, target=target))

    def test_ios_parent_contract_repairs_cannot_carry_product_or_neighbor_changes(self):
        repairs = [
            {"filename": "ios/tests/ios-touch-ui-adapter-contract-test.py", "status": "modified"},
            {"filename": "ios/tests/native_contracts/mute-caller-test.cpp", "status": "modified"},
            {"filename": "ios/tests/native_contracts/test_mute_caller.py", "status": "modified"},
        ]
        for path in (
                "ios/tests/native_contracts/unknown.cpp",
                "ios/tests/ios-touch-ui-adapter-contract-extra.py",
                "ios/metrics/IOSTouchUiMetrics.mm",
                "libraries/audio-client/src/AudioClient.cpp",
                "scripts/system/settings/qml/pages/GraphicsSettingsBase.qml",
                "android/vr/pico/tests/pico-tablet-settings-test.js",
                "tools/sync-test-reuse/gate.py"):
            changes = repairs + [{"filename": path, "status": "modified"}]
            with self.subTest(path=path), self.assertRaises(gate.GateError):
                self.classify(*self.fixture(changes, target="apple-ios"))

    def test_product_repair_scopes_cannot_be_exchanged(self):
        targets = ("apple-ios", "android-vr-pico", "android-phone")
        for target, foreign in ((target, foreign) for target in targets for foreign in targets if target != foreign):
            event, settings, api = self.fixture(target=target)
            path = settings["reconciliation_repair_paths"][foreign][0]
            api.documents[f"repos/{REPOSITORY}/pulls/610/files?per_page=100&page=1"].append(
                {"filename": path, "status": "modified"})
            with self.subTest(target=target), self.assertRaises(gate.GateError):
                self.classify(event, settings, api)

    def test_attested_four_path_pico_repair_requires_full_fallback(self):
        event, settings, api = self.fixture()
        sync = self.classify(event, settings, api)
        self.assertEqual(sync.repair_paths, tuple(sorted(settings["reconciliation_repair_paths"]["android-vr-pico"])))
        # Extra product paths never become part of the qualified parent delta.
        self.assertNotIn(sync.repair_paths[0], sync.parent_changed_paths)
        self.inspect(*self.fixture())

    def test_every_individually_allowed_path_forces_fallback_including_parent_delta_paths(self):
        for path in config()["reconciliation_repair_paths"]["android-vr-pico"]:
            with self.subTest(path=path):
                self.inspect(*self.fixture([{"filename": path, "status": "modified"}]))

    def test_even_explicitly_allowed_markdown_repairs_cannot_take_documentation_shortcut(self):
        path = "docs/product-repair.md"
        event, settings, api = self.fixture([{"filename": path, "status": "modified"}])
        settings["reconciliation_repair_paths"]["android-vr-pico"].append(path)
        self.inspect(event, settings, api)

    def test_unlisted_extra_paths_or_missing_target_allowlist_are_rejected(self):
        for path in ("android/vr/pico/src/unknown.cpp", ".github/workflows/sync-validation.yml",
                     "tools/branch-policy/extra.py", "ios/product.cpp"):
            with self.subTest(path=path):
                event, settings, api = self.fixture()
                api.documents[f"repos/{REPOSITORY}/pulls/610/files?per_page=100&page=1"].append(
                    {"filename": path, "status": "modified"})
                with self.assertRaisesRegex(gate.GateError, "absent from the exact parent delta"):
                    self.classify(event, settings, api)
        event, settings, api = self.fixture()
        settings.pop("reconciliation_repair_paths")
        with self.assertRaises(gate.GateError):
            self.classify(event, settings, api)

    def test_malformed_or_privileged_allowlists_fail_closed(self):
        for paths in (None, "android/**", ["android/**"], ["../escape"],
                      ["tools/branch-policy/check.py"], [".github/sync-test-reuse.json"],
                      ["same", "same"], [None]):
            with self.subTest(paths=paths):
                event, settings, api = self.fixture()
                settings["reconciliation_repair_paths"]["android-vr-pico"] = paths
                with self.assertRaises(gate.GateError):
                    self.classify(event, settings, api)

    def test_rename_checks_both_sides_and_requires_both_extra_paths_to_be_allowed(self):
        one, two = config()["reconciliation_repair_paths"]["android-vr-pico"][:2]
        self.inspect(*self.fixture([{"filename": two, "previous_filename": one, "status": "renamed"}]))
        for unlisted in ("android/vr/pico/unknown.cpp", ".github/workflows/sync-validation.yml",
                         "../escape", "tools/branch-policy/check.py"):
            for source, target in ((unlisted, one), (one, unlisted)):
                with self.subTest(source=source, target=target), self.assertRaises(gate.GateError):
                    self.classify(*self.fixture([{
                        "filename": target, "previous_filename": source, "status": "renamed",
                    }]))
        with self.assertRaisesRegex(gate.GateError, "source path"):
            self.classify(*self.fixture([{"filename": one, "status": "renamed"}]))

    def test_parent_delta_rename_audits_both_paths(self):
        endpoint = f"repos/{REPOSITORY}/compare/{BASE}...{PARENT}"
        api = MappingApi({endpoint: {"merge_base_commit": {"sha": BASE}, "files": [{
            "filename": "new.qml", "previous_filename": "old.qml", "status": "renamed",
        }]}})
        self.assertEqual(gate.compare_files(api, REPOSITORY, BASE, PARENT), (BASE, {"old.qml", "new.qml"}))

    def test_wrong_or_stale_reconciliation_and_candidate_parents_are_rejected(self):
        for sha, parents in ((HEAD, (BASE,)), (HEAD, (PARENT, BASE)), (HEAD, (BASE, "9" * 40)),
                             (HEAD, ("9" * 40, PARENT)), (HEAD, (BASE, PARENT, MERGE)),
                             (MERGE, (PARENT, HEAD)), (MERGE, (BASE, "9" * 40))):
            with self.subTest(sha=sha, parents=parents):
                event, settings, api = self.fixture()
                api.documents[f"repos/{REPOSITORY}/git/commits/{sha}"]["parents"] = [{"sha": p} for p in parents]
                with self.assertRaises(gate.GateError):
                    self.classify(event, settings, api)

    def test_repository_identity_and_live_pr_head_are_bound(self):
        for document, side, field, value in (
            ("event", "repository", "id", 7), ("event", "repository", "full_name", "foreign/fork"),
            ("event", "base", "id", 7), ("event", "head", "id", 7),
            ("event", "base", "full_name", "foreign/fork"),
            ("event", "head", "full_name", "foreign/fork"),
            ("live", "head", "id", 7), ("live", "base", "full_name", "foreign/fork"),
        ):
            with self.subTest(document=document, side=side, field=field):
                event, settings, api = self.fixture()
                target = event if document == "event" else api.documents[f"repos/{REPOSITORY}/pulls/610"]
                if side == "repository":
                    target[side][field] = value
                else:
                    (target["pull_request"] if document == "event" else target)[side]["repo"][field] = value
                with self.assertRaises(gate.GateError):
                    self.classify(event, settings, api)
        for side in ("base", "head"):
            event, settings, api = self.fixture()
            api.documents[f"repos/{REPOSITORY}/pulls/610"][side]["sha"] = "9" * 40
            with self.subTest(side=side), self.assertRaises(gate.GateError):
                self.classify(event, settings, api)
        event, settings, api = self.fixture()
        stale = "9" * 40
        event["pull_request"]["head"]["sha"] = stale
        api.documents[f"repos/{REPOSITORY}/git/commits/{stale}"] = {
            "sha": stale, "parents": [{"sha": BASE}, {"sha": PARENT}],
        }
        with self.assertRaisesRegex(gate.GateError, "merge parents"):
            self.classify(event, settings, api)

    def test_stale_event_base_and_inconsistent_parent_policy_are_rejected(self):
        event, settings, api = self.fixture()
        event["pull_request"]["base"]["sha"] = "9" * 40
        with self.assertRaisesRegex(gate.GateError, "drifted"):
            self.classify(event, settings, api)
        event, settings, api = self.fixture()
        settings["edges"]["android-vr-pico"]["parent"] = "main"
        api.documents[f"repos/{REPOSITORY}/git/ref/heads/main"] = {"object": {"sha": PARENT}}
        with self.assertRaisesRegex(gate.GateError, "trusted branch policy"):
            self.classify(event, settings, api)

    def test_privileged_head_and_executed_candidate_must_exactly_match_parent(self):
        for sha in (HEAD, MERGE):
            for mutation in ("blob", "mode", "delete", "add", "truncated"):
                with self.subTest(sha=sha, mutation=mutation):
                    event, settings, api = self.fixture()
                    tree = api.documents[f"repos/{REPOSITORY}/git/trees/{sha}?recursive=1"]
                    if mutation == "blob":
                        tree["tree"][0]["sha"] = "9" * 40
                    elif mutation == "mode":
                        tree["tree"][0]["mode"] = "120000"
                    elif mutation == "delete":
                        tree["tree"].pop()
                    elif mutation == "add":
                        tree["tree"].append(entry("tools/branch-policy/added.py"))
                    else:
                        tree["truncated"] = True
                    with self.assertRaises(gate.GateError):
                        self.classify(event, settings, api)

    def test_base_and_parent_drift_at_every_repair_attestation_phase_fail_closed(self):
        for branch, original in (("android-vr-pico", BASE), ("android-vr", PARENT)):
            for phase in (1, 2, 3):
                event, settings, api = self.fixture()
                responses = [original] * phase + ["9" * 40] * (4 - phase)
                api.documents[f"repos/{REPOSITORY}/git/ref/heads/{branch}"] = (
                    lambda values=responses: {"object": {"sha": values.pop(0)}})
                with self.subTest(branch=branch, phase=phase), self.assertRaises(gate.GateError):
                    self.classify(event, settings, api)

    def test_wrong_reconciliation_name_cannot_use_repair_authorization(self):
        event, settings, api = self.fixture()
        for pr in (event["pull_request"], api.documents[f"repos/{REPOSITORY}/pulls/610"]):
            pr["head"]["ref"] = "reconcile/android-pico/-invalid"
        with self.assertRaises(gate.GateError):
            self.classify(event, settings, api)

    def test_direct_sync_cannot_use_the_extra_repair_path_exception(self):
        event, settings, api = self.fixture()
        for pr in (event["pull_request"], api.documents[f"repos/{REPOSITORY}/pulls/610"]):
            pr["head"].update(ref="android-vr", sha=PARENT)
        api.documents[f"repos/{REPOSITORY}/git/commits/{PARENT}"] = {"sha": PARENT}
        api.documents[f"repos/{REPOSITORY}/git/commits/{MERGE}"]["parents"] = [
            {"sha": BASE}, {"sha": PARENT}]
        with self.assertRaisesRegex(gate.GateError, "absent from the exact parent delta"):
            self.classify(event, settings, api)

    def test_failed_or_stale_ancestry_attestation_cannot_authorize_repairs(self):
        for ancestor in (BASE, PARENT):
            for field, value in (("status", "diverged"), ("behind_by", 1),
                                 ("merge_base_commit", {"sha": "9" * 40}),
                                 ("base_commit", {"sha": "9" * 40})):
                event, settings, api = self.fixture()
                api.documents[f"repos/{REPOSITORY}/compare/{ancestor}...{HEAD}"][field] = value
                with self.subTest(ancestor=ancestor, field=field), self.assertRaises(gate.GateError):
                    self.classify(event, settings, api)

    def test_attestation_api_failure_or_malformed_tree_never_becomes_fallback_authorization(self):
        for response in (gate.GateError("lookup failed"), [], {"truncated": False, "tree": [None]}):
            event, settings, api = self.fixture()
            api.documents[f"repos/{REPOSITORY}/git/trees/{HEAD}?recursive=1"] = response
            with self.subTest(response=response), self.assertRaises(gate.GateError):
                self.classify(event, settings, api)


class InspectionContracts(unittest.TestCase):
    # Legacy topology/evidence fixtures isolate the orthogonal CodeQL policy;
    # RequiredCodeQLInvocationTests exercises its real ordinary-PR hook below.
    def inspect_request(self, sync_request, evidence_error=None):
        with mock.patch.object(gate, "load_config", return_value=config()), \
             mock.patch.object(gate, "GitHubApi"), \
             trusted_codeql_policy([]), \
             mock.patch.object(gate, "classify_event", return_value=sync_request), \
             mock.patch.object(gate, "verify_evidence", side_effect=evidence_error) as verify, \
             mock.patch.object(gate, "write_outputs") as output:
            event = mock.Mock()
            event.read_text.return_value = "{}"
            self.assertEqual(gate.inspect(SimpleNamespace(config=None, event=event, output=None)), 0)
            return verify.call_count, output.call_args.args[1]

    def test_markdown_sync_needs_no_parent_evidence(self):
        calls, result = self.inspect_request(replace(request(), profile="documentation", changed_paths=("docs/ROADMAP.md",)))
        self.assertEqual(calls, 0)
        self.assertEqual(result["mode"], "reuse")
        self.assertEqual(result["profile"], "documentation")
        self.assertEqual(result["evidence_run_id"], "")

    def test_code_sync_still_falls_back_without_evidence(self):
        calls, result = self.inspect_request(request(), gate.EvidenceError("missing evidence"))
        self.assertEqual(calls, 1)
        self.assertEqual(result["mode"], "fallback")

    def test_tool_sync_checks_the_tools_without_claiming_complete_host_qualification(self):
        calls, result = self.inspect_request(replace(request(), profile='tool-dependencies',
                    changed_paths=('tools/jsdoc/package-lock.json',)))
        self.assertEqual(calls, 0)
        self.assertEqual(result['mode'], 'reuse')
        self.assertEqual(result['evidence_run_id'], '')


class DifferentialContracts(unittest.TestCase):
    def test_retired_desktop_differential_profiles_are_rejected(self):
        for profile in ("linux-desktop", "windows-desktop"):
            with self.subTest(profile=profile):
                with self.assertRaisesRegex(ValueError, "unknown differential profile"):
                    differential.required_roots(Path("."), profile, [])

    def test_documentation_never_selects_an_android_suite(self):
        self.assertEqual(differential.PROFILES["documentation"], ())
        with self.assertRaises(ValueError):
            differential.required_roots(Path("."), "documentation", ["android/source.cpp"])
        with self.assertRaises(ValueError):
            differential.required_roots(Path("."), "documentation", ["docs/helper.py"])

    def test_each_non_documentation_profile_has_a_minimal_owned_root(self):
        self.assertEqual(set(differential.PROFILES) - {"documentation", "tool-dependencies"}, {
            "android-family", "android-phone", "android-vr", "android-pico",
            "apple-family", "apple-ios",
        })
        self.assertTrue(all(differential.PROFILES[name] for name in differential.PROFILES
                            if name not in {"documentation", "tool-dependencies"}))

    def test_tool_profile_rejects_mixed_changes_and_empty_tool_inventory(self):
        valid = ['tools/jsdoc/package-lock.json']
        differential.required_roots(Path('.'), 'tool-dependencies', valid)
        differential.required_roots(Path('.'), 'tool-dependencies',
                                    ['script-archive/marketplace/S3Server/package-lock.json'])
        for paths in ([], ['docs/a.md'], valid + ['libraries/shared/src/AABox.cpp'],
                      valid + ['tools/jsdoc/CMakeLists.txt']):
            with self.assertRaises(ValueError):
                differential.required_roots(Path('.'), 'tool-dependencies', paths)


class RetiredCancellationContracts(unittest.TestCase):
    def test_legacy_command_returns_immediately_without_api_or_polling(self):
        self.assertEqual(config()["redundant_pull_request_workflows"], [])
        legacy = ["cancel-redundant", "--repository", REPOSITORY, "--pull-request", "7", "--head-sha", HEAD]
        for window in ([], ["--window", "60"]):
            with self.subTest(arguments=window), \
                    mock.patch.object(sys, "argv", ["gate.py", *legacy, *window]), \
                    mock.patch.object(gate, "GitHubApi", side_effect=AssertionError("unexpected API access")) as api, \
                    mock.patch.object(gate.time, "monotonic", side_effect=AssertionError("unexpected polling")) as clock, \
                    mock.patch.object(gate.time, "sleep", side_effect=AssertionError("unexpected wait")) as sleep, \
                    mock.patch.object(sys, "stdout", new_callable=io.StringIO) as output:
                self.assertEqual(gate.main(), 0)
                self.assertEqual(output.getvalue(), "cancelled_redundant_runs=0\n")
                api.assert_not_called()
                clock.assert_not_called()
                sleep.assert_not_called()


class DispatchContracts(unittest.TestCase):
    def run_document(self, correlation="gate-700-attempt-2", *, run_id=902,
                     status="completed", conclusion="success"):
        repository = {"id": REPOSITORY_ID, "full_name": REPOSITORY}
        return {"id": run_id, "display_title": f"Sync validation {correlation}",
                "status": status, "conclusion": conclusion, "workflow_id": 350930895,
                "path": ".github/workflows/sync-validation.yml", "event": "workflow_dispatch",
                "head_branch": "main", "head_sha": PARENT, "run_attempt": 1, "check_suite_id": 904,
                "repository": repository, "head_repository": repository,
                "url": f"https://api.github.com/repos/{REPOSITORY}/actions/runs/{run_id}",
                "html_url": f"https://github.com/{REPOSITORY}/actions/runs/{run_id}"}

    def dispatch(self, snapshots, *, mode="reuse", attempt=2, arguments=None,
                 reply="valid", mutate=None, checkout_source=PARENT):
        args = SimpleNamespace(
            config=gate.DEFAULT_CONFIG, repository=REPOSITORY, pull_request=610,
            mode=mode, profile="android-family", base_sha=BASE, head_sha=HEAD,
            merge_sha=MERGE, gate_run_id=700, gate_run_attempt=attempt,
            timeout=30, output=None,
        )
        self.api = mock.Mock()
        queue = list(snapshots)
        current = None
        def request(endpoint, **kwargs):
            nonlocal current
            prefix = f"repos/{REPOSITORY}"
            if endpoint == prefix:
                value = {"id": REPOSITORY_ID, "full_name": REPOSITORY, "default_branch": "main"}
            elif endpoint == prefix + "/branches/main":
                value = {"name": "main", "protected": True, "commit": {"sha": PARENT}}
            elif endpoint == prefix + "/actions/workflows/sync-validation.yml":
                value = {"id": 350930895, "path": ".github/workflows/sync-validation.yml",
                         "name": "Sync validation", "state": "active"}
            elif endpoint.endswith("/dispatches"):
                value = ({"workflow_run_id": 902,
                          "run_url": f"https://api.github.com/{prefix}/actions/runs/902",
                          "html_url": f"https://github.com/{REPOSITORY}/actions/runs/902"}
                         if reply == "valid" else reply)
            elif endpoint == prefix + "/actions/runs/902":
                if queue:
                    current = queue.pop(0)
                value = current
            elif endpoint == prefix + "/actions/runs/902/attempts/1":
                value = current
            elif endpoint == prefix + "/check-suites/904":
                value = {"id": 904, "head_sha": PARENT, "repository": {"id": REPOSITORY_ID,
                         "full_name": REPOSITORY}, "app": {"id": 15368}}
            else:
                raise AssertionError("unexpected API endpoint: " + endpoint)
            return mutate(endpoint, deepcopy(value)) if mutate else deepcopy(value)
        self.api.json.side_effect = request
        clock = [0]
        def sleep(seconds):
            clock[0] += seconds
        with mock.patch.object(gate, "GitHubApi", return_value=self.api), \
             mock.patch.object(gate, "_dispatch_checkout_source", return_value=checkout_source), \
             mock.patch.object(gate.time, "monotonic", side_effect=lambda: clock[0]), \
             mock.patch.object(gate.time, "sleep", side_effect=sleep) as self.sleep, \
             mock.patch.object(gate, "write_outputs") as self.outputs:
            if arguments is not None:
                with mock.patch.object(sys, "argv", ["gate.py", *arguments]):
                    return gate.main()
            return gate.dispatch_and_wait(args)

    def legacy_arguments(self, mode="reuse"):
        return [
            "dispatch-and-wait", "--repository", REPOSITORY, "--pull-request", "610",
            "--mode", mode, "--profile", "android-family", "--base-sha", BASE,
            "--head-sha", HEAD, "--merge-sha", MERGE, "--gate-run-id", "700",
            "--timeout", "30",
        ]

    def assert_dispatch_binding(self, mode, attempt=2):
        posts = [call for call in self.api.json.call_args_list if call.kwargs.get("method") == "POST"]
        self.assertEqual(posts, [mock.call(
            f"repos/{REPOSITORY}/actions/workflows/{config()['validation_workflow']}/dispatches",
            method="POST", fields={
                "ref": "main", "inputs[correlation]": f"gate-700-attempt-{attempt}",
                "inputs[mode]": mode, "inputs[profile]": "android-family",
                "inputs[pull_request]": "610", "inputs[expected_base_sha]": BASE,
                "inputs[expected_head_sha]": HEAD, "inputs[expected_merge_sha]": MERGE,
            }, dispatch_details=True,
        )])
        self.assertFalse(any("/runs?" in call.args[0] for call in self.api.json.call_args_list))

    def test_retry_ignores_old_failures_until_current_run_becomes_visible(self):
        # Direct ownership replaces first-page discovery: old runs are never read.
        for mode in ("reuse", "fallback"):
            with self.subTest(mode=mode):
                self.assertEqual(self.dispatch([
                    self.run_document(status="requested", conclusion=None),
                    self.run_document(status="in_progress", conclusion=None),
                    self.run_document()], mode=mode), 0)
                self.assert_dispatch_binding(mode)
                self.assertEqual(self.sleep.call_count, 2)
                self.outputs.assert_called_once_with(None, {
                    "validation_run_id": 902,
                    "validation_url": f"https://github.com/{REPOSITORY}/actions/runs/902",
                })

    def test_first_attempt_and_retry_dispatch_distinct_correlations(self):
        for attempt in (1, 2):
            with self.subTest(attempt=attempt):
                self.assertEqual(self.dispatch([self.run_document(
                    f"gate-700-attempt-{attempt}")], attempt=attempt), 0)
                self.assert_dispatch_binding("reuse", attempt)
                self.sleep.assert_not_called()

    def test_legacy_workflow_uses_environment_attempt_and_ignores_old_failure(self):
        for mode in ("reuse", "fallback"):
            with self.subTest(mode=mode), mock.patch.dict(
                gate.os.environ, {"GITHUB_RUN_ATTEMPT": "2", "GITHUB_WORKFLOW_SHA": HEAD}, clear=True
            ):
                self.assertEqual(self.dispatch([
                    self.run_document(status="queued", conclusion=None),
                    self.run_document(status="in_progress", conclusion=None), self.run_document(),
                ], arguments=self.legacy_arguments(mode)), 0)
                self.assert_dispatch_binding(mode)
                self.assertEqual(self.sleep.call_count, 2)
                self.outputs.assert_called_once_with(None, {
                    "validation_run_id": 902,
                    "validation_url": f"https://github.com/{REPOSITORY}/actions/runs/902",
                })

    def test_missing_invalid_or_nonpositive_environment_attempt_fails_before_api(self):
        for value in (None, "", "invalid", "2.5", "0", "-1"):
            environment = {} if value is None else {"GITHUB_RUN_ATTEMPT": value}
            with self.subTest(value=value), mock.patch.dict(gate.os.environ, environment, clear=True), \
                 mock.patch("sys.stderr", new_callable=io.StringIO):
                self.assertEqual(self.dispatch([], arguments=self.legacy_arguments()), 2)
                self.api.json.assert_not_called()
                self.outputs.assert_not_called()

    def test_explicit_attempt_takes_priority_over_environment(self):
        for value in (None, "1", "invalid", "0", "-1"):
            environment = {} if value is None else {"GITHUB_RUN_ATTEMPT": value}
            with self.subTest(value=value), mock.patch.dict(gate.os.environ, environment, clear=True):
                self.assertEqual(self.dispatch([self.run_document()], arguments=[
                    *self.legacy_arguments(), "--gate-run-attempt", "2",
                ]), 0)
                self.assert_dispatch_binding("reuse", 2)

    def test_invalid_explicit_attempt_never_falls_back_to_valid_environment(self):
        for value in ("", "invalid", "2.5", "0", "-1"):
            with self.subTest(value=value), mock.patch.dict(
                gate.os.environ, {"GITHUB_RUN_ATTEMPT": "2"}, clear=True
            ), mock.patch("sys.stderr", new_callable=io.StringIO):
                if value in ("0", "-1"):
                    self.assertEqual(self.dispatch([], arguments=[
                        *self.legacy_arguments(), "--gate-run-attempt", value,
                    ]), 2)
                else:
                    with self.assertRaises(SystemExit) as error:
                        self.dispatch([], arguments=[
                            *self.legacy_arguments(), "--gate-run-attempt", value,
                        ])
                    self.assertEqual(error.exception.code, 2)
                self.api.json.assert_not_called()
                self.outputs.assert_not_called()

    def test_current_unsuccessful_run_cannot_be_hidden_by_old_success(self):
        for mode in ("reuse", "fallback"):
            for conclusion in ("failure", "cancelled", "timed_out", "skipped", None):
                with self.subTest(mode=mode, conclusion=conclusion):
                    with self.assertRaisesRegex(gate.GateError, f"{mode} validation did not succeed"):
                        self.dispatch([self.run_document(status="in_progress", conclusion=None),
                                       self.run_document(conclusion=conclusion)], mode=mode)
                    self.outputs.assert_not_called()
                    self.assert_dispatch_binding(mode)

    def test_duplicate_current_correlation_fails_before_accepting_success(self):
        # A same-title success with another ID cannot replace our returned ID.
        for mode in ("reuse", "fallback"):
            with self.subTest(mode=mode), self.assertRaisesRegex(gate.GateError, "identity"):
                self.dispatch([self.run_document(run_id=903)], mode=mode)
            self.outputs.assert_not_called()
            self.assert_dispatch_binding(mode)

    def test_missing_or_nonterminal_current_run_times_out(self):
        for mode in ("reuse", "fallback"):
            for status in ("requested", "queued", "in_progress"):
                with self.subTest(mode=mode, status=status):
                    with self.assertRaisesRegex(gate.GateError, "before timeout"):
                        self.dispatch([self.run_document(status=status, conclusion=None)] * 3, mode=mode)
                    self.outputs.assert_not_called()
                    self.assertEqual(self.sleep.call_count, 3)
                    self.assert_dispatch_binding(mode)

    def test_empty_or_malformed_reply_never_rediscovers_or_redispatches(self):
        good = {"workflow_run_id": 902,
                "run_url": f"https://api.github.com/repos/{REPOSITORY}/actions/runs/902",
                "html_url": f"https://github.com/{REPOSITORY}/actions/runs/902"}
        invalid = [None, {}, [], {"workflow_run_id": True}, *[
            {**good, "workflow_run_id": value} for value in ("902", 0, -1, False)], *[
            {**good, key: value} for key, value in (
                ("run_url", good["run_url"] + "?x=1"), ("run_url", good["run_url"].replace(REPOSITORY, "overte-org/overte")),
                ("html_url", good["html_url"] + "/"), ("html_url", None))]]
        for reply in invalid:
            with self.subTest(reply=reply), self.assertRaises(gate.GateError):
                self.dispatch([], reply=reply)
            self.assert_dispatch_binding("reuse")
            self.outputs.assert_not_called()
            self.assertFalse(any("/actions/runs/" in call.args[0] for call in self.api.json.call_args_list))

    def test_foreign_run_attempt_source_workflow_or_native_app_fails_closed(self):
        cases = [("/actions/runs/902", key, value) for key, value in (
            ("id", True), ("workflow_id", 12), ("event", "pull_request_target"),
            ("head_sha", HEAD), ("head_branch", "apple-main"), ("run_attempt", 2),
            ("display_title", "Sync validation gate-700-attempt-1"),
            ("path", ".github/workflows/other.yml"), ("check_suite_id", True), ("status", []),
            ("repository", {"id": 9, "full_name": REPOSITORY}),
            ("head_repository", {"id": REPOSITORY_ID, "full_name": "overte-org/overte"}))]
        cases += [("/actions/runs/902/attempts/1", "run_attempt", 2),
                  ("/check-suites/904", "app", {"id": 57789}),
                  ("/check-suites/904", "head_sha", HEAD),
                  ("/check-suites/904", "repository", {"id": 9, "full_name": REPOSITORY})]
        for suffix, key, value in cases:
            def mutate(endpoint, document):
                if endpoint.endswith(suffix):
                    document[key] = value
                return document
            with self.subTest(suffix=suffix, key=key), self.assertRaises(gate.GateError):
                self.dispatch([self.run_document()], mutate=mutate)
            self.outputs.assert_not_called()
            self.assert_dispatch_binding("reuse")

    def test_missing_individual_run_or_changed_suite_never_uses_list_fallback(self):
        for absent in (None, []):
            def missing(endpoint, document):
                return absent if endpoint.endswith("/actions/runs/902") else document
            with self.subTest(absent=absent), self.assertRaises(gate.GateError):
                self.dispatch([self.run_document()], mutate=missing)
            self.assert_dispatch_binding("reuse")
            self.outputs.assert_not_called()
        changed = self.run_document()
        changed["check_suite_id"] = 905
        with self.assertRaisesRegex(gate.GateError, "identity changed"):
            self.dispatch([self.run_document(status="in_progress", conclusion=None), changed])
        self.assert_dispatch_binding("reuse")
        self.outputs.assert_not_called()

    def test_changed_default_source_or_registration_rejects_before_dispatch_or_output(self):
        for suffix, key, value in (("/branches/main", "commit", {"sha": HEAD}),
                                   ("/actions/workflows/sync-validation.yml", "id", 9)):
            def mutate(endpoint, document):
                if endpoint.endswith(suffix):
                    document[key] = value
                return document
            with self.subTest(suffix=suffix), self.assertRaises(gate.GateError):
                self.dispatch([], mutate=mutate)
            self.assertFalse(any(call.kwargs.get("method") == "POST" for call in self.api.json.call_args_list))
            self.outputs.assert_not_called()
        branches = [0]
        def changed(endpoint, document):
            if endpoint.endswith("/branches/main"):
                branches[0] += 1
                if branches[0] == 2:
                    document["commit"]["sha"] = HEAD
            return document
        with self.assertRaises(gate.GateError):
            self.dispatch([self.run_document()], mutate=changed)
        self.outputs.assert_not_called()
        self.assert_dispatch_binding("reuse")

    def test_api_error_never_repeats_post_or_uses_an_old_success(self):
        def failed(endpoint, document):
            if endpoint.endswith("/dispatches"):
                raise gate.GateError("synthetic uncertain POST failure")
            return document
        with self.assertRaisesRegex(gate.GateError, "uncertain"):
            self.dispatch([], mutate=failed)
        self.assert_dispatch_binding("reuse")
        self.outputs.assert_not_called()


class DispatchTransportContracts(unittest.TestCase):
    def test_dispatch_uses_fixed_version_and_real_boolean_without_changing_string_inputs(self):
        endpoint = f"repos/{REPOSITORY}/actions/workflows/sync-validation.yml/dispatches"
        with mock.patch.object(gate.subprocess, "run", return_value=SimpleNamespace(stdout='{"workflow_run_id":902}')) as run:
            self.assertEqual(gate.GitHubApi().json(endpoint, method="POST", fields={
                "ref": "main", "inputs[correlation]": "gate-700-attempt-2"}, dispatch_details=True),
                {"workflow_run_id": 902})
        self.assertEqual(run.call_args.args[0], ["gh", "api", "--method", "POST", endpoint,
            "-H", "X-GitHub-Api-Version: 2022-11-28", "-F", "return_run_details=true",
            "-f", "ref=main", "-f", "inputs[correlation]=gate-700-attempt-2"])
        with mock.patch.object(gate.subprocess, "run", return_value=SimpleNamespace(stdout="{}")) as run:
            gate.GitHubApi().json("repos/" + REPOSITORY, method="PATCH", fields={"value": "true"})
        self.assertEqual(run.call_args.args[0], ["gh", "api", "--method", "PATCH", "repos/" + REPOSITORY,
                                               "-f", "value=true"])

    def test_checkout_source_reads_actual_git_head_without_optional_index_writes(self):
        with mock.patch.object(gate.subprocess, "run", return_value=SimpleNamespace(stdout=PARENT + "\n")) as run:
            self.assertEqual(gate._dispatch_checkout_source(), PARENT)
        self.assertEqual(run.call_args.kwargs["cwd"], gate.ROOT)
        self.assertIn("--no-optional-locks", run.call_args.args[0])
        self.assertIn("--no-replace-objects", run.call_args.args[0])
        self.assertEqual(run.call_args.args[0][-1], "HEAD^{commit}")
        with mock.patch.object(gate.subprocess, "run", return_value=SimpleNamespace(stdout="not-a-commit")):
            with self.assertRaises(gate.GateError):
                gate._dispatch_checkout_source()
        with mock.patch.object(gate.subprocess, "run", side_effect=subprocess.TimeoutExpired("git", 30)):
            with self.assertRaisesRegex(gate.GateError, "unavailable"):
                gate._dispatch_checkout_source()

    def test_run_details_cannot_be_requested_for_another_transport_operation(self):
        for endpoint, method in (("repos/" + REPOSITORY, "POST"),
                (f"repos/{REPOSITORY}/actions/workflows/sync-validation.yml/dispatches", "GET")):
            with self.subTest(endpoint=endpoint, method=method), mock.patch.object(gate.subprocess, "run") as run:
                with self.assertRaises(gate.GateError):
                    gate.GitHubApi().json(endpoint, method=method, dispatch_details=True)
                run.assert_not_called()


class DifferentialCandidateTests(unittest.TestCase):
    """Exercise the CLI with changes obtained from a real Git repository."""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="sync-differential-")
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.root = self.directory / "candidate"
        self.root.mkdir()
        self.git("init", "--quiet")
        self.git("config", "user.name", "Regression Test")
        self.git("config", "user.email", "regression@example.invalid")
        for name, content in {
            "android/phone/.keep": "", "android/common/.keep": "",
            "old.json": '{"value": 1}\n', "old.py": "value = 1\n",
            "docs/old.md": "Documentation\n",
        }.items():
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        self.git("add", ".")
        self.git("commit", "--quiet", "-m", "Initial fixture")
        self.base = self.git("rev-parse", "HEAD").strip()

    def git(self, *arguments):
        return subprocess.run(
            ["git", "-C", str(self.root), *arguments], check=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        ).stdout

    def changes(self):
        self.git("add", "-A")
        self.git("commit", "--quiet", "-m", "Candidate fixture")
        fields = iter(self.git("diff", "--name-status", "-z", "--find-renames", self.base, "HEAD").split("\0")[:-1])
        changes = []
        statuses = {"A": "added", "D": "removed", "M": "modified", "T": "changed"}
        for status in fields:
            if status.startswith("R"):
                previous, filename = next(fields), next(fields)
                changes.append({"filename": filename, "status": "renamed", "previous_filename": previous})
            else:
                changes.append({"filename": next(fields), "status": statuses[status]})
        return changes

    def run_candidate(self, changes, *, profile="android-phone", legacy=False, raw=False):
        manifest = self.directory / "changes.json"
        if legacy:
            source = "".join(change["filename"] + "\n" for change in changes)
        else:
            source = changes if raw else json.dumps(changes)
        manifest.write_text(source, encoding="utf-8")
        return subprocess.run(
            [sys.executable, str(HERE / "differential.py"), "--candidate", str(self.root),
             "--profile", profile, "--changed-paths" if legacy else "--changed-files", str(manifest)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )

    def assert_failure(self, result, message):
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn(message, result.stderr)
        self.assertNotIn("PASS", result.stdout)

    def test_git_deleted_json_and_python_skip_content_checks(self):
        self.git("rm", "old.json", "old.py")
        changes = self.changes()
        self.assertEqual({item["status"] for item in changes}, {"removed"})
        result = self.run_candidate(changes)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("paths=2 PASS", result.stdout)

    def test_legacy_filenames_cannot_authorize_a_missing_file(self):
        self.git("rm", "old.py")
        self.assert_failure(self.run_candidate(self.changes(), legacy=True), "changed candidate path is missing")

    def test_added_and_modified_files_must_be_present(self):
        (self.root / "old.json").write_text('{"value": 2}\n', encoding="utf-8")
        (self.root / "new.py").write_text("value = 2\n", encoding="utf-8")
        changes = self.changes()
        self.assertEqual({item["status"] for item in changes}, {"added", "modified"})
        for change in changes:
            path = self.root / change["filename"]
            content = path.read_bytes()
            path.unlink()
            with self.subTest(status=change["status"]):
                self.assert_failure(self.run_candidate(changes), "changed candidate path is missing")
            path.write_bytes(content)
        for legacy in (False, True):
            with self.subTest(legacy=legacy):
                result = self.run_candidate(changes, legacy=legacy)
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_removed_file_must_actually_be_absent(self):
        self.git("rm", "old.json")
        changes = self.changes()
        (self.root / "old.json").write_text("{}", encoding="utf-8")
        self.assert_failure(self.run_candidate(changes), "removed candidate path is still present")

    def test_required_root_removal_still_fails(self):
        self.git("rm", "-r", "android/common")
        self.assert_failure(self.run_candidate(self.changes()), "required candidate path is missing: android/common")

    def test_malformed_current_json_still_fails(self):
        (self.root / "old.json").write_text('{"broken": }', encoding="utf-8")
        self.assert_failure(self.run_candidate(self.changes()), "differential error:")

    def test_malformed_current_python_still_fails(self):
        (self.root / "old.py").write_text("def broken(\n", encoding="utf-8")
        self.assert_failure(self.run_candidate(self.changes()), "py_compile")

    def test_current_conflict_markers_still_fail(self):
        (self.root / "docs/old.md").write_text("<<<<<<< HEAD\nconflict\n=======\nother\n>>>>>>> branch\n", encoding="utf-8")
        self.assert_failure(self.run_candidate(self.changes(), profile="documentation"), "unresolved merge marker")

    def test_git_rename_checks_the_destination(self):
        self.git("mv", "old.py", "renamed.py")
        changes = self.changes()
        self.assertEqual(changes, [{"filename": "renamed.py", "status": "renamed", "previous_filename": "old.py"}])
        result = self.run_candidate(changes)
        self.assertEqual(result.returncode, 0, result.stderr)
        (self.root / "renamed.py").write_text("def broken(\n", encoding="utf-8")
        self.assert_failure(self.run_candidate(changes), "py_compile")
        (self.root / "renamed.py").unlink()
        self.assert_failure(self.run_candidate(changes), "changed candidate path is missing")

    def test_code_renamed_to_markdown_cannot_use_documentation_profile(self):
        self.git("mv", "old.py", "docs/code.md")
        self.assert_failure(self.run_candidate(self.changes(), profile="documentation"), "non-documentation change")

    def test_documentation_deletion_is_valid(self):
        self.git("rm", "docs/old.md")
        result = self.run_candidate(self.changes(), profile="documentation")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_removed_paths_cannot_hide_symlinks_or_traversal(self):
        self.git("rm", "old.py")
        changes = self.changes()
        (self.root / "old.py").symlink_to(self.directory / "absent.py")
        self.assert_failure(self.run_candidate(changes), "symbolic link")
        (self.root / "linked").symlink_to(self.directory, target_is_directory=True)
        for filename, message in (
            ("linked/absent.py", "symbolic link"),
            ("../absent.py", "unsafe changed path"),
            (str(self.directory / "absent.py"), "unsafe changed path"),
        ):
            with self.subTest(filename=filename):
                self.assert_failure(self.run_candidate([{"filename": filename, "status": "removed"}]), message)

    def test_rename_source_is_also_checked_for_unsafe_paths(self):
        self.assert_failure(self.run_candidate([{
            "filename": "old.py", "status": "renamed", "previous_filename": "../outside.py",
        }]), "unsafe changed path")

    def test_malformed_change_metadata_fails_closed(self):
        invalid = [
            "{", "{}", "[null]", '[{"filename": "old.py"}]',
            '[{"filename": "old.py", "status": "renamed"}]',
            '[{"filename": "old.py", "status": "removed", "previous_filename": "old.json"}]',
            '[{"filename": "", "status": "removed"}]',
        ]
        for status in ("", "REMOVED", "deleted", "unchanged", "unknown", None, 1, []):
            invalid.append(json.dumps([{"filename": "absent.py", "status": status}]))
        duplicate = {"filename": "old.py", "status": "modified"}
        invalid.append(json.dumps([duplicate, duplicate]))
        for source in invalid:
            with self.subTest(source=source):
                self.assert_failure(self.run_candidate(source, raw=True), "differential error:")


class LargeComparisonTests(unittest.TestCase):
    def documents(self, truncated=False):
        old_tree, new_tree = "a" * 40, "b" * 40
        old = [entry(f"old/{i}") for i in range(301)]
        new = [entry(f"new/{i}") for i in range(301)]
        old.append({"path": "submodule", "mode": "160000", "type": "commit", "sha": BASE})
        new.append({"path": "submodule", "mode": "160000", "type": "commit", "sha": PARENT})
        return {
            f"repos/{REPOSITORY}/compare/{BASE}...{HEAD}": {
                "base_commit": {"sha": BASE}, "merge_base_commit": {"sha": BASE},
                "files": [{"filename": f"new/{i}"} for i in range(300)]},
            f"repos/{REPOSITORY}/git/commits/{BASE}": {"sha": BASE, "tree": {"sha": old_tree}},
            f"repos/{REPOSITORY}/git/commits/{HEAD}": {"sha": HEAD, "tree": {"sha": new_tree}},
            f"repos/{REPOSITORY}/git/trees/{old_tree}?recursive=1": {"sha": old_tree, "truncated": truncated, "tree": old},
            f"repos/{REPOSITORY}/git/trees/{new_tree}?recursive=1": {"sha": new_tree, "truncated": False, "tree": new},
        }

    def test_full_tree_fallback_includes_deletions_and_gitlinks(self):
        base, files = gate.compare_files(MappingApi(self.documents()), REPOSITORY, BASE, HEAD)
        self.assertEqual(base, BASE)
        self.assertEqual(len(files), 603)
        self.assertIn("old/300", files)
        self.assertIn("new/300", files)
        self.assertIn("submodule", files)

    def test_truncated_full_tree_still_fails_closed(self):
        with self.assertRaises(gate.GateError):
            gate.compare_files(MappingApi(self.documents(True)), REPOSITORY, BASE, HEAD)

    def test_retirement_exception_requires_exact_blob_and_actual_deletion(self):
        path = "android/common/conan/prebuilt/obsolete.sha256"
        settings = {"retired_parent_paths": {path: WORKFLOW_BLOB}}
        original = {"mode": "100644", "type": "blob", "sha": WORKFLOW_BLOB}
        for variant in ("valid", "unlisted", "modified", "different-blob", "parent-present", "merge-present"):
            with self.subTest(variant=variant):
                cfg = settings if variant != "unlisted" else {}
                changes = [{"filename": path, "status": "modified" if variant == "modified" else "removed"}]
                before = {path: dict(original, sha=BASE)} if variant == "different-blob" else {path: original}
                parent = {path: original} if variant == "parent-present" else {}
                merged = {path: original} if variant == "merge-present" else {}
                with mock.patch.object(gate, "comparison_entries", side_effect=[before, parent, merged]):
                    if variant == "valid":
                        gate.authorize_retired_paths(MappingApi(), REPOSITORY, cfg, [path], changes, BASE, PARENT, MERGE)
                    else:
                        with self.assertRaises(gate.GateError):
                            gate.authorize_retired_paths(MappingApi(), REPOSITORY, cfg, [path], changes, BASE, PARENT, MERGE)


class EffectiveBaseTopologyTests(unittest.TestCase):
    def setUp(self):
        self.default = subprocess.check_output(['git', '--no-replace-objects', 'rev-parse', 'HEAD'],
                                               cwd=gate.ROOT, text=True).strip()
        side = lambda ref, sha: {'ref': ref, 'sha': sha, 'repo': {'full_name': REPOSITORY, 'id': REPOSITORY_ID}}
        self.pr = {'number': 610, 'state': 'open', 'mergeable': True, 'merge_commit_sha': MERGE,
                   'base': side('android-main', HEAD), 'head': side('main', self.default)}
        self.event = {'number': 610, 'repository': {'full_name': REPOSITORY, 'id': REPOSITORY_ID},
                      'pull_request': deepcopy(self.pr)}
        self.env = {'GIT_CONFIG_COUNT': '1', 'GIT_CONFIG_KEY_0': 'safe.directory',
                    'GIT_CONFIG_VALUE_0': str(gate.ROOT),
                    'GITHUB_ACTIONS': 'true', 'GITHUB_REPOSITORY': REPOSITORY,
                    'GITHUB_REPOSITORY_ID': str(REPOSITORY_ID), 'GITHUB_RUN_ATTEMPT': '1',
                    'GITHUB_EVENT_NAME': 'pull_request_target', 'GITHUB_RUN_ID': '901',
                    'GITHUB_JOB': 'sync-test-reuse', 'GITHUB_REF': 'refs/heads/android-main',
                    'GITHUB_BASE_REF': 'android-main', 'GITHUB_HEAD_REF': 'main',
                    'GITHUB_SHA': BASE, 'GITHUB_WORKFLOW_SHA': BASE,
                    'GITHUB_WORKFLOW_REF': REPOSITORY + '/.github/workflows/sync-test-reuse.yml@refs/heads/android-main'}
        self.docs = {}
        def put(path, value): self.docs['repos/' + REPOSITORY + '/' + path] = value
        put('pulls/610', self.pr)
        put('branches/android-main', {'name': 'android-main', 'protected': True, 'commit': {'sha': BASE}})
        put('branches/main', {'name': 'main', 'protected': True, 'commit': {'sha': self.default}})
        for ref, oid in (('android-main', BASE), ('main', self.default)):
            put('git/ref/heads/' + ref, {'ref': 'refs/heads/' + ref, 'object': {'type': 'commit', 'sha': oid}})
        merge = {'sha': MERGE, 'tree': {'sha': TREE}, 'parents': [{'sha': BASE}, {'sha': self.default}]}
        put('commits/refs/pull/610/merge', merge); put('git/commits/' + MERGE, merge)
        for revision, tree_id in ((BASE, CODEQL_BASE_TREE), (self.default, METADATA_WORKFLOW_BLOB)):
            put('git/commits/' + revision, {'sha': revision, 'tree': {'sha': tree_id}, 'parents': []})
        recipes = []
        for path in ('.github/workflows/sync-test-reuse.yml', '.github/workflows/sync-validation.yml', '.github/workflows/codeql.yml'):
            oid = subprocess.check_output(['git', 'rev-parse', self.default + ':' + path], cwd=gate.ROOT, text=True).strip()
            recipes.append(entry(path, oid))
        companion = '.github/workflows/pr-metadata-context.yml'
        row = subprocess.check_output(['git', 'ls-tree', self.default, '--', companion],
                                      cwd=gate.ROOT).split()
        if row:
            self.assertEqual(row[:2], [b'100644', b'blob'])
            self.assertEqual(len(row), 4)
            self.assertEqual(row[3].decode(), companion)
            recipes.append(entry(companion, row[2].decode()))
        for tree_id, doc_sha in ((CODEQL_BASE_TREE, BASE), (TREE, HEAD), (METADATA_WORKFLOW_BLOB, BASE)):
            put('git/trees/' + tree_id + '?recursive=1', {'sha': tree_id, 'truncated': False,
                'tree': [*deepcopy(recipes), entry('docs/change.md', doc_sha)]})
        put('compare/' + HEAD + '...' + BASE + '?per_page=1', {'status': 'ahead',
            'base_commit': {'sha': HEAD}, 'merge_base_commit': {'sha': HEAD}, 'ahead_by': 1, 'behind_by': 0,
            'total_commits': 1, 'commits': [{'sha': BASE}], 'files': []})
        repo = self.event['repository']
        for identifier, workflow, path, kind, source, suite, started in (
                (901, 350930894, '.github/workflows/sync-test-reuse.yml', 'pull_request_target', self.default, 9010, '2026-10-16T00:00:00Z'),
                (902, 350930895, '.github/workflows/sync-validation.yml', 'workflow_dispatch', self.default, 9020, '2026-10-16T00:00:01Z')):
            run = {'id': identifier, 'workflow_id': workflow, 'path': path, 'event': kind,
                   'head_sha': source, 'head_branch': 'main', 'run_attempt': 1, 'status': 'in_progress', 'conclusion': None,
                   'check_suite_id': suite, 'run_started_at': started, 'repository': repo, 'head_repository': repo,
                   'pull_requests': [{'number': 610, 'base': self.pr['base'], 'head': self.pr['head']}],
                   'display_title': 'Sync validation gate-901-attempt-1' if identifier == 902 else 'Sync test reuse for PR 610'}
            put(f'actions/runs/{identifier}', run); put(f'actions/runs/{identifier}/attempts/1', deepcopy(run))
            put(f'actions/workflows/{workflow}', {'id': workflow, 'path': path, 'state': 'active'})
            put(f'check-suites/{suite}', {'id': suite, 'head_sha': source, 'app': {'id': 15368}, 'repository': repo})
        self.api = MappingApi(self.docs)

    def test_actual_prt_context_uses_native_H_run_but_protected_B_workflow_and_complete_delta(self):
        with mock.patch.dict('os.environ', self.env, clear=True):
            context = gate.effective_pr_context(self.event, self.api)
            self.assertEqual(context.planning(), {'base': BASE, 'head': self.default, 'candidate': MERGE, 'event_base': HEAD})
            with mock.patch.object(gate, 'compare_merge_base', return_value=HEAD), \
                 mock.patch.object(gate, 'compare_files', return_value=(HEAD, {'docs/change.md'})), \
                 mock.patch.object(gate, 'paginate_pull_files', side_effect=AssertionError('capped PR files are not authority')):
                request = gate.classify_event(self.event, config(), self.api, pr_context=context)
            self.assertEqual(request.base_sha, BASE)
            self.assertEqual(request.event_base_sha, HEAD)
            self.assertEqual(request.changed_paths, ('docs/change.md',))
            self.assertEqual(request.profile, 'documentation')
            self.assertTrue(gate.validate_required_codeql_workflow(self.event, self.api, pr_context=context))
            self.docs[f'repos/{REPOSITORY}/git/trees/{TREE}?recursive=1']['tree'][-1]['mode'] = '100755'
            with mock.patch.object(gate, 'compare_merge_base', return_value=HEAD), \
                 mock.patch.object(gate, 'compare_files', return_value=(HEAD, {'docs/change.md'})):
                self.assertEqual(gate.classify_event(self.event, config(), self.api, pr_context=context).profile,
                                 'android-family')
        self.assertEqual(self.event['pull_request']['base']['sha'], HEAD)

    def test_manual_validation_authenticates_original_gate_and_rechecks_source_without_event_rewrite(self):
        env = {**self.env, 'GITHUB_EVENT_NAME': 'workflow_dispatch', 'GITHUB_RUN_ID': '902', 'GITHUB_JOB': 'validate',
               'GITHUB_REF': 'refs/heads/main', 'GITHUB_SHA': self.default, 'GITHUB_WORKFLOW_SHA': self.default,
               'GITHUB_WORKFLOW_REF': REPOSITORY + '/.github/workflows/sync-validation.yml@refs/heads/main'}
        with mock.patch.dict('os.environ', env, clear=True):
            context = gate.effective_pr_context(self.event, self.api)
            request = gate.SyncRequest(REPOSITORY, REPOSITORY_ID, 610, 'android-main', BASE, 'main', self.default,
                REPOSITORY_ID, MERGE, 'direct', 'main', self.default, 'android', ('docs/change.md',), ('docs/change.md',),
                event_base_sha=HEAD)
            self.assertEqual(gate.recheck_effective_request(self.api, request), context)
            self.docs[f'repos/{REPOSITORY}/git/ref/heads/android-main']['object']['sha'] = PARENT
            with self.assertRaises(gate.GateError): gate.recheck_effective_request(self.api, request)

    def test_current_event_and_older_API_snapshot_need_the_same_authenticated_native_context(self):
        self.event['pull_request']['base']['sha'] = BASE
        with mock.patch.dict('os.environ', self.env, clear=True):
            context = gate.effective_pr_context(self.event, self.api)
            self.assertEqual(context.event_base, BASE)
            self.assertEqual(context.base, BASE)
            self.assertTrue(gate.validate_required_codeql_workflow(self.event, self.api))
            with mock.patch.object(gate, 'compare_merge_base', return_value=HEAD), \
                 mock.patch.object(gate, 'compare_files', return_value=(HEAD, {'docs/change.md'})), \
                 mock.patch.object(gate, 'paginate_pull_files', side_effect=AssertionError('complete B/M inventory required')):
                request = gate.classify_event(self.event, config(), self.api, pr_context=context)
            self.assertEqual(request.event_base_sha, BASE)
            self.assertEqual(request.changed_paths, ('docs/change.md',))
            self.pr['base']['sha'] = BASE
            self.assertIsNone(gate.effective_pr_context(self.event, self.api))
        self.pr['base']['sha'] = HEAD
        with mock.patch.dict('os.environ', {}, clear=True), self.assertRaises(gate.GateError):
            gate.effective_pr_context(self.event, self.api)

    def test_authenticated_candidate_with_missing_optional_merge_SHA_never_sleeps(self):
        self.pr.pop('merge_commit_sha')
        with mock.patch.dict('os.environ', self.env, clear=True):
            context = gate.effective_pr_context(self.event, self.api)
            with mock.patch.object(gate, 'compare_merge_base', return_value=HEAD), \
                 mock.patch.object(gate, 'compare_files', return_value=(HEAD, {'docs/change.md'})), \
                 mock.patch.object(gate.time, 'sleep', side_effect=AssertionError('authenticated M needs no optional API field')) as sleep:
                request = gate.classify_event(self.event, config(), self.api, pr_context=context)
            self.assertEqual(request.merge_sha, MERGE)
            self.assertEqual(request.base_sha, BASE)
            sleep.assert_not_called()

    def test_authenticated_repair_snapshots_keep_the_original_full_privileged_attestation(self):
        fixture = ProductRepairContracts()
        event, settings, api = fixture.fixture()
        snapshot = 'e' * 40
        current = api.documents[f'repos/{REPOSITORY}/pulls/610']
        event['pull_request']['base']['sha'] = snapshot
        current['base']['sha'] = snapshot
        compare = f'repos/{REPOSITORY}/compare/{snapshot}...{BASE}?per_page=1'
        api.documents[compare] = {'status': 'ahead', 'base_commit': {'sha': snapshot},
            'merge_base_commit': {'sha': snapshot}, 'ahead_by': 1, 'behind_by': 0,
            'total_commits': 1, 'commits': [{'sha': BASE}], 'files': []}
        context = gate.EffectivePRContext(BASE, HEAD, MERGE, snapshot)
        arguments = (api, REPOSITORY, REPOSITORY_ID, event['pull_request'], current,
                     'android-vr-pico', 'android-vr', current['head']['ref'], BASE, PARENT, HEAD, MERGE)
        self.assertIsNone(gate.attest_product_repair(*arguments, pr_context=context))
        with self.assertRaises(gate.GateError): gate.attest_product_repair(*arguments)
        api.documents[compare]['status'] = 'diverged'
        with self.assertRaises(gate.GateError): gate.attest_product_repair(*arguments, pr_context=context)
        api.documents[compare]['status'] = 'ahead'
        api.documents[f'repos/{REPOSITORY}/git/commits/{HEAD}']['parents'][0]['sha'] = snapshot
        with self.assertRaises(gate.GateError): gate.attest_product_repair(*arguments, pr_context=context)

    def test_wrong_native_role_missing_association_app_or_ancestry_never_authorizes_stale_base(self):
        for mutation in ('offline', 'source', 'run-head', 'app', 'association', 'attempt-association',
                         'attempt-repository', 'ancestry', 'parents'):
            with self.subTest(mutation=mutation):
                old = deepcopy(self.docs); env = dict(self.env)
                if mutation == 'offline': env = {}
                if mutation == 'source': env['GITHUB_SHA'] = MERGE
                if mutation == 'run-head':
                    for path in ('actions/runs/901', 'actions/runs/901/attempts/1'):
                        self.docs[f'repos/{REPOSITORY}/' + path]['head_sha'] = BASE
                if mutation == 'app': self.docs[f'repos/{REPOSITORY}/check-suites/9010']['app']['id'] = 7
                if mutation == 'association': self.docs[f'repos/{REPOSITORY}/actions/runs/901']['pull_requests'] = []
                if mutation == 'attempt-association': self.docs[f'repos/{REPOSITORY}/actions/runs/901/attempts/1']['pull_requests'] = []
                if mutation == 'attempt-repository': self.docs[f'repos/{REPOSITORY}/actions/runs/901/attempts/1']['repository']['id'] = 7
                if mutation == 'ancestry': self.docs[f'repos/{REPOSITORY}/compare/{HEAD}...{BASE}?per_page=1']['status'] = 'diverged'
                if mutation == 'parents': self.docs[f'repos/{REPOSITORY}/commits/refs/pull/610/merge']['parents'][0]['sha'] = PARENT
                with mock.patch.dict('os.environ', env, clear=True):
                    with self.assertRaises(gate.GateError): gate.effective_pr_context(self.event, self.api)
                self.docs.clear(); self.docs.update(old)

    def test_complete_inventory_keeps_modes_additions_and_deletions_and_refuses_truncation(self):
        before = self.docs[f'repos/{REPOSITORY}/git/trees/{CODEQL_BASE_TREE}?recursive=1']['tree']
        after = self.docs[f'repos/{REPOSITORY}/git/trees/{TREE}?recursive=1']['tree']
        before.append(entry('removed.py')); after.append(dict(entry('new.py'), mode='100755'))
        self.assertEqual(gate.immutable_change_documents(self.api, REPOSITORY, BASE, MERGE), [
            {'filename': 'docs/change.md', 'status': 'modified'}, {'filename': 'new.py', 'status': 'added'},
            {'filename': 'removed.py', 'status': 'removed'}])
        self.docs[f'repos/{REPOSITORY}/git/trees/{TREE}?recursive=1']['truncated'] = True
        with self.assertRaises(gate.GateError): gate.immutable_change_documents(self.api, REPOSITORY, BASE, MERGE)


class RequiredCodeQLInvocationTests(unittest.TestCase):
    """Actual trusted gate hook and immutable API tree; no caller job facts."""
    def setUp(self):
        # Native PRT/manual roles have separate explicit environment fixtures.
        environment = mock.patch.dict('os.environ', {'GITHUB_ACTIONS': 'false'})
        self.addCleanup(environment.stop)
        environment.start()
        temporary = tempfile.TemporaryDirectory(prefix='overte-required-codeql-fixture-')
        self.addCleanup(temporary.cleanup)
        self.policy_root = Path(temporary.name)
        self.policy = {'schema': 1, 'repository': REPOSITORY, 'repository_id': REPOSITORY_ID,
                       'codeql_results_required_branches': ['main']}
        (self.policy_root / '.github').mkdir()
        source = self.policy_root / 'tools/repository-checks/codeql.py'
        source.parent.mkdir(parents=True)
        source.write_text(f"_RESULTS_WORKFLOW = '{WORKFLOW_BLOB}'\n_SELECTIVE_WORKFLOW = '{PARENT}'\n"
                          f"_RETARGET_RESULTS_WORKFLOW = '{RETARGET_WORKFLOW_BLOB}'\n"
                          f"_PINNED_RESULTS_WORKFLOW = '{PINNED_WORKFLOW_BLOB}'\n"
                          f"_METADATA_RESULTS_WORKFLOW = '{METADATA_WORKFLOW_BLOB}'\n"
                          f"_METADATA_SOURCE_WORKFLOW = '{METADATA_SOURCE_BLOB}'\n"
                          "_SCHEDULING_RESULTS_WORKFLOW = '" + "e9aaaed9693efc5ffb4701697ac2a4d51f5f5ba1" + "'\n"
                          "_SCHEDULING_SOURCE_WORKFLOW = '" + "b76ade9fd7a76da21bf2cb2161deae7a262163e8" + "'\n"
                          "def result_workflow_blobs():\n"
                          "    return (_RESULTS_WORKFLOW, _RETARGET_RESULTS_WORKFLOW, "
                          "_PINNED_RESULTS_WORKFLOW, _METADATA_RESULTS_WORKFLOW, _SCHEDULING_RESULTS_WORKFLOW)\n"
                          "def result_workflow_sources():\n"
                          "    return ((_RESULTS_WORKFLOW, None), (_RETARGET_RESULTS_WORKFLOW, None), "
                          "(_PINNED_RESULTS_WORKFLOW, None), (_METADATA_RESULTS_WORKFLOW, _METADATA_SOURCE_WORKFLOW), "
                          "(_SCHEDULING_RESULTS_WORKFLOW, _SCHEDULING_SOURCE_WORKFLOW))\n")
        self.write_policy()
        side = lambda ref, sha: {'ref': ref, 'sha': sha, 'repo': {'full_name': REPOSITORY, 'id': REPOSITORY_ID}}
        self.pr = {'number': 610, 'state': 'open', 'mergeable': True, 'merge_commit_sha': MERGE,
                   'base': side('main', BASE), 'head': side('fix/main/ordinary', HEAD)}
        self.event = {'number': 610, 'repository': {'full_name': REPOSITORY, 'id': REPOSITORY_ID},
                      'pull_request': deepcopy(self.pr)}
        self.documents = {
            f'repos/{REPOSITORY}/pulls/610': self.pr,
            f'repos/{REPOSITORY}/git/ref/heads/main': {'ref': 'refs/heads/main', 'object': {'type': 'commit', 'sha': BASE}},
            f'repos/{REPOSITORY}/git/ref/heads/fix%2Fmain%2Fordinary': {
                'ref': 'refs/heads/fix/main/ordinary', 'object': {'type': 'commit', 'sha': HEAD}},
            f'repos/{REPOSITORY}/git/commits/{MERGE}': {'sha': MERGE, 'tree': {'sha': TREE},
                                                     'parents': [{'sha': BASE}, {'sha': HEAD}]},
            f'repos/{REPOSITORY}/git/trees/{TREE}?recursive=1': {
                'sha': TREE, 'truncated': False, 'tree': [entry('.github/workflows/codeql.yml')]},
            f'repos/{REPOSITORY}/git/commits/{BASE}': {'sha': BASE, 'tree': {'sha': CODEQL_BASE_TREE},
                                                    'parents': []},
            f'repos/{REPOSITORY}/git/trees/{CODEQL_BASE_TREE}?recursive=1': {
                'sha': CODEQL_BASE_TREE, 'truncated': False, 'tree': [entry('.github/workflows/codeql.yml')]},
        }
        self.api = MappingApi(self.documents)

    def write_policy(self):
        (self.policy_root / '.github/repository-checks.json').write_text(json.dumps(self.policy))

    def validate(self):
        return gate.validate_required_codeql_workflow(self.event, self.api, self.policy_root)

    def test_default_disabled_or_inactive_child_adds_no_api_or_event_requirements(self):
        for targets, event in (([], {}), (['main'], {'pull_request': {'base': {'ref': 'apple-ios'}}})):
            self.policy['codeql_results_required_branches'] = targets
            self.write_policy()
            with mock.patch.object(self.api, 'json', side_effect=AssertionError('inactive must not read API')):
                self.assertFalse(gate.validate_required_codeql_workflow(event, self.api, self.policy_root))
        del self.policy['codeql_results_required_branches']
        self.write_policy()
        (self.policy_root / 'tools/repository-checks/codeql.py').unlink()
        self.assertFalse(gate.validate_required_codeql_workflow({}, self.api, self.policy_root))

    def test_legacy_inspection_uses_explicit_inactive_policy_even_when_default_is_active(self):
        validator = gate.validate_required_codeql_workflow
        with trusted_codeql_policy(['main']):
            self.assertIs(gate.validate_required_codeql_workflow, validator)
            with self.assertRaises(gate.GateError):
                validator({}, MappingApi())
            calls, result = InspectionContracts().inspect_request(
                request(), gate.EvidenceError('missing parent evidence'))
            self.assertEqual(calls, 1)
            self.assertEqual(result['mode'], 'fallback')
            self.assertIs(gate.validate_required_codeql_workflow, validator)
            with self.assertRaises(gate.GateError):
                validator({}, MappingApi())

    def test_current_exact_approved_candidate_is_valid_without_job_or_candidate_policy_facts(self):
        calls = []
        original = self.api.json
        def read(endpoint):
            calls.append(endpoint)
            return deepcopy(original(endpoint))
        with mock.patch.object(self.api, 'json', side_effect=read):
            self.assertTrue(self.validate())
        self.assertEqual(calls.count(f'repos/{REPOSITORY}/pulls/610'), 2)
        self.assertFalse(any('/actions/' in call or '/git/ref/pull/' in call for call in calls))
        self.assertFalse(any('/contents/' in call for call in calls), 'candidate activation policy is never read')

    def test_each_permanent_target_is_enabled_only_by_its_trusted_policy(self):
        for target in ('main', 'apple-main', 'apple-ios', 'android-main', 'android-phone', 'android-vr', 'android-vr-pico'):
            self.policy['codeql_results_required_branches'] = [target]
            self.write_policy()
            self.pr['base']['ref'] = target
            self.event['pull_request']['base']['ref'] = target
            self.documents[f'repos/{REPOSITORY}/git/ref/heads/{target}'] = {
                'ref': 'refs/heads/' + target, 'object': {'type': 'commit', 'sha': BASE}}
            with self.subTest(target=target): self.assertTrue(self.validate())

    def test_protected_policy_pins_real_codeql_on_every_permanent_target(self):
        self.policy = json.loads((HERE.parents[1] / '.github/repository-checks.json').read_text())
        targets = ['main', 'apple-main', 'apple-ios', 'android-main',
                   'android-phone', 'android-vr', 'android-vr-pico']
        self.assertEqual(self.policy['codeql_results_required_branches'], targets)
        self.write_policy()
        current = self.documents[f'repos/{REPOSITORY}/git/trees/{TREE}?recursive=1']
        previous = self.documents[f'repos/{REPOSITORY}/git/trees/{CODEQL_BASE_TREE}?recursive=1']
        previous['tree'] = [entry('.github/workflows/codeql.yml', PINNED_WORKFLOW_BLOB)]
        for target in targets:
            self.pr['base']['ref'] = target
            self.event['pull_request']['base']['ref'] = target
            self.documents[f'repos/{REPOSITORY}/git/ref/heads/{target}'] = {
                'ref': 'refs/heads/' + target, 'object': {'type': 'commit', 'sha': BASE}}
            current['tree'] = [entry('.github/workflows/codeql.yml', PINNED_WORKFLOW_BLOB)]
            with self.subTest(target=target, recipe='reviewed'):
                self.assertTrue(self.validate())
            for variant in ('fabricated', 'missing', 'executable', 'symlink', 'gitlink'):
                item = entry('.github/workflows/codeql.yml', PINNED_WORKFLOW_BLOB)
                if variant == 'fabricated': item['sha'] = HEAD
                if variant == 'executable': item['mode'] = '100755'
                if variant == 'symlink': item['mode'] = '120000'
                if variant == 'gitlink': item.update(mode='160000', type='commit')
                current['tree'] = [] if variant == 'missing' else [item]
                self.event['jobs'] = {'codeql-security-results': 'success'}
                self.event['codeql_results_required_branches'] = []
                with self.subTest(target=target, recipe=variant), self.assertRaises(gate.GateError):
                    self.validate()

    def test_exact_retarget_generation_can_deploy_but_cannot_be_reverted(self):
        current = self.documents[f'repos/{REPOSITORY}/git/trees/{TREE}?recursive=1']['tree'][0]
        previous = self.documents[f'repos/{REPOSITORY}/git/trees/{CODEQL_BASE_TREE}?recursive=1']['tree'][0]
        current['sha'] = RETARGET_WORKFLOW_BLOB
        self.assertTrue(self.validate())
        previous['sha'] = RETARGET_WORKFLOW_BLOB
        self.assertTrue(self.validate())
        current['sha'] = WORKFLOW_BLOB
        with self.assertRaisesRegex(gate.GateError, 'cannot be reverted'):
            self.validate()
        previous['sha'] = WORKFLOW_BLOB
        self.assertTrue(self.validate())

    def test_retarget_rollback_proof_requires_complete_authenticated_base_tree(self):
        endpoint = f'repos/{REPOSITORY}/git/trees/{CODEQL_BASE_TREE}?recursive=1'
        original = self.documents[endpoint]
        self.documents[endpoint] = gate.GateError('authenticated base tree unavailable')
        with self.assertRaises(gate.GateError): self.validate()
        self.documents[endpoint] = original
        original['truncated'] = True
        with self.assertRaises(gate.GateError): self.validate()
        original['truncated'] = False
        original['sha'] = TREE
        with self.assertRaises(gate.GateError): self.validate()
        original['sha'] = CODEQL_BASE_TREE
        original['tree'] = []
        with self.assertRaises(gate.GateError): self.validate()
        for mode, kind in (('100755', 'blob'), ('120000', 'blob'), ('160000', 'commit')):
            original['tree'] = [{**entry('.github/workflows/codeql.yml'), 'mode': mode, 'type': kind}]
            with self.subTest(mode=mode), self.assertRaises(gate.GateError): self.validate()

    def test_pinned_workflow_admits_only_forward_exact_result_generations(self):
        current = self.documents[f'repos/{REPOSITORY}/git/trees/{TREE}?recursive=1']['tree'][0]
        previous = self.documents[f'repos/{REPOSITORY}/git/trees/{CODEQL_BASE_TREE}?recursive=1']['tree'][0]
        self.documents[f'repos/{REPOSITORY}/git/trees/{TREE}?recursive=1']['tree'].append(
            entry('.github/workflows/pr-metadata-context.yml', METADATA_SOURCE_BLOB))
        generations = (WORKFLOW_BLOB, RETARGET_WORKFLOW_BLOB, PINNED_WORKFLOW_BLOB, METADATA_WORKFLOW_BLOB)
        for old_index, old in enumerate(generations):
            for new_index, new in enumerate(generations):
                previous['sha'], current['sha'] = old, new
                with self.subTest(old=old, new=new):
                    if new_index < old_index:
                        with self.assertRaisesRegex(gate.GateError, 'cannot be reverted'): self.validate()
                    else:
                        self.assertTrue(self.validate())
        previous['sha'] = current['sha'] = PINNED_WORKFLOW_BLOB
        for mode, kind in (('100755', 'blob'), ('120000', 'blob'), ('160000', 'commit')):
            current.update(mode=mode, type=kind)
            with self.subTest(mode=mode), self.assertRaises(gate.GateError): self.validate()

    def test_metadata_successor_requires_exact_ordinary_relative_source(self):
        tree = self.documents[f'repos/{REPOSITORY}/git/trees/{TREE}?recursive=1']['tree']
        tree[0]['sha'] = METADATA_WORKFLOW_BLOB
        with self.assertRaisesRegex(gate.GateError, 'metadata source workflow'):
            self.validate()
        helper = entry('.github/workflows/pr-metadata-context.yml', METADATA_SOURCE_BLOB)
        tree.append(helper)
        self.assertTrue(self.validate())
        for changes in ({'sha': HEAD}, {'mode': '100755'}, {'mode': '120000'},
                        {'mode': '160000', 'type': 'commit'}):
            tree[1] = {**helper, **changes}
            with self.subTest(changes=changes), self.assertRaisesRegex(gate.GateError, 'metadata source workflow'):
                self.validate()
        tree[1] = helper
        self.assertTrue(self.validate())

    def test_fifth_caller_binds_its_own_helper_and_preserves_the_fourth_pair(self):
        current = self.documents[f'repos/{REPOSITORY}/git/trees/{TREE}?recursive=1']['tree']
        current[:] = [entry('.github/workflows/codeql.yml', 'e9aaaed9693efc5ffb4701697ac2a4d51f5f5ba1'),
            entry('.github/workflows/pr-metadata-context.yml', 'b76ade9fd7a76da21bf2cb2161deae7a262163e8')]
        self.assertTrue(self.validate())
        current[1]['sha'] = METADATA_SOURCE_BLOB
        with self.assertRaisesRegex(gate.GateError, 'metadata source workflow'): self.validate()
        current[0]['sha'] = METADATA_WORKFLOW_BLOB
        self.assertTrue(self.validate())
        current[1]['sha'] = 'b76ade9fd7a76da21bf2cb2161deae7a262163e8'
        with self.assertRaisesRegex(gate.GateError, 'metadata source workflow'): self.validate()
        current[0]['sha'] = 'e9aaaed9693efc5ffb4701697ac2a4d51f5f5ba1'
        for malformed in ({'mode':'100755'}, {'mode':'120000'}, {'type':'commit','mode':'160000'}):
            current[1].update(malformed)
            with self.subTest(malformed=malformed), self.assertRaises(gate.GateError): self.validate()
            current[1] = entry('.github/workflows/pr-metadata-context.yml', 'b76ade9fd7a76da21bf2cb2161deae7a262163e8')

    def test_trusted_metadata_generation_inventory_must_be_complete_and_ordered(self):
        source = self.policy_root / 'tools/repository-checks/codeql.py'
        original = source.read_text()
        for mutation in (original.replace(METADATA_WORKFLOW_BLOB, WORKFLOW_BLOB),
                         original.replace(METADATA_WORKFLOW_BLOB, '0' * 40),
                         original.replace(METADATA_SOURCE_BLOB, '0' * 40),
                         original.replace('_PINNED_RESULTS_WORKFLOW, _METADATA_RESULTS_WORKFLOW, _SCHEDULING_RESULTS_WORKFLOW)',
                                          '_METADATA_RESULTS_WORKFLOW, _PINNED_RESULTS_WORKFLOW, _SCHEDULING_RESULTS_WORKFLOW)')):
            source.write_text(mutation)
            with self.subTest(mutation=mutation), self.assertRaises(gate.GateError):
                self.validate()
        source.write_text(original)
        self.assertTrue(self.validate())

    def test_old_workflow_fake_named_job_missing_and_nonregular_cannot_pass(self):
        tree = self.documents[f'repos/{REPOSITORY}/git/trees/{TREE}?recursive=1']
        for variant in ('old', 'fabricated', 'missing', 'executable', 'symlink', 'gitlink'):
            item = entry('.github/workflows/codeql.yml')
            if variant == 'old': item['sha'] = PARENT
            if variant == 'fabricated': item['sha'] = HEAD
            if variant == 'executable': item['mode'] = '100755'
            if variant == 'symlink': item['mode'] = '120000'
            if variant == 'gitlink': item.update(mode='160000', type='commit')
            tree['tree'] = [] if variant == 'missing' else [item]
            self.event['jobs'] = {'codeql-security-results': 'success'}
            self.event['codeql_results_required_branches'] = []
            with self.subTest(variant=variant), self.assertRaises(gate.GateError): self.validate()

    def test_untrusted_or_malformed_activation_and_foreign_event_never_authorize(self):
        (self.policy_root / '.github/repository-checks.json').write_text('[]')
        with self.assertRaises(gate.GateError): self.validate()
        for targets in (True, ['main', 'main'], ['topic'], [None]):
            self.policy['codeql_results_required_branches'] = targets
            self.write_policy()
            with self.subTest(targets=targets), self.assertRaises(gate.GateError): self.validate()
        self.policy['codeql_results_required_branches'] = ['main']; self.write_policy()
        for identity in (self.event['repository'], self.event['pull_request']['base']['repo'],
                         self.event['pull_request']['head']['repo']):
            identity['full_name'] = 'overte-org/overte'
            with self.assertRaises(gate.GateError): self.validate()
            identity['full_name'] = REPOSITORY

    def test_foreign_current_pr_changed_heads_refs_closed_or_conflicting_fail(self):
        for target, key, value in ((self.pr['head']['repo'], 'id', 1), (self.pr['base'], 'sha', HEAD),
                                   (self.pr['head'], 'ref', 'different'), (self.pr, 'state', 'closed'),
                                   (self.pr, 'mergeable', False),
                                   (self.documents[f'repos/{REPOSITORY}/git/ref/heads/main']['object'], 'sha', HEAD)):
            old = target[key]; target[key] = value
            with self.subTest(key=key), self.assertRaises(gate.GateError): self.validate()
            target[key] = old
        current_ref = self.documents[f'repos/{REPOSITORY}/git/ref/heads/main']
        current_ref['ref'] = 'refs/heads/foreign'
        with self.assertRaises(gate.GateError): self.validate()

    def test_ordered_parent_and_complete_tree_binding_cannot_be_spoofed(self):
        commit = self.documents[f'repos/{REPOSITORY}/git/commits/{MERGE}']
        commit['parents'].reverse()
        with self.assertRaises(gate.GateError): self.validate()
        commit['parents'].reverse()
        tree = self.documents[f'repos/{REPOSITORY}/git/trees/{TREE}?recursive=1']
        for key, value in (('sha', BASE), ('truncated', True), ('tree', [entry('../codeql.yml')]),
                           ('tree', [entry('.github/workflows/codeql.yml')] * 2)):
            old = tree[key]; tree[key] = value
            with self.subTest(key=key), self.assertRaises(gate.GateError): self.validate()
            tree[key] = old

    def test_merge_computation_wait_is_bounded_and_never_retries_api_failures(self):
        sequence = [dict(self.pr, mergeable=None, merge_commit_sha=None), deepcopy(self.pr), deepcopy(self.pr)]
        original = self.api.json
        def read(endpoint):
            return sequence.pop(0) if endpoint.endswith('/pulls/610') else original(endpoint)
        with mock.patch.object(self.api, 'json', side_effect=read), mock.patch.object(gate.time, 'sleep') as sleep:
            self.assertTrue(self.validate())
            sleep.assert_called_once_with(3)
        self.pr.update(mergeable=None, merge_commit_sha=None)
        with mock.patch.object(gate.time, 'sleep') as sleep, self.assertRaisesRegex(gate.GateError, 'did not complete'):
            self.validate()
        self.assertEqual(sleep.call_count, 5)
        with mock.patch.object(self.api, 'json', side_effect=gate.GateError('API unavailable')), \
                mock.patch.object(gate.time, 'sleep') as sleep, self.assertRaises(gate.GateError):
            self.validate()
        sleep.assert_not_called()

    def test_candidate_and_branch_bookends_reject_changes_after_tree_read(self):
        original = self.api.json
        for mutation in ('candidate', 'branch'):
            count = [0]
            def read(endpoint):
                if endpoint.endswith('/pulls/610'):
                    count[0] += 1
                    if count[0] == 2:
                        if mutation == 'candidate': return dict(self.pr, merge_commit_sha=HEAD)
                        return dict(self.pr, head={**self.pr['head'], 'sha': BASE})
                return original(endpoint)
            with self.subTest(mutation=mutation), mock.patch.object(self.api, 'json', side_effect=read), \
                    self.assertRaises(gate.GateError): self.validate()

    def test_actual_inspect_ordinary_hook_validates_before_classification_or_outputs(self):
        actual = gate.validate_required_codeql_workflow
        source = mock.Mock()
        source.read_text.return_value = json.dumps(self.event)
        def validate(event, api): return actual(event, api, self.policy_root)
        with mock.patch.object(gate, 'GitHubApi', return_value=self.api), \
                mock.patch.object(gate, 'validate_required_codeql_workflow', side_effect=validate) as invoked, \
                mock.patch.object(gate, 'load_config', return_value=config()), \
                mock.patch.object(gate, 'write_outputs') as output:
            self.assertEqual(gate.inspect(SimpleNamespace(config=None, event=source, output=None)), 0)
            invoked.assert_called_once()
            self.assertEqual(output.call_args.args[1], {'classification': 'ordinary', 'mode': 'ordinary'})
        self.documents[f'repos/{REPOSITORY}/git/trees/{TREE}?recursive=1']['tree'][0]['sha'] = PARENT
        with mock.patch.object(gate, 'GitHubApi', return_value=self.api), \
                mock.patch.object(gate, 'validate_required_codeql_workflow', side_effect=validate), \
                mock.patch.object(gate, 'load_config', return_value=config()), \
                mock.patch.object(gate, 'classify_event') as classify, \
                mock.patch.object(gate, 'write_outputs') as output, self.assertRaises(gate.GateError):
            gate.inspect(SimpleNamespace(config=None, event=source, output=None))
        classify.assert_not_called()
        output.assert_not_called()


class NativeParentEvidenceTests(unittest.TestCase):
    """Real schema3/API proof with explicit local source/runtime primitives.

    The tiny receipt fixture is not actual protected-source or hosted-E proof.
    Native jobs, source chains, original artifacts and whole receipt hashes use
    the actual producer Adapter verifier. No execution/environment query occurs.
    """
    @classmethod
    def setUpClass(cls):
        directory = str(HERE.parent / 'test-evidence')
        sys.path.insert(0, directory)
        try:
            spec = importlib.util.spec_from_file_location('sync_native_api_fixtures',
                HERE.parent / 'test-evidence/producer-api-test.py')
            cls.fixtures = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(cls.fixtures)
        finally:
            sys.path.remove(directory)

    def setUp(self):
        self.fixture = self.fixtures.MainConsumerTests()
        self.fixture.generation_name = 'protected-producer-postmerge-original-e-v1'
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.setUp()
        self.controller = self.fixture.module
        self.case = self.fixture.case
        self.case.push.update(status='completed', conclusion='success')
        self.original_run = self.fixture.adapter.capture_integrated(500,
            self.case.plan,self.case.policy,now=self.fixtures.NOW).observations[0].run
        self.child_base = hashlib.sha1(b'native child base').hexdigest()
        self.child_merge = hashlib.sha1(b'native child merge').hexdigest()
        self.child_tree = hashlib.sha1(b'native child tree').hexdigest()
        self.default = self.case.integrated
        self.default_tree = self.case.binding['merge_tree']
        self.local = deepcopy(self.fixture.tree)
        self.candidate = deepcopy(self.fixture.tree)
        self.request = gate.SyncRequest(repository=REPOSITORY, repository_id=REPOSITORY_ID,
            number=42, base='apple-main', base_sha=self.child_base, head='main',
            head_sha=self.case.integrated, head_repository_id=REPOSITORY_ID,
            merge_sha=self.child_merge, parent='main', parent_sha=self.case.integrated,
            profile='apple-family', classification='direct', changed_paths=(), parent_changed_paths=(), repair_paths=())
        self.push_rows = [deepcopy(self.case.push)]
        self.extra_mutation = lambda endpoint, value: value
        outer = self
        class Api:
            def json(self, endpoint):
                A = outer.fixtures.A
                path = endpoint[len(A.PREFIX):].lstrip('/').split('?', 1)[0]
                q = outer.request
                if path == 'pulls/42':
                    value = {'number':42,'state':'open', **{
                        side:{'ref':ref,'sha':sha,'repo':{'id':REPOSITORY_ID,'full_name':REPOSITORY}}
                        for side,ref,sha in (('base',q.base,q.base_sha),('head',q.head,q.head_sha))}}
                elif path == 'commits/refs/pull/42/merge':
                    value = {'sha':q.merge_sha,'commit':{'tree':{'sha':outer.child_tree}},
                        'parents':[{'sha':q.base_sha},{'sha':q.head_sha}]}
                elif path == 'git/commits/'+q.merge_sha:
                    value = {'sha':q.merge_sha,'tree':{'sha':outer.child_tree},
                        'parents':[{'sha':q.base_sha},{'sha':q.head_sha}]}
                elif path == 'git/commits/'+outer.default and outer.default != outer.case.integrated:
                    value = {'sha':outer.default,'tree':{'sha':outer.default_tree},'parents':[]}
                elif path.startswith('branches/'):
                    branch = path[len('branches/'):]
                    sha = q.base_sha if branch == q.base else outer.default if branch == 'main' else q.parent_sha
                    value = {'name':branch,'protected':True,'commit':{'sha':sha}}
                elif path.startswith('git/ref/heads/'):
                    branch=path[len('git/ref/heads/'):]
                    sha = q.base_sha if branch == q.base else outer.default if branch == 'main' else q.parent_sha
                    value = {'ref':'refs/heads/'+branch,'object':{'type':'commit','sha':sha}}
                elif path == 'actions/workflows/350930890/runs':
                    value = {'total_count':len(outer.push_rows),'workflow_runs':deepcopy(outer.push_rows)}
                else:
                    return outer.extra_mutation(endpoint, outer.fixture.api.json(endpoint))
                outer.fixture.api.calls.append(endpoint)
                return outer.extra_mutation(endpoint, deepcopy(value))
            def bytes(self, endpoint): return outer.fixture.api.bytes(endpoint)
            def integrated_pr(self, number): return outer.fixture.api.integrated_pr(number)
            def immutable_blob(self, oid, **kwargs):
                raise AssertionError('full-profile fixture has no immutable data reader')
            def immutable_tree(self, oid):
                tree = outer.candidate if oid == outer.child_tree else outer.local if oid == outer.default_tree else None
                return ({'sha':oid,'truncated':False,'tree':[{'path':name,**entry} for name,entry in tree.items()]}
                    if tree is not None else outer.fixture.api.immutable_tree(oid))
        self.api = Api()
        self.transport = SimpleNamespace(native_producer_api=lambda controller:self.api)
        for item in (mock.patch.object(gate,'_native_parent_controller',return_value=self.controller),
            mock.patch.object(self.controller.execution,'checkout_identity',side_effect=lambda root:(self.default,self.default_tree)),
            mock.patch.object(self.controller.inputs,'full_tree',side_effect=lambda *args:self.local)):
            item.start(); self.addCleanup(item.stop)

    def verify(self):
        return gate.native_parent_evidence(self.transport, config(), self.request, now=self.fixtures.NOW)

    def test_native_whole_proof_keeps_original_m_e_lifetime_and_child_input_comparison(self):
        value = self.verify()
        self.assertIsInstance(value, gate.NativeParentEvidence)
        self.assertEqual(value['original_commit'],self.case.binding['merge_sha'])
        self.assertNotEqual(value['original_commit'],value['parent_commit'])
        self.assertNotEqual(value['original_commit'],self.request.merge_sha)
        self.assertEqual(value['environment'],self.fixture.receipt['environment'])
        self.assertEqual(value['expires_at'],self.case.aggregate['expires_at'])
        self.assertEqual(value['candidate_plan']['reused'],list(self.fixture.registry['suites']))
        self.assertEqual(value['candidate_plan']['required'],[])
        self.assertEqual(value['original_proof']['receipt_sha256'],
            hashlib.sha256(self.fixtures.P.canonical(self.fixture.receipt)).hexdigest())
        self.assertTrue(any('/check-runs/' in endpoint for endpoint in self.fixture.api.calls))
        self.assertTrue(any('/attempts/1/jobs' in endpoint for endpoint in self.fixture.api.calls))
        self.assertFalse(any('/dispatches' in endpoint for endpoint in self.fixture.api.calls))
        self.controller.execution.capture_execution_environment.assert_not_called()
        self.controller.execution.execute.assert_not_called()

    def test_every_exact_direct_edge_retains_actual_original_native_source_and_target_profile(self):
        # Protocol source facts are synthetic, independently selected platform
        # omission is explicit. This does not qualify Android platform owners.
        for child, edge in config()['edges'].items():
            parent=edge['parent']
            self.case.binding['base_ref']=parent
            self.case.push['head_branch']=parent
            self.push_rows=[deepcopy(self.case.push)]
            self.default=self.case.integrated if parent=='main' else hashlib.sha1(b'protected default D').hexdigest()
            self.default_tree=self.case.binding['merge_tree'] if parent=='main' else hashlib.sha1(b'protected default tree').hexdigest()
            for tree in (self.fixture.tree,self.fixture.previous,self.candidate):
                tree['tests/platform-profile.json']=self.controller.source_admission.ordinary(
                    self.controller.source_admission.TARGET_PROFILES[parent])
            self.local=deepcopy(self.fixture.tree)
            self.local['tests/platform-profile.json']=self.controller.source_admission.ordinary(
                self.controller.source_admission.SHARED_PROFILE)
            self.candidate['tests/platform-profile.json']=self.controller.source_admission.ordinary(
                self.controller.source_admission.TARGET_PROFILES[child])
            self.request=replace(self.request,base=child,head=parent,parent=parent,profile=edge['differential'])
            # Re-sign exact synthetic source fingerprints; native API publisher
            # is regenerated, never patched away or inferred from success.
            profile={'profile':'ubuntu24-host-qt5-qt6-v1','suites':list(self.fixture.registry['suites']),
                'selection':{'suites':list(self.fixture.registry['suites']),'full_host':True,
                    'include_platform':False,'reason':'fixture-selected-platform-omission'}}
            self.controller.producer.selection_profile.return_value=profile
            self.case.plan['owners']['shared-host']['include_platform']=False
            receipt=deepcopy(self.fixture.receipt)
            receipt['include_platform']=False
            receipt['results']={name:{'status':'passed','fingerprint':self.fixtures.P.inputs.suite_fingerprint(
                self.fixture.registry,name,self.fixture.tree,receipt['environment'])} for name in self.fixture.registry['suites']}
            receipt=self.fixtures.FIXTURES.signed(receipt,'receipt_digest')
            self.case.aggregate['results']['shared-host']['receipt']=receipt
            run=self.original_run
            run=replace(run,final_publisher=replace(run.final_publisher,receipt_sha256=hashlib.sha256(self.fixtures.P.canonical(receipt)).hexdigest()))
            self.case.add_run(run)
            self.case.runs[100]['pull_requests']=[]
            with self.subTest(child=child,parent=parent):
                # Original main schema3 has B==D. Child-origin legacy3 lacks
                # retainedD and must decline even when all controller bytes match.
                if parent!='main':
                    with self.assertRaises(gate.EvidenceError):self.verify()
                    continue
                value=self.verify()
                self.assertEqual(value['parent_branch'],parent)
                self.assertEqual(value['candidate_plan']['reused'],list(self.fixture.registry['suites']))
                self.assertEqual(value['original_proof']['integration']['target'],parent)

    def test_changed_historical_child_content_cannot_match_repository_scoped_proof(self):
        path=next(name for name in self.candidate if name not in self.controller.A.WORKFLOWS
            and name not in {'tests/platform-profile.json','.github/test-suites.json',self.controller.TEMPLATE})
        self.candidate[path]={**self.candidate[path],'sha':'e'*40}
        expected=self.controller.inputs.plan_reuse(self.fixture.registry,self.fixture.tree,self.candidate,
            self.fixture.receipt['results'],self.fixture.receipt['environment'],self.fixture.receipt['environment'])
        self.assertEqual(expected['reused'],[])
        self.assertEqual(expected['required'],list(self.fixture.registry['suites']))
        with self.assertRaises(gate.EvidenceError):self.verify()

    def test_pending_failed_tied_or_retried_latest_parent_never_uses_old_success(self):
        for status,conclusion,attempt in (('queued',None,1),('in_progress',None,1),('completed','failure',1),('completed','success',2)):
            row={**deepcopy(self.case.push),'id':501,'run_started_at':'2026-10-15T10:05:00Z',
                'status':status,'conclusion':conclusion,'run_attempt':attempt}
            self.push_rows=[deepcopy(self.case.push),row]
            with self.subTest(status=status,conclusion=conclusion,attempt=attempt),self.assertRaises(gate.EvidenceError):self.verify()
        self.push_rows=[deepcopy(self.case.push),{**deepcopy(self.case.push),'id':501}]
        with self.assertRaises(gate.EvidenceError):self.verify()

    def test_current_refs_protection_default_and_original_native_whole_hash_are_mandatory(self):
        def mismatch(mode,endpoint,value):
            value=deepcopy(value)
            if mode=='child-parent' and endpoint.endswith('/git/commits/'+self.child_merge): value['parents'].reverse()
            elif mode=='protection' and endpoint.endswith('/branches/'+self.request.base): value['protected']=False
            elif mode=='default' and endpoint.endswith('/git/ref/heads/main'): value['object']['sha']='f'*40
            elif mode=='app' and '/check-runs/' in endpoint: value['app']['id']=42
            elif mode=='publisher' and '/attempts/1/jobs?' in endpoint:
                for job in value['jobs']:
                    if job.get('name','').startswith(self.case.policy.final_publisher_prefix):
                        job['name']=self.case.policy.final_publisher_prefix+'0'*64
            elif mode=='mixed-attempt' and '/attempts/1/jobs?' in endpoint:
                value['jobs'][0]['run_attempt']=2
            elif mode=='push-status' and endpoint.endswith('/actions/runs/500/attempts/1'): value['status']='in_progress';value['conclusion']=None
            return value
        for mode in ('child-parent','protection','default','app','publisher','mixed-attempt','push-status'):
            self.extra_mutation=lambda endpoint,value:mismatch(mode,endpoint,value)
            with self.subTest(mode=mode),self.assertRaises(gate.EvidenceError):self.verify()

    def test_final_context_inventory_source_and_expiry_are_bookended(self):
        for mode in ('child','parent-run','controller','expiry'):
            counts={'child':0,'rows':0,'source':0}
            def mutate(endpoint,value):
                if endpoint.endswith('/pulls/42'):
                    counts['child']+=1
                    if mode=='child' and counts['child']>1:value['head']['sha']='f'*40
                if '/actions/workflows/350930890/runs?' in endpoint:
                    counts['rows']+=1
                    if mode=='parent-run' and counts['rows']>1:value['workflow_runs'][0]['status']='queued'
                return value
            self.extra_mutation=mutate
            def source(*args):
                counts['source']+=1
                return self.case.pp.controller_digest if mode!='controller' or counts['source']==1 else 'sha256:'+'0'*64
            with self.subTest(mode=mode),mock.patch.object(self.controller,'integrated_controller',side_effect=source):
                if mode=='expiry':
                    values=iter([self.fixtures.NOW,self.fixtures.NOW,self.fixtures.NOW,self.fixtures.NOW+timedelta(days=5)])
                    class Clock:
                        @staticmethod
                        def now(tz):return next(values)
                    with mock.patch.object(gate,'datetime',Clock),self.assertRaises(gate.EvidenceError):
                        gate.native_parent_evidence(self.transport,config(),self.request)
                else:
                    with self.assertRaises(gate.EvidenceError):self.verify()

    def test_legacy_success_and_unknown_transport_keep_existing_behavior(self):
        legacy={'schema':2,'kind':gate.NATIVE_PARENT_KIND}
        with mock.patch.object(gate,'_verify_legacy_evidence',return_value=legacy),mock.patch.object(gate,'native_parent_evidence') as native:
            result=gate.verify_evidence(self.transport,config(),self.request)
            self.assertIs(result,legacy)
            self.assertNotIsInstance(result,gate.NativeParentEvidence)
            native.assert_not_called()
        with mock.patch.object(gate,'_verify_legacy_evidence',side_effect=gate.EvidenceError('missing')), \
                mock.patch.object(gate,'native_parent_evidence',return_value=gate.NativeParentEvidence(native=True)) as native:
            self.assertEqual(gate.verify_evidence(self.transport,config(),self.request),{'native':True})
            native.assert_called_once()
            with self.assertRaises(gate.EvidenceError):gate.verify_evidence(MappingApi(),config(),self.request)


class NativeRetainedParentEvidenceTests(unittest.TestCase):
    """Real immutable D/projection + real native Adapter; no host/platform run.

    Native API documents and protected generation enrollment are fixture data.
    Local module loading, selection and host admission are explicit seams; the
    complete source4 envelope, partition, native platform job, artifact hashes
    and Adapter verification use their actual implementations.
    """
    @classmethod
    def setUpClass(cls):
        NativeParentEvidenceTests.setUpClass()
        cls.fixtures=NativeParentEvidenceTests.fixtures
        spec=importlib.util.spec_from_file_location('sync_retained_source_fixtures',
            HERE.parent/'test-evidence/ci-profile-test.py')
        cls.sources=importlib.util.module_from_spec(spec);spec.loader.exec_module(cls.sources)

    def setUp(self):
        native=NativeParentEvidenceTests();self.addCleanup(native.doCleanups);native.setUp()
        self.native=native;self.controller=C=native.controller
        self.fixture=f=native.fixture;self.case=case=native.case
        # Restore actual registry parsing before creating the sealed small
        # immutable source repository, not a narrowed two-suite toy registry.
        for item in f.patches:
            if item.attribute=='load_registry': C.inputs.load_registry.side_effect=item.temp_original
        holder=(self.sources.SevenTargetProfileTests() if getattr(self,'ci_original',False)
            else self.sources.ControllerGenerationTests())
        self.addCleanup(holder.doCleanups);holder.setUp()
        source=holder.f if getattr(self,'ci_original',False) else holder
        self.source=source;self.root=source.root;self.registry=source.registry
        # The real immutable fixture below is original protected default D,
        # even when this suite runs from an Android child checkout. Its parent
        # and current-child maps receive their independently pinned profiles.
        self.assertEqual(C.source_admission.blob_id(
            (self.root/C.source_admission.PROFILE).read_bytes()),C.source_admission.SHARED_PROFILE)
        if getattr(self,'ci_original',False):
            policy=json.loads((self.root/C.ci_profile.POLICY).read_bytes())
            policy['not_before']='2026-10-15T00:00:00Z'
            (self.root/C.ci_profile.POLICY).write_bytes(C.inputs._canonical(policy))
        for suite in self.registry['suites'].values():
            for name in suite['closure']['required']:
                original=C.ROOT/name;target=self.root/name
                if not target.exists():
                    target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(original.read_bytes())
                    target.chmod(original.stat().st_mode&0o777)
        # The future row is deliberately unenrolled in shipping source. Supply
        # one complete reviewed unit generation, with no production catalog edit.
        paths={'.github/workflows/project-tests.yml':C.producer.PLATFORM_TEMPLATE,
            '.github/workflows/parent-qualification.yml':C.producer.PLATFORM_PARENT_TEMPLATE,
            '.github/workflows/repository-checks.yml':'tools/repository-checks/workflows/producers/repository-checks.yml',
            '.github/workflows/sync-validation.yml':'.github/workflows/sync-validation.yml',
            '.github/workflows/browser-client.yml':'.github/workflows/browser-client.yml',
            C.A.METADATA_WORKFLOW:'tools/repository-checks/workflows/metadata-edits/pr-metadata-context.yml'}
        self.generation={name:source.blob((self.root/relative).read_bytes()) for name,relative in paths.items()}
        document=json.loads((self.root/'.github/package-workflow-generations.json').read_bytes())
        document['generations'].append({'name':C.producer.PLATFORM_GENERATION,'workflows':self.generation})
        (self.root/'.github/package-workflow-generations.json').write_bytes(C.inputs._canonical(document))
        self.platforms={}
        # Hosted PR checkouts contain only the merge candidate and its parents.
        # Recover the exact reviewed profile bytes from the current handoff
        # policy instead of requiring unrelated historical Git objects.
        profiles=json.loads((C.ROOT/'.github/android-owner-transfer.json').read_bytes())['profiles']
        for branch in ('android-main','android-phone'):
            oid=C.source_admission.TARGET_PROFILES[branch]
            raw=(json.dumps({'schema':1,'platform':'android',
                'suites':profiles[branch]['required_suites']},indent=2)+'\n').encode()
            self.assertEqual(C.source_admission.blob_id(raw),oid)
            self.platforms[branch]=(raw,json.loads(raw)['suites'])
            for item in self.platforms[branch][1]:
                path=self.root/item['entrypoint']
                if not path.exists():
                    path.parent.mkdir(parents=True,exist_ok=True)
                    path.write_bytes(b'# unit platform entrypoint; never executed\n')
                path.chmod(0o755 if item['interpreter']=='bash' else 0o644)
        (self.root/'retained-fixture-data.txt').write_bytes(b'complete original default source member\n')
        source.git('add','--all');source.git('-c','user.name=Fixture','-c','user.email=fixture@example.invalid',
            'commit','--quiet','-m','Complete immutable source4 native sync fixture')
        self.manifest=C.ci_profile.capture_controller_manifest(self.root,
            source.git('rev-parse','HEAD').decode().strip())
        native.default=self.manifest['source_commit'];native.default_tree=self.manifest['source_tree']
        native.local=deepcopy(self.manifest['entries'])
        apple=getattr(self,'ci_original',False) and not getattr(self,'ci_android',False)
        parent_target='apple-main' if apple else 'android-main'
        child_target='apple-ios' if apple else 'android-phone'
        parent=deepcopy(native.local);parent.update(deepcopy(self.generation))
        parent[C.source_admission.PROFILE]=C.source_admission.ordinary(C.source_admission.TARGET_PROFILES[parent_target])
        previous=deepcopy(parent);previous['retained-fixture-data.txt']=source.blob(b'previous product value\n')
        candidate=deepcopy(parent)
        candidate[C.source_admission.PROFILE]=C.source_admission.ordinary(C.source_admission.TARGET_PROFILES[child_target])
        f.registry=self.registry;f.tree=parent;f.previous=previous;native.candidate=candidate
        self.parent,self.previous,self.candidate=parent,previous,candidate
        case.binding.update(base_ref=parent_target,merge_tree=C.ci_profile._controller_tree_identity(parent))
        native.child_tree=C.ci_profile._controller_tree_identity(candidate)
        native.request=replace(native.request,base=child_target,head=parent_target,parent=parent_target,profile=child_target)
        case.push['head_branch']=parent_target;native.push_rows=[deepcopy(case.push)]
        base_tree=C.ci_profile._controller_tree_identity(previous)
        self.records={case.binding['base_sha']:(base_tree,[]),case.binding['head_sha']:(case.binding['merge_tree'],[]),
            case.binding['merge_sha']:(case.binding['merge_tree'],case.binding['merge_parents']),
            case.integrated:(case.binding['merge_tree'],case.binding['merge_parents']),
            native.default:(native.default_tree,[]),native.child_base:(native.child_tree,[]),
            native.child_merge:(native.child_tree,[native.child_base,case.integrated])}
        self.maps={base_tree:previous,case.binding['merge_tree']:parent,native.default_tree:native.local,
            native.child_tree:candidate}
        self.trees={}
        def encode_tree(entries):
            nodes={}
            for name,entry in entries.items():
                node=nodes
                for part in name.split('/')[:-1]:node=node.setdefault(part,{})
                node[name.split('/')[-1]]=entry
            def visit(node):
                rows=[];raw=b''
                for name,item in sorted(node.items(),key=lambda row:row[0]+('/' if 'sha' not in row[1] else '')):
                    entry=item if 'sha' in item else {'mode':'040000','type':'tree','sha':visit(item)}
                    rows.append({'path':name,**entry})
                    raw+=entry['mode'].lstrip('0').encode()+b' '+name.encode()+b'\0'+bytes.fromhex(entry['sha'])
                oid=hashlib.sha1(b'tree '+str(len(raw)).encode()+b'\0'+raw).hexdigest()
                self.trees[oid]={'sha':oid,'truncated':False,'tree':rows};return oid
            return visit(nodes)
        for oid,tree in self.maps.items():self.assertEqual(encode_tree(tree),oid)
        self.encode_tree=encode_tree
        original_json=native.api.json
        def json_api(endpoint):
            path=endpoint[len(C.A.PREFIX):].lstrip('/').split('?',1)[0]
            if path.startswith('git/commits/'):
                oid=path.rsplit('/',1)[1];tree,parents=self.records[oid]
                value={'sha':oid,'tree':{'sha':tree},'parents':[{'sha':item} for item in parents]}
            elif path.startswith('git/trees/'):value=deepcopy(self.trees[path.rsplit('/',1)[1]])
            elif path=='actions/workflows/repository-checks.yml':value={'id':99,'path':'.github/workflows/repository-checks.yml'}
            else:return original_json(endpoint)
            f.api.calls.append(endpoint);return native.extra_mutation(endpoint,deepcopy(value))
        native.api.json=json_api
        native.api.immutable_tree=lambda oid:{'sha':oid,'truncated':False,
            'tree':[{'path':name,**entry} for name,entry in self.maps[oid].items()]}
        native.api.immutable_blob=lambda oid,**kw:next(raw for raw,_ in self.platforms.values()
            if C.source_admission.blob_id(raw)==oid)
        native.api.immutable_source_blob=lambda oid:C.ci_profile._controller_git(self.root,'cat-file','blob',oid)
        # Root and independent selector seams are explicit. Actual native source
        # compatibility and retained projection are checked again below.
        for item in (mock.patch.object(gate,'ROOT',self.root),
            mock.patch.object(C.inputs,'full_tree',side_effect=lambda *args:native.local),
            mock.patch.object(C.execution,'checkout_identity',side_effect=lambda *args:(native.default,native.default_tree))):
            item.start();self.addCleanup(item.stop)
        package=SimpleNamespace(validate_tree_wiring=lambda tree:C.producer.PLATFORM_GENERATION
            if all(tree.get(name)==entry for name,entry in self.generation.items()) else 'unreviewed',
            workflow_generations=lambda:[{'name':C.producer.PLATFORM_GENERATION,'workflows':self.generation}])
        self.policy=SimpleNamespace(package_policy=lambda:package)
        C.producer._host_policy.return_value=self.policy
        members=mock.patch.object(C.producer,'controller_sources',return_value=sorted(C.source_admission.CONTROLLERS))
        members.start();self.addCleanup(members.stop)
        self.profile={'profile':C.producer.FULL_PROFILE,'binding':None,'suites':list(self.registry['suites']),
            'selection':{'suites':list(self.registry['suites']),'full_host':True,'include_platform':True,'reason':'fixture-full-owner'}}
        if getattr(self,'ci_original',False):
            selected=deepcopy(holder.selection)
            raw_blobs={C.source_admission.blob_id((self.root/name).read_bytes()):(self.root/name).read_bytes()
                for name in (C.ci_profile.DATA_PATH,)}
            old_blob=native.api.immutable_blob
            native.api.immutable_blob=lambda oid,**kw:raw_blobs[oid] if oid in raw_blobs else old_blob(oid,**kw)
            binding=C.ci_profile.validate_selection(selected,parent,native.local,self.registry,
                target=parent_target,base_tree=previous,root=self.root,
                read_blob=native.api.immutable_blob,controller_manifest=self.manifest)
            self.profile={'profile':C.ci_profile.PROFILE,'binding':binding,
                'suites':list(C.ci_profile.SUITES),'selection':selected}
        C.producer.selection_profile.return_value=self.profile
        mocked=mock.patch.object(C.producer,'selection_profile_for_reuse',return_value=self.profile)
        mocked.start();self.addCleanup(mocked.stop)
        # Actual policy construction selects schema4, actual canonical Android
        # recipe and native complete workflow tuple. It is not a mocked policy.
        for item in f.patches:
            if item.attribute=='_policy':C._policy.side_effect=item.temp_original
        admission={**C.source_admission.compatibility(previous,native.local,parent_target,
            read_actual=lambda name:C.source_admission.actual_bytes(self.root,name),
            actual_imports=C.source_admission.actual_import_inventory(self.root)),
            'base':case.binding['base_sha'],'default':native.default}
        C.integrated_controller.return_value=admission['controller_digest']
        adapter=C.A.Adapter(native.api)
        self.partition=C.producer.platform_partition(self.policy,self.profile,self.registry,parent,previous,native.local,
            target=parent_target,root=self.root,read_blob=native.api.immutable_blob)
        case.plan,case.policy=C._policy(self.policy,self.registry,case.binding,admission['controller_digest'],adapter,
            self.root,self.profile['selection'],common_owner=C.producer.common_owner(self.profile,self.partition),
            template=C.producer.PLATFORM_TEMPLATE)
        case.pp=case.policy.producer
        self.git=C.producer.expected_git_context(adapter,case.binding)
        self.environment=self.fixtures.FIXTURES.isolated_codec_environment()
        if getattr(self,'ci_original',False):
            spec=importlib.util.spec_from_file_location('original_lookup_runtime_fixture',
                HERE.parent/'test-evidence/runtime-ci-test.py')
            runtime_fixture=importlib.util.module_from_spec(spec);spec.loader.exec_module(runtime_fixture)
            sample=runtime_fixture.OriginalCIEnvironmentTests();sample.setUp()
            try:self.environment=deepcopy(sample.environment)
            finally:sample.doCleanups()
            R=C.runtime_ci
            self.environment['selection']=self.profile['binding']
            _,manifests=R.runtime._requirement_inventory(self.root)
            self.environment['trusted_execution']={**R.runtime._controller_file_hashes(manifests,self.root),
                **{name:R.runtime._file_digest(self.root/name) for name in R._FILES}}
        context={'source':case.binding['merge_sha'],'run_id':100,'run_attempt':1,
            'profile':'manual-shared-host-compatibility-v1','snapshot':'sha256:'+'1'*64,'git_context':self.git,
            'runtime_profile':C.producer.FULL_PROFILE,'selection':self.profile['selection'],'profile_binding':None,
            'registry':C.ci_profile._digest(self.registry),'prepared':self.environment['prepared'].get('roots',{}),
            'outside_namespaces':{name:100+i for i,name in enumerate(('user','mnt','pid','net','ipc','uts'))}}
        if getattr(self,'ci_original',False):
            context.update(runtime_profile=C.ci_profile.PROFILE,profile_binding=self.profile['binding'],
                prepared={name:entry['digest'] for name,entry in self.environment['prepared'].items()},
                selection_target=parent_target,selection_base=case.binding['base_sha'])
        projection=self.root.parent/'native-sync-projection';projection.mkdir()
        for name in C.ci_profile.controller_paths():
            C.sandbox._write_source(projection,name,(self.root/name).read_bytes(),executable=name=='tests/run-project-tests.py')
        C.sandbox._write_source(projection,C.ci_profile.CONTROLLER_MANIFEST,C.inputs._canonical(self.manifest))
        context['projection']=C.ci_profile._digest(C.sandbox._files(projection))
        C.sandbox._write_source(projection,'context.json',C.inputs._canonical({'shared_host':context}))
        self.retained=C.ci_profile.capture_retained_source(self.manifest,C.sandbox._files(projection),context,admission,root=self.root)
        receipt=deepcopy(f.receipt)
        receipt.update(schema=4,candidate_tree=case.binding['merge_tree'],git_context=self.git,
            environment=self.environment,protected_source=self.retained,requested_suites=self.profile['suites'],
            include_platform=False,platform_results={})
        receipt['results']={name:{'status':'passed','fingerprint':C.inputs.suite_fingerprint(
            self.registry,name,parent,self.environment)} for name in self.profile['suites']}
        self.receipt=self.fixtures.FIXTURES.signed(receipt,'receipt_digest')
        case.aggregate['results']['shared-host']['receipt']=self.receipt
        run=replace(native.original_run,workflow_blob=case.pp.workflow_blob,
            final_publisher=replace(native.original_run.final_publisher,
                receipt_sha256=hashlib.sha256(C.P.canonical(self.receipt)).hexdigest()))
        case.add_run(run);case.runs[100]['pull_requests']=[]
        case.runs[100]['display_title']=C.A.ORDINARY_RUN_NAME
        platform=deepcopy(case.jobs[100][1]);platform.update(id=140,name=C.producer.PLATFORM_JOB,
            check_run_url=f'https://api.github.com/{C.A.PREFIX}/check-runs/140')
        platform['steps']=[{'name':'Execute and verify the complete Android platform inventory',
            **{key:platform[key] for key in ('status','conclusion','started_at','completed_at')}}]
        if self.partition is not None:case.jobs[100].append(platform)

    def verify(self):return self.native.verify()

    def test_complete_original_D_schema4_and_native_android_job_preserve_common_only_reuse(self):
        value=self.verify()
        self.assertIsInstance(value,gate.NativeParentEvidence)
        self.assertEqual(value['original_protected_source'],self.retained)
        self.assertEqual(value['original_protected_source']['default_commit'],self.native.default)
        self.assertNotEqual(self.native.default,self.case.binding['base_sha'])
        self.assertEqual(value['original_commit'],self.case.binding['merge_sha'])
        self.assertNotEqual(value['original_commit'],value['parent_commit'])
        self.assertNotEqual(value['original_commit'],self.native.request.merge_sha)
        self.assertEqual(value['environment'],self.environment)
        self.assertEqual(value['expires_at'],self.case.aggregate['expires_at'])
        self.assertEqual(value['original_platform_observation']['job_id'],140)
        self.assertFalse(value['original_platform_observation']['reusable'])
        self.assertFalse(value['platform_reused'])
        self.assertEqual(value['child_platform_profile'],self.controller.source_admission.ordinary(
            self.controller.source_admission.TARGET_PROFILES['android-phone']))
        self.assertFalse(self.receipt['include_platform']);self.assertEqual(self.receipt['platform_results'],{})
        self.assertTrue(value['candidate_plan']['reused'])
        self.assertTrue(value['candidate_plan']['required'],'different child inventory retains actual unmatched suites')
        self.controller.execution.execute.assert_not_called()
        self.controller.execution.capture_execution_environment.assert_not_called()

    def test_missing_failed_ambiguous_or_foreign_original_platform_job_is_not_reused(self):
        original=deepcopy(self.case.jobs[100])
        for mutation in ('missing','failed','duplicate','step','step-failed','attempt','app'):
            self.case.jobs[100]=deepcopy(original)
            job=self.case.jobs[100][-1]
            if mutation=='missing':self.case.jobs[100].pop()
            elif mutation=='failed':job['conclusion']='failure'
            elif mutation=='duplicate':self.case.jobs[100].append({**deepcopy(job),'id':141})
            elif mutation=='step':job['steps']=[]
            elif mutation=='step-failed':job['steps'][0]['conclusion']='failure'
            elif mutation=='attempt':job['run_attempt']=2
            self.native.extra_mutation=lambda endpoint,value:({**value,'app':{'id':42}}
                if mutation=='app' and endpoint.endswith('/check-runs/140') else value)
            with self.subTest(mutation=mutation),self.assertRaises(gate.EvidenceError):self.verify()

    def test_whole_original_source_projection_and_native_hash_are_required(self):
        original=deepcopy(self.retained)
        # Re-sign both artifact levels: neither local checksum can replace the
        # original native whole-receipt publisher or immutable source proof.
        for mutation in ('missing','default','manifest','projection','publisher'):
            receipt=deepcopy(self.receipt)
            if mutation=='missing':receipt.pop('protected_source')
            elif mutation=='default':receipt['protected_source']['default_commit']='f'*40
            elif mutation=='manifest':receipt['protected_source']['manifest_digest']='sha256:'+'0'*64
            elif mutation=='projection':receipt['protected_source']['projection_digest']='sha256:'+'0'*64
            else:receipt['protected_source']['binding']['snapshot']='sha256:'+'0'*64
            self.case.aggregate['results']['shared-host']['receipt']=self.fixtures.FIXTURES.signed(receipt,'receipt_digest')
            aggregate=self.fixtures.FIXTURES.signed(self.case.aggregate,'aggregate_digest')
            run=self.native.original_run
            self.case.artifacts[100]=self.case.artifacts[100][:1]
            self.case.artifact(run,'aggregate',aggregate)
            with self.subTest(mutation=mutation),self.assertRaises(gate.EvidenceError):self.verify()
        self.assertEqual(self.retained,original)

    def test_current_child_platform_is_separate_and_unknown_or_missing_owner_never_claims_pass(self):
        # Actual current child declaration includes nineteen real commands. No
        # command is launched and no parent common proof changes that inventory.
        with tempfile.TemporaryDirectory(prefix='native-child-platform-') as temporary:
            candidate=Path(temporary)
            raw,items=self.platforms['android-phone']
            path=candidate/self.controller.source_admission.PROFILE;path.parent.mkdir();path.write_bytes(raw)
            for item in items:
                path=candidate/item['entrypoint'];path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'# not executed\n')
            actual=self.controller.execution.platform_suites(candidate,self.registry['suites'])
            self.assertEqual(len(actual),19)
            value=self.verify();self.assertFalse(value['platform_reused'])
            (candidate/items[0]['entrypoint']).unlink()
            with self.assertRaises(self.controller.execution.ExecutionError):
                self.controller.execution.platform_suites(candidate,self.registry['suites'])
        profile=self.controller.source_admission.PROFILE
        for changed in ({'mode':'100644','type':'blob','sha':'f'*40},
                {**self.candidate[profile],'mode':'100755'}):
            self.candidate[profile]=changed
            with self.subTest(profile=changed),self.assertRaises(gate.EvidenceError):self.verify()

    def test_original_platform_source_and_expiry_bookends_reject_late_changes(self):
        count=0
        def mutate(endpoint,value):
            nonlocal count
            if '/attempts/1/jobs?' in endpoint and '/actions/runs/100/' in endpoint:
                count+=1
                if count>2:
                    for job in value['jobs']:
                        if job.get('id')==140:job['steps'][0]['conclusion']='failure'
            return value
        self.native.extra_mutation=mutate
        with self.assertRaises(gate.EvidenceError):self.verify()
        self.assertGreater(count,2)
        self.native.extra_mutation=lambda endpoint,value:value
        original=self.controller.producer.retained_receipt_source
        path=self.root/'tools/test-evidence/execution.py';raw=path.read_bytes();reads=0
        def source(*args,**kwargs):
            nonlocal reads
            reads+=1
            if reads>1:path.write_bytes(raw+b'\n# changed after first retained-source check\n')
            return original(*args,**kwargs)
        try:
            with mock.patch.object(self.controller.producer,'retained_receipt_source',side_effect=source), \
                    self.assertRaises(gate.EvidenceError):self.verify()
            self.assertEqual(reads,2)
        finally:path.write_bytes(raw)
        expired=False;parent_reads=0;parent_run=gate._native_parent_run
        def final_parent(*args,**kwargs):
            nonlocal expired,parent_reads
            value=parent_run(*args,**kwargs);parent_reads+=1
            if parent_reads>1:expired=True
            return value
        fixtures=self.fixtures
        class Clock:
            @staticmethod
            def now(tz):return fixtures.NOW+timedelta(days=5) if expired else fixtures.NOW
        with mock.patch.object(gate,'datetime',Clock), \
                mock.patch.object(gate,'_native_parent_run',side_effect=final_parent),self.assertRaises(gate.EvidenceError):
            gate.native_parent_evidence(self.native.transport,config(),self.native.request)
        self.assertEqual(parent_reads,2)

    def test_complete_recipe_and_original_partition_cannot_be_relabelled(self):
        for path in ('.github/workflows/parent-qualification.yml','.github/workflows/project-tests.yml',
                     self.controller.source_admission.PROFILE):
            original=deepcopy(self.parent[path]);self.parent[path]={**original,'sha':'f'*40}
            try:
                with self.subTest(path=path),self.assertRaises(gate.EvidenceError):self.verify()
            finally:self.parent[path]=original
        # Native owner omission cannot be repaired by declaring a shared/common
        # selection: the authenticated original include-platform decision stays.
        self.profile['selection']['include_platform']=False
        with self.assertRaises(gate.EvidenceError):self.verify()

    def retain_equal_tree_parent(self):
        """Keep source4/E3/Android owner real; add only native transport facts."""
        C=self.controller; native=self.native
        hops=self.fixtures.RetainedIntegratedFakeApi(self.case,1)
        hops.metadata=deepcopy(self.generation)
        hops.helper=deepcopy(native.local[C.A.METADATA_SOURCE])
        hops.policy=C.A.MetadataPolicy(99,self.case.policy.caller_path,
            {C.producer.PLATFORM_GENERATION:hops.metadata},
            {C.producer.PLATFORM_GENERATION:{C.A.METADATA_SOURCE:hops.helper}})
        hops.maps={self.case.binding['merge_tree']:self.parent}
        hops.commits[self.case.binding['base_sha']]=self.records[self.case.binding['base_sha']]
        hops.default=native.default;hops.fallback_json=native.api.json
        native.api.json=hops.json;native.api.integrated_pr=hops.integrated_pr
        hop=hops.hops[0];native.push_rows=[deepcopy(hops.extra_runs[hop['push']])]
        native.request=replace(native.request,head_sha=hops.current,parent_sha=hops.current)
        self.records[native.child_merge]=(native.child_tree,[native.child_base,hops.current])
        self.hops=hops
        return hops

    def test_same_tree_parent_retains_original_B_D_selection_E_and_separate_child_platform(self):
        hops=self.retain_equal_tree_parent()
        original_receipt=deepcopy(self.receipt);original_profile=deepcopy(self.profile)
        value=self.verify()
        self.assertEqual(value['parent_commit'],hops.current)
        self.assertEqual(value['original_commit'],self.case.binding['merge_sha'])
        self.assertEqual(value['original_proof']['origin_integration']['commit'],self.case.integrated)
        self.assertEqual(value['original_protected_source'],self.retained)
        self.assertEqual(value['environment'],self.environment)
        self.assertEqual(value['expires_at'],self.case.aggregate['expires_at'])
        self.assertEqual(value['original_git_context']['commits'][self.case.binding['merge_sha']]['parents'][0],self.case.binding['base_sha'])
        self.assertEqual(self.receipt,original_receipt);self.assertEqual(self.profile,original_profile)
        self.assertFalse(value['platform_reused'])
        if self.partition is not None:self.assertEqual(value['original_platform_observation']['job_id'],140)
        self.controller.execution.execute.assert_not_called()
        self.controller.execution.capture_execution_environment.assert_not_called()

    def test_same_tree_retention_cannot_hide_lost_original_platform_or_late_hop_change(self):
        hops=self.retain_equal_tree_parent()
        if self.partition is not None:
            self.case.jobs[100][-1]['conclusion']='failure'
            with self.assertRaises(gate.EvidenceError):self.verify()
            self.case.jobs[100][-1]['conclusion']='success'
        original=hops.mutate;reads=0
        def mutate(endpoint,value):
            nonlocal reads
            if endpoint.endswith('/check-suites/'+str(hops.extra_runs[hops.run_id]['check_suite_id'])):
                reads+=1
                if reads>2:value['app']['id']=42
            return original(endpoint,value)
        hops.mutate=mutate
        with self.assertRaises(gate.EvidenceError):self.verify()



class NativeOriginalLookupCompatibilityTests(unittest.TestCase):
    """Real immutable original88 + actual native Adapter + complete fake CI2 E.

    Current selector/local source startup are explicit fixture seams inherited
    from the native parent fixture. No identity probe or workload is executed.
    """
    @classmethod
    def setUpClass(cls):
        NativeRetainedParentEvidenceTests.setUpClass()

    def setUp(self):
        self.f=NativeRetainedParentEvidenceTests();self.f.ci_original=True
        self.f.ci_android=self._testMethodName=='test_android_CI2_original_source_is_reused_without_claiming_platform_execution'
        self.addCleanup(self.f.doCleanups);self.f.setUp()
        self.C=self.f.controller;self.original=deepcopy(self.f.retained)
        self.environment=deepcopy(self.f.environment)

    def advance(self,names):
        C=self.C;f=self.f;n=f.native
        for name in names:
            path=f.root/name;path.write_bytes(path.read_bytes()+b'\n# reviewed protected test-only update\n')
        f.source.git('add','--all');f.source.git('-c','user.name=Fixture','-c','user.email=fixture@example.invalid',
            'commit','--quiet','-m','Protected nonproduction source update')
        manifest=C.ci_profile.capture_controller_manifest(f.root,f.source.git('rev-parse','HEAD').decode().strip())
        n.default,n.default_tree=manifest['source_commit'],manifest['source_tree']
        n.local=deepcopy(manifest['entries'])
        f.records[n.default]=(n.default_tree,[]);f.maps[n.default_tree]=n.local
        self.assertEqual(f.encode_tree(n.local),n.default_tree)
        return manifest

    def verify(self):return self.f.verify()

    def test_all_seventeen_original_inputs_remain_bound_while_current_bodies_advance(self):
        C=self.C;f=self.f
        current=self.advance(C.ci_profile._ORIGINAL_LOOKUP_DATA)
        self.assertNotEqual(current['source_commit'],self.original['default_commit'])
        self.assertNotEqual(C.ci_profile.controller_generation(current['entries'],f.registry),
            self.environment['selection']['generation_digest'])
        value=self.verify()
        self.assertEqual(value['environment'],self.environment)
        self.assertEqual(value['original_protected_source'],self.original)
        self.assertEqual(value['runtime_admission']['selection'],self.environment['selection'])
        self.assertEqual(value['original_proof']['receipt_sha256'],
            hashlib.sha256(C.P.canonical(f.receipt)).hexdigest())
        self.assertEqual(value['expires_at'],f.case.aggregate['expires_at'])
        self.assertFalse(value['platform_reused'])
        self.assertEqual(set(value['results']['suites']),set(C.ci_profile.SUITES))
        self.assertIn('tests/run-project-tests.py',value['candidate_inputs'])

    def test_doc_only_body_change_keeps_complete_original_projection_and_E(self):
        self.advance(['tools/test-evidence/AFFECTED_SELECTION.md'])
        value=self.verify()
        self.assertEqual(value['original_protected_source']['projection_digest'],self.original['projection_digest'])
        self.assertEqual(value['environment'],self.environment)

    def test_android_CI2_original_source_is_reused_without_claiming_platform_execution(self):
        self.advance(['tools/test-evidence/producer-api-test.py'])
        value=self.verify()
        self.assertEqual(value['parent_branch'],'android-main')
        self.assertEqual(value['child_platform_profile']['sha'],self.C.source_admission.TARGET_PROFILES['android-phone'])
        self.assertEqual(value['environment'],self.environment)
        self.assertIsNone(value['original_platform_observation'])
        self.assertFalse(value['platform_reused'])
        self.assertEqual(value['original_protected_source'],self.original)

    def test_controller_policy_mode_alias_new_lookup_or_corrupt_original_blob_declines(self):
        C=self.C;f=self.f
        self.advance(['tools/test-evidence/ci-profile-test.py'])
        for change in ('controller','policy','mode','alias','new-member','raw'):
            path=f.root/('tools/test-evidence/runtime_ci.py' if change=='controller' else
                C.ci_profile.POLICY if change=='policy' else 'tools/test-evidence/test.py')
            raw=path.read_bytes();mode=path.stat().st_mode&0o777
            original_reader=f.native.api.immutable_source_blob
            extra=f.root/'tools/test-evidence/unreviewed.so'
            try:
                if change in {'controller','policy'}:path.write_bytes(raw+b'\n# changed actual source\n')
                elif change=='mode':path.chmod(0o755)
                elif change=='alias':path.unlink();path.symlink_to(f.root/'tools/test-evidence/producer.py')
                elif change=='new-member':extra.write_bytes(b'new native import lookup')
                else:f.native.api.immutable_source_blob=lambda oid:b'corrupted original source'
                with self.subTest(change=change),self.assertRaises(gate.EvidenceError):self.verify()
            finally:
                if path.is_symlink():path.unlink()
                path.write_bytes(raw);path.chmod(mode)
                if extra.exists():extra.unlink()
                f.native.api.immutable_source_blob=original_reader

    def test_native_whole_hash_failure_pending_or_expiry_cannot_mint_original_authority(self):
        self.advance(['tools/test-evidence/producer-api-test.py'])
        for change in ('native-hash','pending','expiry'):
            jobs=deepcopy(self.f.case.jobs);runs=deepcopy(self.f.case.runs)
            aggregate=deepcopy(self.f.case.aggregate)
            try:
                if change=='native-hash':
                    for job in self.f.case.jobs[100]:
                        if job['name'].startswith(self.C.producer.PUBLISH_PREFIX):
                            job['name']=self.C.producer.PUBLISH_PREFIX+'0'*64
                elif change=='pending':self.f.case.runs[100].update(status='in_progress',conclusion=None)
                with self.subTest(change=change),self.assertRaises(gate.EvidenceError):
                    if change=='expiry':gate.native_parent_evidence(self.f.native.transport,config(),self.f.native.request,
                        now=self.f.fixtures.NOW+timedelta(hours=2))
                    else:self.verify()
            finally:
                self.f.case.jobs,self.f.case.runs,self.f.case.aggregate=jobs,runs,aggregate

    def test_envelope_dict_or_raw_callback_is_not_original_runtime_authority(self):
        R=self.C.runtime_ci
        for supplied in (self.original,{'verified':True},object()):
            with self.subTest(supplied=type(supplied).__name__),self.assertRaises(R.CIEnvironmentError):
                R.validate_original_environment(supplied,self.environment,None,None,None,{}, {}, {}, {})
        with self.assertRaises(TypeError):self.C.ci_profile.authenticate_original_source(
            read_source_blob=lambda oid:b'',verified={'verified':True})

    def test_actual_native_token_admits_original_plan_only_until_original_expiry(self):
        C=self.C;f=self.f;n=f.native
        self.advance(['tools/test-evidence/producer-test.py'])
        adapter=C.A.Adapter(n.api)
        context=C.P.SharedContext(f.registry,f.parent,f.environment,f.case.binding['merge_sha'],
            f.case.binding['merge_tree'],f.git,f.retained)
        verified,token=C.producer.verify_original_source(adapter,500,f.case.plan,f.case.policy,context,
            f.receipt,f.case.binding,integrated=True,root=f.root,clock=lambda:f.fixtures.NOW)
        args=(f.environment,f.case.aggregate['qualified_at'],f.case.aggregate['expires_at'],f.fixtures.NOW,
            f.profile['selection'],f.profile['selection'],f.parent,f.parent,n.local,f.registry,f.receipt['results'])
        kwargs=dict(root=f.root,target=n.request.parent,base_tree=f.previous,read_blob=n.api.immutable_blob)
        with self.assertRaises(C.runtime_ci.CIEnvironmentError):C.runtime_ci.plan_original_reuse(*args,**kwargs)
        value=C.runtime_ci.plan_original_reuse(*args,**kwargs,original_source=token)
        self.assertEqual(value['reused_suites'],list(C.ci_profile.SUITES))
        self.assertEqual(value['original_expires_at'],verified['expires_at'])
        self.assertEqual(f.environment,self.environment)
        expired=list(args);expired[3]=C.P._time(verified['expires_at'])+timedelta(seconds=1)
        with self.assertRaises(C.runtime_ci.CIEnvironmentError):C.runtime_ci.plan_original_reuse(
            *expired,**kwargs,original_source=token)


class NativeParentSourceGuardTests(unittest.TestCase):
    def test_immutable_complete_import_lookup_precedes_any_proof_import(self):
        # Real immutable Git metadata + real materialized lookup. The only
        # mocked boundary is entering the proof modules after the guard passes.
        with tempfile.TemporaryDirectory(prefix='overte-native-sync-source-') as temporary:
            root=Path(temporary)
            raw=(gate.ROOT/'tools/test-evidence/source_admission.py').read_bytes()
            guard=type(sys)('native_sync_guard_fixture')
            exec(compile(raw,'reviewed source guard','exec'),guard.__dict__)
            for name in guard.IMPORT_MEMBERS:
                path=root/name;path.parent.mkdir(parents=True,exist_ok=True)
                path.write_bytes(raw if name==guard.SELF else b'# immutable fixture lookup\n')
            def git(*args):
                subprocess.run(['git','-c','commit.gpgsign=false',*args],cwd=root,check=True,
                    stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            git('init','-q','--initial-branch=main')
            git('config','user.name','Native source fixture')
            git('config','user.email','fixture@example.invalid')
            git('add','.');git('commit','-qm','Commit complete fixture lookup')
            subject=root/'tools/test-evidence/inputs.py'
            class ReachedProofImport(Exception):pass
            with mock.patch.object(gate,'ROOT',root),mock.patch.object(gate.importlib.util,
                    'spec_from_file_location',side_effect=ReachedProofImport) as imported:
                with self.assertRaises(ReachedProofImport):gate._native_parent_controller()
                self.assertEqual(imported.call_count,1)
                for mode in ('content','executable','untracked','bytecode','missing','alias','helper'):
                    with self.subTest(mode=mode):
                        extra=None
                        if mode=='content':subject.write_bytes(b'# changed after immutable Git\n')
                        elif mode=='executable':subject.chmod(0o755)
                        elif mode=='untracked':extra=subject.with_name('unreviewed.py');extra.write_bytes(b'# negative import lookup\n')
                        elif mode=='bytecode':
                            extra=subject.parent/'__pycache__'/'inputs.cpython-312.pyc'
                            extra.parent.mkdir();extra.write_bytes(b'not an admitted source member')
                        elif mode=='missing':subject.unlink()
                        elif mode=='alias':subject.unlink();subject.symlink_to('execution.py')
                        else:(root/guard.SELF).write_bytes(raw+b'\n# uncommitted helper\n')
                        before=imported.call_count
                        with self.assertRaises(ValueError):gate._native_parent_controller()
                        self.assertEqual(imported.call_count,before,'invalid source must fail before proof import')
                        if subject.is_symlink():subject.unlink()
                        subject.write_bytes(b'# immutable fixture lookup\n');subject.chmod(0o644)
                        (root/guard.SELF).write_bytes(raw)
                        if extra:
                            extra.unlink()
                            if mode=='bytecode':extra.parent.rmdir()



class VerifiedEmptySyncSourceTests(unittest.TestCase):
    """Real tiny Git/raw proof and native Adapter; source enrollment is a fixture."""
    @classmethod
    def setUpClass(cls):
        directory=str(HERE.parent/'test-evidence');sys.path.insert(0,directory)
        try:
            import postmerge
            cls.controller=postmerge
        finally:sys.path.remove(directory)

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.candidate=self.root/'candidate';self.candidate.mkdir()
        def git(*args):
            return subprocess.check_output(['git','-c','commit.gpgsign=false',*args],cwd=self.candidate,
                stderr=subprocess.PIPE).decode().strip()
        self.git=git;git('init','-q','--initial-branch=main');git('config','user.name','Empty fixture')
        git('config','user.email','fixture@example.invalid')
        for path,body in {'ios/.keep':'source\n','interface/.keep':'source\n',
                '.github/workflows/sync-validation.yml':'fixed complete future sync recipe\n',
                'tests/platform-profile.json':'{"schema":1,"platform":"shared","suites":[]}\n'}.items():
            file=self.candidate/path;file.parent.mkdir(parents=True,exist_ok=True);file.write_text(body)
        git('add','.');git('commit','-qm','Base tree');self.base=git('rev-parse','HEAD')
        git('commit','--allow-empty','-qm','Parent commits without content change');self.head=git('rev-parse','HEAD')
        self.tree_sha=git('rev-parse','HEAD^{tree}')
        self.merge=git('commit-tree',self.tree_sha,'-p',self.base,'-p',self.head,'-m','Exact synthetic merge')
        git('checkout','-q','--detach',self.merge)
        C=self.controller;self.default=self.head
        self.tree=gate.suite_inputs.full_tree(self.candidate,self.merge)
        self.local=deepcopy(self.tree)
        self.local['tools/repository-checks/workflows/sync-ci-selection.yml']=deepcopy(
            self.tree['.github/workflows/sync-validation.yml'])
        self.request=gate.SyncRequest(REPOSITORY,REPOSITORY_ID,42,'apple-ios',self.base,'apple-main',
            self.head,REPOSITORY_ID,self.merge,'direct','apple-main',self.head,'apple-ios',(),())
        self.repository={'full_name':REPOSITORY,'id':REPOSITORY_ID,'default_branch':'main'}
        self.pr={'number':42,'state':'open','mergeable':True,'merge_commit_sha':self.merge,'labels':[],
            'base':{'ref':'apple-ios','sha':self.base,'repo':self.repository},
            'head':{'ref':'apple-main','sha':self.head,'repo':self.repository}}
        self.env={'GITHUB_ACTIONS':'true','GITHUB_REPOSITORY':REPOSITORY,'GITHUB_REPOSITORY_ID':str(REPOSITORY_ID),
            'GITHUB_EVENT_NAME':'workflow_dispatch','GITHUB_RUN_ATTEMPT':'1','GITHUB_RUN_ID':'700',
            'GITHUB_JOB':'validate','GITHUB_REF':'refs/heads/main','GITHUB_SHA':self.default,
            'GITHUB_WORKFLOW_SHA':self.default,'GITHUB_WORKFLOW_REF':REPOSITORY+
                '/.github/workflows/sync-validation.yml@refs/heads/main',
            'RUNNER_ENVIRONMENT':'github-hosted','ImageOS':'ubuntu24'}
        self.run={'id':700,'workflow_id':350930895,'check_suite_id':701,'path':'.github/workflows/sync-validation.yml',
            'event':'workflow_dispatch','head_sha':self.default,'head_branch':'main','run_attempt':1,
            'status':'in_progress','conclusion':None,'run_started_at':'2026-10-15T10:00:00Z',
            'repository':self.repository,'head_repository':self.repository}
        self.job={'id':702,'run_id':700,'run_attempt':1,'head_sha':self.default,
            'name':'Validate exact synchronization','status':'in_progress','conclusion':None,
            'started_at':'2026-10-15T10:00:01Z','completed_at':None,
            'check_run_url':'https://api.github.com/'+C.A.PREFIX+'/check-runs/702'}
        self.calls=[];self.mutate=lambda endpoint,value:value
        outer=self
        class Api:
            def json(self,endpoint):
                outer.calls.append(endpoint)
                path=endpoint.removeprefix(C.A.PREFIX).lstrip('/').split('?',1)[0]
                if not path:value=outer.repository
                elif path=='pulls/42':value=outer.pr
                elif path.startswith('git/ref/heads/'):
                    ref=path.removeprefix('git/ref/heads/')
                    value={'ref':'refs/heads/'+ref,'object':{'type':'commit',
                        'sha':outer.base if ref=='apple-ios' else outer.head}}
                elif path.startswith('branches/'):
                    ref=path.removeprefix('branches/')
                    value={'name':ref,'protected':True,'commit':{'sha':outer.base if ref=='apple-ios' else outer.head}}
                elif path=='commits/refs/pull/42/merge':
                    value={'sha':outer.merge,'commit':{'tree':{'sha':outer.tree_sha}},
                        'parents':[{'sha':outer.base},{'sha':outer.head}]}
                elif path=='pulls/42/files':value=[]
                elif path.startswith('compare/'):value={'base_commit':{'sha':path.removeprefix('compare/').split('...')[0]},
                    'merge_base_commit':{'sha':outer.base},'files':[]}
                elif path.startswith('git/commits/'):
                    oid=path.removeprefix('git/commits/');parents=outer.git('show','-s','--format=%P',oid).split()
                    value={'sha':oid,'tree':{'sha':outer.tree_sha},'parents':[{'sha':p} for p in parents]}
                elif path=='actions/workflows/sync-validation.yml':
                    value={'id':350930895,'name':'Sync validation','path':'.github/workflows/sync-validation.yml','state':'active'}
                elif path in {'actions/runs/700','actions/runs/700/attempts/1'}:value=outer.run
                elif path=='actions/runs/700/attempts/1/jobs':value={'total_count':1,'jobs':[outer.job]}
                elif path=='check-suites/701':value={'id':701,'head_sha':outer.default,
                    'repository':outer.repository,'app':{'id':15368}}
                elif path=='check-runs/702':value={**outer.job,'id':702,'check_suite':{'id':701},'app':{'id':15368}}
                else:raise AssertionError('unregistered native empty API read: '+path)
                return outer.mutate(path,deepcopy(value))
        self.api=Api();self.transport=SimpleNamespace(native_producer_api=lambda controller:self.api)
        self.stack=self.enterContext(__import__('contextlib').ExitStack())
        self.stack.enter_context(mock.patch.object(gate,'_native_parent_controller',return_value=C))
        actual_identity=C.execution.checkout_identity
        self.stack.enter_context(mock.patch.object(C.execution,'checkout_identity',side_effect=lambda root:
            (self.default,self.tree_sha) if root==gate.ROOT else actual_identity(root)))
        actual_tree=C.inputs.full_tree
        self.stack.enter_context(mock.patch.object(C.inputs,'full_tree',side_effect=lambda root,*args:
            deepcopy(self.local) if root==gate.ROOT else actual_tree(root,*args)))
        self.stack.enter_context(mock.patch.object(C,'full_tree',side_effect=lambda adapter,oid:
            (self.tree_sha,deepcopy(self.local if oid==self.default else self.tree))))
        self.package=SimpleNamespace(validate_tree_wiring=lambda tree:C.ci_profile.RETAINED_SOURCE_GENERATION,
            load=gate.package_checks.load)
        self.stack.enter_context(mock.patch.object(C.producer,'_host_policy',return_value=SimpleNamespace(
            package_policy=lambda:self.package)))
        self.source={'kind':'reuse-current-controller-precheck-v1','controller_digest':'sha256:'+'1'*64,
            'base':self.base,'default':self.default}
        self.source_guard=self.stack.enter_context(mock.patch.object(C.producer,'reuse_source_context',return_value=self.source))

    def verify(self):
        return gate.verified_empty_sync(self.transport,config(),self.request,self.candidate,environment=self.env)

    def test_real_git_ordered_merge_and_native_app_yield_no_test_authority(self):
        result=self.verify();self.assertIsNotNone(result)
        self.assertEqual(result['kind'],'verified-empty-sync-v1')
        self.assertEqual(result['immutable']['candidate'],self.merge)
        self.assertEqual(result['immutable']['tree'],self.tree_sha)
        self.assertFalse(result['reusable']);self.assertFalse(result['qualification'])
        self.assertEqual(result['native']['job']['job_id'],702)
        self.assertGreaterEqual(self.source_guard.call_count,2)
        self.assertFalse(any('artifact' in endpoint for endpoint in self.calls))

    def test_actual_gate_topology_remains_mandatory_for_an_empty_candidate(self):
        actual=gate.classify_event({'repository':self.repository,'pull_request':self.pr},config(),self.api)
        self.assertEqual(actual,self.request)
        self.assertEqual(gate.commit_parents(gate.commit(self.api,REPOSITORY,self.merge)),
            (self.base,self.head))
        self.assertIsNotNone(self.verify())
        original=self.pr['head']['ref'];self.pr['head']['ref']='foreign/unconfigured-branch'
        self.assertIsNone(gate.classify_event({'repository':self.repository,'pull_request':self.pr},config(),self.api))
        self.pr['head']['ref']=original
        def wrong_parent(path,value):
            if path=='git/commits/'+self.merge:value['parents'].reverse()
            return value
        self.mutate=wrong_parent
        with self.assertRaises(gate.GateError):
            gate.classify_event({'repository':self.repository,'pull_request':self.pr},config(),self.api)
        self.assertIsNone(self.verify())

    def test_native_source_app_attempt_registration_and_diagnostics_never_use_empty(self):
        original=deepcopy(self.run)
        for kind in ('app','attempt','registration','run-source','job','suite','unprotected','merge-parents','diagnostics','recipe'):
            self.run=deepcopy(original)
            def mutate(path,value):
                if kind=='app' and path=='check-runs/702':value['app']['id']=42
                elif kind=='attempt' and path=='actions/runs/700/attempts/1':value['run_attempt']=2
                elif kind=='registration' and path=='actions/workflows/sync-validation.yml':value['id']=42
                elif kind=='run-source' and path.startswith('actions/runs/'):value['head_sha']='f'*40
                elif kind=='job' and path.endswith('/jobs'):value['jobs'].append(deepcopy(self.job))
                elif kind=='suite' and path=='check-suites/701':value['app']['id']=42
                elif kind=='unprotected' and path.startswith('branches/'):value['protected']=False
                elif kind=='merge-parents' and path=='git/commits/'+self.merge:value['parents'].reverse()
                elif kind=='diagnostics' and path=='pulls/42':value['labels']=[{'name':'android-long-diagnostics'}]
                return value
            self.mutate=mutate
            old=self.package.validate_tree_wiring
            if kind=='recipe':self.package.validate_tree_wiring=lambda tree:'npm-consumers-sync-ci-v1'
            with self.subTest(kind=kind):self.assertIsNone(self.verify())
            self.package.validate_tree_wiring=old
        self.mutate=lambda path,value:value
        for key in ('GITHUB_EVENT_NAME','GITHUB_SHA','GITHUB_JOB','GITHUB_WORKFLOW_SHA'):
            value=self.env[key];self.env[key]='foreign'
            with self.subTest(environment=key):self.assertIsNone(self.verify())
            self.env[key]=value

    def test_changed_native_bookend_source_and_nonempty_raw_tree_are_conservative(self):
        reads=0
        def move(path,value):
            nonlocal reads
            if path=='actions/workflows/sync-validation.yml':
                reads+=1
                if reads>1:value['state']='disabled_manually'
            return value
        self.mutate=move;self.assertIsNone(self.verify());self.mutate=lambda p,v:v
        self.source_guard.side_effect=ValueError('controller changed');self.assertIsNone(self.verify())
        self.source_guard.side_effect=None
        self.request=replace(self.request,changed_paths=('ios/new.cpp',))
        self.assertIsNone(self.verify())
        self.request=replace(self.request,changed_paths=(),repair_paths=('ios/repair.cpp',))
        self.assertIsNone(self.verify())
        self.request=replace(self.request,repair_paths=())
        (self.candidate/'ios/new.cpp').write_text('changed tree\n');self.git('add','.')
        self.git('commit','-qm','Actual nonempty source')
        self.assertIsNone(self.verify())


if __name__ == "__main__":
    unittest.main(verbosity=2)
