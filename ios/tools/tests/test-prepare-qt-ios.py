#!/usr/bin/env python3
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

import pathlib
import stat
import subprocess
import tempfile
import unittest


REPO = pathlib.Path(__file__).resolve().parents[3]
SCRIPT = REPO / "ios" / "tools" / "prepare-qt-ios.sh"


def executable(path: pathlib.Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def fake_qt(root: pathlib.Path, version: str, target: bool) -> None:
    version_file = root / "lib/cmake/Qt6/Qt6ConfigVersion.cmake"
    version_file.parent.mkdir(parents=True)
    version_file.write_text(f'set(PACKAGE_VERSION "{version}")\n', encoding="utf-8")
    if target:
        executable(root / "bin/qt-cmake")
        (root / "lib/cmake/Qt6/qt.toolchain.cmake").touch()
        for module in (
            "Core", "Gui", "Network", "Qml", "Quick", "Multimedia", "Svg",
            "WebChannel", "WebSockets", "WebView", "Core5Compat", "ShaderTools",
        ):
            config = root / f"lib/cmake/Qt6{module}/Qt6{module}Config.cmake"
            config.parent.mkdir(parents=True)
            config.touch()
    else:
        for tool in ("moc", "rcc", "qmlcachegen", "qsb"):
            executable(root / f"bin/{tool}")


class QtToolchainPreparationTest(unittest.TestCase):
    def run_script(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(SCRIPT), *args], cwd=REPO, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
        )

    def test_manifest_uses_source_for_ios(self) -> None:
        result = self.run_script("manifest")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("QT_HOST_PACKAGE=qt.qt6.6111.clang_64", result.stdout)
        self.assertIn("QT_IOS_DISTRIBUTION=source-or-entitled-cache", result.stdout)
        self.assertNotIn("QT_IOS_PACKAGE=", result.stdout)
        self.assertIn("qt-everywhere-src-6.11.1.tar.xz", result.stdout)

    def test_validates_matching_host_and_target(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = pathlib.Path(directory)
            target, host = base / "ios", base / "macos"
            fake_qt(target, "6.11.1", target=True)
            fake_qt(host, "6.11.1", target=False)
            result = self.run_script("validate", str(target), str(host))
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_rejects_mismatched_host(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = pathlib.Path(directory)
            target, host = base / "ios", base / "macos"
            fake_qt(target, "6.11.1", target=True)
            fake_qt(host, "6.11.0", target=False)
            result = self.run_script("validate", str(target), str(host))
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("exactly 6.11.1 is required", result.stderr)

    def test_installer_command_only_requests_verified_host_package(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            installer = pathlib.Path(directory) / "installer"
            executable(installer)
            result = self.run_script("installer-command", str(installer), str(pathlib.Path(directory) / "Qt"))
            command = result.stdout.splitlines()[0]
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("qt.qt6.6111.clang_64", command)
            self.assertNotIn(".ios", command)
            self.assertNotIn("--accept-licenses", command)


if __name__ == "__main__":
    unittest.main()
