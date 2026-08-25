#!/usr/bin/env python3
"""Static contract for the shared QML controls used by physical iOS E2E."""

# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    action_bar = (
        ROOT / "scripts/system/+android_phoneInterface/mobileActionBar.js"
    ).read_text(encoding="utf-8")
    tablet_home = (
        ROOT / "interface/resources/qml/hifi/tablet/TabletHome.qml"
    ).read_text(encoding="utf-8")
    button_qml = (
        ROOT / "interface/resources/qml/hifi/+android_interface/button.qml"
    ).read_text(encoding="utf-8")

    assert action_bar.count('objectName: "OverteTabletOpen"') == 1
    assert tablet_home.count('objectName: "OverteTabletClose"') == 1
    assert "tabletButton = addButton(navigationBar" in action_bar
    assert "onClicked: tabletProxy.hideAndroidTablet()" in tablet_home
    assert "Accessible.role: Accessible.Button" in button_qml
    assert "Accessible.id: objectName" in button_qml
    assert "Accessible.name: text" in button_qml
    assert "Accessible.onPressAction: clicked()" in button_qml
    assert "activeFocusOnTab: true" in button_qml
    assert "Accessible.id: objectName" in tablet_home
    assert "Accessible.onPressAction: tabletProxy.hideAndroidTablet()" in tablet_home
    print("PASS stable iOS tablet accessibility identifiers")


if __name__ == "__main__":
    main()
