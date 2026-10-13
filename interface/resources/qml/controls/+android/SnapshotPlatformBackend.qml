// Copyright 2026 Overte contributors.
// SPDX-License-Identifier: Apache-2.0
import QtQuick 2.7
import Overte.Android 1.0

Item {
    id: root
    readonly property var capabilities: nativeAdapter.capabilities
    readonly property bool busy: nativeAdapter.busy
    readonly property string error: nativeAdapter.error
    signal completed(string ticket, string status, string error)
    function request(path, action) { return nativeAdapter.request(path, action); }
    function cancel(ticket) { nativeAdapter.cancel(ticket); }
    NativeSnapshotAdapter {
        id: nativeAdapter
        onCompleted: root.completed(ticket, status, error)
    }
}
