// Copyright 2026 Overte contributors.
// SPDX-License-Identifier: Apache-2.0
import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.3
import controlsUit 1.0 as HifiControls

Flickable {
    id: graphicsPage
    objectName: "settings.graphics"
    visible: Qt.platform.os === "android" && currentPage === "Graphics"
    Layout.fillHeight: true
    width: parent.width
    contentWidth: width
    contentHeight: graphicsColumn.implicitHeight + 32
    clip: true
    boundsBehavior: Flickable.StopAtBounds
    pressDelay: metrics.pressDelay
    flickDeceleration: metrics.flickDeceleration
    maximumFlickVelocity: metrics.maximumFlickVelocity
    property bool ready: false
    property var values: ({ haze: false, localLights: false,
        proceduralMaterials: false, mirrors: false, resolutionScale: 0.65 })

    HifiControls.TouchUiMetrics {
        id: metrics
        objectName: "phone.graphics.metrics"
        availableWidth: graphicsPage.width
        availableHeight: graphicsPage.height
    }

    function requestState() {
        if (Qt.platform.os === "android") { toScript({ type: "phone.graphics.ready" }) }
    }
    function fromScript(message) {
        if (message && message.type === "phone.graphics.state" && message.values) {
            values = message.values
            ready = true
        }
    }
    function update(key, value) {
        toScript({ type: "phone.graphics.update", key: key, value: value })
    }
    onVisibleChanged: if (visible) { requestState() }
    Component.onCompleted: requestState()

    Column {
        id: graphicsColumn
        x: 16
        y: 16
        width: graphicsPage.width - 32
        spacing: 12

        Text {
            width: graphicsColumn.width
            text: qsTr("World appearance")
            color: "white"
            font.pixelSize: Math.round(22 * metrics.textScale)
            font.bold: true
        }
        Text {
            width: graphicsColumn.width
            text: qsTr("World effects can increase battery use and heat. Frame rate stays at 30 FPS. Your choices are saved.")
            wrapMode: Text.Wrap
            color: "#d9e2e8"
            font.pixelSize: Math.round(16 * metrics.textScale)
        }
        Repeater {
            model: [
                { key: "localLights", title: qsTr("Local lights") },
                { key: "haze", title: qsTr("Haze and fog") },
                { key: "proceduralMaterials", title: qsTr("Custom material shaders") },
                { key: "mirrors", title: qsTr("Mirrors") }
            ]
            delegate: Switch {
                objectName: "settings.graphics." + modelData.key
                width: graphicsColumn.width
                text: modelData.title
                checked: graphicsPage.values[modelData.key] === true
                enabled: graphicsPage.ready
                implicitHeight: Math.max(48, metrics.adaptiveMinimumControlHeight, contentItem.implicitHeight + 16)
                font.pixelSize: Math.round(18 * metrics.textScale)
                contentItem: Text {
                    text: parent.text
                    color: "white"
                    font: parent.font
                    verticalAlignment: Text.AlignVCenter
                    leftPadding: parent.indicator.width + parent.spacing
                    wrapMode: Text.Wrap
                }
                Accessible.name: text
                Accessible.role: Accessible.CheckBox
                onToggled: graphicsPage.update(modelData.key, checked)
            }
        }
        Text {
            width: graphicsColumn.width
            text: qsTr("Resolution: %1%").arg(Math.round(graphicsPage.values.resolutionScale * 100))
            color: "white"
            font.pixelSize: Math.round(18 * metrics.textScale)
        }
        Slider {
            objectName: "settings.graphics.resolutionScale"
            width: graphicsColumn.width
            from: 0.5
            to: 0.7
            stepSize: 0.05
            snapMode: Slider.SnapAlways
            value: graphicsPage.values.resolutionScale
            enabled: graphicsPage.ready
            implicitHeight: Math.max(48, metrics.adaptiveMinimumControlHeight)
            Accessible.name: qsTr("Render resolution")
            Accessible.role: Accessible.Slider
            onMoved: graphicsPage.update("resolutionScale", Math.round(value * 100) / 100)
        }
    }
    ScrollBar.vertical: ScrollBar { }
}
