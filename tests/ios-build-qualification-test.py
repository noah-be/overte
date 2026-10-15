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
            "result": "success" if decision.get("host_required" if name == "host" else "required") == "true" else "skipped"}
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

    def test_packaged_markdown_mixed_unknown_and_empty_inputs_still_require_app_and_host(self):
        for relative in ("scripts/README.md", "interface/resources/README.md", "unknown/host-helper.py", None):
            with self.subTest(path=relative):
                self.git("checkout", "-q", "--detach", self.base)
                if relative is not None:
                    self.write("tools/test-evidence/run.py", "# Mixed independent host change\n")
                event, merge = self.candidate(relative)
                decision = self.route(event, merge)
                self.assertEqual((decision["required"], decision["host_required"]), ("true", "true"))
                self.assertEqual(self.verify(decision, event, merge), decision)

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
