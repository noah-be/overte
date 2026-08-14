#!/usr/bin/env python3
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

import pathlib
import subprocess
import tempfile
import unittest


REPO = pathlib.Path(__file__).resolve().parents[3]
SCRIPT = REPO / "ios" / "tools" / "build-qt-ios-from-source.sh"


class QtSourceBuildTest(unittest.TestCase):
    def run_script(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(SCRIPT), *args], cwd=REPO, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
        )

    def test_plan_is_pinned_and_minimal(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            result = self.run_script(
                "--work-root", str(root / "work"),
                "--install-root", str(root / "qt"), "--print-plan",
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("QT_VERSION=6.11.1", result.stdout)
        self.assertIn(
            "MODULES=qtbase,qtdeclarative,qtmultimedia,qtsvg,qtwebchannel,"
            "qtwebsockets,qtwebview,qt5compat,qtshadertools",
            result.stdout,
        )
        self.assertIn("QT_SOURCE_SHA256=252acef8", result.stdout)
        self.assertIn("IOS_PLAN_ID=", result.stdout)
        self.assertIn("TARGET_SDK=iphoneos", result.stdout)
        self.assertIn("skip-qtwebengine", result.stdout)
        self.assertNotIn("accept-license", result.stdout.lower())

    def test_all_resumable_stages_share_the_same_plan(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            for stage in ("source", "host", "ios", "all"):
                result = self.run_script(
                    "--work-root", str(root / "work"),
                    "--install-root", str(root / "qt"),
                    "--stage", stage,
                    "--print-plan",
                )
                self.assertEqual(result.returncode, 0, (stage, result.stderr))
                self.assertIn("PLAN_ID=", result.stdout)

    def test_rejects_unknown_stage(self) -> None:
        result = self.run_script(
            "--work-root", "/tmp/work", "--install-root", "/tmp/qt",
            "--stage", "partial", "--print-plan",
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("--stage must be", result.stderr)

    def test_rejects_relative_or_shared_roots(self) -> None:
        relative = self.run_script("--work-root", "work", "--install-root", "/tmp/qt", "--print-plan")
        self.assertNotEqual(relative.returncode, 0)
        self.assertIn("absolute path", relative.stderr)
        same = self.run_script("--work-root", "/tmp/qt", "--install-root", "/tmp/qt", "--print-plan")
        self.assertNotEqual(same.returncode, 0)
        self.assertIn("must differ", same.stderr)

    def test_rejects_unknown_options(self) -> None:
        result = self.run_script("--work-root", "/tmp/work", "--install-root", "/tmp/qt", "--yes")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unknown argument", result.stderr)

    def test_target_build_requires_an_explicit_supported_sdk(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertEqual(source.count('-platform macx-ios-clang -sdk "$target_sdk"'), 2)
        self.assertEqual(source.count("-skip qtwebengine -platform macx-ios-clang"), 2)
        self.assertIn("iphoneos|iphonesimulator", source)
        self.assertIn(".overte-qt-host-plan-id", source)
        self.assertIn(".overte-qt-ios-plan-id", source)

        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            simulator = self.run_script(
                "--work-root", str(root / "work"),
                "--install-root", str(root / "qt"),
                "--target-sdk", "iphonesimulator",
                "--print-plan",
            )
        self.assertEqual(simulator.returncode, 0, simulator.stderr)
        self.assertIn("TARGET_SDK=iphonesimulator", simulator.stdout)
        self.assertIn("IOS_PLAN_ID=", simulator.stdout)
        self.assertIn("-iphonesimulator", simulator.stdout)

        invalid = self.run_script(
            "--work-root", "/tmp/work", "--install-root", "/tmp/qt",
            "--target-sdk", "auto", "--print-plan",
        )
        self.assertNotEqual(invalid.returncode, 0)
        self.assertIn("--target-sdk must be", invalid.stderr)

    def test_every_compiler_language_uses_the_per_file_watchdog(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("ios/ci/compiler-watchdog.py", source)
        for language in ("C", "CXX", "OBJC", "OBJCXX"):
            self.assertEqual(source.count(f"CMAKE_{language}_COMPILER_LAUNCHER=$compiler_watchdog;--"), 2)
        self.assertIn("OVERTE_COMPILER_WATCHDOG_LOG", source)
        self.assertIn('tail -n 0 -F "$live_log"', source)
        self.assertIn('ios/ci/build-heartbeat.py', source)
        self.assertIn('--root-pid "$build_pid"', source)
        self.assertEqual(source.count('build_with_live_compiler_tracking "$'), 2)


if __name__ == "__main__":
    unittest.main()
