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
    assert info["UIRequiredDeviceCapabilities"] == ["arm64"]
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
    require_text(cmake, r'XCODE_ATTRIBUTE_CLANG_ENABLE_OBJC_ARC "YES"', "Objective-C ARC must be target-local")
    require_text(cmake, r"AUTOMOC OFF", "native bootstrap must not inherit Qt AUTOGEN")
    require_text(cmake, r'"-framework CoreGraphics"', "UIKit geometry symbols need an explicit framework")
    require_text(cmake, r'"-framework Metal"', "bootstrap must link Metal")
    require_text(cmake, r'"-framework AVFoundation"', "bootstrap must link AVFoundation")

    qt_compat = SOURCE_ROOT / "cmake" / "QtCompat.cmake"
    require_text(qt_compat, r"OVERTE_QT_MAJOR", "Qt major selection must be centralized")
    require_text(qt_compat, r"overte_find_qt", "Qt package lookup needs a version-neutral helper")
    require_text(qt_compat, r"overte_link_qt_modules", "Qt target linking needs a version-neutral helper")
    require_text(qt_compat, r"overte_qt_add_resources", "Qt resources need a version-neutral helper")

    root_cmake = SOURCE_ROOT / "CMakeLists.txt"
    require_text(root_cmake, r"ANDROID OR UWP OR IOS", "iOS must use the mobile build policy")
    require_text(root_cmake, r"OVERTE_IOS_BOOTSTRAP_ONLY", "root CMake must default to the audited iOS graph")
    require_text(root_cmake, r"add_subdirectory\(ios\)", "root CMake must expose the iOS bootstrap")
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
    require_text(platform_probe, r"create:YES", "bootstrap must create its application support directory")
    app_delegate = IOS_ROOT / "src" / "AppDelegate.mm"
    require_text(app_delegate, r"AVAudioSessionInterruptionNotification", "audio must observe interruptions")
    require_text(app_delegate, r"AVAudioSessionRouteChangeNotification", "audio must observe route changes")
    require_text(app_delegate, r"applicationDidReceiveMemoryWarning", "lifecycle must observe memory pressure")
    require_text(app_delegate, r"LifecycleStateMachine", "application lifecycle must feed a tested state model")
    require_text(app_delegate, r"UIWindowSceneSessionRoleApplication", "scene configuration must use the current UIKit role")
    require_text(app_delegate, r"AVAudioSessionCategoryOptionAllowBluetoothHFP", "audio session must use the current Bluetooth option")
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


def test_ci_contract() -> None:
    workflow = SOURCE_ROOT / ".github" / "workflows" / "ios-bootstrap.yml"
    require_text(workflow, r"runs-on: macos-26", "CI must use an Xcode 26 capable host")
    require_text(workflow, r"push:\s+branches:\s+- feature/ios-support", "fork CI must run without changing its default branch")
    require_text(workflow, r"runs-on: ubuntu-24\.04", "host contracts need an independent Linux gate")
    require_text(workflow, r"needs: host-contracts", "macOS CI must wait for host contracts")
    require_text(workflow, r"persist-credentials: false", "checkout credentials must not persist")
    require_text(workflow, r"simulator-smoke\.sh", "CI must launch both form factors")
    require_text(workflow, r"verify-app\.sh", "CI must inspect the produced bundle")

    verifier = IOS_ROOT / "ci" / "verify-app.sh"
    require_text(verifier, r'lipo "\$executable" -verify_arch arm64', "bundle verification must enforce arm64")
    require_text(verifier, r"QtWebEngine", "bundle verification must reject desktop WebEngine")
    require_text(verifier, r"verify-bundle-metadata\.py", "bundle metadata must be host-testable")

    smoke = IOS_ROOT / "ci" / "simulator-smoke.sh"
    require_text(smoke, r"for family in iphone ipad", "smoke tier must cover iPhone and iPad")
    require_text(smoke, r"select-simulator\.py", "simulator choice must use the tested selector")
    require_text(smoke, r"simctl io.*screenshot", "simulator failures must preserve a screenshot")
    require_text(smoke, r"log show", "simulator failures must preserve app logs")

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
    )
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"PASS {len(tests)} iOS host contract tests")


if __name__ == "__main__":
    main()
