// Copyright 2026 Overte contributors.
// SPDX-License-Identifier: Apache-2.0
import QtQuick 2.7
import QtQuick.Controls 2.3
import QtQuick.Layouts 1.3
import Qt.labs.folderlistmodel 2.2
import controlsUit 1.0 as HifiControls
import "../hifi/dialogs"

Rectangle {
    id: root
    objectName: "nativeFileBrowser"
    anchors.fill: parent
    z: 1000
    color: "#292929"
    property string caption: "Select file"
    property alias title: root.caption
    property url dir: helper.home()
    property string filter: "All files (*)"
    property int options: 0
    property bool selectDirectory: false
    property bool showHidden: true
    property bool multiSelect: false
    property bool saveDialog: false
    property var helper: fileDialogHelper
    property alias model: files
    property var chosen: []
    property var backStack: []
    property string requestId: ""
    property string error: ""
    property bool closing: false
    property bool destroyOnCompletion: true
    readonly property var filters: filter.split(";;")
    readonly property var patterns: {
        var current = filters[filterBox.currentIndex] || "All files (*)";
        var match = /\(([^)]+)\)/.exec(current);
        return match ? match[1].split(/\s+/).filter(function(value) { return value.length > 0; }) : ["*"];
    }
    signal selectedFile(var file)
    signal selectedFiles(var files)
    signal canceled()
    function finish(urls) {
        if (closing || !urls.length) return;
        closing = true;
        selectedFiles(urls);
        selectedFile(urls[0]);
        if (destroyOnCompletion) Qt.callLater(function() { root.destroy(); });
    }
    function cancel() {
        if (closing) return;
        closing = true;
        if (requestId) helper.cancelDocuments(requestId);
        canceled();
        if (destroyOnCompletion) Qt.callLater(function() { root.destroy(); });
    }
    function openSystemPicker() {
        error = "";
        requestId = helper.openDocuments(caption, filter, multiSelect);
        if (!requestId) error = "The system document picker is unavailable or already in use.";
    }
    function enterDirectory(url, remember) {
        if (remember !== false && String(url) !== String(dir)) backStack = backStack.concat([String(dir)]);
        dir = url;
        chosen = [];
        filename.text = "";
        error = "";
    }
    function choose(row) {
        if (files.isFolder(row)) { enterDirectory(files.get(row, "fileUrl")); return; }
        var url = files.get(row, "fileUrl");
        if (!url) url = files.get(row, "fileURL");
        if (multiSelect) {
            var selection = chosen.slice(), position = selection.indexOf(String(url));
            if (position < 0) selection.push(String(url)); else selection.splice(position, 1);
            chosen = selection;
        } else chosen = [String(url)];
        filename.text = files.get(row, "fileName");
    }
    function accept() {
        var url;
        error = "";
        if (selectDirectory) {
            url = filename.text ? helper.pathToUrl(filename.text.charAt(0) === "/" ? filename.text : helper.urlToPath(dir) + "/" + filename.text) : dir;
            if (!helper.urlIsDir(url)) { error = "Select an existing folder."; return; }
            finish([url]);
        } else if (saveDialog) {
            url = helper.saveHelper(filename.text, dir, patterns);
            if (!url || !filename.text.trim()) { error = "Enter a valid filename."; return; }
            if (!helper.urlIsWritable(url)) { error = "The selected location is not writable."; return; }
            if (helper.urlExists(url)) { overwrite.open(); return; }
            finish([url]);
        } else if (multiSelect && chosen.length) {
            if (!chosen.every(function(selected) { return helper.urlIsFile(selected); })) { error = "A selected file is no longer available."; return; }
            finish(chosen);
        } else {
            var path = filename.text.trim();
            url = helper.pathToUrl(path.charAt(0) === "/" || /^[A-Za-z]:[\\/]/.test(path) ? path : helper.urlToPath(dir) + "/" + path);
            if (helper.urlIsDir(url)) { enterDirectory(url); return; }
            if (!helper.urlIsFile(url)) { error = "Select an existing file."; return; }
            finish([url]);
        }
    }
    onDirChanged: pathInput.text = helper.urlToPath(dir)
    Component.onCompleted: pathInput.text = helper.urlToPath(dir)
    Component.onDestruction: { closing = true; if (requestId) helper.cancelDocuments(requestId); }
    Connections {
        target: root.helper
        function onDocumentsSelected(id, urls) { if (!root.closing && id === root.requestId) { root.requestId = ""; root.finish(urls); } }
        function onDocumentSelectionCanceled(id) { if (id === root.requestId) root.requestId = ""; }
        function onDocumentSelectionFailed(id, message) { if (id === root.requestId) { root.requestId = ""; root.error = message; } }
        function onContentsChanged() { var folder = files.folder; files.folder = ""; files.folder = folder; }
    }
    FolderListModel { id: files; folder: root.dir; nameFilters: root.patterns; showDirs: true; showHidden: root.showHidden; showDotAndDotDot: false; sortField: [FolderListModel.Name, FolderListModel.Size, FolderListModel.Time][sortBox.currentIndex]; sortReversed: descending.checked }
    HifiControls.TouchUiMetrics { id: metrics }
    ColumnLayout {
        anchors.fill: parent; anchors.margins: 12; spacing: 8
        Label { text: root.caption; color: "white"; font.pixelSize: 22; Layout.fillWidth: true; wrapMode: Text.WordWrap }
        RowLayout {
            Layout.fillWidth: true
            Button { objectName: "fileBack"; text: "Back"; implicitHeight: 48; enabled: root.backStack.length > 0; onClicked: { var stack = root.backStack.slice(), previous = stack.pop(); root.backStack = stack; root.enterDirectory(previous, false); } }
            Button { objectName: "fileUp"; text: "Up"; implicitHeight: 48; enabled: String(files.parentFolder).length > 0; onClicked: root.enterDirectory(files.parentFolder) }
            TextField { id: pathInput; objectName: "fileFolderPath"; Layout.fillWidth: true; implicitHeight: 48; onAccepted: { var url = root.helper.pathToUrl(text); if (root.helper.urlIsDir(url)) root.enterDirectory(url); else root.error = "Folder unavailable."; } }
        }
        RowLayout {
            Layout.fillWidth: true
            Button { objectName: "fileHome"; text: "Home"; implicitHeight: 48; onClicked: root.enterDirectory(root.helper.home()) }
            ComboBox { model: root.helper.drives(); Layout.fillWidth: true; implicitHeight: 48; onActivated: root.enterDirectory(root.helper.pathToUrl(currentText)) }
            CheckBox { text: "Hidden"; checked: root.showHidden; onToggled: root.showHidden = checked }
        }
        RowLayout {
            Layout.fillWidth: true
            ComboBox { id: sortBox; objectName: "fileSort"; model: ["Name", "Size", "Modified"]; Layout.fillWidth: true; implicitHeight: 48 }
            CheckBox { id: descending; text: "Descending" }
        }
        ListView {
            id: list; objectName: "fileList"; Layout.fillWidth: true; Layout.fillHeight: true; clip: true; model: files
            ScrollBar.vertical: ScrollBar {}
            Keys.onReturnPressed: { if (currentIndex >= 0) { root.choose(currentIndex); if (!files.isFolder(currentIndex)) root.accept(); } }
            delegate: ItemDelegate { objectName: "fileRow" + index; width: list.width; height: 48; text: (fileIsDir ? "▸ " : "") + fileName + (fileIsDir ? "" : " · " + fileSize + " bytes"); highlighted: root.chosen.indexOf(String(fileUrl)) !== -1; onClicked: root.choose(index) }
        }
        ComboBox { id: filterBox; objectName: "fileFilter"; model: root.filters; Layout.fillWidth: true; implicitHeight: 48 }
        TextField { id: filename; objectName: "fileNameInput"; placeholderText: root.selectDirectory ? "Folder path" : "Filename or full path"; Layout.fillWidth: true; implicitHeight: 48; onAccepted: root.accept() }
        Label { text: root.error; visible: text.length > 0; color: "#ffaaaa"; wrapMode: Text.WordWrap; Layout.fillWidth: true }
        Flow {
            Layout.fillWidth: true; spacing: 8
            Button { objectName: "systemDocumentPicker"; text: "System documents"; implicitHeight: 48; visible: !root.saveDialog && !root.selectDirectory; enabled: !root.requestId; onClicked: root.openSystemPicker() }
            Button { objectName: "fileAccept"; text: root.saveDialog ? "Save" : "Select"; implicitHeight: 48; enabled: !root.requestId; onClicked: root.accept() }
            Button { objectName: "fileCancel"; text: "Cancel"; implicitHeight: 48; onClicked: root.cancel() }
        }
        NativeKeyboardHost { Layout.fillWidth: true; Layout.preferredHeight: implicitHeight; inputFocused: filename.activeFocus || pathInput.activeFocus }
    }
    Dialog {
        id: overwrite; objectName: "fileOverwriteDialog"; title: "Replace existing file?"; modal: true; x: Math.max(0, (root.width - width) / 2); y: Math.max(0, (root.height - height) / 2)
        standardButtons: Dialog.Yes | Dialog.No
        onAccepted: root.finish([root.helper.saveHelper(filename.text, root.dir, root.patterns)])
    }
}
