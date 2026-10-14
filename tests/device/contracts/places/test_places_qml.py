#!/usr/bin/env python3
"""Exercise production Places controls, models and ordered script messages in Qt.

The QML, adaptive metrics and profile are unmodified production files. Only the
native script bridge is captured by SignalSpy; these cases do not establish
actual navigation, persistent bookmarks, network directories or physical input.
"""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[4]
runner = shutil.which(os.environ.get("OVERTE_QML_TEST_RUNNER", "qmltestrunner"))
if not runner:
    raise SystemExit("Qt Quick Test is required for the native Places UI contract")
with tempfile.TemporaryDirectory(prefix="overte-places-qml-") as temporary:
    stage = Path(temporary)
    production = stage / "production"
    production.mkdir()
    shutil.copy2(ROOT / "scripts/system/places/PicoPlaces.qml", production)
    controls = stage / "controlsUit"
    controls.mkdir()
    types = ("TouchUiMetrics", "TouchUiProfile", "TouchUiProfileBase")
    (controls / "qmldir").write_text("module controlsUit\n" + "".join(
        f"{name} 1.0 {name}.qml\n" for name in types))
    for name in types:
        shutil.copy2(ROOT / "interface/resources/qml/controlsUit" / f"{name}.qml", controls)
    shutil.copy2(Path(__file__).with_name("tst_places.qml"), stage)
    subprocess.run([runner, "-import", str(stage), "-input", str(stage / "tst_places.qml")],
                   check=True, timeout=90, env=os.environ | {
                       "QT_QPA_PLATFORM": "offscreen", "QT_QUICK_BACKEND": "software"})
