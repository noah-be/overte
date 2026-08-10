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


def fake_qt(
    root: pathlib.Path,
    version: str,
    target: bool,
    source_host_layout: bool = False,
) -> None:
    cmake_dir = root / "lib/cmake/Qt6"
    cmake_dir.mkdir(parents=True)
    (cmake_dir / "Qt6ConfigVersion.cmake").write_text(
        'include("${CMAKE_CURRENT_LIST_DIR}/Qt6ConfigVersionImpl.cmake")\n',
        encoding="utf-8",
    )
    (cmake_dir / "Qt6ConfigVersionImpl.cmake").write_text(
        f'set(PACKAGE_VERSION "{version}")\n', encoding="utf-8",
    )
    if target:
        executable(root / "bin/qt-cmake")
        (root / "lib/cmake/Qt6/qt.toolchain.cmake").touch()
        ios_spec = root / "mkspecs/macx-ios-clang/qmake.conf"
        ios_spec.parent.mkdir(parents=True)
        ios_spec.touch()
        ios_plugin = root / "lib/cmake/Qt6Gui/Qt6QIOSIntegrationPluginConfig.cmake"
        ios_plugin.parent.mkdir(parents=True)
        ios_plugin.touch()
        for module in (
            "Core", "Gui", "Network", "Qml", "Quick", "Multimedia", "Svg",
            "WebChannel", "WebSockets", "WebView", "Core5Compat", "ShaderTools",
        ):
            config = root / f"lib/cmake/Qt6{module}/Qt6{module}Config.cmake"
            config.parent.mkdir(parents=True, exist_ok=True)
            config.touch()
    else:
        for tool in ("moc", "rcc", "qmlcachegen", "qsb"):
            tool_dir = "libexec" if source_host_layout and tool != "qsb" else "bin"
            executable(root / tool_dir / tool)


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

    def test_validates_source_built_qt6_host_tool_layout(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = pathlib.Path(directory)
            target, host = base / "ios", base / "macos"
            fake_qt(target, "6.11.1", target=True)
            fake_qt(host, "6.11.1", target=False, source_host_layout=True)
            result = self.run_script("validate", str(target), str(host))
            self.assertEqual(result.returncode, 0, result.stderr)

            host_result = self.run_script("validate-host", str(host))
            self.assertEqual(host_result.returncode, 0, host_result.stderr)
            self.assertIn("host tools validated", host_result.stdout)

            target_result = self.run_script("validate-target", str(target))
            self.assertEqual(target_result.returncode, 0, target_result.stderr)
            self.assertIn("iOS target validated", target_result.stdout)

    def test_rejects_missing_host_tool_from_bin_and_libexec(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = pathlib.Path(directory)
            target, host = base / "ios", base / "macos"
            fake_qt(target, "6.11.1", target=True)
            fake_qt(host, "6.11.1", target=False, source_host_layout=True)
            (host / "libexec/moc").unlink()
            result = self.run_script("validate", str(target), str(host))
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("moc", result.stderr)
            self.assertIn("bin", result.stderr)
            self.assertIn("libexec", result.stderr)

    def test_rejects_non_ios_target_tree(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = pathlib.Path(directory) / "target"
            fake_qt(target, "6.11.1", target=True)
            (target / "mkspecs/macx-ios-clang/qmake.conf").unlink()
            result = self.run_script("validate-target", str(target))
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("macx-ios-clang", result.stderr)

    def test_rejects_mismatched_host(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = pathlib.Path(directory)
            target, host = base / "ios", base / "macos"
            fake_qt(target, "6.11.1", target=True)
            fake_qt(host, "6.11.0", target=False)
            result = self.run_script("validate", str(target), str(host))
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("exactly 6.11.1 is required", result.stderr)

    def test_accepts_legacy_direct_config_version(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = pathlib.Path(directory)
            target, host = base / "ios", base / "macos"
            fake_qt(target, "6.11.1", target=True)
            fake_qt(host, "6.11.1", target=False)
            for root in (target, host):
                (root / "lib/cmake/Qt6/Qt6ConfigVersionImpl.cmake").unlink()
                (root / "lib/cmake/Qt6/Qt6ConfigVersion.cmake").write_text(
                    'set(PACKAGE_VERSION "6.11.1")\n', encoding="utf-8",
                )
            result = self.run_script("validate", str(target), str(host))
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_rejects_conflicting_version_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = pathlib.Path(directory)
            target, host = base / "ios", base / "macos"
            fake_qt(target, "6.11.1", target=True)
            fake_qt(host, "6.11.1", target=False)
            (target / "lib/cmake/Qt6/Qt6ConfigVersion.cmake").write_text(
                'set(PACKAGE_VERSION "6.11.0")\n', encoding="utf-8",
            )
            result = self.run_script("validate", str(target), str(host))
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("conflicting Qt versions", result.stderr)

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
