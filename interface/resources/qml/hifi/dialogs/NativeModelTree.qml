// Copyright 2026 Overte contributors.
// SPDX-License-Identifier: Apache-2.0
import QtQuick 2.7
import QtQuick.Controls 2.3

// A Qt5/Qt6 view of the existing hierarchical QAbstractItemModel. Model indexes
// remain native values; the editor never duplicates the asset/script backend.
Item {
    id: root
    property var sourceModel: null
    property string filterText: ""
    property bool multiSelect: false
    property int pathRole: 256
    property int folderRole: -1
    property int statusRole: -1
    property var expanded: ({})
    property var selectedKeys: []
    property var rows: []
    property int currentRow: -1
    property int revision: 0
    property string previousCurrentKey: ""
    property alias view: list
    readonly property var currentIndex: currentRow >= 0 && currentRow < rows.length ? rows[currentRow].index : null
    readonly property var selectedIndexes: {
        var result = [];
        for (var i = 0; i < rows.length; ++i) if (selectedKeys.indexOf(rows[i].key) !== -1) result.push(rows[i].index);
        return result;
    }
    readonly property var selection: QtObject {
        readonly property var currentIndex: root.currentIndex
        readonly property var selectedIndexes: root.selectedIndexes
    }
    signal activated(var index)
    function invalidateRows() {
        if (currentRow >= 0 && currentRow < rows.length) previousCurrentKey = rows[currentRow].key;
        currentRow = -1;
        rows = [];
    }
    function rebuild() {
        if (!sourceModel) { rows = []; selectedKeys = []; currentRow = -1; return; }
        var result = [], filter = filterText.trim().toLowerCase();
        function visit(parent, depth, prefix) {
            var count = sourceModel.rowCount(parent), found = false;
            for (var i = 0; i < count; ++i) {
                var index = sourceModel.index(i, 0, parent);
                var name = String(sourceModel.data(index, 0) || "");
                var path = String(sourceModel.data(index, pathRole) || "");
                var key = path || prefix + "/" + name;
                var folder = folderRole >= 0 ? !!sourceModel.data(index, folderRole) : sourceModel.hasChildren(index);
                var start = result.length;
                var row = {index: index, name: name, path: path, key: key, depth: depth, folder: folder,
                    status: statusRole >= 0 ? String(sourceModel.data(index, statusRole) || "") : ""};
                result.push(row);
                var matches = !filter || (name + " " + path).toLowerCase().indexOf(filter) !== -1;
                var childMatches = false;
                if (folder && (filter || expanded[key])) childMatches = visit(index, depth + 1, key);
                if (!matches && !childMatches) result.splice(start, result.length - start);
                else found = true;
            }
            return found;
        }
        var previousKey = currentRow >= 0 && currentRow < rows.length ? rows[currentRow].key : previousCurrentKey;
        previousCurrentKey = "";
        visit(sourceModel.index(-1, -1), 0, "");
        rows = result;
        var valid = [];
        currentRow = -1;
        for (var r = 0; r < rows.length; ++r) {
            if (rows[r].key === previousKey) currentRow = r;
            if (selectedKeys.indexOf(rows[r].key) !== -1) valid.push(rows[r].key);
        }
        selectedKeys = valid;
        ++revision;
        selectionChanged();
    }
    function selectRow(row, additive) {
        if (row < 0 || row >= rows.length) return;
        currentRow = row;
        var keys = additive || multiSelect ? selectedKeys.slice() : [];
        var position = keys.indexOf(rows[row].key);
        if (position < 0) keys.push(rows[row].key); else if (additive || multiSelect) keys.splice(position, 1);
        selectedKeys = keys;
        selectionChanged();
    }
    function toggle(row) {
        if (row < 0 || row >= rows.length || !rows[row].folder) return;
        var next = Object.assign({}, expanded);
        next[rows[row].key] = !next[rows[row].key];
        expanded = next;
        rebuild();
    }
    function clearSelection() { selectedKeys = []; currentRow = -1; selectionChanged(); }
    onSourceModelChanged: refresh.restart()
    onFilterTextChanged: refresh.restart()
    Component.onCompleted: rebuild()
    Timer { id: refresh; interval: 0; onTriggered: root.rebuild() }
    Connections {
        target: root.sourceModel
        ignoreUnknownSignals: true
        function onModelAboutToBeReset() { root.invalidateRows(); }
        function onRowsAboutToBeRemoved() { root.invalidateRows(); }
        function onLayoutAboutToBeChanged() { root.invalidateRows(); }
        function onModelReset() { refresh.restart(); }
        function onRowsInserted() { refresh.restart(); }
        function onRowsRemoved() { refresh.restart(); }
        function onDataChanged() { refresh.restart(); }
        function onLayoutChanged() { refresh.restart(); }
    }
    ListView {
        id: list
        objectName: "nativeModelTree"
        anchors.fill: parent
        clip: true
        model: root.rows
        keyNavigationEnabled: false
        ScrollBar.vertical: ScrollBar { }
        Keys.onPressed: function(event) {
            if (event.key === Qt.Key_Down || event.key === Qt.Key_Up) {
                root.selectRow(Math.max(0, Math.min(root.rows.length - 1, root.currentRow + (event.key === Qt.Key_Down ? 1 : -1))), false);
                positionViewAtIndex(root.currentRow, ListView.Contain); event.accepted = true;
            } else if (event.key === Qt.Key_Right || event.key === Qt.Key_Left || event.key === Qt.Key_Space) {
                root.toggle(root.currentRow); event.accepted = true;
            } else if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) {
                if (root.currentRow >= 0 && root.currentRow < root.rows.length) {
                    if (root.rows[root.currentRow].folder) root.toggle(root.currentRow);
                    else root.activated(root.currentIndex);
                }
                event.accepted = true;
            }
        }
        delegate: Rectangle {
            width: list.width
            height: 48
            color: root.selectedKeys.indexOf(modelData.key) !== -1 ? "#276a9c" : (index % 2 ? "#303030" : "#383838")
            Label { x: 8 + modelData.depth * 18; anchors.verticalCenter: parent.verticalCenter; text: modelData.folder ? (root.expanded[modelData.key] ? "▾ " : "▸ ") + modelData.name : modelData.name; color: "white"; width: parent.width - x - (status.width + 12); elide: Text.ElideRight }
            Label { id: status; anchors.right: parent.right; anchors.rightMargin: 8; anchors.verticalCenter: parent.verticalCenter; text: modelData.status; color: "#dddddd"; width: Math.min(implicitWidth, parent.width / 3); elide: Text.ElideRight }
            MouseArea {
                objectName: "nativeTreeRow" + index
                anchors.fill: parent
                hoverEnabled: true
                onClicked: function(mouse) {
                    root.selectRow(index, (mouse.modifiers & Qt.ControlModifier) !== 0);
                    list.forceActiveFocus();
                    if (modelData.folder && mouse.x < 40 + modelData.depth * 18) root.toggle(index);
                }
                onDoubleClicked: { if (modelData.folder) root.toggle(index); else root.activated(modelData.index); }
                ToolTip.visible: containsMouse
                ToolTip.delay: 600
                ToolTip.text: modelData.path
            }
        }
        Label { anchors.centerIn: parent; visible: root.rows.length === 0; text: "No matching items"; color: "#cccccc" }
    }
}
