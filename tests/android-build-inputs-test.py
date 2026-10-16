#!/usr/bin/env python3
"""Check dormant APK input planning through real immutable Git histories."""

import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "tools/repository-checks/android-build-inputs.py"
SPEC = importlib.util.spec_from_file_location("android_apk_source_planning", HELPER)
APK = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(APK)


METADATA_LEAVES = (
    'tools/repository-checks/metadata_context.py',
    'tools/repository-checks/workflows/metadata-edits/pr-metadata-context.yml',
    'tools/repository-checks/workflows/metadata-edits/codeql-metadata.yml',
    '.github/workflows/pr-metadata-context.yml',
    'tools/repository-checks/workflows/producers/legacy/repository-checks-protected-ci-v1.yml',
    'tools/repository-checks/workflows/producers/legacy/parent-qualification-postmerge-v1.yml',
    'tools/repository-checks/workflows/producers/legacy/protected-project-tests-ci37-v1.yml',
)


class MetadataLeafClassificationTests(unittest.TestCase):
    def test_only_exact_ordinary_metadata_leaves_are_independent_android_inputs(self):
        for path in METADATA_LEAVES:
            self.assertEqual(APK.INDEPENDENT_HOST_PATHS[path], '100644')
            self.assertEqual(APK._kind(APK.inventory.Entry(path, '100644', 'blob', 'a' * 40)),
                             'independent-host')
            for mode, kind in [('100755', 'blob'), ('120000', 'blob'), ('160000', 'commit'),
                               ('040000', 'tree'), ('100644', 'commit')]:
                with self.subTest(path=path, mode=mode, kind=kind):
                    self.assertEqual(APK._kind(APK.inventory.Entry(path, mode, kind, 'a' * 40)),
                                     'application-input')
            for neighbor in (path + '.neighbor', path.upper(), path.replace('/metadata', '/metadata-neighbor', 1)):
                if neighbor == path:
                    continue
                with self.subTest(path=path, neighbor=neighbor):
                    self.assertEqual(APK._kind(APK.inventory.Entry(neighbor, '100644', 'blob', 'a' * 40)),
                                     'application-input')


class ApkInputsTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.git("init", "-q")
        self.git("config", "user.name", "APK input fixture")
        self.git("config", "user.email", "apk-inputs@example.invalid")
        self.git("config", "commit.gpgsign", "false")
        self.write("CMakeLists.txt", "project(ApkFixture)\n")
        self.write("android/phone/build.sh", "#!/bin/sh\nexit 1\n")
        self.write("android/vr/pico/build.sh", "#!/bin/sh\nexit 1\n")
        self.write("interface/src/main.cpp", "int main() { return 0; }\n")
        self.write("docs/README.md", "# Independent guide\n")
        self.write("README.md", "# Independent root guide\n")
        self.write("tools/test-evidence/run.py", "# Independent host controller\n")
        self.write("tests/run-project-tests.py", "#!/usr/bin/env python3\n")
        (self.root / "tests/run-project-tests.py").chmod(0o755)
        self.write("server-console/package-lock.json", '{"lockfileVersion":3}\n')
        self.write("tools/jsdoc/package-lock.json", '{"lockfileVersion":3}\n')
        self.base = self.commit("Create reviewed isolated APK reader fixture")
        # These tiny fixture graphs are deliberately reviewed independently.
        # Tests never bless an arbitrary production tree or need remote history.
        contracts = copy.deepcopy(APK.VARIANTS)
        for variant in contracts:
            contracts[variant]["reviewed_boundary"] = APK.review_boundary(
                self.root, self.base, variant)["boundary"]
        replacement = patch.object(APK, "VARIANTS", contracts)
        replacement.start()
        self.addCleanup(replacement.stop)

    def git(self, *args, input=None):
        return subprocess.run(["git", *args], cwd=self.root, input=input, text=True,
                              capture_output=True, check=True, timeout=30).stdout.strip()

    def write(self, path, content):
        destination = self.root / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content)

    def commit(self, message, *, stage=True):
        if stage:
            self.git("add", "-A")
        self.git("commit", "-q", "--allow-empty", "-m", message)
        return self.git("rev-parse", "HEAD")

    def plan(self, candidate, variant="phone", base=None):
        return APK.candidate_plan(self.root, base or self.base, candidate, variant)

    def independent(self, candidate, *, base=None):
        for variant in APK.VARIANTS:
            plan = self.plan(candidate, variant, base)
            self.assertFalse(plan["requires_source_build"], plan)
            self.assertTrue(plan["exclusions_applicable"])
            self.assertEqual(plan["base"]["source_fingerprint"], plan["candidate"]["source_fingerprint"])
            self.assertEqual(plan["reason"], "independent-host-documents-or-npm-only")
        return plan

    def test_host_changes_are_data_never_candidate_execution(self):
        self.write("tools/test-evidence/run.py", "raise RuntimeError('must never execute candidate')\n")
        candidate = self.commit("Change an independent host helper")
        plan = self.independent(candidate)
        self.assertEqual(plan["changes"][0]["kind"], "independent-host")
        self.assertEqual(plan["candidate"]["revision"], candidate)
        self.assertEqual(plan["candidate"]["tree"], self.git("rev-parse", candidate + "^{tree}"))
        self.assertNotEqual(plan["base"]["tree"], plan["candidate"]["tree"])

    def test_seven_metadata_controller_recipe_leaves_preserve_both_android_reader_boundaries(self):
        for path in METADATA_LEAVES:
            self.write(path, '# Fixed independent metadata source fixture; never execute\n')
        plan = self.independent(self.commit('Add the seven exact metadata controller and recipe leaves'))
        self.assertEqual({item['path'] for item in plan['changes']}, set(METADATA_LEAVES))
        self.assertEqual({item['kind'] for item in plan['changes']}, {'independent-host'})

    def test_exact_npm_locks_and_host_documentation_preserve_source_identity(self):
        for path in APK.INDEPENDENT_NPM_PATHS:
            self.write(path, '{"lockfileVersion":3,"reviewedChange":true}\n')
        self.write("docs/README.md", "# Updated guide\n")
        self.write("tests/repository-checks-test.py", "# Required independently\n")
        plan = self.independent(self.commit("Update independent npm and host inputs"))
        self.assertEqual({change["kind"] for change in plan["changes"]},
                         {"independent-npm", "independent-documentation", "independent-host"})

    def test_packaged_npm_metadata_is_not_an_extension_exemption(self):
        for path in ("scripts/developer/tests/unit_tests/package.json",
                     "scripts/communityScripts/libraries/materialdesignicons/package.json",
                     "unpublishedScripts/marketplace/doppleganger-attachments/package.json",
                     "android/phone/package-lock.json", "new/package-lock.json"):
            with self.subTest(path=path):
                self.git("checkout", "-q", "--detach", self.base)
                self.write(path, '{"changed":true}\n')
                candidate = self.commit("Change packaged or unknown npm metadata")
                for variant in APK.VARIANTS:
                    self.assertTrue(self.plan(candidate, variant)["requires_source_build"])

    def test_native_java_gradle_conan_resources_and_unknown_inputs_require_rebuild(self):
        paths = (
            "libraries/shared/src/SharedUtil.cpp", "libraries/shared/src/SharedUtil.h", "QCoreApplication",
            "android/common/libraries/qt/src/main/java/org/qtproject/qt5/android/QtNative.java",
            "security/redaction/java/org/overte/security/Sanitizer.java",
            "android/phone/apps/phoneInterface/src/main/java/org/overte/phone/MainActivity.java",
            "android/vr/pico/apps/picoInterface/src/main/AndroidManifest.xml",
            "android/phone/apps/phoneInterface/src/main/res/values/strings.xml",
            "android/vr/pico/apps/picoInterface/src/main/assets/runtime.json",
            "android/phone/apps/phoneInterface/build.gradle", "android/vr/pico/settings.gradle",
            "android/common/gradle/wrapper/gradle-wrapper.properties", "android/phone/gradle.properties",
            "android/vr/pico/cmake/pico-source-bootstrap.cmake", "cmake/macros/TargetQt.cmake",
            "conanfile.py", "android/common/conan/profiles/phone-arm64-16k",
            "android/common/conan/patches/qt-pico-android-runtime.patch",
            "android/phone/fdroid/manifests/recipe-exports/index.json",
            "android/vr/pico/release/qualified-reuse-v3.py", "provenance/conan_sources.py",
            "android/phone/tests/check-phone-apk-16k.sh", "android/vr/pico/ci/verify-pico-apk.py",
            "tools/dependency-releases/check.py", ".github/dependency-releases.json",
            "interface/resources/qml/Panel.qml", "interface/resources/README.md", "scripts/README.md",
            "tools/jsdoc/config.json", "docs/toolchain.cmake", "docs/data.bin", "android/README.md",
            "tests/device/fixture/scene.json", "tests/device/fixture/README.md",
            ".github/workflows/android-phone-build.yml", ".github/workflows/pico4-build.yml",
            "new/unknown", "tools/test-evidence/unreviewed-helper.py", "tests/new-host-test.py",
        )
        for path in paths:
            with self.subTest(path=path):
                self.git("checkout", "-q", "--detach", self.base)
                self.write(path, "Changed build/source/unknown input\n")
                candidate = self.commit("Add a conservative application input")
                for variant in APK.VARIANTS:
                    plan = self.plan(candidate, variant)
                    self.assertTrue(plan["requires_source_build"])
                    self.assertFalse(plan["exclusions_applicable"])
                    self.assertEqual(plan["changes"][0]["kind"], "application-input")
                    self.assertNotEqual(plan["base"]["source_fingerprint"], plan["candidate"]["source_fingerprint"])

    def test_each_product_entrypoint_is_a_reader(self):
        for path in ("android/phone/build.sh", "android/vr/pico/build.sh"):
            with self.subTest(path=path):
                self.git("checkout", "-q", "--detach", self.base)
                self.write(path, "#!/bin/sh\n# New reader\n")
                candidate = self.commit("Change product build entrypoint")
                self.assertTrue(self.plan(candidate)["requires_source_build"])

    def test_added_deleted_and_renamed_independent_inputs_are_complete(self):
        self.write("docs/new/guide.md", "# New independent guide\n")
        added = self.commit("Add independent guide")
        self.assertIsNone(self.independent(added)["changes"][0]["old"])
        self.git("mv", "docs/new/guide.md", "docs/new/renamed.md")
        renamed = self.commit("Rename independent guide")
        self.assertEqual([item["path"] for item in self.independent(renamed, base=added)["changes"]],
                         ["docs/new/guide.md", "docs/new/renamed.md"])
        (self.root / "server-console/package-lock.json").unlink()
        deleted = self.commit("Delete independent npm lock")
        self.assertIsNone(self.independent(deleted, base=renamed)["changes"][0]["new"])

    def test_native_deletion_and_rename_into_resources_require_build(self):
        (self.root / "interface/src/main.cpp").unlink()
        removed = self.commit("Remove native source")
        self.assertTrue(self.plan(removed)["requires_source_build"])
        self.assertIsNone(self.plan(removed)["changes"][0]["new"])
        self.git("checkout", "-q", "--detach", self.base)
        (self.root / "interface/resources").mkdir(parents=True)
        self.git("mv", "README.md", "interface/resources/README.md")
        moved = self.commit("Move documentation into packaged resources")
        self.assertTrue(self.plan(moved)["requires_source_build"])
        self.assertEqual(len(self.plan(moved)["changes"]), 2)

    def test_mixed_independent_and_application_change_cannot_hide_source(self):
        self.write("tools/jsdoc/package-lock.json", '{"update":true}\n')
        self.write("tools/test-evidence/run.py", "# Host change\n")
        self.write("interface/src/main.cpp", "int main() { return 1; }\n")
        candidate = self.commit("Combine npm host and native changes")
        plan = self.plan(candidate)
        self.assertTrue(plan["requires_source_build"])
        self.assertEqual(len(plan["changes"]), 3)

    def test_exact_executable_shared_runner_mode_and_mode_transitions(self):
        self.write("tests/run-project-tests.py", "#!/usr/bin/env python3\n# Host-only change\n")
        candidate = self.commit("Change executable reviewed host runner")
        self.independent(candidate)
        (self.root / "tests/run-project-tests.py").chmod(0o644)
        mode = self.commit("Change runner mode")
        for variant in APK.VARIANTS:
            plan = self.plan(mode, variant, candidate)
            self.assertTrue(plan["requires_source_build"])
            change = plan["changes"][0]
            self.assertEqual((change["old"]["mode"], change["new"]["mode"]), ("100755", "100644"))
            self.assertEqual(change["old"]["oid"], change["new"]["oid"])

    def test_executable_docs_npm_and_ordinary_host_mode_are_not_exempt(self):
        for path in ("README.md", "server-console/package-lock.json", "tools/test-evidence/run.py"):
            with self.subTest(path=path):
                self.git("checkout", "-q", "--detach", self.base)
                (self.root / path).chmod(0o755)
                self.assertTrue(self.plan(self.commit("Make an independent input executable"))["requires_source_build"])

    def test_reader_then_host_change_remains_unreviewed_in_both_trees(self):
        self.write("CMakeLists.txt", "project(ApkFixture)\nfile(READ server-console/package-lock.json APP_INPUT)\n")
        integrated = self.commit("Introduce a reader of a formerly independent npm lock")
        self.write("server-console/package-lock.json", '{"nowReadByApp":true}\n')
        candidate = self.commit("Change formerly independent npm input")
        for variant in APK.VARIANTS:
            plan = self.plan(candidate, variant, integrated)
            self.assertTrue(plan["requires_source_build"])
            self.assertEqual(plan["reason"], "reader-boundary-not-reviewed")
            self.assertFalse(plan["base"]["exclusions_applicable"])
            self.assertFalse(plan["candidate"]["exclusions_applicable"])
            self.assertNotEqual(plan["base"]["source_fingerprint"], plan["candidate"]["source_fingerprint"])
            self.assertNotEqual(APK.review_boundary(self.root, integrated, variant)["boundary"],
                                APK.VARIANTS[variant]["reviewed_boundary"])
            self.assertTrue(self.plan(candidate, variant, integrated)["requires_source_build"])

    def test_restoring_candidate_reader_does_not_bless_unreviewed_base(self):
        self.write("interface/src/main.cpp", "int main() { return 2; }\n")
        stale = self.commit("Change reviewed reader graph")
        self.write("interface/src/main.cpp", "int main() { return 0; }\n")
        self.write("README.md", "# Changed guide\n")
        restored = self.commit("Restore app graph and update guide")
        plan = self.plan(restored, base=stale)
        self.assertFalse(plan["base"]["exclusions_applicable"])
        self.assertTrue(plan["candidate"]["exclusions_applicable"])
        self.assertTrue(plan["requires_source_build"])

    def test_unchanged_symlink_blocks_later_referent_change_even_with_proposed_anchor(self):
        (self.root / "interface/guide-link").symlink_to("../docs/README.md")
        linked = self.commit("Add an unproven source alias")
        self.assertEqual(self.plan(linked)["candidate"]["nonregular_paths"], ["interface/guide-link"])
        contracts = copy.deepcopy(APK.VARIANTS)
        for variant in contracts:
            contracts[variant]["reviewed_boundary"] = APK.review_boundary(self.root, linked, variant)["boundary"]
        self.write("docs/README.md", "# Changed link referent\n")
        candidate = self.commit("Change docs through an unchanged app symlink")
        with patch.object(APK, "VARIANTS", contracts):
            plan = self.plan(candidate, base=linked)
            self.assertTrue(plan["requires_source_build"])
            self.assertEqual(plan["reason"], "unproven-symlink-or-gitlink-closure")

    def test_gitlink_and_case_unknown_paths_do_not_receive_exemptions(self):
        self.git("update-index", "--add", "--cacheinfo", "160000," + self.base + ",vendor/dependency")
        candidate = self.commit("Add uninspected submodule", stage=False)
        plan = self.plan(candidate)
        self.assertTrue(plan["requires_source_build"])
        self.assertEqual(plan["changes"][0]["new"]["type"], "commit")
        self.git("checkout", "-q", "--detach", self.base)
        self.write("Server-console/package-lock.json", "{}\n")
        self.assertTrue(self.plan(self.commit("Add unknown case variant"))["requires_source_build"])

    def test_variants_never_share_fingerprint_or_dependency_contract(self):
        phone = APK.input_fingerprint(self.root, self.base, "phone")
        pico = APK.input_fingerprint(self.root, self.base, "pico")
        self.assertNotEqual(phone["source_fingerprint"], pico["source_fingerprint"])
        self.assertEqual(APK.VARIANTS["phone"]["target_sdk"], 36)
        self.assertEqual(APK.VARIANTS["pico"]["target_sdk"], 35)
        self.assertNotEqual(APK.VARIANTS["phone"]["dependency_contract"], APK.VARIANTS["pico"]["dependency_contract"])
        for variant in (None, 1, "release", "phone-emulator", "fdroid"):
            with self.subTest(variant=variant), self.assertRaises(APK.InputError):
                self.plan(self.base, variant)

    def test_source_plan_never_claims_external_dependency_or_apk_success(self):
        self.write("README.md", "# Changed independent guide\n")
        plan = self.independent(self.commit("Change independent docs"))
        self.assertEqual(plan["build_evidence"], "not-provided")
        self.assertEqual(plan["artifact_reuse"], "not-authorized")
        self.assertEqual(plan["workflow_dispatch"], "not-performed")
        self.assertEqual(len(plan["verification_required"]), 6)
        self.assertTrue(all("required" not in key or key == "verification_required" for key in plan))
        json.dumps(plan, allow_nan=False)

    def test_empty_inventory_and_commit_metadata_are_not_build_proof(self):
        candidate = self.commit("Change only commit metadata")
        plan = self.plan(candidate)
        self.assertTrue(plan["requires_source_build"])
        self.assertEqual(plan["reason"], "empty-change-inventory-requires-verification")
        self.assertEqual(plan["base"]["tree"], plan["candidate"]["tree"])
        self.assertNotEqual(plan["base"]["revision"], plan["candidate"]["revision"])

    def test_candidate_worktree_index_and_replacement_refs_do_not_supply_source(self):
        self.write("README.md", "# Committed guide\n")
        candidate = self.commit("Change independent docs")
        expected = self.plan(candidate)
        self.write("interface/src/main.cpp", "Staged different app source\n")
        self.git("add", "interface/src/main.cpp")
        self.write("CMakeLists.txt", "Unstaged build graph\n")
        self.write("new-untracked.py", "raise RuntimeError('do not import')\n")
        self.assertEqual(self.plan(candidate), expected)
        self.git("reset", "--hard", "-q", candidate)
        self.write("interface/src/main.cpp", "int main() { return 9; }\n")
        replacement = self.commit("Prepare replacement Git object")
        self.git("replace", candidate, replacement)
        self.assertEqual(self.plan(candidate), expected)

    def test_missing_truncated_or_mutable_inventory_fails_closed(self):
        for revision in ("HEAD", "0" * 40, "a" * 39, "A" * 40, None):
            with self.subTest(revision=revision), self.assertRaises(APK.InputError):
                self.plan(revision)
        original = APK.inventory._git
        def truncated(repository, *args):
            return b"100644 blob " + b"a" * 40 + b"\tREADME.md" if args[0] == "ls-tree" else original(repository, *args)
        with patch.object(APK.inventory, "_git", side_effect=truncated), self.assertRaises(APK.InputError):
            self.plan(self.base)

    def test_cli_unsupported_inventory_never_prints_green_plan(self):
        result = subprocess.run([sys.executable, str(HELPER), "--repository", str(self.root),
                                 "--base", self.base, "--candidate", "HEAD", "--variant", "phone"],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertIn("verification required", result.stderr)


if __name__ == "__main__":
    unittest.main()
