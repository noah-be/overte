#!/usr/bin/env python3
"""Exercise candidate selection, failing jobs, real archive bindings and history."""

import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile


ROOT = Path(__file__).resolve().parents[1]


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
    return [{'name': name, 'run_id': 123, 'run_attempt': 1, 'head_sha': SOURCE,
             'status': 'completed', 'conclusion': 'success',
             'steps': [{'name': step, 'conclusion': 'success'} for step in steps]} for name in names]


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
            # YAML permits this spelling, but our repository's
            # workflow structure contract requires an unquoted trigger key.
            previous = canonical.replace("\non:\n", "\n'on':\n", 1)
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


class HistoryTests(unittest.TestCase):
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
                    "html_url": f"https://github.com/noah-be/overte/actions/runs/{number}",
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
