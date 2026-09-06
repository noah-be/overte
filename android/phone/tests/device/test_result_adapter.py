"""Synthetic host fixtures test actual Phone/Shared consumers; no device claim."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

from result_adapter import ROOT, PLANS, SUITES, EvidenceError, verify_phone_results

class PhoneResultTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="phone-result-fixture-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.catalog = {m["id"]: m for m in json.loads(
            (ROOT / "tests/device/catalog.json").read_text())["modules"]}
        self.write_plan("emulator")

    def write_plan(self, milestone):
        for suite in PLANS[milestone]:
            directory = self.root / suite
            directory.mkdir(exist_ok=True)
            modules = SUITES[suite]
            seconds = 1800 if suite == "stability" else 1
            run = dict(schemaVersion=1, adapter="android-phone-adb", suite=suite,
                       platform="android", physical=milestone == "core", requireComplete=True,
                       capabilities=sorted({c for m in modules for c in self.catalog[m]["requires"]}),
                       modules=list(modules), startedEpochMs=1000, finishedEpochMs=1000+seconds*1000,
                       durationSeconds=seconds, status="passed")
            summary = dict(schemaVersion=1, adapter=run["adapter"], suite=suite, status="passed",
                           results=[dict(id=m, description=self.catalog[m]["description"], status="passed",
                                         returncode=0, durationSeconds=1) for m in modules])
            tree = ET.Element("testsuite", name="device-" + suite, tests=str(len(modules)),
                              failures="0", errors="0", skipped="0", time=str(seconds))
            for module in modules:
                case = ET.SubElement(tree, "testcase", classname="overte.device", name=module, time="1")
                ET.SubElement(case, "system-out").text = "OVT_REDACTED"
            (directory / "run-manifest.json").write_text(json.dumps(run))
            (directory / "summary.json").write_text(json.dumps(summary))
            (directory / "junit.xml").write_bytes(ET.tostring(tree))
            self.identify(directory)

    def identify(self, directory):
        # Test-only identity writer. Production adapter never invents receipts.
        identity = dict(contract="overte-sh004-result-v1", sourceRevision="a"*40,
                        artifactSha256="b"*64)
        for key, name in (("runSha256", "run-manifest.json"), ("summarySha256", "summary.json"),
                          ("junitSha256", "junit.xml")):
            identity[key] = hashlib.sha256((directory / name).read_bytes()).hexdigest()
        (directory / "result-identity.json").write_text(json.dumps(identity))

    def check(self, milestone="emulator"):
        return verify_phone_results(self.root, "a"*40, "b"*64, "android-phone-adb", milestone)

    def test_complete_synthetic_emulator_and_core_bind_without_acceptance(self):
        self.assertEqual(4, len(self.check()))
        self.write_plan("core")
        self.assertEqual(11, len(self.check("core")))

    def test_missing_suite_and_wrong_identity_fail(self):
        (self.root / "tablet-e2e/result-identity.json").unlink()
        with self.assertRaises(EvidenceError): self.check()
        self.write_plan("emulator")
        with self.assertRaises(EvidenceError):
            verify_phone_results(self.root, "c"*40, "b"*64, "android-phone-adb", "emulator")

    def test_wrong_physical_class_missing_operation_or_incomplete_run_fails(self):
        path = self.root / "smoke/run-manifest.json"
        original = json.loads(path.read_text())
        for key, value in (("physical", True), ("capabilities", []), ("requireComplete", False),
                           ("modules", []), ("suite", "unrelated")):
            with self.subTest(key=key):
                path.write_text(json.dumps(original | {key: value}))
                self.identify(path.parent)
                with self.assertRaises(EvidenceError): self.check()

    def test_core_cannot_use_short_virtual_smoke_as_journey(self):
        with self.assertRaises(EvidenceError): self.check("core")
        self.write_plan("core")
        path = self.root / "stability/run-manifest.json"
        run = json.loads(path.read_text())
        run.update(durationSeconds=1700, finishedEpochMs=1701000)
        path.write_text(json.dumps(run))
        xml = self.root / "stability/junit.xml"
        tree = ET.fromstring(xml.read_bytes()); tree.set("time", "1700")
        xml.write_bytes(ET.tostring(tree))
        self.identify(path.parent)
        with self.assertRaises(EvidenceError): self.check("core")

    def test_cli_is_closed_and_reads_actual_consumer(self):
        command = [sys.executable, str(Path(__file__).with_name("result_adapter.py")),
                   "--result-root", str(self.root), "--expected-source-sha", "a"*40,
                   "--expected-artifact-sha256", "b"*64,
                   "--expected-adapter", "android-phone-adb", "--milestone", "emulator"]
        result = subprocess.run(command, capture_output=True, text=True, timeout=5)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("PHONE_RESULTS_BOUND_NOT_ACCEPTED\n", result.stdout)
        result = subprocess.run(command + ["--private-canary"], capture_output=True, text=True, timeout=5)
        self.assertEqual(2, result.returncode)
        self.assertEqual("PHONE_RESULT_ARGUMENTS_REJECTED\n", result.stderr)

    def test_emulator_cli_requires_canonical_runner_evidence(self):
        command = [sys.executable, str(ROOT / "android/phone/emulator/phone_acceptance.py"),
                   "verify-results", "--result", str(ROOT / "android/phone/tests/emulator/fixtures/passing-results.xml"),
                   "--output", str(self.root / "report.txt"), "--runner-result-root", str(self.root),
                   "--expected-source-sha", "a"*40, "--expected-artifact-sha256", "b"*64,
                   "--expected-adapter", "android-phone-adb"]
        result = subprocess.run(command, capture_output=True, text=True, timeout=5)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("PHONE_EMULATOR_RESULTS_BOUND_NOT_ACCEPTED\n", result.stdout)
        (self.root / "smoke/result-identity.json").unlink()
        result = subprocess.run(command, capture_output=True, text=True, timeout=5)
        self.assertEqual(2, result.returncode)
        self.assertIn("shared runner results rejected", result.stderr)

if __name__ == "__main__": unittest.main()
