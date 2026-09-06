#!/usr/bin/env python3
"""Actual Appium CLI dispatch, test-only native/OS boundary; no device use."""
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
from adapters.appium import adapter

FIXTURE = '''
def configure_parser(parser): parser.add_argument("--native-proof", required=True)
def create_adapter(args, base):
    if args.native_proof != "test-only": raise ValueError("private-value")
    class Native(base):
        def __init__(self): self.platform = args.platform; self.adapter_id = "appium-" + args.platform
        def discover(self): return []
        def describe(self, target): return {"adapter": self.adapter_id, "testBoundaryOnly": True}
        def invoke(self, target, operation, values): return {"operation": operation, "count": len(values)}
        def cleanup(self, target): return {"cleaned": True}
    return Native()
'''


class IOSNativeBinding(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="sh004-ios-native-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        (self.root / "ios").mkdir()
        self.path = self.root / "ios/binding.py"
        self.path.write_text(FIXTURE)
        patch = mock.patch.object(native_binding, "ADAPTER_ROOT", self.root)
        patch.start(); self.addCleanup(patch.stop)

    def call(self, action, extra=()):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            result = adapter.main(["--platform", "ios", "--native-binding", "--native-proof", "test-only",
                                   action, "--target", "private-test-target", *extra])
        self.assertEqual(result, 0)
        self.assertNotIn("private-test-target", output.getvalue())
        return json.loads(output.getvalue())

    def test_actual_dispatch_and_prefix_candidate_arguments(self):
        self.assertEqual(self.call("discover"), [])
        self.assertEqual(self.call("describe"), {"adapter": "appium-ios", "testBoundaryOnly": True})
        self.assertEqual(self.call("invoke", ["--operation", "app.version"]), {"operation": "app.version", "count": 0})
        self.assertEqual(self.call("cleanup"), {"cleaned": True})

    def test_missing_binding_never_constructs_base_or_uses_unbound_fallback(self):
        self.path.unlink()
        with mock.patch.object(adapter, "AppiumAdapter") as base:
            with self.assertRaisesRegex(ValueError, "UNAVAILABLE"):
                self.call("describe")
            base.assert_not_called()

    def test_incompatible_platform_and_shared_argument_mutation(self):
        with self.assertRaisesRegex(ValueError, "PRODUCT_REJECTED"):
            adapter.cli(["--platform", "android", "--native-binding", "describe"])
        self.path.write_text(FIXTURE.replace('"--native-proof", required=True', '"--native-proof", dest="platform", required=True'))
        with self.assertRaisesRegex(ValueError, "SHARED_ARGUMENT_MUTATION"):
            self.call("describe")

    def test_no_opt_in_retains_original_diagnostics(self):
        args, module = adapter.cli(["--platform", "ios", "discover"])
        self.assertIsNone(module); self.assertFalse(args.native_binding)

    def test_actual_entrypoint_uses_closed_bound_error(self):
        code = ("import sys,runpy;from pathlib import Path;sys.path.insert(0,sys.argv.pop(1));"
                "from adapters import native_binding;native_binding.ADAPTER_ROOT=Path(sys.argv.pop(1));"
                "sys.argv.pop(0);runpy.run_path(sys.argv[0],run_name='__main__')")
        result = subprocess.run([sys.executable, "-c", code, str(ROOT), str(self.root / "absent"),
            str(ROOT / "adapters/appium/adapter.py"), "--platform", "ios", "--native-binding", "describe",
            "--target", "private-test-target"], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr, "OVT_APPIUM_ADAPTER_REJECTED\n")


if __name__ == "__main__": unittest.main()
