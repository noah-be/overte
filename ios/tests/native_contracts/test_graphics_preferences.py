"""Production iOS startup/render/preset/setter bodies across persistent processes.

GPU/platform/display and asynchronous Setting::Manager writes are explicit
fixtures. Real Qt INI persistence is observed; this is not a native device run.
"""
from pathlib import Path
import json
import os
import hashlib
from datetime import datetime, timezone
import shlex
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tests/device/contracts/lifecycle"))
from test_login_dialog_domain_receiver import block

BASELINE = "c41ddaea7976b6e3855c1f135af06a99802a0074"
# Exact historical production block retained as test input for shallow CI checkouts.
# The immutable original revision is provenance, not a runtime Git-history dependency.
LEGACY_STARTUP_SHA256 = "4ba894a55166ecc2b52de984644a4408615cf5cafd0069a9c804370afd976bfa"
LEGACY_STARTUP = r'''    // Load settings of the RenderScritpingInterface
    // Do that explicitely before being used
    RenderScriptingInterface::getInstance()->loadSettings();

    // Setup the PerformanceManager which will enforce the several settings to match the Preset
    // On the first run, the Preset is evaluated from the
    getPerformanceManager().setupPerformancePresetSettings(_firstRun.get());

#if defined(Q_OS_IOS)
    // iPads are passively cooled and the XCUITest runner shares the same
    // thermal budget as Interface.  A persisted desktop/realtime preset can
    // otherwise drive the client at 60 Hz until iPadOS suspends the test
    // runner under thermal pressure.  Apply a predictable mobile ceiling after
    // the performance preset while preserving any user-selected render scale
    // that is already lower than the supported iOS default.
    constexpr int IOS_TARGET_FPS { 30 };
    constexpr float IOS_MAX_VIEWPORT_RESOLUTION_SCALE { 0.8f };
    auto iosRenderSettings = RenderScriptingInterface::getInstance();
    iosRenderSettings->setShadowsEnabled(false);
    iosRenderSettings->setBloomEnabled(false);
    iosRenderSettings->setAmbientOcclusionEnabled(false);
    iosRenderSettings->setAntialiasingMode(AntialiasingSetupConfig::Mode::NONE);
    if (iosRenderSettings->getViewportResolutionScale() > IOS_MAX_VIEWPORT_RESOLUTION_SCALE) {
        iosRenderSettings->setViewportResolutionScale(IOS_MAX_VIEWPORT_RESOLUTION_SCALE);
    }
    DependencyManager::get<LODManager>()->setWorldDetailQuality(WORLD_DETAIL_LOW);

    auto& iosRefreshRateManager = getRefreshRateManager();
    iosRefreshRateManager.setCustomRefreshRate(
        RefreshRateManager::RefreshRateRegime::FOCUS_ACTIVE, IOS_TARGET_FPS);
    iosRefreshRateManager.setCustomRefreshRate(
        RefreshRateManager::RefreshRateRegime::FOCUS_INACTIVE, IOS_TARGET_FPS);
    iosRefreshRateManager.setCustomRefreshRate(
        RefreshRateManager::RefreshRateRegime::STARTUP, IOS_TARGET_FPS);
    iosRefreshRateManager.setRefreshRateProfile(RefreshRateManager::RefreshRateProfile::CUSTOM);
    logIOSRuntimeMarker(
        "OVERTE_IOS_RENDER_PROFILE stage=mobile-budget-applied",
        "target_fps=", IOS_TARGET_FPS,
        "scale=", iosRenderSettings->getViewportResolutionScale(),
        "shadows=", iosRenderSettings->getShadowsEnabled(),
        "bloom=", iosRenderSettings->getBloomEnabled(),
        "ambient_occlusion=", iosRenderSettings->getAmbientOcclusionEnabled(),
        "antialiasing=", iosRenderSettings->getAntialiasingMode() != AntialiasingSetupConfig::Mode::NONE,
        "world_detail=", WORLD_DETAIL_LOW);
#endif

'''
KEYS = ["renderMethod", "hazeEnabled", "shadowsEnabled", "bloomEnabled", "ambientOcclusionEnabled", "antialiasingMode",
        "viewportResolutionScale", "lodManager/desktopWorldDetailQuality", "refreshRateProfile",
        "customRefreshRateFocusActive", "customRefreshRateFocusInactive", "customRefreshRateStartup",
        "customRefreshRateUnfocus", "customRefreshRateMinimized", "customRefreshRateShutdown"]


class GraphicsPreferences(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.evidence = []
        cls.temp = tempfile.TemporaryDirectory(prefix="ios-graphics-persistence-")
        cls.directory = Path(cls.temp.name)
        flags = shlex.split(subprocess.check_output(["pkg-config", "--cflags", "--libs", "Qt6Core"], text=True))
        render = (ROOT / "interface/src/scripting/RenderScriptingInterface.cpp").read_text()
        header = (ROOT / "interface/src/scripting/RenderScriptingInterface.h").read_text()
        performance = (ROOT / "interface/src/PerformanceManager.cpp").read_text()
        refresh = (ROOT / "interface/src/RefreshRateManager.cpp").read_text()
        lod = (ROOT / "interface/src/LODManager.cpp").read_text()
        settings = (ROOT / "libraries/shared/src/SettingHandle.cpp").read_text()
        for name, text in {
            "render-settings.inc": header[header.index("    Setting::Handle<int> _renderMethodSetting"):
                header.index("    // Force assign both setting")],
            "settings-value.inc": block(settings, "QVariant Settings::value("),
            "render-methods.inc": "\n".join(block(render, signature) for signature in [
                "void RenderScriptingInterface::loadSettings(", "void RenderScriptingInterface::setRenderMethod(", "void RenderScriptingInterface::forceRenderMethod(",
                "void RenderScriptingInterface::setShadowsEnabled(", "void RenderScriptingInterface::forceShadowsEnabled(",
                "void RenderScriptingInterface::setHazeEnabled(", "void RenderScriptingInterface::forceHazeEnabled(",
                "void RenderScriptingInterface::setBloomEnabled(", "void RenderScriptingInterface::forceBloomEnabled(",
                "void RenderScriptingInterface::setAmbientOcclusionEnabled(", "void RenderScriptingInterface::forceAmbientOcclusionEnabled(",
                "void RenderScriptingInterface::setAntialiasingMode(", "void RenderScriptingInterface::forceAntialiasingMode(",
                "void RenderScriptingInterface::setViewportResolutionScale(", "void RenderScriptingInterface::forceViewportResolutionScale("]),
            "performance-methods.inc": "\n".join(block(performance, signature) for signature in [
                "void PerformanceManager::setupPerformancePresetSettings(", "void PerformanceManager::setPerformancePreset(",
                "PerformanceManager::PerformancePreset PerformanceManager::getPerformancePreset(",
                "void PerformanceManager::applyPerformancePreset("]),
            "refresh-methods.inc": "\n".join(block(refresh, signature) for signature in [
                "void RefreshRateManager::setRefreshRateProfile(", "void RefreshRateManager::setCustomRefreshRate("]),
            "lod-methods.inc": "\n".join(block(lod, signature) for signature in [
                "void LODManager::loadSettings(", "void LODManager::saveSettings(",
                "void LODManager::setWorldDetailQuality(WorldDetailQuality quality, bool",
                "void LODManager::setWorldDetailQuality(WorldDetailQuality quality)",
                "WorldDetailQuality LODManager::getWorldDetailQuality("]),
        }.items():
            (cls.directory / name).write_text(text)
        application = (ROOT / "interface/src/Application.cpp").read_text()
        if hashlib.sha256(LEGACY_STARTUP.encode()).hexdigest() != LEGACY_STARTUP_SHA256:
            raise AssertionError("Historical startup fixture hash does not match the retained c41 production body")
        previous = LEGACY_STARTUP + "#if defined(Q_OS_ANDROID)"
        for label, source in [("current", application), ("previous", previous)]:
            start = source.index("    // Load settings of the RenderScritpingInterface")
            capture = source.find("#if defined(Q_OS_IOS)\n    // Capture existing choices")
            if capture != -1:
                assert capture < start
                start = capture
            end = source.index("#if defined(Q_OS_ANDROID)", start)
            (cls.directory / "startup.inc").write_text(source[start:end])
            command = ["c++", "-std=c++17", "-fPIC", "-pthread", "-I" + str(ROOT), "-I" + str(cls.directory),
                str(Path(__file__).with_name("graphics-preferences-test.cpp")), "-o", str(cls.directory / label), *flags]
            subprocess.run(command, check=True, timeout=60)

    @classmethod
    def tearDownClass(cls):
        evidence = os.environ.get("OVERTE_TEST_GRAPHICS_EVIDENCE")
        if evidence:
            payload = {"sourceRevision": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
                "legacySourceRevision": BASELINE, "legacyStartupSHA256": LEGACY_STARTUP_SHA256, "boundary": "Host production bodies / Qt INI store; no device, GPU or Setting::Manager writer proof",
                "qtCoreVersion": subprocess.check_output(["pkg-config", "--modversion", "Qt6Core"], text=True).strip(),
                "observations": cls.evidence}
            Path(evidence).write_text(json.dumps(payload, indent=2) + "\n")
        cls.temp.cleanup()

    def invoke(self, file, action, option="normal", binary="current"):
        if isinstance(option, dict):
            option = json.dumps(option)
        result = subprocess.run([str(self.directory / binary), str(file), action, option],
                                check=True, text=True, stdout=subprocess.PIPE, timeout=10)
        observation = json.loads(result.stdout)
        self.evidence.append({"test": self.id(), "binary": binary, "action": action,
            "utc": datetime.now(timezone.utc).isoformat(), "result": observation,
            "ini_sha256": hashlib.sha256(file.read_bytes()).hexdigest(),
            "ini": file.read_text()})
        return observation

    def fresh(self):
        directory = tempfile.TemporaryDirectory(prefix="ios-graphics-store-")
        self.addCleanup(directory.cleanup)
        return Path(directory.name) / "preferences.ini"

    def assert_same_choices(self, expected, actual):
        for key in KEYS:
            self.assertEqual(expected.get(key), actual.get(key), key)

    def test_fresh_and_repeated_starts_keep_the_existing_safe_mobile_profile(self):
        file = self.fresh()
        first = self.invoke(file, "startup", "first")
        self.assertEqual(first["runtime"], {"shadows": False, "bloom": False, "ao": False, "aa": 0,
            "haze": True, "method": 0, "scale": first["runtime"]["scale"], "lod": 0, "profile": 3, "active": 30, "inactive": 30, "startup": 30})
        self.assertAlmostEqual(first["runtime"]["scale"], 0.8, places=6)
        second = self.invoke(file, "startup")
        self.assert_same_choices(first["stored"], second["stored"])

    def test_user_changes_survive_normal_restart_and_can_be_changed_again(self):
        file = self.fresh()
        self.invoke(file, "startup", "first")
        for user in ["first", "second", "first"]:
            selected = self.invoke(file, "user", user)["stored"]
            for _ in range(2):
                result = self.invoke(file, "startup")
                self.assert_same_choices(selected, result["stored"])
                self.assertEqual(result["runtime"]["haze"], selected["hazeEnabled"])
                self.assertEqual(result["runtime"]["method"], selected["renderMethod"])
                self.assertEqual(result["runtime"]["profile"], selected["refreshRateProfile"])
                self.assertEqual(result["runtime"]["lod"], selected["lodManager/desktopWorldDetailQuality"])
                self.assertAlmostEqual(result["runtime"]["scale"], selected["viewportResolutionScale"], places=6)

    def test_saved_choices_survive_unknown_preset_and_first_resolution_migration(self):
        file = self.fresh()
        self.invoke(file, "startup", "first")
        selected = self.invoke(file, "user", "first")["stored"]
        self.invoke(file, "seed", {"performancePreset": 0, "iosViewportResolutionScaleDefaultApplied": False})
        restored = self.invoke(file, "startup")
        self.assert_same_choices(selected, restored["stored"])
        self.assertTrue(restored["stored"]["iosViewportResolutionScaleDefaultApplied"])

    def test_partial_preferences_keep_real_existing_values_and_default_only_unset_options(self):
        file = self.fresh()
        self.invoke(file, "seed", {"shadowsEnabled": True, "viewportResolutionScale": 1.3,
            "refreshRateProfile": 1, "customRefreshRateFocusActive": 47})
        result = self.invoke(file, "startup", "first")
        self.assertTrue(result["stored"]["shadowsEnabled"])
        self.assertFalse(result["stored"]["bloomEnabled"])
        self.assertFalse(result["stored"]["ambientOcclusionEnabled"])
        self.assertEqual(result["stored"]["antialiasingMode"], 0)
        self.assertAlmostEqual(result["stored"]["viewportResolutionScale"], 1.3, places=6)
        self.assertEqual(result["stored"]["refreshRateProfile"], 1)
        self.assertEqual(result["stored"]["customRefreshRateFocusActive"], 47)
        self.assertEqual(result["stored"]["customRefreshRateFocusInactive"], 30)

    def test_an_explicit_graphics_preset_survives_repeated_starts(self):
        file = self.fresh()
        self.invoke(file, "startup", "first")
        selected = self.invoke(file, "preset")["stored"]
        self.assertEqual(selected["performancePreset"], 4)
        for flag in ["normal", "first", "normal"]:
            result = self.invoke(file, "startup", flag)["stored"]
            self.assert_same_choices(selected, result)
            self.assertEqual(result["performancePreset"], 4)

    def test_previous_preset_reassignment_drops_saved_render_method_and_haze(self):
        file = self.fresh()
        self.invoke(file, "startup", "first")
        selected = self.invoke(file, "user", "first")["stored"]
        self.invoke(file, "seed", {"performancePreset": 0})
        previous = self.invoke(file, "startup", binary="previous")["stored"]
        self.assertNotEqual(previous["renderMethod"], selected["renderMethod"])
        self.assertNotEqual(previous["hazeEnabled"], selected["hazeEnabled"])

    def test_invalid_scale_and_profile_use_safe_values(self):
        file = self.fresh()
        self.invoke(file, "seed", {"viewportResolutionScale": 0, "refreshRateProfile": 999,
            "iosViewportResolutionScaleDefaultApplied": True, "performancePreset": 5})
        result = self.invoke(file, "startup")
        self.assertAlmostEqual(result["runtime"]["scale"], 0.8, places=6)
        self.assertEqual(result["runtime"]["profile"], 3)

    def test_actual_previous_startup_reproduces_destructive_persistence(self):
        file = self.fresh()
        self.invoke(file, "startup", "first")
        selected = self.invoke(file, "user", "first")["stored"]
        before = self.invoke(file, "startup", binary="previous")
        self.assertNotEqual(before["stored"]["shadowsEnabled"], selected["shadowsEnabled"])
        self.assertNotEqual(before["stored"]["ambientOcclusionEnabled"], selected["ambientOcclusionEnabled"])
        self.assertNotEqual(before["stored"]["antialiasingMode"], selected["antialiasingMode"])
        self.assertNotEqual(before["stored"]["viewportResolutionScale"], selected["viewportResolutionScale"])
        self.assertNotEqual(before["stored"]["lodManager/desktopWorldDetailQuality"], selected["lodManager/desktopWorldDetailQuality"])
        self.assertNotEqual(before["stored"]["refreshRateProfile"], selected["refreshRateProfile"])
        self.assertNotEqual(before["stored"]["customRefreshRateFocusActive"], selected["customRefreshRateFocusActive"])
        self.assertNotEqual(before["stored"]["customRefreshRateFocusInactive"], selected["customRefreshRateFocusInactive"])
        self.assertNotEqual(before["stored"]["customRefreshRateStartup"], selected["customRefreshRateStartup"])
        self.invoke(file, "user", "second")
        before = self.invoke(file, "startup", binary="previous")
        self.assertFalse(before["stored"]["bloomEnabled"])

if __name__ == "__main__":
    unittest.main()
