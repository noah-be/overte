// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0
import QtQuick 2.7
import QtQuick.Controls 2.3
import QtQuick.Layouts 1.3

Rectangle {
    id: root
    color: "#17212a"
    signal sendToScript(var message)
    signal selectionChanged()
    property int currentTab: 0
    property var entityRows: []
    property var selectedIDs: []
    property var selectionRows: []
    property var selected: selectionRows.length === 1 ? selectionRows[0] : null
    property var changed: ({})
    property string statusText: qsTr("Choose an entity type or select an existing entity")
    property bool statusError: false
    property bool canUndo: false
    property bool canRedo: false
    property var focusedNumber: null
    // OffscreenQmlSurface locates these properties on focus and requests the
    // established headset keyboard. Touch clients retain their OS IME.
    property bool keyboardEnabled: false
    property bool keyboardRaised: false
    property bool punctuationMode: false
    property var keyboardItem: null
    onKeyboardRaisedChanged: {
        if (typeof KeyboardScriptingInterface !== "undefined" && KeyboardScriptingInterface.use3DKeyboard) {
            KeyboardScriptingInterface.raised = keyboardEnabled && keyboardRaised
        }
    }
    onKeyboardEnabledChanged: {
        if (keyboardEnabled && !keyboardItem && typeof KeyboardScriptingInterface !== "undefined"
                && !KeyboardScriptingInterface.use3DKeyboard) {
            keyboardItem = Qt.createQmlObject('import QtQuick 2.7; import controlsUit 1.0; Keyboard {'
                + ' anchors.bottom: parent.bottom; raised: parent.keyboardEnabled && parent.keyboardRaised;'
                + ' numeric: parent.punctuationMode }', root, "NativeCreateKeyboard")
        }
    }

    function send(method, params) {
        sendToScript({ method: "nativeCreate." + method, params: params || {} })
    }
    function fromScript(message) {
        if (!message || !message.params) { return }
        var value = message.params
        if (message.method === "nativeCreate.list") {
            entityRows = value.entities || []
            selectedIDs = value.selectedIDs || []
        } else if (message.method === "nativeCreate.selection") {
            var previousID = selected ? selected.id : ""
            selectionRows = value.entities || []
            selectedIDs = selectionRows.map(function(item) { return item.id })
            canUndo = value.canUndo === true
            canRedo = value.canRedo === true
            changed = ({})
            if (!selected || selected.id !== previousID) {
                focusedNumber = null
                send("numericFocus", { focused: false })
            }
            selectionChanged()
        } else if (message.method === "nativeCreate.status") {
            statusText = value.text || ""
            statusError = value.error === true
        } else if (message.method === "picoAdjustFocusedNumber") {
            var direction = Number(value.direction)
            if (focusedNumber && (direction === -1 || direction === 1)) {
                focusedNumber.stepNumber(direction)
            }
        }
    }
    function select(id) {
        var ids = multiSelect.checked ? selectedIDs.slice() : []
        var index = ids.indexOf(id)
        if (index !== -1) { ids.splice(index, 1) } else { ids.push(id) }
        send("select", { ids: ids })
        if (!multiSelect.checked) { currentTab = 2 }
    }
    function change(key, value) {
        var update = JSON.parse(JSON.stringify(changed))
        update[key] = value
        changed = update
    }
    function componentValue(key, component) {
        var value = changed[key] || (selected && selected.properties[key]) || {}
        return typeof value[component] === "number" ? value[component] : key === "dimensions" ? 0.2 : 0
    }
    function changeComponent(key, component, text) {
        if (text.trim().length === 0 || !isFinite(Number(text))) {
            statusText = qsTr("Enter a finite number")
            statusError = true
            return false
        }
        var value = JSON.parse(JSON.stringify(changed[key] || (selected && selected.properties[key]) || {}))
        var components = key === "color" ? ["red", "green", "blue"] : ["x", "y", "z"]
        components.forEach(function(name) { if (typeof value[name] !== "number") { value[name] = 0 } })
        value[component] = Number(text)
        change(key, value)
        return true
    }
    function apply(properties) {
        if (selected) { send("edit", { id: selected.id, properties: properties || changed }) }
    }
    function tool(action) { send("tool", { action: action }) }
    function createEntity(type) {
        var properties = { type: type }
        var urlProperty = { Model: "modelURL", Image: "imageURL", Web: "sourceUrl",
            Sound: "soundURL", Script: "scriptURL", Material: "materialURL" }[type]
        if (urlProperty && resourceUrl.text.trim()) { properties[urlProperty] = resourceUrl.text.trim() }
        if (type === "Model" && !resourceUrl.text.trim()) {
            statusText = qsTr("Enter a model URL before creating a model")
            statusError = true
            return
        }
        if (type === "Shape") { properties.shape = shapeChoice.currentText }
        if (type === "Text") { properties.text = newText.text || qsTr("Text") }
        send("create", { properties: properties, host: createHost.currentIndex === 1 ? "avatar" : "domain" })
        currentTab = 2
    }
    function importParameters() {
        var result = { url: importUrl.text.trim(), host: importHost.currentIndex === 1 ? "avatar" : "domain" }
        if (specificPosition.checked) {
            var x = Number(importX.text), y = Number(importY.text), z = Number(importZ.text)
            if (!importX.text.trim() || !importY.text.trim() || !importZ.text.trim()
                    || !isFinite(x) || !isFinite(y) || !isFinite(z)) {
                statusText = qsTr("Import position must contain finite numbers")
                statusError = true
                return null
            }
            result.position = { x: x, y: y, z: z }
        }
        return result
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 10
        anchors.bottomMargin: 10 + (root.keyboardItem ? root.keyboardItem.height : 0)
        spacing: 8

        RowLayout {
            Layout.fillWidth: true
            Text { text: qsTr("CREATE"); color: "white"; font.pixelSize: 22; font.bold: true; Layout.fillWidth: true }
            Button { objectName: "NativeCreateUndo"; text: qsTr("Undo"); enabled: root.canUndo; onClicked: root.tool("undo") }
            Button { objectName: "NativeCreateRedo"; text: qsTr("Redo"); enabled: root.canRedo; onClicked: root.tool("redo") }
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: 2
            Repeater {
                model: [qsTr("NEW"), qsTr("LIST"), qsTr("PROPERTIES"), qsTr("TOOLS"), qsTr("IMPORT")]
                Button {
                    objectName: "NativeCreateTab_" + index
                    Layout.fillWidth: true
                    Layout.preferredWidth: 1
                    Layout.minimumWidth: 0
                    Layout.preferredHeight: 46
                    text: modelData
                    font.pixelSize: root.width < 450 ? 10 : 13
                    highlighted: root.currentTab === index
                    onClicked: root.currentTab = index
                }
            }
        }

        Text {
            objectName: "NativeCreateStatus"
            Layout.fillWidth: true
            text: root.statusText
            color: root.statusError ? "#ff9e9e" : "#d9e2e8"
            wrapMode: Text.Wrap
            font.pixelSize: 14
            Accessible.name: text
        }

        StackLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            currentIndex: root.currentTab

            ScrollView {
                clip: true
                ColumnLayout {
                    width: parent.parent.width
                    spacing: 10
                    Text { text: qsTr("Entity host"); color: "white" }
                    ComboBox { id: createHost; objectName: "NativeCreateHost"; Layout.fillWidth: true; model: [qsTr("Domain"), qsTr("My avatar")] }
                    TextField { id: resourceUrl; objectName: "NativeCreateResourceUrl"; Layout.fillWidth: true; placeholderText: qsTr("Resource URL for model, image, web, audio or script") }
                    TextField { id: newText; objectName: "NativeCreateText"; Layout.fillWidth: true; placeholderText: qsTr("Initial text for a Text entity") }
                    ComboBox { id: shapeChoice; Layout.fillWidth: true; model: ["Cube", "Sphere", "Cylinder", "Cone", "Torus", "Plane"] }
                    RowLayout {
                        Layout.fillWidth: true
                        ComboBox {
                            id: detailedType
                            objectName: "NativeCreateDetailedType"
                            Layout.fillWidth: true
                            model: ["Model", "Particle", "Material", "PolyVox", "Sound", "Script"]
                        }
                        Button {
                            objectName: "NativeCreateDetailed"
                            text: qsTr("More options")
                            onClicked: root.sendToScript({ method: "newEntityButtonClicked",
                                params: { buttonName: "new" + detailedType.currentText + "Button" } })
                        }
                    }
                    Flow {
                        Layout.fillWidth: true
                        spacing: 6
                        Repeater {
                            model: ["Shape", "Model", "Light", "Text", "Image", "Web", "Zone",
                                "ParticleEffect", "ProceduralParticleEffect", "Material", "PolyVox", "Grid",
                                "Sound", "Canvas", "Empty", "Script"]
                            Button {
                                objectName: "NativeCreateNew_" + modelData
                                width: (parent.width - 6) / 2
                                height: 52
                                text: modelData
                                font.pixelSize: 12
                                onClicked: root.createEntity(modelData)
                            }
                        }
                    }
                    Button { Layout.fillWidth: true; text: qsTr("Open domain assets"); onClicked: root.tool("assets") }
                }
            }

            ColumnLayout {
                RowLayout {
                    Layout.fillWidth: true
                    TextField { id: listSearch; Layout.fillWidth: true; placeholderText: qsTr("Filter by name or type") }
                    Button { objectName: "NativeCreateRefresh"; text: qsTr("Refresh"); onClicked: root.send("refresh") }
                }
                CheckBox { id: multiSelect; text: qsTr("Select multiple entities"); palette.windowText: "white" }
                ListView {
                    id: entityList
                    objectName: "NativeCreateEntityList"
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    clip: true
                    model: root.entityRows.filter(function(item) {
                        return (item.name + " " + item.type).toLowerCase().indexOf(listSearch.text.toLowerCase()) !== -1
                    })
                    delegate: Button {
                        objectName: "NativeCreateEntity_" + modelData.id
                        width: entityList.width
                        height: 60
                        text: (modelData.name || qsTr("Unnamed")) + " — " + modelData.type + (modelData.locked ? " 🔒" : "")
                        highlighted: root.selectedIDs.indexOf(modelData.id) !== -1
                        onClicked: root.select(modelData.id)
                    }
                    ScrollBar.vertical: ScrollBar {}
                }
                Text { text: root.entityRows.length + qsTr(" nearby entities"); color: "#d9e2e8" }
            }

            ScrollView {
                clip: true
                ColumnLayout {
                    width: parent.parent.width
                    spacing: 8
                    Text {
                        Layout.fillWidth: true
                        text: root.selected ? root.selected.type + " — " + root.selected.id
                            : qsTr("Select one entity from LIST or the world to edit its properties")
                        color: "white"
                        wrapMode: Text.Wrap
                    }
                    Text {
                        visible: root.selected && !root.selected.editable
                        text: qsTr("This entity is locked or you do not have editing permission")
                        color: "#ff9e9e"
                        Layout.fillWidth: true
                        wrapMode: Text.Wrap
                    }
                    Button {
                        visible: root.selected !== null && root.selected.canUnlock === true
                        text: qsTr("Unlock entity")
                        onClicked: root.apply({ locked: false })
                    }
                    Button {
                        visible: root.selected !== null && root.selected.canLock === true
                        text: qsTr("Lock entity")
                        onClicked: root.apply({ locked: true })
                    }
                    ColumnLayout {
                        Layout.fillWidth: true
                        visible: root.selected !== null
                        enabled: root.selected && root.selected.editable
                        TextField {
                            id: entityName
                            objectName: "NativeCreateName"
                            Layout.fillWidth: true
                            placeholderText: qsTr("Name")
                            onTextEdited: root.change("name", text)
                            Connections { target: root; onSelectionChanged: entityName.text = root.selected ? root.selected.properties.name || "" : "" }
                        }
                        Repeater {
                            model: ["position", "rotation", "dimensions", "color"]
                            ColumnLayout {
                                Layout.fillWidth: true
                                property string propertyName: modelData
                                Text { text: parent.propertyName; color: "white" }
                                RowLayout {
                                    Layout.fillWidth: true
                                    Repeater {
                                        model: parent.parent.propertyName === "color" ? ["red", "green", "blue"] : ["x", "y", "z"]
                                        TextField {
                                            id: numberField
                                            objectName: "NativeCreateField_" + propertyName + "_" + modelData
                                            property string propertyName: parent.parent.propertyName
                                            property string componentName: modelData
                                            property real step: propertyName === "rotation" || propertyName === "color" ? 1 : 0.01
                                            Layout.fillWidth: true
                                            Layout.minimumWidth: 0
                                            Layout.preferredWidth: 1
                                            inputMethodHints: Qt.ImhFormattedNumbersOnly
                                            placeholderText: componentName
                                            onTextEdited: root.changeComponent(propertyName, componentName, text)
                                            onActiveFocusChanged: {
                                                if (activeFocus) { root.focusedNumber = numberField }
                                                else if (root.focusedNumber === numberField) { root.focusedNumber = null }
                                                root.send("numericFocus", { focused: root.focusedNumber !== null })
                                            }
                                            function stepNumber(direction) {
                                                var number = Number(text)
                                                if (!isFinite(number)) { return }
                                                text = (number + direction * step).toFixed(step < 1 ? 3 : 0)
                                                if (root.changeComponent(propertyName, componentName, text)) {
                                                    root.send("preview", { id: root.selected.id, properties: root.changed })
                                                }
                                            }
                                            Connections {
                                                target: root
                                                onSelectionChanged: {
                                                    if (!numberField.activeFocus) { numberField.text = String(root.componentValue(numberField.propertyName, numberField.componentName)) }
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                        }
                        Flow {
                            Layout.fillWidth: true
                            Repeater {
                                model: ["visible", "dynamic", "collisionless"]
                                CheckBox {
                                    id: flag
                                    text: modelData
                                    palette.windowText: "white"
                                    onClicked: root.change(modelData, checked)
                                    Connections { target: root; onSelectionChanged: flag.checked = root.selected && root.selected.properties[flag.text] === true }
                                }
                            }
                        }
                        Button { objectName: "NativeCreateApply"; text: qsTr("Apply properties"); Layout.fillWidth: true; onClicked: root.apply() }
                        Button { objectName: "NativeCreateDelete"; text: qsTr("Delete selected entity"); Layout.fillWidth: true; onClicked: root.tool("delete") }
                        Label { text: qsTr("Advanced properties (JSON)"); color: "white" }
                        TextArea {
                            id: advanced
                            objectName: "NativeCreateAdvanced"
                            Layout.fillWidth: true
                            Layout.preferredHeight: 220
                            wrapMode: TextEdit.Wrap
                            selectByMouse: true
                            Connections { target: root; onSelectionChanged: if (!advanced.activeFocus) { advanced.text = JSON.stringify(root.selected ? root.selected.properties : {}, null, 2) } }
                        }
                        Button {
                            objectName: "NativeCreateApplyAdvanced"
                            text: qsTr("Apply advanced properties")
                            Layout.fillWidth: true
                            onClicked: {
                                try { root.apply(JSON.parse(advanced.text)) }
                                catch (error) { root.statusText = qsTr("Properties must be a valid JSON object"); root.statusError = true }
                            }
                        }
                    }
                }
            }

            ScrollView {
                clip: true
                Flow {
                    width: parent.parent.width
                    spacing: 6
                    Repeater {
                        model: [
                            ["duplicate", qsTr("Duplicate")], ["copy", qsTr("Copy")], ["paste", qsTr("Paste")],
                            ["delete", qsTr("Delete")], ["parent", qsTr("Parent")], ["unparent", qsTr("Unparent")],
                            ["focus", qsTr("Focus selection")], ["move-to-avatar", qsTr("Move to avatar")],
                            ["grid-avatar", qsTr("Grid at avatar")], ["grid-selection", qsTr("Grid at selection")],
                            ["grid-visible", qsTr("Show/hide grid")], ["grid-snap", qsTr("Toggle grid snap")],
                            ["space-mode", qsTr("Local/world space")], ["rotate-x", qsTr("Rotate X 90°")],
                            ["rotate-y", qsTr("Rotate Y 90°")], ["rotate-z", qsTr("Rotate Z 90°")],
                            ["export", qsTr("Export selection")], ["assets", qsTr("Domain assets")]
                        ]
                        Button {
                            objectName: "NativeCreateTool_" + modelData[0]
                            width: (parent.width - 6) / 2
                            height: 52
                            text: modelData[1]
                            font.pixelSize: 12
                            onClicked: root.tool(modelData[0])
                        }
                    }
                }
            }

            ScrollView {
                clip: true
                ColumnLayout {
                    width: parent.parent.width
                    spacing: 10
                    Text { text: qsTr("Import entity JSON"); color: "white"; font.pixelSize: 20 }
                    TextField { id: importUrl; objectName: "NativeCreateImportUrl"; Layout.fillWidth: true; placeholderText: qsTr("HTTP, HTTPS or ATP URL") }
                    ComboBox { id: importHost; objectName: "NativeCreateImportHost"; Layout.fillWidth: true; model: [qsTr("Domain"), qsTr("My avatar")] }
                    CheckBox { id: specificPosition; text: qsTr("Place at coordinates instead of in front of avatar"); palette.windowText: "white"; Layout.fillWidth: true }
                    RowLayout {
                        Layout.fillWidth: true
                        enabled: specificPosition.checked
                        TextField { id: importX; Layout.fillWidth: true; Layout.preferredWidth: 1; Layout.minimumWidth: 0; text: "0"; placeholderText: "X"; inputMethodHints: Qt.ImhFormattedNumbersOnly }
                        TextField { id: importY; Layout.fillWidth: true; Layout.preferredWidth: 1; Layout.minimumWidth: 0; text: "0"; placeholderText: "Y"; inputMethodHints: Qt.ImhFormattedNumbersOnly }
                        TextField { id: importZ; Layout.fillWidth: true; Layout.preferredWidth: 1; Layout.minimumWidth: 0; text: "0"; placeholderText: "Z"; inputMethodHints: Qt.ImhFormattedNumbersOnly }
                    }
                    Button { objectName: "NativeCreateImport"; Layout.fillWidth: true; text: qsTr("Import URL"); onClicked: { var params = root.importParameters(); if (params) { root.send("import", params) } } }
                    Button { objectName: "NativeCreateBrowse"; Layout.fillWidth: true; text: qsTr("Choose local JSON file and import"); onClicked: { var params = root.importParameters(); if (params) { root.send("browse", params) } } }
                    Text { text: qsTr("Imported entities become the current selection and can be undone."); color: "#d9e2e8"; wrapMode: Text.Wrap; Layout.fillWidth: true }
                }
            }
        }
    }

    Component.onCompleted: send("ready")
    Component.onDestruction: {
        send("numericFocus", { focused: false })
        if (typeof KeyboardScriptingInterface !== "undefined" && KeyboardScriptingInterface.raised) {
            KeyboardScriptingInterface.raised = false
        }
    }
}
