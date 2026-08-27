#!/usr/bin/env python3
"""Static end-to-end contracts for trusted Android startup URLs."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[3]


class AndroidStartupUrlPathTest(unittest.TestCase):
    def test_shared_launcher_to_native_parser_chain_is_intact(self):
        launcher = (ROOT / "android/common/device_tests/e2e_android/src/main/java/"
                    "org/overte/e2e/E2eLauncherActivityBase.java").read_text(
                        encoding="utf-8")
        loader = (ROOT / "android/common/libraries/qt/src/main/java/"
                  "org/qtproject/qt5/android/bindings/QtActivityLoader.java").read_text(
                      encoding="utf-8")
        setup = (ROOT / "interface/src/Application_Setup.cpp").read_text(
            encoding="utf-8")

        self.assertIn('appendQueryParameter("location", SPAWN_VIEWPOINT)', launcher)
        self.assertIn('putExtra("applicationArguments", arguments)', launcher)
        self.assertIn('intent.getStringExtra("applicationArguments")', loader)
        self.assertIn("appParams.replace(' ', '\\t').trim()", loader)
        self.assertIn('_urlParam = parser.value("url");', setup)

    def test_android_startup_selection_and_location_decoding(self):
        application = (ROOT / "interface/src/Application.cpp").read_text(
            encoding="utf-8")
        address_manager = (ROOT / "libraries/networking/src/AddressManager.cpp").read_text(
            encoding="utf-8")

        self.assertIn("hasExplicitAndroidStartupUrl", application)
        self.assertIn("android::startup::selectDestination", application)
        self.assertIn("#ifdef Q_OS_ANDROID", application)
        self.assertIn(
            "queryItemValue(LOCATION_QUERY_KEY, QUrl::FullyDecoded)",
            address_manager,
        )

    def test_all_android_products_compile_the_shared_interface(self):
        products = (
            "android/phone/apps/phoneInterface/CMakeLists.txt",
            "android/vr/pico/apps/picoInterface/CMakeLists.txt",
            "android/vr/quest/apps/questInterface/CMakeLists.txt",
        )
        for product in products:
            cmake = (ROOT / product).read_text(encoding="utf-8")
            self.assertIn(
                'add_subdirectory("${CMAKE_SOURCE_DIR}/interface"', cmake,
                product,
            )

    def test_intent_trust_boundary_is_not_expanded(self):
        manifests = (
            "android/phone/apps/phoneInterface/src/main/AndroidManifest.xml",
            "android/vr/pico/apps/picoInterface/src/main/AndroidManifest.xml",
        )
        for manifest in manifests:
            source = (ROOT / manifest).read_text(encoding="utf-8")
            self.assertRegex(
                source,
                r'android:name="\.(?:Phone|Pico)InterfaceActivity"[\s\S]*?'
                r'android:exported="false"',
                manifest,
            )

        quest_permissions = (
            ROOT / "android/vr/quest/apps/questInterface/src/main/java/"
            "io/highfidelity/questInterface/PermissionsChecker.java"
        ).read_text(encoding="utf-8")
        self.assertIn("getIntent().getStringExtra(EXTRA_ARGS)", quest_permissions)
        self.assertIn(
            "new Intent(this, InterfaceActivity.class)", quest_permissions
        )
        self.assertIn(
            'intent.putExtra("applicationArguments", mArgs)', quest_permissions
        )


if __name__ == "__main__":
    unittest.main()
