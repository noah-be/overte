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
KEYS = ["shadowsEnabled", "bloomEnabled", "ambientOcclusionEnabled", "antialiasingMode",
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
                "void RenderScriptingInterface::loadSettings(",
                "void RenderScriptingInterface::setShadowsEnabled(", "void RenderScriptingInterface::forceShadowsEnabled(",
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
        previous = subprocess.check_output(["git", "show", BASELINE + ":interface/src/Application.cpp"], cwd=ROOT, text=True)
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
                "legacySourceRevision": BASELINE, "boundary": "Host production bodies / Qt INI store; no device, GPU or Setting::Manager writer proof",
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
            "scale": first["runtime"]["scale"], "lod": 0, "profile": 3, "active": 30, "inactive": 30, "startup": 30})
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
