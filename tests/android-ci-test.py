#!/usr/bin/env python3
"""Offline Android ownership contracts; no product, native or Gradle builds."""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import copy
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("trusted_android_ci", ROOT / "tools/repository-checks/android.py")
android = importlib.util.module_from_spec(spec)
spec.loader.exec_module(android)

FAST = {
    "test-android-e2e-launcher", "test-android-startup-url-path", "suite-runner-self-test",
    "ci-reproducibility-contract", "shell-syntax-contract", "python-syntax-contract",
    "result-summary-self-test", "android-static-quality", "test-documentation-contract",
    "java-deep-links", "legacy-user-story-policy", "legacy-gradle-dependencies",
    "legacy-gradle-report-harness", "phone-test-inventory", "android-project-module-inventory",
    "pico-harness-self-tests", "java-safe-asset-paths", "pico-audio-input-policy",
    "pico-interface-activity-policy", "native-host-tests", "javascript-test-support",
    "javascript-lifecycle-endurance", "script-app-router", "script-security",
    "script-portal-lifecycle", "qml-components", "pico-audio-jni-boundary",
}
CONTRACT_ONLY = {"phone-contracts", "android-workflow-contracts", "phone-apk-provenance",
                 "phone-release-version", "phone-release-metadata",
                 "phone-release-runner-authorization", "phone-build-parallelism"}
PICO = {"suite-runner", "coverage-matrix", "shell-syntax", "package-contract", "apk-verifier",
        "release-contract", "platform-glue", "android-entrypoints", "webview-bridge",
        "webview-touch-state", "audio-capture-state", "audio-native-transport", "openxr-loader",
        "openxr-input", "openxr-display", "interaction-diagnostics", "tablet-lifecycle",
        "tablet-settings", "create-qml", "create-properties", "create-message", "avatar-hotpath",
        "shadergen-jobs", "world-state", "microphone-runner", "unattended-runner", "device-lock",
        "device-acceptance", "serverless-fixtures", "power-analyzer"}
VR_NATIVE = {"android_vr_openxr_debug_policy", "pico_openxr_input_policy", "pico_openxr_space_policy",
             "pico_openxr_display_policy", "pico_openxr_graphics_policy", "pico_openxr_extension_policy",
             "pico_openxr_event_policy"}
SHA = "sha256:" + "a" * 64


def runtime():
    tools = {name: {"version": "tool 1.0", "executable_digest": SHA} for name in android.TOOLS}
    tools.update(java={"version": 'openjdk 21.0.12 2026-07-21', "executable_digest": SHA},
                 javac={"version": "javac 21.0.12", "executable_digest": SHA},
                 node={"version": "v22.22.0", "executable_digest": SHA},
                 qmltestrunner={"version": "Qt5", "executable_digest": SHA})
    return {"schema": 1, "profile": "android-host-java21-v1", "tools": tools,
            "python": {"version": "3.12.12", "executable_digest": SHA, "packages": {},
                       "lookup": {"mode": "controller-virtualenv", "aliases": ["python", "python3"],
                                  "include_system_site_packages": False, "user_site_enabled": False}, "flags": {"optimize": 0}},
            "gcovr": {"version": "8.4", "executable_digest": SHA},
            "quality": {"shellcheck": {"version": "version: 0.11.0", "executable_digest": SHA},
                        "ruff": {"version": "ruff 0.15.22", "executable_digest": SHA}},
            "system": {"distribution": "ubuntu", "version": "24.04", "architecture": "x86_64",
                       "kernel": "6.8.0", "packages_digest": SHA},
            "trusted_execution": {name: SHA for name in android.EXECUTION_FILES}}


def sign(value):
    value.pop("receipt_digest", None)
    value["receipt_digest"] = android.digest(value)
    return value


class AndroidOwnershipTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="android-ci-offline-")
        self.addCleanup(self.temporary.cleanup)
        self.candidate = Path(self.temporary.name) / "candidate"
        self.candidate.mkdir()
        candidate_policy = self.candidate / ".github/android-checks.json"
        candidate_policy.parent.mkdir()
        candidate_policy.write_text('{"untrusted": "candidate policy must never select the plan"}\n')
        self.policy = android.load_policy()
        suites = [{"id": name, "command": item["command"], "tiers": item["tiers"],
                   "kind": "fixture", "description": name}
                  for name, item in self.policy["catalog_suites"].items()]
        self.catalog_path = self.candidate / "android/common/tests/suite/catalog.json"
        self.catalog_path.parent.mkdir(parents=True)
        self.catalog = {"schemaVersion": 1, "suites": suites}
        self.catalog_path.write_text(json.dumps(self.catalog))
        paths = {item["command"][0] for item in self.policy["catalog_suites"].values()}
        paths |= {item["command"][1] for item in self.policy["executions"].values()}
        for relative in paths:
            path = self.candidate / "android" / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("# Immutable offline source fixture.\n")
        sources = dict(self.policy["robolectric_sources"])
        sources.update(self.policy["branch_robolectric_sources"].get("android-phone", {}))
        self.write_java_sources(sources)
        self.git("init", "-q", "-b", "android-phone")
        self.git("config", "user.email", "android-ci@example.invalid")
        self.git("config", "user.name", "Android CI fixture")
        self.commit()
        self.calls = []
        self.behavior = None
        self.branch = "android-phone"
        self.active_items = None

    def write_java_sources(self, sources):
        for relative, item in sources.items():
            path = self.candidate / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            package, name = item["class"].rsplit(".", 1)
            config = ("@RunWith(RobolectricTestRunner.class)\n@Config(sdk = {" +
                ", ".join(map(str, item["sdks"])) + "}, manifest = Config.NONE)\n") if item["sdks"] else ""
            methods = "\n".join("@Test public void " + method + "() {}" for method in item["methods"])
            path.write_text("package " + package + ";\n" + config + "public final class " + name + " {\n" + methods + "\n}\n")

    def git(self, *args):
        return subprocess.check_output(["git", *args], cwd=self.candidate, stderr=subprocess.PIPE, text=True).strip()

    def commit(self):
        self.git("add", ".")
        self.git("commit", "-qm", "Immutable Android catalog fixture")

    def change_catalog(self, change):
        change(self.catalog)
        self.catalog_path.write_text(json.dumps(self.catalog))
        self.commit()

    def sparse_clone(self, name="sparse"):
        sparse = Path(self.temporary.name) / name
        commands = [["git", "clone", "--quiet", "--no-checkout", "--no-hardlinks", str(self.candidate), str(sparse)],
                    ["git", "-C", str(sparse), "sparse-checkout", "init", "--cone"],
                    ["git", "-C", str(sparse), "sparse-checkout", "set", ".github"],
                    ["git", "-C", str(sparse), "checkout", "--quiet", "--detach", "HEAD"]]
        for command in commands:
            subprocess.run(command, check=True, capture_output=True, text=True)
        self.assertFalse((sparse / "android").exists())
        self.assertTrue((sparse / ".github/android-checks.json").is_file())
        return sparse

    def junit(self, path, names, *, failed=False, skipped=False, duplicate=False, counters=None):
        names = list(names)
        if duplicate:
            names.append(names[0])
        suite = ET.Element("testsuite", tests=str(len(names)), failures="1" if failed else "0",
                           errors="0", skipped="1" if skipped else "0")
        if counters:
            suite.attrib.update(counters)
        for index, name in enumerate(names):
            classname, case_name = name.split("::", 1) if "::" in name else ("android.fixture", name)
            case = ET.SubElement(suite, "testcase", name=case_name, classname=classname)
            if index == 0 and (failed or skipped):
                ET.SubElement(case, "failure" if failed else "skipped")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(ET.tostring(suite))

    def run_command(self, command, timeout, cancelled):
        item_name = None
        for name, item in self.policy["executions"].items():
            expected = item["command"]
            if command[1:2] == expected[1:2]:
                item_name = name
                break
        self.assertIsNotNone(item_name, command)
        self.calls.append(item_name)
        self.assertEqual(timeout, self.policy["executions"][item_name]["timeout"])
        self.assertEqual(os.environ["GIT_CONFIG_COUNT"], "2")
        self.assertEqual(os.environ["GIT_CONFIG_KEY_0"], "maintenance.auto")
        self.assertEqual(os.environ["GIT_CONFIG_VALUE_0"], "false")
        self.assertEqual(os.environ["GIT_CONFIG_KEY_1"], "gc.auto")
        self.assertEqual(os.environ["GIT_CONFIG_VALUE_1"], "0")
        self.assertEqual(os.environ["OVERTE_REQUIRE_QML_TESTS"], "1")
        self.assertEqual(os.environ["QT_QPA_PLATFORM"], "offscreen")
        report_root = Path(os.environ["OVERTE_TEST_REPORT_DIR"])
        item = copy.deepcopy(self.policy["executions"][item_name])
        item["cases"] = self.policy["branch_cases"].get(self.branch, {}).get(item_name, item["cases"])
        if self.active_items is not None:
            item = self.active_items[item_name]
        if self.behavior:
            result = self.behavior(item_name, item, report_root)
            if result is not None:
                return result
        if item["report"] == "native":
            self.junit(report_root / "native/TEST-native.xml", item["cases"])
        elif item["report"] == "pico":
            self.assertEqual(command[-2:], ["--junit", str(report_root / "pico.xml")])
            self.junit(report_root / "pico.xml", item["cases"])
        elif item["report"] == "robolectric":
            self.junit(report_root / "robolectric/TEST-launcher.xml", item["cases"])
        return 0, "offline observed success", ""

    def execute(self, views=None, **kwargs):
        self.active_items = android.plan(self.candidate, self.branch, views=views)["executions"]
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            return android.execute(self.candidate, self.branch, views=views,
                                   run_command=self.run_command, capture=runtime, **kwargs)

    def verify(self, receipt, views=None):
        return android.verify(self.candidate, self.branch, receipt, views=views, environment=runtime())

    def test_reviewed_real_fast_contract_inventory_and_four_branch_coverage(self):
        self.assertEqual(set(self.policy["views"]["fast"]), FAST)
        self.assertEqual(set(self.policy["views"]["contracts"]) - FAST, CONTRACT_ONLY)
        for branch in self.policy["branches"]:
            current = android.plan(self.candidate, branch, views=["fast", "contracts"])
            self.assertEqual(set(current["executions"]), FAST | CONTRACT_ONLY)
            self.assertEqual(len(current["executions"]), 34)
        self.assertEqual(len(set(self.policy["views"]["contracts"]) & FAST), 14)

    def test_full_and_github_only_sparse_plans_preserve_all_actual_branch_variants(self):
        phone_full = android.plan(self.candidate, "android-phone", views=list(android.VIEWS))
        sparse = self.sparse_clone("phone-sparse")
        self.assertEqual(android.plan(sparse, "android-phone", views=list(android.VIEWS)), phone_full)
        self.assertEqual(len(phone_full["executions"]["phone-robolectric-launcher"]["cases"]), 116)
        self.assertEqual(len(phone_full["executions"]["native-host-tests"]["cases"]), 23)
        self.assertEqual(len(phone_full["executions"]["pico4-device-free"]["cases"]), 30)
        # Common branch trees do not contain Phone's additional sourceSet class.
        for relative in self.policy["branch_robolectric_sources"]["android-phone"]:
            if relative not in self.policy["robolectric_sources"]:
                (self.candidate / relative).unlink()
        self.write_java_sources(self.policy["robolectric_sources"])
        self.commit()
        sparse = self.sparse_clone("common-sparse")
        for branch in ("android-main", "android-vr", "android-vr-pico"):
            with self.subTest(branch=branch):
                full = android.plan(self.candidate, branch, views=list(android.VIEWS))
                self.assertEqual(android.plan(sparse, branch, views=list(android.VIEWS)), full)
                self.assertEqual(len(full["executions"]["phone-robolectric-launcher"]["cases"]), 80)
                self.assertEqual(len(full["executions"]["native-host-tests"]["cases"]), 21)
                self.assertEqual(len(full["executions"]["pico4-device-free"]["cases"]),
                                 39 if branch == "android-vr-pico" else 30)

    def test_new_phone_robolectric_class_is_discovered_without_materializing_sources(self):
        relative = "android/phone/apps/phoneInterface/src/test/java/org/overte/phone/NewBoundaryRobolectricTest.java"
        (self.candidate / relative).write_text("package org.overte.phone;\n@RunWith(RobolectricTestRunner.class)\n"
            "@Config(sdk = {26, 35}, manifest = Config.NONE)\npublic final class NewBoundaryRobolectricTest {\n"
            "@Test public void boundaryRemainsClosed() {}\n}\n")
        self.commit()
        sparse = self.sparse_clone()
        full = android.plan(self.candidate, "android-phone", views=["coverage"])
        current = android.plan(sparse, "android-phone", views=["coverage"])
        self.assertEqual(current, full)
        cases = current["executions"]["phone-robolectric-launcher"]["cases"]
        self.assertEqual(len(cases), 118)
        self.assertIn("org.overte.phone.NewBoundaryRobolectricTest::boundaryRemainsClosed[26]", cases)
        self.assertIn("org.overte.phone.NewBoundaryRobolectricTest::boundaryRemainsClosed", cases)

    def test_sparse_verification_reads_the_same_source_proof_without_running_candidate_code(self):
        status, receipt = self.execute(["coverage"])
        self.assertEqual(status, 0)
        sparse = self.sparse_clone()
        self.assertEqual(android.verify(sparse, "android-phone", receipt, views=["coverage"],
                                       environment=runtime())["verified"], "true")
        command = mock.Mock(side_effect=AssertionError("planning cannot execute candidate code"))
        capture = mock.Mock(side_effect=AssertionError("empty plan needs no runtime"))
        with self.assertRaisesRegex(android.AndroidError, "source input is unavailable"):
            android.execute(sparse, "android-phone", views=["coverage"], run_command=command, capture=capture)
        with redirect_stdout(io.StringIO()):
            status, empty = android.execute(sparse, "android-phone", views=[], run_command=command, capture=capture)
        self.assertEqual(status, 0)
        self.assertEqual(android.verify(sparse, "android-phone", empty, views=[])["verified"], "true")
        command.assert_not_called()
        capture.assert_not_called()

    def test_git_catalog_entrypoint_and_java_deletions_fail_in_full_and_sparse_plans(self):
        initial = self.git("rev-parse", "HEAD")
        paths = ("android/common/tests/suite/catalog.json", "android/common/tests/shell-syntax-test.sh",
                 next(iter(self.policy["robolectric_sources"])))
        for index, relative in enumerate(paths):
            with self.subTest(path=relative):
                self.git("reset", "--hard", "--quiet", initial)
                (self.candidate / relative).unlink()
                self.commit()
                sparse = self.sparse_clone("missing-" + str(index))
                for checkout in (self.candidate, sparse):
                    with self.assertRaisesRegex(android.AndroidError, "source is missing"):
                        android.plan(checkout, "android-phone")

    def test_git_symlink_and_gitlink_sources_cannot_supply_catalog_entrypoint_or_java(self):
        initial = self.git("rev-parse", "HEAD")
        paths = ("android/common/tests/suite/catalog.json", "android/common/tests/shell-syntax-test.sh",
                 next(iter(self.policy["robolectric_sources"])))
        for index, relative in enumerate(paths):
            for mode in ("120000", "160000"):
                with self.subTest(path=relative, mode=mode):
                    self.git("reset", "--hard", "--quiet", initial)
                    path = self.candidate / relative
                    path.unlink()
                    if mode == "120000":
                        path.symlink_to("/bin/true")
                        self.commit()
                    else:
                        path.mkdir()
                        self.git("update-index", "--add", "--cacheinfo", mode, initial, relative)
                        self.git("commit", "-qm", "Non-regular immutable Android source fixture")
                    sparse = self.sparse_clone("nonregular-" + str(index) + "-" + mode)
                    for checkout in (self.candidate, sparse):
                        with self.assertRaisesRegex(android.AndroidError, "not a regular blob"):
                            android.plan(checkout, "android-phone")

    def test_discovered_java_symlinks_and_gitlinks_cannot_escape_the_case_inventory(self):
        initial = self.git("rev-parse", "HEAD")
        relative = "android/phone/apps/phoneInterface/src/test/java/org/overte/phone/NewBoundaryRobolectricTest.java"
        for mode in ("120000", "160000"):
            with self.subTest(mode=mode):
                self.git("reset", "--hard", "--quiet", initial)
                path = self.candidate / relative
                if path.is_symlink():
                    path.unlink()
                if mode == "120000":
                    path.symlink_to("PermissionsActivityRobolectricTest.java")
                    self.commit()
                else:
                    path.mkdir()
                    self.git("update-index", "--add", "--cacheinfo", mode, initial, relative)
                    self.git("commit", "-qm", "Discovered non-regular Java source fixture")
                sparse = self.sparse_clone("new-source-" + mode)
                for checkout in (self.candidate, sparse):
                    with self.assertRaisesRegex(android.AndroidError, "not a regular blob"):
                        android.plan(checkout, "android-phone", views=["coverage"])

    def test_regular_executable_git_mode_remains_supported_and_changes_source_identity(self):
        previous = android.plan(self.candidate, "android-phone")
        relative = "android/common/tests/shell-syntax-test.sh"
        self.git("update-index", "--chmod=+x", relative)
        (self.candidate / relative).chmod(0o755)
        self.git("commit", "-qm", "Executable immutable Android entrypoint fixture")
        current = android.plan(self.candidate, "android-phone")
        self.assertEqual(android.plan(self.sparse_clone(), "android-phone"), current)
        self.assertNotEqual(previous["tree"], current["tree"])
        self.assertNotEqual(previous["plan"], current["plan"])
        self.assertEqual(previous["executions"], current["executions"])

    def test_git_replacement_blob_cannot_substitute_robolectric_source(self):
        previous = android.plan(self.candidate, "android-phone", views=["coverage"])
        relative = next(iter(self.policy["robolectric_sources"]))
        original = self.git("rev-parse", "HEAD:" + relative)
        replacement = subprocess.run(["git", "hash-object", "-w", "--stdin"], cwd=self.candidate,
            input=b"// Counterfeit replacement with no mandatory Java tests.\n", check=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout.decode("ascii").strip()
        self.git("replace", original, replacement)
        self.assertEqual(android.plan(self.candidate, "android-phone", views=["coverage"]), previous)

    def test_oversized_git_catalog_entrypoint_and_java_fail_before_content_read(self):
        initial = self.git("rev-parse", "HEAD")
        paths = ("android/common/tests/suite/catalog.json", "android/common/tests/shell-syntax-test.sh",
                 next(iter(self.policy["robolectric_sources"])))
        actual_run = subprocess.run
        for index, relative in enumerate(paths):
            with self.subTest(path=relative):
                self.git("reset", "--hard", "--quiet", initial)
                (self.candidate / relative).write_bytes(b"x" * (android.MAX_SOURCE_BYTES + 1))
                self.commit()
                oversized = self.git("rev-parse", "HEAD:" + relative)
                sparse = self.sparse_clone("oversized-" + str(index))
                def bounded(command, *args, **kwargs):
                    self.assertNotEqual(command[-3:], ["cat-file", "blob", oversized],
                                        "oversized source contents must never be read")
                    return actual_run(command, *args, **kwargs)
                with mock.patch.object(android.subprocess, "run", side_effect=bounded):
                    for checkout in (self.candidate, sparse):
                        with self.assertRaisesRegex(android.AndroidError, "source is oversized"):
                            android.plan(checkout, "android-phone")

    def test_dirty_full_and_sparse_checkouts_never_produce_an_immutable_plan(self):
        sparse = self.sparse_clone()
        for checkout in (self.candidate, sparse):
            source = checkout / ".github/android-checks.json"
            original = source.read_text()
            for kind in ("unstaged", "staged", "deleted", "untracked"):
                with self.subTest(checkout=checkout.name, kind=kind):
                    untracked = checkout / ".github/untracked.json"
                    if kind == "deleted":
                        source.unlink()
                    elif kind == "untracked":
                        untracked.write_text("untracked candidate input")
                    else:
                        source.write_text("dirty candidate input")
                        if kind == "staged":
                            subprocess.run(["git", "-C", str(checkout), "add", ".github"],
                                           check=True, capture_output=True)
                    with self.assertRaises(ValueError):
                        android.plan(checkout, "android-phone")
                    subprocess.run(["git", "-C", str(checkout), "reset", "--hard", "--quiet", "HEAD"],
                                   check=True, capture_output=True)
                    untracked.unlink(missing_ok=True)
                    self.assertEqual(source.read_text(), original)

    def test_each_owner_runs_once_and_populates_all_selected_views(self):
        status, receipt = self.execute(list(android.VIEWS))
        self.assertEqual(status, 0)
        self.assertEqual(len(self.calls), 40)
        self.assertEqual(len(set(self.calls)), 40)
        self.assertEqual(self.calls.count("phone-robolectric-launcher"), 1)
        self.assertEqual(self.calls.count("pico4-device-free"), 1)
        self.assertNotIn("android-vr-native-policies", self.calls)
        self.assertNotIn("android-vr-pico-runtime", self.calls)
        self.assertEqual(self.verify(receipt, list(android.VIEWS))["verified"], "true")
        self.assertEqual(set(receipt["executions"]["pico4-device-free"]["cases"]), PICO)
        self.assertEqual(set(receipt["views"]["android-vr"]["android-vr-native-policies"]["cases"]), VR_NATIVE)
        self.assertEqual(len(receipt["views"]["android-vr"]["android-vr-pico-runtime"]["cases"]), 16)

    def test_meaningful_instrumented_variants_stay_distinct_and_mutation_is_explicit(self):
        current = android.plan(self.candidate, "android-main")
        self.assertEqual(len(current["executions"]), 39)
        self.assertNotIn("critical-policy-mutations", current["executions"])
        names = {"native-host-tests", "phone-native-coverage", "phone-jvm-coverage", "phone-javascript-coverage"}
        self.assertTrue(names <= set(current["executions"]))
        self.assertEqual(len({current["executions"][name]["variant"] for name in names}), 4)
        status, receipt = self.execute(["mutation"])
        self.assertEqual(status, 0)
        self.assertEqual(self.calls, ["critical-policy-mutations"])
        self.assertEqual(self.verify(receipt, ["mutation"])["verified"], "true")

    def test_cli_can_plan_verified_empty_selection_without_running_product_tests(self):
        result = subprocess.run([os.sys.executable, str(ROOT / "tools/repository-checks/android.py"), "plan",
            "--candidate", str(self.candidate), "--branch", "android-phone", "--no-views"],
            check=True, capture_output=True, text=True)
        current = json.loads(result.stdout)
        self.assertEqual(current["executions"], {})
        self.assertEqual(current["views"], {})

    def test_receipt_and_report_paths_cannot_change_immutable_candidate(self):
        for kwargs in ({"receipt_path": self.candidate / "receipt.json"}, {"reports": self.candidate / "results"}):
            with self.assertRaises(android.AndroidError):
                self.execute([], **kwargs)
        self.assertEqual(self.git("status", "--porcelain"), "")

    def test_reviewed_pico_and_native_case_inventories_are_complete(self):
        self.assertEqual(set(self.policy["executions"]["pico4-device-free"]["cases"]), PICO)
        native = set(self.policy["executions"]["native-host-tests"]["cases"])
        self.assertEqual(len(native), 21)
        self.assertTrue(VR_NATIVE <= native)
        self.assertIn("qt_input_connection_compat", native)
        self.assertIn("phone_pending_handoff_deterministic_properties", native)

    def test_branch_local_phone_and_pico_assertions_cannot_be_lost(self):
        phone = android.plan(self.candidate, "android-phone")
        common = android.plan(self.candidate, "android-main")
        pico = android.plan(self.candidate, "android-vr-pico")
        self.assertEqual(set(phone["executions"]["native-host-tests"]["cases"]) -
                         set(common["executions"]["native-host-tests"]["cases"]),
                         {"phone_lifecycle_handoff", "phone_touch_ui_metrics"})
        self.assertEqual(len(phone["executions"]["native-host-tests"]["cases"]), 23)
        self.assertEqual(set(pico["executions"]["pico4-device-free"]["cases"]) - PICO,
            {"source-inputs-v1", "source-inputs-v2", "source-inputs-v3", "embedded-web", "legacy-web-lifecycle",
             "legacy-web-qt-jni", "native-classloader", "emote", "tablet-e2e-adapter"})
        self.assertEqual(len(pico["executions"]["pico4-device-free"]["cases"]), 39)
        self.assertEqual(len(pico["views"]["pico"]["pico4-device-free"]["cases"]), 39)

    def test_relevant_catalog_omission_unknown_addition_and_duplicate_are_rejected(self):
        changes = [lambda c: c["suites"].pop(),
                   lambda c: c["suites"].append({"id": "unreviewed-fast-test", "tiers": ["fast"], "command": ["unknown.sh"]}),
                   lambda c: c["suites"].append(copy.deepcopy(c["suites"][0]))]
        original = copy.deepcopy(self.catalog)
        for change in changes:
            self.catalog = copy.deepcopy(original)
            self.change_catalog(change)
            with self.assertRaises(android.AndroidError):
                android.plan(self.candidate, "android-phone")

    def test_changed_command_or_tier_cannot_self_approve(self):
        for field, value in [("command", ["--version"]), ("tiers", ["host"])]:
            original = copy.deepcopy(self.catalog)
            self.change_catalog(lambda c: c["suites"][0].update({field: value}))
            with self.assertRaises(android.AndroidError):
                android.plan(self.candidate, "android-phone")
            self.catalog = original
            self.catalog_path.write_text(json.dumps(original))
            self.commit()

    def test_phone_only_host_declaration_is_preserved_without_becoming_a_common_test(self):
        self.change_catalog(lambda c: c["suites"].append({"id": "phone-startup-host-regression",
            "tiers": ["host", "prepared-host"], "command": ["phone/tests/phone-startup-host-test.py"]}))
        self.assertEqual(len(android.plan(self.candidate, "android-phone")["executions"]), 39)

    def test_immutable_identity_and_safe_entrypoints(self):
        source = self.candidate / "android/common/tests/shell-syntax-test.sh"
        source.write_text("dirty source")
        with self.assertRaises(ValueError):
            android.plan(self.candidate, "android-phone")
        self.git("checkout", "--", ".")
        source.unlink()
        source.symlink_to("/bin/true")
        self.commit()
        with self.assertRaises(android.AndroidError):
            android.plan(self.candidate, "android-phone")

    def test_empty_trusted_selection_executes_nothing_and_needs_no_android_runtime(self):
        with mock.patch.object(android, "capture_environment", side_effect=AssertionError("unneeded runtime")):
            status, receipt = self.execute([])
            self.assertEqual(android.verify(self.candidate, "android-phone", receipt, views=[])["verified"], "true")
        self.assertEqual(status, 0)
        self.assertEqual(self.calls, [])
        self.assertIsNone(receipt["environment"])
        with self.assertRaises(android.AndroidError):
            self.verify(receipt)

    def test_successful_pico_driver_which_omits_one_required_case_fails(self):
        def behavior(name, item, report):
            if name == "pico4-device-free":
                self.junit(report / "pico.xml", [x for x in item["cases"] if x != "world-state"])
                return 0, "misleading driver success", ""
        self.behavior = behavior
        status, receipt = self.execute(["pico"])
        self.assertEqual(status, 1)
        self.assertEqual(receipt["executions"]["pico4-device-free"]["returncode"], 0)
        with self.assertRaises(android.AndroidError):
            self.verify(receipt, ["pico"])

    def test_new_pico_cases_and_phone_native_cases_are_observed_not_just_declared(self):
        self.branch = "android-vr-pico"
        status, receipt = self.execute(["pico"])
        self.assertEqual(status, 0)
        self.assertEqual(len(receipt["executions"]["pico4-device-free"]["cases"]), 39)
        self.assertEqual(self.verify(receipt, ["pico"])["verified"], "true")
        def pico_omits_new_cases(name, item, report):
            self.junit(report / "pico.xml", PICO)
            return 0, "old 30-case driver", ""
        self.behavior = pico_omits_new_cases
        self.assertEqual(self.execute(["pico"])[0], 1)
        self.branch = "android-phone"
        def phone_omits_extra_cases(name, item, report):
            if name == "native-host-tests":
                self.junit(report / "native/TEST-native.xml", self.policy["executions"][name]["cases"])
                return 0, "old 21-case driver", ""
        self.behavior = phone_omits_extra_cases
        self.assertEqual(self.execute(["android-vr"])[0], 1)

    def test_successful_native_driver_cannot_omit_vr_subcases(self):
        def behavior(name, item, report):
            if name == "native-host-tests":
                self.junit(report / "native/TEST-native.xml", set(item["cases"]) - VR_NATIVE)
                return 0, "omitted VR cases", ""
        self.behavior = behavior
        status, receipt = self.execute(["android-vr"])
        self.assertEqual(status, 1)
        with self.assertRaises(android.AndroidError):
            self.verify(receipt, ["android-vr"])

    def test_missing_duplicate_skipped_and_inconsistent_junit_cannot_pass(self):
        for mode in ("missing", "duplicate", "skipped", "counters", "extra"):
            def behavior(name, item, report):
                if name != "pico4-device-free":
                    return None
                if mode != "missing":
                    names = item["cases"] + (["unreviewed-case"] if mode == "extra" else [])
                    self.junit(report / "pico.xml", names, duplicate=mode == "duplicate", skipped=mode == "skipped",
                               counters={"tests": "0"} if mode == "counters" else None)
                return 0, "driver exit zero", ""
            self.behavior = behavior
            status, receipt = self.execute(["pico"])
            self.assertEqual(status, 1, mode)
            with self.assertRaises(android.AndroidError):
                self.verify(receipt, ["pico"])

    def test_robolectric_zero_and_all_skipped_reports_fail(self):
        for mode in ("zero", "skipped"):
            def behavior(name, item, report):
                if name == "phone-robolectric-launcher":
                    self.junit(report / "robolectric/TEST-launcher.xml", [] if mode == "zero" else ["lifecycle[api=35]"],
                               skipped=mode == "skipped")
                    return 0, "driver exit zero", ""
            self.behavior = behavior
            status, receipt = self.execute(["coverage"])
            self.assertEqual(status, 1)
            with self.assertRaises(android.AndroidError):
                self.verify(receipt, ["coverage"])

    def test_robolectric_requires_all_classes_sdk_variants_and_new_methods(self):
        status, receipt = self.execute(["coverage"])
        self.assertEqual(status, 0)
        cases = receipt["executions"]["phone-robolectric-launcher"]["cases"]
        self.assertEqual(len(cases), 116)
        self.assertEqual(len({name.split("::")[0] for name in cases}), 8)
        self.assertTrue(any(name.endswith("[24]") for name in cases))
        self.assertTrue(any(name.endswith("[28]") for name in cases))
        def omitted(name, item, report):
            if name == "phone-robolectric-launcher":
                self.junit(report / "robolectric/TEST-launcher.xml", [item["cases"][0]])
                return 0, "successful one-case driver", ""
        self.behavior = omitted
        self.assertEqual(self.execute(["coverage"])[0], 1)
        self.behavior = None
        path = self.candidate / "android/phone/apps/phoneInterface/src/test/java/org/overte/phone/PermissionsActivityRobolectricTest.java"
        source = path.read_text()
        path.write_text(source[:-2] + "@Test public void additionalBoundary() {}\n}\n")
        self.commit()
        status, receipt = self.execute(["coverage"])
        self.assertEqual(status, 0)
        self.assertEqual(len(receipt["executions"]["phone-robolectric-launcher"]["cases"]), 118)
        self.assertEqual(self.verify(receipt, ["coverage"])["verified"], "true")

    def test_new_phone_robolectric_class_is_discovered_and_cannot_be_omitted(self):
        path = self.candidate / "android/phone/apps/phoneInterface/src/test/java/org/overte/phone/NewBoundaryRobolectricTest.java"
        path.write_text("package org.overte.phone;\n@RunWith(RobolectricTestRunner.class)\n"
                        "@Config(sdk = {26, 35}, manifest = Config.NONE)\n"
                        "public final class NewBoundaryRobolectricTest {\n"
                        "@Test public void boundaryRemainsClosed() {}\n}\n")
        self.commit()
        status, receipt = self.execute(["coverage"])
        self.assertEqual(status, 0)
        self.assertEqual(len(receipt["executions"]["phone-robolectric-launcher"]["cases"]), 118)
        def omits_new_class(name, item, report):
            if name == "phone-robolectric-launcher":
                self.junit(report / "robolectric/TEST-launcher.xml", [case for case in item["cases"]
                    if not case.startswith("org.overte.phone.NewBoundaryRobolectricTest::")])
                return 0, "omitted new class", ""
        self.behavior = omits_new_class
        self.assertEqual(self.execute(["coverage"])[0], 1)

    def test_robolectric_highest_sdk_cannot_change_behind_unsuffixed_junit_name(self):
        path = self.candidate / "android/phone/apps/phoneInterface/src/test/java/org/overte/phone/PermissionsActivityRobolectricTest.java"
        # Robolectric names its highest SDK without a suffix. XML names alone
        # therefore cannot distinguish {26,35} from {26,34}.
        source = path.read_text().replace("{26, 35}", "{26, 34}")
        source += "// @Config(sdk = {26, 35}, manifest = Config.NONE)\n"
        path.write_text(source)
        self.commit()
        with self.assertRaises(android.AndroidError):
            android.plan(self.candidate, self.branch, views=["coverage"])

    def test_process_failure_or_optional_skip_is_a_required_failure(self):
        for code in (1, 77, 130, 143):
            self.behavior = lambda *args: (code, "unsuccessful", "")
            status, receipt = self.execute(["mutation"])
            self.assertEqual(status, 1)
            with self.assertRaises(android.AndroidError):
                self.verify(receipt, ["mutation"])

    def test_receipt_omission_changed_source_plan_runtime_or_cases_fails_after_resigning(self):
        _, original = self.execute(["android-vr"])
        changes = [lambda r: r.update(candidate="b" * 40), lambda r: r.update(tree="b" * 40),
                   lambda r: r.update(plan=SHA), lambda r: r["executions"].pop("pico4-device-free"),
                   lambda r: r["executions"]["pico4-device-free"]["cases"].pop("world-state"),
                   lambda r: r["environment"]["tools"]["java"].update(version="openjdk 17.0.1"),
                   lambda r: r["views"]["android-vr"].pop("android-vr-pico-runtime")]
        for change in changes:
            receipt = copy.deepcopy(original)
            change(receipt)
            sign(receipt)
            with self.assertRaises(android.AndroidError):
                self.verify(receipt, ["android-vr"])

    def test_fixed_environment_strips_candidate_overrides_credentials_and_restores_parent(self):
        overrides = {"OVERTE_CMAKE_COMMAND": "/bin/true", "OVERTE_REQUIRE_QML_TESTS": "0", "BASH_ENV": "/invalid",
                     "JAVA_TOOL_OPTIONS": "-invalid", "GRADLE_OPTS": "-invalid",
                     "ORG_GRADLE_PROJECT_overteProductSourceRoot": "/invalid", "GH_TOKEN": "fixture-token", "GITHUB_TOKEN": "fixture-token",
                     "GITHUB_OUTPUT": "/invalid", "GITHUB_ENV": "/invalid", "GITHUB_PATH": "/invalid", "GITHUB_STATE": "/invalid"}
        def behavior(*args):
            for name in overrides:
                if name != "OVERTE_REQUIRE_QML_TESTS":
                    self.assertNotIn(name, os.environ)
        self.behavior = behavior
        with mock.patch.dict(os.environ, overrides):
            self.assertEqual(self.execute(["mutation"])[0], 0)
            for name, value in overrides.items():
                self.assertEqual(os.environ[name], value)

    def test_ambient_git_overrides_cannot_remove_fixed_child_cleanup_policy(self):
        def behavior(*args):
            gc = subprocess.check_output(["git", "config", "--get", "gc.auto"], cwd=self.candidate, text=True).strip()
            maintenance = subprocess.check_output(["git", "config", "--get", "maintenance.auto"], cwd=self.candidate, text=True).strip()
            self.assertEqual((maintenance, gc), ("false", "0"))
        self.behavior = behavior
        overrides = {"GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "gc.auto", "GIT_CONFIG_VALUE_0": "999"}
        with mock.patch.dict(os.environ, overrides):
            self.assertEqual(self.execute(["mutation"])[0], 0)
            self.assertEqual({name: os.environ[name] for name in overrides}, overrides)

    def test_gcovr_launcher_cannot_resolve_to_same_binary_with_a_different_package_prefix(self):
        _, shared_runtime = android._shared()
        directory = Path(self.temporary.name) / "fake-venv/bin"
        directory.mkdir(parents=True)
        python = directory / "python"
        python.symlink_to(os.sys.executable)
        launcher = directory / "gcovr"
        # Both interpreters resolve to the same binary. Only the raw invocation
        # inside this venv is allowed to select its actual gcovr package context.
        launcher.write_text("#!" + os.sys.executable + "\n# offline entrypoint\n")
        with mock.patch.object(android.sys, "executable", str(python)), \
                mock.patch.object(android.shutil, "which", return_value=str(launcher)), \
                mock.patch.object(shared_runtime, "_checked_executable", return_value=python.resolve()), \
                mock.patch.object(android.importlib.metadata, "version", return_value="8.4"):
            with self.assertRaises(android.AndroidError):
                android._gcovr_identity(shared_runtime)
            launcher.write_text("#!" + str(python) + "\n# offline entrypoint\n")
            self.assertEqual(android._gcovr_identity(shared_runtime)["version"], "8.4")

    def test_capture_observes_the_same_fixed_policy_as_candidate_children(self):
        observations = []
        def capture():
            self.assertNotIn("GH_TOKEN", os.environ)
            self.assertNotIn("GITHUB_OUTPUT", os.environ)
            self.assertNotIn("OVERTE_CMAKE_COMMAND", os.environ)
            self.assertEqual(os.environ["OVERTE_REQUIRE_QML_TESTS"], "1")
            self.assertEqual(os.environ["GIT_CONFIG_VALUE_1"], "0")
            self.assertEqual(os.environ["PATH"].split(os.pathsep)[0], str(Path(os.sys.executable).parent))
            observations.append(True)
            return runtime()
        with mock.patch.dict(os.environ, {"GH_TOKEN": "fixture", "GITHUB_OUTPUT": "/fixture", "OVERTE_CMAKE_COMMAND": "/bin/true"}):
            with redirect_stdout(io.StringIO()):
                status, receipt = android.execute(self.candidate, self.branch, views=["mutation"],
                    capture=capture, run_command=self.run_command)
            self.assertEqual(status, 0)
            self.assertEqual(len(observations), 2)
            self.assertEqual(os.environ["GH_TOKEN"], "fixture")
            self.assertEqual(self.verify(receipt, ["mutation"])["verified"], "true")

    def test_real_venv_lookup_preserves_invocation_prefix_and_restores_ambient_environment(self):
        virtualenv = Path(self.temporary.name) / "isolated-python"
        subprocess.run([os.sys.executable, "-m", "venv", "--without-pip", str(virtualenv)], check=True,
                       capture_output=True, text=True)
        code = """
import importlib.util,json,os,sys
from pathlib import Path
spec=importlib.util.spec_from_file_location('trusted_android', %r)
a=importlib.util.module_from_spec(spec);spec.loader.exec_module(a)
old_path=os.environ['PATH'];old_virtual=os.environ.get('VIRTUAL_ENV')
def observed():
    shared,runtime=a._shared()
    result=runtime._python_lookup_identity()
    result['private_present']='GH_TOKEN' in os.environ or 'GITHUB_OUTPUT' in os.environ
    result['fixed_git']=os.environ['GIT_CONFIG_VALUE_1']=='0'
    return result
result=a._capture_effective(observed)
result['restored']=os.environ['PATH']==old_path and os.environ.get('VIRTUAL_ENV')==old_virtual
print(json.dumps(result))
""" % str(ROOT / "tools/repository-checks/android.py")
        environment = dict(os.environ, VIRTUAL_ENV="/wrong-prefix", GH_TOKEN="fixture-token", GITHUB_OUTPUT="/fixture")
        result = subprocess.run([str(virtualenv / "bin/python3"), "-B", "-c", code], check=True,
            capture_output=True, text=True, env=environment)
        value = json.loads(result.stdout)
        self.assertEqual(value["mode"], "controller-virtualenv")
        self.assertFalse(value["private_present"])
        self.assertTrue(value["fixed_git"])
        self.assertTrue(value["restored"])

    def test_runtime_change_or_candidate_mutation_during_execution_invalidates_success(self):
        changed = runtime()
        changed["tools"]["java"]["executable_digest"] = "sha256:" + "b" * 64
        with redirect_stdout(io.StringIO()), self.assertRaises(android.AndroidError):
            android.execute(self.candidate, "android-phone", views=["mutation"], run_command=self.run_command,
                            capture=mock.Mock(side_effect=[runtime(), changed]))
        def behavior(*args):
            self.catalog_path.write_text("changed candidate")
        self.behavior = behavior
        with self.assertRaises(ValueError):
            self.execute(["mutation"])

    def test_runtime_rejects_java17_node20_and_missing_coverage_tools(self):
        for change in [lambda r: r["tools"]["java"].update(version="openjdk 17.0.12"),
                       lambda r: r["tools"]["javac"].update(version="javac 17.0.12"),
                       lambda r: r["tools"]["node"].update(version="v20.1.0"),
                       lambda r: r["gcovr"].update(version="8.3"),
                       lambda r: r["tools"].pop("qmltestrunner")]:
            value = runtime()
            change(value)
            with self.assertRaises(android.AndroidError):
                android.validate_environment(value)

    def test_launch_exception_restores_process_environment(self):
        with mock.patch.dict(os.environ, {"GITHUB_OUTPUT": "/fixture", "OVERTE_REQUIRE_QML_TESTS": "0"}):
            with self.assertRaises(OSError), redirect_stdout(io.StringIO()):
                android.execute(self.candidate, "android-phone", views=["mutation"], capture=runtime,
                    run_command=mock.Mock(side_effect=OSError("offline launch failure")))
            self.assertEqual(os.environ["GITHUB_OUTPUT"], "/fixture")
            self.assertEqual(os.environ["OVERTE_REQUIRE_QML_TESTS"], "0")


if __name__ == "__main__":
    unittest.main()
