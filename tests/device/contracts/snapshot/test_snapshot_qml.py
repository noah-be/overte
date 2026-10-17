#!/usr/bin/env python3
"""Run the production native Snapshot review; substitute only native services."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[4]
runner = shutil.which(os.environ.get('OVERTE_QML_TEST_RUNNER', 'qmltestrunner'))
if not runner:
    raise SystemExit('Qt Quick Test is required for the native Snapshot review')
with tempfile.TemporaryDirectory(prefix='overte-snapshot-qml-') as temporary:
    stage = Path(temporary)
    production = stage / 'production'
    shutil.copytree(ROOT / 'scripts/system/snapshot', production)
    review = production / 'NativeSnapshotReview.qml'
    review.chmod(0o644)
    review.write_text('import TestSnapshot 1.0\n' + review.read_text())
    # Keep the complete actual controls module, including implicit Text/Button
    # siblings. Test the logical module and QFileSelector rather than selector
    # directory imports which can accidentally hide production shadowing.
    shutil.copytree(ROOT / 'interface/resources/qml/controls', stage / 'controls')
    boundary = stage / 'TestSnapshot'
    boundary.mkdir()
    (boundary / 'qmldir').write_text('module TestSnapshot\nsingleton Snapshot 1.0 Snapshot.qml\n'
        'singleton KeyboardScriptingInterface 1.0 Keyboard.qml\n')
    (boundary / 'Snapshot.qml').write_text('pragma Singleton\nimport QtQuick 2.7\nQtObject {'
        ' function getAvailableSnapshotFormats() { return ["png", "jpg", "webp"] }'
        ' function getSnapshotFormat() { return "png" } function setSnapshotFormat(value) {}'
        ' function snapshotFileUrl(path) { return "" } }\n')
    (boundary / 'Keyboard.qml').write_text('pragma Singleton\nimport QtQuick 2.7\nQtObject {'
        ' property bool use3DKeyboard: true; property bool raised: false }\n')
    tests = stage / 'tests'
    tests.mkdir()
    shutil.copy2(Path(__file__).with_name('qml') / 'tst_snapshot.qml', tests)
    selected = stage / 'controls/+snapshot_test'
    selected.mkdir()
    shutil.copy2(Path(__file__).with_name('qml') / 'NativeExportBoundary.qml', selected / 'SnapshotPlatformBackend.qml')
    for selector in ([], ['-file-selector', 'snapshot_test']):
        subprocess.run([runner, *selector, '-import', str(stage), '-input', str(tests)],
            check=True, timeout=60, env=os.environ | {'QT_QPA_PLATFORM': 'offscreen',
                'QT_QUICK_BACKEND': 'software', 'QT_LOGGING_TO_CONSOLE': '1'})
