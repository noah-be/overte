#!/usr/bin/env python3
"""Actual canonical parser/owned binding, test-only candidate and OS boundaries."""
import argparse
import importlib.util
from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests/device"))
from adapters.appium import adapter


class Base:
    created = 0

    def __init__(self, platform):
        Base.created += 1
        self.platform = platform
        self.adapter_id = "appium-ios"

    def describe(self, selector):
        return {"adapter": self.adapter_id, "executionIdentity": {"untrusted": True}}

    def cleanup(self, selector):
        return {"cleaned": True}


class Binding(unittest.TestCase):
    def load(self, action="describe"):
        return adapter.cli(["--platform", "ios", "--native-binding", action])

    def test_actual_fixed_loader_and_fail_before_base(self):
        args, binding = self.load()
        before = Base.created
        with self.assertRaisesRegex(ValueError, "INPUTS_REQUIRED"):
            binding.create_adapter(args, Base)
        self.assertEqual(before, Base.created)

    def test_no_install_claim_or_session_after_candidate_success(self):
        args, binding = self.load()
        with mock.patch.object(binding, "candidate_preflight") as preflight:
            native = binding.create_adapter(args, Base)
            self.assertEqual(native.describe("test-only"), {"adapter": "appium-ios"})
            self.assertEqual(preflight.call_count, 2)
            for call in (lambda: native.ensure_session("test-only"),
                         lambda: native.invoke("test-only", "app.version", {})):
                with self.assertRaisesRegex(ValueError, "INSTALLED_CODE_BINDING_UNAVAILABLE"):
                    call()
            preflight.side_effect = ValueError("candidate changed")
            with self.assertRaises(ValueError):
                native.describe("test-only")
            self.assertEqual(native.cleanup("test-only"), {"cleaned": True})

    def test_cleanup_needs_no_candidate_preflight(self):
        args, binding = self.load("cleanup")
        with mock.patch.object(binding, "candidate_preflight", side_effect=AssertionError("must not run")):
            native = binding.create_adapter(args, Base)
            self.assertEqual(native.cleanup("test-only"), {"cleaned": True})

    def test_prefix_arguments_and_no_execute_escape(self):
        args, binding = adapter.cli(["--platform", "ios", "--native-binding",
                                    "--candidate-manifest", "test-only.json", "describe"])
        self.assertEqual(args.candidate_manifest, "test-only.json")
        with mock.patch("sys.stderr"), self.assertRaises(SystemExit):
            adapter.cli(["--platform", "ios", "--native-binding", "--execute-simulator", "describe"])

    def test_actual_entrypoint_closes_private_failures(self):
        result = subprocess.run([sys.executable, "-B", str(ROOT / "tests/device/adapters/appium/adapter.py"),
                                 "--platform", "ios", "--native-binding", "describe",
                                 "--target", "private-test-canary"], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr, "OVT_APPIUM_ADAPTER_REJECTED\n")


if __name__ == "__main__":
    unittest.main()
