#!/usr/bin/env python3
"""Security and contract tests for parent qualification reuse."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
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
                        with self.assertRaisesRegex(gate.EvidenceError, "qualified parent-delta input changed"):
                            gate.verify_evidence(object(), settings, request(parent_changed_paths=(relative,)))
                    unchanged = changed


class EvidenceContracts(unittest.TestCase):
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

    def test_historical_target_input_outside_parent_delta_does_not_invalidate_reuse(self):
        _, tree = evidence_fixture()
        path = "tests/run-project-tests.py"
        changed = dict(tree)
        changed[path] = dict(changed[path], sha="f" * 40)
        self.assertEqual(
            self.verify(
                merge_tree=changed,
                sync_request=request(parent_changed_paths=("interface/example.cpp",)),
            )["parent_commit"],
            PARENT,
        )

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
                "base": {"ref": base, "sha": base_sha},
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

    def test_retired_desktop_targets_and_scopes_cannot_receive_sync_reuse(self):
        for platform in ("linux", "windows"):
            for base, head in ((platform + "-main", "main"),
                               (platform + "-main", f"reconcile/{platform}/refresh"),
                               ("android-main", platform + "-main"),
                               ("android-main", f"reconcile/{platform}/refresh")):
                with self.subTest(base=base, head=head):
                    self.assertIsNone(gate.classify_event(self.event(base, head), config(), MappingApi()))

    def test_executable_docs_and_code_renames_keep_full_qualification(self):
        for change in ({"filename": "docs/helper.py"},
                       {"filename": "docs/helper.md", "previous_filename": "tools/helper.py"}):
            with self.subTest(change=change), \
                 mock.patch.object(gate, "branch_sha", side_effect=[BASE, PARENT, BASE, PARENT]), \
                 mock.patch.object(gate, "commit", side_effect=[{"sha": PARENT}, {"sha": MERGE, "parents": [{"sha": BASE}, {"sha": PARENT}]}]), \
                 mock.patch.object(gate, "compare_merge_base", return_value=HEAD), \
                 mock.patch.object(gate, "compare_files", return_value=(HEAD, {change["filename"]})), \
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


class InspectionContracts(unittest.TestCase):
    def inspect_request(self, sync_request, evidence_error=None):
        with mock.patch.object(gate, "load_config", return_value=config()), \
             mock.patch.object(gate, "GitHubApi"), \
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
        self.assertEqual(set(differential.PROFILES) - {"documentation"}, {
            "android-family", "android-phone", "android-vr", "android-pico",
            "apple-family", "apple-ios",
        })
        self.assertTrue(all(differential.PROFILES[name] for name in differential.PROFILES if name != "documentation"))


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


if __name__ == "__main__":
    unittest.main(verbosity=2)
