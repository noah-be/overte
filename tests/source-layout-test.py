#!/usr/bin/env python3
"""Verify the shared/platform source boundary and fail-closed suite selection."""

import json
import importlib.util
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("source_boundary", ROOT / "tools/source-boundary/check.py")
BOUNDARY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BOUNDARY)


class SourceLayoutTests(unittest.TestCase):
    def test_shared_sources_do_not_include_android_owned_headers_unconditionally(self):
        self.assertEqual(BOUNDARY.audit(ROOT), [])

    def test_removed_header_regression_and_conditional_paths(self):
        include = '#include "AndroidHelper.h"\n'
        unsafe = [include,
                  '#ifdef Q_OS_IOS\n' + include + '#endif\n',
                  '#if defined(Q_OS_ANDROID) || defined(Q_OS_IOS)\n' + include + '#endif\n',
                  '#ifndef Q_OS_ANDROID\n' + include + '#endif\n',
                  '#if defined(Q_OS_ANDROID)\n#else\n' + include + '#endif\n',
                  '#if defined(Q_OS_ANDROID)\n#elif FEATURE\n' + include + '#endif\n',
                  '#if UNKNOWN_FEATURE\n' + include + '#endif\n',
                  '#if Q_OS_ANDROID == 0\n' + include + '#endif\n',
                  '#if Q_OS_/**/ANDROID\n' + include + '#endif\n']
        safe = ['#if defined(Q_OS_ANDROID)\n' + include + '#endif\n',
                '#if defined Q_OS_ANDROID && FEATURE\n' + include + '#endif\n',
                '#if FEATURE\n#if defined(__ANDROID__)\n' + include + '#endif\n#endif\n',
                '#if FEATURE\n#elif defined(Q_OS_ANDROID)\n' + include + '#endif\n',
                '#ifndef Q_OS_ANDROID\n#else\n' + include + '#endif\n',
                '/* ' + include + '*/\n',
                '#if defined(ANDROID_APP_PHONE_INTERFACE)\n' + include + '#endif\n']
        for source in unsafe:
            with self.subTest(source=source):
                self.assertTrue(BOUNDARY.violations(source, {"AndroidHelper.h"}, []))
        for source in safe:
            with self.subTest(source=source):
                self.assertEqual(BOUNDARY.violations(source, {"AndroidHelper.h"}, []), [])
        self.assertTrue(BOUNDARY.violations('#include "../../android/phone/NewHeader.h"', set(), [("android",)]))
        with self.assertRaises(ValueError):
            BOUNDARY.violations('#if FEATURE\n', set(), [])

    def test_product_reintroduction_cannot_bypass_the_pull_request_gate(self):
        workflow = (ROOT / ".github/workflows/repository-checks.yml").read_text()
        pull_request = workflow.split("  pull_request:\n", 1)[1].split("  workflow_dispatch:\n", 1)[0]
        self.assertNotIn("paths", pull_request)
        self.assertIn("uses: ./.github/workflows/project-tests.yml", workflow)
        self.assertIn("tools/repository-checks/check.py plan", workflow)

    def test_branch_profile_matches_owned_sources(self):
        profile = json.loads((ROOT / "tests/platform-profile.json").read_text())
        policy = json.loads((ROOT / ".github/platform-source-policy.json").read_text())
        self.assertIn(profile["platform"], ("shared", "android"))
        for path in policy["shared_mobile_files"]:
            self.assertTrue((ROOT / path).is_file(), "shared iOS/Phone dependency: " + path)
        if profile["platform"] == "shared":
            for path in policy["android_roots"] + policy["android_files"]:
                self.assertFalse((ROOT / path).exists(), path)
            for directory in ("interface", "scripts", "tests-manual"):
                unexpected = [str(path.relative_to(ROOT)) for path in (ROOT / directory).rglob("+android*")
                              if path.name not in policy["shared_mobile_selectors"]]
                self.assertEqual(unexpected, [])
        else:
            for path in policy["android_required"]:
                self.assertTrue((ROOT / path).is_file(), path)
            names = {suite["name"] for suite in profile["suites"]}
            self.assertTrue({"pico4-device-free", "android-source-boundary"} <= names)

    def test_main_keeps_manual_workflow_registrations_without_build_implementation(self):
        profile = json.loads((ROOT / "tests/platform-profile.json").read_text())
        if profile["platform"] != "shared":
            return  # Android-owned workflow contracts check the actual implementation.
        policy = json.loads((ROOT / ".github/platform-source-policy.json").read_text())
        for path in policy["dispatch_registrations"]:
            source = (ROOT / path).read_text()
            self.assertIn("workflow_dispatch:", source)
            self.assertIn("select-platform-ref:", source)
            self.assertNotIn("self-hosted", source)
            self.assertNotIn("uses:", source)
            self.assertIn("exit 1", source)

    def test_invalid_platform_profiles_never_silently_drop_product_tests(self):
        with tempfile.TemporaryDirectory(prefix="overte-source-profile-") as directory:
            root = Path(directory)
            (root / "tests").mkdir()
            shutil.copyfile(ROOT / "tests/run-project-tests.py", root / "tests/run-project-tests.py")
            profiles = [
                {"schema": 1, "platform": "unknown", "suites": []},
                {"schema": 1, "platform": "android", "suites": []},
                {"schema": 1, "platform": "android", "suites": [
                    {"name": "product", "entrypoint": "missing.sh", "interpreter": "bash"}]},
                {"schema": 1, "platform": "shared", "suites": [
                    {"name": "product", "entrypoint": "missing.sh", "interpreter": "bash"}]},
            ]
            for profile in profiles:
                with self.subTest(profile=profile):
                    (root / "tests/platform-profile.json").write_text(json.dumps(profile))
                    result = subprocess.run([sys.executable, str(root / "tests/run-project-tests.py"), "--list"],
                                            capture_output=True, text=True)
                    self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
