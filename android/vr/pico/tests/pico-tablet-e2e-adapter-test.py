#!/usr/bin/env python3
"""Device-free contracts for the Pico semantic Tablet-E2E adapter."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[4]
DEVICE_ROOT = ROOT / "tests/device"
if str(DEVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(DEVICE_ROOT))

from contracts import load_tablet_product_policy  # noqa: E402


APP = ROOT / "android/vr/pico/apps/picoInterface"
BRIDGE = (APP / "e2e/PicoE2eTabletBridge.cpp").read_text(encoding="utf-8")
ADAPTER = (DEVICE_ROOT / "adapters/android/adapter.py").read_text(encoding="utf-8")
POLICY = ROOT / "android/vr/pico/device-tests/pico4-tablet-policy.json"


class PicoTabletE2EAdapterTest(unittest.TestCase):
    def test_product_policy_requires_the_real_vr_surface(self):
        policy = load_tablet_product_policy(POLICY)
        self.assertEqual("pico4.vr", policy["profileId"])
        home = policy["expectations"]["settings.home"]["requiredControlIds"]
        self.assertTrue({
            "settings.audio", "settings.controllers", "settings.general",
            "settings.graphics", "settings.security",
        }.issubset(home))
        self.assertIn(
            "settings.hmd-preferences",
            policy["expectations"]["settings.general"]["requiredControlIds"],
        )
        self.assertIn(
            "settings.vr-render-resolution",
            policy["expectations"]["settings.graphics"]["requiredControlIds"],
        )

    def test_bridge_observes_qml_and_uses_the_vr_surface_pointer_path(self):
        self.assertIn("getTabletRoot()", BRIDGE)
        self.assertIn('property("semanticScreenId")', BRIDGE)
        self.assertIn("bool semanticScreenFound { false };", BRIDGE)
        self.assertIn("else if (!semanticScreenFound)", BRIDGE)
        self.assertIn("visibleControlIds", BRIDGE)
        self.assertIn("item->mapToScene(local)", BRIDGE)
        self.assertIn("getTabletSurface()", BRIDGE)
        self.assertIn("surface->hoverBeginEvent", BRIDGE)
        self.assertIn("surface->handlePointerEvent(press", BRIDGE)
        self.assertIn("surface->handlePointerEvent(release", BRIDGE)
        self.assertIn("surface->hoverEndEvent", BRIDGE)
        self.assertIn("PointerEvent::Press", BRIDGE)
        self.assertIn("PointerEvent::Release", BRIDGE)
        self.assertNotIn("pico4-tablet-policy.json", BRIDGE)
        self.assertNotIn("gotoHomeScreen", BRIDGE)
        self.assertNotIn("loadQMLSource", BRIDGE)

    def test_bridge_is_debug_only_and_app_private(self):
        cmake = (APP / "CMakeLists.txt").read_text(encoding="utf-8")
        setup = (APP / "overrides/Application_Setup.cpp").read_text(encoding="utf-8")
        self.assertIn("if(OVERTE_PICO_E2E_OPENXR_INPUT)", cmake)
        self.assertIn("PicoE2eTabletBridge.cpp", cmake)
        self.assertIn("OVERTE_E2E_OPENXR_INPUT_V1", setup)
        self.assertIn("installTabletBridge(this)", setup)
        self.assertIn("/data/user/0/org.overte.pico/files/overte-e2e", BRIDGE)
        self.assertIn("QFileInfo(PROBE_PATH).canonicalFilePath()", BRIDGE)
        self.assertIn("activeProbe == expectedProbe", BRIDGE)

    def test_adapter_exposes_semantics_only_for_qualified_pico(self):
        capability_block = ADAPTER.split(
            'if self.kind == "pico" and os.environ.get("OVERTE_PICO_OPENXR_INPUT") == "1":',
            1,
        )[1].split("return sorted(values)", 1)[0]
        self.assertIn('"tablet.snapshot"', capability_block)
        self.assertIn('"tablet.activate"', capability_block)
        self.assertIn("validate_tablet_ui_snapshot", ADAPTER)
        self.assertIn("PICO_TABLET_OBSERVATION", ADAPTER)
        self.assertIn("PICO_TABLET_COMMAND", ADAPTER)
        self.assertNotIn("OVERTE_E2E_TABLET_POLICY", ADAPTER)

    def test_visible_navigation_controls_have_single_semantic_names(self):
        home = (ROOT / "interface/resources/qml/hifi/tablet/TabletHome.qml").read_text(
            encoding="utf-8")
        header = (ROOT / "scripts/system/settings/qml/HeaderElement.qml").read_text(
            encoding="utf-8")
        general = (ROOT / "interface/resources/qml/hifi/tablet/TabletGeneralPreferences.qml").read_text(
            encoding="utf-8")
        settings_script = (ROOT / "scripts/system/settings/settings.js").read_text(
            encoding="utf-8")
        self.assertEqual(1, home.count('objectName: "nav.close"'))
        self.assertNotIn('objectName: "OverteTabletClose"', home)
        self.assertIn('objectName: "nav.home"', header)
        self.assertIn('objectName: "nav.back"', general)
        self.assertIn('event.type === "returnToSettings"', settings_script)


if __name__ == "__main__":
    unittest.main()
