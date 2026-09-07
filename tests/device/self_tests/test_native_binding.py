#!/usr/bin/env python3
"""Canonical CLI/dispatch and fixed native import, with test-only OS boundary."""
import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from adapters import native_binding
from adapters.android import adapter


FIXTURE = '''
def configure_parser(parser):
    parser.add_argument("--native-proof", required=True)
def create_adapter(args, base):
    if args.native_proof != "test-only-os-proof":
        raise ValueError("synthetic-private-value-must-not-escape")
    class Native(base):
        def __init__(self):
            self.kind = args.kind
            self.profile = __import__("adapters.android.adapter", fromlist=["PROFILES"]).PROFILES[args.kind]
        def discover(self): return []
        def selected_target(self, target, action):
            if target != "private-test-only": raise ValueError("no target")
            return target
        def cleanup_target(self, target): return self.selected_target(target, "cleanup")
        def describe(self, target):
            return {"adapter": self.profile["adapter"], "executionIdentity": {
                "schemaVersion": 1, "sourceRevision": "a" * 40,
                "artifactSha256": "b" * 64, "installedCandidateVerified": True}}
        def invoke(self, target, operation, values): return {"operation": operation, "count": len(values)}
        def cleanup(self, target): return {"cleaned": True}
    return Native()
'''


class NativeBinding(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="sh004-native-binding-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        (self.root / "pico4").mkdir()
        self.path = self.root / "pico4/binding.py"
        self.path.write_text(FIXTURE)
        self.patch = mock.patch.object(native_binding, "ADAPTER_ROOT", self.root)
        self.patch.start(); self.addCleanup(self.patch.stop)

    def invoke(self, action, extra=()):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            result = adapter.main(["--kind", "pico", "--native-binding", action,
                                   "--native-proof", "test-only-os-proof", "--target", "private-test-only", *extra])
        self.assertEqual(result, 0)
        self.assertNotIn("private-test-only", output.getvalue())
        return json.loads(output.getvalue())

    def test_actual_canonical_dispatch_uses_native_subclass(self):
        self.assertEqual(self.invoke("discover"), [])
        result = self.invoke("describe")
        self.assertEqual(result["adapter"], "android-pico-adb")
        self.assertTrue(result["executionIdentity"]["installedCandidateVerified"])
        self.assertEqual(self.invoke("invoke", ["--operation", "app.version", "--arguments", "{}"]),
                         {"operation": "app.version", "count": 0})
        self.assertEqual(self.invoke("cleanup"), {"cleaned": True})

    def test_candidate_flags_before_runner_appended_action(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            result = adapter.main(["--kind", "pico", "--native-binding",
                "--native-proof", "test-only-os-proof", "describe", "--target", "private-test-only"])
        self.assertEqual(result, 0)
        self.assertEqual(json.loads(output.getvalue())["adapter"], "android-pico-adb")

    def test_missing_binding_fails_before_any_device_construction(self):
        self.path.unlink()
        with mock.patch.object(adapter, "AndroidAdapter") as base:
            with self.assertRaisesRegex(ValueError, "UNAVAILABLE"):
                self.invoke("describe")
            base.assert_not_called()

    def test_symlink_and_wrong_base_rejected(self):
        other = self.root / "outside.py"; other.write_text(FIXTURE)
        self.path.unlink(); self.path.symlink_to(other)
        with self.assertRaisesRegex(ValueError, "UNAVAILABLE"):
            self.invoke("describe")
        self.path.unlink(); self.path.write_text(FIXTURE.replace("return Native()", "return object()"))
        with self.assertRaisesRegex(ValueError, "BASE_REJECTED"):
            self.invoke("describe")

    def test_shared_argument_override_rejected(self):
        self.path.write_text(FIXTURE.replace('parser.add_argument("--native-proof", required=True)',
            'parser.add_argument("--native-proof", dest="kind", required=True)'))
        with self.assertRaisesRegex(ValueError, "SHARED_ARGUMENT_MUTATION"):
            self.invoke("describe")

    def test_real_entrypoint_missing_binding_does_not_expose_rejected_values(self):
        # Pin an empty TEST-only extension root in the child, so this negative
        # also works after native owners have supplied their real module.
        absent = self.root / "missing"
        code = ("import sys,runpy;from pathlib import Path;sys.path.insert(0,sys.argv.pop(1));"
                "from adapters import native_binding;native_binding.ADAPTER_ROOT=Path(sys.argv.pop(1));"
                "sys.argv.pop(0);runpy.run_path(sys.argv[0],run_name='__main__')")
        result = subprocess.run([sys.executable, "-c", code, str(ROOT), str(absent),
            str(ROOT / "adapters/android/adapter.py"),
            "--kind", "pico", "--native-binding", "describe", "--target", "private-test-only"],
            capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr, "OVT_ANDROID_ADAPTER_REJECTED\n")

    def test_no_opt_in_retains_unbound_diagnostics(self):
        args, module = adapter.cli(["--kind", "pico", "discover"])
        self.assertIsNone(module)
        self.assertFalse(args.native_binding)


if __name__ == "__main__":
    unittest.main()
