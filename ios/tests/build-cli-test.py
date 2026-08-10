#!/usr/bin/env python3
"""Exercise the iOS build CLI on Linux with deterministic Apple-tool shims."""

# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
import os
import stat
import subprocess
import tempfile
from pathlib import Path


IOS_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = IOS_ROOT.parent
BUILD_SCRIPT = IOS_ROOT / "build-ios.sh"


def make_executable(path: Path, body: str) -> None:
    path.write_text("#!/usr/bin/env bash\nset -euo pipefail\n" + body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def run_cli(environment: dict[str, str], *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(BUILD_SCRIPT), *arguments],
        cwd=SOURCE_ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )


def main() -> None:
    build_script_text = BUILD_SCRIPT.read_text(encoding="utf-8")
    assert '"${client_graph_arguments[@]}"' not in build_script_text
    assert '"${configure_arguments[@]}"' in build_script_text
    assert "Keep this array unconditionally non-empty" in build_script_text

    with tempfile.TemporaryDirectory(prefix="overte-ios-cli-") as temporary:
        root = Path(temporary)
        shims = root / "bin"
        shims.mkdir()
        log = root / "tool.log"
        sdk = root / "iPhone.sdk"
        sdk.mkdir()

        make_executable(shims / "uname", 'echo Darwin\n')
        make_executable(
            shims / "xcodebuild",
            'printf "Xcode %s\\nBuild version TEST\\n" "${FAKE_XCODE_VERSION:-26.2}"\n',
        )
        make_executable(
            shims / "xcrun",
            'case "$*" in\n'
            '  *--show-sdk-version*) echo "${FAKE_SDK_VERSION:-26.1}" ;;\n'
            '  *--show-sdk-path*) echo "$FAKE_SDK_PATH" ;;\n'
            '  *) echo "unexpected xcrun invocation: $*" >&2; exit 64 ;;\n'
            'esac\n',
        )
        make_executable(
            shims / "cmake",
            'if [[ "${1:-}" == "--version" ]]; then\n'
            '  echo "cmake version ${FAKE_CMAKE_VERSION:-3.30.1}"\n'
            'else\n'
            '  printf "cmake" >> "$FAKE_TOOL_LOG"\n'
            '  printf " <%s>" "$@" >> "$FAKE_TOOL_LOG"\n'
            '  printf "\\n" >> "$FAKE_TOOL_LOG"\n'
            'fi\n',
        )
        make_executable(
            shims / "conan",
            'if [[ "${1:-}" == "--version" ]]; then\n'
            '  echo "Conan version ${FAKE_CONAN_VERSION:-2.25.2}"\n'
            'else\n'
            '  printf "conan" >> "$FAKE_TOOL_LOG"\n'
            '  printf " <%s>" "$@" >> "$FAKE_TOOL_LOG"\n'
            '  printf " sdk-device=<%s> sdk-simulator=<%s>\\n" '
            '"${OVERTE_IOS_DEVICE_SDK_PATH:-}" "${OVERTE_IOS_SIMULATOR_SDK_PATH:-}" '
            '>> "$FAKE_TOOL_LOG"\n'
            "  echo '{\"graph\":{\"nodes\":{\"0\":{\"ref\":\"overte-ios-dependencies/0.1\","
            "\"context\":\"host\",\"settings\":{\"os\":\"iOS\"},\"options\":{}}}}}'\n"
            'fi\n',
        )
        make_executable(
            shims / "lipo",
            '[[ "${FAKE_LIPO_FAIL:-0}" == "0" ]]\n',
        )

        environment = os.environ.copy()
        environment.update(
            {
                "PATH": f"{shims}{os.pathsep}{environment['PATH']}",
                "FAKE_SDK_PATH": str(sdk),
                "FAKE_TOOL_LOG": str(log),
            }
        )

        qt_root = root / "qt-ios"
        (qt_root / "lib/cmake/Qt6").mkdir(parents=True)
        (qt_root / "lib/cmake/Qt6/Qt6Config.cmake").touch()
        (qt_root / "lib/cmake/Qt6/qt.toolchain.cmake").touch()
        (qt_root / "lib/cmake/Qt6/Qt6ConfigVersionImpl.cmake").write_text(
            'set(PACKAGE_VERSION "6.11.1")\n', encoding="utf-8"
        )
        (qt_root / "bin").mkdir()
        make_executable(
            qt_root / "bin/qt-cmake",
            'printf "qt-cmake" >> "$FAKE_TOOL_LOG"\n'
            'printf " <%s>" "$@" >> "$FAKE_TOOL_LOG"\n'
            'printf "\\n" >> "$FAKE_TOOL_LOG"\n',
        )
        environment["OVERTE_IOS_QT_ROOT"] = str(qt_root)

        moltenvk_root = root / "MoltenVK"
        (moltenvk_root / "MoltenVK/include/vulkan").mkdir(parents=True)
        (moltenvk_root / "MoltenVK/include/vulkan/vulkan.h").touch()
        simulator_slice = moltenvk_root / "MoltenVK/MoltenVK.xcframework/ios-arm64_x86_64-simulator"
        simulator_slice.mkdir(parents=True)
        (simulator_slice / "libMoltenVK.a").touch()
        device_slice = moltenvk_root / "MoltenVK/MoltenVK.xcframework/ios-arm64"
        device_slice.mkdir(parents=True)
        (device_slice / "libMoltenVK.a").touch()
        environment["OVERTE_IOS_MOLTENVK_ROOT"] = str(moltenvk_root)

        v8_root = root / "v8-ios"
        (v8_root / "include/node").mkdir(parents=True)
        (v8_root / "include/node/v8.h").touch()
        (v8_root / "lib").mkdir()
        (v8_root / "lib/libnode.a").touch()
        environment["OVERTE_IOS_V8_ROOT"] = str(v8_root)

        doctor = run_cli(
            environment,
            "doctor",
            "--platform",
            "simulator",
            "--require-qt",
            "--require-v8",
            "--require-moltenvk",
        )
        assert doctor.returncode == 0, doctor.stderr
        assert "iOS build environment is ready" in doctor.stdout
        assert "Python:" in doctor.stdout
        assert "Static non-JIT V8:" in doctor.stdout

        wrong_slice = run_cli(environment | {"FAKE_LIPO_FAIL": "1"}, "doctor", "--require-v8")
        assert wrong_slice.returncode == 1
        assert "does not contain arm64" in wrong_slice.stderr

        outdated_environment = environment | {"FAKE_XCODE_VERSION": "25.4"}
        outdated = run_cli(outdated_environment, "doctor")
        assert outdated.returncode == 1
        assert "Xcode 26 or newer is required" in outdated.stderr

        wrong_conan_environment = environment | {"FAKE_CONAN_VERSION": "2.26.0"}
        wrong_conan = run_cli(wrong_conan_environment, "doctor")
        assert wrong_conan.returncode == 1
        assert "required for the audited graph" in wrong_conan.stderr

        qt_version_file = qt_root / "lib/cmake/Qt6/Qt6ConfigVersionImpl.cmake"
        qt_version_file.write_text('set(PACKAGE_VERSION "6.10.3")\n', encoding="utf-8")
        outdated_qt = run_cli(environment, "doctor", "--require-qt")
        assert outdated_qt.returncode == 1
        assert "Qt 6.11.1 or newer is required" in outdated_qt.stderr
        qt_version_file.write_text('set(PACKAGE_VERSION "6.11.1")\n', encoding="utf-8")

        qt_toolchain_file = qt_root / "lib/cmake/Qt6/qt.toolchain.cmake"
        qt_toolchain_file.unlink()
        missing_qt_toolchain = run_cli(environment, "doctor", "--require-qt")
        assert missing_qt_toolchain.returncode == 1
        assert "Qt6/qt.toolchain.cmake" in missing_qt_toolchain.stderr
        qt_toolchain_file.touch()

        invalid_bundle = run_cli(environment, "doctor", "--bundle-id", "not valid")
        assert invalid_bundle.returncode == 1
        assert "invalid bundle identifier" in invalid_bundle.stderr

        invalid_team = run_cli(environment, "doctor", "--development-team", "short")
        assert invalid_team.returncode == 1
        assert "exactly 10" in invalid_team.stderr

        invalid_configuration = run_cli(environment, "doctor", "--configuration", "../Release")
        assert invalid_configuration.returncode == 1
        assert "invalid Xcode configuration" in invalid_configuration.stderr

        log.write_text("", encoding="utf-8")
        configured = run_cli(
            environment,
            "configure",
            "--platform",
            "device",
            "--development-team",
            "ABCDE12345",
            "--bundle-id",
            "org.overte.interface.devtest",
        )
        assert configured.returncode == 0, configured.stderr
        invocation = log.read_text(encoding="utf-8")
        assert f"<-S> <{SOURCE_ROOT}>" in invocation
        assert "<-DCMAKE_SYSTEM_NAME=iOS>" in invocation
        assert "<-DOVERTE_IOS_BOOTSTRAP_ONLY=ON>" in invocation
        assert "<-DOVERTE_IOS_ENABLE_SIGNING=ON>" in invocation
        assert "<-DOVERTE_IOS_DEVELOPMENT_TEAM=ABCDE12345>" in invocation
        assert "<-DOVERTE_IOS_BUNDLE_IDENTIFIER=org.overte.interface.devtest>" in invocation

        client_build = root / "client-build"
        (client_build / "conan").mkdir(parents=True)
        (client_build / "conan/conan_toolchain.cmake").touch()
        log.write_text("", encoding="utf-8")
        client_graph = run_cli(
            environment,
            "configure",
            "--platform",
            "device",
            "--build-dir",
            str(client_build),
            "--client-graph",
        )
        assert client_graph.returncode == 0, client_graph.stderr
        invocation = log.read_text(encoding="utf-8")
        assert invocation.startswith("qt-cmake "), invocation
        assert "<-DOVERTE_IOS_BOOTSTRAP_ONLY=OFF>" in invocation
        assert f"<-DQT_CHAINLOAD_TOOLCHAIN_FILE={client_build}/conan/conan_toolchain.cmake>" in invocation
        assert "<-DCMAKE_TOOLCHAIN_FILE=" not in invocation
        assert "<-DCMAKE_PREFIX_PATH=" not in invocation
        assert invocation.count("TOOLCHAIN_FILE=") == 1, invocation

        missing_client_toolchain = run_cli(
            environment,
            "configure",
            "--build-dir",
            str(root / "missing-client-build"),
            "--client-graph",
        )
        assert missing_client_toolchain.returncode == 1
        assert "run deps first" in missing_client_toolchain.stderr

        invalid_client_command = run_cli(environment, "build", "--client-graph")
        assert invalid_client_command.returncode == 1
        assert "only valid with the configure command" in invalid_client_command.stderr

        log.write_text("", encoding="utf-8")
        bootstrap_build = run_cli(
            environment,
            "build",
            "--build-dir",
            str(root / "bootstrap-build"),
        )
        assert bootstrap_build.returncode == 0, bootstrap_build.stderr
        invocation = log.read_text(encoding="utf-8")
        assert "<-DOVERTE_IOS_BOOTSTRAP_ONLY=ON>" in invocation
        assert "<--target> <OverteIOSBootstrap>" in invocation

        log.write_text("", encoding="utf-8")
        dependencies = run_cli(
            environment,
            "deps",
            "--platform",
            "simulator",
            "--build-dir",
            str(root / "dependency-build"),
        )
        assert dependencies.returncode == 0, dependencies.stderr
        invocation = log.read_text(encoding="utf-8")
        assert "conan <install>" in invocation
        assert "sdk-simulator=<" + str(sdk) + ">" in invocation
        sbom = json.loads(
            (root / "dependency-build/conan/sbom.cdx.json").read_text(encoding="utf-8")
        )
        assert sbom["bomFormat"] == "CycloneDX"

        clean_target = SOURCE_ROOT / "build-ios/custom-host-contract"
        clean_target.mkdir(parents=True, exist_ok=True)
        preview = run_cli(
            environment, "clean", "--build-dir", "build-ios/custom-host-contract"
        )
        assert preview.returncode == 0 and clean_target.exists()
        assert "Run again with --confirm" in preview.stdout
        removal = run_cli(
            environment,
            "clean",
            "--build-dir",
            "build-ios/custom-host-contract",
            "--confirm",
        )
        assert removal.returncode == 0 and not clean_target.exists()

    print("PASS iOS build CLI shim tests")


if __name__ == "__main__":
    main()
