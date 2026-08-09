import os
from pathlib import Path
import stat
import subprocess
import tempfile
import unittest


ANDROID_ROOT = Path(__file__).resolve().parents[2]
RUNNER = ANDROID_ROOT / "tests/quality/run-static-quality.sh"


def executable(path: Path, content: str) -> None:
    path.write_text("#!/usr/bin/env bash\nset -euo pipefail\n" + content, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


class StaticQualityHarnessTest(unittest.TestCase):
    def test_installer_and_workflow_pin_versions_and_digests(self):
        installer = (ANDROID_ROOT / "tests/quality/install-tools.sh").read_text(encoding="utf-8")
        requirements = (ANDROID_ROOT / "tests/quality/requirements.txt").read_text(encoding="utf-8")
        workflow = (ANDROID_ROOT.parent / ".github/workflows/android-tests.yml").read_text(
            encoding="utf-8")
        self.assertIn("shellcheck_version=0.11.0", installer)
        self.assertIn(
            "8c3be12b05d5c177a04c29e3c78ce89ac86f1595681cab149b65b97c4e227198",
            installer)
        self.assertIn("ruff==0.15.22", requirements)
        self.assertIn(
            "365523eb91d9224e1bcb03b022fbf0facb8f9e23792a2c53d9d4b3924bdbdebb",
            requirements)
        self.assertLess(workflow.index("tests/quality/install-tools.sh"),
                        workflow.index("tests/run-tests.sh fast"))

    def test_pinned_tools_receive_the_reviewed_inventories(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shellcheck = root / "shellcheck"
            ruff = root / "ruff"
            log = root / "calls"
            executable(shellcheck, r'''
if [[ "${1:-}" == --version ]]; then printf 'version: 0.11.0\n'; exit; fi
printf 'shellcheck:%s\n' "$*" >>"$QUALITY_CALL_LOG"
''')
            executable(ruff, r'''
if [[ "${1:-}" == --version ]]; then printf 'ruff 0.15.22\n'; exit; fi
printf 'ruff:%s\n' "$*" >>"$QUALITY_CALL_LOG"
''')
            result = subprocess.run(
                [RUNNER], cwd=ANDROID_ROOT,
                env={**os.environ, "OVERTE_SHELLCHECK_COMMAND": str(shellcheck),
                     "OVERTE_RUFF_COMMAND": str(ruff), "QUALITY_CALL_LOG": str(log)},
                text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            self.assertEqual(0, result.returncode, result.stdout)
            calls = log.read_text(encoding="utf-8")
            self.assertIn("phone-device-lock.sh", calls)
            self.assertIn("tests/quality/install-tools.sh", calls)
            self.assertIn("tests/suite", calls)
            self.assertIn("--no-cache --select E4,E7,E9,F", calls)

    def test_wrong_tool_version_fails_before_linting(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shellcheck = root / "shellcheck"
            ruff = root / "ruff"
            executable(shellcheck, "printf 'version: 0.10.0\\n'\n")
            executable(ruff, "printf 'ruff 0.15.22\\n'\n")
            result = subprocess.run(
                [RUNNER], cwd=ANDROID_ROOT,
                env={**os.environ, "OVERTE_SHELLCHECK_COMMAND": str(shellcheck),
                     "OVERTE_RUFF_COMMAND": str(ruff)},
                text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            self.assertEqual(1, result.returncode)
            self.assertIn("ShellCheck 0.11.0 is required", result.stdout)


if __name__ == "__main__":
    unittest.main()
