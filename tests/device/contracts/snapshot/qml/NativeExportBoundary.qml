// SPDX-License-Identifier: Apache-2.0
// Only the system export boundary is substituted; the caller executes unchanged.
import QtQuick 2.7
QtObject {
    property var capabilities: ["save", "share"]
    property bool busy: false
    property string error: ""
    property string active: ""
    property int sequence: 0
    signal completed(string ticket, string status, string error)
    function request(path, action) {
        if (busy || !path || capabilities.indexOf(action) === -1) { return "" }
        busy = true; active = "export_" + (++sequence); return active
    }
    function cancel(ticket) {
        if (ticket !== active) { return }
        busy = false; active = ""; completed(ticket, "cancelled", "")
    }
}
