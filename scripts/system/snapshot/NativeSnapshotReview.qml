// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0
import QtQuick 2.7
import QtQuick 2.7 as Quick
import QtQuick.Controls 2.3 as Controls
import QtQuick.Layouts 1.3

Rectangle {
    id: root
    color: "#17212a"
    signal sendToScript(var message)
    property var images: []
    property bool capturing: false
    property bool processing: false
    property bool loggedIn: false
    property bool canShare: false
    property bool canBlast: false
    property string statusText: qsTr("Take a snapshot. Captures are saved in the app.")
    property bool statusError: false
    property string uploadPath: ""
    property string exportTicket: ""
    property bool printEnabled: false
    property bool printProcessing: false
    property bool keyboardEnabled: true
    property bool keyboardRaised: false
    property bool punctuationMode: false
    property var keyboardItem: null
    onKeyboardRaisedChanged: {
        if (typeof KeyboardScriptingInterface !== "undefined" && KeyboardScriptingInterface.use3DKeyboard) {
            KeyboardScriptingInterface.raised = keyboardRaised
        }
    }
    Component.onCompleted: {
        if (typeof KeyboardScriptingInterface !== "undefined" && !KeyboardScriptingInterface.use3DKeyboard) {
            keyboardItem = Qt.createQmlObject('import QtQuick 2.7; import controlsUit 1.0; Keyboard {'
                + ' anchors.bottom: parent.bottom; raised: parent.keyboardEnabled && parent.keyboardRaised;'
                + ' numeric: parent.punctuationMode }', root, "SnapshotKeyboard")
        }
        send("ready")
    }
    Component.onDestruction: {
        cancelExport()
        send("cancelSnapshotCapture")
        send("cancelSnapshotUpload", { path: uploadPath })
        if (typeof KeyboardScriptingInterface !== "undefined" && KeyboardScriptingInterface.use3DKeyboard) {
            KeyboardScriptingInterface.raised = false
        }
    }

    SnapshotPlatform {
        id: platform
        onCompleted: function(ticket, status, error) {
            if (ticket !== root.exportTicket) { return }
            root.exportTicket = ""
            root.statusError = status === "error"
            root.statusText = status === "success" ? qsTr("System save or sharing finished.")
                : status === "cancelled" ? qsTr("System request cancelled.")
                : qsTr("System save or sharing failed: ") + error
        }
    }
    function send(action, value) {
        var message = value || {}
        message.type = "snapshot"
        message.action = action
        sendToScript(message)
    }
    function cancelExport() {
        if (exportTicket) { statusText = qsTr("Cancellation requested. Waiting for the system result."); platform.cancel(exportTicket) }
    }
    function exportImage(path, action) {
        statusError = false
        exportTicket = platform.request(path, action)
        if (!exportTicket) { statusError = true; statusText = platform.error || qsTr("System request could not start.") }
        else { statusText = action === "save" ? qsTr("Waiting for system save…") : qsTr("Waiting for system sharing…") }
    }
    function imageUrl(path) {
        return typeof Snapshot !== "undefined" ? Snapshot.snapshotFileUrl(path) : ""
    }
    function updateImages(rows, appendGif) {
        var next = appendGif ? images.filter(function(row) { return !isGif(row.localPath) }) : []
        ;(rows || []).slice(0, 8).forEach(function(row) { if (row.localPath) { next.push(row) } })
        images = next
    }
    function isGif(path) { return /\.gif$/i.test(path || "") }
    function upload(path) {
        uploadPath = path
        statusError = false
        statusText = qsTr("Uploading snapshot…")
        send("shareSnapshotForUrl", { data: path })
    }
    function fromScript(message) {
        if (!message || message.type !== "snapshot") { return }
        var options = message.options || {}
        if (message.action === "showPreviousImages" || message.action === "addImages") {
            loggedIn = options.isLoggedIn === true
            canShare = options.canShare === true || message.canShare === true
            canBlast = options.canBlast === true
            processing = options.processingGif === true
            updateImages(message.image_data, message.action === "addImages" && options.containsGif && !processing)
            if (!processing) { capturing = false }
        } else if (message.action === "clearPreviousImages") {
            images = []; capturing = true; processing = false; uploadPath = ""
            statusError = false; statusText = qsTr("Capturing snapshot…")
        } else if (message.action === "captureStatus") {
            capturing = message.phase === "capturing" || message.phase === "processing"
            processing = message.phase === "processing"
            statusError = message.phase === "error"
            statusText = message.phase === "complete" ? qsTr("Snapshot saved in the app.")
                : message.phase === "cancelled" ? qsTr("Capture cancelled.")
                : message.phase === "error" ? qsTr("Capture failed: ") + (message.error || "capture-failed")
                : message.phase === "processing" ? qsTr("Processing snapshot…") : qsTr("Capturing snapshot…")
        } else if (message.action === "snapshotUploadComplete") {
            images = images.map(function(row) {
                if (isGif(row.localPath) === isGif(message.image_url)) {
                    var next = JSON.parse(JSON.stringify(row)); next.story_id = message.story_id; return next
                }
                return row
            })
        } else if (message.action === "uploadStatus") {
            if (message.path !== uploadPath) { return }
            uploadPath = ""
            statusError = message.status === "error"
            statusText = message.status === "success" ? qsTr("Uploaded. Choose a sharing audience below.")
                : message.status === "cancelled" ? qsTr("Upload cancelled. The server may already have received data.")
                : qsTr("Upload failed: ") + (message.error || "upload-failed")
        } else if (message.action === "snapshotError") {
            statusError = true; statusText = message.error || qsTr("Snapshot operation failed.")
            uploadPath = ""
        } else if (message.action === "captureSettings") {
            captureMode.currentIndex = message.setting ? 1 : 0
        } else if (message.action === "setPrintButtonEnabled") {
            printEnabled = true; printProcessing = false
        } else if (message.action === "setPrintButtonLoading") {
            printEnabled = false; printProcessing = true
        } else if (message.action === "setPrintButtonDisabled") {
            printEnabled = false; printProcessing = false
        }
    }

    Controls.ScrollView {
        id: scroll
        anchors.fill: parent
        anchors.margins: 16
        contentWidth: availableWidth
        ColumnLayout {
            width: scroll.availableWidth
            spacing: 12
            Quick.Text { text: qsTr("Snapshots"); color: "white"; font.pixelSize: 26 }
            Quick.Text { Layout.fillWidth: true; text: root.statusText; color: root.statusError ? "#ffb1a9" : "#cdd9e4"; wrapMode: Quick.Text.Wrap }
            Controls.TextField {
                id: captureName
                objectName: "snapshotName"
                Layout.fillWidth: true
                placeholderText: qsTr("Optional snapshot name")
                maximumLength: 48
                onActiveFocusChanged: root.keyboardRaised = activeFocus
            }
            Controls.ComboBox {
                id: captureMode
                objectName: "snapshotMode"
                Layout.fillWidth: true
                model: [qsTr("Still"), qsTr("Still + animated GIF"), qsTr("360° panorama"), qsTr("360° cubemap")]
            }
            Controls.ComboBox {
                id: captureFormat
                objectName: "snapshotFormat"
                Layout.fillWidth: true
                model: typeof Snapshot !== "undefined" ? Snapshot.getAvailableSnapshotFormats() : ["png"]
                Component.onCompleted: {
                    if (typeof Snapshot !== "undefined") { currentIndex = Math.max(0, model.indexOf(Snapshot.getSnapshotFormat() || "png")) }
                }
                onActivated: if (typeof Snapshot !== "undefined") { Snapshot.setSnapshotFormat(currentText) }
            }
            RowLayout {
                Controls.Button {
                    objectName: "snapshotCapture"
                    Layout.minimumHeight: 44
                    text: qsTr("Take snapshot")
                    enabled: !root.capturing && !platform.busy && !root.uploadPath
                    onClicked: {
                        captureName.focus = false
                        root.send("takeSnapshot", { mode: ["still", "animated", "panorama", "cubemap"][captureMode.currentIndex], filename: captureName.text })
                    }
                }
                Controls.Button {
                    objectName: "snapshotCancelCapture"
                    Layout.minimumHeight: 44
                    text: qsTr("Cancel capture")
                    visible: root.capturing
                    onClicked: root.send("cancelSnapshotCapture")
                }
            }
            Controls.Button {
                objectName: "snapshotCancelUpload"
                Layout.minimumHeight: 44
                text: qsTr("Cancel upload")
                visible: !!root.uploadPath
                onClicked: root.send("cancelSnapshotUpload", { path: root.uploadPath })
            }
            Controls.Button { text: qsTr("Log in to upload"); visible: !root.loggedIn && root.images.length > 0; onClicked: root.send("login") }
            Quick.Text {
                Layout.fillWidth: true
                visible: root.images.length > 0 && platform.capabilities.length === 0
                text: platform.error
                color: "#cdd9e4"; wrapMode: Quick.Text.Wrap
            }
            Repeater {
                model: root.images
                delegate: ColumnLayout {
                    Layout.fillWidth: true
                    Quick.Text { text: root.isGif(modelData.localPath) ? qsTr("Animated snapshot") : qsTr("Still / 360° snapshot"); color: "white" }
                    Item {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 220
                        Quick.Image {
                            anchors.fill: parent
                            visible: !root.isGif(modelData.localPath)
                            source: visible ? root.imageUrl(modelData.localPath) : ""
                            sourceSize.width: 1024
                            asynchronous: true
                            fillMode: Quick.Image.PreserveAspectFit
                            onStatusChanged: if (status === Quick.Image.Error) { root.statusError = true; root.statusText = qsTr("Snapshot preview could not load."); root.send("alertSnapshotLoadFailed") }
                        }
                        Quick.AnimatedImage {
                            anchors.fill: parent
                            visible: root.isGif(modelData.localPath)
                            source: visible ? root.imageUrl(modelData.localPath) : ""
                            playing: visible && root.visible
                            fillMode: Quick.Image.PreserveAspectFit
                            onStatusChanged: if (status === Quick.Image.Error) { root.statusError = true; root.statusText = qsTr("Animated preview could not load."); root.send("alertSnapshotLoadFailed") }
                        }
                    }
                    Flow {
                        Layout.fillWidth: true
                        spacing: 8
                        Controls.Button { text: qsTr("Save to device"); visible: platform.capabilities.indexOf("save") !== -1; enabled: !platform.busy && !root.capturing; onClicked: root.exportImage(modelData.localPath, "save") }
                        Controls.Button { text: qsTr("System share"); visible: platform.capabilities.indexOf("share") !== -1; enabled: !platform.busy && !root.capturing; onClicked: root.exportImage(modelData.localPath, "share") }
                        Controls.Button { text: qsTr("Upload for URL"); enabled: root.loggedIn && root.canShare && !root.uploadPath && !root.capturing; onClicked: root.upload(modelData.localPath) }
                        Controls.Button { text: qsTr("Share with connections"); visible: !!modelData.story_id; enabled: root.canBlast && !modelData.blastButtonDisabled; onClicked: root.send("blastToConnections", { story_id: modelData.story_id, isGif: root.isGif(modelData.localPath) }) }
                        Controls.Button { text: qsTr("Share with everyone"); visible: !!modelData.story_id; enabled: !modelData.hifiButtonDisabled; onClicked: root.send("shareSnapshotWithEveryone", { story_id: modelData.story_id, isGif: root.isGif(modelData.localPath) }) }
                    }
                }
            }
            Controls.Button { text: qsTr("Cancel system request"); visible: !!root.exportTicket; onClicked: root.cancelExport() }
            Controls.Button { text: root.printProcessing ? qsTr("Preparing print…") : qsTr("Print to polaroid"); enabled: root.printEnabled; onClicked: root.send("printToPolaroid") }
            Controls.Button { text: qsTr("Snapshot settings"); onClicked: root.send("openSettings") }
        }
    }
}
