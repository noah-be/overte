#!/usr/bin/env python3
"""Execute production shared QML callers with only the OS web view substituted."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[4]
FIXTURES = Path(__file__).with_name("qml")


class EmbeddedWebQmlTests(unittest.TestCase):
    def test_actual_shared_qml_bridge_startup_and_source_replacement(self):
        runner = shutil.which(os.environ.get("OVERTE_QML_TEST_RUNNER", "qmltestrunner"))
        self.assertIsNotNone(runner, "Qt Quick Test is required for this host suite")
        with tempfile.TemporaryDirectory(prefix="overte-embedded-web-qml-") as temporary:
            stage = Path(temporary)
            controls = stage / "controls"
            world = stage / "+android_interface"
            tests = stage / "tests"
            for directory in (controls, world, tests):
                directory.mkdir()
            for name in ("EmbeddedWebView.qml", "NativeFlickableWebViewCore.qml", "FlickableWebViewCore.qml",
                         "TabletWebScreen.qml", "TabletWebView.qml", "TabletWebButton.qml"):
                shutil.copy2(ROOT / "interface/resources/qml/controls" / name, controls / name)
            (controls / "qmldir").write_text('module controls\n' + ''.join(
                name + ' 1.0 ' + name + '.qml\n' for name in (
                    'EmbeddedWebView', 'NativeFlickableWebViewCore', 'FlickableWebViewCore',
                    'TabletWebScreen', 'TabletWebView', 'TabletWebButton')), encoding='utf-8')
            modules = {
                "controlsUit": ("Keyboard", "Key", "TouchUiMetrics", "TouchUiProfileBase"),
                "stylesUit": ("HifiConstants", "RalewaySemiBold"),
                "styles": ("HifiConstants",),
            }
            for module, names in modules.items():
                directory = stage / module
                directory.mkdir()
                for name in names:
                    shutil.copy2(ROOT / "interface/resources/qml" / module / (name + ".qml"), directory)
                (directory / "qmldir").write_text("module " + module + "\n" + "".join(
                    name + " 1.0 " + name + ".qml\n" for name in names), encoding="utf-8")
            # Select real shared measurements with native screen-space IME available.
            (stage / "controlsUit/TouchUiProfile.qml").write_text(
                'import QtQuick 2.7\nTouchUiProfileBase { systemImeAvailable: true }\n', encoding="utf-8")
            for module in ("Hifi", "TabletScriptingInterface"):
                directory = stage / module
                directory.mkdir()
                (directory / "qmldir").write_text("module " + module + "\nNativeBoundary 1.0 NativeBoundary.qml\n", encoding="utf-8")
                (directory / "NativeBoundary.qml").write_text("import QtQuick 2.7\nQtObject {}\n", encoding="utf-8")
            backend_selector = controls / "+android_interface"
            backend_selector.mkdir()
            shutil.copy2(FIXTURES / "FakeEmbeddedWebBackend.qml", backend_selector / "EmbeddedWebBackend.qml")
            shutil.copy2(ROOT / "interface/resources/qml/controls/EmbeddedWebBackend.qml", controls)
            shutil.copy2(ROOT / "interface/resources/qml/Web3DSurface.qml", stage)
            for name in ("Web3DSurface.qml", "Web3DSurfaceAndroid.qml"):
                shutil.copy2(ROOT / "interface/resources/qml/+android_interface" / name, world / name)
            for name in ("FakeDocument.qml", "tst_embedded_web_view.qml"):
                shutil.copy2(FIXTURES / name, tests / name)
            subprocess.run([runner, "-file-selector", "android_interface", "-import", str(stage),
                            "-input", str(tests)], check=True, timeout=60,
                           env=os.environ | {"QT_QPA_PLATFORM": "offscreen", "QT_QUICK_BACKEND": "software"})


if __name__ == "__main__":
    unittest.main()
