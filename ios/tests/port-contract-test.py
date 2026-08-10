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
    require_text(root_cmake, r"set\(PLATFORM_QT_COMPONENTS WebView Xml Core5Compat\)", "iOS must select WebView and transitional Core5Compat")

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
    if "QtWebEngine" in ios_webview.read_text(encoding="utf-8"):
        raise AssertionError("iOS web surface must not import Qt WebEngine")

    moltenvk = SOURCE_ROOT / "cmake" / "modules" / "FindMoltenVK.cmake"
    require_text(moltenvk, r"ios-arm64_x86_64-simulator", "MoltenVK lookup must support arm64 simulator")
    require_text(moltenvk, r"ios-arm64", "MoltenVK lookup must support arm64 devices")
    require_text(moltenvk, r"NO_DEFAULT_PATH", "MoltenVK must not be found incidentally")

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
    require_text(workflow, r"push:\s+branches:\s+- feature/ios-support", "fork CI must run without changing its default branch")
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
    require_text(integrated, r"qt_cache_key:", "integrated CI must require an explicit Qt cache")
    require_text(integrated, r"fail-on-cache-miss: true", "Qt restoration must fail closed")
    require_text(integrated, r"runs-on: ubuntu-24\.04", "integrated CI needs Linux host contracts")
    require_text(integrated, r"runs-on: macos-26", "integrated CI must use an Xcode 26 host")
    require_text(integrated, r"needs: host-contracts", "macOS integration must wait for host contracts")
    require_text(integrated, r"persist-credentials: false", "checkout credentials must not persist")
    require_text(integrated, r"doctor --platform device --require-qt", "toolchain stage must validate Xcode and Qt")
    require_text(integrated, r"deps --platform device --graphics-toolchain", "dependency stage must resolve the device graph")
    require_text(integrated, r"configure --platform device --client-graph", "configure stage must select the full client graph")
    require_text(integrated, r"cmake --build build-ios/device --config Debug --target Overte", "integrated CI must build the real client target")
    require_text(integrated, r"package-client --platform device", "integrated CI must package the numbered client IPA")
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
    require_text(qt_source, r"concurrency:\s+group: ios-qt-source-\$\{\{ github\.ref \}\}", "Qt source cache writers must serialize per ref")
    require_text(qt_source, r"cancel-in-progress: false", "an expensive Qt source cache build must not be cancelled by a duplicate dispatch")
    require_text(qt_source, r"workflow_call:[\s\S]*?qt_cache_key:[\s\S]*?jobs\.qt-ios-source\.outputs\.qt_cache_key", "reusable Qt workflow must expose its cache key")
    require_text(qt_source, r"outputs:[\s\S]*?qt_cache_key:.*steps\.cache-key\.outputs\.value", "Qt job output must originate from the cache-key step")

    bootstrap_workflow = SOURCE_ROOT / ".github" / "workflows" / "ios-bootstrap.yml"
    require_text(bootstrap_workflow, r"needs\.provision-qt-ios\.outputs\.qt_cache_key", "reusable cache output must reach the integrated caller")

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
    require_text(qt_source, r"outputs:\s+qt_cache_key:", "Qt provisioning must expose its deterministic cache key")
    require_text(qt_source, r"value:.*jobs\.qt-ios-source\.outputs\.qt_cache_key", "reusable Qt output must come from the successful provision job")
    require_text(qt_source, r"qt_cache_key:.*steps\.cache-key\.outputs\.value", "Qt job output must use the deterministic key step")
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
    require_text(workflow, r"qt_cache_key:.*needs\.provision-qt-ios\.outputs\.qt_cache_key", "the provisioned cache key must feed the integrated gate")
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
    require_text(smoke, r'simctl openurl.*hifi://overte_hub', "simulator smoke must exercise Overte deep links")
    require_text(smoke, r"sleep 5", "simulator smoke must allow startup failures to surface")
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
