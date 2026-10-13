// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0
import QtQuick 2.7

// Selected native backends perform system Save/Share. Capture still saves a
// real file in the application directory when no system export exists.
QtObject {
    readonly property var capabilities: []
    readonly property bool busy: false
    readonly property string error: qsTr("System save and sharing are unavailable on this client.")
    signal completed(string ticket, string status, string error)
    function request(path, action) { return "" }
    function cancel(ticket) {}
}
