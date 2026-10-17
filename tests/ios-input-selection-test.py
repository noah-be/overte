#!/usr/bin/env python3
"""Exercise dormant iOS input selection against actual immutable Git histories."""

import importlib.util
from copy import deepcopy
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


REVIEWED_ANDROID_CI_PATHS = (
    ".github/workflows/android-required.yml",
    ".github/android-owner-transfer.json",
    "tests/android-owner-transfer-test.py",
    "tools/repository-checks/android_handoff.py",
    "tools/repository-checks/workflows/android-owned/android-required.yml",
    "tools/repository-checks/workflows/android-owned/handoff/.github/workflows/android-tests.yml",
    "tools/repository-checks/workflows/android-owned/handoff/.github/workflows/android-vr-tests.yml",
    "tools/repository-checks/workflows/android-owned/handoff/android/common/tests/android-workflow-contract-test.py",
    "tools/repository-checks/workflows/android-owned/handoff/android/common/tests/ci/test_ci_contract.py",
    "tools/repository-checks/workflows/android-owned/handoff/android/common/tests/ci/validate_ci_contract.py",
    "tools/repository-checks/workflows/android-owned/project-tests.yml",
    "tools/repository-checks/workflows/android-owned/repository-checks.yml",
    "tools/repository-checks/workflows/android-owned/handoff/android/phone/tests/phone-release-metadata-test.py",
)


REVIEWED_SANDBOX_CI_PATHS = (
    ".github/shared-sandbox.json",
    ".github/workflows/shared-sandbox-host-diagnostic.yml",
    "tools/repository-checks/workflows/shared-sandbox-host-diagnostic.yml",
    "tools/test-evidence/sandbox.py",
    "tools/test-evidence/sandbox-test.py",
    "tools/test-evidence/sandbox_host.py",
    "tools/test-evidence/sandbox-host-test.py",
    "tools/test-evidence/sandbox_host_fixture.py",
    "tools/test-evidence/sandbox_probe.py",
    "tools/test-evidence/sandbox_shared.py",
    "tools/test-evidence/postmerge.py",
    "tools/repository-checks/workflows/producers/repository-checks.yml",
    "tools/repository-checks/workflows/producers/parent-qualification.yml",
    "tools/repository-checks/workflows/producers/protected-project-tests-android-platform.yml",
    "tools/repository-checks/workflows/producers/parent-qualification-android-platform.yml",
)


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

    def test_exact_artifact_identity_launcher_add_edit_delete_are_app_independent(self):
        relative = "tests/device/run_artifact_identity.py"
        self.write(relative, "raise RuntimeError('candidate helper must never execute')\n")
        added = self.commit("Add the exact Linux shared Device launcher")
        plan = self.assert_independent(added)
        self.assertEqual([(change["path"], change["kind"]) for change in plan["changes"]],
                         [(relative, "independent-host")])
        self.write(relative, "raise RuntimeError('changed helper remains independently owned')\n")
        changed = self.commit("Edit the exact Linux shared Device launcher")
        self.assert_independent(changed, added)
        (self.root / relative).unlink()
        removed = self.commit("Remove the independently required Device launcher")
        self.assert_independent(removed, changed)

    def test_artifact_identity_launcher_exception_keeps_modes_neighbors_and_historical_readers(self):
        relative = "tests/device/run_artifact_identity.py"
        for mode in ("100755", "120000"):
            with self.subTest(mode=mode):
                self.git("checkout", "-q", "--detach", self.base)
                self.write(relative, "# Unexpected launcher mode\n")
                if mode == "120000":
                    (self.root / relative).unlink()
                    (self.root / relative).symlink_to("other.py")
                else:
                    (self.root / relative).chmod(0o755)
                self.assertTrue(self.plan(self.commit("Reject unreviewed launcher mode"))["requires_application_build"])
        for changes in ({"tests/device/run_artifact_identity_extra.py": "# Unknown neighbor\n"},
                        {relative: "# Exact helper\n", "interface/src/main.cpp": "int main() { return 1; }\n"}):
            with self.subTest(paths=sorted(changes)):
                self.git("checkout", "-q", "--detach", self.base)
                for path, content in changes.items():
                    self.write(path, content)
                self.assertTrue(self.plan(self.commit("Keep unknown and mixed product inputs required"))["requires_application_build"])
        self.git("checkout", "-q", "--detach", self.base)
        self.write("CMakeLists.txt", "project(InputFixture)\nfile(GLOB INPUTS tests/device/*.py)\n")
        historical = self.commit("Introduce an unreviewed historical helper reader")
        self.write(relative, "# A later helper edit cannot hide reader drift\n")
        plan = self.plan(self.commit("Change helper after historical application reader drift"), historical)
        self.assertTrue(plan["requires_application_build"])
        self.assertEqual(plan["reason"], "reader-boundary-not-reviewed")

    def test_exact_doctor_cli_is_executable_ci_with_a_required_owner(self):
        relative = "tools/repository-health/check.py"
        self.write(relative, "raise RuntimeError('the iOS selector must not execute Doctor')\n")
        (self.root / relative).chmod(0o755)
        added = self.commit("Add the exact independent executable Doctor CLI")
        self.assert_independent(added)
        self.write(relative, "raise RuntimeError('changed Doctor still belongs to CI')\n")
        changed = self.commit("Change only the independent executable Doctor CLI")
        self.assert_independent(changed, added)
        (self.root / relative).unlink()
        removed = self.commit("Remove Doctor without changing application inputs")
        self.assert_independent(removed, changed)
        # Its deletion is still a failure of the required CLI owner, rather
        # than a reason to compile an unrelated iOS application.
        registry = json.loads((ROOT / ".github/test-suites.json").read_text())
        owner = registry["suites"]["repository-doctor"]
        self.assertEqual(owner["command"], ["python", "tests/repository-health-test.py"])
        self.assertEqual(owner["layer"], "quick")
        self.assertEqual(owner["closure"]["kind"], "repository")
        checker_test = (ROOT / "tests/repository-health-test.py").read_text()
        self.assertIn('CHECKER = ROOT / "tools/repository-health/check.py"', checker_test)
        self.assertIn('SPEC.loader.exec_module(HEALTH)', checker_test)

    def test_doctor_exception_keeps_modes_neighbors_and_historical_readers_bound(self):
        relative = "tools/repository-health/check.py"
        for mode in ("100644", "120000"):
            with self.subTest(mode=mode):
                self.git("checkout", "-q", "--detach", self.base)
                self.write(relative, "# Doctor fixture\n")
                if mode == "120000":
                    (self.root / relative).unlink()
                    (self.root / relative).symlink_to("other.py")
                else:
                    (self.root / relative).chmod(0o644)
                self.assertTrue(self.plan(self.commit("Reject nonreviewed Doctor mode"))["requires_application_build"])
        for neighbor in ("tools/repository-health/other.py", "tools/repository-health/check-extra.py"):
            with self.subTest(neighbor=neighbor):
                self.git("checkout", "-q", "--detach", self.base)
                self.write(neighbor, "# An unreviewed reader remains an application input\n")
                self.assertTrue(self.plan(self.commit("Reject unknown Doctor neighbor"))["requires_application_build"])
        self.git("checkout", "-q", "--detach", self.base)
        (self.root / "CMakeLists.txt").unlink()
        self.assertTrue(self.plan(self.commit("Reject missing genuine application reader"))["requires_application_build"])
        self.git("checkout", "-q", "--detach", self.base)
        self.write("CMakeLists.txt", "include(tools/repository-health/check.py)\n")
        historical = self.commit("Introduce an unreviewed historical Doctor reader")
        self.write(relative, "# Later Doctor-only edit cannot hide the earlier reader\n")
        (self.root / relative).chmod(0o755)
        candidate = self.commit("Change Doctor after historical application reader drift")
        plan = self.plan(candidate, historical)
        self.assertTrue(plan["requires_application_build"])
        self.assertEqual(plan["reason"], "reader-boundary-not-reviewed")

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
        self.assertTrue(set(REVIEWED_ANDROID_CI_PATHS).issubset(INPUTS.INDEPENDENT_HOST_PATHS))
        self.assertTrue(set(REVIEWED_SANDBOX_CI_PATHS).issubset(INPUTS.INDEPENDENT_HOST_PATHS))
        self.assertTrue(all(change["kind"] == "independent-host" for change in plan["changes"]))
        self.assertTrue({"tests/android-ci-test.py", "tests/repository-health-test.py", "tests/run-project-tests.py",
                         "tools/repository-checks/check.py", "tools/repository-checks/android.py",
                         ".github/workflows/parent-qualification.yml",
                         "tools/repository-checks/workflows/sync-ci-selection.yml",
                         "tools/repository-checks/workflows/metadata-edits/repository-checks.yml",
                         "tools/repository-checks/workflows/metadata-edits/codeql.yml",
                         "tools/repository-checks/workflows/metadata-edits/codeql-pinned.yml",
                         "tools/repository-checks/workflows/metadata-edits/sync-test-reuse.yml",
                         "tools/repository-checks/workflows/host/parent-qualification.yml"}.issubset(
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
        for relative in ("tools/test-evidence/run.py", "tools/repository-checks/workflows/sync-ci-selection.yml",
                         "tools/repository-checks/workflows/metadata-edits/repository-checks.yml",
                         "tools/repository-checks/workflows/metadata-edits/codeql.yml",
                         "tools/repository-checks/workflows/metadata-edits/codeql-pinned.yml",
                         "tools/repository-checks/workflows/metadata-edits/sync-test-reuse.yml"):
            with self.subTest(path=relative):
                self.git("checkout", "-q", "--detach", self.base)
                self.write(relative, "# Independent CI source\n")
                (self.root / relative).chmod(0o755)
                plan = self.plan(self.commit("Make a different independent host file executable"))
                self.assertTrue(plan["requires_application_build"])
                self.assertEqual(plan["changes"][0]["kind"], "application-input")

    def test_metadata_workflow_siblings_are_not_blanket_independent_inputs(self):
        for name in ('unreviewed.yml', 'codeql-pinned-extra.yml'):
            self.git('checkout', '-q', '--detach', self.base)
            self.write("tools/repository-checks/workflows/metadata-edits/" + name, "name: Unreviewed\n")
            self.assertTrue(self.plan(self.commit("Add an unreviewed staged workflow"))["requires_application_build"])
        self.git('checkout', '-q', '--detach', self.base)
        relative = 'tools/repository-checks/workflows/metadata-edits/codeql-pinned.yml'
        target = self.root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.symlink_to('unreviewed-target')
        self.assertTrue(self.plan(self.commit('Reject staged workflow alias'))['requires_application_build'])

    def test_generic_ci_workflows_require_exact_ordinary_files(self):
        for relative in ('.github/workflows/documentation-checks.yml',
                         '.github/workflows/workflow-security.yml'):
            with self.subTest(path=relative):
                self.git('checkout','-q','--detach',self.base)
                self.write(relative,'name: Fixed generic CI fixture\n')
                self.assert_independent(self.commit('Update reviewed generic CI workflow'))
                for mode in ('100755','120000'):
                    self.git('checkout','-q','--detach',self.base)
                    self.write(relative,'name: Fixed generic CI fixture\n')
                    path=self.root/relative
                    if mode=='120000':
                        path.unlink();path.symlink_to('unreviewed-target')
                    else:path.chmod(0o755)
                    self.assertTrue(self.plan(self.commit('Reject nonordinary generic CI workflow'))[
                        'requires_application_build'])
                self.git('checkout','-q','--detach',self.base)
                self.write(relative.replace('.yml','-extra.yml'),'name: Unreviewed neighbor\n')
                self.assertTrue(self.plan(self.commit('Reject neighboring generic workflow'))[
                    'requires_application_build'])

    def test_android_handoff_ci_paths_require_ordinary_exact_files(self):
        for relative in REVIEWED_ANDROID_CI_PATHS:
            for mode in ("100755", "120000"):
                with self.subTest(path=relative, mode=mode):
                    self.git("checkout", "-q", "--detach", self.base)
                    self.write(relative, "# Independent CI fixture\n")
                    if mode == "120000":
                        (self.root / relative).unlink()
                        (self.root / relative).symlink_to("unreviewed-target")
                    else:
                        (self.root / relative).chmod(0o755)
                    self.assertTrue(self.plan(self.commit("Reject nonordinary staged Android CI"))["requires_application_build"])
        for relative in (".github/android-owner-transfer-unreviewed.json",
                         "tests/android-owner-transfer-unreviewed-test.py",
                         "tools/repository-checks/android_handoff_unreviewed.py",
                         "tools/repository-checks/workflows/android-owned/handoff/android/phone/tests/unreviewed.py",
                         "android/phone/tests/phone-release-metadata-test.py"):
            with self.subTest(path=relative):
                self.git("checkout", "-q", "--detach", self.base)
                self.write(relative, "# Unknown sibling or real product target\n")
                self.assertTrue(self.plan(self.commit("Reject unreviewed Android input"))["requires_application_build"])

    def test_sandbox_ci_paths_require_exact_ordinary_sources(self):
        for relative in REVIEWED_SANDBOX_CI_PATHS:
            for mode in ("100755", "120000"):
                with self.subTest(path=relative, mode=mode):
                    self.git("checkout", "-q", "--detach", self.base)
                    self.write(relative, "# Reviewed sandbox CI fixture\n")
                    if mode == "120000":
                        (self.root / relative).unlink()
                        (self.root / relative).symlink_to("unreviewed-target")
                    else:
                        (self.root / relative).chmod(0o755)
                    self.assertTrue(self.plan(self.commit("Reject nonordinary sandbox CI"))["requires_application_build"])
        for relative in (".github/shared-sandbox-extra.json",
                         ".github/workflows/shared-sandbox-host-extra.yml",
                         "tools/repository-checks/workflows/shared-sandbox-extra.yml",
                         "tools/repository-checks/workflows/producers/protected-project-tests-android-platform-extra.yml",
                         "tools/repository-checks/workflows/producers/parent-qualification-android-platform-extra.yml",
                         "tools/test-evidence/sandbox_extra.py",
                         "tools/test-evidence/sandbox_native.h"):
            with self.subTest(path=relative):
                self.git("checkout", "-q", "--detach", self.base)
                self.write(relative, "# Unknown sandbox sibling or native scanner input\n")
                self.assertTrue(self.plan(self.commit("Reject unknown sandbox input"))["requires_application_build"])

    def npm_fixture(self):
        """Review a disposable real-Git graph, retaining actual dependency entries."""
        self.consumers = INPUTS.npm_selector()
        self.npm_policies = deepcopy(self.consumers.PROJECTS)
        for project, policy in self.npm_policies.items():
            self.write(project + "/package.json", '{"private":true}\n')
            self.write(project + "/consumer.js", "module.exports = 1;\n")
            self.write_npm_lock(project, policy["old"])
        self.base = self.commit("Create reviewed package reader fixtures")
        snapshot = self.consumers._snapshot(self.root, self.base)
        for project, policy in self.npm_policies.items():
            policy["complement"] = self.consumers._digest(self.consumers._complement(snapshot, project))
            policy["entries"] = 2
            lock = json.loads((self.root / project / "package-lock.json").read_text())
            policy["graph"] = self.consumers._digest(self.consumers._graph(lock, policy["node"]))
        for replacement in (patch.dict(self.consumers.PROJECTS, self.npm_policies, clear=True),
                            patch.object(INPUTS, "npm_selector", return_value=self.consumers),
                            patch.object(INPUTS, "REVIEWED_BOUNDARY", INPUTS.review_boundary(self.root, self.base)["boundary"])):
            replacement.start(); self.addCleanup(replacement.stop)

    def write_npm_lock(self, project, dependency):
        self.write(project + "/package-lock.json", json.dumps({"lockfileVersion": 3,
            "packages": {"": {"name": "fixture"}, self.npm_policies[project]["node"]: dependency,
                         "node_modules/unchanged": {"version": "1.0.0"}}}) + "\n")

    def npm_owner(self, candidate, base=None):
        base = base or self.base
        profiles = self.consumers.select(self.root, base, candidate)
        value = {"base": base, "candidate": candidate, "tree": profiles["candidate"]["tree"], "unknown": False,
                 "consumer_generation": True, "policy": {"trusted-fixture": "a" * 64},
                 "dependency_profiles": profiles,
                 "package_set": [project for project, selected in profiles["projects"].items() if selected["required"]]}
        value["plan"] = INPUTS._digest(value).removeprefix("sha256:")
        return value

    def update_npm_locks(self):
        for project, policy in self.npm_policies.items():
            self.write_npm_lock(project, policy["new"])

    def test_exact_npm_locks_and_finite_ci_require_a_bound_required_owner(self):
        self.npm_fixture(); self.update_npm_locks()
        for path in ("tools/repository-checks/npm_consumers.py",
                     "tools/repository-checks/workflows/npm-consumers/repository-checks.yml"):
            self.write(path, "candidate code must never execute\n")
        candidate = self.commit("Update reviewed dependencies with independent CI")
        self.assertTrue(self.plan(candidate)["requires_application_build"])
        owner = self.npm_owner(candidate)
        plan = INPUTS.candidate_plan(self.root, self.base, candidate, package_owner=owner)
        self.assertFalse(plan["requires_application_build"], plan)
        self.assertEqual(plan["package_ownership"]["packagePlan"], owner["plan"])
        self.assertEqual(set(plan["package_ownership"]["changedPaths"]), set(INPUTS.NPM_PACKAGE_PROFILES))
        self.assertEqual(plan["base"]["fingerprint"], plan["candidate"]["fingerprint"])
        # Standalone source fingerprints retain locks; this is no IPA reuse proof.
        self.assertNotEqual(INPUTS.input_fingerprint(self.root, self.base)["fingerprint"],
                            INPUTS.input_fingerprint(self.root, candidate)["fingerprint"])
        self.assertTrue(all(change["kind"] == "independent-npm-package" for change in plan["changes"]
                            if change["path"] in INPUTS.NPM_PACKAGE_PROFILES))
        for field, value in (("consumer_generation", False), ("unknown", True), ("base", "f" * 40),
                             ("tree", "e" * 40), ("package_set", []), ("dependency_profiles", {})):
            changed = {**deepcopy(owner), field: value}; changed.pop("plan")
            changed["plan"] = INPUTS._digest(changed).removeprefix("sha256:")
            with self.subTest(field=field):
                self.assertTrue(INPUTS.candidate_plan(self.root, self.base, candidate,
                                                     package_owner=changed)["requires_application_build"])

    def test_reviewed_npm_formatting_has_no_execution_claim_and_no_package_job(self):
        self.npm_fixture()
        path = self.root / "browser-client/package-lock.json"
        path.write_text(json.dumps(json.loads(path.read_text()), indent=4))
        candidate = self.commit("Format reviewed npm lock only")
        owner = self.npm_owner(candidate)
        self.assertEqual(owner["package_set"], [])
        plan = INPUTS.candidate_plan(self.root, self.base, candidate, package_owner=owner)
        self.assertFalse(plan["requires_application_build"])
        self.assertEqual(plan["package_ownership"]["projects"]["browser-client"]["execution"], "not-performed")

    def test_full_npm_lock_graph_owner_preserves_independent_ios_inputs(self):
        self.npm_fixture()
        for project in self.npm_policies:
            with self.subTest(project=project):
                self.git("checkout","-q","--detach",self.base)
                lock=self.root/project/"package-lock.json"
                value=json.loads(lock.read_text())
                value["packages"]["node_modules/unchanged"]["version"]="9.0.0"
                lock.write_text(json.dumps(value))
                candidate=self.commit("Update an independently owned lock dependency graph")
                owner=self.npm_owner(candidate)
                self.assertEqual(owner["dependency_profiles"]["projects"][project]["profile"],"full")
                self.assertIn(project,owner["package_set"])
                plan=INPUTS.candidate_plan(self.root,self.base,candidate,package_owner=owner)
                self.assertFalse(plan["requires_application_build"],plan)
                self.assertEqual(plan["package_ownership"]["projects"][project]["profile"],"full")
                missing=deepcopy(owner);missing["package_set"]=[];missing.pop("plan")
                missing["plan"]=INPUTS._digest(missing).removeprefix("sha256:")
                self.assertTrue(INPUTS.candidate_plan(self.root,self.base,candidate,
                    package_owner=missing)["requires_application_build"])

    def test_npm_owner_cannot_hide_config_consumers_or_native_changes(self):
        self.npm_fixture()
        for change in ("consumer", "config", "native", "unknown", "symlink", "mode", "deleted"):
            with self.subTest(change=change):
                self.git("checkout", "-q", "--detach", self.base)
                self.update_npm_locks()
                lock = self.root / "browser-client/package-lock.json"
                if change == "consumer": self.write("browser-client/consumer.js", "module.exports = 2;\n")
                elif change == "config": self.write("postcss.config.cjs", "throw Error('never execute');\n")
                elif change == "native": self.write("interface/src/main.cpp", "int main() { return 2; }\n")
                elif change == "unknown": self.write("tools/unreviewed-input.py", "# Unknown reader\n")
                elif change == "mode": lock.chmod(0o755)
                elif change == "symlink": lock.unlink(); lock.symlink_to("package.json")
                elif change == "deleted": lock.unlink()
                candidate = self.commit("Change package or native boundary")
                plan = INPUTS.candidate_plan(self.root, self.base, candidate, package_owner=self.npm_owner(candidate))
                self.assertTrue(plan["requires_application_build"], plan)

    def test_npm_negative_selection_binds_both_historical_reader_complements(self):
        self.npm_fixture()
        self.write("CMakeLists.txt", "file(READ browser-client/package-lock.json APP_INPUT)\n")
        historical = self.commit("Introduce an earlier application dependency reader")
        self.update_npm_locks()
        self.write("CMakeLists.txt", "project(InputFixture)\n")
        candidate = self.commit("Restore current reader while updating dependency")
        plan = INPUTS.candidate_plan(self.root, historical, candidate,
                                    package_owner=self.npm_owner(candidate, historical))
        self.assertFalse(plan["exclusions_applicable"])
        self.assertTrue(plan["requires_application_build"])
        self.assertEqual(plan["candidate"]["boundary"], INPUTS.REVIEWED_BOUNDARY)
        self.assertNotEqual(plan["base"]["boundary"], INPUTS.REVIEWED_BOUNDARY)

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
            "tools/repository-checks/workflows/unreviewed-sync.yml",
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

    def test_new_ci_exemptions_cannot_hide_an_earlier_app_discovery_reader(self):
        # Historical child readers matter even when only the later CI file is
        # changed. A new app glob must invalidate both-side negative ownership.
        self.write("CMakeLists.txt", "project(InputFixture)\nfile(GLOB DEVICE_INPUTS tests/device/*.py)\n")
        integrated = self.commit("Add an application discovery reader")
        self.write("tests/device/run_control_plane_tests.py", "raise RuntimeError('must never execute')\n")
        candidate = self.commit("Change a newly discovered generic host runner")
        plan = self.plan(candidate, integrated)
        self.assertTrue(plan["requires_application_build"])
        self.assertEqual(plan["reason"], "reader-boundary-not-reviewed")
        self.assertFalse(plan["exclusions_applicable"])
        self.assertEqual([change["path"] for change in plan["changes"]],
                         ["tests/device/run_control_plane_tests.py"])

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
