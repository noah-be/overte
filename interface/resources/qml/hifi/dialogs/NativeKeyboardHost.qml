// Copyright 2026 Overte contributors.
// SPDX-License-Identifier: Apache-2.0
import QtQuick 2.7
import controlsUit 1.0 as HifiControls

Item {
    id: root
    property bool inputFocused: false
    property bool keyboardEnabled: typeof HMD !== "undefined" && HMD.active && !metrics.systemImeAvailable
    property alias numeric: keyboard.numeric
    property alias password: keyboard.password
    readonly property bool use3DKeyboard: typeof KeyboardScriptingInterface !== "undefined" && KeyboardScriptingInterface.use3DKeyboard
    readonly property bool raised: keyboard.raised
    readonly property real contentScale: Math.min(1, width / keyboard.keyboardWidth)
    implicitHeight: raised && !use3DKeyboard ? keyboard.raisedHeight * contentScale : 0
    visible: raised && !use3DKeyboard
    HifiControls.TouchUiMetrics { id: metrics }
    Item {
        width: keyboard.keyboardWidth
        height: keyboard.raisedHeight
        scale: root.contentScale
        transformOrigin: Item.TopLeft
        HifiControls.Keyboard { id: keyboard; raised: root.keyboardEnabled && root.inputFocused; numeric: false; password: false }
    }
    Connections {
        target: keyboard
        function onRaisedChanged() { if (typeof KeyboardScriptingInterface !== "undefined") KeyboardScriptingInterface.punctuationMode = keyboard.raised; }
    }
    Component.onDestruction: {
        keyboard.raised = false;
        if (typeof KeyboardScriptingInterface !== "undefined") KeyboardScriptingInterface.punctuationMode = false;
    }
}
