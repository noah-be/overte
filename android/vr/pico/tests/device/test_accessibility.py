#!/usr/bin/env python3
"""Check actual startup semantics and pinned Tablet IDs without claiming VR usability."""
import json
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET
ROOT = Path(__file__).resolve().parents[5]
PICO = ROOT / 'android/vr/pico'
NS = '{http://schemas.android.com/apk/res/android}'
class AccessibilityTest(unittest.TestCase):
    def test_tablet_preferences_retain_original_shared_button(self):
        setup = (ROOT / 'interface/src/Application_Setup.cpp').read_text()
        self.assertIn('DependencyManager::set<TabletScriptingInterface>();', setup)
        qml = ROOT / 'interface/resources/qml'
        general = (qml / 'hifi/tablet/TabletGeneralPreferences.qml').read_text()
        self.assertIn('TabletPreferencesDialog {', general)
        preferences = (qml / 'hifi/tablet/tabletWindows/TabletPreferencesDialog.qml').read_text()
        self.assertIn('import controlsUit 1.0 as HifiControls', preferences)
        for name in ('GeneralPreferencesSave', 'GeneralPreferencesCancel'):
            self.assertIn('HifiControls.Button {\n                objectName: "' + name + '"', preferences)
        self.assertNotIn('PICO_TABLET_PREFERENCES_', preferences)
        self.assertIn('if (!usesAndroidClickAction) { dialog.saveAll(); }', preferences)
        self.assertIn('if (!usesAndroidClickAction) { dialog.restoreAll(); }', preferences)
        self.assertIn('dialog.cancelToTabletHome();', preferences)
        button = (qml / 'controlsUit/Button.qml').read_text()
        # Main/Pico retains Android-only base dispatch. Neither the Apple
        # Android-or-iOS selector nor Phone's navigation route is transplanted.
        self.assertIn('readonly property bool usesAndroidClickAction: Qt.platform.os === "android"\n', button)
        self.assertIn('if (control.usesAndroidClickAction)', button)
        self.assertIn('focusPolicy: visible && enabled ? Qt.StrongFocus : Qt.NoFocus', button)
        self.assertNotIn('onCanceled:', button)
        self.assertNotIn('PICO_QML_BUTTON', button)
        self.assertIn('typeof control.androidClickAction === "function"', button)
        # Original complete Button executes in the released real Qt test.
        # Derived actions execute in the separate Shared original-block test;
        # this source pin is not whole-dialog/persistence/native action proof.

    def test_settings_use_original_shared_toggle_controls(self):
        qml = ROOT / 'interface/resources/qml'
        controller = (qml / 'hifi/tablet/ControllerSettings.qml').read_text()
        self.assertIn('import controlsUit 1.0 as HifiControls', controller)
        self.assertIn('HifiControls.CheckBox {', controller)
        for name, control in (('CheckBoxPreference', 'CheckBox'), ('PrimaryHandPreference', 'RadioButton')):
            preference = (qml / 'dialogs/preferences' / (name + '.qml')).read_text()
            self.assertIn('import controlsUit 1.0', preference)
            self.assertIn(control + ' {', preference)
            original = (qml / 'controlsUit' / (control + '.qml')).read_text()
            self.assertIn('focusPolicy: visible && enabled ? Qt.StrongFocus : Qt.NoFocus', original)
            self.assertIn('onVisibleChanged: { if (!visible) { focus = false; } }', original)
            self.assertIn('onEnabledChanged: { if (!enabled) { focus = false; } }', original)
        # Original controls execute in the Shared real Qt test. Custom setting
        # effects/persistence/ordering are not replaced or proved by this pin.

    def test_audio_switch_reaches_existing_pico_audio_service(self):
        setup = (ROOT / 'interface/src/Application_Setup.cpp').read_text()
        self.assertIn('DependencyManager::set<AudioScriptingInterface, scripting::Audio>();', setup)
        ui = (ROOT / 'interface/src/Application_UI.cpp').read_text()
        self.assertIn('surfaceContext->setContextProperty("AudioScriptingInterface", '
                      'DependencyManager::get<AudioScriptingInterface>().data());', ui)
        settings = (ROOT / 'scripts/system/settings/Settings.qml').read_text()
        self.assertIn('semanticId: "settings.audio"', settings)
        self.assertIn('targetPage: "hifi/audio/Audio.qml"', settings)
        qml = ROOT / 'interface/resources/qml'
        audio = (qml / 'hifi/audio/Audio.qml').read_text()
        self.assertIn('import controlsUit 1.0 as HifiControlsUit', audio)
        self.assertIn('HifiControlsUit.Switch {\n                    id: muteMic;', audio)
        self.assertIn('AudioScriptingInterface.mutedDesktop = checked;', audio)
        self.assertIn('AudioScriptingInterface.mutedHMD = checked;', audio)
        control = (qml / 'controlsUit/Switch.qml').read_text()
        self.assertIn('rootSwitch.chooseCheckedByUser(false);', control)
        self.assertIn('rootSwitch.chooseCheckedByUser(true);', control)
        self.assertIn('rootSwitch.clicked();', control)
        # Released runtime test executes complete control and original muteMic;
        # this source pin does not execute the actual audio engine or device.

    def test_startup_announces_label_and_not_decorative_progress(self):
        root = ET.parse(PICO / 'apps/picoInterface/src/main/res/layout/activity_startup.xml').getroot()
        status = root.find('TextView')
        self.assertEqual(status.get(NS + 'id'), '@+id/startup_status')
        self.assertEqual(status.get(NS + 'importantForAccessibility'), 'yes')
        self.assertEqual(status.get(NS + 'accessibilityLiveRegion'), 'polite')
        self.assertEqual(status.get(NS + 'text'), '@string/startup_status')
        for tag in ('ImageView', 'ProgressBar'):
            self.assertEqual(root.find(tag).get(NS + 'importantForAccessibility'), 'no')
        strings = ET.parse(PICO / 'apps/picoInterface/src/main/res/values/strings.xml').getroot()
        self.assertTrue(strings.find("string[@name='startup_status']").text.strip())
        def luminance(color):
            values = [int(color[i:i+2], 16)/255 for i in (1,3,5)]
            linear = [v/12.92 if v <= .04045 else ((v+.055)/1.055)**2.4 for v in values]
            return sum(v*w for v,w in zip(linear, (.2126,.7152,.0722)))
        foreground = luminance(status.get(NS + 'textColor'))
        background = luminance(root.get(NS + 'background'))
        self.assertGreater((foreground+.05)/(background+.05), 7)
        self.assertTrue(status.get(NS + 'textSize').endswith('sp'))

    def test_pico_required_controls_remain_explicit_not_blanket_exemptions(self):
        policy = json.loads((PICO / 'device-tests/pico4-tablet-policy.json').read_text())
        home = policy['expectations']['settings.home']['requiredControlIds']
        for control in ('settings.audio', 'settings.controllers', 'settings.general', 'settings.security'):
            self.assertIn(control, home)
        self.assertIn('settings.hmd-preferences', policy['expectations']['settings.general']['requiredControlIds'])
        self.assertIn('settings.vr-render-resolution', policy['expectations']['settings.graphics']['requiredControlIds'])
if __name__ == '__main__': unittest.main(verbosity=2)
