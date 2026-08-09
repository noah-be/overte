#!/usr/bin/env python3
"""Device-free contract tests for the Overte iOS bootstrap boundary."""

# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
import plistlib
import re
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


def test_versions() -> None:
    versions = parse_versions()
    assert versions["OVERTE_IOS_MIN_VERSION"] == "17.0"
    assert int(versions["OVERTE_IOS_REQUIRED_SDK_MAJOR"]) >= 26
    assert int(versions["OVERTE_IOS_REQUIRED_XCODE_MAJOR"]) >= 26
    assert tuple(map(int, versions["OVERTE_IOS_QT_MIN_VERSION"].split("."))) >= (6, 11, 0)


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

    recipe = IOS_ROOT / "conanfile.py"
    require_text(recipe, r'package_type = "application"', "staged graph must not publish a library")
    require_text(recipe, r'str\(self\.settings\.os\) != "iOS"', "staged graph must reject non-iOS hosts")
    for forbidden in ("steamworks", "discord-rpc", "openvr", "openxr", "sdl"):
        if re.search(rf'self\.requires\("{re.escape(forbidden)}/', recipe.read_text(encoding="utf-8")):
            raise AssertionError(f"desktop-only dependency entered iOS graph: {forbidden}")
    require_text(recipe, r'self\.tool_requires\("scribe/', "shader generator must run in the build context")
    require_text(recipe, r'self\.tool_requires\("spirv-cross/', "SPIR-V conversion must run in the build context")


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
    assert info["NSAppTransportSecurity"] == {"NSAllowsLocalNetworking": True}
    assert info["UIApplicationSceneManifest"]["UIApplicationSupportsMultipleScenes"] is False
    url_schemes = info["CFBundleURLTypes"][0]["CFBundleURLSchemes"]
    assert set(url_schemes) == {"overte", "hifi"}
    assert set(info["UISupportedInterfaceOrientations~ipad"]) >= {
        "UIInterfaceOrientationPortrait",
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
    cmake = IOS_ROOT / "CMakeLists.txt"
    require_text(cmake, r'CMAKE_SYSTEM_NAME STREQUAL "iOS"', "CMake must reject non-iOS targets")
    require_text(cmake, r'XCODE_ATTRIBUTE_TARGETED_DEVICE_FAMILY "1,2"', "bundle must support iPhone and iPad")
    require_text(cmake, r'XCODE_ATTRIBUTE_CODE_SIGNING_ALLOWED "NO"', "unsigned builds must be explicit")
    require_text(cmake, r'"-framework Metal"', "bootstrap must link Metal")
    require_text(cmake, r'"-framework AVFoundation"', "bootstrap must link AVFoundation")

    qt_compat = SOURCE_ROOT / "cmake" / "QtCompat.cmake"
    require_text(qt_compat, r"OVERTE_QT_MAJOR", "Qt major selection must be centralized")
    require_text(qt_compat, r"overte_find_qt", "Qt package lookup needs a version-neutral helper")
    require_text(qt_compat, r"overte_link_qt_modules", "Qt target linking needs a version-neutral helper")

    root_cmake = SOURCE_ROOT / "CMakeLists.txt"
    require_text(root_cmake, r"ANDROID OR UWP OR IOS", "iOS must use the mobile build policy")
    require_text(root_cmake, r"set\(PLATFORM_QT_COMPONENTS WebView Xml Core5Compat\)", "iOS must select WebView and transitional Core5Compat")

    file_utils = SOURCE_ROOT / "libraries" / "shared" / "src" / "shared" / "FileUtils.cpp"
    require_text(file_utils, r'extraSelectors << "ios" << "mobile" << "touch"', "iOS selectors must include mobile touch variants")
    require_text(file_utils, r'<< "android_phoneInterface" << "android_interface"', "iOS must inherit the tested Phone presentation")

    ios_webview = SOURCE_ROOT / "interface" / "resources" / "qml" / "controls" / "+ios" / "FlickableWebViewCore.qml"
    require_text(ios_webview, r"import QtWebView 1\.1", "iOS web surfaces must use Qt WebView")
    if "QtWebEngine" in ios_webview.read_text(encoding="utf-8"):
        raise AssertionError("iOS web surface must not import Qt WebEngine")

    moltenvk = SOURCE_ROOT / "cmake" / "modules" / "FindMoltenVK.cmake"
    require_text(moltenvk, r"ios-arm64_x86_64-simulator", "MoltenVK lookup must support arm64 simulator")
    require_text(moltenvk, r"ios-arm64", "MoltenVK lookup must support arm64 devices")
    require_text(moltenvk, r"NO_DEFAULT_PATH", "MoltenVK must not be found incidentally")

    metal_shader = IOS_ROOT / "src" / "BootstrapShaders.metal"
    require_text(metal_shader, r"overteBootstrapVertex", "Metal probe needs a compiled vertex function")
    require_text(metal_shader, r"overteBootstrapFragment", "Metal probe needs a compiled fragment function")
    bootstrap_view = IOS_ROOT / "src" / "BootstrapViewController.mm"
    require_text(bootstrap_view, r"UIPanGestureRecognizer", "bootstrap must exercise continuous touch input")
    require_text(bootstrap_view, r"UIUserInterfaceIdiomPad", "bootstrap must distinguish iPad layout")
    require_text(bootstrap_view, r"safeAreaLayoutGuide", "bootstrap controls must respect safe areas")
    platform_probe = IOS_ROOT / "src" / "PlatformProbe.mm"
    require_text(platform_probe, r"nw_path_monitor_create", "bootstrap must exercise network reachability")
    require_text(platform_probe, r"CMMotionManager", "bootstrap must detect motion capability")
    require_text(platform_probe, r"NSApplicationSupportDirectory", "bootstrap must use an app container path")
    app_delegate = IOS_ROOT / "src" / "AppDelegate.mm"
    require_text(app_delegate, r"AVAudioSessionInterruptionNotification", "audio must observe interruptions")
    require_text(app_delegate, r"AVAudioSessionRouteChangeNotification", "audio must observe route changes")
    require_text(app_delegate, r"applicationDidReceiveMemoryWarning", "lifecycle must observe memory pressure")
    scene_delegate = IOS_ROOT / "src" / "SceneDelegate.mm"
    require_text(scene_delegate, r"allowedSchemes", "deep links must use an explicit scheme allowlist")
    if "Accepted deep link with scheme %{public}@\", url" in scene_delegate.read_text(encoding="utf-8"):
        raise AssertionError("deep-link logs must not expose the complete URL")
    rendering_spike = SOURCE_ROOT / "docs" / "ios" / "RENDERING_SPIKE.md"
    require_text(rendering_spike, r"15 percent", "rendering decision needs a performance threshold")
    require_text(rendering_spike, r"30-minute", "rendering decision needs a stability threshold")


def test_scope_contract() -> None:
    scope = SOURCE_ROOT / "docs" / "ios" / "PORT_SCOPE.md"
    architecture = SOURCE_ROOT / "docs" / "ios" / "ARCHITECTURE.md"
    dependency_policy = SOURCE_ROOT / "docs" / "ios" / "DEPENDENCY_POLICY.md"
    qt_setup = SOURCE_ROOT / "docs" / "ios" / "QT_SETUP.md"
    for path in (scope, architecture, dependency_policy, qt_setup):
        assert path.is_file() and path.stat().st_size > 500, path
    require_text(scope, r"First usable client", "scope needs a product acceptance target")
    require_text(architecture, r"non-JIT", "architecture must address executable-memory policy")
    require_text(dependency_policy, r"Steamworks.*disabled|disabled.*Steamworks", "desktop-only dependencies must be classified")
    require_text(qt_setup, r"OVERTE_IOS_QT_ROOT", "Qt setup must define its explicit target root")

    scripting = SOURCE_ROOT / "docs" / "ios" / "SCRIPTING.md"
    require_text(scripting, r"--jitless", "iOS scripting must enforce non-JIT execution")
    require_text(scripting, r"OVERTE_IOS_V8_ROOT", "iOS V8 package must use an explicit root")

    script_engine = SOURCE_ROOT / "libraries" / "script-engine" / "src" / "v8" / "ScriptEngineV8.cpp"
    require_text(script_engine, r'--stack-size=256 --jitless --no-expose-wasm', "iOS V8 flags must fail closed")
    qt6_migration = SOURCE_ROOT / "docs" / "ios" / "QT6_MIGRATION.md"
    require_text(qt6_migration, r"QAudioDeviceInfo/QAudioInput/QAudioOutput", "Qt 6 audio boundary must be explicit")
    require_text(qt6_migration, r"must not enter the iOS target", "desktop-only Qt paths must be excluded")


def test_ci_contract() -> None:
    workflow = SOURCE_ROOT / ".github" / "workflows" / "ios-bootstrap.yml"
    require_text(workflow, r"runs-on: macos-26", "CI must use an Xcode 26 capable host")
    require_text(workflow, r"persist-credentials: false", "checkout credentials must not persist")
    require_text(workflow, r"simulator-smoke\.sh", "CI must launch both form factors")
    require_text(workflow, r"verify-app\.sh", "CI must inspect the produced bundle")

    verifier = IOS_ROOT / "ci" / "verify-app.sh"
    require_text(verifier, r"lipo -verify_arch arm64", "bundle verification must enforce arm64")
    require_text(verifier, r"QtWebEngine", "bundle verification must reject desktop WebEngine")

    smoke = IOS_ROOT / "ci" / "simulator-smoke.sh"
    require_text(smoke, r"for family in iphone ipad", "smoke tier must cover iPhone and iPad")


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
        "performance", "scripting", "privacy",
    }
    assert required_categories <= {case["category"] for case in cases}

    signing = SOURCE_ROOT / "docs" / "ios" / "SIGNING_AND_DEVICE_TESTS.md"
    require_text(signing, r"script never\s+installs", "device installation must require a separate action")
    require_text(signing, r"separate externally approved release action", "App Store upload must stay external")
    privacy_doc = SOURCE_ROOT / "docs" / "ios" / "PRIVACY.md"
    require_text(privacy_doc, r"Xcode's\s+privacy report", "release gate must include Xcode privacy aggregation")
    require_text(privacy_doc, r"runtime network\s+trace", "collected-data review must use runtime evidence")


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
    )
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"PASS {len(tests)} iOS host contract tests")


if __name__ == "__main__":
    main()
