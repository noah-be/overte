#!/usr/bin/env python3

import json
import os
from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[2]
WATCHDOG = ROOT / "ios" / "ci" / "compiler-watchdog.py"


class CompilerWatchdogTest(unittest.TestCase):
    def invoke(self, code: str, timeout: float = 2.0) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["OVERTE_COMPILER_WATCHDOG_DISABLE_SCCACHE"] = "1"
        return subprocess.run(
            [sys.executable, str(WATCHDOG), "--interval", "0.05",
             "--inactivity-timeout", str(timeout), "--term-grace", "0.1", "--",
             sys.executable, "-c", code, "secret-source-name.cpp"],
            text=True, capture_output=True, env=env, timeout=5, check=False,
        )

    def test_preserves_compiler_exit_and_sanitizes_output(self) -> None:
        result = self.invoke("import sys; sys.exit(23)")
        self.assertEqual(result.returncode, 23, result.stdout + result.stderr)
        self.assertNotIn("secret-source-name", result.stdout)
        records = [json.loads(line) for line in result.stdout.splitlines()]
        self.assertEqual(records[0]["compiler_watchdog"], "start")
        self.assertEqual(records[-1]["exit_code"], 23)

    def test_reports_each_active_invocation(self) -> None:
        result = self.invoke("import time; end=time.time()+.25\nwhile time.time()<end: pass")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        records = [json.loads(line) for line in result.stdout.splitlines()]
        self.assertTrue(any(row["compiler_watchdog"] == "progress" for row in records))
        self.assertEqual(records[-1]["compiler_watchdog"], "end")

    def test_terminates_inactive_invocation(self) -> None:
        result = self.invoke("import time; time.sleep(3)", timeout=0.2)
        self.assertEqual(result.returncode, 124, result.stdout + result.stderr)
        self.assertIn('"compiler_watchdog":"stalled"', result.stdout)

    def test_correlates_daemon_owned_clang_by_source_and_output(self) -> None:
        namespace: dict[str, object] = {}
        exec(WATCHDOG.read_text(encoding="utf-8").replace(
            'if __name__ == "__main__":', 'if False:'), namespace)
        rows = [{"pid": 77, "ppid": 1, "cpu": 4.0, "rss": 12,
                 "comm": "clang++", "command": "clang++ /secret/unit.cpp -o /secret/unit.o"}]
        matches = namespace["_correlated_compilers"](rows, "/secret/unit.cpp", "/secret/unit.o")
        self.assertEqual([row["pid"] for row in matches], [77])


if __name__ == "__main__":
    unittest.main()
