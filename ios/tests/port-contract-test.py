#!/usr/bin/env python3
"""Device-free contract tests for the Overte iOS bootstrap boundary."""

# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import importlib.util
import json
import plistlib
import re
import subprocess
import sys
from pathlib import Path


IOS_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = IOS_ROOT.parent


def require_text(path: Path, pattern: str, message: str) -> None:
    text = path.read_text(encoding="utf-8")
    if re.search(pattern, text, re.MULTILINE) is None:
        raise AssertionError(f"{message}: {path}")


def parse_versions() -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in (IOS_ROOT / "versions.env").read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        assert separator and re.fullmatch(r"[A-Z][A-Z0-9_]+", key), raw_line
        assert re.fullmatch(r"[0-9]+(?:\.[0-9]+)*", value), raw_line
        values[key] = value
    return values


def load_python_module(path: Path, name: str):
    specification = importlib.util.spec_from_file_location(name, path)
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def test_versions() -> None:
    versions = parse_versions()
    assert versions["OVERTE_IOS_MIN_VERSION"] == "17.0"
    assert int(versions["OVERTE_IOS_REQUIRED_SDK_MAJOR"]) >= 26
    assert int(versions["OVERTE_IOS_REQUIRED_XCODE_MAJOR"]) >= 26
    assert tuple(map(int, versions["OVERTE_IOS_QT_MIN_VERSION"].split("."))) >= (6, 11, 0)
    assert versions["OVERTE_IOS_CONAN_VERSION"] == "2.25.2"
    assert tuple(map(int, versions["OVERTE_IOS_PYTHON_MIN_VERSION"].split("."))) >= (3, 11, 0)

    comparator = IOS_ROOT / "tools" / "version-at-least.py"
    cases = (
        ("26", "26.0", True),
        ("26.0.1", "26", True),
        ("25.9", "26", False),
        ("3.24.0", "3.24", True),
        ("3.23.99", "3.24.0", False),
    )
    for actual, required, expected in cases:
        result = subprocess.run(
            [sys.executable, str(comparator), actual, required],
            check=False,
            capture_output=True,
            text=True,
        )
        assert (result.returncode == 0) is expected, (actual, required, result)
    invalid = subprocess.run(
        [sys.executable, str(comparator), "26-beta", "26"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert invalid.returncode == 2 and "invalid numeric version" in invalid.stderr


def test_profiles() -> None:
    expected = {
        "ios-arm64": "iphoneos",
        "ios-simulator-arm64": "iphonesimulator",
    }
    for profile_name, sdk in expected.items():
        profile = IOS_ROOT / "conan" / "profiles" / profile_name
        require_text(profile, r"^os=iOS$", "profile must target iOS")
        require_text(profile, rf"^os\.sdk={sdk}$", "profile has the wrong SDK")
        require_text(profile, r"^arch=armv8$", "profile must target arm64")
        require_text(profile, r"^\*:shared=False$", "iOS dependencies must default to static")
        require_text(profile, r"^tools\.cmake\.cmaketoolchain:generator=Ninja$", "single-architecture dependency builds must avoid Xcode app-bundle validation")
        require_text(profile, r'^tools\.build:cflags=\["-falign-functions=32", "-fPIC"\]$', "Conan must propagate aligned C flags into the chainloaded toolchain")
        require_text(profile, r'^tools\.build:cxxflags=\["-falign-functions=32", "-fPIC"\]$', "Conan must propagate aligned C++ flags into the chainloaded toolchain")
        assert "tools.cmake.cmaketoolchain:generator=Xcode" not in profile.read_text(encoding="utf-8"), \
            "dependency profiles must not turn upstream command-line tools into iOS app bundles"

    macos_build_profile = IOS_ROOT / "conan" / "profiles" / "macos-arm64"
    require_text(macos_build_profile, r"^os=Macos$", "Conan build tools must target the native macOS runner")
    require_text(macos_build_profile, r"^arch=armv8$", "Conan build tools must target the arm64 runner")
    require_text(macos_build_profile, r"^compiler=apple-clang$", "Conan build tools must use Apple Clang")
    require_text(macos_build_profile, r"^compiler\.version=17$", "Conan build profile must match Xcode 26 Apple Clang")
    require_text(macos_build_profile, r"^compiler\.libcxx=libc\+\+$", "Conan build tools must use libc++")
    require_text(macos_build_profile, r"^build_type=Release$", "Conan build tools must be release binaries")

    build_cli = IOS_ROOT / "build-ios.sh"
    require_text(build_cli, r"-G Xcode", "the final Overte application must retain the Xcode generator")
    require_text(build_cli, r'--profile:build="\$script_dir/conan/profiles/macos-arm64"', "dependency resolution must use the audited native build profile")
    require_text(build_cli, r'readonly overte_conan_remote_url="https://artifactory\.overte\.org/artifactory/api/conan/overte"', "custom recipes must come from the canonical Overte Conan remote")
    require_text(build_cli, r"conan remote (?:add|update) overte", "dependency resolution must configure the Overte Conan remote")
    assert "--profile:build=default" not in build_cli.read_text(encoding="utf-8"), \
        "dependency resolution must not rely on a mutable Conan default profile"

    recipe = IOS_ROOT / "conanfile.py"
    require_text(recipe, r'package_type = "application"', "staged graph must not publish a library")
    require_text(recipe, r'str\(self\.settings\.os\) != "iOS"', "staged graph must reject non-iOS hosts")
    for forbidden in ("steamworks", "discord-rpc", "openvr", "openxr", "sdl"):
        if re.search(rf'self\.requires\("{re.escape(forbidden)}/', recipe.read_text(encoding="utf-8")):
            raise AssertionError(f"desktop-only dependency entered iOS graph: {forbidden}")
    recipe_text = recipe.read_text(encoding="utf-8")
    if re.search(r'self\.requires\("quazip/', recipe_text):
        raise AssertionError("legacy QuaZIP must remain behind the Qt 6 iOS integration gate")
    require_text(recipe, r'self\.requires\("openssl/3\.5\.7"', "staged TLS must not use OpenSSL 1.1")
    require_text(recipe, r'self\.tool_requires\("scribe/', "shader generator must run in the build context")
    require_text(recipe, r'self\.tool_requires\("spirv-cross/', "SPIR-V conversion must run in the build context")
    build_script = IOS_ROOT / "build-ios.sh"
    require_text(build_script, r"audit-conan-graph\.py", "resolved Conan graphs must be audited")
    require_text(build_script, r"generate-sbom\.py", "resolved Conan graphs must emit an SBOM")
    require_text(build_script, r'\$build_dir/ios/\$configuration-iphone', "package must use the subdirectory target output")
    require_text(build_script, r"OVERTE_IOS_SDK_NAME", "configure must pass the selected SDK to Metal compilation")
    require_text(build_script, r"Payload/OverteIOSBootstrap\.app", "device packaging must use the standard IPA payload layout")
    require_text(build_script, r"artifact_prefix", "artifact filenames must start with a build number")
    require_text(build_script, r"device-\$\{signing_label\}\.ipa", "device IPA names must disclose signing state")
    require_text(build_script, r'"buildNumber": int\(build_number\)', "artifact manifests must record the build number")
    require_text(build_script, r'"requiresSigning": not is_signed', "device manifests must disclose the signing requirement")
    require_text(build_script, r"package-client\)", "integrated client packaging must be an explicit command")
    require_text(build_script, r"embedded\.mobileprovision", "signed client packaging must audit its provisioning profile")
    require_text(build_script, r"application-identifier mismatch", "signed client packaging must bind the team and bundle ID")
    require_text(build_script, r"get-task-allow differs", "signed client packaging must compare debug entitlement state")
    require_text(build_script, r"unexpectedly contains _CodeSignature", "unsigned Sideloadly input must reject stale signatures")
    handoff = IOS_ROOT / "tools" / "verify-windows-handoff.py"
    require_text(handoff, r"LATEST-OverteIOSClient\.json", "handoff verifier must resolve the current JSON pointer")
    require_text(handoff, r"hashlib\.sha256", "handoff verifier must recompute SHA-256")
    require_text(handoff, r"Sideloadly must sign", "handoff verifier must explain unsigned device artifacts")
    require_text(build_script, r"positive OVERTE_IOS_ARTIFACT_SEQUENCE", "integrated artifacts must reject missing or zero numbering")
    require_text(build_script, r"LATEST-OverteIOSClient\.json", "integrated artifacts need machine-readable VM handoff metadata")
    require_text(build_script, r"sharedFolderRelativePath", "integrated manifests must name the Windows shared-folder payload")


def test_dependency_inventory() -> None:
    inventory_path = IOS_ROOT / "dependencies.json"
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    assert inventory["schemaVersion"] == 1
    dependencies = inventory["dependencies"]

    root_recipe = (SOURCE_ROOT / "conanfile.py").read_text(encoding="utf-8")
    recipe_dependencies = set(re.findall(r'self\.requires\("([^/\[]+)', root_recipe))
    missing = sorted(recipe_dependencies - dependencies.keys())
    assert not missing, f"root Conan dependencies lack an iOS classification: {missing}"

    for name, policy in dependencies.items():
        assert policy["class"] in {
            "required",
            "required-audit",
            "disabled",
            "deferred",
            "host-tool",
            "graphics-toolchain",
            "graphics-runtime",
            "non-jit-port",
            "replace-with-qt6-ios",
        }, name
        if policy["class"] in {"disabled", "host-tool", "deferred", "graphics-toolchain"}:
            assert policy["ship"] is False, name


def test_plists() -> None:
    info_path = IOS_ROOT / "resources" / "Info.plist.in"
    with info_path.open("rb") as stream:
        info = plistlib.load(stream)
    assert info["LSRequiresIPhoneOS"] is True
    assert info["NSMicrophoneUsageDescription"]
    assert info["NSLocalNetworkUsageDescription"]
    assert "NSBonjourServices" not in info, "direct domain UDP must not declare unused Bonjour services"
    assert info["NSAppTransportSecurity"] == {"NSAllowsLocalNetworking": True}
    assert info["UIApplicationSceneManifest"]["UIApplicationSupportsMultipleScenes"] is False
    assert info["UIRequiredDeviceCapabilities"] == ["arm64"]
    url_schemes = info["CFBundleURLTypes"][0]["CFBundleURLSchemes"]
    assert set(url_schemes) == {"overte", "hifi"}
    assert set(info["UISupportedInterfaceOrientations~ipad"]) >= {
        "UIInterfaceOrientationPortrait",
        "UIInterfaceOrientationLandscapeLeft",
        "UIInterfaceOrientationLandscapeRight",
    }

    interface_info_path = IOS_ROOT / "resources" / "InterfaceInfo.plist.in"
    with interface_info_path.open("rb") as stream:
        interface_info = plistlib.load(stream)
    assert interface_info["NSAppTransportSecurity"] == {"NSAllowsLocalNetworking": True}
    assert "NSAllowsArbitraryLoads" not in interface_info["NSAppTransportSecurity"]
    assert "NSExceptionDomains" not in interface_info["NSAppTransportSecurity"]
    interface_schemes = interface_info["CFBundleURLTypes"][0]["CFBundleURLSchemes"]
    assert set(interface_schemes) == {"hifi", "hifiapp"}
    assert "NSBonjourServices" not in interface_info
    assert interface_info["UILaunchScreen"] == {"UIColorName": "AccentColor"}
    assert interface_info["UIRequiresFullScreen"] is False
    assert interface_info["UIRequiredDeviceCapabilities"] == ["arm64"]
    assert set(interface_info["UISupportedInterfaceOrientations~ipad"]) == {
        "UIInterfaceOrientationPortrait",
        "UIInterfaceOrientationPortraitUpsideDown",
        "UIInterfaceOrientationLandscapeLeft",
        "UIInterfaceOrientationLandscapeRight",
    }

    privacy_path = IOS_ROOT / "resources" / "PrivacyInfo.xcprivacy"
    with privacy_path.open("rb") as stream:
        privacy = plistlib.load(stream)
    assert privacy["NSPrivacyTracking"] is False
    assert privacy["NSPrivacyTrackingDomains"] == []
    accessed = {
        entry["NSPrivacyAccessedAPIType"]: entry["NSPrivacyAccessedAPITypeReasons"]
        for entry in privacy["NSPrivacyAccessedAPITypes"]
    }
    assert accessed == {
        "NSPrivacyAccessedAPICategoryFileTimestamp": ["C617.1"],
        "NSPrivacyAccessedAPICategorySystemBootTime": ["35F9.1"],
        "NSPrivacyAccessedAPICategoryDiskSpace": ["E174.1"],
        "NSPrivacyAccessedAPICategoryUserDefaults": ["CA92.1"],
    }
    evidence = {
        "NSPrivacyAccessedAPICategoryFileTimestamp": (
            SOURCE_ROOT / "libraries/networking/src/FileResourceRequest.cpp",
            r"QFileInfo\(file\)\.lastModified\(\)",
        ),
        "NSPrivacyAccessedAPICategorySystemBootTime": (
            SOURCE_ROOT / "interface/src/main.cpp",
            r"QElapsedTimer\s+startupTime",
        ),
        "NSPrivacyAccessedAPICategoryDiskSpace": (
            SOURCE_ROOT / "libraries/shared/src/shared/FileCache.cpp",
            r"QStorageInfo\(_dirpath\.c_str\(\)\)\.bytesFree\(\)",
        ),
        "NSPrivacyAccessedAPICategoryUserDefaults": (
            SOURCE_ROOT / "libraries/shared/src/SettingManager.cpp",
            r"QSettings\s+settings",
        ),
    }
    assert set(evidence) == set(accessed), "every declared category needs source evidence"
    for category, (path, pattern) in evidence.items():
        require_text(path, pattern, f"missing required-reason API evidence for {category}")

    entitlements_path = IOS_ROOT / "resources" / "Overte.entitlements"
    with entitlements_path.open("rb") as stream:
        entitlements = plistlib.load(stream)
    assert entitlements == {}, "bootstrap must not request undeclared capabilities"


def test_assets() -> None:
    assets = IOS_ROOT / "resources" / "Assets.xcassets"
    for relative in (
        "Contents.json",
        "AppIcon.appiconset/Contents.json",
        "AccentColor.colorset/Contents.json",
    ):
        with (assets / relative).open(encoding="utf-8") as stream:
            payload = json.load(stream)
        assert payload["info"]["version"] == 1

    app_icon = assets / "AppIcon.appiconset" / "AppIcon-1024.png"
    assert app_icon.is_file() and app_icon.stat().st_size > 10_000
    icon_payload = json.loads((assets / "AppIcon.appiconset/Contents.json").read_text(encoding="utf-8"))
    assert icon_payload["images"][0]["filename"] == app_icon.name


def test_cmake_boundary() -> None:
    root_cmake = SOURCE_ROOT / "CMakeLists.txt"
    for mobile_option in ("SERVER", "TOOLS", "INSTALLER"):
        require_text(
            root_cmake,
            rf'set\(OVERTE_BUILD_{mobile_option} OFF CACHE BOOL "Overwritten \(mobile build\)" FORCE\)',
            f"mobile {mobile_option.lower()} option must be a real forced OFF cache boolean",
        )
    autoscribe = SOURCE_ROOT / "cmake/macros/AutoScribeShader.cmake"
    require_text(autoscribe, r"if \(IOS\)[\s\S]*shadergen\.stamp", "iOS shader generation must avoid Xcode ARG_MAX via one stamp output")
    require_text(autoscribe, r"AUTOSCRIBE_SHADERGEN_DEPENDS[\s\S]*AUTOSCRIBE_SHADERGEN_COMMANDS_FILE", "iOS shader generation must retain its authoritative command manifest")
    debug_draw = SOURCE_ROOT / "libraries/shared/src/DebugDraw.h"
    require_text(debug_draw, r'#include "RegisteredMetaTypes\.h"', "Qt 6 moc must see GLM metatype declarations before invokable arguments")
    registered_metatypes = SOURCE_ROOT / "libraries/shared/src/RegisteredMetaTypes.h"
    require_text(registered_metatypes, r"#include <QtCore/QVariant>", "registered inline metatype helpers must have a complete QVariant type")
    shared_util = SOURCE_ROOT / "libraries/shared/src/SharedUtil.h"
    require_text(shared_util, r"#include <QtCore/QVariant>", "global-instance templates must have a complete QVariant type")
    shared_util_impl = SOURCE_ROOT / "libraries/shared/src/SharedUtil.cpp"
    require_text(shared_util_impl, r"QChar::fromLatin1\(static_cast<char>\(byte\)\)", "byte diagnostics must explicitly preserve their Latin-1 character")
    require_text(shared_util_impl, r"QDateTime::fromSecsSinceEpoch\(static_cast<qint64>\(rest\)\)", "multi-day elapsed formatting must preserve sub-day truncation with the Qt 6 epoch API")
    require_text(shared_util_impl, r"QDateTime::fromSecsSinceEpoch\(static_cast<qint64>\(seconds\)\)", "elapsed formatting must preserve second truncation with the Qt 6 epoch API")
    assert "QDateTime::fromTime_t" not in shared_util_impl.read_text(encoding="utf-8"), "Qt 6 removed QDateTime::fromTime_t"
    trace = SOURCE_ROOT / "libraries/shared/src/Trace.cpp"
    require_text(trace, r'"ph", QString\(QChar::fromLatin1\(static_cast<char>\(type\)\)\)', "trace event phases must explicitly preserve their one-byte JSON representation")
    setting_helpers = SOURCE_ROOT / "libraries/shared/src/SettingHelpers.cpp"
    require_text(setting_helpers, r"#include <QIODevice>", "settings serializers must include the complete device type they access")
    sampler = SOURCE_ROOT / "libraries/shared/src/Sampler.cpp"
    sampler_text = sampler.read_text(encoding="utf-8")
    assert sampler_text.count("result += QString::number(") == 13, "sampler diagnostics must explicitly format all numeric fields"
    for data_location_source in (
        SOURCE_ROOT / "libraries/shared/src/RunningMarker.cpp",
        SOURCE_ROOT / "libraries/shared/src/shared/FileUtils.cpp",
        SOURCE_ROOT / "libraries/networking/src/AssetClient.cpp",
        SOURCE_ROOT / "interface/src/AvatarBookmarks.cpp",
        SOURCE_ROOT / "interface/src/LocationBookmarks.cpp",
        SOURCE_ROOT / "interface/src/ui/JSConsole.cpp",
    ):
        data_location_text = data_location_source.read_text(encoding="utf-8")
        assert "QStandardPaths::DataLocation" not in data_location_text, f"Qt 6 removed DataLocation: {data_location_source}"
        assert "QStandardPaths::AppLocalDataLocation" in data_location_text, f"local app-data semantics must be preserved: {data_location_source}"
    file_utils = SOURCE_ROOT / "libraries/shared/src/shared/FileUtils.cpp"
    require_text(file_utils, r"#include <QtCore/QStandardPaths>", "file path helpers must include the Qt type they use")
    require_text(file_utils, r"defined\(Q_OS_MAC\) && !defined\(Q_OS_IOS\)[\s\S]*QProcess::startDetached\(\"osascript\"", "desktop Finder process launching must remain unreachable on iOS")
    for native_widget in (
        SOURCE_ROOT / "libraries/gl/src/gl/GLWidget.h",
        SOURCE_ROOT / "libraries/gl/src/gl/GLWidget.cpp",
        SOURCE_ROOT / "libraries/vk/src/vk/VKWidget.h",
        SOURCE_ROOT / "libraries/vk/src/vk/VKWidget.cpp",
    ):
        require_text(native_widget, r"QT_VERSION >= QT_VERSION_CHECK\(6, 0, 0\)[\s\S]*qintptr \*result[\s\S]*long \*result", "native widget event results must use the Qt 6 pointer-sized signature with a Qt 5 fallback")
    context_wrapper = SOURCE_ROOT / "libraries/gl/src/gl/QOpenGLContextWrapper.cpp"
    require_text(context_wrapper, r"defined\(Q_OS_IOS\)[\s\S]*return result;[\s\S]*#else[\s\S]*_context->nativeHandle\(\)", "Qt 6 iOS must not compile the removed desktop nativeHandle API")
    gl_config = SOURCE_ROOT / "libraries/gl/src/gl/Config.h"
    require_text(gl_config, r"defined\(Q_OS_IOS\)[\s\S]*#include <QtGui/QOpenGLContext>[\s\S]*#include <glad/glad\.h>", "Apple OpenGLES declarations must precede glad function-name macros on iOS")
    gl_cmake = SOURCE_ROOT / "libraries/gl/CMakeLists.txt"
    require_text(gl_cmake, r"OVERTE_QT_MAJOR EQUAL 6[\s\S]*setup_hifi_library\(Gui Widgets OpenGL\)[\s\S]*else\(\)[\s\S]*setup_hifi_library\(Gui Widgets\)", "Qt 6 GL diagnostics must link the QtOpenGL module without changing Qt 5")
    for gl_debug_source in (
        SOURCE_ROOT / "libraries/gl/src/gl/OffscreenGLCanvas.cpp",
        SOURCE_ROOT / "libraries/gl/src/gl/GLHelpers.cpp",
        SOURCE_ROOT / "libraries/gl/src/gl/ContextQt.cpp",
    ):
        require_text(gl_debug_source, r"QT_VERSION >= QT_VERSION_CHECK\(6, 0, 0\)[\s\S]*QtOpenGL/QOpenGLDebug", "Qt 6 GL diagnostics must use their QtOpenGL headers")
    gl_helpers = SOURCE_ROOT / "libraries/gl/src/gl/GLHelpers.cpp"
    require_text(gl_helpers, r"bool khrDebugEnabled\(\) \{[\s\S]*Q_OS_IOS[\s\S]*return false;[\s\S]*glPushDebugGroupKHR", "iOS GLES compatibility must not compile unavailable KHR desktop debug markers")
    require_text(gl_helpers, r"bool extDebugMarkerEnabled\(\) \{[\s\S]*Q_OS_IOS[\s\S]*return false;[\s\S]*glPushGroupMarkerEXT", "iOS GLES compatibility must not compile unavailable EXT desktop debug markers")
    ios_platform = SOURCE_ROOT / "libraries/platform/src/platform/backend/IOSPlatform.cpp"
    require_text(ios_platform, r"#include <QtCore/QString>", "iOS platform inventory must include the complete QString return type used from QSysInfo")
    socket_type = SOURCE_ROOT / "libraries/networking/src/SocketType.h"
    require_text(socket_type, r"#include <cstdint>[\s\S]*#include <QtCore/QDebug>[\s\S]*#include <QtCore/QString>", "SocketType inline formatting must include its complete standard and Qt value types")
    sandbox_utils = SOURCE_ROOT / "libraries/networking/src/SandboxUtils.cpp"
    require_text(sandbox_utils, r"!defined\(Q_OS_WIN\) && !defined\(Q_OS_IOS\)[\s\S]*#include <QMessageBox>", "desktop sandbox UI and signals must remain unreachable on iOS")
    require_text(sandbox_utils, r"void runLocalSandbox[\s\S]*defined\(Q_OS_IOS\)[\s\S]*Local sandbox processes are unavailable on iOS[\s\S]*return;[\s\S]*#elif defined\(Q_OS_WIN\)[\s\S]*QProcess::startDetached", "iOS must fail closed before desktop child-process launching")
    resource_cache_cpp = SOURCE_ROOT / "libraries/networking/src/ResourceCache.cpp"
    resource_cache_h = SOURCE_ROOT / "libraries/networking/src/ResourceCache.h"
    require_text(resource_cache_cpp, r"BLOCKING_INVOKE_METHOD\(this, \[this, url, extra, extraHash, scriptThread\][\s\S]*&result\)", "resource prefetch must use the typed blocking invoke boundary")
    require_text(resource_cache_cpp, r"BLOCKING_INVOKE_METHOD\(this, \[this\] \{ return getResourceList\(\); \}, &list\)", "resource-list return values must use the typed blocking invoke boundary")
    require_text(resource_cache_cpp, r"QT_VERSION >= QT_VERSION_CHECK\(6, 0, 0\)[\s\S]*size_t qHash\(const QPointer<QObject>& value, size_t seed\) noexcept[\s\S]*reinterpret_cast<quintptr>", "Qt 6 QPointer hashing must use its size_t seed without overload ambiguity")
    require_text(resource_cache_h, r"QT_VERSION >= QT_VERSION_CHECK\(6, 0, 0\)[\s\S]*size_t qHash\(const QPointer<QObject>& value, size_t seed = 0\) noexcept[\s\S]*uint qHash", "QPointer hash declarations must preserve Qt 6 and Qt 5 signatures")
    packet_headers = SOURCE_ROOT / "libraries/networking/src/udt/PacketHeaders.cpp"
    require_text(packet_headers, r"#include <QtCore/QIODevice>[\s\S]*QDataStream stream\(&buffer, QIODevice::WriteOnly\)", "protocol signature serialization must include the complete QIODevice open-mode type")
    node_permissions = SOURCE_ROOT / "libraries/networking/src/NodePermissions.cpp"
    node_permissions_text = node_permissions.read_text(encoding="utf-8")
    assert node_permissions_text.count("QUuid {}") == 4, "standard permission keys must construct explicit null UUID values"
    for standard_name in ("localhost", "logged-in", "anonymous", "friends"):
        assert f'QStringLiteral("{standard_name}")' in node_permissions_text, f"standard permission key must preserve {standard_name}"
    network_socket = SOURCE_ROOT / "libraries/networking/src/udt/NetworkSocket.cpp"
    require_text(network_socket, r"#include <QtCore/QVariant>[\s\S]*QVariant NetworkSocket::socketOption", "socket-option definitions must include their complete QVariant value type")
    require_text(network_socket, r"not recognized in socketOption\(\)\";[\s\S]*return \{\};", "unknown socket types must return an invalid QVariant fail closed")
    limited_node_list = SOURCE_ROOT / "libraries/networking/src/LimitedNodeList.cpp"
    require_text(limited_node_list, r"senderString = uuidStringWithoutCurlyBraces\(sourceID\);", "packet mismatch diagnostics must pass the UUID value to the UUID formatter")
    assert "uuidStringWithoutCurlyBraces(sourceID.toString())" not in limited_node_list.read_text(encoding="utf-8"), "UUID formatting must not round-trip through an incompatible QString"
    path_utils = SOURCE_ROOT / "libraries/shared/src/PathUtils.cpp"
    path_utils_text = path_utils.read_text(encoding="utf-8")
    assert "capturedRef(" not in path_utils_text, "Qt 6 removed QRegularExpressionMatch::capturedRef"
    assert path_utils_text.count('match.captured("pid")') == 2, "temporary-directory PID captures must retain both validation paths"
    assert 'match.captured("timestamp")' in path_utils_text, "temporary-directory timestamp capture must remain available"
    json_helpers = SOURCE_ROOT / "libraries/shared/src/shared/JSONHelpers.cpp"
    require_text(json_helpers, r"std::min\(array\.size\(\), static_cast<qsizetype>\(result\.length\(\)\)\)", "Qt 6 JSON array sizes must share an explicit index type")
    require_text(json_helpers, r"setProperty\(key\.c_str\(\), it\.value\(\)\.toVariant\(\)\)", "JSON properties must cross the QObject boundary as explicit variants")
    config_map = SOURCE_ROOT / "libraries/shared/src/HifiConfigVariantMap.cpp"
    require_text(config_map, r"QVariantMap mergedMap;", "command-line configuration must use its declared return-map type")
    assert "QMultiMap<QString, QVariant> mergedMap" not in config_map.read_text(encoding="utf-8"), "Qt 6 no longer slices QMultiMap into QVariantMap"
    grab = SOURCE_ROOT / "libraries/shared/src/Grab.cpp"
    require_text(grab, r"#include <QtCore/QIODevice>", "grab serialization must include the complete device type used for stream mode flags")
    shutdown_listener = SOURCE_ROOT / "libraries/shared/src/ShutdownEventListener.h"
    require_text(shutdown_listener, r"QT_VERSION >= QT_VERSION_CHECK\(6, 0, 0\)[\s\S]*qintptr\* result[\s\S]*long\* result", "native event filters must use the Qt 6 result type with a Qt 5 fallback")
    shutdown_listener_impl = SOURCE_ROOT / "libraries/shared/src/ShutdownEventListener.cpp"
    require_text(shutdown_listener_impl, r"QT_VERSION >= QT_VERSION_CHECK\(6, 0, 0\)[\s\S]*qintptr\* result[\s\S]*long\* result", "native event filter declarations and definitions must keep matching Qt-versioned result types")
    platform_helper = SOURCE_ROOT / "libraries/shared/src/shared/PlatformHelper.h"
    require_text(platform_helper, r"#include <QtCore/QObject>", "QObject-derived platform helpers must include their complete base type")
    cmake = IOS_ROOT / "CMakeLists.txt"
    require_text(cmake, r'CMAKE_SYSTEM_NAME STREQUAL "iOS"', "CMake must reject non-iOS targets")
    require_text(cmake, r'XCODE_ATTRIBUTE_TARGETED_DEVICE_FAMILY "1,2"', "bundle must support iPhone and iPad")
    require_text(cmake, r'XCODE_ATTRIBUTE_CODE_SIGNING_ALLOWED "NO"', "unsigned builds must be explicit")
    require_text(cmake, r'XCODE_ATTRIBUTE_CLANG_ENABLE_OBJC_ARC "YES"', "Objective-C ARC must be target-local")
    require_text(cmake, r"AUTOMOC OFF", "native bootstrap must not inherit Qt AUTOGEN")
    require_text(cmake, r'"-framework CoreGraphics"', "UIKit geometry symbols need an explicit framework")
    require_text(cmake, r'XCODE_EXPLICIT_FILE_TYPE "sourcecode\.metal"', "Xcode must compile the Metal shader source")
    require_text(cmake, r'"-framework Metal"', "bootstrap must link Metal")
    require_text(cmake, r'"-framework AVFoundation"', "bootstrap must link AVFoundation")
    require_text(cmake, r'NOT EXISTS.*PrivacyInfo', "bootstrap configure must require its privacy manifest")
    interface_cmake = SOURCE_ROOT / "interface" / "CMakeLists.txt"
    require_text(interface_cmake, r'NOT EXISTS.*OVERTE_IOS_PRIVACY_MANIFEST', "full client must fail closed without its privacy manifest")
    require_text(interface_cmake, r'MACOSX_PACKAGE_LOCATION Resources', "full client must bundle its privacy manifest as a resource")
    require_text(interface_cmake, r'CODE_SIGN_ENTITLEMENTS.*Overte\.entitlements', "full client signing must use the audited empty entitlement allowlist")
    require_text(interface_cmake, r'PRODUCT_BUNDLE_IDENTIFIER.*OVERTE_IOS_BUNDLE_IDENTIFIER', "full client signature identity must use the requested bundle ID")
    require_text(interface_cmake, r'Integrated iOS signing requires OVERTE_IOS_DEVELOPMENT_TEAM', "signed full-client configure must require a team")
    require_text(interface_cmake, r'CODE_SIGNING_ALLOWED "NO"', "unsigned full-client builds must explicitly disable signing")
    interface_cmake_text = interface_cmake.read_text(encoding="utf-8")
    target_creation = interface_cmake_text.index("add_executable(${TARGET_NAME} MACOSX_BUNDLE")
    first_target_properties = interface_cmake_text.index("set_target_properties(${TARGET_NAME} PROPERTIES")
    assert first_target_properties > target_creation, "Interface bundle properties must follow target creation"
    assert "set_target_properties(${this_target}" not in interface_cmake_text, "undefined pre-target alias must not configure Interface"
    require_text(interface_cmake, r'ASSETCATALOG_COMPILER_APPICON_NAME "AppIcon"', "full client must select the existing app icon set")
    require_text(interface_cmake, r'IPHONEOS_DEPLOYMENT_TARGET.*CMAKE_OSX_DEPLOYMENT_TARGET', "full client minimum OS must follow the configured deployment target")
    require_text(interface_cmake, r'TARGETED_DEVICE_FAMILY "1,2"', "full client must target iPhone and iPad")
    require_text(interface_cmake, r'SUPPORTED_PLATFORMS "iphoneos iphonesimulator"', "full client must declare device and simulator platforms")
    require_text(interface_cmake, r'"\$\{OVERTE_IOS_ASSET_CATALOG\}"', "full client must compile the existing asset catalog")

    networking_constants = SOURCE_ROOT / "libraries/networking/src/NetworkingConstants.h"
    require_text(networking_constants, r'URL_SCHEME_OVERTE\s*=\s*"hifi"', "registered deep-link scheme must match AddressManager")
    require_text(networking_constants, r'URL_SCHEME_OVERTEAPP\s*=\s*"hifiapp"', "registered app-command scheme must match client dispatch")
    require_text(networking_constants, r'METAVERSE_SERVER_URL_STABLE\s*\{\s*"https://', "directory traffic must use HTTPS without an ATS exception")

    qt_compat = SOURCE_ROOT / "cmake" / "QtCompat.cmake"
    require_text(qt_compat, r"OVERTE_QT_MAJOR", "Qt major selection must be centralized")
    require_text(qt_compat, r"overte_find_qt", "Qt package lookup needs a version-neutral helper")
    require_text(qt_compat, r"overte_link_qt_modules", "Qt target linking needs a version-neutral helper")
    require_text(qt_compat, r"overte_qt_add_resources", "Qt resources need a version-neutral helper")
    require_text(qt_compat, r"OVERTE_QT_UNAVAILABLE_COMPONENTS OpenGL XmlPatterns", "Qt 6 iOS must centrally reject unavailable modules")
    require_text(qt_compat, r"overte_filter_qt_components", "Qt package lookup must filter unavailable iOS modules")

    root_cmake = SOURCE_ROOT / "CMakeLists.txt"
    require_text(root_cmake, r"ANDROID OR UWP OR IOS", "iOS must use the mobile build policy")
    require_text(root_cmake, r"OVERTE_IOS_BOOTSTRAP_ONLY", "root CMake must default to the audited iOS graph")
    require_text(root_cmake, r"add_subdirectory\(ios\)", "root CMake must expose the iOS bootstrap")
    require_text(root_cmake, r"set\(PLATFORM_QT_COMPONENTS WebView Xml\)", "iOS must select WebView and Xml without retired Core5Compat")

    ui_cmake = SOURCE_ROOT / "libraries" / "ui" / "CMakeLists.txt"
    require_text(ui_cmake, r"NOT \(IOS AND OVERTE_QT_MAJOR EQUAL 6\)", "UI must exclude legacy Qt modules from iOS")
    if "XmlPatterns" in ui_cmake.read_text(encoding="utf-8"):
        raise AssertionError("UI must not link the removed Qt XmlPatterns module")
    info_view = SOURCE_ROOT / "libraries" / "ui" / "src" / "InfoView.cpp"
    require_text(info_view, r"QXmlStreamReader", "InfoView version parsing must work with Qt 6")
    require_text(info_view, r'attributes\.value\(QStringLiteral\("id"\)\).*QStringLiteral\("version"\)', "InfoView must locate the version input")
    require_text(info_view, r'attributes\.value\(QStringLiteral\("value"\)\)', "InfoView must return the version value")
    if "QXmlQuery" in info_view.read_text(encoding="utf-8"):
        raise AssertionError("InfoView must not depend on removed Qt XmlPatterns APIs")

    file_utils = SOURCE_ROOT / "libraries" / "shared" / "src" / "shared" / "FileUtils.cpp"
    require_text(file_utils, r'extraSelectors << "ios" << "mobile" << "touch"', "iOS selectors must include mobile touch variants")
    require_text(file_utils, r'<< "android_phoneInterface" << "android_interface"', "iOS must inherit the tested Phone presentation")

    ios_webview = SOURCE_ROOT / "interface" / "resources" / "qml" / "controls" / "+ios" / "FlickableWebViewCore.qml"
    require_text(ios_webview, r"import QtWebView 1\.1", "iOS web surfaces must use Qt WebView")
    offscreen_qml_surface = SOURCE_ROOT / "libraries" / "ui" / "src" / "ui" / "OffscreenQmlSurface.cpp"
    require_text(
        offscreen_qml_surface,
        r'#if !defined\(Q_OS_ANDROID\) && !defined\(Q_OS_IOS\)\s+FileTypeProfile::registerWithContext\(context\);\s+HFWebEngineProfile::registerWithContext\(context\);',
        "iOS must not compile WebEngine profile registration in offscreen contexts",
    )
    menu_source = SOURCE_ROOT / "interface" / "src" / "Menu.cpp"
    require_text(
        menu_source,
        r'#if !defined\(Q_OS_ANDROID\) && !defined\(Q_OS_IOS\)\s+FileTypeProfile::clearCache\(\);\s+HFWebEngineProfile::clearCache\(\);',
        "iOS must not compile WebEngine profile cache operations",
    )
    if "QtWebEngine" in ios_webview.read_text(encoding="utf-8"):
        raise AssertionError("iOS web surface must not import Qt WebEngine")

    moltenvk = SOURCE_ROOT / "cmake" / "modules" / "FindMoltenVK.cmake"
    require_text(moltenvk, r"ios-arm64_x86_64-simulator", "MoltenVK lookup must support arm64 simulator")
    require_text(moltenvk, r"ios-arm64", "MoltenVK lookup must support arm64 devices")
    require_text(moltenvk, r"MoltenVK/static/MoltenVK\.xcframework", "MoltenVK lookup must use the current static package layout")
    require_text(moltenvk, r"NO_DEFAULT_PATH", "MoltenVK must not be found incidentally")
    integrated_workflow = (SOURCE_ROOT / ".github/workflows/ios-integrated.yml")
    moltenvk_pin = IOS_ROOT / "moltenvk.env"
    require_text(moltenvk_pin, r"OVERTE_IOS_MOLTENVK_VERSION=1\.4\.2", "MoltenVK version must be explicit")
    require_text(moltenvk_pin, r"OVERTE_IOS_MOLTENVK_SHA256=[0-9a-f]{64}", "MoltenVK digest must be explicit")
    require_text(integrated_workflow, r"Restore pinned MoltenVK", "integrated CI must restore MoltenVK independently")
    require_text(integrated_workflow, r"OVERTE_IOS_MOLTENVK_SHA256", "MoltenVK download must verify its pinned digest")
    require_text(integrated_workflow, r"--require-moltenvk", "integrated preflight must validate MoltenVK")
    require_text(integrated_workflow, r"Save validated MoltenVK", "validated MoltenVK must become a reusable checkpoint")

    metal_shader = IOS_ROOT / "src" / "BootstrapShaders.metal"
    require_text(metal_shader, r"overteBootstrapVertex", "Metal probe needs a compiled vertex function")
    require_text(metal_shader, r"overteBootstrapFragment", "Metal probe needs a compiled fragment function")
    require_text(metal_shader, r"overteSceneVertex", "resolved domains need a compiled scene renderer")
    require_text(metal_shader, r"instanceID", "scene renderer must draw more than a bootstrap triangle")
    bootstrap_view = IOS_ROOT / "src" / "BootstrapViewController.mm"
    require_text(bootstrap_view, r"UIPanGestureRecognizer", "bootstrap must exercise continuous touch input")
    require_text(bootstrap_view, r"UIUserInterfaceIdiomPad", "bootstrap must distinguish iPad layout")
    require_text(bootstrap_view, r"safeAreaLayoutGuide", "bootstrap controls must respect safe areas")
    require_text(bootstrap_view, r"parseOverteAddress", "preview must use the tested Overte address parser")
    require_text(bootstrap_view, r"mv\.overte\.org/server/api/v1/places", "preview must resolve real Overte places")
    require_text(bootstrap_view, r"sceneLoaded = YES", "an active place must transition into its scene preview")
    require_text(bootstrap_view, r"UIPinchGestureRecognizer", "scene camera must support touch zoom")
    require_text(bootstrap_view, r"instanceCount:26", "scene draw must submit its complete instance set")
    require_text(bootstrap_view, r"OverteOpenURLNotification", "preview must consume incoming Overte deep links")
    address_parser = IOS_ROOT / "src" / "OverteAddress.cpp"
    require_text(address_parser, r"40102", "address parser must share Overtes default domain port")
    require_text(address_parser, r'"hifi".*"overte"', "address parser must accept both registered schemes")
    platform_probe = IOS_ROOT / "src" / "PlatformProbe.mm"
    require_text(platform_probe, r"nw_path_monitor_create", "bootstrap must exercise network reachability")
    require_text(platform_probe, r"CMMotionManager", "bootstrap must detect motion capability")
    require_text(platform_probe, r"NSApplicationSupportDirectory", "bootstrap must use an app container path")
    require_text(platform_probe, r"create:YES", "bootstrap must create its application support directory")
    app_delegate = IOS_ROOT / "src" / "AppDelegate.mm"
    require_text(app_delegate, r"AVAudioSessionInterruptionNotification", "audio must observe interruptions")
    require_text(app_delegate, r"AVAudioSessionRouteChangeNotification", "audio must observe route changes")
    require_text(app_delegate, r"applicationDidReceiveMemoryWarning", "lifecycle must observe memory pressure")
    require_text(app_delegate, r"LifecycleStateMachine", "application lifecycle must feed a tested state model")
    require_text(app_delegate, r"UIWindowSceneSessionRoleApplication", "scene configuration must use the current UIKit role")
    require_text(app_delegate, r"AVAudioSessionCategoryOptionAllowBluetoothHFP", "audio session must use the current Bluetooth option")
    require_text(app_delegate, r"applicationDidBecomeActive[\s\S]*setAudioSessionActive\(true\)", "foreground activation must activate the iOS audio session")
    require_text(app_delegate, r"applicationDidEnterBackground[\s\S]*setAudioSessionActive\(false, AVAudioSessionSetActiveOptionNotifyOthersOnDeactivation\)", "background entry must release the iOS audio session")
    require_text(app_delegate, r"shouldResume[\s\S]*setAudioSessionActive\(true\)", "interruption recovery must obey ShouldResume")
    require_text(app_delegate, r"requestRecordPermission", "bootstrap must request microphone permission")
    scene_delegate = IOS_ROOT / "src" / "SceneDelegate.mm"
    require_text(scene_delegate, r"PendingDeepLinkStore", "deep links must survive cold-start delivery")
    require_text(scene_delegate, r"connectionOptions\.URLContexts", "cold-start deep links must be routed")
    if "Accepted deep link with scheme %{public}@\", url" in scene_delegate.read_text(encoding="utf-8"):
        raise AssertionError("deep-link logs must not expose the complete URL")
    deep_link_store = IOS_ROOT / "src" / "PendingDeepLinkStore.cpp"
    require_text(deep_link_store, r"MAX_PENDING_URLS", "pending deep links must be bounded")
    require_text(deep_link_store, r"UnsupportedScheme", "deep-link schemes must fail closed")

    request_filters = SOURCE_ROOT / "libraries" / "ui" / "src" / "ui" / "types" / "RequestFilters.h"
    require_text(
        request_filters,
        r"!defined\(Q_OS_ANDROID\) && !defined\(Q_OS_IOS\)",
        "Qt WebEngine request filters must be excluded from iOS",
    )
    for asset_source in (
        SOURCE_ROOT / "libraries" / "networking" / "src" / "AssetResourceRequest.cpp",
        SOURCE_ROOT / "libraries" / "networking" / "src" / "AssetUtils.cpp",
    ):
        require_text(asset_source, r"QRegularExpression", "ATP validation must use the Qt 6 regular-expression API")
        require_text(asset_source, r"QRegularExpression::anchoredPattern", "ATP validation must preserve exact-match semantics")
        if "QRegExp" in asset_source.read_text(encoding="utf-8"):
            raise AssertionError(f"ATP validation retained removed QRegExp API: {asset_source}")
    address_manager = SOURCE_ROOT / "libraries" / "networking" / "src" / "AddressManager.cpp"
    require_text(address_manager, r"QRegularExpression::CaseInsensitiveOption", "address matching must preserve case-insensitive host and UUID handling")
    require_text(address_manager, r"anchoredPattern\(IP_ADDRESS_REGEX_STRING\)", "IP matching must preserve exact-match semantics")
    require_text(address_manager, r"anchoredPattern\(HOSTNAME_REGEX_STRING\)", "hostname matching must preserve exact-match semantics")
    require_text(address_manager, r"\.captured\([1-4]\)", "address matching must preserve captured network and viewpoint fields")
    require_text(address_manager, r"positionMatch\.capturedEnd", "viewpoint orientation parsing must start after the position match")
    if "QRegExp" in address_manager.read_text(encoding="utf-8"):
        raise AssertionError("AddressManager retained removed QRegExp API")
    audio_compat = SOURCE_ROOT / "libraries" / "audio-client" / "src" / "AudioDeviceCompat.h"
    require_text(audio_compat, r"QT_VERSION >= QT_VERSION_CHECK\(6, 0, 0\)", "audio device adapter must select APIs at compile time")
    require_text(audio_compat, r"using HifiQtAudioDevice = QAudioDevice;", "Qt 6 audio adapter must use QAudioDevice")
    require_text(audio_compat, r"QMediaDevices::audioInputs", "Qt 6 input enumeration must use QMediaDevices")
    require_text(audio_compat, r"QMediaDevices::audioOutputs", "Qt 6 output enumeration must use QMediaDevices")
    require_text(audio_compat, r"QMediaDevices::defaultAudioInput", "Qt 6 default input must use QMediaDevices")
    require_text(audio_compat, r"QMediaDevices::defaultAudioOutput", "Qt 6 default output must use QMediaDevices")
    require_text(audio_compat, r"using HifiQtAudioDevice = QAudioDeviceInfo;", "Qt 5 audio adapter must preserve QAudioDeviceInfo")
    require_text(audio_compat, r"using HifiAudioSource = QAudioSource;", "Qt 6 input must use QAudioSource")
    require_text(audio_compat, r"using HifiAudioSink = QAudioSink;", "Qt 6 output must use QAudioSink")
    require_text(audio_compat, r"using HifiAudioSource = QAudioInput;", "Qt 5 input must remain QAudioInput")
    require_text(audio_compat, r"using HifiAudioSink = QAudioOutput;", "Qt 5 output must remain QAudioOutput")
    require_text(audio_compat, r"hifiAudioSinkPullCapacity", "removed Qt 6 periodSize API needs an explicit allocation boundary")
    require_text(audio_compat, r"capacity bound, not a latency or callback-cadence estimate", "Qt 6 buffer size must not be misreported as a backend period")
    require_text(audio_compat, r"setSampleFormat\(QAudioFormat::Int16\)", "Qt 6 network PCM must remain signed 16-bit")
    require_text(audio_compat, r"return device\.description\(\);", "Qt 6 device naming must use QAudioDevice::description")
    require_text(audio_compat, r"hifiAudioDeviceSupportsChannelCount", "channel-count capability must remain behind the Qt 5/6 adapter")
    require_text(audio_compat, r"minimumChannelCount\(\).*maximumChannelCount\(\)", "Qt 6 channel capability must use QAudioDevice range APIs")
    hifi_audio_device = SOURCE_ROOT / "libraries" / "audio-client" / "src" / "HifiAudioDeviceInfo.h"
    require_text(hifi_audio_device, r"HifiQtAudioDevice", "audio device model must consume the compatibility type")
    if "QAudioDeviceInfo" in hifi_audio_device.read_text(encoding="utf-8"):
        raise AssertionError("HifiAudioDeviceInfo bypassed the Qt 5/6 device adapter")
    compatibility_debt = json.loads((IOS_ROOT / "compatibility-debt.json").read_text(encoding="utf-8"))
    audio_rule = next(rule for rule in compatibility_debt["rules"] if rule["id"] == "qt6-removed-audio-api")
    assert set(audio_rule["files"]) == {"libraries/audio-client/src/AudioDeviceCompat.h"}, "removed Qt 5 audio APIs must be isolated in the adapter"
    audio_runtime_rule = next(rule for rule in compatibility_debt["rules"] if rule["id"] == "qt6-audio-runtime-semantics")
    assert "On-device evidence" in audio_runtime_rule["exitCriterion"]
    audio_client_header = SOURCE_ROOT / "libraries" / "audio-client" / "src" / "AudioClient.h"
    require_text(audio_client_header, r"HifiAudioSource\* _audioInput", "input ownership must use the Qt 5/6 stream adapter")
    require_text(audio_client_header, r"HifiAudioSink\* _audioOutput", "output ownership must use the Qt 5/6 stream adapter")
    audio_client_source = SOURCE_ROOT / "libraries" / "audio-client" / "src" / "AudioClient.cpp"
    require_text(audio_client_source, r"new HifiAudioSource", "input construction must use the stream adapter")
    require_text(audio_client_source, r"new HifiAudioSink", "output construction must use the stream adapter")
    require_text(audio_client_source, r"QT_VERSION < QT_VERSION_CHECK\(6, 0, 0\)\s*\n\s*connect\([^\n]*HifiAudioSink::notify", "removed Qt 6 notify signal must remain Qt 5-only")
    require_text(audio_client_source, r"schedulePullTelemetry\(\)", "Qt 6 starvation telemetry must be driven by real sink pulls")
    require_text(audio_client_source, r"HifiAudioSink::stateChanged", "Qt 6 sink state changes must remain observable")
    require_text(audio_client_source, r"setSampleRate\(AudioConstants::SAMPLE_RATE\)", "audio must preserve the 48 kHz network rate contract")
    require_text(audio_client_source, r"hifiConfigurePcm16", "audio formats must use the Qt 5/6 PCM adapter")
    require_text(audio_client_source, r'qRegisterMetaType<HifiAudioDeviceMode>\("HifiAudioDeviceMode"\)', "queued audio mode calls must register the compatibility enum on every platform")
    require_text(audio_client_source, r"return false;\s*// a supported format could not be found", "unsupported audio formats must fail closed")
    if "QAudioDeviceInfo" in audio_client_source.read_text(encoding="utf-8"):
        raise AssertionError("AudioClient bypassed QMediaDevices/QAudioDevice compatibility helpers")
    if re.search(r"(?:\bdevice|devices\.(?:first|last)\(\)|getDevice\(\))\.deviceName\(\)", audio_client_source.read_text(encoding="utf-8")):
        raise AssertionError("AudioClient bypassed the Qt 5/6 device-name adapter")
    if "supportedChannelCounts()" in audio_client_source.read_text(encoding="utf-8"):
        raise AssertionError("AudioClient retained the removed Qt 5 channel-count API")
    audio_wav_source = SOURCE_ROOT / "libraries" / "audio-client" / "src" / "AudioFileWav.cpp"
    require_text(audio_wav_source, r'"AudioDeviceCompat\.h"', "WAV serialization must consume the Qt 5/6 format adapter")
    require_text(audio_wav_source, r"hifiAudioSampleSize\(audioFormat\)", "WAV serialization must use the Qt 5/6 sample-size adapter")
    require_text(audio_wav_source, r"sampleSize <= 0[\s\S]*return false", "unknown WAV sample formats must fail closed")
    if ".sampleSize()" in audio_wav_source.read_text(encoding="utf-8"):
        raise AssertionError("AudioFileWav retained the removed Qt 5 QAudioFormat::sampleSize API")
    script_cache_source = SOURCE_ROOT / "libraries" / "script-engine" / "src" / "ScriptCache.cpp"
    if "QNetworkConfiguration" in script_cache_source.read_text(encoding="utf-8"):
        raise AssertionError("iOS-reachable ScriptCache retained the removed Qt 5 network-configuration API")
    fingerprint_source = SOURCE_ROOT / "libraries" / "networking" / "src" / "FingerprintUtils.cpp"
    require_text(fingerprint_source, r"defined\(Q_OS_MAC\) && !defined\(Q_OS_IOS\)[\s\S]*#include <IOKit/IOBSD\.h>", "desktop IOKit fingerprint headers must be excluded from iOS")
    require_text(fingerprint_source, r"defined\(Q_OS_IOS\)[\s\S]*return QUuid\(\)\.toString\(\);[\s\S]*#else", "iOS fingerprint discovery must select the app-local fallback")
    require_text(fingerprint_source, r"FALLBACK_FINGERPRINT_KEY[\s\S]*QUuid::createUuid\(\)[\s\S]*settings\.setValue", "iOS fallback identity must be random and app-local")
    account_manager_source = (SOURCE_ROOT / "libraries" / "networking" / "src" / "AccountManager.cpp").read_text(encoding="utf-8")
    assert account_manager_source.count("&QNetworkReply::errorOccurred") == 6, "all account reply errors must use the Qt 5.15+/6 signal"
    require_text(SOURCE_ROOT / "libraries" / "networking" / "src" / "AccountManager.h", r"void requestAccessTokenError\(QNetworkReply::NetworkError error\);", "access-token transport errors need a real Qt slot")
    require_text(SOURCE_ROOT / "libraries" / "networking" / "src" / "AccountManager.cpp", r"requestAccessTokenError[\s\S]*emit loginFailed\(\)", "access-token transport errors must preserve login failure notification")
    xhr_source = (SOURCE_ROOT / "libraries" / "script-engine" / "src" / "XMLHttpRequestClass.cpp").read_text(encoding="utf-8")
    assert xhr_source.count("&QNetworkReply::errorOccurred") == 2, "XHR error connect/disconnect must remain symmetric on Qt 5.15+/6"
    for source in (account_manager_source, xhr_source):
        legacy_errors = list(re.finditer(r"SIGNAL\(error\(QNetworkReply::NetworkError\)\)", source))
        assert legacy_errors, "pre-5.15 network reply compatibility unexpectedly disappeared"
        for match in legacy_errors:
            prefix = source[max(0, match.start() - 300):match.start()]
            assert prefix.rfind("#else") > prefix.rfind("#endif"), "legacy QNetworkReply::error must remain below a version fallback"
    touch_event_source = SOURCE_ROOT / "libraries" / "script-engine" / "src" / "TouchEvent.cpp"
    require_text(touch_event_source, r"using OverteScriptTouchPoint = QEventPoint;", "Qt 6 script touch events must use QEventPoint")
    require_text(touch_event_source, r"return event\.points\(\);[\s\S]*#else[\s\S]*return event\.touchPoints\(\);", "script touch-point enumeration must preserve Qt 5 and Qt 6 paths")
    require_text(touch_event_source, r"return point\.position\(\);[\s\S]*#else[\s\S]*return point\.pos\(\);", "script touch positions must preserve Qt 5 and Qt 6 semantics")
    touchscreen_source = SOURCE_ROOT / "libraries" / "input-plugins" / "src" / "input-plugins" / "TouchscreenDevice.cpp"
    require_text(touchscreen_source, r"using OverteTouchscreenPoint = QEventPoint;", "Qt 6 touchscreen input must use QEventPoint")
    require_text(touchscreen_source, r"return event->points\(\);[\s\S]*#else[\s\S]*return event->touchPoints\(\);", "touchscreen enumeration must preserve Qt 5 and Qt 6 paths")
    require_text(touchscreen_source, r"return point\.position\(\);[\s\S]*#else[\s\S]*return point\.pos\(\);", "touchscreen positions must preserve Qt 5 and Qt 6 semantics")
    fst_source = SOURCE_ROOT / "libraries" / "model-serializers" / "src" / "FST.cpp"
    require_text(fst_source, r"_other\.cbegin\(\)[\s\S]*mapping\.insert\(it\.key\(\), it\.value\(\)\)", "FST mappings must use Qt 5/6-compatible explicit insertion")
    if ".unite(" in fst_source.read_text(encoding="utf-8"):
        raise AssertionError("iOS-reachable FST serialization retained removed Qt 6 QHash::unite")
    prepare_joints_source = SOURCE_ROOT / "libraries" / "model-baker" / "src" / "model-baker" / "PrepareJointsTask.cpp"
    require_text(prepare_joints_source, r"isVariantHash[\s\S]*metaType\(\)\.id\(\) == QMetaType::QVariantHash[\s\S]*#else[\s\S]*type\(\) == QVariant::Hash", "joint baking must preserve strict Qt 5/6 QVariantHash checks")
    prepare_joints_text = prepare_joints_source.read_text(encoding="utf-8")
    assert prepare_joints_text.count("isVariantHash(mapping[") == 3, "all three joint mapping hash checks must use the compatibility boundary"
    if re.search(r"mapping\[[^\]]+\]\.type\(\)", prepare_joints_text):
        raise AssertionError("PrepareJointsTask retained direct Qt 5 QVariant type checks")
    require_text(audio_client_source, r"hifiAudioDeviceSupportsChannelCount\([^,]+, 2\)", "stereo-input availability must use the Qt 5/6 capability adapter")
    require_text(audio_client_source, r"Q_OS_MACOS.*!defined\(Q_OS_IOS\)", "desktop AudioHardware must be excluded from iOS")
    audio_client_cmake = SOURCE_ROOT / "libraries" / "audio-client" / "CMakeLists.txt"
    require_text(audio_client_cmake, r"if \(APPLE AND NOT IOS\)", "desktop CoreAudio linkage must be excluded from iOS")
    require_text(audio_client_cmake, r"src/IOSAudioPermission\.mm", "full client must compile the iOS permission bridge")
    require_text(audio_client_cmake, r"enable_language\(OBJCXX\)", "full client must enable Objective-C++ before compiling the permission bridge")
    permission_bridge = SOURCE_ROOT / "libraries" / "audio-client" / "src" / "IOSAudioPermission.mm"
    require_text(permission_bridge, r"AVAudioSessionRecordPermissionGranted", "microphone permission must fail closed unless granted")
    require_text(permission_bridge, r"requestRecordPermission", "full client must be able to request microphone permission")
    require_text(permission_bridge, r"dispatch_get_main_queue", "permission UI must be requested on the main queue")
    require_text(permission_bridge, r"dispatch_once", "permission requests must be coalesced per process")
    require_text(permission_bridge, r"pthread_main_np[\s\S]*dispatch_sync\(dispatch_get_main_queue", "full-client AVAudioSession mutations must run on the main queue")
    require_text(permission_bridge, r"AVAudioSessionCategoryPlayAndRecord", "full client must configure a duplex audio session")
    require_text(permission_bridge, r"AVAudioSessionModeGameChat", "full client must select game-chat audio processing")
    require_text(permission_bridge, r"AVAudioSessionInterruptionOptionShouldResume", "interruption recovery must obey ShouldResume")
    require_text(permission_bridge, r"AVAudioSessionSetActiveOptionNotifyOthersOnDeactivation", "full-client shutdown must release the audio session")
    require_text(audio_client_source, r"overteIOSMicrophonePermissionGranted", "AudioClient input must enforce iOS permission")
    require_text(audio_client_source, r"void AudioClient::start\(\)[\s\S]*overteIOSActivateAudioSession", "AudioClient start must activate the native session")
    require_text(audio_client_source, r"void AudioClient::stop\(\)[\s\S]*overteIOSDeactivateAudioSession", "AudioClient stop must deactivate the native session")
    interface_cmake = SOURCE_ROOT / "interface" / "CMakeLists.txt"
    require_text(interface_cmake, r"MACOSX_BUNDLE_INFO_PLIST.*ios/resources/InterfaceInfo\.plist\.in", "full client must package its audited iOS plist")
    integrated_info = IOS_ROOT / "resources" / "InterfaceInfo.plist.in"
    with integrated_info.open("rb") as stream:
        integrated_plist = plistlib.load(stream)
    assert integrated_plist["NSMicrophoneUsageDescription"]
    assert integrated_plist["NSLocalNetworkUsageDescription"]
    assert integrated_plist["NSAppTransportSecurity"] == {"NSAllowsLocalNetworking": True}
    assert "NSBonjourServices" not in integrated_plist, "full client does not browse or advertise Bonjour"
    assert integrated_plist["LSRequiresIPhoneOS"] is True
    assert "UIApplicationSceneManifest" not in integrated_plist, "full client plist must not name bootstrap-only delegates"
    network_socket = SOURCE_ROOT / "libraries" / "networking" / "src" / "udt" / "NetworkSocket.cpp"
    require_text(network_socket, r"IOS_LOCAL_NETWORK_UDP_ERROR", "iOS UDP denial/unavailability needs categorical telemetry")
    require_text(network_socket, r"static_cast<int>\(socketError\)", "iOS UDP telemetry must use a bounded error category")
    require_text(network_socket, r"lastReportedCategory\.exchange", "iOS UDP telemetry must coalesce repeated error categories")
    udt_socket = SOURCE_ROOT / "libraries" / "networking" / "src" / "udt" / "Socket.cpp"
    require_text(udt_socket, r"iOS udt::writeDatagram error category", "iOS UDP send errors need address-free telemetry")
    require_text(udt_socket, r"iOS UDP datagram dropped because the socket is unbound", "unbound iOS UDP writes must fail closed")
    udt_text = udt_socket.read_text(encoding="utf-8")
    private_log = re.search(
        r"#if defined\(Q_OS_IOS\)\s+QDebug\(&errorString\) << \"iOS udt::writeDatagram error category\"([\s\S]*?)#else",
        udt_text,
    )
    assert private_log and "sockAddr" not in private_log.group(1) and "errorString(socketType)" not in private_log.group(1), "iOS UDP telemetry must not disclose LAN endpoints"
    for mode_boundary in (
        SOURCE_ROOT / "libraries" / "audio-client" / "src" / "AudioClient.cpp",
        SOURCE_ROOT / "libraries" / "audio-client" / "src" / "AudioClient.h",
        SOURCE_ROOT / "interface" / "src" / "scripting" / "AudioDevices.cpp",
        SOURCE_ROOT / "interface" / "src" / "scripting" / "AudioDevices.h",
        SOURCE_ROOT / "interface" / "src" / "AndroidHelper.cpp",
        SOURCE_ROOT / "libraries" / "ui" / "src" / "ui" / "OffscreenQmlSurface.cpp",
    ):
        mode_text = mode_boundary.read_text(encoding="utf-8")
        assert "HifiAudioDeviceMode" in mode_text, mode_boundary
        if re.search(r"QAudio::(?:Mode|AudioInput|AudioOutput)", mode_text):
            raise AssertionError(f"audio mode boundary bypasses compatibility enum: {mode_boundary}")
    render_utils = SOURCE_ROOT / "libraries" / "render-utils" / "CMakeLists.txt"
    require_text(
        render_utils,
        r"overte_qt_add_resources",
        "render-utils resources must use the Qt 5/6 compatibility helper",
    )
    rendering_spike = SOURCE_ROOT / "docs" / "ios" / "RENDERING_SPIKE.md"
    require_text(rendering_spike, r"15 percent", "rendering decision needs a performance threshold")
    require_text(rendering_spike, r"30-minute", "rendering decision needs a stability threshold")


def test_scope_contract() -> None:
    scope = SOURCE_ROOT / "docs" / "ios" / "PORT_SCOPE.md"
    architecture = SOURCE_ROOT / "docs" / "ios" / "ARCHITECTURE.md"
    dependency_policy = SOURCE_ROOT / "docs" / "ios" / "DEPENDENCY_POLICY.md"
    qt_setup = SOURCE_ROOT / "docs" / "ios" / "QT_SETUP.md"
    host_preparation = SOURCE_ROOT / "docs" / "ios" / "HOST_PREPARATION.md"
    xcode_first_run = SOURCE_ROOT / "docs" / "ios" / "XCODE_FIRST_RUN.md"
    review_checklist = SOURCE_ROOT / "docs" / "ios" / "REVIEW_CHECKLIST.md"
    compliance = SOURCE_ROOT / "docs" / "ios" / "COMPLIANCE.md"
    for path in (
        scope, architecture, dependency_policy, qt_setup, host_preparation,
        xcode_first_run, review_checklist, compliance,
    ):
        assert path.is_file() and path.stat().st_size > 500, path
    require_text(scope, r"First usable client", "scope needs a product acceptance target")
    require_text(architecture, r"non-JIT", "architecture must address executable-memory policy")
    require_text(dependency_policy, r"Steamworks.*disabled|disabled.*Steamworks", "desktop-only dependencies must be classified")
    require_text(qt_setup, r"OVERTE_IOS_QT_ROOT", "Qt setup must define its explicit target root")
    require_text(
        IOS_ROOT / "build-ios.sh",
        r"Qt6ConfigVersionImpl\.cmake",
        "doctor must validate the configured Qt 6 version",
    )
    require_text(host_preparation, r"cannot be closed here", "external validation limits must be explicit")
    require_text(xcode_first_run, r"first-run-triage\.json", "Xcode failures need deterministic classification")
    require_text(review_checklist, r"Signing, provisioning, upload", "external actions must remain explicit")
    require_text(compliance, r"CycloneDX 1\.6", "compliance handoff must identify the SBOM format")
    asset_interface = SOURCE_ROOT / "libraries" / "networking" / "src" / "BaseAssetScriptingInterface.cpp"
    require_text(
        asset_interface,
        r"error\s*=\s*request->getErrorString\(\);",
        "asset download failures must forward their textual error instead of assigning an enum to QString",
    )
    account_manager = SOURCE_ROOT / "libraries" / "networking" / "src" / "AccountManager.cpp"
    require_text(
        account_manager,
        r"QT_VERSION < QT_VERSION_CHECK\(6, 0, 0\)[\s\S]*qRegisterMetaTypeStreamOperators<OAuthAccessToken>",
        "Qt 5 stream-operator registration must not compile against Qt 6",
    )
    require_text(
        account_manager,
        r"QUuid::fromString\(QString::fromLatin1\([\s\S]*rawHeader\(METAVERSE_SESSION_ID_HEADER\)",
        "session IDs must be parsed explicitly from textual response headers",
    )
    require_text(
        account_manager,
        r"#if !defined\(Q_OS_IOS\)[\s\S]*QProcess launcher;[\s\S]*launcher\.startDetached\(\);[\s\S]*#endif",
        "desktop launcher processes must be excluded from iOS",
    )
    shared_qml = SOURCE_ROOT / "libraries" / "qml" / "src" / "qml" / "impl" / "SharedObject.cpp"
    require_text(
        shared_qml,
        r"QQuickGraphicsDevice::fromOpenGLContext\(context\)[\s\S]*_renderControl->initialize\(\);",
        "Qt 6 offscreen QML must initialize render control with its explicit OpenGL device",
    )
    require_text(
        shared_qml,
        r"QQuickRenderTarget::fromOpenGLTexture\(texture, size\)",
        "Qt 6 offscreen QML must render into the acquired texture",
    )
    require_text(
        shared_qml,
        r"QT_VERSION < QT_VERSION_CHECK\(6, 0, 0\)[\s\S]*setClearBeforeRendering\(true\)",
        "removed clear-before-rendering API must remain Qt 5-only",
    )
    render_event_handler = SOURCE_ROOT / "libraries" / "qml" / "src" / "qml" / "impl" / "RenderEventHandler.cpp"
    require_text(
        render_event_handler,
        r"QT_VERSION >= QT_VERSION_CHECK\(6, 0, 0\)[\s\S]*QQuickOpenGLUtils::resetOpenGLState\(\);[\s\S]*#else[\s\S]*_quickWindow->resetOpenGLState\(\);",
        "offscreen QML must use the Qt 6 OpenGL state-reset utility with its Qt 5 fallback",
    )
    offscreen_surface = SOURCE_ROOT / "libraries" / "qml" / "src" / "qml" / "OffscreenSurface.cpp"
    require_text(
        offscreen_surface,
        r"releaseTexture\(\{\s*texture,\s*fence\s*\}\);",
        "the backend-neutral discard boundary must forward its opaque fence without a GLsync dependency",
    )
    users_interface = SOURCE_ROOT / "libraries" / "script-engine" / "src" / "UsersScriptingInterface.h"
    require_text(
        users_interface,
        r"#include\s+<QObject>[\s\S]*class UsersScriptingInterface\s*:\s*public QObject",
        "UsersScriptingInterface must include its complete QObject base type",
    )
    touch_event = SOURCE_ROOT / "libraries" / "script-engine" / "src" / "TouchEvent.cpp"
    require_text(
        touch_event,
        r"QEventPoint::State::Pressed[\s\S]*QEventPoint::State::Updated[\s\S]*QEventPoint::State::Stationary[\s\S]*QEventPoint::State::Released",
        "Qt 6 scripted touch state flags must use QEventPoint states",
    )
    require_text(
        touch_event,
        r"#else[\s\S]*Qt::TouchPointPressed[\s\S]*Qt::TouchPointMoved[\s\S]*Qt::TouchPointStationary[\s\S]*Qt::TouchPointReleased",
        "Qt 5 scripted touch state flags must remain available",
    )
    scripts_filter_header = SOURCE_ROOT / "libraries" / "script-engine" / "src" / "ScriptsModelFilter.h"
    require_text(
        scripts_filter_header,
        r"QT_VERSION >= QT_VERSION_CHECK\(6, 0, 0\)[\s\S]*Q_PROPERTY\(QRegularExpression filterRegExp READ filterRegularExpression WRITE setFilterRegularExpression\)",
        "Qt 6 scripts model must preserve the filterRegExp QML compatibility property",
    )
    scripts_filter = SOURCE_ROOT / "libraries" / "script-engine" / "src" / "ScriptsModelFilter.cpp"
    require_text(
        scripts_filter,
        r"filterRegularExpression\(\)\.pattern\(\)\.isEmpty\(\)[\s\S]*#else[\s\S]*filterRegExp\(\)\.isEmpty\(\)",
        "scripts filtering must use the Qt 6 regular-expression accessor with its Qt 5 fallback",
    )
    input_configuration = SOURCE_ROOT / "libraries" / "plugins" / "src" / "plugins" / "InputConfiguration.cpp"
    input_configuration_text = input_configuration.read_text(encoding="utf-8")
    assert input_configuration_text.count("BLOCKING_INVOKE_METHOD(this, [this") == 7
    assert "Q_RETURN_ARG" not in input_configuration_text and "Q_ARG(" not in input_configuration_text
    require_text(
        input_configuration,
        r"bool result \{ false \};[\s\S]*return uncalibratePlugin\(pluginName\);[\s\S]*&result",
        "input plug-in uncalibration must use the typed blocking return boundary",
    )
    script_value_wrapper = SOURCE_ROOT / "libraries" / "script-engine" / "src" / "v8" / "ScriptValueV8Wrapper.cpp"
    require_text(
        script_value_wrapper,
        r"Failed to set property: .*QString::number\(arrayIndex\)",
        "V8 array-index diagnostics must use an explicit decimal QString conversion",
    )
    triage = json.loads((IOS_ROOT / "first-run-triage.json").read_text(encoding="utf-8"))
    assert triage["schemaVersion"] == 1
    phases = triage["phases"]
    assert len(phases) >= 10
    assert len({phase["id"] for phase in phases}) == len(phases)
    assert all(phase["ownerArea"] and phase["signatures"] for phase in phases)

    scripting = SOURCE_ROOT / "docs" / "ios" / "SCRIPTING.md"
    require_text(scripting, r"--jitless", "iOS scripting must enforce non-JIT execution")
    require_text(scripting, r"OVERTE_IOS_V8_ROOT", "iOS V8 package must use an explicit root")

    script_engine = SOURCE_ROOT / "libraries" / "script-engine" / "src" / "v8" / "ScriptEngineV8.cpp"
    require_text(script_engine, r'--stack-size=256 --jitless --no-expose-wasm', "iOS V8 flags must fail closed")
    qt6_migration = SOURCE_ROOT / "docs" / "ios" / "QT6_MIGRATION.md"
    require_text(qt6_migration, r"QAudioDeviceInfo/QAudioInput/QAudioOutput", "Qt 6 audio boundary must be explicit")
    require_text(qt6_migration, r"must not enter the iOS target", "desktop-only Qt paths must be excluded")
    require_text(qt6_migration, r"This AppDelegate is not linked into the Qt full-client target", "bootstrap AVAudioSession behavior must not be claimed for the full client")

    setup_library = SOURCE_ROOT / "cmake" / "macros" / "SetupHifiLibrary.cmake"
    setup_library_text = setup_library.read_text(encoding="utf-8")
    assert len(re.findall(r"elseif \(NOT IOS AND \(APPLE OR", setup_library_text)) == 3, (
        "all AVX, AVX2, and AVX512 compiler-flag branches must exclude iOS"
    )
    for desktop_flag in ("-mavx", "-mavx2", "-mavx512f"):
        require_text(setup_library, re.escape(desktop_flag), f"desktop SIMD flag {desktop_flag} must remain available")

    target_neuron = SOURCE_ROOT / "cmake" / "macros" / "TargetNeuron.cmake"
    require_text(
        target_neuron,
        r"if \(WIN32 OR \(APPLE AND NOT IOS\)\)[\s\S]*?find_package\(Neuron REQUIRED\)",
        "the desktop-only Neuron SDK must not enter the iOS plugin graph",
    )
    assert "if (WIN32 OR APPLE)" not in target_neuron.read_text(encoding="utf-8")

    add_crashpad = SOURCE_ROOT / "cmake" / "macros" / "AddCrashpad.cmake"
    require_text(
        add_crashpad,
        r"if \(IOS\)\s+message\(STATUS \"Checking crashpad config - desktop handler packaging is not supported on iOS, disabled\.\"\)\s+set\(USE_CRASHPAD FALSE\)\s+endif\(\)\s+if \(USE_CRASHPAD\)",
        "iOS must disable Crashpad before package discovery and desktop handler packaging",
    )
    require_text(
        add_crashpad,
        r"COMMAND \$\{CMAKE_COMMAND\} -E copy \$\{CRASHPAD_HANDLER_EXE_PATH\}",
        "desktop targets must retain their existing Crashpad handler packaging",
    )

    platform_cmake = SOURCE_ROOT / "libraries" / "platform" / "CMakeLists.txt"
    platform_factory = SOURCE_ROOT / "libraries" / "platform" / "src" / "platform" / "backend" / "Platform.cpp"
    ios_platform = platform_factory.parent / "IOSPlatform.cpp"
    require_text(
        platform_cmake,
        r"if \(IOS\)[\s\S]*?list\(REMOVE_ITEM PLATFORM_TARGET_SOURCES[\s\S]*?MACOSPlatform\.cpp[\s\S]*?MACOSPlatform\.h",
        "iOS must exclude the AppKit/CGL platform implementation from its target sources",
    )
    require_text(
        platform_cmake,
        r"else\(\)[\s\S]*?list\(REMOVE_ITEM PLATFORM_TARGET_SOURCES[\s\S]*?IOSPlatform\.cpp[\s\S]*?IOSPlatform\.h[\s\S]*?endif\(\)\s+set_property",
        "desktop targets must not compile the iOS fallback backend",
    )
    require_text(
        platform_factory,
        r"#if defined\(Q_OS_IOS\)\s+#include \"IOSPlatform\.h\"\s+#elif defined\(Q_OS_WIN\)",
        "the iOS platform factory must take precedence over Darwin/macOS aliases",
    )
    require_text(
        platform_factory,
        r"#if defined\(Q_OS_IOS\)\s+_instance = new IOSInstance\(\);\s+#elif defined\(Q_OS_WIN\)",
        "the full client must instantiate the conservative iOS platform backend",
    )
    ios_platform_text = ios_platform.read_text(encoding="utf-8")
    for desktop_api in (
        r"#include\s*[<\"]AppKit",
        r"#include\s*[<\"]ApplicationServices",
        r"#include\s*[<\"]OpenGL/OpenGL\.h",
        r"\bCGL(?:Query|Describe|Destroy)",
        r"QProcess[^;]*system_profiler",
    ):
        assert re.search(desktop_api, ios_platform_text) is None, (
            f"iOS platform fallback imported desktop API: {desktop_api}"
        )
    require_text(ios_platform, r"OS_IOS", "iOS platform telemetry must not identify itself as macOS")
    require_text(
        ios_platform,
        r"void IOSInstance::enumerateGraphicsApis\(\) \{[\s\S]*?Do not call the generic GL/Vulkan probe",
        "iOS platform discovery must not probe graphics before the renderer owns a surface",
    )

    fst_reader = SOURCE_ROOT / "libraries" / "model-serializers" / "src" / "FSTReader.cpp"
    require_text(
        fst_reader,
        r"#if QT_VERSION >= QT_VERSION_CHECK\(6, 0, 0\)\s+const bool hasJointHash = jointMapping\.metaType\(\)\.id\(\) == QMetaType::QVariantHash;",
        "FST joint mappings must use the Qt 6 metatype API",
    )
    require_text(
        fst_reader,
        r"#else\s+const bool hasJointHash = jointMapping\.type\(\) == QVariant::Hash;\s+#endif",
        "the model parser must retain its Qt 5 type check",
    )
    require_text(
        fst_reader,
        r"if \(mapping\.contains\(\"joint\"\) && hasJointHash\) \{\s+joints = mapping\.value\(\"joint\"\)\.toHash\(\);",
        "the Qt 6 port must preserve FST joint-map extraction",
    )

    for qml_message_source, argument in (
        (SOURCE_ROOT / "libraries" / "ui" / "src" / "QmlWindowClass.cpp", "webMessage"),
        (SOURCE_ROOT / "libraries" / "ui" / "src" / "ui" / "OffscreenQmlSurface.cpp", "message"),
    ):
        require_text(
            qml_message_source,
            rf"#if QT_VERSION >= QT_VERSION_CHECK\(6, 0, 0\)\s+const bool isStringMessage = {argument}\.metaType\(\)\.id\(\) == QMetaType::QString;",
            "QML/web keyboard messages must use the Qt 6 metatype API",
        )
        require_text(
            qml_message_source,
            rf"#else\s+const bool isStringMessage = {argument}\.type\(\) == QVariant::String;\s+#endif\s+QString messageString = isStringMessage \? {argument}\.toString\(\) : \"\";",
            "Qt 5 compatibility and exact string-only keyboard handling must remain",
        )

    offscreen_qml = SOURCE_ROOT / "libraries" / "ui" / "src" / "ui" / "OffscreenQmlSurface.cpp"
    require_text(
        offscreen_qml,
        r"#if QT_VERSION < QT_VERSION_CHECK\(6, 0, 0\)\s+#include <QtMultimedia/QMediaService>\s+#include <QtMultimedia/QAudioOutputSelectorControl>\s+#include <QtMultimedia/QMediaPlayer>\s+#endif",
        "removed Qt 5 multimedia service headers must not enter the Qt 6 iOS source",
    )
    require_text(
        offscreen_qml,
        r"#if QT_VERSION < QT_VERSION_CHECK\(6, 0, 0\)\s+class AudioHandler[\s\S]*?QMediaPlayer[\s\S]*?#endif",
        "the legacy QML audio-output control implementation must remain Qt 5-only",
    )
    require_text(
        offscreen_qml,
        r"#if QT_VERSION < QT_VERSION_CHECK\(6, 0, 0\) && !defined\(Q_OS_ANDROID\) && !defined\(Q_OS_IOS\)[\s\S]*?new AudioHandler",
        "no Qt 6 or mobile target may instantiate the removed service-control adapter",
    )

    suggestions_engine = SOURCE_ROOT / "interface" / "src" / "webbrowser" / "WebBrowserSuggestionsEngine.cpp"
    require_text(
        suggestions_engine,
        r"#if QT_VERSION >= QT_VERSION_CHECK\(6, 0, 0\)\s+const bool isSuggestionList = res\.metaType\(\)\.id\(\) == QMetaType::QVariantList;",
        "the iOS suggestion parser must use the Qt 6 metatype API",
    )
    require_text(
        suggestions_engine,
        r"#else\s+const bool isSuggestionList = res\.type\(\) == QVariant::List;\s+#endif\s+if \(err\.error != QJsonParseError::NoError \|\| !isSuggestionList\)",
        "Qt 5 compatibility and JSON top-level-list validation must remain",
    )

    avatar_doctor = SOURCE_ROOT / "interface" / "src" / "avatar" / "AvatarDoctor.cpp"
    require_text(
        avatar_doctor,
        r"#if QT_VERSION >= QT_VERSION_CHECK\(6, 0, 0\)\s+const bool hasJointNameHash = jointNameMapping\.metaType\(\)\.id\(\) == QMetaType::QVariantHash;",
        "avatar joint-map diagnostics must use the Qt 6 metatype API",
    )
    require_text(
        avatar_doctor,
        r"#else\s+const bool hasJointNameHash = jointNameMapping\.type\(\) == QVariant::Hash;\s+#endif\s+if \(mapping\.contains\(JOINT_NAME_MAPPING_FIELD\) && hasJointNameHash\)",
        "Qt 5 compatibility and strict joint-hash validation must remain",
    )

    setting_helpers = SOURCE_ROOT / "libraries" / "shared" / "src" / "SettingHelpers.cpp"
    require_text(
        setting_helpers,
        r"#if QT_VERSION >= QT_VERSION_CHECK\(6, 0, 0\)\s+return variant\.metaType\(\)\.id\(\);\s+#else\s+return variant\.userType\(\);\s+#endif",
        "settings serialization must use stable Qt 5/6 metatype IDs",
    )
    setting_helpers_text = setting_helpers.read_text(encoding="utf-8")
    assert ".type()" not in setting_helpers_text, "SettingHelpers retained the removed QVariant::type API"
    for normalized_type in ("Float", "UShort", "QUrl"):
        require_text(
            setting_helpers,
            rf"variantType == QMetaType::{normalized_type}",
            f"settings JSON must preserve {normalized_type} normalization",
        )
    for serialized_type in ("QVariantHash", "UnknownType", "QVariantMap", "QVariantList", "QString", "QByteArray", "QRect", "QSize", "QPoint"):
        require_text(
            setting_helpers,
            rf"case QMetaType::{serialized_type}:",
            f"settings JSON must preserve {serialized_type} handling",
        )

    osc_interface = SOURCE_ROOT / "interface" / "src" / "scripting" / "OSCScriptingInterface.cpp"
    require_text(
        osc_interface,
        r"#if QT_VERSION >= QT_VERSION_CHECK\(6, 0, 0\)\s+return value\.metaType\(\)\.id\(\);\s+#else\s+return value\.userType\(\);\s+#endif",
        "OSC serialization must use stable Qt 5/6 metatype IDs",
    )
    osc_text = osc_interface.read_text(encoding="utf-8")
    assert "QVariant::Type" not in osc_text and ".type()" not in osc_text, (
        "OSC serialization retained removed QVariant type APIs"
    )
    expected_osc_types = {
        "Int": "Int",
        "Float": "Double",
        "String": "QString",
        "Blob": "QByteArray",
        "False": "Bool",
        "True": "Bool",
        "Null": "UnknownType",
    }
    for tag, meta_type in expected_osc_types.items():
        require_text(
            osc_interface,
            rf"\{{ OSCTag::{tag}, QMetaType::{meta_type} \}}",
            f"OSC tag {tag} must retain its QVariant payload type",
        )
    require_text(
        osc_interface,
        r"oscVariantTypeId\(arg\) == QMetaType::QVariantMap",
        "explicit OSC type wrappers must remain QVariant maps",
    )

    octree_persist = SOURCE_ROOT / "libraries" / "octree" / "src" / "OctreePersistThread.cpp"
    require_text(octree_persist, r"#include <QRegularExpression>", "octree backup cleanup must use the Qt 6 regex API")
    require_text(octree_persist, r"QRegularExpression::anchoredPattern", "backup matching must preserve QRegExp exactMatch semantics")
    require_text(octree_persist, r"filenameRegex\.match\(absPath\)\.hasMatch\(\)", "backup cleanup must test the anchored Qt 6 match")

    domain_handler = SOURCE_ROOT / "libraries" / "networking" / "src" / "DomainHandler.cpp"
    require_text(
        domain_handler,
        r"QHostInfo::lookupHost\(domainURL\.host\(\), this, &DomainHandler::completedHostnameLookup\)",
        "domain DNS completion must use the typed Qt 6 context overload",
    )
    if re.search(r"QHostInfo::lookupHost\([^;]*\bSLOT\s*\(", domain_handler.read_text(encoding="utf-8")):
        raise AssertionError("domain DNS lookup must not depend on string-normalized Qt slot signatures")

    network_socket = SOURCE_ROOT / "libraries" / "networking" / "src" / "udt" / "NetworkSocket.cpp"
    require_text(
        network_socket,
        r"#if QT_VERSION >= QT_VERSION_CHECK\(5, 15, 0\)\s+connect\(&_udpSocket, &QAbstractSocket::errorOccurred,\s+this, &NetworkSocket::onUDPSocketError\);",
        "the iOS UDT socket must connect Qt 6 UDP errors through the typed signal",
    )
    require_text(
        network_socket,
        r"#else\s+// Preserve compatibility with Android builds that still use Qt before 5\.15\.",
        "the Qt 6 socket fix must retain the legacy Android compatibility branch",
    )

    octree_processor = SOURCE_ROOT / "interface" / "src" / "octree" / "OctreePacketProcessor.cpp"
    ios_free_file_logger_guard = (
        r"#if !defined\(Q_OS_ANDROID\) && !defined\(Q_OS_IOS\) && !defined\(OVERTE_IOS\)"
    )
    processor_text = octree_processor.read_text(encoding="utf-8")
    assert len(re.findall(ios_free_file_logger_guard, processor_text)) == 2, (
        "FileLogger include and queue diagnostic must both be excluded from iOS"
    )
    require_text(
        octree_processor,
        ios_free_file_logger_guard + r"\s+#include <shared/FileLogger\.h>",
        "the entity receive path must not import the desktop file logger on iOS",
    )
    require_text(
        octree_processor,
        ios_free_file_logger_guard + r"[\s\S]*?qApp->getLogger\(\)->extraDebugging\(\)[\s\S]*?#endif",
        "the desktop queue diagnostic must remain inside the same iOS exclusion",
    )

    resource_manager = SOURCE_ROOT / "libraries" / "networking" / "src" / "ResourceManager.cpp"
    resource_manager_text = resource_manager.read_text(encoding="utf-8")
    normalize_string = re.search(
        r"QString ResourceManager::normalizeURL\(const QString& urlString\) \{([\s\S]*?)\n\}",
        resource_manager_text,
    )
    assert normalize_string is not None, "ResourceManager string URL normalization is missing"
    normalize_body = normalize_string.group(1)
    assert "foreach" not in normalize_body, "ATP prefix normalization must compile with QT_NO_FOREACH"
    assert "for (const auto& entry : copy)" in normalize_body
    assert "result.replace(0, prefix.size(), replacement);" in normalize_body, (
        "range-for migration must preserve prefix replacement boundaries"
    )

    obj_writer = SOURCE_ROOT / "libraries" / "model-serializers" / "src" / "OBJWriter.cpp"
    require_text(obj_writer, r'#include <QRegularExpression>', "OBJ group-name sanitization must use the Qt 6 regex API")
    require_text(
        obj_writer,
        r'\.replace\(QRegularExpression\(QStringLiteral\("\[\^-_a-zA-Z0-9\]"\)\), QStringLiteral\("_"\)\)',
        "OBJ group-name sanitization must preserve its global allowed-character replacement",
    )
    if "QRegExp" in obj_writer.read_text(encoding="utf-8"):
        raise AssertionError("OBJWriter retained removed QRegExp API")

    tooltip = SOURCE_ROOT / "libraries" / "ui" / "src" / "Tooltip.cpp"
    require_text(tooltip, r'#include <QtCore/QRegularExpression>', "place-name previews must use the Qt 6 regex API")
    require_text(tooltip, r"QRegularExpression::anchoredPattern\(PLACE_NAME_REGEX_STRING\)", "place-name matching must remain exact")
    require_text(tooltip, r"placeNameRegex\.match\(_title\)\.hasMatch\(\)", "place-name previews must retain their match gate")
    if "QRegExp" in tooltip.read_text(encoding="utf-8"):
        raise AssertionError("Tooltip retained removed QRegExp API")

    http_manager = SOURCE_ROOT / "libraries" / "embedded-webserver" / "src" / "HTTPManager.cpp"
    require_text(http_manager, r'#include <QtCore/QRegularExpression>', "SSI includes must use the Qt 6 regex API")
    require_text(http_manager, r'includeRegExp\.match\(localFileString, matchPosition\)', "SSI scanning must retain its search offset")
    require_text(http_manager, r'includeMatch\.captured\(1\) == "file"', "SSI file/virtual capture semantics must be preserved")
    require_text(http_manager, r'includeMatch\.captured\(2\)', "SSI include paths must still come from capture group two")
    require_text(http_manager, r'matchPosition \+= matchedLength;', "SSI scanning must retain its post-replacement advance")
    if "QRegExp" in http_manager.read_text(encoding="utf-8"):
        raise AssertionError("HTTPManager retained removed QRegExp API")

    archive_download = SOURCE_ROOT / "interface" / "src" / "ArchiveDownloadInterface.cpp"
    archive_download_text = archive_download.read_text(encoding="utf-8")
    assert "QTextCodec" not in archive_download_text, (
        "archive extraction must not retain an unused Qt Core5Compat dependency"
    )
    assert "QStringList extracted = JlCompress::extractDir(archive, target);" in archive_download_text, (
        "removing the unused codec include must not replace the production archive extractor"
    )
    assert "if (!validateArchive(archive))" in archive_download_text, (
        "removing the unused codec include must preserve fail-closed archive validation"
    )

    application_assets = SOURCE_ROOT / "interface" / "src" / "Application_Assets.cpp"
    require_text(application_assets, r'#include <QRegularExpression>', "asset ZIP names must use the Qt 6 regex API")
    require_text(
        application_assets,
        r'zipFile\.section\("/", -1\)\.remove\(QRegularExpression\(QStringLiteral\("\[\.\]zip\(\.\*\)\$"\)\)\)',
        "asset ZIP suffix removal must remain anchored and operate on the final path component",
    )
    if "QRegExp" in application_assets.read_text(encoding="utf-8"):
        raise AssertionError("Application_Assets retained removed QRegExp API")

    location_bookmarks = SOURCE_ROOT / "interface" / "src" / "LocationBookmarks.cpp"
    require_text(location_bookmarks, r'#include <QRegularExpression>', "bookmark names must use the Qt 6 regex API")
    require_text(
        location_bookmarks,
        r'bookmarkName\.trimmed\(\)\.replace\(\s*QRegularExpression\(QStringLiteral\("\(\\r\\n\|\[\\r\\n\\t\\v \]\)\+"\)\), QStringLiteral\(" "\)\)',
        "bookmark names must still trim boundaries and collapse supported whitespace runs",
    )
    if "QRegExp" in location_bookmarks.read_text(encoding="utf-8"):
        raise AssertionError("LocationBookmarks retained removed QRegExp API")

    snapshot = SOURCE_ROOT / "interface" / "src" / "ui" / "Snapshot.cpp"
    require_text(snapshot, r'#include <QtCore/QRegularExpression>', "snapshot usernames must use the Qt 6 regex API")
    require_text(
        snapshot,
        r'username\.replace\(QRegularExpression\(QStringLiteral\("\[\^A-Za-z0-9_\]"\)\), QStringLiteral\("-"\)\)',
        "snapshot usernames must retain their global ASCII allowlist replacement",
    )
    if "QRegExp" in snapshot.read_text(encoding="utf-8"):
        raise AssertionError("Snapshot retained removed QRegExp API")

    update_dialog = SOURCE_ROOT / "interface" / "src" / "ui" / "UpdateDialog.cpp"
    require_text(update_dialog, r'#include <QtCore/QRegularExpression>', "release notes must use the Qt 6 regex API")
    require_text(
        update_dialog,
        r'releaseNotes\.remove\(QRegularExpression\(QStringLiteral\("\^\\n\+"\)\)\)',
        "release notes must still remove only leading newline runs",
    )
    if "QRegExp" in update_dialog.read_text(encoding="utf-8"):
        raise AssertionError("UpdateDialog retained removed QRegExp API")

    model_selector = SOURCE_ROOT / "interface" / "src" / "ModelSelector.cpp"
    require_text(model_selector, r'#include <QRegularExpression>', "model selection must use the Qt 6 regex API")
    require_text(
        model_selector,
        r'fileInfo\.isFile\(\) && fileInfo\.completeSuffix\(\)\.contains\(\s*QRegularExpression\(QStringLiteral\("fst\|fbx\|FST\|FBX"\)\)\)',
        "model selection must retain its file gate and complete-suffix substring alternatives",
    )
    if "QRegExp" in model_selector.read_text(encoding="utf-8"):
        raise AssertionError("ModelSelector retained removed QRegExp API")

    scripts_model = SOURCE_ROOT / "libraries" / "script-engine" / "src" / "ScriptsModel.cpp"
    require_text(scripts_model, r'#include <QRegularExpression>', "default-script keys must use the Qt 6 regex API")
    require_text(
        scripts_model,
        r'QRegularExpression::anchoredPattern\(QStringLiteral\("\.\*\\\\\.js"\)\)',
        "default-script matching must preserve the former whole-string .js gate",
    )
    require_text(
        scripts_model,
        r'if \(jsRegex\.match\(xml\.text\(\)\.toString\(\)\)\.hasMatch\(\)\)',
        "default-script XML keys must retain their match gate",
    )
    if "QRegExp" in scripts_model.read_text(encoding="utf-8"):
        raise AssertionError("ScriptsModel retained removed QRegExp API")

    string_helpers = SOURCE_ROOT / "libraries" / "shared" / "src" / "shared" / "StringHelpers.cpp"
    require_text(string_helpers, r'#include <QRegularExpression>', "word wrapping must use the Qt 6 regex API")
    require_text(
        string_helpers,
        r'input\.split\(QRegularExpression\(QStringLiteral\("\\\\s\+"\)\), Qt::KeepEmptyParts\)',
        "word wrapping must retain whitespace-run splitting and legacy empty-part handling",
    )
    if "QRegExp" in string_helpers.read_text(encoding="utf-8"):
        raise AssertionError("StringHelpers retained removed QRegExp API")

    config_variant_map = SOURCE_ROOT / "libraries" / "shared" / "src" / "HifiConfigVariantMap.cpp"
    require_text(config_variant_map, r'#include <QtCore/QRegularExpression>', "CLI keys must use the Qt 6 regex API")
    require_text(
        config_variant_map,
        r'QRegularExpression::anchoredPattern\(DASHED_KEY_REGEX_STRING\)',
        "CLI key scanning must preserve whole-argument matching",
    )
    require_text(
        config_variant_map,
        r'dashedKeyRegex\.match\(argumentList\[keyIndex\]\)\.captured\(2\)',
        "CLI map keys must still come from capture group two of the matched argument",
    )
    assert config_variant_map.read_text(encoding="utf-8").count("argumentList.indexOf(dashedKeyRegex") == 3, (
        "CLI key scanning must retain initial, next-key, and post-config searches"
    )
    if "QRegExp" in config_variant_map.read_text(encoding="utf-8"):
        raise AssertionError("HifiConfigVariantMap retained removed QRegExp API")

    anim_expression = SOURCE_ROOT / "libraries" / "animation" / "src" / "AnimExpression.cpp"
    anim_expression_text = anim_expression.read_text(encoding="utf-8")
    assert "QRegExp" not in anim_expression_text, (
        "the animation expression parser must not retain an unused Core5Compat include"
    )
    assert "parseExpr(_expression, iter);" in anim_expression_text, (
        "removing the unused regex include must preserve expression parsing"
    )
    assert "if (iter->isSpace())" in anim_expression_text and "else if (iter->isLetter())" in anim_expression_text, (
        "the animation expression tokenizer must remain the production character-driven implementation"
    )
    assert "AnimExpression::OpCode AnimExpression::evaluate" in anim_expression_text, (
        "removing the unused regex include must preserve expression evaluation"
    )
    anim_expression_header = SOURCE_ROOT / "libraries" / "animation" / "src" / "AnimExpression.h"
    anim_expression_header_text = anim_expression_header.read_text(encoding="utf-8")
    assert "#include <QStringView>" in anim_expression_header_text
    assert "explicit Token(QStringView strView)" in anim_expression_header_text
    assert "explicit OpCode(QStringView strView)" in anim_expression_header_text
    assert "const auto stringView = QStringView(str).mid(pos, len);" in anim_expression_text
    assert "QString sub = QStringView(str).mid(pos, len).toString();" in anim_expression_text
    flow = SOURCE_ROOT / "libraries" / "animation" / "src" / "Flow.cpp"
    flow_text = flow.read_text(encoding="utf-8")
    assert "QStringView(name).left(3).toString().toUpper()" in flow_text
    assert "QStringView(name).mid(name.size() - j, 1).toString().toFloat(&toFloatSuccess)" in flow_text
    assert "QStringView(name).mid(simPrefix.size(), name.size() - j + 1 - simPrefix.size()).toString()" in flow_text
    assert "QStringView(name).mid(simPrefix.size(), name.size() - simPrefix.size()).toString()" in flow_text
    for animation_text in (anim_expression_header_text, anim_expression_text, flow_text):
        if "QStringRef" in animation_text:
            raise AssertionError("iOS-reachable animation code retained removed QStringRef API")
    entity_properties_template = SOURCE_ROOT / "libraries" / "entities" / "src" / "EntityItemProperties.cpp.in"
    entity_properties_template_text = entity_properties_template.read_text(encoding="utf-8")
    assert "#include <QtCore/QStringView>" in entity_properties_template_text
    assert "uint16_t getCollisionGroupAsBitMask(QStringView name)" in entity_properties_template_text
    assert "maskString.split(QLatin1Char(','), Qt::KeepEmptyParts)" in entity_properties_template_text
    assert "getCollisionGroupAsBitMask(QStringView(groupName))" in entity_properties_template_text
    if "QStringRef" in entity_properties_template_text or "splitRef(" in entity_properties_template_text:
        raise AssertionError("generated EntityItemProperties source retained removed QStringRef API")
    entity_generator = SOURCE_ROOT / "cmake" / "macros" / "GenerateEntityProperties.cmake"
    require_text(
        entity_generator,
        r'configure_file\(\s*\$\{CMAKE_CURRENT_SOURCE_DIR\}/src/EntityItemProperties\.cpp\.in\s*\$\{CMAKE_CURRENT_BINARY_DIR\}/src/EntityItemProperties\.cpp\)',
        "the migrated EntityItemProperties template must remain the generated production source",
    )

    log_handler = SOURCE_ROOT / "libraries" / "shared" / "src" / "LogHandler.h"
    log_handler_text = log_handler.read_text(encoding="utf-8")
    assert "QRegExp" not in log_handler_text, (
        "the shared logging interface must not expose an unused Core5Compat dependency"
    )
    assert "bool parseOptions(const QString& options, const QString &paramName);" in log_handler_text, (
        "removing the unused regex include must preserve logging option parsing"
    )
    assert "static void verboseMessageHandler(" in log_handler_text, (
        "removing the unused regex include must preserve the Qt message-handler entry point"
    )
    assert "void printRepeatedMessage(" in log_handler_text and "void setupRepeatedMessageFlusher();" in log_handler_text, (
        "removing the unused regex include must preserve repeated-message handling"
    )

    file_logger = SOURCE_ROOT / "libraries" / "shared" / "src" / "shared" / "FileLogger.cpp"
    require_text(file_logger, r'#include <QtCore/QRegularExpression>', "rolled log matching must use the Qt 6 regex API")
    require_text(
        file_logger,
        r'QRegularExpression::anchoredPattern\("overte-log_" \+ DATETIME_WILDCARD \+ "\(_" \+ SESSION_WILDCARD \+ "\)\?\\\\\.txt"\)',
        "rolled log matching must preserve the complete timestamp/session filename pattern",
    )
    require_text(
        file_logger,
        r'!LOG_FILENAME_REGEX\.match\(fileInfo\.fileName\(\)\)\.hasMatch\(\)',
        "log-directory accounting must retain its whole-filename match gate",
    )
    if "QRegExp" in file_logger.read_text(encoding="utf-8"):
        raise AssertionError("FileLogger retained removed QRegExp API")

    application_graphics = SOURCE_ROOT / "interface" / "src" / "Application_Graphics.cpp"
    require_text(application_graphics, r'#include <QtCore/QRegularExpression>', "script allowlists must use the Qt 6 regex API")
    require_text(
        application_graphics,
        r'qEnvironmentVariable\("EXTRA_ALLOWLIST"\)\.trimmed\(\)\.split\(\s*QRegularExpression\(QStringLiteral\("\\\\s\*,\\\\s\*"\)\), Qt::SkipEmptyParts\)',
        "environment script allowlists must retain comma splitting and empty-entry rejection",
    )
    require_text(
        application_graphics,
        r'raw\.toString\(\)\.trimmed\(\)\.split\(\s*QRegularExpression\(QStringLiteral\("\\\\s\*\[,\\r\\n\]\+\\\\s\*"\)\), Qt::SkipEmptyParts\)',
        "settings script allowlists must retain comma/newline splitting and empty-entry rejection",
    )
    if "QRegExp" in application_graphics.read_text(encoding="utf-8"):
        raise AssertionError("Application_Graphics retained removed QRegExp API")

    base_log_dialog = SOURCE_ROOT / "interface" / "src" / "ui" / "BaseLogDialog.cpp"
    require_text(base_log_dialog, r'#include <QRegularExpression>', "log highlighting must use the Qt 6 regex API")
    require_text(base_log_dialog, r'auto match = expression\.match\(text\);', "bold log scanning must begin at the first match")
    require_text(base_log_dialog, r'const int index = match\.capturedStart\(\);', "bold formatting must begin at the matched range")
    require_text(base_log_dialog, r'const int length = match\.capturedLength\(\);', "bold formatting must retain matched length")
    require_text(
        base_log_dialog,
        r'match = expression\.match\(text, index \+ length\);',
        "bold log scanning must advance beyond the prior matched range",
    )
    if "QRegExp" in base_log_dialog.read_text(encoding="utf-8"):
        raise AssertionError("BaseLogDialog retained removed QRegExp API")

    models_browser = SOURCE_ROOT / "interface" / "src" / "ui" / "ModelsBrowser.cpp"
    require_text(models_browser, r'#include <QRegularExpression>', "model-browser keys must use the Qt 6 regex API")
    require_text(
        models_browser,
        r'QRegularExpression rx\(QRegularExpression::anchoredPattern\(_nameFilter\)\)',
        "model-browser filtering must preserve whole-key matching for the configured expression",
    )
    require_text(
        models_browser,
        r'if \(rx\.match\(xml\.text\(\)\.toString\(\)\)\.hasMatch\(\)\)',
        "model-browser XML keys must retain their filter gate",
    )
    if "QRegExp" in models_browser.read_text(encoding="utf-8"):
        raise AssertionError("ModelsBrowser retained removed QRegExp API")

    js_console = SOURCE_ROOT / "interface" / "src" / "ui" / "JSConsole.cpp"
    require_text(js_console, r'#include <QRegularExpression>', "console completion must use the Qt 6 regex API")
    require_text(
        js_console,
        r'QStringLiteral\("\(\(\(\[A-Za-z0-9_\\\\\.\]\+\)\\\\\.\)\|\(\?!\\\\\.\)\)\(\[a-zA-Z0-9_\]\*\)\$"\)',
        "console completion must retain module/property groups and its cursor suffix anchor",
    )
    require_text(
        js_console,
        r'regExp\.match\(leftOfCursor\)\.capturedTexts\(\)',
        "console completion captures must come from the left-of-cursor suffix match",
    )
    assert "const int MODULE_INDEX = 3;" in js_console.read_text(encoding="utf-8")
    assert "const int PROPERTY_INDEX = 4;" in js_console.read_text(encoding="utf-8")
    if "QRegExp" in js_console.read_text(encoding="utf-8"):
        raise AssertionError("JSConsole retained removed QRegExp API")

    application_version = SOURCE_ROOT / "libraries" / "shared" / "src" / "ApplicationVersion.cpp"
    require_text(application_version, r'#include <QtCore/QRegularExpression>', "version parsing must use the Qt 6 regex API")
    require_text(
        application_version,
        r'QStringLiteral\("\(\[\\\\d\]\+\)\\\\\.\(\[\\\\d\]\+\)\(\?:\\\\\.\(\[\\\\d\]\+\)\)\?"\)',
        "version parsing must retain major/minor and optional patch capture groups",
    )
    require_text(application_version, r'const auto semanticMatch = semanticRegex\.match\(versionString\);', "semantic versions must retain unanchored search behavior")
    require_text(application_version, r'if \(semanticMatch\.hasMatch\(\)\)', "semantic-version classification must retain its match gate")
    require_text(application_version, r'auto captures = semanticMatch\.capturedTexts\(\);', "version components must come from the successful match")
    if "QRegExp" in application_version.read_text(encoding="utf-8"):
        raise AssertionError("ApplicationVersion retained removed QRegExp API")

    script_manager = SOURCE_ROOT / "libraries" / "script-engine" / "src" / "ScriptManager.cpp"
    require_text(
        script_manager,
        r'QString\(modulePath\)\.replace\(\s*QRegularExpression\(QStringLiteral\("/\[\^/\]\*\$"\)\), QString\(\)\)',
        "CommonJS __dirname must still remove the final slash-delimited path component",
    )
    if 'QRegExp("/[^/]*$")' in script_manager.read_text(encoding="utf-8"):
        raise AssertionError("ScriptManager retained QRegExp in CommonJS __dirname derivation")
    script_manager_text = script_manager.read_text(encoding="utf-8")
    assert len(re.findall(
        r'qEnvironmentVariable\("EXTRA_ALLOWLIST"\)\.trimmed\(\)\.split\(\s*'
        r'QRegularExpression\(QStringLiteral\("\\\\s\*,\\\\s\*"\)\), Qt::SkipEmptyParts\)',
        script_manager_text,
    )) == 2, "both ScriptManager allowlist paths must preserve environment comma splitting"
    assert len(re.findall(
        r'raw\.toString\(\)\.trimmed\(\)\.split\(\s*'
        r'QRegularExpression\(QStringLiteral\("\\\\s\*\[,\\r\\n\]\+\\\\s\*"\)\), Qt::SkipEmptyParts\)',
        script_manager_text,
    )) == 2, "both ScriptManager allowlist paths must preserve settings comma/newline splitting"
    if "QRegExp" in script_manager_text:
        raise AssertionError("ScriptManager retained removed QRegExp API")

    gpu_ident = SOURCE_ROOT / "libraries" / "shared" / "src" / "GPUIdent.cpp"
    require_text(gpu_ident, r'#include <QtCore/QRegularExpression>', "GPU adapter matching must use the Qt 6 regex API")
    require_text(
        gpu_ident,
        r'QRegularExpression wordMatcher \{ QStringLiteral\("\\\\W"\) \};',
        "GPU adapter matching must retain its non-word-character split expression",
    )
    gpu_ident_text = gpu_ident.read_text(encoding="utf-8")
    assert "vendor.toUpper().split(wordMatcher)" in gpu_ident_text
    assert "renderer.toUpper().split(wordMatcher)" in gpu_ident_text
    assert 'words.removeAll("");' in gpu_ident_text and "words.removeDuplicates();" in gpu_ident_text
    if "QRegExp" in gpu_ident_text:
        raise AssertionError("GPUIdent retained removed QRegExp API")

    script_highlighting_header = SOURCE_ROOT / "interface" / "src" / "ScriptHighlighting.h"
    script_highlighting_source = SOURCE_ROOT / "interface" / "src" / "ScriptHighlighting.cpp"
    highlighting_header_text = script_highlighting_header.read_text(encoding="utf-8")
    highlighting_source_text = script_highlighting_source.read_text(encoding="utf-8")
    assert "#include <QRegularExpression>" in highlighting_header_text
    assert highlighting_header_text.count("QRegularExpression _") == 8, (
        "all eight script-highlighting expressions must use the Qt 6 regex type"
    )
    for legacy_api in ("QRegExp", "indexIn(", "matchedLength()"):
        if legacy_api in highlighting_header_text or legacy_api in highlighting_source_text:
            raise AssertionError(f"ScriptHighlighting retained removed regex API: {legacy_api}")
    assert highlighting_source_text.count("while (match.hasMatch())") == 4, (
        "keyword, quote, number, and boolean scanners must retain iterative matches"
    )
    assert "while (commentMatch.hasMatch())" in highlighting_source_text
    assert "const int length = match.capturedLength();" in highlighting_source_text
    assert "match = _keywordRegex.match(text, index + length);" in highlighting_source_text
    assert "match = _quotedTextRegex.match(text, index + length);" in highlighting_source_text
    assert "match = _numberRegex.match(text, index + length);" in highlighting_source_text
    assert "match = _truefalseRegex.match(text, index + length);" in highlighting_source_text
    assert "_alphacharRegex.match(text, index - 1).capturedStart() != (index - 1)" in highlighting_source_text
    assert "previousBlockState() != BlockStateInMultiComment" in highlighting_source_text
    assert "setCurrentBlockState(BlockStateInMultiComment);" in highlighting_source_text
    assert "quoted_index <= index && index <= (quoted_index + quoted_length)" in highlighting_source_text

    nitpick_cmake = SOURCE_ROOT / "tools" / "nitpick" / "CMakeLists.txt"
    nitpick_cmake_text = nitpick_cmake.read_text(encoding="utf-8")
    assert "overte_find_qt(COMPONENTS Widgets Core5Compat QUIET REQUIRED)" in nitpick_cmake_text
    assert "overte_qt_add_binary_resources(" in nitpick_cmake_text
    assert "overte_qt_wrap_ui(QT_UI_HEADERS" in nitpick_cmake_text
    for legacy_cmake_api in ("find_package(Qt5", "qt5_add_binary_resources", "qt5_wrap_ui"):
        if legacy_cmake_api in nitpick_cmake_text:
            raise AssertionError(f"nitpick retained direct Qt 5 CMake API: {legacy_cmake_api}")

    qt_compat = SOURCE_ROOT / "cmake" / "QtCompat.cmake"
    require_text(
        qt_compat,
        r'function\(overte_get_qt_target output_variable component\)\s+set\(_overte_qt_target "\$\{OVERTE_QT_TARGET_PREFIX\}\$\{component\}"\)',
        "Qt imported targets must be resolved through the selected major-version prefix",
    )
    require_text(
        qt_compat,
        r'if\(NOT TARGET "\$\{_overte_qt_target\}"\)\s+message\(FATAL_ERROR',
        "Qt target resolution must fail closed when the selected component is unavailable",
    )
    deploy_cmake = SOURCE_ROOT / "cmake" / "macros" / "PackageLibrariesForDeployment.cmake"
    require_text(deploy_cmake, r'overte_get_qt_target\(Qt_Core_Target Core\)', "Windows deployment must resolve Qt Core centrally")
    require_text(
        deploy_cmake,
        r'get_target_property\(Qt_Core_Location "\$\{Qt_Core_Target\}" LOCATION\)',
        "Windows deployment must retain its Qt binary-directory lookup",
    )
    if "Qt5::Core" in deploy_cmake.read_text(encoding="utf-8"):
        raise AssertionError("Windows deployment retained a direct Qt 5 imported target")

    require_text(
        qt_compat,
        r'function\(overte_qt_add_translation output_variable\)\s+if\(OVERTE_QT_MAJOR EQUAL 6\)\s+qt_add_translation\(\$\{output_variable\} \$\{ARGN\}\)\s+else\(\)\s+qt5_add_translation\(\$\{output_variable\} \$\{ARGN\}\)',
        "translation compilation must dispatch centrally for Qt 6 and Qt 5",
    )
    require_text(
        qt_compat,
        r'set\(\$\{output_variable\} "\$\{\$\{output_variable\}\}" PARENT_SCOPE\)',
        "Qt code-generation wrappers must return generated outputs to their callers",
    )
    linguist_macros = SOURCE_ROOT / "cmake" / "modules" / "FindQt5LinguistToolsMacros.cmake"
    require_text(
        linguist_macros,
        r'overte_qt_add_translation\(\$\{_qm_files\} \$\{_my_temptsfiles\}\)',
        "custom translation generation must compile temporary TS files through QtCompat",
    )
    if "qt5_add_translation" in linguist_macros.read_text(encoding="utf-8"):
        raise AssertionError("custom translation generation retained a direct Qt 5 command")

    installers_cmake = SOURCE_ROOT / "cmake" / "macros" / "GenerateInstallers.cmake"
    require_text(
        installers_cmake,
        r'overte_find_qt\(COMPONENTS Core QUIET REQUIRED\)\s+overte_get_qt_target\(Qt_qmake_Target qmake\)',
        "AppImage packaging must resolve qmake through the selected Qt major version",
    )
    require_text(
        installers_cmake,
        r'get_target_property\(Qt_qmake_Executable "\$\{Qt_qmake_Target\}" LOCATION\)',
        "AppImage packaging must retain its imported qmake executable lookup",
    )
    require_text(
        installers_cmake,
        r'set\(CPACK_QMAKE_EXECUTABLE \$\{Qt_qmake_Executable\}\)',
        "AppImage packaging must continue forwarding qmake into CPack",
    )
    installers_text = installers_cmake.read_text(encoding="utf-8")
    if "find_package(Qt5" in installers_text or "Qt5::qmake" in installers_text:
        raise AssertionError("installer generation retained direct Qt 5 qmake discovery")

    interface_cmake = SOURCE_ROOT / "interface" / "CMakeLists.txt"
    interface_cmake_text = interface_cmake.read_text(encoding="utf-8")
    assert "# overte_find_qt(COMPONENTS LinguistTools QUIET REQUIRED)" in interface_cmake_text
    assert "# OVERTE_CREATE_TRANSLATION_CUSTOM(${QM} ${INTERFACE_SRCS} ${QT_UI_FILES} ${TS})" in interface_cmake_text
    for legacy_cmake_api in ("find_package(Qt5", "qt5_create_translation_custom"):
        if legacy_cmake_api in interface_cmake_text:
            raise AssertionError(f"Interface translation recipe retained direct Qt 5 API: {legacy_cmake_api}")
    require_text(
        linguist_macros,
        r'function\(OVERTE_CREATE_TRANSLATION_CUSTOM _qm_files\)',
        "the dormant Interface translation recipe must name a Qt-major-neutral custom wrapper",
    )

    qt_launcher_cmake = SOURCE_ROOT / "launchers" / "qt" / "CMakeLists.txt"
    require_text(
        qt_launcher_cmake,
        r'if\(CMAKE_SYSTEM_NAME STREQUAL "iOS"\)\s+message\(FATAL_ERROR "The legacy qtlite launcher is desktop-only and cannot be configured for iOS"\)',
        "the legacy desktop qtlite launcher must fail closed outside the iOS graph",
    )
    assert 'include("${CMAKE_CURRENT_LIST_DIR}/../../cmake/QtCompat.cmake")' in qt_launcher_cmake.read_text(encoding="utf-8")
    assert "overte_find_qt(COMPONENTS Core Gui Qml Quick QuickControls2 Network REQUIRED)" in qt_launcher_cmake.read_text(encoding="utf-8")
    assert "overte_qt_add_resources(RES_SOURCES ${RESOURCES_QRC})" in qt_launcher_cmake.read_text(encoding="utf-8")
    assert "overte_link_qt_modules(${PROJECT_NAME} Core Quick QuickControls2 Qml Gui Network)" in qt_launcher_cmake.read_text(encoding="utf-8")
    qt_launcher_text = qt_launcher_cmake.read_text(encoding="utf-8")
    if "find_package(Qt5" in qt_launcher_text or "Qt5::" in qt_launcher_text:
        raise AssertionError("legacy desktop launcher retained direct Qt 5 package/target APIs")

    buffer_helpers = SOURCE_ROOT / "libraries" / "graphics" / "src" / "graphics" / "BufferViewHelpers.h"
    require_text(
        buffer_helpers,
        r"#if QT_VERSION >= QT_VERSION_CHECK\(6, 0, 0\)\s+const bool isMap = v\.metaType\(\)\.id\(\) == QMetaType::QVariantMap;",
        "model buffer conversion must use the Qt 6 metatype API",
    )
    require_text(
        buffer_helpers,
        r"#else\s+const bool isMap = v\.type\(\) == QVariant::Map;\s+#endif",
        "the Qt 6 metatype port must preserve the desktop Qt 5 branch",
    )

    model_renderer = SOURCE_ROOT / "libraries" / "entities-renderer" / "src" / "RenderableModelEntityItem.cpp"
    model_renderer_text = model_renderer.read_text(encoding="utf-8")
    assert "foreach" not in model_renderer_text, (
        "model render/collision handoff must compile with Qt 6 QT_NO_FOREACH"
    )
    require_text(
        model_renderer,
        r"for \(const HFMMesh& mesh : collisionGeometry\.meshes\) \{\s+// each meshPart is a convex hull\s+for \(const HFMMeshPart& meshPart : mesh\.parts\)",
        "compound-model traversal must preserve the nested mesh/part order",
    )

    touch_header = SOURCE_ROOT / "libraries" / "input-plugins" / "src" / "input-plugins" / "TouchscreenVirtualPadDevice.h"
    touch_source = touch_header.with_suffix(".cpp")
    require_text(touch_header, r"using OverteTouchPoint = QEventPoint;", "Qt 6 touch input must use QEventPoint")
    require_text(touch_header, r"using OverteTouchPoint = QTouchEvent::TouchPoint;", "Qt 5 touch input compatibility must remain")
    require_text(touch_source, r"return event->points\(\);", "Qt 6 touch events must expose their current points")
    require_text(touch_source, r"return point\.position\(\);", "Qt 6 touch coordinates must use QEventPoint position")
    require_text(touch_source, r"QInputDevice::DeviceType::TouchScreen", "iPad support must detect the Qt 6 touchscreen device type")

    application_header = SOURCE_ROOT / "interface" / "src" / "Application.h"
    application_source = application_header.with_suffix(".cpp")
    application_events = application_header.parent / "Application_Events.cpp"
    require_text(
        application_header,
        r"#if defined\(Q_OS_ANDROID\) \|\| defined\(Q_OS_IOS\) \|\| defined\(OVERTE_IOS\)\s+void beforeEnterBackground\(\);",
        "the production network/display lifecycle boundary must be available to iOS",
    )
    require_text(
        application_events,
        r"case Qt::ApplicationSuspended:\s+case Qt::ApplicationHidden:[\s\S]*?if \(_isForeground && !_aboutToQuit && _startUpFinished\) \{\s+beforeEnterBackground\(\);\s+enterBackground\(\);",
        "an actual iOS background transition must pause networking and the display plugin exactly once",
    )
    require_text(
        application_events,
        r"case Qt::ApplicationActive:[\s\S]*?if \(!_isForeground && !_aboutToQuit && _startUpFinished\) \{\s+enterForeground\(\);",
        "iOS foreground re-entry must reactivate the production display and network path",
    )
    require_text(
        application_source,
        r"auto displayPlugin = getActiveDisplayPlugin\(\);\s+if \(displayPlugin && displayPlugin->isActive\(\)\)",
        "backgrounding before display selection must not dereference a null plugin",
    )


def test_ci_contract() -> None:
    workflow = SOURCE_ROOT / ".github" / "workflows" / "ios-bootstrap.yml"
    require_text(workflow, r"runs-on: macos-26", "CI must use an Xcode 26 capable host")
    require_text(workflow, r"push:\s+branches:\s+- apple-ios", "iOS CI must run on the durable integration branch")
    require_text(workflow, r"runs-on: ubuntu-24\.04", "host contracts need an independent Linux gate")
    require_text(workflow, r"needs: host-contracts", "macOS CI must wait for host contracts")
    require_text(workflow, r"persist-credentials: false", "checkout credentials must not persist")
    require_text(workflow, r"simulator-smoke\.sh", "CI must launch both form factors")
    require_text(workflow, r"verify-app\.sh", "CI must inspect the produced bundle")
    require_text(workflow, r"unsigned-device-sdk:", "CI must compile against the physical-device SDK")
    require_text(workflow, r"package --platform device", "device SDK CI must build and package the arm64 device target")
    require_text(workflow, r"github\.run_number.*overte-ios-device-unsigned", "CI artifact names must start with the build number")
    require_text(workflow, r"Payload/OverteIOSBootstrap\.app/default\.metallib", "CI must inspect the IPA payload")
    require_text(workflow, r"org\.overte\.interface\.dev\s+\\\s+iphoneos", "device SDK CI must verify its platform metadata")

    verifier = IOS_ROOT / "ci" / "verify-app.sh"
    require_text(verifier, r'lipo "\$executable" -verify_arch arm64', "bundle verification must enforce arm64")
    require_text(verifier, r"QtWebEngine", "bundle verification must reject desktop WebEngine")
    require_text(verifier, r"verify-bundle-metadata\.py", "bundle metadata must be host-testable")

    integrated = SOURCE_ROOT / ".github" / "workflows" / "ios-integrated.yml"
    integrated_text = integrated.read_text(encoding="utf-8")
    require_text(integrated, r"^\s*workflow_dispatch:", "integrated CI must be manually dispatched")
    require_text(integrated, r"^\s*workflow_call:", "integrated CI must be callable after Qt provisioning")
    if re.search(r"^\s*(push|pull_request|schedule):", integrated_text, re.MULTILINE):
        raise AssertionError("experimental integrated CI must not run automatically")
    require_text(integrated, r"qt_host_cache_key:", "integrated CI must require an explicit Qt host cache")
    require_text(integrated, r"qt_ios_cache_key:", "integrated CI must require an explicit Qt iOS cache")
    require_text(integrated, r"path: \$\{\{ github\.workspace \}\}/build-ios/qt-install/qt/macos", "consumer must restore host tools with the producer's absolute path form")
    require_text(integrated, r"path: \$\{\{ github\.workspace \}\}/build-ios/qt-install/qt/ios", "consumer must restore target Qt with the producer's absolute path form")
    require_text(integrated, r"fail-on-cache-miss: true", "Qt restoration must fail closed")
    require_text(integrated, r"runs-on: ubuntu-24\.04", "integrated CI needs Linux host contracts")
    require_text(integrated, r"runs-on: macos-26", "integrated CI must use an Xcode 26 host")
    require_text(integrated, r"defaults:\n\s+run:\n(?:\s+#.*\n){0,3}\s+shell: bash", "integrated diagnostics pipelines must run with pipefail")
    require_text(integrated, r"CONAN_HOME: \$\{\{ github\.workspace \}\}/build-ios/conan-home", "Conan state must be isolated inside the workspace")
    require_text(integrated, r"Select deterministic Conan package cache key", "integrated CI must key its validated dependency checkpoint")
    require_text(integrated, r"Restore validated Conan package cache", "integrated CI must reuse validated dependency packages")
    require_text(integrated, r"Save validated Conan package cache", "integrated CI must save dependencies immediately after graph validation")
    require_text(integrated, r"timeout-minutes: 180", "the first full-client Xcode build needs a non-truncating timeout")
    require_text(integrated, r"needs: host-contracts", "macOS integration must wait for host contracts")
    require_text(integrated, r"persist-credentials: false", "checkout credentials must not persist")
    require_text(integrated, r"doctor --platform device --require-qt", "toolchain stage must validate Xcode and Qt")
    require_text(integrated, r"deps --platform device --graphics-toolchain", "dependency stage must resolve the device graph")
    require_text(integrated, r"configure --platform device --client-graph", "configure stage must select the full client graph")
    require_text(integrated, r"cmake --build build-ios/device --config Release.*--target Overte", "integrated CI must build the real client target with the Conan dependency configuration")
    require_text(integrated, r"--parallel.*sysctl -n hw\.logicalcpu", "integrated Xcode build must use all runner CPUs")
    require_text(integrated, r"package-client --platform device --configuration Release", "integrated CI must package the matching Release client IPA")
    require_text(integrated, r"LATEST-OverteIOSClient\.json", "integrated CI must upload VM transfer metadata")
    require_text(integrated, r"check-release-readiness\.py build-ios/artifacts", "integrated CI must run the read-only readiness aggregator")
    require_text(integrated, r'deviceAccepted"\) is not False', "CI must reject an unsupported device-acceptance claim")
    require_text(integrated, r"device-unsigned-readiness\.json", "CI must upload the numbered build-readiness report")
    require_text(integrated, r"expected exactly one numbered integrated-client manifest", "CI readiness must select an unambiguous numbered manifest")
    require_text(integrated, r"sanitize-ci-log\.py", "integrated failure logs must be redacted before upload")
    require_text(integrated, r"ci-upload-diagnostics/", "diagnostic upload must use only the sanitized directory")
    require_text(integrated, r"github\.run_number.*ios-integrated-failure-diagnostics", "failure diagnostics must be numbered")
    if "build-ios/device/CMakeCache.txt" in integrated.read_text(encoding="utf-8"):
        raise AssertionError("integrated CI must not upload a potentially sensitive CMake cache")

    qt_source = SOURCE_ROOT / ".github" / "workflows" / "ios-qt-source.yml"
    require_text(qt_source, r"concurrency:\s+group: ios-qt-source-macos26-arm64", "Qt source cache writers must serialize across branches sharing keys")
    require_text(qt_source, r"cancel-in-progress: false", "an expensive Qt source cache build must not be cancelled by a duplicate dispatch")
    require_text(qt_source, r"workflow_call:[\s\S]*?qt_host_cache_key:[\s\S]*?qt_ios_cache_key:", "reusable Qt workflow must expose both component keys")
    require_text(qt_source, r"qt_host_cache_key:.*steps\.cache-key\.outputs\.host", "host output must originate from the deterministic key step")
    require_text(qt_source, r"qt_ios_cache_key:.*steps\.cache-key\.outputs\.ios", "iOS output must originate from the deterministic key step")
    require_text(qt_source, r"--stage source", "Qt provisioning must checkpoint the verified source archive")
    require_text(qt_source, r"--stage host", "Qt provisioning must build the host as an independent checkpoint")
    require_text(qt_source, r"Save validated Qt host tools immediately", "host Qt must survive a later target failure")
    require_text(qt_source, r'host_plan_hash="f7a0f4a6a8d51a462a14c9b51e1595338d023f4fd06a0a134aeadbf07a9bce18"', "target-only fixes must retain the validated host cache key")
    require_text(qt_source, r'ios_plan_hash=.*build-qt-ios-from-source\.sh', "target cache key must change with iOS configure policy")
    require_text(qt_source, r"--stage ios", "Qt provisioning must build the iOS target independently")
    require_text(qt_source, r"Save compiler recovery cache after a build failure", "failed compiles must retain reusable compiler outputs without duplicating every successful run")
    require_text(qt_source, r"if: failure\(\) && steps\.sccache\.outcome == 'success'", "compiler recovery must only create a new generation after a failed build")
    require_text(qt_source, r"restore-keys:[\s\S]*?sccache_prefix", "the next run must restore the latest compatible compiler cache")

    bootstrap_workflow = SOURCE_ROOT / ".github" / "workflows" / "ios-bootstrap.yml"
    require_text(bootstrap_workflow, r"needs\.provision-qt-ios\.outputs\.qt_host_cache_key", "host cache output must reach the integrated caller")
    require_text(bootstrap_workflow, r"needs\.provision-qt-ios\.outputs\.qt_ios_cache_key", "iOS cache output must reach the integrated caller")
    require_text(bootstrap_workflow, r"contains\(github\.event\.head_commit\.message, '\[ios-integrated\]'\)", "integrated-only fixes must be able to reuse provisioned Qt caches")
    require_text(bootstrap_workflow, r"simulator:[\s\S]*!contains\(github\.event\.head_commit\.message, '\[ios-integrated\]'\)", "integrated-only retries must skip the independent simulator gate")
    require_text(bootstrap_workflow, r"unsigned-device-sdk:[\s\S]*!contains\(github\.event\.head_commit\.message, '\[ios-integrated\]'\)", "integrated-only retries must skip the independent device SDK gate")
    if bootstrap_workflow.read_text(encoding="utf-8").count("ios/tests/run-tests.sh") != 1:
        raise AssertionError("branch CI must run the host suite exactly once before macOS jobs")

    bash32_forbidden = re.compile(r"\b(?:mapfile|readarray)\b|declare\s+-A|local\s+-A|\$\{[^}\n]+(?:,,|\^\^)")
    for shell_path in (
        IOS_ROOT / "build-ios.sh",
        IOS_ROOT / "ci" / "verify-app.sh",
        IOS_ROOT / "tools" / "prepare-qt-ios.sh",
        IOS_ROOT / "tools" / "build-qt-ios-from-source.sh",
    ):
        if bash32_forbidden.search(shell_path.read_text(encoding="utf-8")):
            raise AssertionError(f"Bash 4-only syntax entered macOS workflow path: {shell_path}")
    for forbidden in ("QT_ACCOUNT", "QT_PASSWORD", "aqtinstall", "download.qt.io"):
        if forbidden in integrated_text:
            raise AssertionError(f"integrated CI must not invent Qt acquisition credentials: {forbidden}")

    qt_source = SOURCE_ROOT / ".github" / "workflows" / "ios-qt-source.yml"
    qt_source_text = qt_source.read_text(encoding="utf-8")
    require_text(qt_source, r"^\s*workflow_dispatch:", "Qt source provisioning must be manually dispatched")
    require_text(qt_source, r"^\s*workflow_call:", "Qt source provisioning must be reusable from the branch workflow")
    require_text(qt_source, r"outputs:\s+qt_host_cache_key:", "Qt provisioning must expose its deterministic host key")
    require_text(qt_source, r"qt_ios_cache_key:", "Qt provisioning must expose its deterministic iOS key")
    require_text(qt_source, r"value:.*jobs\.qt-ios-source\.outputs\.qt_host_cache_key", "reusable host output must come from the successful provision job")
    require_text(qt_source, r"value:.*jobs\.qt-ios-source\.outputs\.qt_ios_cache_key", "reusable iOS output must come from the successful provision job")
    if re.search(r"^\s*(push|pull_request|schedule):", qt_source_text, re.MULTILINE):
        raise AssertionError("expensive Qt source provisioning must not run automatically")
    require_text(qt_source, r"runs-on: macos-26", "Qt iOS must be built on the Xcode runner")
    require_text(qt_source, r"build-qt-ios-from-source\.sh", "Qt provisioning must use the audited source-build script")
    require_text(qt_source, r"actions/cache/save@[0-9a-f]{40}", "Qt cache writes must use an immutable action revision")
    for forbidden in ("accept-license", "QT_ACCOUNT", "QT_PASSWORD", "upload-artifact"):
        if forbidden in qt_source_text:
            raise AssertionError(f"Qt source workflow contains forbidden acquisition behavior: {forbidden}")
    require_text(workflow, r"contains\(github\.event\.head_commit\.message, '\[qt-source\]'\)", "branch CI must require an explicit Qt source opt-in")
    require_text(workflow, r"uses: \./\.github/workflows/ios-qt-source\.yml", "branch CI must call the audited Qt provisioner")
    require_text(workflow, r"needs: provision-qt-ios", "integrated configure must wait for successful Qt provisioning")
    require_text(workflow, r"uses: \./\.github/workflows/ios-integrated\.yml", "opt-in branch CI must call the integrated configure gate")
    require_text(workflow, r"qt_host_cache_key:.*needs\.provision-qt-ios\.outputs\.qt_host_cache_key", "the host cache key must feed the integrated gate")
    require_text(workflow, r"qt_ios_cache_key:.*needs\.provision-qt-ios\.outputs\.qt_ios_cache_key", "the target cache key must feed the integrated gate")
    require_text(verifier, r"default\.metallib", "bundle verification must require compiled Metal shaders")

    ios_cmake = IOS_ROOT / "CMakeLists.txt"
    require_text(ios_cmake, r"air64-apple-ios", "Metal compilation must target iOS AIR")
    require_text(ios_cmake, r"--sdk.*OVERTE_IOS_SDK_NAME", "Metal compilation must use the selected Xcode SDK")
    require_text(ios_cmake, r"\$<CONFIG>-\$\{OVERTE_IOS_SDK_NAME\}/OverteIOSBootstrap\.app", "compiled Metal shaders must use the flat iOS app path")

    smoke = IOS_ROOT / "ci" / "simulator-smoke.sh"
    require_text(smoke, r"for family in iphone ipad", "smoke tier must cover iPhone and iPad")
    require_text(smoke, r"select-simulator\.py", "simulator choice must use the tested selector")
    require_text(smoke, r"simctl io.*screenshot", "simulator failures must preserve a screenshot")
    require_text(smoke, r"log show", "simulator failures must preserve app logs")
    require_text(smoke, r"run-with-timeout\.py", "every simulator command needs a portable timeout boundary")
    require_text(smoke, r"wait for \$family boot.*360", "simulator boot must have a bounded six-minute wait")
    require_text(smoke, r"shutdown iphone.*&[\s\S]*shutdown ipad.*&", "independent simulator shutdowns should overlap")
    require_text(smoke, r"START.*timeout=[\s\S]*END.*elapsed", "simulator phases must expose timing evidence")
    require_text(smoke, r'simctl openurl.*hifi://overte_hub', "simulator smoke must exercise Overte deep links")
    require_text(smoke, r"OVERTE_IOS_SIMULATOR_GRACE_SECONDS:-5", "simulator smoke must allow startup failures to surface")
    require_text(
        smoke,
        r'simctl terminate "\$active_udid" "\$bundle_id"',
        "simulator smoke must prove launch survival by terminating the running app",
    )

    selector = load_python_module(IOS_ROOT / "tools" / "select-simulator.py", "select_simulator")
    fixture = {
        "devices": {
            "com.apple.CoreSimulator.SimRuntime.iOS-9-3": [
                {"name": "iPhone Legacy", "udid": "old-phone", "isAvailable": True},
            ],
            "com.apple.CoreSimulator.SimRuntime.iOS-26-0": [
                {"name": "iPhone Z", "udid": "new-phone-z", "isAvailable": True},
                {"name": "iPhone A", "udid": "new-phone-a", "isAvailable": True},
                {"name": "iPad Pro", "udid": "new-tablet", "isAvailable": True},
            ],
            "com.apple.CoreSimulator.SimRuntime.tvOS-26-0": [
                {"name": "iPhone impostor", "udid": "wrong-platform", "isAvailable": True},
            ],
        }
    }
    assert selector.select_device(fixture, "iphone") == "new-phone-a"
    assert selector.select_device(fixture, "ipad") == "new-tablet"
    fixture["devices"]["com.apple.CoreSimulator.SimRuntime.iOS-26-0"][1]["isAvailable"] = False
    assert selector.select_device(fixture, "iphone") == "new-phone-z"
    try:
        selector.select_device({"devices": {"malformed-runtime": []}}, "iphone")
    except LookupError as error:
        assert "no available iphone simulator" in str(error)
    else:
        raise AssertionError("missing iPhone simulator was accepted")
    try:
        selector.select_device({"devices": []}, "ipad")
    except (AttributeError, TypeError):
        pass
    else:
        raise AssertionError("malformed simulator payload was accepted")


def test_device_acceptance_contract() -> None:
    matrix_path = IOS_ROOT / "tests" / "device-acceptance.json"
    matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
    assert matrix["schemaVersion"] == 1
    assert set(matrix["requiredFormFactors"]) == {"iphone", "ipad"}
    cases = matrix["cases"]
    ids = [case["id"] for case in cases]
    assert len(ids) == len(set(ids)), "device acceptance IDs must be unique"
    assert all(case["deviceOnly"] is True for case in cases)
    required_categories = {
        "lifecycle", "network", "graphics", "input", "audio", "layout",
        "performance", "scripting", "privacy", "accessibility",
    }
    assert required_categories <= {case["category"] for case in cases}
    bootstrap = (IOS_ROOT / "src" / "BootstrapViewController.mm").read_text(encoding="utf-8")
    for contract in (
        "adjustsFontForContentSizeCategory",
        "UIAccessibilityReduceMotionStatusDidChangeNotification",
        "UIHoverGestureRecognizer",
        "viewWillTransitionToSize",
    ):
        assert contract in bootstrap, f"bootstrap missing accessibility/iPad contract: {contract}"

    signing = SOURCE_ROOT / "docs" / "ios" / "SIGNING_AND_DEVICE_TESTS.md"
    require_text(signing, r"script never\s+installs", "device installation must require a separate action")
    require_text(signing, r"separate externally approved release action", "App Store upload must stay external")
    result_schema = IOS_ROOT / "tests" / "device-result.schema.json"
    schema = json.loads(result_schema.read_text(encoding="utf-8"))
    assert schema["$schema"].endswith("2020-12/schema")
    assert set(schema["properties"]["formFactor"]["enum"]) == {"iphone", "ipad"}
    require_text(signing, r"validate-device-results\.py", "device evidence needs an offline validator")
    privacy_doc = SOURCE_ROOT / "docs" / "ios" / "PRIVACY.md"
    require_text(privacy_doc, r"Xcode's\s+privacy report", "release gate must include Xcode privacy aggregation")
    require_text(privacy_doc, r"runtime network\s+trace", "collected-data review must use runtime evidence")
    evidence_tool = IOS_ROOT / "tools" / "prepare-entity-evidence.py"
    require_text(evidence_tool, r'"containsRawDeviceLog": False', "entity handoff must exclude raw device logs")
    require_text(evidence_tool, r"rawLogSha256", "entity handoff must retain raw-log provenance")
    require_text(evidence_tool, r"make_archive", "entity handoff must create a portable offline ZIP")
    readiness_tool = IOS_ROOT / "tools" / "check-release-readiness.py"
    require_text(readiness_tool, r'"buildReady": True', "readiness must report a verified build separately")
    require_text(readiness_tool, r'"deviceAccepted": device_accepted', "readiness must not equate build and device acceptance")
    require_text(readiness_tool, r"bundle SHA-256 differs", "device evidence must bind to the exact artifact")


def test_integration_readiness_contract() -> None:
    path = IOS_ROOT / "integration-readiness.json"
    readiness = json.loads(path.read_text(encoding="utf-8"))
    assert readiness["schemaVersion"] == 1
    assert readiness["supportedDefaultGraph"] == "bootstrap"
    gates = readiness["gates"]
    gate_ids = [gate["id"] for gate in gates]
    assert len(gate_ids) == len(set(gate_ids)) and len(gates) >= 10
    required_areas = {
        "audio", "automation", "build-system", "dependencies", "distribution",
        "plugins", "rendering", "scripting", "shared-client", "user-interface", "web",
    }
    assert required_areas <= {gate["area"] for gate in gates}
    for gate in gates:
        assert gate["status"] in {"complete", "prepared", "external-validation"}
        assert isinstance(gate["requiresMac"], bool)
        assert isinstance(gate["requiresDevice"], bool)
        assert gate["evidence"]
        for evidence in gate["evidence"]:
            assert not evidence.startswith("/") and ".." not in Path(evidence).parts
            assert (SOURCE_ROOT / evidence).exists(), (gate["id"], evidence)
        if gate["status"] != "complete":
            assert gate["remainingAction"] != "none"

    debt = IOS_ROOT / "compatibility-debt.json"
    require_text(debt, r"qt6-removed-audio-api", "Qt 6 source debt must be inventoried")
    require_text(debt, r"dynamic-plugin-packaging", "static plug-in debt must be inventoried")


def test_script_entity_id_qt6_contract() -> None:
    script_values = SOURCE_ROOT / "libraries" / "script-engine" / "src" / "ScriptValueUtils.cpp"
    require_text(
        script_values,
        r"EntityItemID\s+fromString\s*\{\s*QUuid\s*\(\s*uuidAsString\s*\)\s*\}\s*;",
        "Qt 6 must parse script UUID strings explicitly before constructing EntityItemID",
    )

    v8_proxy = SOURCE_ROOT / "libraries" / "script-engine" / "src" / "v8" / "ScriptObjectV8Proxy.cpp"
    require_text(v8_proxy, r"QVariant\s*\(\s*QMetaType\s*\(\s*typeId\s*\)",
                 "Qt 6 dynamic variants must use QMetaType objects")
    require_text(v8_proxy, r'QGenericArgument\s*\(\s*"ScriptValue"',
                 "stored script invocation arguments must remain QGenericArgument values")
    require_text(v8_proxy, r'QGenericArgument\s*\(\s*"QVariant"',
                 "stored QVariant invocation arguments must remain QGenericArgument values")
    require_text(v8_proxy, r'qScriptArgLists\[i\]\.reserve\(numArgs\)',
                 "stored script argument addresses must survive list population")
    require_text(v8_proxy, r'qVarArgLists\[i\]\.reserve\(numArgs\)',
                 "stored QVariant argument addresses must survive list population")

    script_message = SOURCE_ROOT / "libraries" / "script-engine" / "src" / "ScriptMessage.cpp"
    require_text(script_message, r'_fileName\s*=\s*object\["fileName"\]\.toString\(\)',
                 "script message file names must remain strings")


def main() -> None:
    tests = (
        test_versions,
        test_profiles,
        test_dependency_inventory,
        test_plists,
        test_assets,
        test_cmake_boundary,
        test_scope_contract,
        test_ci_contract,
        test_device_acceptance_contract,
        test_integration_readiness_contract,
        test_script_entity_id_qt6_contract,
    )
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"PASS {len(tests)} iOS host contract tests")


if __name__ == "__main__":
    main()
