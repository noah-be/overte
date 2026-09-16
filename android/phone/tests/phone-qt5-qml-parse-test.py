#!/usr/bin/env python3
"""Compile shared Phone QML using the actual Qt 5 deployment toolchain.

Pass --qmlcachegen from the Phone Qt dependency package. A Qt 6 host parser
would miss the versionless-import regression this gate is intended to catch.
This syntax gate complements physical QML component construction tests.
"""
import argparse
import pathlib
import subprocess
import tempfile

parser = argparse.ArgumentParser()
parser.add_argument("--qmlcachegen", required=True, type=pathlib.Path)
args = parser.parse_args()
root = pathlib.Path(__file__).resolve().parents[3]
paths = [
    "scripts/system/settings/qml/SettingNumber.qml",
    "interface/resources/qml/dialogs/TabletCustomQueryDialog.qml",
    "interface/resources/qml/hifi/tablet/TabletHome.qml",
]
with tempfile.TemporaryDirectory(prefix="phone-qt5-qml-") as temporary:
    temporary = pathlib.Path(temporary)
    # Fail if the selected parser accepts Qt 6-style versionless imports.
    probe = temporary / "versionless.qml"
    probe.write_text("import QtQuick\nItem {}\n")
    result = subprocess.run([str(args.qmlcachegen), "-o", str(temporary / "probe.qmlc"), str(probe)],
                            capture_output=True, text=True)
    if result.returncode == 0 or "requires a version" not in result.stderr:
        raise SystemExit("Expected the Phone Qt 5 parser; refusing an unsuitable host tool")
    for index, relative in enumerate(paths):
        subprocess.run([str(args.qmlcachegen), "-o", str(temporary / (str(index) + ".qmlc")),
                        str(root / relative)], check=True)
        print("PASS:", relative)
