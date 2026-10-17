#!/usr/bin/env python3
"""Exercise the unchanged packaged chat UI with actual Qt Quick input and models.

Only headset-keyboard and URL-opening native context services are substituted.
There is no substituted chat widget, model, message formatter or Controls type.
"""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[4]
runner = shutil.which(os.environ.get("OVERTE_QML_TEST_RUNNER", "qmltestrunner"))
if not runner:
    raise SystemExit("Qt Quick Test is required for the native chat UI contract")
with tempfile.TemporaryDirectory(prefix="overte-chat-qml-") as temporary:
    stage = Path(temporary)
    production = stage / "production"
    shutil.copytree(ROOT / "scripts/communityScripts/armored-chat", production)
    qml = production / "armored_chat.qml"
    qml.chmod(0o644)
    qml.write_text("import TestChat 1.0\n" + qml.read_text())
    services = stage / "TestChat"
    services.mkdir()
    (services / "qmldir").write_text("module TestChat\nsingleton KeyboardScriptingInterface 1.0 Keyboard.qml\n")
    (services / "Keyboard.qml").write_text(
        "pragma Singleton\nimport QtQuick 2.7\nQtObject { property bool use3DKeyboard: true; property bool raised: false }\n")
    (stage / "tst_chat.qml").write_text((Path(__file__).with_name("tst_chat.qml")).read_text())
    subprocess.run([runner, "-import", str(stage), "-input", str(stage / "tst_chat.qml")],
        check=True, timeout=60, env=os.environ | {"QT_QPA_PLATFORM": "offscreen", "QT_QUICK_BACKEND": "software",
            "QT_LOGGING_TO_CONSOLE": "1", "QT_LOGGING_RULES": "*.warning=true;*.info=true"})
