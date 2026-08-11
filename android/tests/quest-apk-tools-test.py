#!/usr/bin/env python3
"""Host-only tests for Quest APK verification and size reporting."""

import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[2]
VERIFIER = ROOT / "android/ci/verify-quest-apk.py"
ANALYZER = ROOT / "android/ci/analyze-apk-size.py"
LIBRARIES = ("libc++_shared.so", "libinterface.so", "libopenxr_loader.so",
             "libpicoInterface.so", "libpicoOpenXR.so", "libplugins_libopenxr.so")


class QuestApkToolsTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary.name)
        self.aapt = self._tool("aapt", """
if [ "$1 $2" = "dump badging" ]; then
  printf "package: name='%s' versionCode='1' versionName='0.1.0'\n" "${MOCK_PACKAGE:-org.overte.quest.preview}"
  printf "sdkVersion:'26'\ntargetSdkVersion:'35'\n"
else
  printf '%s\n' android.hardware.vr.headtracking com.oculus.intent.category.VR com.oculus.supportedDevices 'quest2|questpro|quest3|quest3s'
fi
""")
        self.signer = self._tool("apksigner", """
printf 'Number of signers: %s\n' "${MOCK_SIGNERS:-1}"
printf 'Signer #1 certificate SHA-256 digest: %064d\n' 0
""")
        self.aligner = self._tool("zipalign", "test \"${MOCK_ALIGNED:-1}\" = 1\n")

    def tearDown(self):
        self.temporary.cleanup()

    def _tool(self, name, body):
        path = self.directory / name
        path.write_text("#!/usr/bin/env bash\nset -eu\n" + body, encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR)
        return path

    def _apk(self, omit=None):
        path = self.directory / "quest.apk"
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("AndroidManifest.xml", b"manifest")
            for library in LIBRARIES:
                if library != omit:
                    archive.writestr(f"lib/arm64-v8a/{library}", b"elf")
            archive.writestr("assets/resources.rcc", b"resource data")
        return path

    def _verify(self, apk, env=None):
        variables = os.environ.copy()
        variables.update(env or {})
        return subprocess.run([str(VERIFIER), str(apk), "--aapt", str(self.aapt),
                               "--apksigner", str(self.signer), "--zipalign", str(self.aligner)],
                              text=True, capture_output=True, env=variables, check=False)

    def test_accepts_expected_quest_apk(self):
        result = self._verify(self._apk())
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["package"], "org.overte.quest.preview")
        self.assertTrue(report["zip_aligned"])

    def test_rejects_wrong_package(self):
        result = self._verify(self._apk(), {"MOCK_PACKAGE": "org.example.wrong"})
        self.assertEqual(result.returncode, 2)
        self.assertIn("expected package", result.stderr)

    def test_rejects_missing_runtime_library(self):
        result = self._verify(self._apk(omit="libopenxr_loader.so"))
        self.assertEqual(result.returncode, 2)
        self.assertIn("required Quest native libraries", result.stderr)

    def test_rejects_bad_alignment(self):
        result = self._verify(self._apk(), {"MOCK_ALIGNED": "0"})
        self.assertEqual(result.returncode, 2)
        self.assertIn("command failed", result.stderr)

    def test_size_budget_is_enforced(self):
        result = subprocess.run([str(ANALYZER), str(self._apk()), "--budget-mib", "0"],
                                text=True, capture_output=True, check=False)
        self.assertEqual(result.returncode, 2)
        self.assertIn("Largest entries", result.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
