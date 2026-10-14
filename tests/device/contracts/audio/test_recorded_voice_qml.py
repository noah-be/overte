#!/usr/bin/env python3
"""Click the production voice controls, substituting only native audio/tablet services."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[4]
FIXTURES = Path(__file__).with_name("qml")
runner = shutil.which(os.environ.get("OVERTE_QML_TEST_RUNNER", "qmltestrunner"))
if runner is None:
    raise SystemExit("Qt Quick Test is required for the recorded voice-test UI contract")
with tempfile.TemporaryDirectory(prefix="overte-recorded-voice-qml-") as temporary:
    stage = Path(temporary)
    production = stage / "production"
    tests = stage / "tests"
    production.mkdir(); tests.mkdir()
    # Only add an import for the native context fixture; widget code is unchanged.
    qml = (ROOT / "interface/resources/qml/hifi/audio/LoopbackAudio.qml").read_text()
    (production / "LoopbackAudio.qml").write_text("import TestVoice 1.0\n" + qml)
    modules = {
        "controlsUit": ("Button", "TouchUiMetrics", "TouchUiProfileBase"),
        "stylesUit": ("HifiConstants", "RalewayRegular", "RalewaySemiBold", "HiFiGlyphs"),
    }
    for module, names in modules.items():
        directory = stage / module
        directory.mkdir()
        for name in names:
            shutil.copy2(ROOT / "interface/resources/qml" / module / (name + ".qml"), directory)
        (directory / "qmldir").write_text("module " + module + "\n" + "".join(
            name + " 1.0 " + name + ".qml\n" for name in names))
    # Tablet sounds are a native boundary; the actual button and metrics execute.
    (stage / "TabletScriptingInterface").mkdir()
    (stage / "TabletScriptingInterface/qmldir").write_text(
        "module TabletScriptingInterface\nsingleton Tablet 1.0 Tablet.qml\nsingleton TabletEnums 1.0 TabletEnums.qml\n")
    (stage / "TabletScriptingInterface/Tablet.qml").write_text(
        "pragma Singleton\nimport QtQuick 2.7\nQtObject { function playSound(value) {} }\n")
    (stage / "TabletScriptingInterface/TabletEnums.qml").write_text(
        "pragma Singleton\nimport QtQuick 2.7\nQtObject { enum Sound { ButtonHover, ButtonClick } }\n")
    (stage / "TestVoice").mkdir()
    (stage / "TestVoice/qmldir").write_text("module TestVoice\nsingleton AudioScriptingInterface 1.0 FakeVoice.qml\n")
    shutil.copy2(FIXTURES / "FakeVoice.qml", stage / "TestVoice")
    shutil.copy2(FIXTURES / "tst_recorded_voice.qml", tests)
    for touch in (False, True):
        (stage / "controlsUit/TouchUiProfile.qml").write_text(
            "import QtQuick 2.7\nTouchUiProfileBase { directTouch: " + str(touch).lower() + " }\n")
        subprocess.run([runner, "-import", str(stage), "-input", str(tests)], check=True, timeout=60,
                       env=os.environ | {"QT_QPA_PLATFORM": "offscreen", "QT_QUICK_BACKEND": "software"})
