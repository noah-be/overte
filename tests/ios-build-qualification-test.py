#!/usr/bin/env python3
"""Exercise candidate selection, failing jobs, real archive bindings and history."""

import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import plistlib
import posixpath
import re
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import zipfile


ROOT = Path(__file__).resolve().parents[1]


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
    "tools/test-evidence/producer_workflow.py",
    "tools/test-evidence/postmerge.py",
    "tools/repository-checks/workflows/producers/protected-project-tests.yml",
    "tools/repository-checks/workflows/producers/repository-checks.yml",
    "tools/repository-checks/workflows/producers/parent-qualification.yml",
    "tools/repository-checks/workflows/producers/protected-project-tests-android-platform.yml",
    "tools/repository-checks/workflows/producers/parent-qualification-android-platform.yml",
)


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / f"tools/ios-build-qualification/{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CHECK, HISTORY = load("check"), load("history")
SOURCE, TREE = "a" * 40, "b" * 40


def needs(required=True):
    return {"route": {"result": "success", "outputs": {
        "required": str(required).lower(), "source": SOURCE, "tree": TREE,
        "reason": "application-build-required" if required else "ordinary-markdown-only"}},
        **{name: {"result": "success" if required else "skipped"} for name in ("host", "qt", "client")}}


def records():
    names = ['iOS host contracts', 'qt / qt-ios-source', 'client / Host contracts',
             'client / Static JITless V8 checkpoint', 'client / Toolchain, dependencies, build and package']
    steps = ['Build experimental full client', 'Verify required Interface QML plugins in full-client link',
             'Package numbered unsigned client IPA', 'Upload short-lived unsigned E2E client handoff']
    return [{'id': index + 1, 'name': name, 'run_id': 123, 'run_attempt': 1, 'head_sha': SOURCE,
             'status': 'completed', 'conclusion': 'success',
             'steps': [{'name': step, 'status': 'completed', 'conclusion': 'success'} for step in steps]}
            for index, name in enumerate(names)]


def fixture(directory, info_changes=None, **changes):
    ipa = directory / "0688-OverteIOSClient-Release-device-unsigned.ipa"
    manifest = ipa.with_suffix(".json")
    info = {"CFBundleIdentifier": "org.overte.interface.e2e", "CFBundleExecutable": "Overte",
            "CFBundleSupportedPlatforms": ["iPhoneOS"], "CFBundleShortVersionString": "0.1.0",
            "CFBundleVersion": "1", "OverteE2ETestBuildContractVersion": 1,
            **(info_changes or {})}
    with zipfile.ZipFile(ipa, "w") as archive:
        archive.writestr("Payload/Overte.app/Info.plist", plistlib.dumps(info))
        archive.writestr("Payload/Overte.app/Overte", b"\xcf\xfa\xed\xfe\x0c\x00\x00\x01" + b"\0" * 5000)
    value = {"schemaVersion": 1, "product": "overte-ios-integrated-client", "sourceRevision": SOURCE,
             "platform": "iphoneos", "architecture": "arm64", "configuration": "Release",
             "testBuildContractVersion": 1, "signed": False, "requiresSigning": True,
             "buildNumber": 688, "artifact": ipa.name, "manifest": manifest.name,
             "sha256": hashlib.sha256(ipa.read_bytes()).hexdigest(), **changes}
    manifest.write_text(json.dumps(value))
    return ipa, manifest


class QualificationTests(unittest.TestCase):
    def test_deployed_template_passes_actual_repository_health_contracts(self):
        spec = importlib.util.spec_from_file_location(
            "qualification_repository_health", ROOT / "tools/repository-health/check.py")
        health = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = health
        spec.loader.exec_module(health)
        config = health.load_config(ROOT / ".github/repository-health.json")
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            shutil.copytree(ROOT / ".github", root / ".github")
            shutil.copytree(ROOT / "tools/branch-policy", root / "tools/branch-policy")
            canonical = (ROOT / "tools/ios-build-qualification/workflow.yml").read_text()
            deployed = root / ".github/workflows/ios-build-qualification.yml"
            deployed.write_text(canonical)
            report = health.Doctor(root, config).local()
            self.assertEqual(report["status"], "PASS", report)
            # Valid quoted trigger keys retain the actual workflow contract.
            quoted = canonical.replace("\non:\n", "\n'on':\n", 1)
            self.assertNotEqual(quoted, canonical)
            deployed.write_text(quoted)
            report = health.Doctor(root, config).local()
            self.assertEqual(report["status"], "PASS", report)
            # A mismatched quote remains invalid YAML, not a spelling waiver.
            previous = canonical.replace("\non:\n", "\n'on\":\n", 1)
            self.assertNotEqual(previous, canonical)
            deployed.write_text(previous)
            report = health.Doctor(root, config).local()
            self.assertEqual(report["status"], "FAIL")
            self.assertIn("WORKFLOW_SYNTAX", [finding["code"] for finding in
                          report["results"]["repository_contracts"]["findings"]])

    def test_canonical_workflow_keeps_immutable_action_references(self):
        # The template is outside .github/workflows on main. Audit it here
        # before the product branch installs it as an executable workflow.
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workflows = root / ".github/workflows"
            workflows.mkdir(parents=True)
            canonical = (ROOT / "tools/ios-build-qualification/workflow.yml").read_text()
            workflow = workflows / "ios-build-qualification.yml"
            workflow.write_text(canonical)
            for name in ("ios-integrated.yml", "ios-qt-source.yml"):
                (workflows / name).write_text("# Product-owned dependency, checked on apple-ios.\n")
            command = [sys.executable, str(ROOT / "tools/workflow-security/check-action-pins.py"),
                       "--root", str(root)]
            valid = subprocess.run(command, capture_output=True, text=True, timeout=30)
            self.assertEqual(valid.returncode, 0, valid.stdout + valid.stderr)
            workflow.write_text(canonical.replace(
                "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1", "actions/checkout@main"))
            invalid = subprocess.run(command, capture_output=True, text=True, timeout=30)
            self.assertNotEqual(invalid.returncode, 0)

    def test_reusable_job_success_cannot_hide_a_skipped_compiler(self):
        for conclusion in ("skipped", "failure", "cancelled", None):
            value = records()
            value[-1]["steps"][0]["conclusion"] = conclusion
            with self.subTest(conclusion=conclusion), self.assertRaises(ValueError):
                CHECK.verify_build_execution(value, 123, 1, SOURCE)
        for key, wrong in (("head_sha", "c" * 40), ("run_id", 669), ("run_attempt", 2)):
            value = records()
            value[-1][key] = wrong
            with self.assertRaises(ValueError):
                CHECK.verify_build_execution(value, 123, 1, SOURCE)
        with self.assertRaises(ValueError):
            CHECK.verify_build_execution(records()[:-1], 123, 1, SOURCE)

    def test_failed_only_qualifier_reports_actual_api_snapshot_identity(self):
        jobs = records()
        result = CHECK.verify_build_execution(jobs, 123, 2, SOURCE)
        self.assertEqual(result["apiSnapshotRunAttempt"], 1)
        self.assertEqual(result["qualifierRunAttempt"], 2)
        self.assertEqual(result["apiSnapshotJobIds"], [1, 2, 3, 4, 5])
        self.assertIsNone(result["originalExecutionRunAttempt"])
        self.assertIsNone(result["originalExecutionJobIds"])
        self.assertEqual(jobs, records())
        self.assertEqual(result["artifactIdVerification"], "not-observed-by-legacy-invocation")
        self.assertEqual(result["originalArtifactZipDigestVerification"],
                         "not-observed-by-legacy-invocation")

    def test_failed_only_report_still_checks_exact_inner_ipa(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            ipa, manifest = fixture(directory)
            result = CHECK.report(needs(), SOURCE, 688, 123, 2, directory, records())
            self.assertEqual(result["runAttempt"], 2)
            self.assertEqual(result["producer"]["apiSnapshotRunAttempt"], 1)
            self.assertEqual(result["artifact"]["sha256"], hashlib.sha256(ipa.read_bytes()).hexdigest())
            payload = json.loads(manifest.read_text())
            payload["sourceRevision"] = "c" * 40
            manifest.write_text(json.dumps(payload))
            with self.assertRaisesRegex(ValueError, "sourceRevision"):
                CHECK.report(needs(), SOURCE, 688, 123, 2, directory, records())

    def test_actual_job_ids_are_mandatory_and_unique(self):
        for invalid in (None, 0, -1, True, "1"):
            jobs = records()
            jobs[-1]["id"] = invalid
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                CHECK.verify_build_execution(jobs, 123, 2, SOURCE)
        jobs = records()
        jobs[-1]["id"] = jobs[0]["id"]
        with self.assertRaises(ValueError):
            CHECK.verify_build_execution(jobs, 123, 2, SOURCE)

    def test_mixed_or_future_producer_attempts_are_rejected(self):
        jobs = records()
        jobs[-1]["run_attempt"] = 2
        with self.assertRaisesRegex(ValueError, "inconsistent"):
            CHECK.verify_build_execution(jobs, 123, 2, SOURCE)
        for producer, qualifier in ((2, 1), (1, 3), (3, 2), (True, 2), (0, 2)):
            jobs = records()
            for job in jobs:
                job["run_attempt"] = producer
            with self.subTest(producer=producer, qualifier=qualifier), self.assertRaises(ValueError):
                CHECK.verify_build_execution(jobs, 123, qualifier, SOURCE)
        for job in jobs:
            job["run_attempt"] = 3
        self.assertEqual(CHECK.verify_build_execution(jobs, 123, 3, SOURCE)["apiSnapshotRunAttempt"], 3)

    def test_cloned_attempt_two_api_does_not_claim_new_execution(self):
        jobs = records()
        for job in jobs:
            job.update(id=job["id"] + 100, run_attempt=2,
                       started_at="2026-10-13T19:58:16Z", completed_at="2026-10-13T21:27:42Z")
            for step in job["steps"]:
                step.update(started_at="2026-10-13T20:09:31Z", completed_at="2026-10-13T21:27:30Z")
        before = copy.deepcopy(jobs)
        result = CHECK.verify_build_execution(jobs, 123, 2, SOURCE)
        self.assertEqual(result["apiSnapshotRunAttempt"], 2)
        self.assertEqual(result["apiSnapshotJobIds"], [101, 102, 103, 104, 105])
        self.assertIsNone(result["originalExecutionRunAttempt"])
        self.assertIsNone(result["originalExecutionJobIds"])
        self.assertEqual(result["originalExecutionIdentityVerification"],
                         "not-observed-by-legacy-invocation")
        self.assertNotIn("producerRunAttempt", result)
        self.assertNotIn("jobIds", result)
        self.assertEqual(jobs, before)

    def test_clone_snapshot_success_cannot_hide_failed_native_steps(self):
        for index in range(4):
            jobs = records()
            for job in jobs:
                job.update(id=job["id"] + 100, run_attempt=2)
            jobs[-1]["steps"][index]["conclusion"] = "failure"
            with self.subTest(index=index), self.assertRaises(ValueError):
                CHECK.verify_build_execution(jobs, 123, 2, SOURCE)

    def test_pending_api_steps_fail_despite_completed_job_and_artifact(self):
        for index in range(4):
            for status in (None, "pending", "in_progress", "skipped"):
                jobs = records()
                jobs[-1]["steps"][index]["status"] = status
                # Even an incongruous success conclusion cannot hide a
                # nonterminal mandatory step.
                with self.subTest(index=index, status=status), self.assertRaises(ValueError):
                    CHECK.verify_build_execution(jobs, 123, 2, SOURCE)

    def test_duplicate_jobs_and_native_steps_fail_on_retry(self):
        jobs = records()
        jobs.append(copy.deepcopy(jobs[-1]))
        with self.assertRaises(ValueError):
            CHECK.verify_build_execution(jobs, 123, 2, SOURCE)
        jobs = records()
        jobs[-1]["steps"].append(copy.deepcopy(jobs[-1]["steps"][0]))
        with self.assertRaises(ValueError):
            CHECK.verify_build_execution(jobs, 123, 2, SOURCE)

    def test_retry_does_not_accept_other_run_or_head(self):
        for key, invalid in (("run_id", 124), ("run_id", True), ("head_sha", "c" * 40)):
            jobs = records()
            jobs[0][key] = invalid
            with self.subTest(key=key, invalid=invalid), self.assertRaises(ValueError):
                CHECK.verify_build_execution(jobs, 123, 2, SOURCE)
        for invalid in (0, True, "2"):
            with self.assertRaises(ValueError):
                CHECK.verify_build_execution(records(), 123, invalid, SOURCE)

    def test_required_repository_router_rejects_a_skippable_final_gate(self):
        event = {"pull_request": {"base": {"ref": "apple-ios"}}}
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)
            candidate, trusted = path / "candidate", path / "trusted"
            (candidate / ".github/workflows").mkdir(parents=True)
            (trusted / ".github").mkdir(parents=True)
            (trusted / "tools/ios-build-qualification").mkdir(parents=True)
            config = json.loads((ROOT / ".github/ios-build-qualification.json").read_text())
            config["enforceWorkflow"] = True
            (trusted / ".github/ios-build-qualification.json").write_text(json.dumps(config))
            canonical = (ROOT / "tools/ios-build-qualification/workflow.yml").read_text()
            (trusted / "tools/ios-build-qualification/workflow.yml").write_text(canonical)
            with self.assertRaises(ValueError):
                CHECK.validate_wiring(candidate, event, trusted)
            workflow = candidate / config["workflowPath"]
            workflow.write_text(canonical)
            CHECK.validate_wiring(candidate, event, trusted)
            changed = canonical.replace("if: always()", "if: false")
            self.assertNotEqual(changed, canonical)
            workflow.write_text(changed)
            with self.assertRaises(ValueError):
                CHECK.validate_wiring(candidate, event, trusted)
            # Main-owned staged deployment is explicit, not an implicit success fallback.
            config["enforceWorkflow"] = False
            (trusted / ".github/ios-build-qualification.json").write_text(json.dumps(config))
            workflow.unlink()
            CHECK.validate_wiring(candidate, event, trusted)

    def test_all_selected_jobs_must_succeed(self):
        for job in needs():
            for result in ("skipped", "failure", "cancelled", "timed_out", None):
                value = needs()
                value[job]["result"] = result
                with self.subTest(job=job, result=result), self.assertRaises(ValueError):
                    CHECK.verify_jobs(value, SOURCE)
        for job in needs():
            value = needs()
            del value[job]
            with self.assertRaises(ValueError):
                CHECK.verify_jobs(value, SOURCE)
        value = needs()
        value["route"]["outputs"]["source"] = "c" * 40
        with self.assertRaises(ValueError):
            CHECK.verify_jobs(value, SOURCE)

    def test_documentation_report_is_never_a_built_or_installed_app(self):
        result = CHECK.report(needs(False), SOURCE, 688, 123, 1, Path("missing"), [])
        self.assertEqual(result["ipa"], "not-required")
        self.assertIsNone(result["artifact"])
        self.assertEqual(result["installation"], "not-performed")
        value = needs(False)
        value["client"]["result"] = "success"
        with self.assertRaises(ValueError):
            CHECK.verify_jobs(value, SOURCE)

    def test_verified_ipa_is_bound_to_the_exact_candidate_and_run(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)
            fixture(path)
            result = CHECK.report(needs(), SOURCE, 688, 123, 1, path, records())
            self.assertEqual(result["ipa"], "verified")
            self.assertEqual(result["artifact"]["appBuild"], "1")
            self.assertEqual(result["buildNumber"], 688)
            self.assertEqual(result["installation"], "not-performed")
            for mutation in ({"sourceRevision": "c" * 40}, {"buildNumber": 669},
                             {"platform": "iphonesimulator"}, {"testBuildContractVersion": 0},
                             {"testBuildContractVersion": True}, {"sha256": "0" * 64},
                             {"artifact": "../other.ipa"}, {"signed": True}):
                fixture(path, **mutation)
                with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                    CHECK.report(needs(), SOURCE, 688, 123, 1, path, records())
            fixture(path)
            (path / "second.ipa").write_bytes(b"different")
            with self.assertRaises(ValueError):
                CHECK.verify_ipa(path, SOURCE, 688)

    def test_missing_artifact_cannot_pass_a_successful_build(self):
        with tempfile.TemporaryDirectory() as temp, self.assertRaises(ValueError):
            CHECK.report(needs(), SOURCE, 688, 123, 1, Path(temp), records())

    def test_archive_identity_is_checked_beyond_the_manifest(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)
            fixture(path, info_changes={"OverteE2ETestBuildContractVersion": True})
            with self.assertRaises(ValueError):
                CHECK.verify_ipa(path, SOURCE, 688)
            ipa, manifest = fixture(path)
            with zipfile.ZipFile(ipa, "w") as archive:
                archive.writestr("Payload/Bootstrap.app/Info.plist", plistlib.dumps({
                    "CFBundleIdentifier": "org.overte.bootstrap", "CFBundleSupportedPlatforms": ["iPhoneOS"]}))
            value = json.loads(manifest.read_text())
            value["sha256"] = CHECK.sha256(ipa)
            manifest.write_text(json.dumps(value))
            with self.assertRaises(ValueError):
                CHECK.verify_ipa(path, SOURCE, 688)


class CandidateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.git("init", "-q")
        # These disposable repositories must have no detached writers during
        # strict TemporaryDirectory cleanup. Keep the setting local to each
        # fixture; candidate routing and artifact checks remain unchanged.
        self.git("config", "maintenance.auto", "false")
        self.git("config", "gc.auto", "0")
        self.git("config", "user.name", "Test")
        self.git("config", "user.email", "test@example.invalid")
        (self.root / "readme.md").write_text("Initial\n")
        (self.root / "code.cpp").write_text("int value;\n")
        self.git("add", ".")
        self.git("commit", "-qm", "Initial")
        self.base = self.git("rev-parse", "HEAD")

    def git(self, *args):
        return subprocess.check_output(["git", *args], cwd=self.root, text=True, stderr=subprocess.PIPE).strip()

    def candidate(self, path):
        (self.root / path).write_text("Changed\n")
        self.git("add", ".")
        self.git("commit", "-qm", "Candidate")
        head = self.git("rev-parse", "HEAD")
        merged = self.git("commit-tree", "HEAD^{tree}", "-p", self.base, "-p", head, "-m", "Merge candidate")
        self.git("checkout", "--detach", merged)
        repo = {"id": CHECK.REPOSITORY_ID, "full_name": CHECK.REPOSITORY}
        event = {"repository": repo, "pull_request": {
            "base": {"sha": self.base, "ref": "apple-ios", "repo": repo},
            "head": {"sha": head, "ref": "fix/ios/example", "repo": repo}}}
        return event, merged

    def test_cpp_change_requires_full_build_and_exact_merge(self):
        event, merged = self.candidate("code.cpp")
        self.assertEqual(CHECK.route(event, self.root, merged)["required"], "true")
        event["pull_request"]["base"]["sha"] = "d" * 40
        with self.assertRaises(ValueError):
            CHECK.route(event, self.root, merged)

    def test_ordinary_markdown_change_is_explicitly_classified(self):
        event, merged = self.candidate("readme.md")
        self.assertEqual(CHECK.route(event, self.root, merged)["required"], "false")

    def test_executable_markdown_is_not_exempt(self):
        (self.root / "script.md").write_text("#!/bin/sh\n")
        (self.root / "script.md").chmod(0o755)
        event, merged = self.candidate("script.md")
        self.assertEqual(CHECK.route(event, self.root, merged)["required"], "true")

    def test_foreign_pr_source_and_wrong_checkout_fail(self):
        event, merged = self.candidate("code.cpp")
        event = copy.deepcopy(event)
        event["pull_request"]["head"]["repo"] = {"id": 99, "full_name": "other/overte"}
        with self.assertRaises(ValueError):
            CHECK.route(event, self.root, merged)
        with self.assertRaises(ValueError):
            CHECK.route(event, self.root, "d" * 40)


class InputSelectionCompatibilityTests(unittest.TestCase):
    git = CandidateTests.git

    def setUp(self):
        CandidateTests.setUp(self)
        self.policy_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.policy_directory.cleanup)
        self.trusted = Path(self.policy_directory.name)
        (self.trusted / ".github").mkdir()
        directory = self.trusted / "tools/ios-build-qualification"
        directory.mkdir(parents=True)
        self.config = json.loads((ROOT / ".github/ios-build-qualification.json").read_text())
        self.config["inputSelection"] = True
        self.save_config()
        canonical = (ROOT / "tools/ios-build-qualification/workflow.yml").read_text()
        (directory / "workflow.yml").write_text(canonical)
        (directory / "check.py").write_bytes((ROOT / "tools/ios-build-qualification/check.py").read_bytes())
        self.write(".github/workflows/ios-build-qualification.yml", canonical)
        self.write("CMakeLists.txt", "project(ReviewedFixture)\n")
        self.write("docs/guide.md", "# Reviewed independent guide\n")
        self.write("tools/test-evidence/run.py", "# Reviewed independent host control\n")
        self.base = self.commit("Create reviewed app reader and independent host fixture")
        selector = CHECK.input_selector()
        anchor = selector.review_boundary(self.root, self.base)["boundary"]
        code = (ROOT / "tools/ios-build-qualification/inputs.py").read_text()
        code = code.replace(selector.REVIEWED_BOUNDARY, anchor)
        (directory / "inputs.py").write_text(code)

    def save_config(self):
        (self.trusted / ".github/ios-build-qualification.json").write_text(json.dumps(self.config))

    def write(self, relative, value):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value)

    def commit(self, message):
        self.git("add", "-A")
        self.git("commit", "-qm", message, "--allow-empty")
        return self.git("rev-parse", "HEAD")

    def candidate(self, relative=None, value="Changed\n"):
        if relative is not None:
            self.write(relative, value)
        head = self.commit("Prepare exact iOS candidate head")
        merge = self.git("commit-tree", "HEAD^{tree}", "-p", self.base, "-p", head, "-m", "Exact candidate")
        self.git("checkout", "--detach", merge)
        repo = {"id": CHECK.REPOSITORY_ID, "full_name": CHECK.REPOSITORY}
        event = {"repository": repo, "pull_request": {
            "base": {"sha": self.base, "ref": "apple-ios", "repo": repo},
            "head": {"sha": head, "ref": "fix/ios/example", "repo": repo}}}
        return event, merge

    def route(self, event, merge):
        return CHECK.route(event, self.root, merge, policy_root=self.trusted)

    def needs(self, decision):
        return {"route": {"result": "success", "outputs": decision}, **{name: {
            "result": "success" if (decision.get("host_required", decision.get("required"))
                if name == "host" else decision.get("required")) == "true" else "skipped"}
            for name in ("host", "qt", "client")}}

    def verify(self, decision, event, merge):
        return CHECK.verify_jobs(self.needs(decision), merge, event=event, candidate=self.root, policy_root=self.trusted)

    def test_absent_false_and_malformed_trusted_flag_preserve_legacy_or_fail_closed(self):
        event, merge = self.candidate("tools/test-evidence/run.py", "raise RuntimeError('never execute candidate')\n")
        selected = self.route(event, merge)
        self.assertEqual((selected["required"], selected["host_required"]), ("false", "false"))
        self.assertEqual(selected["reason"], "independent-host-or-documentation-only")
        for value in (False, None):
            if value is None:
                self.config.pop("inputSelection", None)
            else:
                self.config["inputSelection"] = value
            self.save_config()
            legacy = self.route(event, merge)
            self.assertEqual(legacy["required"], "true")
            self.assertEqual(legacy["reason"], "application-build-required")
            self.assertNotIn("host_required", legacy)
            self.assertNotIn("selection", legacy)
        self.config["inputSelection"] = "true"
        self.save_config()
        with self.assertRaisesRegex(ValueError, "trusted build qualification policy"):
            self.route(event, merge)

    def test_enabled_light_route_cannot_publish_green_without_authenticated_shared_owner(self):
        event, merge = self.candidate("tools/test-evidence/run.py", "# Independent host change\n")
        decision = self.route(event, merge)
        self.assertEqual(decision["required"], "false")
        self.assertEqual(decision["host_required"], "false")
        with self.assertRaisesRegex(ValueError, "independently authenticated shared host owner"):
            self.verify(decision, event, merge)
        with self.assertRaisesRegex(ValueError, "independently authenticated shared host owner"):
            CHECK.report(self.needs(decision), merge, 688, 123, 1, Path("missing"), [],
                         event=event, candidate=self.root, policy_root=self.trusted)

    def test_enabled_documentation_plan_is_explicit_but_final_activation_remains_blocked(self):
        event, merge = self.candidate("docs/guide.md", "# Independent guide changed\n")
        decision = self.route(event, merge)
        self.assertEqual(decision["required"], "false")
        with self.assertRaisesRegex(ValueError, "independently authenticated shared host owner"):
            self.verify(decision, event, merge)

    def test_final_verifier_recomputes_every_source_reason_and_selection_field(self):
        event, merge = self.candidate("code.cpp", "int changedApplication;\n")
        decision = self.route(event, merge)
        self.assertEqual(self.verify(decision, event, merge), decision)
        changes = {"required": "false", "host_required": "false", "source": "c" * 40,
                   "tree": "c" * 40, "base": "c" * 40, "head": "c" * 40,
                   "reason": "independent-host-or-documentation-only", "selection": "sha256:" + "c" * 64,
                   "unreviewed_skip": "true"}
        for field, value in changes.items():
            changed = {**decision, field: value}
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.verify(changed, event, merge)
        for field in decision:
            changed = dict(decision)
            del changed[field]
            with self.subTest(missing=field), self.assertRaises(ValueError):
                self.verify(changed, event, merge)
        with self.assertRaisesRegex(ValueError, "independent event and candidate"):
            CHECK.verify_jobs(self.needs(decision), merge, policy_root=self.trusted)
        altered = copy.deepcopy(event)
        altered["pull_request"]["head"]["sha"] = "d" * 40
        with self.assertRaisesRegex(ValueError, "exact event base and head"):
            self.verify(decision, altered, merge)

    def test_packaged_markdown_mixed_and_unknown_inputs_still_require_app_and_host(self):
        for relative in ("scripts/README.md", "interface/resources/README.md", "unknown/host-helper.py"):
            with self.subTest(path=relative):
                self.git("checkout", "-q", "--detach", self.base)
                self.write("tools/test-evidence/run.py", "# Mixed independent host change\n")
                event, merge = self.candidate(relative)
                decision = self.route(event, merge)
                self.assertEqual((decision["required"], decision["host_required"]), ("true", "true"))
                self.assertEqual(self.verify(decision, event, merge), decision)

    def test_identical_base_head_and_merge_trees_skip_builds_with_independent_proof(self):
        event, merge = self.candidate()
        for flag in (False, True):
            with self.subTest(input_selection=flag):
                self.config["inputSelection"] = flag
                self.save_config()
                decision = self.route(event, merge)
                self.assertEqual(decision["reason"], "unchanged-tree")
                self.assertEqual(decision["required"], "false")
                self.assertEqual(self.verify(decision, event, merge), decision)
                result = CHECK.report(self.needs(decision), merge, 688, 123, 1, Path("missing"), [],
                                      event=event, candidate=self.root, policy_root=self.trusted)
                self.assertEqual((result["ipa"], result["artifact"], result["producer"]),
                                 ("not-required", None, None))
                self.assertEqual(result["unchangedTreeProof"]["candidate"], merge)
                self.assertNotIn("inputSelection", result)
                for field in ("tree", "base", "head", "source"):
                    changed = {**decision, field: "e" * 40}
                    with self.subTest(forged=field), self.assertRaises(ValueError):
                        self.verify(changed, event, merge)
                with self.assertRaisesRegex(ValueError, "independent event and candidate"):
                    CHECK.verify_jobs(self.needs(decision), merge, policy_root=self.trusted)
                for state in ("failure", "cancelled", "success"):
                    selected = self.needs(decision)
                    selected["host"]["result"] = state
                    with self.subTest(unexpected_host=state), self.assertRaises(ValueError):
                        CHECK.verify_jobs(selected, merge, event=event, candidate=self.root,
                                          policy_root=self.trusted)
        altered = copy.deepcopy(event)
        altered["pull_request"]["base"]["sha"], altered["pull_request"]["head"]["sha"] = (
            altered["pull_request"]["head"]["sha"], altered["pull_request"]["base"]["sha"])
        with self.assertRaisesRegex(ValueError, "exact event base and head"):
            self.verify(decision, altered, merge)

    def test_real_source_changes_cannot_claim_an_unchanged_tree(self):
        event, merge = self.candidate("code.cpp", "int changed;\n")
        actual = self.route(event, merge)
        forged = {field: actual[field] for field in ("source", "tree", "base", "head")}
        forged.update(required="false", reason="unchanged-tree")
        with self.assertRaisesRegex(ValueError, "independent exact candidate"):
            self.verify(forged, event, merge)

    def test_equal_base_and_merge_with_a_different_head_is_not_a_history_only_noop(self):
        event, _ = self.candidate("code.cpp", "int changedHead;\n")
        head = event["pull_request"]["head"]["sha"]
        merge = self.git("commit-tree", self.base + "^{tree}", "-p", self.base, "-p", head,
                         "-m", "Merge that discarded the head change")
        self.git("checkout", "--detach", merge)
        for flag in (False, True):
            self.config["inputSelection"] = flag
            self.save_config()
            decision = self.route(event, merge)
            self.assertEqual(decision["required"], "true")
            self.assertNotEqual(decision["reason"], "unchanged-tree")
            self.assertEqual(self.verify(decision, event, merge), decision)

    def test_legacy_cli_reads_bare_metadata_for_noop_without_executing_candidate(self):
        event, merge = self.candidate()
        decision = self.route(event, merge)
        event_file = self.root.parent / "independent-event.json"
        event_file.write_text(json.dumps(event))
        original_run = subprocess.run
        observed = []
        def local_transport(command, **kwargs):
            observed.append(command)
            if "fetch" in command:
                command = [str(self.root) if arg == "https://github.com/noah-l-frank/overte.git" else arg
                           for arg in command]
            return original_run(command, **kwargs)
        with patch.dict(CHECK.os.environ, {"GITHUB_EVENT_PATH": str(event_file)}), \
                patch.object(CHECK.subprocess, "run", side_effect=local_transport):
            with CHECK.verification_candidate(self.needs(decision), merge) as (actual, metadata):
                self.assertEqual(actual, event)
                self.assertEqual(CHECK.git(metadata, "rev-parse", "--is-bare-repository"), "true")
                self.assertEqual(CHECK.verify_jobs(self.needs(decision), merge, event=actual,
                    candidate=metadata, policy_root=self.trusted), decision)
        fetch = next(c for c in observed if "fetch" in c)
        self.assertIn("https://github.com/noah-l-frank/overte.git", fetch)
        self.assertIn("--filter=blob:none", fetch)
        self.assertIn("--depth=2", fetch)
        self.assertFalse(any("checkout" in c for c in observed))
        with patch.dict(CHECK.os.environ, {"GITHUB_EVENT_PATH": str(event_file)}), \
                patch.object(CHECK.subprocess, "run", side_effect=OSError("private transport detail")):
            with self.assertRaisesRegex(ValueError, "^independent unchanged-tree Git metadata is unavailable$"):
                with CHECK.verification_candidate(self.needs(decision), merge):
                    self.fail("transport failure cannot authorize omission")

    def test_reader_change_then_host_only_candidate_cannot_use_stale_boundary(self):
        self.write("CMakeLists.txt", "project(ReviewedFixture)\nfile(READ tools/test-evidence/run.py APP_INPUT)\n")
        self.base = self.commit("Integrate a new application reader")
        event, merge = self.candidate("tools/test-evidence/run.py", "# Newly consumed application input\n")
        decision = self.route(event, merge)
        self.assertEqual(decision["reason"], "reader-boundary-not-reviewed")
        self.assertEqual((decision["required"], decision["host_required"]), ("true", "true"))
        self.assertEqual(self.verify(decision, event, merge), decision)

    def test_manual_run_and_full_report_keep_exact_source_and_no_reused_app_claim(self):
        event, merge = self.candidate("code.cpp", "int modified;\n")
        decision = self.route(event, merge)
        jobs = records()
        for job in jobs:
            job["head_sha"] = event["pull_request"]["head"]["sha"]
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            fixture(directory, sourceRevision=merge)
            result = CHECK.report(self.needs(decision), merge, 688, 123, 1, directory, jobs,
                                  event=event, candidate=self.root, policy_root=self.trusted)
        self.assertEqual(result["ipa"], "verified")
        self.assertEqual(result["sourceRevision"], merge)
        self.assertEqual(result["inputSelection"], {"plan": decision["selection"],
                         "applicationBuildRequired": True, "iosHostRequired": True})
        manual = {"repository": event["repository"]}
        decision = self.route(manual, merge)
        self.assertEqual((decision["required"], decision["host_required"]), ("true", "true"))
        self.assertEqual(decision["reason"], "manual-application-build-required")
        self.assertEqual(self.verify(decision, manual, merge), decision)


class HostGenerationTests(unittest.TestCase):
    """Portable real-Git fixtures; no host/product execution or remote transport."""
    ACTUAL = "52f1cc38180e96cdfd8049a4be93517961ae7dbd"

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        directory = Path(self.temporary.name)
        self.root, self.trusted = directory / "candidate", directory / "trusted"
        self.root.mkdir();self.trusted.mkdir()
        self.git("init", "-q")
        self.blobs = {}
        self.git("config", "user.email", "fixture@example.invalid")
        self.git("config", "user.name", "Offline source fixture")
        for relative in (".github/ios-build-qualification.json", ".github/ios-host-orchestration.json",
                         "tools/ios-build-qualification/inputs.py", "tools/ios-build-qualification/host-workflow.yml",
                         "tools/test-evidence/source_admission.py"):
            target = self.trusted / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((ROOT / relative).read_bytes())
        self.host = load("host")
        document = json.loads((self.trusted / self.host.POLICY).read_text())
        # Existing historical cases use their own complete immutable schema-1
        # source tuple, independently of later protected registrations.
        document["schema"] = 1
        document.pop("reviewedGenerations", None)
        document["activationTargets"] = ["apple-ios"]
        launcher = (ROOT / "tools/ios-build-qualification/fixtures/host-launcher-52f.sh").read_text()
        sources = {self.host.WORKFLOW: (ROOT / "tools/ios-build-qualification/workflow.yml").read_text(),
                   ".github/workflows/ios-integrated.yml": "# Fixed disposable client callee.\n",
                   ".github/workflows/ios-qt-source.yml": "# Fixed disposable Qt callee.\n",
                   "ios/tests/run-tests.sh": ("100755", launcher),
                   "ios/ci/host-test-network.sh": ("100755", "# Fixed disposable network launcher.\n"),
                   "tests/requirements-host.txt": (ROOT / "tests/requirements-host.txt").read_text(),
                   "ios/release-check/test_fixture.py": "# Fixed discoverable test.\n",
                   "tests/device/ios/self_tests/test_fixture.py": "# Fixed discoverable test.\n"}
        literals = re.findall(r'\$script_dir/([^"$\s]+\.(?:py|cjs|sh|cmake))', launcher)
        block = re.search(r"readonly rendering_contracts=\(\n(.*?)\n\)", launcher, re.S)[1]
        literals += re.findall(r"^    ([a-z0-9-]+\.py)$", block, re.M)
        for path in literals:
            sources.setdefault(posixpath.normpath("ios/tests/" + path), "# Fixed immutable host source fixture.\n")
        self.legacy = self.commit(None, sources)
        observed = self.host.entries(CHECK.input_selector().read_snapshot(self.root, self.legacy))
        document["legacy"] = {path: observed[path] for path in self.host.PATHS}
        (self.trusted / self.host.POLICY).write_text(json.dumps(document))
        next_source = (self.trusted / self.host.TEMPLATE).read_text()
        self.base = self.commit(self.legacy, {self.host.WORKFLOW: next_source})
        # Only this disposable trusted policy explicitly approves the fixture graph.
        inputs = CHECK.input_selector()
        boundary = inputs.review_boundary(self.root, self.base)["boundary"]
        path = self.trusted / "tools/ios-build-qualification/inputs.py"
        path.write_text(path.read_text().replace(inputs.REVIEWED_BOUNDARY, boundary))

    def git(self, *arguments, data=None):
        return subprocess.run(["git", "--no-replace-objects", *arguments], cwd=self.root, input=data,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True).stdout.decode().strip()

    def commit(self, parent, changes, *, parents=None):
        self.git("read-tree", parent) if parent else self.git("read-tree", "--empty")
        records = []
        for path, value in changes.items():
            if value is None:
                records.append(f"0 {'0' * 40}\t{path}\0".encode())
                continue
            mode, content = value if isinstance(value, tuple) else ("100644", value)
            if mode == "160000":
                oid = parent
            else:
                # Equal immutable bytes identify the same blob within this
                # disposable repository. Negative cases still create real Git
                # trees/commits with every supplied path, mode and parent.
                if content not in self.blobs:
                    self.blobs[content] = self.git("hash-object", "-w", "--stdin", data=content.encode())
                oid = self.blobs[content]
            records.append(f"{mode} {oid}\t{path}\0".encode())
        if records:
            self.git("update-index", "-z", "--index-info", data=b"".join(records))
        tree = self.git("write-tree")
        ancestors = parents if parents is not None else [parent] if parent else []
        revision = self.git("commit-tree", tree, *(argument for p in ancestors for argument in ("-p", p)),
                            "-m", "Immutable offline iOS source fixture")
        self.git("update-ref", "HEAD", revision)
        return revision

    def candidate(self, changes=None, *, base=None):
        base = base or self.base
        head = self.commit(base, changes or {})
        merge = self.commit(head, {}, parents=[base, head])
        repository = {"full_name": CHECK.REPOSITORY, "id": CHECK.REPOSITORY_ID}
        event = {"repository": repository, "pull_request": {
            "base": {"ref": "apple-ios", "sha": base, "repo": repository},
            "head": {"ref": "fix/ios/offline", "sha": head, "repo": repository}}}
        return event, merge

    def route(self, event, source):
        with patch.object(self.host, "SOURCE_READY", True), patch.object(CHECK, "host_handoff", return_value=self.host):
            return CHECK.route(event, self.root, source, policy_root=self.trusted)

    def needs(self, output):
        return {"route": {"result": "success", "outputs": output}, **{name: {
            "result": "success" if output["host_required" if name == "host" else "required"] == "true" else "skipped"}
            for name in ("host", "qt", "client")}}

    def verify(self, output, event, source, *, required=None):
        with patch.object(self.host, "SOURCE_READY", True), patch.object(CHECK, "host_handoff", return_value=self.host):
            return CHECK.verify_jobs(required or self.needs(output), source, event=event, candidate=self.root,
                                     policy_root=self.trusted)

    def execution(self, head, *, attempt=1):
        repository = {"full_name": CHECK.REPOSITORY, "id": CHECK.REPOSITORY_ID}
        run = {"id": 123, "run_attempt": attempt, "head_sha": head, "path": self.host.WORKFLOW,
               "repository": repository, "run_started_at": "2026-10-15T10:00:00Z"}
        job = {"id": 456, "name": "iOS host contracts", "run_id": 123, "run_attempt": attempt,
               "head_sha": head, "status": "completed", "conclusion": "success",
               "started_at": "2026-10-15T10:01:00Z", "completed_at": "2026-10-15T10:09:00Z",
               "steps": [{"name": "Run iOS host contracts", "status": "completed", "conclusion": "success",
                          "started_at": "2026-10-15T10:02:00Z", "completed_at": "2026-10-15T10:08:00Z"}]}
        return [job], run

    def test_actual_legacy_complete_generation_and_protocol_are_unchanged(self):
        self.assertEqual(self.host.resolve(self.root, self.legacy, policy_root=self.trusted)[0], "legacy")
        event, source = self.candidate({"docs/ios-fixture.md": "Independent documentation\n"}, base=self.legacy)
        output = CHECK.route(event, self.root, source, policy_root=self.trusted)
        self.assertEqual(output["reason"], "ordinary-markdown-only")
        self.assertNotIn("host_required", output)
        self.assertNotIn("generation", output)
        actual = self.git("cat-file", "blob", self.legacy + ":" + self.host.WORKFLOW)
        self.assertEqual(actual, (ROOT / "tools/ios-build-qualification/workflow.yml").read_text().strip())
        document = self.host.policy()
        self.assertEqual(document["reviewedSource"], self.ACTUAL)
        self.assertEqual(document["legacy"]["ios/tests/run-tests.sh"]["oid"],
                         self.git("hash-object", "--stdin", data=(ROOT / "tools/ios-build-qualification/fixtures/host-launcher-52f.sh").read_bytes()))

    def test_next_generation_requires_both_trusted_activation_controls(self):
        event, source = self.candidate({"docs/ios-fixture.md": "Independent documentation\n"})
        with patch.object(self.host, "SOURCE_READY", False), self.assertRaisesRegex(ValueError, "not qualified or activated"):
            self.host.route(event, self.root, source, policy_root=self.trusted)
        value = json.loads((self.trusted / self.host.POLICY).read_text());value["activationTargets"] = []
        (self.trusted / self.host.POLICY).write_text(json.dumps(value))
        with patch.object(self.host, "SOURCE_READY", True), self.assertRaisesRegex(ValueError, "not qualified or activated"):
            self.host.route(event, self.root, source, policy_root=self.trusted)
        self.assertTrue(load("host").SOURCE_READY)
        self.assertEqual(json.loads((ROOT / self.host.POLICY).read_text())["activationTargets"], ["apple-ios"])

    def compiler_data_policy(self):
        """Explicit disposable reviewed tuple; never candidate policy authority."""
        callee = "# Fixed disposable verified compiler-data client callee.\n"
        oid = self.git("hash-object", "--stdin", data=callee.encode())
        path = self.trusted / self.host.POLICY
        document = json.loads(path.read_text())
        row = self.host.generations(self.trusted)["host-v1"]
        row = {name: dict(entry) for name, entry in row.items()}
        row[".github/workflows/ios-integrated.yml"]["oid"] = oid
        document["schema"] = 2
        document["reviewedGenerations"] = {self.host.COMPILER_DATA_GENERATION: row}
        path.write_text(json.dumps(document))
        return callee, oid, document

    def test_protected_compiler_data_registration_preserves_both_original_tuples(self):
        approved = self.host.generations()
        document = self.host.policy()
        self.assertEqual(document["schema"], 2)
        self.assertEqual(set(approved), {"legacy", "host-v1", "host-v1-compiler-data-v1"})
        self.assertEqual(approved["legacy"], document["legacy"])
        caller = self.git("hash-object", "--stdin", data=(ROOT / self.host.TEMPLATE).read_bytes())
        original = {**document["legacy"], self.host.WORKFLOW: {"mode": "100644", "type": "blob", "oid": caller}}
        self.assertEqual(approved["host-v1"], original)
        self.assertEqual(self.host.COMPILER_DATA_CALLEE, "66892fd2b87b7aa4b0ffe8c12407fc5a7597db44")
        self.assertEqual(approved[self.host.COMPILER_DATA_GENERATION], {
            **original, ".github/workflows/ios-integrated.yml": {
                "mode": "100644", "type": "blob", "oid": "66892fd2b87b7aa4b0ffe8c12407fc5a7597db44"}})

    def test_preregistered_compiler_generation_retains_app_and_host_owners(self):
        original = self.host.generations(self.trusted)
        callee, oid, _ = self.compiler_data_policy()
        with patch.object(self.host, "COMPILER_DATA_CALLEE", oid):
            approved = self.host.generations(self.trusted)
            self.assertEqual({name: approved[name] for name in original}, original)
            self.assertEqual(self.host.resolve(self.root, self.legacy, policy_root=self.trusted)[0], "legacy")
            self.assertEqual(self.host.resolve(self.root, self.base, policy_root=self.trusted)[0], "host-v1")
            event, source = self.candidate({".github/workflows/ios-integrated.yml": callee})
            self.assertEqual(self.host.resolve(self.root, source, policy_root=self.trusted)[0],
                             self.host.COMPILER_DATA_GENERATION)
            output = self.route(event, source)
            self.assertEqual((output["required"], output["host_required"]), ("true", "true"))
            self.assertEqual(self.verify(output, event, source), output)
            for owner in ("host", "qt", "client"):
                required = self.needs(output)
                required[owner]["result"] = "skipped"
                with self.subTest(owner=owner), self.assertRaises(ValueError):
                    self.verify(output, event, source, required=required)
            with patch.object(self.host, "SOURCE_READY", False), self.assertRaisesRegex(ValueError, "not qualified or activated"):
                self.host.route(event, self.root, source, policy_root=self.trusted)

    def test_compiler_generation_policy_rejects_unknown_partial_mixed_and_ambiguous_rows(self):
        _, oid, valid = self.compiler_data_policy()
        name = self.host.COMPILER_DATA_GENERATION
        cases = []
        def changed(label, edit):
            value = json.loads(json.dumps(valid))
            edit(value)
            cases.append((label, value))
        changed("schema-bool", lambda value: value.update(schema=True))
        changed("schema-unknown", lambda value: value.update(schema=3))
        changed("schema1-extra-row", lambda value: value.update(schema=1))
        changed("missing-registration", lambda value: value.pop("reviewedGenerations"))
        changed("unknown-name", lambda value: value["reviewedGenerations"].update(unknown=value["reviewedGenerations"][name]))
        changed("partial", lambda value: value["reviewedGenerations"][name].pop("tests/requirements-host.txt"))
        changed("wrong-mode", lambda value: value["reviewedGenerations"][name][".github/workflows/ios-integrated.yml"].update(mode="100755"))
        changed("symlink", lambda value: value["reviewedGenerations"][name][".github/workflows/ios-integrated.yml"].update(mode="120000"))
        changed("nonblob", lambda value: value["reviewedGenerations"][name][".github/workflows/ios-integrated.yml"].update(type="tree"))
        changed("mixed-caller", lambda value: value["reviewedGenerations"][name].update({self.host.WORKFLOW: value["legacy"][self.host.WORKFLOW]}))
        changed("foreign-callee", lambda value: value["reviewedGenerations"][name][".github/workflows/ios-integrated.yml"].update(oid="f" * 40))
        changed("ambiguous-old-callee", lambda value: value["reviewedGenerations"][name].update({
            ".github/workflows/ios-integrated.yml": value["legacy"][".github/workflows/ios-integrated.yml"]}))
        with patch.object(self.host, "COMPILER_DATA_CALLEE", oid):
            for label, value in cases:
                with self.subTest(policy=label), self.assertRaises(ValueError):
                    (self.trusted / self.host.POLICY).write_text(json.dumps(value))
                    self.host.generations(self.trusted)

    def test_compiler_generation_requires_all_six_exact_ordinary_candidate_entries(self):
        callee, oid, _ = self.compiler_data_policy()
        current = self.commit(self.base, {".github/workflows/ios-integrated.yml": callee})
        with patch.object(self.host, "COMPILER_DATA_CALLEE", oid):
            for path in sorted(self.host.PATHS):
                for label, value in (("changed", "Unreviewed component\n"), ("missing", None),
                                     ("symlink", ("120000", "other"))):
                    revision = self.commit(current, {path: value})
                    with self.subTest(path=path, mutation=label), self.assertRaisesRegex(ValueError, "complete reviewed generation"):
                        self.host.resolve(self.root, revision, policy_root=self.trusted)

    def test_schema2_preserves_exact_original_bootstrap_and_cannot_extend_it(self):
        event, source = self.bootstrap_candidate()
        inputs = CHECK.input_selector(self.trusted)
        previous = inputs.read_snapshot(self.root, self.legacy)
        current = inputs.read_snapshot(self.root, source)
        head = inputs.read_snapshot(self.root, event["pull_request"]["head"]["sha"])
        with patch.object(self.host, "BOOTSTRAP_REVIEWED_TREE", self.bootstrap_tree()):
            original = self.host.workflow_bootstrap(self.root, previous, current, head, policy_root=self.trusted)
            self.assertIsNotNone(original)
            callee, oid, _ = self.compiler_data_policy()
            with patch.object(self.host, "COMPILER_DATA_CALLEE", oid):
                self.assertEqual(self.host.workflow_bootstrap(self.root, previous, current, head,
                    policy_root=self.trusted), original)
                self.assertEqual(set(original["generations"]), {"legacy", "host-v1"})
                event, source = self.bootstrap_candidate({".github/workflows/ios-integrated.yml": callee})
                self.assertIsNone(self.host.workflow_bootstrap(self.root, previous,
                    inputs.read_snapshot(self.root, source),
                    inputs.read_snapshot(self.root, event["pull_request"]["head"]["sha"]), policy_root=self.trusted))

    def compiler_input_fixture(self):
        """Pin complete old/new disposable source, with independently fixed anchors."""
        callee, oid, _ = self.compiler_data_policy()
        original, updated, changes = {}, {}, {}
        old_sources = {}
        for path, (mode, _) in self.host.COMPILER_DATA_ORIGINAL.items():
            old = self.git("cat-file", "blob", self.base + ":" + path) + "\n" if path in self.host.PATHS \
                else "# Original reviewed fixture: " + path + "\n"
            new = callee if path == ".github/workflows/ios-integrated.yml" else "# Updated reviewed fixture: " + path + "\n"
            original[path] = (mode, self.git("hash-object", "--stdin", data=old.encode()))
            updated[path] = (mode, self.git("hash-object", "--stdin", data=new.encode()))
            old_sources[path], changes[path] = (mode, old), (mode, new)
        base = self.commit(self.base, old_sources)
        inputs = self.host.selector(self.trusted)
        snapshot = inputs.read_snapshot(self.root, base)
        boundary = inputs.review_boundary(self.root, base)["boundary"]
        path = self.trusted / "tools/ios-build-qualification/inputs.py"
        path.write_text(path.read_text().replace(inputs.REVIEWED_BOUNDARY, boundary)
                        + "\n# Exact compiler-data fixture reader anchor.\n")
        replacement = patch.multiple(self.host, COMPILER_DATA_CALLEE=oid,
            COMPILER_DATA_ORIGINAL=original, COMPILER_DATA_UPDATED=updated,
            REVIEWED_CI_HOST_BOUNDARY=self.host.ci_host_boundary(snapshot))
        replacement.start()
        self.addCleanup(replacement.stop)
        return base, changes

    def test_exact_compiler_data_transition_skips_only_app_and_preserves_actual_sources(self):
        base, changes = self.compiler_input_fixture()
        event, source = self.candidate(changes, base=base)
        inputs = self.host.selector(self.trusted)
        previous = inputs.read_snapshot(self.root, base)
        current = inputs.read_snapshot(self.root, source)
        head = inputs.read_snapshot(self.root, event["pull_request"]["head"]["sha"])
        actual = [self.host.entries(snapshot) for snapshot in (previous, current, head)]
        self.assertTrue(inputs.candidate_plan(self.root, base, source)["requires_application_build"])
        proof = self.host.compiler_data_selection(previous, current, head, policy_root=self.trusted)
        self.assertEqual(proof["candidate"], {"revision": source, "tree": current.tree})
        self.assertEqual(proof["base"], {"revision": base, "tree": previous.tree})
        self.assertEqual(proof["changedPaths"], sorted(changes))
        self.assertEqual([self.host.entries(snapshot) for snapshot in (previous, current, head)], actual)
        output = self.route(event, source)
        self.assertEqual((output["required"], output["host_required"], output["reason"]),
                         ("false", "true", "reviewed-compiler-data-only-inputs"))
        self.assertEqual(self.verify(output, event, source), output)
        needs = self.needs(output);needs["host"]["result"] = "skipped"
        with self.assertRaises(ValueError): self.verify(output, event, source, required=needs)

    def test_installed_compiler_profile_preserves_ci_omission_but_keeps_guide_host_tests(self):
        base, changes = self.compiler_input_fixture()
        installed = self.commit(base, changes)
        inputs = self.host.selector(self.trusted)
        self.assertNotEqual(self.host.ci_host_boundary(inputs.read_snapshot(self.root, installed)),
                            self.host.REVIEWED_CI_HOST_BOUNDARY)
        for path, host_required in (("tools/test-evidence/source-admission-test.py", "false"),
                ("docs/ios-fixture.md", "true"), ("docs/ios/SIGNING_AND_DEVICE_TESTS.md", "true")):
            event, source = self.candidate({path: "# Independent reviewed update\n"}, base=installed)
            output = self.route(event, source)
            self.assertEqual((output["required"], output["host_required"]), ("false", host_required), path)
            self.assertEqual(self.verify(output, event, source), output)
            if host_required == "false":
                self.assertIsNone(self.host.ci_host_omission(inputs.read_snapshot(self.root, installed),
                    inputs.read_snapshot(self.root, source), policy_root=self.trusted))
        manual = {"repository": {"full_name": CHECK.REPOSITORY, "id": CHECK.REPOSITORY_ID}, "ref": "apple-ios"}
        self.assertEqual(self.route(manual, source)["required"], "true")

    def test_compiler_selection_rejects_unreviewed_profiles_readers_modes_and_neighbors(self):
        base, changes = self.compiler_input_fixture()
        for path in sorted(changes):
            for label, value in (("body", "# Unreviewed replacement\n"), ("missing", None),
                                 ("alias", ("120000", "outside")),
                                 ("mode", ("100644" if changes[path][0] == "100755" else "100755", changes[path][1]))):
                event, source = self.candidate({**changes, path: value}, base=base)
                with self.subTest(path=path, mutation=label):
                    inputs = self.host.selector(self.trusted)
                    self.assertIsNone(self.host.compiler_data_selection(inputs.read_snapshot(self.root, base),
                        inputs.read_snapshot(self.root, source),
                        inputs.read_snapshot(self.root, event["pull_request"]["head"]["sha"]), policy_root=self.trusted))
        for extra in ({"ios/ci/qt-checkpoint-artifact-neighbor.py": "# Unknown reader\n"},
                      {"CMakeLists.txt": "file(READ ios/ci/qt-checkpoint-artifact.py INPUT)\n"},
                      {"browser-client/package-lock.json": "{}\n"}):
            event, source = self.candidate({**changes, **extra}, base=base)
            self.assertEqual((self.route(event, source)["required"], self.route(event, source)["host_required"]),
                             ("true", "true"))
        drift = self.commit(base, {"CMakeLists.txt": "# Historical product reader drift\n"})
        event, source = self.candidate(changes, base=drift)
        self.assertEqual(self.route(event, source)["required"], "true")
        installed = self.commit(base, changes)
        drift = self.commit(installed, {"CMakeLists.txt": "# Historical installed-profile reader drift\n"})
        event, source = self.candidate({"tools/test-evidence/source-admission-test.py": "# Independent change\n"}, base=drift)
        self.assertEqual((self.route(event, source)["required"], self.route(event, source)["host_required"]),
                         ("true", "true"))

    def bootstrap_tree(self):
        return self.git("rev-parse", self.legacy + "^{tree}")

    def bootstrap_candidate(self, changes=None, *, base=None):
        return self.candidate({self.host.WORKFLOW: (self.trusted / self.host.TEMPLATE).read_text(),
                               **(changes or {})}, base=base or self.legacy)

    def test_finite_legacy_workflow_bootstrap_keeps_full_host_without_qt_or_ipa(self):
        event, source = self.bootstrap_candidate()
        self.assertTrue(CHECK.input_selector(self.trusted).candidate_plan(self.root, self.legacy, source)["requires_application_build"])
        with patch.object(self.host, "BOOTSTRAP_REVIEWED_TREE", self.bootstrap_tree()):
            output = self.route(event, source)
            self.assertEqual((output["required"], output["host_required"], output["reason"]),
                             ("false", "true", "reviewed-host-v1-workflow-bootstrap"))
            self.assertEqual(self.verify(output, event, source), output)
            jobs, run = self.execution(event["pull_request"]["head"]["sha"])
            with patch.object(self.host, "SOURCE_READY", True), patch.object(CHECK, "host_handoff", return_value=self.host), \
                    patch.object(CHECK, "verify_ipa", side_effect=AssertionError("bootstrap cannot manufacture an IPA")):
                result = CHECK.report(self.needs(output), source, 688, 123, 1, self.root, jobs,
                    event=event, candidate=self.root, policy_root=self.trusted, run_metadata=run)
            self.assertEqual((result["ipa"], result["artifact"]), ("not-required", None))
            self.assertEqual(result["hostSelection"]["producer"]["originalExecutionJobId"], 456)
            for state in ("skipped", "failure", "cancelled", None):
                required = self.needs(output);required["host"]["result"] = state
                with self.assertRaises(ValueError): self.verify(output, event, source, required=required)

    def test_bootstrap_cannot_approve_a_different_reader_tree_or_any_mixed_change(self):
        event, source = self.bootstrap_candidate()
        self.assertEqual(self.route(event, source)["required"], "true")
        for path in ("docs/bootstrap.md", "tools/test-evidence/run.py", "unknown-input", "CMakeLists.txt",
                     "interface/resources/packaged.md", "browser-client/package.json", "browser-client/package-lock.json",
                     "script-archive/marketplace/S3Server/package.json", "script-archive/marketplace/S3Server/package-lock.json"):
            with self.subTest(path=path), patch.object(self.host, "BOOTSTRAP_REVIEWED_TREE", self.bootstrap_tree()):
                event, source = self.bootstrap_candidate({path: "Additional input\n"})
                self.assertEqual((self.route(event, source)["required"], self.route(event, source)["host_required"]), ("true", "true"))
        with patch.object(self.host, "BOOTSTRAP_REVIEWED_TREE", self.bootstrap_tree()):
            changed_base = self.commit(self.legacy, {"CMakeLists.txt": "file(READ .github/workflows/ios-build-qualification.yml APP_INPUT)\n"})
            event, source = self.bootstrap_candidate(base=changed_base)
            self.assertEqual(self.route(event, source)["required"], "true")

    def test_bootstrap_requires_regular_complete_generations_and_exact_head_tree(self):
        with patch.object(self.host, "BOOTSTRAP_REVIEWED_TREE", self.bootstrap_tree()):
            for path in self.host.PATHS:
                for altered in (None, ("120000", "outside"), ("100755", "Changed mode/source\n")):
                    with self.subTest(path=path, altered=altered):
                        event, source = self.bootstrap_candidate({path: altered})
                        with patch.object(self.host, "SOURCE_READY", True), self.assertRaises(ValueError):
                            self.host.route(event, self.root, source, policy_root=self.trusted)
            event, _ = self.bootstrap_candidate({"docs/head-only.md": "Not present in the merge\n"})
            head = event["pull_request"]["head"]["sha"]
            source = self.commit(self.legacy, {self.host.WORKFLOW: (self.trusted / self.host.TEMPLATE).read_text()},
                                 parents=[self.legacy, head])
            self.assertEqual(self.route(event, source)["required"], "true")
            source = self.commit(head, {}, parents=[head, self.legacy])
            with self.assertRaisesRegex(ValueError, "exact ordered event parents"):
                self.route(event, source)

    def live_facts(self, event, source):
        event = copy.deepcopy(event);event["number"] = event["pull_request"]["number"] = 42
        prefix = "repos/" + CHECK.REPOSITORY
        live = {**copy.deepcopy(event["pull_request"]), "state": "open", "merged": False, "merge_commit_sha": source}
        facts = {prefix + "/pulls/42": live,
                 prefix + "/commits/refs/pull/42/merge": {"sha":source,"parents":[
                     {"sha":event["pull_request"][side]["sha"]} for side in ("base","head")]}}
        item=event["pull_request"]["base"]
        facts[prefix+"/branches/apple-ios"]={"name":"apple-ios","protected":True,"commit":{"sha":item["sha"]}}
        item=event["pull_request"]["head"]
        key=prefix+"/git/ref/heads/"+self.host.quote(item["ref"],safe="")
        facts[key]={"ref":"refs/heads/"+item["ref"],"object":{"type":"commit","sha":item["sha"]}}
        return event, facts

    def test_fresh_context_independently_reads_pr_and_both_current_branch_heads(self):
        event, source = self.bootstrap_candidate()
        event, facts = self.live_facts(event, source)
        seen = []
        def api(endpoint):
            seen.append(endpoint)
            return copy.deepcopy(facts[endpoint])
        with patch.object(self.host, "SOURCE_READY", True), patch.object(self.host, "_api_get", side_effect=api):
            observed = self.host.fresh_context(event, self.root, source, policy_root=self.trusted)
        self.assertEqual(seen, list(facts))
        self.assertEqual(observed["candidate"], source)
        self.assertEqual(observed["number"], 42)
        self.assertEqual(observed["baseRef"], "apple-ios")

    def test_fresh_stale_snapshots_bind_current_ios_base_without_rewriting_observations(self):
        event,source=self.bootstrap_candidate();event,facts=self.live_facts(event,source)
        prefix="repos/"+CHECK.REPOSITORY
        actual_base=event["pull_request"]["base"]["sha"]
        snapshots=("1"*40,"2"*40)
        event["pull_request"]["base"]["sha"]=snapshots[0]
        facts[prefix+"/pulls/42"]["base"]["sha"]=snapshots[1]
        for snapshot in snapshots:
            facts[prefix+"/compare/"+snapshot+"..."+actual_base+"?per_page=1"]={"status":"ahead",
                "ahead_by":40,"behind_by":0,"total_commits":40,"base_commit":{"sha":snapshot},
                "merge_base_commit":{"sha":snapshot},"commits":[{"sha":"3"*40}],"files":[]}
        native={"GITHUB_ACTIONS":"true","GITHUB_EVENT_NAME":"pull_request","GITHUB_REPOSITORY":CHECK.REPOSITORY,
            "GITHUB_REPOSITORY_ID":str(CHECK.REPOSITORY_ID),"GITHUB_SHA":source,"GITHUB_WORKFLOW_SHA":source,
            "GITHUB_REF":"refs/pull/42/merge","GITHUB_BASE_REF":"apple-ios","GITHUB_HEAD_REF":event["pull_request"]["head"]["ref"],
            "GITHUB_WORKFLOW_REF":CHECK.REPOSITORY+"/.github/workflows/ios-build-qualification.yml@refs/pull/42/merge"}
        original=copy.deepcopy(event)
        with patch.dict(self.host.os.environ,native,clear=True),patch.object(self.host,"SOURCE_READY",True), \
             patch.object(self.host,"_api_get",side_effect=lambda key:copy.deepcopy(facts[key])):
            self.assertEqual(self.host.fresh_context(event,self.root,source,policy_root=self.trusted)["base"],actual_base)
            self.assertEqual(event,original)
            facts[prefix+"/compare/"+snapshots[0]+"..."+actual_base+"?per_page=1"]["merge_base_commit"]["sha"]="4"*40
            with self.assertRaises(ValueError):self.host.fresh_context(event,self.root,source,policy_root=self.trusted)

    def test_stale_foreign_closed_or_unavailable_current_metadata_never_authorizes_bootstrap(self):
        event, source = self.bootstrap_candidate();event, facts = self.live_facts(event, source)
        pull = "repos/" + CHECK.REPOSITORY + "/pulls/42"
        mutations = (lambda f: f[pull].update(state="closed"), lambda f: f[pull].update(merged=True),
                     lambda f: f[pull].update(number=True), lambda f: f[pull].update(merge_commit_sha=SOURCE),
                     lambda f: f[pull]["base"].update(ref="main"), lambda f: f[pull]["base"].update(sha=SOURCE),
                     lambda f: f[pull]["head"]["repo"].update(id=1), lambda f: f[pull].update(head=[]),
                     lambda f: f[next(k for k in f if k.endswith("apple-ios"))]["commit"].update(sha=SOURCE),
                     lambda f: f[list(f)[-1]]["object"].update(type="tag"))
        for mutate in mutations:
            changed = copy.deepcopy(facts);mutate(changed)
            with patch.object(self.host, "SOURCE_READY", True), patch.object(self.host, "_api_get", side_effect=lambda key: changed.get(key, {})), self.assertRaises(ValueError):
                self.host.fresh_context(event, self.root, source, policy_root=self.trusted)
        with patch.object(self.host, "SOURCE_READY", True), patch.object(self.host, "_api_get", side_effect=ValueError("unavailable")), self.assertRaises(ValueError):
            self.host.fresh_context(event, self.root, source, policy_root=self.trusted)
        with patch.object(self.host, "SOURCE_READY", False), patch.object(self.host, "_api_get") as api, self.assertRaisesRegex(ValueError, "not qualified or activated"):
            self.host.fresh_context(event, self.root, source, policy_root=self.trusted)
        api.assert_not_called()

    def test_final_live_bookend_refuses_ref_change_during_trusted_verification(self):
        event, source = self.bootstrap_candidate();event, facts = self.live_facts(event, source)
        with (patch.object(self.host, "SOURCE_READY", True), patch.object(CHECK, "host_handoff", return_value=self.host),
              patch.object(self.host, "_api_get", side_effect=lambda key: copy.deepcopy(facts[key])) as api):
            with CHECK.fresh_host_candidate(event, self.root, source, policy_root=self.trusted):
                pass
            self.assertEqual(api.call_count, 8)
            with self.assertRaisesRegex(ValueError, "branch head changed"):
                with CHECK.fresh_host_candidate(event, self.root, source, policy_root=self.trusted):
                    facts[list(facts)[-1]]["object"]["sha"] = SOURCE

    def test_fixed_get_reader_has_no_candidate_path_config_or_raw_error_channel(self):
        completed = subprocess.CompletedProcess([], 0, stdout=b'{"number":42}', stderr=b'')
        secret = "offline-fixture-token-not-a-secret"
        with (patch.dict(self.host.os.environ, {"GH_TOKEN": secret, "GH_HOST": "untrusted.invalid", "GH_CONFIG_DIR": "/candidate"}),
              patch.object(self.host.Path, "stat", return_value=SimpleNamespace(st_mode=0o100755, st_uid=0)),
              patch.object(self.host.subprocess, "run", return_value=completed) as run):
            self.assertEqual(self.host._api_get("repos/noah-l-frank/overte/pulls/42"), {"number": 42})
            argv = run.call_args.args[0];environment = run.call_args.kwargs["env"]
            self.assertEqual(argv[:7], ["/usr/bin/gh", "api", "--hostname", "github.com", "--method", "GET", "repos/noah-l-frank/overte/pulls/42"])
            self.assertEqual(environment["GH_TOKEN"], secret)
            self.assertNotIn("GH_HOST", environment)
            self.assertNotEqual(environment["GH_CONFIG_DIR"], "/candidate")
            for response in (subprocess.CompletedProcess([], 1, stdout=b'', stderr=secret.encode()),
                             subprocess.CompletedProcess([], 0, stdout=b'{"number":42,"number":43}', stderr=b''),
                             subprocess.CompletedProcess([], 0, stdout=b'[' + b'0' * 1_000_001 + b']', stderr=b'')):
                run.return_value = response
                with self.assertRaises(ValueError) as error: self.host._api_get("repos/noah-l-frank/overte/pulls/42")
                self.assertNotIn(secret, str(error.exception))

    def test_route_and_final_clis_publish_nothing_when_the_last_live_bookend_changes(self):
        event, source = self.bootstrap_candidate();event, facts = self.live_facts(event, source)
        event_file = self.trusted / "event.json";event_file.write_text(json.dumps(event))
        output = self.trusted / "result.json"
        jobs, run = self.execution(event["pull_request"]["head"]["sha"])
        with patch.object(self.host, "BOOTSTRAP_REVIEWED_TREE", self.bootstrap_tree()):
            selected = self.route(event, source)
        for name, value in (("needs", self.needs(selected)), ("jobs", jobs), ("run", run)):
            (self.trusted / (name + ".json")).write_text(json.dumps(value))
        route, report, wiring, fresh = CHECK.route, CHECK.report, CHECK.validate_wiring, self.host.fresh_context
        def with_policy(function):
            def call(*args, **kwargs):
                kwargs["policy_root"] = self.trusted
                return function(*args, **kwargs)
            return call
        for action in ("route", "verify"):
            arguments = ["check.py", action, "--event", str(event_file), "--candidate", str(self.root), "--output", str(output)]
            if action == "route":
                arguments += ["--sha", source]
            else:
                arguments += ["--source", source, "--needs", str(self.trusted / "needs.json"),
                    "--jobs", str(self.trusted / "jobs.json"), "--run-metadata", str(self.trusted / "run.json"),
                    "--build-number", "688", "--run-id", "123", "--attempt", "1", "--artifacts", str(self.trusted / "absent-ipa")]
            for changed in (False, True):
                output.unlink(missing_ok=True)
                calls = []
                def api(endpoint):
                    calls.append(endpoint)
                    value = copy.deepcopy(facts[endpoint])
                    if changed and endpoint.endswith("/pulls/42") and calls.count(endpoint) > 1:
                        value["merge_commit_sha"] = SOURCE
                    return value
                with (patch.object(self.host, "SOURCE_READY", True), patch.object(self.host, "BOOTSTRAP_REVIEWED_TREE", self.bootstrap_tree()),
                      patch.object(CHECK, "host_handoff", return_value=self.host), patch.object(self.host, "fresh_context", side_effect=with_policy(fresh)),
                      patch.object(self.host, "_api_get", side_effect=api), patch.object(CHECK, "route", side_effect=with_policy(route)),
                      patch.object(CHECK, "report", side_effect=with_policy(report)), patch.object(CHECK, "validate_wiring", side_effect=with_policy(wiring)),
                      patch.object(sys, "argv", arguments), patch.object(sys, "stdout", new_callable=io.StringIO),
                      patch.object(sys, "stderr", new_callable=io.StringIO), patch.dict(self.host.os.environ, {"GITHUB_STEP_SUMMARY": ""})):
                    code = CHECK.main()
                self.assertEqual(code, 1 if changed else 0, (action, calls))
                self.assertEqual(output.exists(), not changed)
                self.assertEqual(len(calls), 5 if changed else 8)

    def test_manual_cli_keeps_full_build_without_pr_api_and_rejects_another_target(self):
        event_file = self.trusted / "manual-event.json"
        output = self.trusted / "manual-output.txt"
        route, wiring = CHECK.route, CHECK.validate_wiring
        def with_policy(function):
            def call(*args, **kwargs):
                kwargs["policy_root"] = self.trusted
                return function(*args, **kwargs)
            return call
        for ref, expected_code in (("refs/heads/apple-ios", 0), ("refs/heads/main", 1)):
            event_file.write_text(json.dumps({"repository": {"full_name": CHECK.REPOSITORY,
                "id": CHECK.REPOSITORY_ID}, "ref": ref}))
            output.unlink(missing_ok=True)
            with (patch.object(self.host, "SOURCE_READY", True), patch.object(CHECK, "host_handoff", return_value=self.host),
                  patch.object(self.host, "_api_get", side_effect=AssertionError("manual route requested PR metadata")) as api,
                  patch.object(CHECK, "route", side_effect=with_policy(route)),
                  patch.object(CHECK, "validate_wiring", side_effect=with_policy(wiring)),
                  patch.object(sys, "argv", ["check.py", "route", "--event", str(event_file), "--candidate", str(self.root),
                      "--sha", self.base, "--output", str(output)]),
                  patch.object(sys, "stdout", new_callable=io.StringIO) as stdout,
                  patch.object(sys, "stderr", new_callable=io.StringIO)):
                self.assertEqual(CHECK.main(), expected_code, ref)
            api.assert_not_called()
            self.assertEqual(output.exists(), expected_code == 0)
            if expected_code == 0:
                result = json.loads(stdout.getvalue())
                self.assertEqual((result["required"], result["host_required"], result["reason"]),
                                 ("true", "true", "manual-application-build-required"))
                self.assertIn("required=true\n", output.read_text())
                self.assertIn("host_required=true\n", output.read_text())

    def test_proven_host_and_docs_changes_keep_ios_host_and_skip_app_only(self):
        for path in ("docs/ios-fixture.md", "tools/test-evidence/run.py"):
            event, source = self.candidate({path: "Reviewed independent input\n"})
            output = self.route(event, source)
            self.assertEqual((output["required"], output["host_required"]), ("false", "true"))
            self.assertEqual(self.verify(output, event, source), output)
            with patch.object(self.host, "SOURCE_READY", True), patch.object(CHECK, "host_handoff", return_value=self.host):
                CHECK.validate_wiring(self.root, event, self.trusted)

    def test_exact_app_independent_fixtures_keep_the_required_ios_host(self):
        paths = ('.github/workflows/issue-intake.yml',
            'tests/device/contracts/chat/test_chat_qml.py',
            'tests/device/contracts/snapshot/test_snapshot_native.py',
            'tests/device/contracts/snapshot/test_snapshot_qml.py',
            'tests/device/self_tests/test_android_adapter.py',
            'tests/device/self_tests/test_pico_property_eligibility.py',
            'tests/issue-intake-test.py', 'tools/issue-intake/install.py')
        base = self.commit(self.base, {path: '# Fixed reviewed host fixture\n' for path in paths})
        inputs = self.host.selector(self.trusted)
        self.assertFalse(set(paths) & self.host.CI_HOST_INDEPENDENT_PATHS)
        for path in paths:
            event, source = self.candidate({path: '# Changed reviewed host fixture\n'}, base=base)
            selected = inputs.candidate_plan(self.root, base, source)
            output = self.route(event, source)
            with self.subTest(path=path):
                self.assertFalse(selected['requires_application_build'])
                self.assertEqual(selected['changes'][0]['kind'], 'independent-host')
                self.assertEqual((output['required'], output['host_required'], output['reason']),
                                 ('false', 'true', 'independent-host-or-documentation-only'))
                self.assertEqual(self.verify(output, event, source), output)
                needs = self.needs(output);needs['host']['result'] = 'skipped'
                with self.assertRaises(ValueError): self.verify(output, event, source, required=needs)
        event, source = self.candidate({path: '# Mixed reviewed host fixtures\n' for path in paths}, base=base)
        output = self.route(event, source)
        self.assertEqual((output['required'], output['host_required']), ('false', 'true'))
        self.assertEqual(self.verify(output, event, source), output)

    def test_app_independent_fixture_modes_neighbors_and_historical_readers_stay_guarded(self):
        paths = ('.github/workflows/issue-intake.yml',
            'tests/device/contracts/chat/test_chat_qml.py',
            'tests/device/contracts/snapshot/test_snapshot_native.py',
            'tests/device/contracts/snapshot/test_snapshot_qml.py',
            'tests/device/self_tests/test_android_adapter.py',
            'tests/device/self_tests/test_pico_property_eligibility.py',
            'tests/issue-intake-test.py', 'tools/issue-intake/install.py')
        base = self.commit(self.base, {path: '# Fixed reviewed host fixture\n' for path in paths})
        inputs = self.host.selector(self.trusted)
        for path in paths:
            for mode in ('100755', '120000'):
                event, source = self.candidate({path: (mode, '# Unexpected fixture mode\n')}, base=base)
                with self.subTest(path=path, mode=mode):
                    selected = inputs.candidate_plan(self.root, base, source)
                    self.assertTrue(selected['requires_application_build'])
                    # Host source validation may reject an alias even before a
                    # route is emitted; either outcome must forbid app omission.
                    try: output = self.route(event, source)
                    except ValueError: pass
                    else: self.assertEqual((output['required'], output['host_required']), ('true', 'true'))
        for changes in ({paths[1]: '# Reviewed fixture\n',
                         'CMakeLists.txt': 'file(READ tests/device/contracts/chat/test_chat_qml.py APP_INPUT)\n'},
                        {'tests/device/contracts/chat/test_chat_extra.py': '# Unknown neighbor\n'},
                        {'tools/issue-intake/install-extra.py': '# Unknown neighboring reader\n'}):
            event, source = self.candidate(changes, base=base)
            with self.subTest(changes=sorted(changes)):
                self.assertEqual((self.route(event, source)['required'], self.route(event, source)['host_required']),
                                 ('true', 'true'))
        drift = self.commit(base, {'CMakeLists.txt': 'file(READ tests/issue-intake-test.py APP_INPUT)\n'})
        event, source = self.candidate({paths[-2]: '# Later host fixture change\n'}, base=drift)
        output = self.route(event, source)
        self.assertEqual((output['required'], output['host_required'], output['reason']),
                         ('true', 'true', 'reader-boundary-not-reviewed'))

    def test_protected_bootstrap_boundary_refresh_restores_only_reviewed_host_omissions(self):
        path = self.trusted / "tools/ios-build-qualification/inputs.py"
        reviewed = path.read_text()
        selector = CHECK.input_selector(self.trusted)
        legacy_boundary = selector.review_boundary(self.root, self.legacy)["boundary"]
        self.assertNotEqual(legacy_boundary, selector.REVIEWED_BOUNDARY)
        event, source = self.candidate({"tools/test-evidence/run.py": "# Independent host update\n"})
        # A distinct source length also distinguishes rapid fixture rewrites
        # from a timestamp/size-matching Python bytecode cache entry.
        path.write_text(reviewed.replace(selector.REVIEWED_BOUNDARY, legacy_boundary)
                        + "\n# Previous trusted deployment anchor.\n")
        stale = self.route(event, source)
        self.assertEqual((stale["required"], stale["host_required"], stale["reason"]),
                         ("true", "true", "reader-boundary-not-reviewed"))
        path.write_text(reviewed)
        refreshed = self.route(event, source)
        self.assertEqual((refreshed["required"], refreshed["host_required"], refreshed["reason"]),
                         ("false", "true", "independent-host-or-documentation-only"))
        self.assertEqual(self.verify(refreshed, event, source), refreshed)
        self.assertNotEqual(stale["selection"], refreshed["selection"])

    def test_reviewed_ci_reader_complement_skips_own_host_without_a_test_receipt(self):
        inputs = self.host.selector(self.trusted)
        boundary = self.host.ci_host_boundary(inputs.read_snapshot(self.root, self.base))
        event, source = self.candidate({"tools/ios-build-qualification/host.py": "# Changed independent CI owner\n",
                                        "tests/device/run_control_plane_tests.py": "# Changed shared owner\n"})
        with patch.object(self.host, "REVIEWED_CI_HOST_BOUNDARY", boundary):
            output = self.route(event, source)
            self.assertEqual((output["required"], output["host_required"], output["reason"]),
                             ("false", "false", "reviewed-ci-only-host-inputs"))
            self.assertEqual(self.verify(output, event, source), output)
            with patch.object(CHECK, "host_handoff", return_value=self.host), \
                    patch.object(self.host, "verify_execution", side_effect=AssertionError("no host executed")), \
                    patch.object(CHECK, "verify_ipa", side_effect=AssertionError("no IPA built")):
                result = CHECK.report(self.needs(output), source, 688, 123, 1, self.root, [],
                    event=event, candidate=self.root, policy_root=self.trusted)
            self.assertEqual(result["ipa"], "not-required")
            self.assertIsNone(result["hostSelection"]["producer"])
            self.assertIs(result["hostSelection"]["iosHostRequired"], False)
            for name in ("host", "qt", "client"):
                needs = self.needs(output);needs[name]["result"] = "success"
                with self.assertRaises(ValueError): self.verify(output, event, source, required=needs)

    def test_exact_governance_document_omits_host_only_with_regular_reviewed_inputs(self):
        document = "docs/BRANCH_GOVERNANCE.md"
        base = self.commit(self.base, {document: "# Reviewed governance\n"})
        inputs = self.host.selector(self.trusted)
        previous = inputs.read_snapshot(self.root, base)
        boundary = self.host.ci_host_boundary(previous)
        with patch.object(self.host, "REVIEWED_CI_HOST_BOUNDARY", boundary):
            event, source = self.candidate({document: "# Updated governance\n"}, base=base)
            output = self.route(event, source)
            self.assertEqual((output["required"], output["host_required"], output["reason"]),
                             ("false", "false", "reviewed-ci-only-host-inputs"))
            self.assertEqual(self.verify(output, event, source), output)
            changes = ({document: ("100755", "# Unexpected executable document\n")},
                       {document: ("120000", "BRANCH_WORKFLOW.md")},
                       {"docs/BRANCH_GOVERNANCE-extra.md": "# Unknown neighboring document\n"},
                       {document: "# Mixed governance edit\n",
                        "ios/tests/dsym_fixture.py": "# Changed host reader\n"})
            for change in changes:
                with self.subTest(change=change):
                    _, candidate = self.candidate(change, base=base)
                    self.assertIsNone(self.host.ci_host_omission(
                        previous, inputs.read_snapshot(self.root, candidate)))

    def test_exact_doctor_cli_omits_only_ios_host_work_and_preserves_reader_guards(self):
        inputs = self.host.selector(self.trusted)
        previous = inputs.read_snapshot(self.root, self.base)
        boundary = self.host.ci_host_boundary(previous)
        doctor = "tools/repository-health/check.py"
        with patch.object(self.host, "REVIEWED_CI_HOST_BOUNDARY", boundary):
            event, source = self.candidate({doctor: ("100755", "raise RuntimeError('never run Doctor in iOS')\n")})
            output = self.route(event, source)
            self.assertEqual((output["required"], output["host_required"]), ("false", "false"))
            self.assertEqual(self.verify(output, event, source), output)
            added = inputs.read_snapshot(self.root, source)
            removed = self.commit(source, {doctor: None})
            self.assertIsNotNone(self.host.ci_host_omission(added, inputs.read_snapshot(self.root, removed)))
            changes = ({doctor: ("100644", "# Wrong executable mode\n")},
                       {doctor: ("120000", "other.py")},
                       {"tools/repository-health/other.py": "# Unknown neighbor\n"},
                       {"ios/tests/dsym_fixture.py": None})
            for change in changes:
                with self.subTest(change=change):
                    _, candidate = self.candidate(change)
                    self.assertIsNone(self.host.ci_host_omission(previous, inputs.read_snapshot(self.root, candidate)))
            historical = self.commit(self.base, {"ios/tests/dsym_fixture.py": "# Historical new reader\n"})
            _, candidate = self.candidate({doctor: ("100755", "# Later Doctor edit\n")}, base=historical)
            self.assertIsNone(self.host.ci_host_omission(inputs.read_snapshot(self.root, historical),
                                                       inputs.read_snapshot(self.root, candidate)))

    def test_doctor_with_changed_npm_locks_needs_the_actual_bounded_package_plan(self):
        self.npm_fixture()
        event, source = self.candidate({**self.npm_changes(),
            "tools/repository-health/check.py": ("100755", "# Independent Doctor update\n")})
        owner = self.npm_owner(event, source)
        inputs = self.host.selector(self.trusted)
        previous = inputs.read_snapshot(self.root, self.base)
        current = inputs.read_snapshot(self.root, source)
        with patch.object(self.host, "REVIEWED_CI_HOST_BOUNDARY", self.npm_host_boundary):
            self.assertIsNone(self.host.ci_host_omission(previous, current, repository=self.root,
                                                       policy_root=self.trusted))
            admitted = self.host.ci_host_omission(previous, current, repository=self.root,
                                                 package_owner=owner, policy_root=self.trusted)
            self.assertIsNotNone(admitted)
            self.assertEqual(admitted["reason"], "reviewed-ci-and-required-npm-host-inputs")
            self.assertEqual(set(admitted["package_ownership"]["changedPaths"]), self.host.NPM_HOST_PATHS)
            self.assertFalse(inputs.candidate_plan(self.root, self.base, source,
                                                   package_owner=owner)["requires_application_build"])
            self.assertTrue(inputs.candidate_plan(self.root, self.base, source)["requires_application_build"])
            invalid = {**owner, "plan": "0" * 64}
            self.assertIsNone(self.host.ci_host_omission(previous, current, repository=self.root,
                                                       package_owner=invalid, policy_root=self.trusted))

    def test_ci_host_boundary_is_finite_and_binds_both_historical_reader_trees(self):
        inputs = self.host.selector(self.trusted)
        previous = inputs.read_snapshot(self.root, self.base)
        boundary = self.host.ci_host_boundary(previous)
        ci = "tools/ios-build-qualification/host.py"
        with patch.object(self.host, "REVIEWED_CI_HOST_BOUNDARY", boundary):
            # Exercise every reviewed filename without relying on historical Git objects.
            all_ci = self.commit(self.base, {path: (
                "100755" if path in self.host.CI_HOST_EXECUTABLE_PATHS else "100644",
                "# Independent CI fixture\n") for path in self.host.CI_HOST_INDEPENDENT_PATHS})
            selected = self.host.ci_host_omission(previous, inputs.read_snapshot(self.root, all_ci))
            self.assertEqual(set(selected["changedPaths"]), self.host.CI_HOST_INDEPENDENT_PATHS)
            self.assertTrue(set(REVIEWED_ANDROID_CI_PATHS).issubset(selected["changedPaths"]))
            self.assertTrue(set(REVIEWED_SANDBOX_CI_PATHS).issubset(selected["changedPaths"]))
            mode_change = self.commit(all_ci, {ci: ("100755", "# Changed independent executable mode\n")})
            self.assertIsNone(self.host.ci_host_omission(inputs.read_snapshot(self.root, all_ci),
                                                       inputs.read_snapshot(self.root, mode_change)))
            removed_ci = self.commit(all_ci, {ci: None})
            self.assertIsNotNone(self.host.ci_host_omission(inputs.read_snapshot(self.root, all_ci),
                                                          inputs.read_snapshot(self.root, removed_ci)))
            cases = ({"ios/tests/dsym_fixture.py": "# Changed imported helper\n"},
                     {"ios/tests/port-contract-test.py": "# Changed source reader\n"},
                     {"ios/tests/port-contract-test.py": None},
                     {"docs/ios/HOST_PREPARATION.md": "Changed consumed documentation\n"},
                     {"tools/new-native-input.h": "class QRegExp {};\n"},
                     {"ios/release-check/test_added.py": "# New discovered test\n"},
                     {"tests/device/ios/self_tests/test_added.py": "# New discovered test\n"},
                     {"unknown/ci-helper.py": "# Unreviewed input\n"},
                     {"tools/repository-checks/workflows/unreviewed-sync.yml": "# Unreviewed sibling\n"},
                     {"tools/repository-checks/workflows/sync-ci-selection.yml": ("100755", "# Unreviewed executable YAML\n")},
                     {"tools/repository-checks/workflows/metadata-edits/repository-checks.yml": ("100755", "# Unreviewed executable YAML\n")},
                     {"tools/repository-checks/workflows/metadata-edits/codeql.yml": ("100755", "# Unreviewed executable YAML\n")},
                     {"tools/repository-checks/workflows/metadata-edits/codeql-pinned.yml": ("100755", "# Unreviewed executable YAML\n")},
                     {"tools/repository-checks/workflows/metadata-edits/codeql-pinned.yml": ("120000", "unreviewed-target")},
                     {"tools/repository-checks/workflows/metadata-edits/codeql-pinned-extra.yml": "# Unreviewed sibling\n"},
                     {"tools/repository-checks/workflows/metadata-edits/sync-test-reuse.yml": ("100755", "# Unreviewed executable YAML\n")},
                     {"tools/repository-checks/workflows/metadata-edits/unreviewed.yml": "# Unreviewed sibling\n"},
                     {"ios/tests/port-contract-test.py": ("100755", "# Changed mode\n")},
                     {ci: ("120000", "outside")},
                     {ci: ("100755", "# Unreviewed executable CI addition\n")},
                     {"unknown-link": ("120000", "outside")},
                     {"unknown-gitlink": ("160000", "")})
            cases += tuple({path: (mode, "# Nonordinary Android CI fixture\n")}
                           for path in REVIEWED_ANDROID_CI_PATHS for mode in ("100755", "120000"))
            cases += tuple({path: "# Unknown sibling or real product target\n"} for path in (
                ".github/android-owner-transfer-unreviewed.json",
                "tests/android-owner-transfer-unreviewed-test.py",
                "tools/repository-checks/android_handoff_unreviewed.py",
                "tools/repository-checks/workflows/android-owned/handoff/android/phone/tests/unreviewed.py",
                "android/phone/tests/phone-release-metadata-test.py"))
            cases += tuple({path: (mode, "# Nonordinary sandbox CI fixture\n")}
                           for path in REVIEWED_SANDBOX_CI_PATHS for mode in ("100755", "120000"))
            cases += tuple({path: "# Unknown sandbox sibling or native scanner input\n"} for path in (
                ".github/shared-sandbox-extra.json",
                ".github/workflows/shared-sandbox-host-extra.yml",
                "tools/repository-checks/workflows/shared-sandbox-extra.yml",
                "tools/repository-checks/workflows/producers/repository-checks-extra.yml",
                "tools/repository-checks/workflows/producers/protected-project-tests-android-platform-extra.yml",
                "tools/repository-checks/workflows/producers/parent-qualification-android-platform-extra.yml",
                "tools/test-evidence/sandbox_extra.py",
                "tools/test-evidence/sandbox_native.h"))
            for changes in cases:
                with self.subTest(changes=changes):
                    revision = self.commit(self.base, {ci: "# Independent CI edit\n", **changes})
                    self.assertIsNone(self.host.ci_host_omission(previous, inputs.read_snapshot(self.root, revision)))
            drift = self.commit(self.base, {"ios/tests/dsym_fixture.py": "# Historical new reader\n"})
            restored = self.commit(drift, {ci: "# CI edit\n", "ios/tests/dsym_fixture.py": None})
            self.assertEqual(self.host.ci_host_boundary(inputs.read_snapshot(self.root, restored)), boundary)
            self.assertIsNone(self.host.ci_host_omission(inputs.read_snapshot(self.root, drift),
                                                       inputs.read_snapshot(self.root, restored)))
            self.assertIsNone(self.host.ci_host_omission(previous, previous))

    def test_application_requirement_never_uses_ci_host_omission(self):
        event, source = self.candidate({"interface/src/changed.cpp": "// Application input\n"})
        with patch.object(self.host, "ci_host_omission", side_effect=AssertionError("app needs full host")):
            output = self.route(event, source)
        self.assertEqual((output["required"], output["host_required"]), ("true", "true"))

    def npm_fixture(self):
        """Bind real immutable synthetic packages to disposable trusted definitions."""
        consumers = CHECK.input_selector().npm_selector()
        self.npm_policies = copy.deepcopy(consumers.PROJECTS)
        sources = {}
        for project, definition in self.npm_policies.items():
            sources[project + "/package.json"] = '{"private":true}\n'
            sources[project + "/consumer.js"] = 'module.exports = 1;\n'
            sources[project + "/package-lock.json"] = self.npm_lock(project, definition["old"])
        self.base = self.commit(self.base, sources)
        snapshot = consumers._snapshot(self.root, self.base)
        for project, definition in self.npm_policies.items():
            complement = consumers._digest(consumers._complement(snapshot, project))
            lock = json.loads(sources[project + "/package-lock.json"])
            graph = consumers._digest(consumers._graph(lock, definition["node"]))
            definition.update({"complement": complement, "graph": graph, "entries": 2})
        # Review only the disposable policy data in memory. Keep the actual
        # immutable selector implementation and avoid rewriting tool source.
        consumers.PROJECTS = copy.deepcopy(self.npm_policies)
        original_selector = self.host.selector

        def fixture_selector(policy_root):
            module = original_selector(policy_root)
            module.npm_selector = lambda: consumers
            return module

        selector_patch = patch.object(self.host, "selector", side_effect=fixture_selector)
        selector_patch.start(); self.addCleanup(selector_patch.stop)
        target = self.trusted / ".github/repository-checks.json"
        target.write_text(json.dumps({"repository": CHECK.REPOSITORY, "repository_id": CHECK.REPOSITORY_ID,
                                      "required_contexts": ["repository-checks"]}))
        inputs = self.host.selector(self.trusted)
        boundary = inputs.review_boundary(self.root, self.base)["boundary"]
        target = self.trusted / "tools/ios-build-qualification/inputs.py"
        target.write_text(target.read_text().replace(inputs.REVIEWED_BOUNDARY, boundary)
                          + "\n# Reviewed synthetic npm reader graph.\n")
        self.npm_host_boundary = self.host.ci_host_boundary(inputs.read_snapshot(self.root, self.base))

    def npm_lock(self, project, dependency):
        return json.dumps({"lockfileVersion": 3, "packages": {"": {"name": "fixture"},
            self.npm_policies[project]["node"]: dependency,
            "node_modules/unchanged": {"version": "1.0.0"}}}) + "\n"

    def npm_changes(self):
        return {project + "/package-lock.json": self.npm_lock(project, definition["new"])
                for project, definition in self.npm_policies.items()}

    def npm_owner(self, event, source):
        inputs = self.host.selector(self.trusted)
        base = event["pull_request"]["base"]["sha"]
        profiles = inputs.npm_selector().select(self.root, base, source)
        value = {"base": base, "candidate": source, "tree": profiles["candidate"]["tree"], "unknown": False,
                 "consumer_generation": True, "policy": {"trusted-fixture": "a" * 64},
                 "dependency_profiles": profiles,
                 "package_set": [project for project, selected in profiles["projects"].items() if selected["required"]]}
        value["plan"] = inputs._digest(value).removeprefix("sha256:")
        return value

    def npm_controller(self, owner, *, generation=True, mandatory=True, activated=False):
        return SimpleNamespace(validate_wiring=Mock(return_value="npm-consumers-v1"),
            consumer_generation=Mock(return_value=generation), has_staged_caller=Mock(return_value=mandatory),
            activated=Mock(return_value=activated), candidate_plan=Mock(return_value=owner))

    def test_required_five_workflow_npm_owner_omits_only_unchanged_ios_readers(self):
        self.npm_fixture()
        event, source = self.candidate({**self.npm_changes(),
            "tools/repository-checks/npm_consumers.py": "candidate code must never execute\n",
            "tools/repository-checks/workflows/npm-consumers/browser-client.yml": "# Independent CI\n"})
        owner = self.npm_owner(event, source)
        controller = self.npm_controller(owner)  # Explicit target activation can still be main-only.
        with patch.object(self.host, "package_controller", return_value=controller), \
                patch.object(self.host, "REVIEWED_CI_HOST_BOUNDARY", self.npm_host_boundary):
            output = self.route(event, source)
            self.assertEqual((output["required"], output["host_required"], output["reason"]),
                             ("false", "false", "reviewed-ci-and-required-npm-host-inputs"))
            controller.validate_wiring.assert_called_with(self.root)
            controller.consumer_generation.assert_called_with(self.root)
            controller.candidate_plan.assert_called_with(self.root, event, source)
            self.assertEqual(self.verify(output, event, source), output)
            with patch.object(self.host, "verify_execution", side_effect=AssertionError("no host executed")), \
                    patch.object(CHECK, "host_handoff", return_value=self.host):
                result = CHECK.report(self.needs(output), source, 688, 123, 1, self.root, [],
                                      event=event, candidate=self.root, policy_root=self.trusted)
            self.assertEqual(result["ipa"], "not-required")
            self.assertIsNone(result["hostSelection"]["producer"])
            controller.candidate_plan.return_value = {**owner, "plan": "0" * 64}
            with self.assertRaises(ValueError): self.verify(output, event, source)
        inputs = self.host.selector(self.trusted)
        previous = inputs.read_snapshot(self.root, self.base); current = inputs.read_snapshot(self.root, source)
        with patch.object(self.host, "REVIEWED_CI_HOST_BOUNDARY", self.npm_host_boundary):
            self.assertIsNone(self.host.ci_host_omission(previous, current))
            self.assertIsNotNone(self.host.ci_host_omission(previous, current, repository=self.root,
                                                           package_owner=owner, policy_root=self.trusted))

    def test_npm_owner_requires_full_generation_and_independent_mandatory_aggregate(self):
        self.npm_fixture(); event, source = self.candidate(self.npm_changes())
        owner = self.npm_owner(event, source)
        for controller in (self.npm_controller(owner, generation=False),
                           self.npm_controller(owner, mandatory=False),
                           self.npm_controller({**owner, "consumer_generation": False})):
            with self.subTest(controller=controller), patch.object(self.host, "package_controller", return_value=controller):
                output = self.route(event, source)
                self.assertEqual((output["required"], output["host_required"]), ("true", "true"))
        controller = self.npm_controller(owner)
        controller.validate_wiring.side_effect = ValueError("incomplete five-workflow tuple")
        with patch.object(self.host, "package_controller", return_value=controller):
            self.assertEqual(self.route(event, source)["required"], "true")
        controller = self.npm_controller(owner)
        (self.trusted / ".github/repository-checks.json").write_text(json.dumps({"repository": CHECK.REPOSITORY,
            "repository_id": CHECK.REPOSITORY_ID, "required_contexts": []}))
        with patch.object(self.host, "package_controller", return_value=controller):
            self.assertEqual(self.route(event, source)["required"], "true")
        with patch.object(self.host, "package_controller", side_effect=ValueError("owner unavailable")):
            self.assertEqual(self.route(event, source)["required"], "true")

    def test_reviewed_npm_formatting_omits_ios_jobs_without_a_package_execution_claim(self):
        self.npm_fixture()
        project = "browser-client"
        content = json.dumps(json.loads(self.npm_lock(project, self.npm_policies[project]["old"])), indent=4)
        event, source = self.candidate({project + "/package-lock.json": content})
        owner = self.npm_owner(event, source)
        self.assertEqual(owner["package_set"], [])
        with patch.object(self.host, "package_controller", return_value=self.npm_controller(owner)), \
                patch.object(self.host, "REVIEWED_CI_HOST_BOUNDARY", self.npm_host_boundary):
            output = self.route(event, source)
            self.assertEqual((output["required"], output["host_required"]), ("false", "false"))
            self.assertEqual(self.verify(output, event, source), output)

    def test_full_required_package_graph_omits_unchanged_ios_app_and_host(self):
        self.npm_fixture()
        for project in self.npm_policies:
            changes=json.loads(self.npm_changes()[project+"/package-lock.json"])
            changes["packages"]["node_modules/unchanged"]["version"]="9.0.0"
            event,source=self.candidate({project+"/package-lock.json":json.dumps(changes)})
            owner=self.npm_owner(event,source)
            self.assertEqual(owner["dependency_profiles"]["projects"][project]["profile"],"full")
            self.assertIn(project,owner["package_set"])
            with self.subTest(project=project), \
                    patch.object(self.host,"package_controller",return_value=self.npm_controller(owner)), \
                    patch.object(self.host,"REVIEWED_CI_HOST_BOUNDARY",self.npm_host_boundary):
                output=self.route(event,source)
                self.assertEqual((output["required"],output["host_required"]),("false","false"))
                self.assertEqual(self.verify(output,event,source),output)

    def test_npm_owned_selection_keeps_unknown_product_config_and_modes_full(self):
        self.npm_fixture()
        cases = ({"browser-client/consumer.js": "module.exports = 2;\n"},
                 {"postcss.config.cjs": "throw Error('never execute');\n"},
                 {".npmrc": "registry=https://example.invalid\n"},
                 {"interface/src/changed.cpp": "// Native product input\n"},
                 {"ios/release-check/test_added.py": "# New discovered test\n"},
                 {"unknown/input.py": "# Unknown input\n"},
                 {"unknown-link": ("120000", "outside")},
                 {"unknown-gitlink": ("160000", "")},
                 {"browser-client/package-lock.json": ("100755", self.npm_changes()["browser-client/package-lock.json"])},
                 {"browser-client/package-lock.json": ("120000", "package.json")},
                 {"browser-client/package-lock.json": None})
        for changes in cases:
            with self.subTest(changes=changes):
                event, source = self.candidate({**self.npm_changes(), **changes})
                owner = self.npm_owner(event, source)
                with patch.object(self.host, "package_controller", return_value=self.npm_controller(owner)), \
                        patch.object(self.host, "REVIEWED_CI_HOST_BOUNDARY", self.npm_host_boundary):
                    output = self.route(event, source)
                    self.assertEqual((output["required"], output["host_required"]), ("true", "true"))

    def test_npm_host_boundary_rejects_historical_reader_drift_and_keeps_app_proof_separate(self):
        self.npm_fixture()
        drift = self.commit(self.base, {"docs/ios/HOST_PREPARATION.md": "Historical host reader input\n"})
        event, source = self.candidate(self.npm_changes(), base=drift)
        owner = self.npm_owner(event, source)
        with patch.object(self.host, "package_controller", return_value=self.npm_controller(owner)), \
                patch.object(self.host, "REVIEWED_CI_HOST_BOUNDARY", self.npm_host_boundary):
            output = self.route(event, source)
            self.assertEqual((output["required"], output["host_required"]), ("false", "true"))
        drift = self.commit(self.base, {"ios/tests/imported-reader.py": "# Historical new helper\n"})
        event, source = self.candidate(self.npm_changes(), base=drift)
        owner = self.npm_owner(event, source)
        with patch.object(self.host, "package_controller", return_value=self.npm_controller(owner)), \
                patch.object(self.host, "REVIEWED_CI_HOST_BOUNDARY", self.npm_host_boundary):
            output = self.route(event, source)
            self.assertEqual((output["required"], output["host_required"]), ("true", "true"))

    def test_exact_three_tree_noop_can_skip_host_and_app_without_ci_boundary(self):
        event, source = self.candidate()
        with patch.object(self.host, "ci_host_omission", side_effect=AssertionError("no-op has its own proof")):
            output = self.route(event, source)
        self.assertEqual((output["required"], output["host_required"], output["reason"]), ("false", "false", "unchanged-tree"))
        self.assertEqual(self.verify(output, event, source), output)

    def test_app_unknown_mixed_packaged_mode_and_nonregular_inputs_keep_full(self):
        for changes in ({"interface/src/ios-unknown.cpp": "// application\n"},
                        {"unknown-host-helper.py": "# unknown\n"},
                        {"browser-client/package-lock.json": '{"lockfileVersion":3}\n'},
                        {"script-archive/marketplace/S3Server/package-lock.json": '{"lockfileVersion":3}\n'},
                        {"docs/ios-fixture.md": "Doc\n", "CMakeLists.txt": "project(Changed)\n"},
                        {"interface/resources/README.md": "Packaged source\n"},
                        {"docs/ios-fixture.md": ("100755", "Executable document\n")},
                        {"docs/ios-fixture.md": ("120000", "outside")},
                        {"docs/vendor": ("160000", "")}):
            with self.subTest(changes=changes):
                event, source = self.candidate(changes)
                output = self.route(event, source)
                self.assertEqual((output["required"], output["host_required"]), ("true", "true"))
                self.assertEqual(self.verify(output, event, source), output)
        event, source = self.candidate({"docs/ios-fixture.md": "Doc\n"})
        manual = {"repository": event["repository"], "ref": "refs/heads/apple-ios"}
        self.assertEqual(self.route(manual, source)["required"], "true")

    def test_reader_change_then_host_edit_cannot_use_a_stale_boundary(self):
        base = self.commit(self.base, {"CMakeLists.txt": "file(READ tools/test-evidence/run.py APP_INPUT)\n"})
        event, source = self.candidate({"tools/test-evidence/run.py": "# Newly read input\n"}, base=base)
        output = self.route(event, source)
        self.assertEqual((output["required"], output["reason"]), ("true", "reader-boundary-not-reviewed"))

    def test_generation_rejects_each_altered_missing_or_nonregular_component(self):
        for path in self.host.PATHS:
            for value in ("Altered input\n", None, ("120000", "outside"), ("160000", "")):
                with self.subTest(path=path, value=value):
                    source = self.commit(self.base, {path: value})
                    with self.assertRaisesRegex(ValueError, "complete reviewed generation"):
                        self.host.resolve(self.root, source, policy_root=self.trusted)

    def test_next_protected_base_cannot_roll_back_to_complete_legacy_generation(self):
        old = self.git("cat-file", "blob", self.legacy + ":" + self.host.WORKFLOW) + "\n"
        event, source = self.candidate({self.host.WORKFLOW: old})
        with self.assertRaisesRegex(ValueError, "cannot roll back"):
            self.route(event, source)

    def test_missing_test_source_closure_cannot_manufacture_a_host_plan(self):
        event, source = self.candidate({"ios/tests/native_contracts/test_entity_consent_application.py": None})
        with self.assertRaisesRegex(ValueError, "source closure is missing"):
            self.route(event, source)

    def test_final_recomputes_every_output_and_rejects_missing_event_or_failed_selected_job(self):
        event, source = self.candidate({"docs/ios-fixture.md": "Doc\n"})
        output = self.route(event, source)
        for key in output:
            altered = {**output, key: "forged"}
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.verify(altered, event, source)
        for conclusion in ("failure", "skipped", "cancelled", None):
            jobs = self.needs(output);jobs["host"]["result"] = conclusion
            with self.assertRaises(ValueError): self.verify(output, event, source, required=jobs)
        jobs = self.needs(output);jobs["qt"]["result"] = "success"
        with self.assertRaises(ValueError): self.verify(output, event, source, required=jobs)
        with patch.object(CHECK, "host_handoff", return_value=self.host), self.assertRaises(ValueError):
            CHECK.verify_jobs(self.needs(output), source, policy_root=self.trusted)
        for mutate in (lambda e: e["repository"].update(id=1),
                       lambda e: e["pull_request"]["base"].update(ref="main"),
                       lambda e: e["pull_request"]["head"]["repo"].update(full_name="foreign/repo"),
                       lambda e: e["pull_request"]["head"].update(sha=e["pull_request"]["base"]["sha"])):
            changed = copy.deepcopy(event);mutate(changed)
            with self.assertRaises(ValueError): self.verify(output, changed, source)

    def test_host_only_report_requires_actual_same_run_job_and_step_without_ipa(self):
        event, source = self.candidate({"docs/ios-fixture.md": "Doc\n"})
        output = self.route(event, source)
        jobs, run = self.execution(event["pull_request"]["head"]["sha"])
        with patch.object(self.host, "SOURCE_READY", True), patch.object(CHECK, "host_handoff", return_value=self.host), \
                patch.object(CHECK, "verify_ipa", side_effect=AssertionError("host-only must not inspect an IPA")):
            result = CHECK.report(self.needs(output), source, 688, 123, 1, self.root, jobs,
                event=event, candidate=self.root, policy_root=self.trusted, run_metadata=run)
        self.assertEqual((result["ipa"], result["artifact"]), ("not-required", None))
        self.assertEqual(result["hostSelection"]["producer"]["originalExecutionJobId"], 456)
        for mutate in (lambda j: j[0].update(conclusion="failure"), lambda j: j[0].update(status="queued"),
                       lambda j: j[0].update(run_id=999), lambda j: j[0].update(head_sha=SOURCE),
                       lambda j: j[0].update(run_attempt=2), lambda j: j.append(copy.deepcopy(j[0])),
                       lambda j: j[0]["steps"][0].update(conclusion="skipped"),
                       lambda j: j[0].update(steps=[]),
                       lambda j: j[0]["steps"][0].update(completed_at="2026-10-15T10:02:00Z")):
            changed = copy.deepcopy(jobs);mutate(changed)
            with self.assertRaises(ValueError): self.host.verify_execution(changed, run, 123, 1, run["head_sha"])
        for field, wrong in (("id", 99), ("run_attempt", 2), ("head_sha", SOURCE), ("path", "different.yml"),
                             ("run_started_at", "2026-10-15T11:00:00Z")):
            with self.assertRaises(ValueError):
                self.host.verify_execution(jobs, {**run, field: wrong}, 123, 1, run["head_sha"])

    def test_failed_only_retry_cannot_relabel_an_older_host_execution(self):
        jobs, run = self.execution(SOURCE, attempt=2)
        run["run_started_at"] = "2026-10-15T11:00:00Z"
        with self.assertRaisesRegex(ValueError, "first attempt only"):
            self.host.verify_execution(jobs, run, 123, 2, SOURCE)
        run["run_started_at"] = "2026-10-15T10:00:00Z"
        with self.assertRaisesRegex(ValueError, "first attempt only"):
            self.host.verify_execution(jobs, run, 123, 2, SOURCE)

    def test_execution_failure_and_environment_channels_cannot_create_success(self):
        selected = {"host_required": "true", "selection": "fixed"}
        secret = {"GH_TOKEN": "fixture", "GITHUB_OUTPUT": "/fixture", "ACTIONS_RUNTIME_TOKEN": "fixture",
                  "ACTIONS_ID_TOKEN_REQUEST_URL": "fixture", "OVERTE_SKIP_TESTS": "1"}
        with patch.dict(self.host.os.environ, secret), self.host.candidate_environment():
            self.assertFalse(any(name in self.host.os.environ for name in secret))
            self.assertEqual(self.host.os.environ["GIT_CONFIG_VALUE_0"], "false")
        with patch.object(self.host, "route", return_value=selected), patch.object(self.host, "git"), \
                patch.object(self.host, "preflight") as preflight, \
                patch.object(self.host.subprocess, "run", side_effect=subprocess.CalledProcessError(7, ["fixture"])):
            with self.assertRaises(subprocess.CalledProcessError): self.host.execute({}, self.root, SOURCE)
            preflight.assert_called_once_with(self.root)
        with patch.object(self.host, "route", side_effect=[selected, {**selected, "selection": "changed"}]), \
                patch.object(self.host, "git"), patch.object(self.host, "preflight"), patch.object(self.host.subprocess, "run"):
            with self.assertRaisesRegex(ValueError, "source plan changed"):
                self.host.execute({}, self.root, SOURCE)


    def test_next_template_preserves_full_build_jobs_dependencies_and_independent_final(self):
        import yaml
        legacy = yaml.safe_load((ROOT / "tools/ios-build-qualification/workflow.yml").read_text())
        source = (ROOT / self.host.TEMPLATE).read_text()
        current = yaml.safe_load(source)
        for name in ("qt", "client"):
            self.assertEqual(current["jobs"][name], legacy["jobs"][name])
        host = current["jobs"]["host"]
        self.assertEqual(host["if"], "needs.route.outputs.host_required == 'true'")
        old_dependencies = next(s for s in legacy["jobs"]["host"]["steps"] if s.get("name") == "Install host contract dependencies")
        self.assertEqual(next(s for s in host["steps"] if s.get("name") == old_dependencies["name"]), old_dependencies)
        self.assertIn("--event", source);self.assertIn("--candidate candidate", source)
        self.assertIn("--run-metadata", source)
        self.assertIn("/attempts/$GITHUB_RUN_ATTEMPT/jobs", source)
        self.assertIn("/attempts/$GITHUB_RUN_ATTEMPT\"", source)
        self.assertEqual(current["jobs"]["ios-device-build"]["needs"], ["route", "host", "qt", "client"])
        for declaration in re.findall(r"(?m)^\s+uses: (.+)$", source):
            self.assertRegex(declaration, r"^(?:\./\.github/workflows/[a-z-]+\.yml|[^@\s]+@[0-9a-f]{40})$")
        for field in ("host_required", "generation", "selection", "host_inputs"):
            self.assertEqual(current["jobs"]["route"]["outputs"][field], "${{ steps.plan.outputs." + field + " }}")
        for name in ("route", "ios-device-build"):
            self.assertEqual(current["jobs"][name]["permissions"]["pull-requests"], "read")
        route = next(step for step in current["jobs"]["route"]["steps"] if step.get("id") == "plan")
        final = next(step for step in current["jobs"]["ios-device-build"]["steps"] if step.get("name") == "Require selected jobs and verify exact IPA provenance")
        self.assertEqual(route["env"]["GH_TOKEN"], "${{ github.token }}")
        self.assertEqual(final["env"]["GH_TOKEN"], "${{ github.token }}")

    def test_preflight_requires_real_qt_modules_and_preserves_forced_launcher_variants(self):
        seen = []
        qml = Path(self.temporary.name) / "qml"
        modules = ("QtQml", "QtQml/Models", "QtQml/WorkerScript", "QtQuick", "QtQuick/Controls", "QtQuick/Layouts",
                   "QtQuick/Templates", "QtQuick/Window", "Qt/labs/settings", "Qt/labs/folderlistmodel", "QtQuick/Dialogs", "QtTest")
        for name in modules:
            path = qml / name / "qmldir";path.parent.mkdir(parents=True, exist_ok=True);path.write_text("# Fixture module\n")
        def runner(command, **kwargs):
            seen.append(command)
            output = str(qml) if command[0] == "qtpaths6" else "v22.0.0\n"
            return subprocess.CompletedProcess(command, 0, stdout=output)
        environment = {"OVERTE_QML_TEST_RUNNER": "/usr/lib/qt6/bin/qmltestrunner",
                       "OVERTE_HOST_TEST_NETWORK_RUNNER": str(self.root / "ios/ci/host-test-network.sh")}
        with patch.object(self.host.shutil, "which", return_value="/fixture/tool"), \
                patch.object(self.host.os, "access", return_value=True), patch.dict(self.host.os.environ, environment):
            self.host.preflight(self.root, runner=runner)
            self.assertIn(["pkg-config", "--exists", "Qt6Core", "Qt6Gui", "Qt6Qml", "Qt6Concurrent", "Qt6WebChannel", "vulkan", "glm"], seen)
            (qml / "QtTest/qmldir").unlink()
            with self.assertRaisesRegex(ValueError, "mandatory iOS QML module"):
                self.host.preflight(self.root, runner=runner)
            with self.assertRaises(subprocess.CalledProcessError):
                self.host.preflight(self.root, runner=lambda *a, **k: (_ for _ in ()).throw(subprocess.CalledProcessError(1, "pkg-config")))


class HistoryTests(unittest.TestCase):
    def test_history_covers_qualification_failures_and_workflow_identity(self):
        repo = {"full_name": HISTORY.REPOSITORY, "id": HISTORY.REPOSITORY_ID}
        workflows = [{"id": index, "path": f".github/workflows/{name}"}
                     for index, name in enumerate(HISTORY.HISTORY_WORKFLOWS, 1)]
        runs = [{"id": 9000 + item["id"], "workflow_id": item["id"], "path": item["path"],
                 "name": item["path"], "repository": repo, "run_attempt": 1,
                 "run_number": 688 if item["id"] == 1 else 1, "head_sha": SOURCE,
                 "head_branch": "apple-ios" if item["id"] == 1 else "ci/ios/example",
                 "status": "completed", "conclusion": "failure", "event": "pull_request",
                 "created_at": f"2026-09-26T10:0{item['id']}:00Z",
                 "html_url": f"https://github.com/noah-l-frank/overte/actions/runs/{9000 + item['id']}"}
                for item in workflows]
        responses = {
            f"repos/{HISTORY.REPOSITORY}/actions/workflows?per_page=100":
                {"total_count": 2, "workflows": workflows},
            **{f"repos/{HISTORY.REPOSITORY}/actions/workflows/{run['workflow_id']}/runs?per_page=50":
               {"workflow_runs": [run]} for run in runs}}
        with patch.object(HISTORY, "api", side_effect=responses.__getitem__):
            selected, coverage = HISTORY.read_history()
        self.assertEqual(len(selected), 2)
        self.assertTrue(all(item["status"] == "inspected" for item in coverage.values()))
        jobs = lambda _: [{"name": HISTORY.BUILD_JOB, "conclusion": "failure"}]
        report = HISTORY.analyze(selected, jobs, lambda _: [], SOURCE)
        self.assertEqual(report["latestFailure"]["runId"], 9002)
        self.assertEqual(report["latestFailure"]["buildNumber"], 1)
        self.assertEqual(report["latestFailure"]["workflow"]["path"], workflows[1]["path"])
        self.assertIsNone(report["latestDeviceBuild"])
        # A timed-out qualification is also a failure requiring investigation.
        selected[-1]["conclusion"] = "timed_out"
        self.assertEqual(HISTORY.analyze(selected, jobs, lambda _: [], SOURCE)
                         ["latestFailure"]["runId"], 9002)
        # A foreign run must not silently become this fork's build history.
        runs[1]["repository"] = {"full_name": "other/overte", "id": 99}
        with patch.object(HISTORY, "api", side_effect=responses.__getitem__), self.assertRaises(ValueError):
            HISTORY.read_history()

    def test_unregistered_qualification_is_explicit_and_inventory_must_be_complete(self):
        workflow = {"id": 1, "path": ".github/workflows/ios-bootstrap.yml"}
        inventory = {"total_count": 1, "workflows": [workflow]}
        with patch.object(HISTORY, "api", side_effect=[inventory, {"workflow_runs": []}]):
            runs, coverage = HISTORY.read_history()
        self.assertEqual(runs, [])
        self.assertEqual(coverage["ios-build-qualification.yml"]["status"], "not-registered")
        inventory["total_count"] = 2
        with patch.object(HISTORY, "api", return_value=inventory), self.assertRaises(ValueError):
            HISTORY.read_history()

    def test_expired_failure_logs_remain_explicitly_unknown(self):
        with patch.object(HISTORY, "gh", side_effect=subprocess.CalledProcessError(1, ["gh"])):
            result = HISTORY.failure_diagnostics(687)
        self.assertFalse(result["failedLogInspected"])
        self.assertEqual(result["diagnosis"], "unknown")
        with patch.object(HISTORY, "gh", return_value="fatal error: 'AndroidHelper.h' file not found"):
            result = HISTORY.failure_diagnostics(687)
        self.assertTrue(result["failedLogInspected"])
        self.assertEqual(result["missingHeaders"], ["AndroidHelper.h"])

    def test_host_only_success_does_not_replace_a_device_build(self):
        def run(number, conclusion, source):
            return {"id": number, "run_attempt": 1, "run_number": number, "head_sha": source,
                    "head_branch": "apple-ios", "status": "completed", "conclusion": conclusion,
                    "html_url": f"https://github.com/noah-l-frank/overte/actions/runs/{number}",
                    "created_at": f"2026-09-{number - 650:02d}", "event": "push"}
        runs = [run(687, "failure", SOURCE), run(684, "success", SOURCE), run(669, "success", "c" * 40)]
        jobs = {687: [{"name": HISTORY.BUILD_JOB, "conclusion": "failure"}],
                684: [{"name": "host-contracts", "conclusion": "success"}],
                669: [{"name": HISTORY.BUILD_JOB, "conclusion": "success", "steps": [
                    {"name": "Package numbered unsigned client IPA", "conclusion": "success"}]}]}
        artifacts = lambda _: [{"id": 1, "name": "669-overte-ios-integrated-e2e-unsigned-669", "expired": True}]
        result = HISTORY.analyze(runs, jobs.__getitem__, artifacts, SOURCE)
        self.assertEqual(result["latestDeviceBuild"]["buildNumber"], 669)
        self.assertFalse(result["latestDeviceBuild"]["matchesCurrentBranch"])
        self.assertEqual(result["latestDeviceBuild"]["availability"], "expired")
        self.assertEqual(result["latestFailure"]["runId"], 687)
        self.assertEqual(result["installation"]["status"], "unknown")
        unavailable = HISTORY.analyze(runs, jobs.__getitem__, lambda _: [], SOURCE)
        self.assertEqual(unavailable["latestDeviceBuild"]["buildNumber"], 669)
        self.assertEqual(unavailable["latestDeviceBuild"]["availability"], "missing")

    def test_blind_retry_requires_diagnosis_and_external_state_repair(self):
        report = {"sourceRevision": SOURCE, "latestFailure": {"runId": 687, "sourceRevision": SOURCE}}
        for reviewed, diagnosis, retry in ((None, None, None), (686, "x" * 40, None),
                                           (687, "x" * 40, None)):
            with self.assertRaises(ValueError):
                HISTORY.review_failure(report, reviewed, diagnosis, retry)
        report["sourceRevision"] = "c" * 40
        value = HISTORY.review_failure(report, 687, "Guarded the Android-only include that broke iOS compilation.", None)
        self.assertFalse(value["sameSource"])

    def test_app_version_is_not_installation_provenance(self):
        with self.assertRaises(ValueError):
            HISTORY.installation_evidence({"version": "0.1.0", "build": 1}, SOURCE)
        receipt = {"status": "installed-and-vm-stopped", "source": "c" * 40, "sha256": "d" * 64,
                   "build": 669, "utc": "2026-09-15T09:00:48Z", "ipadReturnedToFedora": True}
        result = HISTORY.installation_evidence(receipt, SOURCE)
        self.assertFalse(result["matchesCurrentBranch"])
        self.assertEqual(result["currentDeviceState"], "not-rechecked")


if __name__ == "__main__":
    unittest.main(verbosity=2)
