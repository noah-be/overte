// Copyright 2026 Overte contributors.
// SPDX-License-Identifier: Apache-2.0
import QtQuick 2.7
import controls 1.0 as SharedControls

SharedControls.AndroidEmbeddedWebBackend {
    // Both world HTML and the VR tablet belong to the offscreen HMD scene.
    presentation: "texture"
    onEditorFocusChanged: {
        if (typeof eventBridge === "undefined") { return; }
        var message = active ? "_RAISE_KEYBOARD" : "_LOWER_KEYBOARD";
        if (active && numeric) { message += "_NUMERIC"; }
        if (active && password) { message += "_PASSWORD"; }
        eventBridge.emitWebEvent(message);
    }
}
