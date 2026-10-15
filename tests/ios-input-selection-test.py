#!/usr/bin/env python3
"""Exercise dormant iOS input selection against actual immutable Git histories."""

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("ios_application_inputs", ROOT / "tools/ios-build-qualification/inputs.py")
INPUTS = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = INPUTS
SPEC.loader.exec_module(INPUTS)


class ImmutableInputTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.git("init", "-q")
        self.git("config", "user.name", "Input fixture")
        self.git("config", "user.email", "input-fixture@example.invalid")
        self.git("config", "commit.gpgsign", "false")
        self.write("CMakeLists.txt", "project(InputFixture)\n")
        self.write("ios/build-ios.sh", "#!/bin/sh\n# Reviewed fixture entrypoint.\n")
        self.write("interface/src/main.cpp", "int main() { return 0; }\n")
        self.write("docs/README.md", "# Independent documentation\n")
        self.write("README.md", "# Independent root guide\n")
        self.write("tools/test-evidence/run.py", "# Independent host control plane\n")
        self.base = self.commit("Create reviewed input fixture")
        # A deliberately reviewed, isolated fixture boundary replaces the
        # production apple-ios anchor. No remote commit is needed to run tests.
        anchor = INPUTS.review_boundary(self.root, self.base)["boundary"]
        replacement = patch.object(INPUTS, "REVIEWED_BOUNDARY", anchor)
        replacement.start()
        self.addCleanup(replacement.stop)

    def git(self, *args, input=None):
        result = subprocess.run(["git", *args], cwd=self.root, input=input, text=True,
                                capture_output=True, check=True, timeout=30)
        return result.stdout.strip()

    def write(self, path, content):
        destination = self.root / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content)

    def commit(self, message, *, stage=True):
        if stage:
            self.git("add", "-A")
        self.git("commit", "-q", "--allow-empty", "-m", message)
        return self.git("rev-parse", "HEAD")

    def plan(self, candidate, base=None):
        return INPUTS.candidate_plan(self.root, base or self.base, candidate)

    def assert_independent(self, candidate, base=None):
        plan = self.plan(candidate, base)
        self.assertFalse(plan["requires_application_build"], plan)
        self.assertTrue(plan["exclusions_applicable"])
        self.assertEqual(plan["reason"], "independent-host-or-documentation-only")
        self.assertEqual(plan["base"]["fingerprint"], plan["candidate"]["fingerprint"])
        self.assertNotEqual(plan["base"]["revision"], plan["candidate"]["revision"])
        return plan

    def test_independent_host_content_is_not_executed_and_keeps_exact_provenance(self):
        self.write("tools/test-evidence/run.py", "raise RuntimeError('candidate must never execute')\n")
        candidate = self.commit("Change only an independent host tool")
        plan = self.assert_independent(candidate)
        self.assertEqual([change["path"] for change in plan["changes"]], ["tools/test-evidence/run.py"])
        self.assertEqual(plan["changes"][0]["kind"], "independent-host")
        self.assertEqual(plan["candidate"]["tree"], self.git("rev-parse", candidate + "^{tree}"))
        self.assertNotEqual(plan["base"]["tree"], plan["candidate"]["tree"])
        json.dumps(plan, allow_nan=False)

    def test_added_and_deleted_independent_files_are_observed(self):
        self.write("docs/new/guide.md", "# Added guide\n")
        self.write("tests/repository-checks-test.py", "# Added exact reviewed host test\n")
        added = self.commit("Add independent documentation and host test")
        plan = self.assert_independent(added)
        self.assertEqual({change["path"] for change in plan["changes"]},
                         {"docs/new/guide.md", "tests/repository-checks-test.py"})
        self.assertTrue(all(change["old"] is None for change in plan["changes"]))
        (self.root / "README.md").unlink()
        (self.root / "tools/test-evidence/run.py").unlink()
        removed = self.commit("Delete independent root guide and host tool")
        plan = self.assert_independent(removed, added)
        self.assertEqual({change["path"] for change in plan["changes"]},
                         {"README.md", "tools/test-evidence/run.py"})
        self.assertTrue(all(change["new"] is None for change in plan["changes"]))

    def test_reviewed_host_foundation_inventory_can_propagate_without_app_input_changes(self):
        for relative in INPUTS.INDEPENDENT_HOST_PATHS:
            destination = self.root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text("raise RuntimeError('candidate host code must never execute')\n")
            destination.chmod(0o755 if relative in INPUTS.INDEPENDENT_EXECUTABLE_HOST_PATHS else 0o644)
        plan = self.assert_independent(self.commit("Propagate reviewed host CI foundation inventory"))
        self.assertTrue(plan["changes"])
        self.assertTrue(all(change["kind"] == "independent-host" for change in plan["changes"]))
        self.assertTrue({"tests/android-ci-test.py", "tests/repository-health-test.py", "tests/run-project-tests.py",
                         "tools/repository-checks/check.py", "tools/repository-checks/android.py",
                         ".github/workflows/parent-qualification.yml"}.issubset(
                             {change["path"] for change in plan["changes"]}))

    def test_only_exact_reviewed_executable_host_modes_are_exempt(self):
        for relative in INPUTS.INDEPENDENT_EXECUTABLE_HOST_PATHS:
            with self.subTest(path=relative):
                self.git("checkout", "-q", "--detach", self.base)
                self.write(relative, "# Exact independent executable host check\n")
                (self.root / relative).chmod(0o755)
                executable = self.commit("Add reviewed executable host check")
                self.assert_independent(executable)
                (self.root / relative).chmod(0o644)
                changed_mode = self.commit("Change the reviewed host mode")
                plan = self.plan(changed_mode, executable)
                self.assertTrue(plan["requires_application_build"])
                self.assertEqual(plan["changes"][0]["kind"], "application-input")
        self.git("checkout", "-q", "--detach", self.base)
        (self.root / "tools/test-evidence/run.py").chmod(0o755)
        plan = self.plan(self.commit("Make a different independent host file executable"))
        self.assertTrue(plan["requires_application_build"])
        self.assertEqual(plan["changes"][0]["kind"], "application-input")

    def test_rename_inventory_retains_both_paths(self):
        self.git("mv", "docs/README.md", "docs/RENAMED.md")
        candidate = self.commit("Rename an independent guide")
        plan = self.assert_independent(candidate)
        self.assertEqual([change["path"] for change in plan["changes"]], ["docs/README.md", "docs/RENAMED.md"])
        self.assertIsNone(plan["changes"][0]["new"])
        self.assertIsNone(plan["changes"][1]["old"])

    def test_rename_into_packaged_source_requires_application_build(self):
        (self.root / "interface/resources").mkdir(parents=True)
        self.git("mv", "README.md", "interface/resources/README.md")
        candidate = self.commit("Move a guide into packaged resources")
        plan = self.plan(candidate)
        self.assertTrue(plan["requires_application_build"])
        self.assertEqual([change["path"] for change in plan["changes"]], ["README.md", "interface/resources/README.md"])
        self.assertEqual(plan["changes"][1]["kind"], "application-input")

    def test_application_and_build_inputs_of_every_extension_remain_relevant(self):
        paths = (
            "interface/resources/README.md", "scripts/README.md", "ios/resources/README.md",
            "resources/fonts/README.md", "resources/serverless/tutorial.json",
            "interface/resources/qml/Panel.qml", "libraries/shared/src/SharedUtil.cpp",
            "ios/ui/IOSTouchUiMetrics.mm", "ios/resources/PrivacyInfo.xcprivacy",
            "ios/resources/InterfaceE2EInfo.plist.in", "ios/versions.env", "ios/v8.env",
            "ios/conanfile.py", "ios/conan/profiles/ios-arm64", "ios/dependencies.json",
            "ios/tools/generate-sbom.py", "ios/ci/xcode-compiler-launcher.sh",
            "cmake/templates/BuildInfo.h.in", "tools/shadergen.py", "tools/jsdoc/config.json",
            "tools/CMakeLists.txt", "docs/CMakeLists.txt", "docs/new.bin", "android/README.md",
            "tests/device/contracts/audio/ios-shim-test.cpp", "tests/device/contracts/audio/fixture.json",
            "tests/device/contracts/tablet/fixtures/README.md", "ios/tests/fixtures/xcode-sccache/main.c",
            "tests/new-host-test.py", "tools/test-evidence/new-helper.py",
            "tools/sync-test-reuse/new.cmake", ".github/workflows/ios-integrated.yml",
            ".github/ios-build-qualification.json", "new/unknown-input",
        )
        for path in paths:
            with self.subTest(path=path):
                self.git("checkout", "-q", "--detach", self.base)
                self.write(path, "Changed application or unknown input\n")
                candidate = self.commit("Add an application or unknown input")
                plan = self.plan(candidate)
                self.assertTrue(plan["requires_application_build"])
                self.assertFalse(plan["exclusions_applicable"])
                self.assertEqual([(change["path"], change["kind"]) for change in plan["changes"]],
                                 [(path, "application-input")])
                self.assertNotEqual(plan["base"]["fingerprint"], plan["candidate"]["fingerprint"])

    def test_mixed_host_documentation_and_application_change_requires_build(self):
        self.write("docs/README.md", "# Updated documentation\n")
        self.write("tools/test-evidence/run.py", "# Updated host tool\n")
        self.write("interface/src/main.cpp", "int main() { return 1; }\n")
        plan = self.plan(self.commit("Change application with its host tooling"))
        self.assertTrue(plan["requires_application_build"])
        self.assertEqual(len(plan["changes"]), 3)

    def test_deleting_application_input_changes_fingerprint(self):
        (self.root / "interface/src/main.cpp").unlink()
        plan = self.plan(self.commit("Remove application source"))
        self.assertTrue(plan["requires_application_build"])
        self.assertEqual(plan["changes"][0]["kind"], "application-input")
        self.assertIsNone(plan["changes"][0]["new"])
        self.assertNotEqual(plan["base"]["fingerprint"], plan["candidate"]["fingerprint"])

    def test_executable_markdown_and_mode_only_changes_are_not_exempt(self):
        (self.root / "README.md").chmod(0o755)
        candidate = self.commit("Make a document executable")
        plan = self.plan(candidate)
        change = plan["changes"][0]
        self.assertTrue(plan["requires_application_build"])
        self.assertEqual(change["old"]["mode"], "100644")
        self.assertEqual(change["new"]["mode"], "100755")
        self.assertEqual(change["old"]["oid"], change["new"]["oid"])
        self.assertEqual(change["kind"], "application-input")
        (self.root / "README.md").chmod(0o644)
        ordinary = self.commit("Restore ordinary document mode")
        self.assertTrue(self.plan(ordinary, candidate)["requires_application_build"])

    def test_symlink_and_unchanged_link_referent_block_exclusions(self):
        (self.root / "interface/guide-link").symlink_to("../docs/README.md")
        linked = self.commit("Introduce an unproven source link")
        plan = self.plan(linked)
        self.assertTrue(plan["requires_application_build"])
        self.assertEqual(plan["candidate"]["nonregular_paths"], ["interface/guide-link"])
        # Even an anchor containing this link does not prove its referent
        # closure. A subsequent docs-only change must still build the app.
        with patch.object(INPUTS, "REVIEWED_BOUNDARY", INPUTS.review_boundary(self.root, linked)["boundary"]):
            self.write("docs/README.md", "# Changed through an unchanged link\n")
            candidate = self.commit("Change the unproven link referent")
            plan = self.plan(candidate, linked)
            self.assertTrue(plan["requires_application_build"])
            self.assertEqual(plan["reason"], "unproven-symlink-or-gitlink-closure")
            self.assertFalse(plan["exclusions_applicable"])
            self.assertNotEqual(plan["base"]["fingerprint"], plan["candidate"]["fingerprint"])

    def test_symlink_with_document_name_is_not_documentation(self):
        (self.root / "README.md").unlink()
        (self.root / "README.md").symlink_to("interface/src/main.cpp")
        plan = self.plan(self.commit("Replace root guide with a source link"))
        self.assertTrue(plan["requires_application_build"])
        self.assertEqual(plan["changes"][0]["new"]["mode"], "120000")
        self.assertEqual(plan["changes"][0]["kind"], "application-input")

    def test_gitlink_inventory_and_unknown_nested_closure_block_exclusions(self):
        self.git("update-index", "--add", "--cacheinfo", "160000," + self.base + ",vendor/dependency")
        linked = self.commit("Add an uninspected dependency gitlink", stage=False)
        plan = self.plan(linked)
        self.assertTrue(plan["requires_application_build"])
        self.assertEqual(plan["changes"][0]["new"]["mode"], "160000")
        self.assertEqual(plan["changes"][0]["new"]["type"], "commit")
        with patch.object(INPUTS, "REVIEWED_BOUNDARY", INPUTS.review_boundary(self.root, linked)["boundary"]):
            self.write("docs/README.md", "# Later independent change\n")
            self.git("add", "docs/README.md")
            candidate = self.commit("Change documentation with an uninspected gitlink", stage=False)
            plan = self.plan(candidate, linked)
            self.assertTrue(plan["requires_application_build"])
            self.assertEqual(plan["reason"], "unproven-symlink-or-gitlink-closure")

    def test_stale_reader_boundary_cannot_authorize_later_host_change(self):
        self.write("CMakeLists.txt", "project(InputFixture)\nfile(READ tools/test-evidence/run.py HOST_INPUT)\n")
        integrated = self.commit("Make the app read a formerly independent host file")
        self.write("tools/test-evidence/run.py", "# Now consumed by the application\n")
        candidate = self.commit("Change the newly consumed host input")
        plan = self.plan(candidate, integrated)
        self.assertEqual([change["path"] for change in plan["changes"]], ["tools/test-evidence/run.py"])
        self.assertTrue(plan["requires_application_build"])
        self.assertEqual(plan["reason"], "reader-boundary-not-reviewed")
        self.assertFalse(plan["base"]["exclusions_applicable"])
        self.assertFalse(plan["candidate"]["exclusions_applicable"])
        self.assertNotEqual(plan["base"]["fingerprint"], plan["candidate"]["fingerprint"])
        # Merely calculating a proposed refresh does not approve it.
        proposal = INPUTS.review_boundary(self.root, integrated)
        self.assertNotEqual(proposal["boundary"], INPUTS.REVIEWED_BOUNDARY)
        self.assertTrue(self.plan(candidate, integrated)["requires_application_build"])

    def test_both_trees_must_match_reviewed_reader_boundary(self):
        self.write("interface/src/main.cpp", "int main() { return 2; }\n")
        stale = self.commit("Change the reviewed application boundary")
        self.write("interface/src/main.cpp", "int main() { return 0; }\n")
        self.write("docs/README.md", "# Updated guide\n")
        restored = self.commit("Restore the reviewed graph with documentation")
        plan = self.plan(restored, stale)
        self.assertFalse(plan["base"]["exclusions_applicable"])
        self.assertTrue(plan["candidate"]["exclusions_applicable"])
        self.assertFalse(plan["exclusions_applicable"])
        self.assertTrue(plan["requires_application_build"])

    def test_unreviewed_default_boundary_is_conservative(self):
        self.write("docs/README.md", "# Independent change\n")
        candidate = self.commit("Change documentation")
        with patch.object(INPUTS, "REVIEWED_BOUNDARY", "sha256:" + "0" * 64):
            plan = self.plan(candidate)
            self.assertTrue(plan["requires_application_build"])
            self.assertEqual(plan["reason"], "reader-boundary-not-reviewed")
            self.assertNotEqual(plan["base"]["fingerprint"], plan["candidate"]["fingerprint"])

    def test_empty_inventory_and_git_metadata_only_commit_stay_full(self):
        candidate = self.commit("Change only commit metadata")
        plan = self.plan(candidate)
        self.assertTrue(plan["requires_application_build"])
        self.assertEqual(plan["reason"], "empty-change-inventory")
        self.assertEqual(plan["changes"], [])
        self.assertEqual(plan["base"]["tree"], plan["candidate"]["tree"])
        self.assertNotEqual(plan["base"]["revision"], plan["candidate"]["revision"])
        self.assertEqual(plan["base"]["fingerprint"], plan["candidate"]["fingerprint"])
        self.assertTrue(self.plan(self.base)["requires_application_build"])

    def test_worktree_index_and_untracked_state_do_not_supply_inputs(self):
        self.write("docs/README.md", "# Committed documentation\n")
        candidate = self.commit("Change only documentation")
        expected = self.plan(candidate)
        self.write("interface/src/main.cpp", "Unstaged application change\n")
        self.write("ios/build-ios.sh", "Staged application change\n")
        self.git("add", "ios/build-ios.sh")
        self.write("unknown/untracked.cpp", "Untracked application change\n")
        self.assertEqual(self.plan(candidate), expected)
        self.assertFalse(expected["requires_application_build"])

    def test_replacement_refs_do_not_change_immutable_source_identity(self):
        original = INPUTS.read_snapshot(self.root, self.base)
        self.write("interface/src/main.cpp", "int main() { return 9; }\n")
        replacement = self.commit("Create a replacement commit")
        self.git("replace", self.base, replacement)
        self.assertNotEqual(self.git("rev-parse", self.base + "^{tree}"), original.tree)
        self.assertEqual(INPUTS.read_snapshot(self.root, self.base), original)

    def test_refs_tags_missing_objects_and_malformed_ids_cannot_supply_candidate(self):
        self.git("tag", "-a", "-m", "Annotated input fixture", "fixture-tag", self.base)
        tag = self.git("rev-parse", "fixture-tag")
        for invalid in ("HEAD", "fixture-tag", tag, "-h", "0" * 40, "A" * 40, "a" * 39, None, 1):
            with self.subTest(revision=invalid), self.assertRaises(INPUTS.InputError):
                INPUTS.read_snapshot(self.root, invalid)

    def test_malformed_or_truncated_inventory_fails_closed(self):
        original = INPUTS._git
        records = (
            b"100644 blob " + b"a" * 40 + b"\tdocs/README.md",  # Missing NUL terminator.
            b"100644 blob " + b"a" * 40 + b"\t../README.md\0",
            b"040000 tree " + b"a" * 40 + b"\tdocs\0",  # Recursive inventory must contain leaves.
            b"100644 blob " + b"a" * 40 + b"\t.\0",
            b"100644 blob " + b"a" * 40 + b"\tdocs/\xff.md\0",
            (b"100644 blob " + b"a" * 40 + b"\tdocs/README.md\0") * 2,
        )
        for raw in records:
            def invoke(repository, *arguments):
                return raw if arguments[0] == "ls-tree" else original(repository, *arguments)
            with self.subTest(raw=raw), patch.object(INPUTS, "_git", side_effect=invoke), \
                    self.assertRaises(INPUTS.InputError):
                self.plan(self.base)

    def test_fingerprint_policy_changes_when_trusted_boundary_changes(self):
        before = INPUTS.input_fingerprint(self.root, self.base)
        with patch.object(INPUTS, "REVIEWED_REVISION", "b" * 40):
            after = INPUTS.input_fingerprint(self.root, self.base)
        self.assertEqual(before["boundary"], after["boundary"])
        self.assertNotEqual(before["fingerprint"], after["fingerprint"])


if __name__ == "__main__":
    unittest.main()
