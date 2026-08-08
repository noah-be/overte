import QtQuick 2.7
import QtQuick.Controls 2.3
import QtQuick.Layouts 1.3
import controlsUit 1.0 as HifiControls
import stylesUit 1.0

Rectangle {
    id: root
    color: "#404040"

    property string entityID: ""
    property bool loading: false
    property var focusedNumericField: null
    property real focusedNumericStep: 0.01
    function finiteNumber(value, fallback) {
        var number = Number(value);
        return isFinite(number) ? number : fallback;
    }
    function numberText(value) {
        return finiteNumber(value, 0).toFixed(3);
    }

    function setVector(fields, vector) {
        fields[0].text = numberText(vector.x);
        fields[1].text = numberText(vector.y);
        fields[2].text = numberText(vector.z);
    }

    function fromScript(message) {
        if (message.method === "picoAdjustFocusedNumber") {
            adjustFocusedNumber(message.params.direction);
            return;
        }
        if (message.method !== "picoPropertiesSelection") {
            return;
        }
        loading = true;
        var params = message.params || {};
        var properties = params.properties || {};
        entityID = params.id || "";
        emptyLabel.visible = entityID === "";
        editor.visible = entityID !== "";
        if (entityID !== "") {
            nameField.text = properties.name || "";
            typeValue.text = properties.type || "";
            setVector([positionX, positionY, positionZ], properties.position || {});
            setVector([rotationX, rotationY, rotationZ], properties.rotation || {});
            setVector([dimensionsX, dimensionsY, dimensionsZ], properties.dimensions || {});
            var color = properties.color || { red: 255, green: 255, blue: 255 };
            colorR.value = color.red;
            colorG.value = color.green;
            colorB.value = color.blue;
            visibleCheck.checked = properties.visible !== false;
            dynamicCheck.checked = properties.dynamic === true;
            collisionsCheck.checked = properties.collisionless !== true;
        }
        loading = false;
    }

    function numeric(field) {
        return finiteNumber(field.text, 0);
    }

    function setNumericFocus(field, focused, step) {
        if (focused) {
            focusedNumericField = field;
            focusedNumericStep = Math.max(0.001, finiteNumber(step, 0.01));
        } else if (focusedNumericField === field) {
            focusedNumericField = null;
        }
        editRoot.sendToScript({
            method: "picoNumericFocus",
            params: { focused: focusedNumericField !== null }
        });
    }

    function adjustFocusedNumber(direction) {
        if (focusedNumericField === null) {
            return;
        }
        direction = Number(direction);
        if (direction !== -1 && direction !== 1) {
            return;
        }
        var value = finiteNumber(focusedNumericField.text, 0);
        value += direction * focusedNumericStep;
        var decimals = focusedNumericStep < 0.1 ? 3 : (focusedNumericStep < 1 ? 2 : 0);
        focusedNumericField.text = value.toFixed(decimals);
        sendEntityProperties("picoPreviewEntity");
    }

    function sendEntityProperties(method) {
        if (entityID === "") {
            return;
        }
        editRoot.sendToScript({
            method: method,
            params: {
                id: entityID,
                properties: {
                    name: nameField.text,
                    position: { x: numeric(positionX), y: numeric(positionY), z: numeric(positionZ) },
                    rotation: { x: numeric(rotationX), y: numeric(rotationY), z: numeric(rotationZ) },
                    dimensions: {
                        x: Math.max(0.001, numeric(dimensionsX)),
                        y: Math.max(0.001, numeric(dimensionsY)),
                        z: Math.max(0.001, numeric(dimensionsZ))
                    },
                    color: { red: colorR.value, green: colorG.value, blue: colorB.value },
                    visible: visibleCheck.checked,
                    dynamic: dynamicCheck.checked,
                    collisionless: !collisionsCheck.checked
                }
            }
        });
    }

    function sendApply() {
        sendEntityProperties("picoEditEntity");
    }

    Component.onCompleted: {
        editRoot.sendToScript({ method: "picoRequestSelection", params: {} });
    }
    Component.onDestruction: {
        editRoot.sendToScript({
            method: "picoNumericFocus",
            params: { focused: false }
        });
    }

    Text {
        id: emptyLabel
        anchors.centerIn: parent
        color: "white"
        font.pixelSize: 24
        text: "No entity selected"
    }

    ScrollView {
        id: editor
        anchors.fill: parent
        anchors.margins: 24
        clip: true
        visible: false

        ColumnLayout {
            width: editor.availableWidth
            spacing: 14

            Text {
                text: "NATIVE PICO PROPERTIES"
                color: "white"
                font.pixelSize: 20
                font.bold: true
            }

            RowLayout {
                Layout.fillWidth: true
                Text { text: "Type"; color: "white"; Layout.preferredWidth: 125 }
                Text { id: typeValue; color: "#b8e6ff"; font.pixelSize: 18 }
            }

            RowLayout {
                Layout.fillWidth: true
                Text { text: "Name"; color: "white"; Layout.preferredWidth: 125 }
                TextField { id: nameField; Layout.fillWidth: true; font.pixelSize: 17 }
            }

            Text { text: "Position (m)"; color: "white"; font.bold: true }
            VectorRow {
                id: positionRow
                fields: [positionX, positionY, positionZ]
                step: 0.1
                onNumericFocusChanged: root.setNumericFocus(field, focused, step)
            }
            TextField { id: positionX; visible: false }
            TextField { id: positionY; visible: false }
            TextField { id: positionZ; visible: false }

            Text { text: "Rotation (degrees)"; color: "white"; font.bold: true }
            VectorRow {
                fields: [rotationX, rotationY, rotationZ]
                step: 1.0
                onNumericFocusChanged: root.setNumericFocus(field, focused, step)
            }
            TextField { id: rotationX; visible: false }
            TextField { id: rotationY; visible: false }
            TextField { id: rotationZ; visible: false }

            Text { text: "Dimensions (m)"; color: "white"; font.bold: true }
            VectorRow {
                fields: [dimensionsX, dimensionsY, dimensionsZ]
                step: 0.01
                onNumericFocusChanged: root.setNumericFocus(field, focused, step)
            }
            TextField { id: dimensionsX; visible: false }
            TextField { id: dimensionsY; visible: false }
            TextField { id: dimensionsZ; visible: false }

            Text { text: "Color (RGB)"; color: "white"; font.bold: true }
            RowLayout {
                Layout.fillWidth: true
                SpinBox { id: colorR; from: 0; to: 255; editable: true; Layout.fillWidth: true }
                SpinBox { id: colorG; from: 0; to: 255; editable: true; Layout.fillWidth: true }
                SpinBox { id: colorB; from: 0; to: 255; editable: true; Layout.fillWidth: true }
            }

            RowLayout {
                Layout.fillWidth: true
                CheckBox { id: visibleCheck; text: "Visible"; checked: true }
                CheckBox { id: dynamicCheck; text: "Dynamic" }
                CheckBox { id: collisionsCheck; text: "Collisions"; checked: true }
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: 18
                Button {
                    text: "APPLY"
                    Layout.fillWidth: true
                    onClicked: root.sendApply()
                }
                Button {
                    text: "DELETE"
                    Layout.fillWidth: true
                    onClicked: editRoot.sendToScript({
                        method: "picoDeleteEntity",
                        params: { id: root.entityID }
                    })
                }
            }
        }
    }
}
