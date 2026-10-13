// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0
import QtQuick 2.7
import controls 1.0 as SharedControls

QtObject {
    id: root
    property QtObject backend: SharedControls.SnapshotPlatformBackend {}
    readonly property var capabilities: backend.capabilities
    readonly property bool busy: backend.busy
    readonly property string error: backend.error
    signal completed(string ticket, string status, string error)
    function request(path, action) { return backend.request(path, action) }
    function cancel(ticket) { backend.cancel(ticket) }
    property Connections relay: Connections {
        target: root.backend
        function onCompleted(ticket, status, error) { root.completed(ticket, status, error) }
    }
}
