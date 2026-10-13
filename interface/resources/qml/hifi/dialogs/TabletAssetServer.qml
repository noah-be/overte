// Copyright 2017 High Fidelity, Inc.
// Copyright 2026 Overte contributors.
// SPDX-License-Identifier: Apache-2.0
import QtQuick 2.7
import QtQuick.Controls 2.3
import QtQuick.Layouts 1.3
import controlsUit 1.0 as HifiControls
import "../../dialogs"

Rectangle {
    id: root
    objectName: "AssetServer"
    color: "#292929"
    implicitWidth: 600
    implicitHeight: 700
    property string title: "Asset Browser"
    property var assetProxyModel: Assets.proxyModel
    property var assetMappingsModel: Assets.mappingModel
    property var currentDirectory: fileDialogHelper.home()
    property bool assetWriteAllowed: Entities.canWriteAssets()
    property bool importAllowed: Entities.canRez() || Entities.canRezTmp()
    property bool busy: false
    property string status: ""
    property var lifecycle: ({active: true})
    readonly property int updatesCount: tree.revision
    readonly property int selectedItemCount: tree.selectedIndexes.length
    readonly property var currentIndex: tree.currentIndex
    readonly property string selectedUrl: currentIndex !== null ? String(assetProxyModel.data(currentIndex, 259) || "") : ""
    readonly property string selectedPath: currentIndex !== null ? String(assetProxyModel.data(currentIndex, 256) || "") : ""
    signal sendToScript(var message)
    function writable() {
        assetWriteAllowed = Entities.canWriteAssets();
        if (!assetWriteAllowed) status = "You can browse assets; writing requires Asset Server permission.";
        return assetWriteAllowed;
    }
    function reload() { assetMappingsModel.refresh(); }
    function selectedPaths() {
        return tree.selectedIndexes.map(function(index) { return String(assetProxyModel.data(index, 256) || ""); }).filter(function(path) { return path.length > 0; });
    }
    function normalizedPath(path) {
        path = String(path).trim();
        if (path.charAt(0) !== "/") path = "/" + path;
        if (path.split("/").some(function(part) { return part === "." || part === ".."; })) return "";
        return path;
    }
    function resultHandler(operation, done) {
        var lifetime = lifecycle;
        return function(error) {
            if (!lifetime.active) return;
            busy = false;
            status = error ? operation + " failed: " + String(error) : operation + " complete.";
            if (done) done(error);
            reload();
        };
    }
    function doDeleteFile(paths) {
        if (!writable() || busy || !paths.length) return;
        busy = true;
        Assets.deleteMappings(paths, resultHandler("Delete"));
    }
    function doRenameFile(oldPath, newPath) {
        if (!writable() || busy || !oldPath) return;
        newPath = normalizedPath(newPath);
        if (!newPath || newPath === "/") { status = "Enter a valid asset path."; return; }
        if (oldPath.slice(-1) === "/" && newPath.slice(-1) !== "/") newPath += "/";
        if (Assets.isKnownFolder(newPath)) { status = "Cannot overwrite an existing folder."; return; }
        if (Assets.isKnownMapping(newPath) && newPath !== oldPath) {
            pendingRenameOld = oldPath; pendingRenameNew = newPath; overwriteDialog.open(); return;
        }
        busy = true;
        Assets.renameMapping(oldPath, newPath, resultHandler("Rename"));
    }
    property string pendingRenameOld: ""
    property string pendingRenameNew: ""
    function setMapping(path, hash) {
        if (!writable() || busy) return;
        path = normalizedPath(path); hash = String(hash).trim().toLowerCase();
        if (!path || path === "/" || !/^[a-f0-9]{64}$/.test(hash)) { status = "Provide an asset path and a 64-digit SHA-256 hash."; return; }
        busy = true;
        Assets.setMapping(path, hash, resultHandler("Mapping"));
    }
    function bakingAvailable() {
        var revision = tree.revision;
        var indexes = tree.selectedIndexes;
        if (tree.currentIndex === null || !indexes.length) return false;
        var states = indexes.map(function(index) { return assetProxyModel.data(index, 261); });
        return states.indexOf("--") === -1 && states.every(function(state) { return (state !== "Not Baked") === (states[0] !== "Not Baked"); });
    }
    function setBakingEnabled(enabled) {
        if (!writable() || busy || !bakingAvailable()) return;
        busy = true;
        Assets.setBakingEnabled(selectedPaths(), enabled, resultHandler("Baking selection"));
    }
    function canAddToWorld(url) { return selectedItemCount === 1 && /\.(fbx|obj|gltf|glb|vrm|jpg|jpeg|png)(?:[?#]|$)/i.test(url); }
    function importSucceeded(id) {
        status = !id || !String(id).replace(/[0{}-]/g, "") ? "Import failed: entity creation was denied or unavailable." : "Added asset to the world.";
    }
    function addToWorld() {
        if (!canAddToWorld(selectedUrl)) return;
        if (!Entities.canRez() && !Entities.canRezTmp()) { status = "You do not have permission to create entities."; return; }
        var grabbable = MenuInterface.isOptionChecked("Create Entities As Grabbable (except Zones, Particles, and Lights)");
        var position = Vec3.sum(MyAvatar.position, Vec3.multiply(2, Quat.getForward(MyAvatar.orientation)));
        var name = String(assetProxyModel.data(currentIndex, 0));
        if (/\.(jpg|jpeg|png)(?:[?#]|$)/i.test(selectedUrl)) {
            importSucceeded(Entities.addImageEntity(name, selectedUrl, grabbable, position));
        } else {
            modelUrl.text = selectedUrl;
            modelName = name;
            modelPosition = position;
            shape.currentIndex = 2;
            dynamic.checked = false;
            modelDialog.open();
        }
    }
    property string modelName: ""
    property var modelPosition
    function importModel() {
        if (!Entities.canRez() && !Entities.canRezTmp()) { status = "You do not have permission to create entities."; return; }
        var types = ["none", "simple-hull", "simple-compound", "static-mesh", "box", "sphere"];
        var type = types[shape.currentIndex];
        if (type === "static-mesh" && dynamic.checked) { status = "A static mesh cannot be dynamic."; return; }
        var gravity = Vec3.multiply(Vec3.fromPolar(Math.PI / 2, 0), dynamic.checked ? 10 : 0);
        importSucceeded(Entities.addModelEntity(modelName, modelUrl.text.trim(), "", type, dynamic.checked, type === "none",
            MenuInterface.isOptionChecked("Create Entities As Grabbable (except Zones, Particles, and Lights)"), modelPosition, gravity));
    }
    function uploadFile(url, dropping) {
        if (!writable() || busy) return;
        var local = fileDialogHelper.urlToPath(url);
        if (!local || !fileDialogHelper.urlIsFile(url)) { status = "Select a readable local document."; return; }
        var folder = selectedPath ? selectedPath.slice(0, selectedPath.lastIndexOf("/") + 1) : "/";
        var name = local.replace(/\\/g, "/").split("/").pop();
        var lifetime = lifecycle;
        busy = true;
        status = "Preparing upload...";
        Assets.uploadFile(local, folder + name, function() { if (lifetime.active) status = "Uploading " + name; },
            resultHandler("Upload", function(error) { if (error === -1) status = "Upload canceled."; }), dropping === true);
    }
    function uploadClicked(url) {
        if (!writable() || busy) return;
        if (url) { uploadFile(url, true); return; }
        var browser = fileBrowser.createObject(root, {dir: currentDirectory});
        if (!browser) { status = "The file browser is unavailable."; return; }
        browser.selectedFile.connect(function(selected) { currentDirectory = browser.dir; Qt.callLater(function() { root.uploadFile(selected, false); }); });
    }
    Component.onCompleted: { assetMappingsModel.autoRefreshEnabled = true; reload(); }
    Component.onDestruction: { lifecycle.active = false; assetMappingsModel.autoRefreshEnabled = false; }
    Connections {
        target: root.assetMappingsModel
        function onErrorGettingMappings(message) { root.status = "Could not browse assets: " + message; }
    }
    Connections {
        target: ApplicationInterface
        function onUploadRequest(url) { root.uploadClicked(url); }
    }
    Connections {
        target: Entities
        function onCanWriteAssetsChanged(allowed) { root.assetWriteAllowed = allowed; }
        function onCanRezChanged() { root.importAllowed = Entities.canRez() || Entities.canRezTmp(); }
        function onCanRezTmpChanged() { root.importAllowed = Entities.canRez() || Entities.canRezTmp(); }
    }
    HifiControls.TouchUiMetrics { id: metrics }
    Component { id: fileBrowser; NativeFileBrowser {} }
    DropArea { anchors.fill: parent; onDropped: function(drop) { if (drop.hasUrls && drop.urls.length === 1 && root.writable()) { root.uploadFile(drop.urls[0], true); drop.acceptProposedAction(); } } }
    ColumnLayout {
        anchors.fill: parent; anchors.margins: 12; spacing: 8
        Label { text: root.title; font.pixelSize: 22; color: "white"; Layout.fillWidth: true }
        Label { text: root.assetWriteAllowed ? "Browse and manage domain assets" : "Browse domain assets · writing unavailable"; color: "#cccccc"; Layout.fillWidth: true; wrapMode: Text.WordWrap }
        Flow {
            Layout.fillWidth: true; spacing: 8
            Button { objectName: "assetRefresh"; text: "Refresh"; implicitHeight: 48; onClicked: root.reload() }
            Button { objectName: "assetImport"; text: "Add to World"; implicitHeight: 48; enabled: root.importAllowed && root.canAddToWorld(root.selectedUrl); onClicked: root.addToWorld() }
            Button { objectName: "assetCopyUrl"; text: "Copy URL"; implicitHeight: 48; enabled: root.selectedUrl.length > 0; onClicked: Window.copyToClipboard(root.selectedUrl) }
        }
        TextField { id: search; objectName: "assetFilter"; placeholderText: "Filter assets and folders"; Layout.fillWidth: true; implicitHeight: 48; onTextChanged: tree.filterText = text }
        CheckBox { text: "Select multiple"; checked: tree.multiSelect; onToggled: tree.multiSelect = checked }
        NativeModelTree { id: tree; objectName: "assetTree"; Layout.fillWidth: true; Layout.fillHeight: true; sourceModel: root.assetProxyModel; folderRole: 257; statusRole: 261 }
        Label { text: root.selectedUrl; color: "#cccccc"; elide: Text.ElideMiddle; Layout.fillWidth: true }
        Label { text: root.updatesCount, root.currentIndex !== null ? String(root.assetProxyModel.data(root.currentIndex, 262) || "") : ""; visible: text.length > 0; color: "#ffaaaa"; wrapMode: Text.WordWrap; Layout.fillWidth: true }
        CheckBox { objectName: "assetBaking"; text: "Use baked version"; enabled: root.assetWriteAllowed && !root.busy && root.bakingAvailable(); checked: root.currentIndex !== null && root.bakingAvailable() && root.assetProxyModel.data(root.currentIndex, 261) !== "Not Baked"; onToggled: root.setBakingEnabled(checked) }
        Flow {
            Layout.fillWidth: true; spacing: 8
            Button { objectName: "assetUpload"; text: "Upload"; implicitHeight: 48; enabled: root.assetWriteAllowed && !root.busy; onClicked: root.uploadClicked() }
            Button { objectName: "assetRename"; text: "Rename"; implicitHeight: 48; enabled: root.assetWriteAllowed && !root.busy && root.selectedItemCount === 1; onClicked: { renamePath.text = root.selectedPath; renameDialog.open(); } }
            Button { objectName: "assetDelete"; text: "Delete"; implicitHeight: 48; enabled: root.assetWriteAllowed && !root.busy && root.selectedItemCount > 0; onClicked: deleteDialog.open() }
            Button { objectName: "assetMapping"; text: "Set Mapping"; implicitHeight: 48; enabled: root.assetWriteAllowed && !root.busy; onClicked: mappingDialog.open() }
        }
        BusyIndicator { running: root.busy; visible: running; Layout.preferredHeight: 36 }
        Label { objectName: "assetStatus"; text: root.status; color: "#cccccc"; wrapMode: Text.WordWrap; Layout.fillWidth: true; visible: text.length > 0 }
        NativeKeyboardHost { id: inputKeyboard; Layout.fillWidth: true; Layout.preferredHeight: implicitHeight; inputFocused: search.activeFocus }
    }
    Dialog {
        id: renameDialog
        objectName: "renameDialog"
        title: "Rename asset or folder"
        modal: true; focus: true
        width: Math.min(root.width - 24, 500)
        x: (root.width - width) / 2
        y: Math.max(0, (root.height - height) / 2)
        standardButtons: Dialog.Ok | Dialog.Cancel
        Column {
            width: parent.width
            TextField {
                id: renamePath
                objectName: "assetRenamePath"
                width: parent.width; implicitHeight: 48
                Keys.onEscapePressed: function(event) { renameDialog.reject(); event.accepted = true; }
            }
            NativeKeyboardHost { width: parent.width; inputFocused: renameDialog.visible && renamePath.activeFocus }
        }
        onClosed: tree.view.forceActiveFocus()
        onAccepted: root.doRenameFile(root.selectedPath, renamePath.text)
    }
    Dialog {
        id: overwriteDialog
        title: "Overwrite existing mapping?"
        modal: true; focus: true
        width: Math.min(root.width - 24, 500)
        x: (root.width - width) / 2
        y: Math.max(0, (root.height - height) / 2)
        standardButtons: Dialog.Yes | Dialog.No
        onAccepted: {
            if (root.writable() && !root.busy) {
                root.busy = true;
                Assets.renameMapping(root.pendingRenameOld, root.pendingRenameNew, root.resultHandler("Rename"));
            }
        }
    }
    Dialog {
        id: deleteDialog
        title: "Delete selected mappings?"
        modal: true; focus: true
        width: Math.min(root.width - 24, 500)
        x: (root.width - width) / 2
        y: Math.max(0, (root.height - height) / 2)
        standardButtons: Dialog.Yes | Dialog.No
        Label { text: root.selectedPaths().join("\n"); wrapMode: Text.WordWrap; width: Math.max(100, Math.min(root.width - 60, 500)) }
        onAccepted: root.doDeleteFile(root.selectedPaths())
    }
    Dialog {
        id: mappingDialog
        objectName: "mappingDialog"
        title: "Set asset mapping"
        modal: true; focus: true
        width: Math.min(root.width - 24, 500)
        x: (root.width - width) / 2
        y: Math.max(0, (root.height - height) / 2)
        standardButtons: Dialog.Ok | Dialog.Cancel
        Column {
            width: parent.width
            TextField {
                id: mappingPath
                objectName: "assetMappingPath"
                width: parent.width; implicitHeight: 48
                placeholderText: "/asset/path"
                Keys.onEscapePressed: function(event) { mappingDialog.reject(); event.accepted = true; }
            }
            TextField {
                id: mappingHash
                objectName: "assetMappingHash"
                width: parent.width; implicitHeight: 48
                placeholderText: "SHA-256 hash"
                Keys.onEscapePressed: function(event) { mappingDialog.reject(); event.accepted = true; }
            }
            NativeKeyboardHost { width: parent.width; inputFocused: mappingDialog.visible && (mappingPath.activeFocus || mappingHash.activeFocus) }
        }
        onClosed: tree.view.forceActiveFocus()
        onAccepted: root.setMapping(mappingPath.text, mappingHash.text)
    }
    Dialog {
        id: modelDialog
        objectName: "modelDialog"
        title: "Import model"
        modal: true; focus: true
        width: Math.min(root.width - 24, 500)
        x: (root.width - width) / 2
        y: Math.max(0, (root.height - height) / 2)
        standardButtons: Dialog.Ok | Dialog.Cancel
        Column {
            width: parent.width; spacing: 8
            TextField {
                id: modelUrl
                objectName: "assetModelUrl"
                width: parent.width; implicitHeight: 48
                Keys.onEscapePressed: function(event) { modelDialog.reject(); event.accepted = true; }
            }
            ComboBox {
                id: shape
                objectName: "assetModelShape"
                width: parent.width; implicitHeight: 48
                model: ["No Collision", "Basic · whole model", "Good · sub-meshes", "Exact · static polygons", "Box", "Sphere"]
            }
            CheckBox {
                id: dynamic
                objectName: "assetModelDynamic"
                text: "Dynamic"
                enabled: shape.currentIndex !== 3
                onEnabledChanged: { if (!enabled) checked = false; }
            }
            NativeKeyboardHost { width: parent.width; inputFocused: modelDialog.visible && modelUrl.activeFocus }
        }
        onClosed: tree.view.forceActiveFocus()
        onAccepted: root.importModel()
    }
}
