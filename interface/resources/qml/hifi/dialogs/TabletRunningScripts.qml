// Copyright 2016 High Fidelity, Inc.
// Copyright 2026 Overte contributors.
// SPDX-License-Identifier: Apache-2.0
import QtQuick 2.7
import QtQuick.Controls 2.3
import QtQuick.Layouts 1.3
import controlsUit 1.0 as HifiControls

Rectangle {
    id: root
    objectName: "RunningScripts"
    color: "#292929"
    implicitWidth: 600
    implicitHeight: 700
    property string title: "Running Scripts"
    property var scripts: ScriptDiscoveryService
    property var scriptsModel: scripts.scriptsModelFilter
    property var runningScriptsModel: []
    property bool developerMenuEnabled: false
    property bool isHMD: HMD.active
    property string status: ""
    signal sendToScript(var message)
    function filename(url) { return String(url).split(/[?#]/)[0].replace(/\\/g, "/").split("/").pop(); }
    function canEditScript(url) { var name = filename(url); return developerMenuEnabled || (name !== "controllerScripts.js" && name !== "defaultScripts.js"); }
    function updateRunningScripts() {
        var list = scripts.getRunning().slice();
        list.sort(function(a, b) { var aa = filename(a.url || a.path).toLowerCase(), bb = filename(b.url || b.path).toLowerCase(); return aa < bb ? -1 : aa > bb ? 1 : 0; });
        runningScriptsModel = list;
    }
    function loadScript(url) {
        if (!String(url).trim()) return;
        if (/^atp:/i.test(String(url).trim())) { status = "Client scripts cannot be loaded over ATP."; return; }
        status = "Loading " + filename(url);
        scripts.loadOneScript(String(url).trim());
    }
    function reloadScript(url) { if (canEditScript(url)) { scripts.stopScript(url, true); status = "Restarting " + filename(url); } }
    function stopScript(url) { if (canEditScript(url)) { scripts.stopScript(url); status = "Stopping " + filename(url); } }
    function reloadAll() {
        if (developerMenuEnabled) scripts.reloadAllScripts();
        else runningScriptsModel.forEach(function(script) { root.reloadScript(script.url || script.path); });
    }
    function stopAll() { runningScriptsModel.forEach(function(script) { root.stopScript(script.url || script.path); }); }
    function loadDefaults() { if (developerMenuEnabled) loadScript(scripts.defaultScriptsPath + "/defaultScripts.js"); }
    Component.onCompleted: { developerMenuEnabled = MenuInterface.isOptionChecked("Developer Menu"); updateRunningScripts(); }
    Connections {
        target: root.scripts
        function onScriptCountChanged() { root.updateRunningScripts(); }
        function onScriptLoadError(url, error) { root.status = "Failed to load " + String(url) + (error ? ": " + error : ""); }
    }
    Timer { interval: 1000; repeat: true; running: root.visible; onTriggered: root.developerMenuEnabled = MenuInterface.isOptionChecked("Developer Menu") }
    HifiControls.TouchUiMetrics { id: metrics }
    ColumnLayout {
        anchors.fill: parent; anchors.margins: 12; spacing: 8
        Label { text: root.title; color: "white"; font.pixelSize: 22; Layout.fillWidth: true }
        Flow {
            Layout.fillWidth: true; spacing: 8
            Button { objectName: "scriptReloadAll"; text: "Reload All"; implicitHeight: 48; onClicked: root.reloadAll() }
            Button { objectName: "scriptStopAll"; text: "Stop All"; implicitHeight: 48; onClicked: root.stopAll() }
            Button { objectName: "scriptLoadDefaults"; text: "Load Defaults"; visible: root.developerMenuEnabled; implicitHeight: 48; onClicked: root.loadDefaults() }
        }
        ListView {
            id: running; objectName: "runningScriptList"; Layout.fillWidth: true; Layout.preferredHeight: Math.min(220, root.height / 3); clip: true; model: root.runningScriptsModel
            ScrollBar.vertical: ScrollBar {}
            delegate: RowLayout {
                width: running.width; height: 48
                Label { text: root.filename(modelData.url || modelData.path); color: "white"; Layout.fillWidth: true; elide: Text.ElideMiddle; ToolTip.text: modelData.url || modelData.path; ToolTip.visible: scriptHover.containsMouse; MouseArea { id: scriptHover; anchors.fill: parent; hoverEnabled: true; acceptedButtons: Qt.NoButton } }
                Button { objectName: "scriptRestart" + index; text: "Restart"; enabled: root.canEditScript(modelData.url || modelData.path); implicitHeight: 48; onClicked: root.reloadScript(modelData.url || modelData.path) }
                Button { objectName: "scriptStop" + index; text: "Stop"; enabled: root.canEditScript(modelData.url || modelData.path); implicitHeight: 48; onClicked: root.stopScript(modelData.url || modelData.path) }
            }
        }
        Flow {
            Layout.fillWidth: true; spacing: 8
            Button { objectName: "scriptFromUrl"; text: "From URL"; implicitHeight: 48; onClicked: ApplicationInterface.loadScriptURLDialog() }
            Button { objectName: "scriptFromFile"; text: "From File"; implicitHeight: 48; onClicked: ApplicationInterface.loadDialog() }
            Button { objectName: "scriptLoadSelected"; text: "Load Selected"; implicitHeight: 48; enabled: browser.currentIndex !== null && !!root.scriptsModel.data(browser.currentIndex, 256); onClicked: root.loadScript(root.scriptsModel.data(browser.currentIndex, 256)) }
        }
        TextField { objectName: "scriptFilter"; placeholderText: "Filter installed scripts"; Layout.fillWidth: true; implicitHeight: 48; onTextChanged: browser.filterText = text; id: filter }
        NativeModelTree { id: browser; objectName: "scriptTree"; Layout.fillWidth: true; Layout.fillHeight: true; sourceModel: root.scriptsModel; onActivated: function(index) { root.loadScript(root.scriptsModel.data(index, 256)); } }
        Label { text: root.status; color: "#cccccc"; wrapMode: Text.WordWrap; Layout.fillWidth: true; visible: text.length > 0 }
        NativeKeyboardHost { Layout.fillWidth: true; Layout.preferredHeight: implicitHeight; inputFocused: filter.activeFocus }
    }
}
