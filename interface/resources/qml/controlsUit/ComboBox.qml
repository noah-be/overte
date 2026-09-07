//
//  ComboBox.qml
//
//  Created by Bradley Austin David on 27 Jan 2016
//  Copyright 2016 High Fidelity, Inc.
//
//  Distributed under the Apache License, Version 2.0.
//  See the accompanying file LICENSE or http://www.apache.org/licenses/LICENSE-2.0.html
//

import QtQuick 2.7
import QtQuick.Controls 2.2

import "../stylesUit"
import "." as HifiControls

FocusScope {
    id: root
    HifiConstants { id: hifi }
    HifiControls.TouchUiMetrics { id: touchMetrics }

    property alias model: comboBox.model;
    property alias editable: comboBox.editable
    property alias editText: comboBox.editText
    readonly property alias popup: comboBox.popup
    property alias comboBox: comboBox
    readonly property alias currentText: comboBox.currentText;
    property alias displayText: comboBox.displayText;
    property alias currentIndex: comboBox.currentIndex;
    property int currentHighLightedIndex: comboBox.currentIndex;

    property int dropdownHeight: 480
    property int colorScheme: hifi.colorSchemes.light
    readonly property bool isLightColorScheme: colorScheme == hifi.colorSchemes.light
    property string label: ""
    property real controlHeight: height + (comboBoxLabel.visible ? comboBoxLabel.height + comboBoxLabel.anchors.bottomMargin : 0)

    readonly property ComboBox control: comboBox

    property bool isDesktop: true

    signal accepted();

    function showList() { if (visible && enabled) { comboBox.popup.open(); } }
    onVisibleChanged: { if (!visible) { comboBox.popup.close(); } }
    onEnabledChanged: { if (!enabled) { comboBox.popup.close(); } }

    implicitHeight: comboBox.height;
    focus: true

    ComboBox {
        id: comboBox
        anchors.fill: parent
        hoverEnabled: touchMetrics.hoverSupported
        visible: true
        height: Math.max(hifi.fontSizes.textFieldInput + 13,
            touchMetrics.adaptiveMinimumControlHeight)

        function previousItem() {
            root.currentHighLightedIndex = count <= 0 ? -1 :
                (root.currentHighLightedIndex <= 0 || root.currentHighLightedIndex >= count ? count - 1 : root.currentHighLightedIndex - 1);
        }
        function nextItem() {
            root.currentHighLightedIndex = count <= 0 ? -1 :
                (root.currentHighLightedIndex < 0 || root.currentHighLightedIndex >= count - 1 ? 0 : root.currentHighLightedIndex + 1);
        }
        function selectCurrentItem() { selectSpecificItem(root.currentHighLightedIndex); }
        function selectSpecificItem(index) {
            if (index < 0 || index >= count || Math.floor(index) !== index) { return; }
            root.currentIndex = index;
            comboBox.popup.close();
            root.accepted();
        }
        // Native delegate activation and editable Return are commits; closing
        // a popup (Escape/outside click/visibility teardown) is not a commit.
        onActivated: root.accepted()
        onAccepted: root.accepted()
        onCurrentIndexChanged: root.currentHighLightedIndex = currentIndex


        Keys.onUpPressed: previousItem();
        Keys.onDownPressed: nextItem();
        Keys.onSpacePressed: {
            if (comboBox.editable) { event.accepted = false; } else { selectCurrentItem(); }
        }
        Keys.onRightPressed: {
            if (comboBox.editable) { event.accepted = false; } else { selectCurrentItem(); }
        }
        Keys.onReturnPressed: {
            if (comboBox.editable) { event.accepted = false; } else { selectCurrentItem(); }
        }

        background: Rectangle {
            gradient: Gradient {
                GradientStop {
                    position: 0.2
                    color: comboBox.popup.visible
                           ? (isLightColorScheme ? hifi.colors.dropDownPressedLight : hifi.colors.dropDownPressedDark)
                           : (isLightColorScheme ? hifi.colors.dropDownLightStart : hifi.colors.dropDownDarkStart)
                }
                GradientStop {
                    position: 1.0
                    color: comboBox.popup.visible
                           ? (isLightColorScheme ? hifi.colors.dropDownPressedLight : hifi.colors.dropDownPressedDark)
                           : (isLightColorScheme ? hifi.colors.dropDownLightFinish : hifi.colors.dropDownDarkFinish)
                }
            }
        }

        indicator: Item {
            id: dropIcon
            anchors { right: parent.right; verticalCenter: parent.verticalCenter }
            height: root.height
            width: height
            Rectangle {
                width: 1
                height: parent.height
                anchors.top: parent.top
                anchors.left: parent.left
                color: isLightColorScheme ? hifi.colors.faintGray : hifi.colors.baseGray
            }
            HiFiGlyphs {
                anchors { top: parent.top; topMargin: -11; horizontalCenter: parent.horizontalCenter }
                size: hifi.dimensions.spinnerSize
                text: hifi.glyphs.caratDn
                color: comboBox.hovered || comboBox.popup.visible ? hifi.colors.baseGray : (isLightColorScheme ? hifi.colors.lightGray : hifi.colors.lightGrayText)
            }
        }

        contentItem: TextInput {
            id: textField
            anchors {
                left: parent.left
                leftMargin: hifi.dimensions.textPadding
                right: dropIcon.left
                rightMargin: hifi.dimensions.textPadding
                verticalCenter: parent.verticalCenter
            }
            font.family: "Fira Sans"
            font.weight: Font.DemiBold
            font.pixelSize: Math.round(hifi.fontSizes.textFieldInput * touchMetrics.textScale)
            verticalAlignment: TextInput.AlignVCenter
            readOnly: !comboBox.editable
            selectByMouse: comboBox.editable
            clip: true
            text: comboBox.editable ? comboBox.editText : comboBox.displayText
            color: comboBox.editable ? displayColor : "transparent"
            readonly property color displayColor: comboBox.hovered || comboBox.popup.visible ? hifi.colors.baseGray :
                (isLightColorScheme ? hifi.colors.lightGray : hifi.colors.lightGrayText)
            // Preserve the existing elided label when editing is disabled.
            Text {
                anchors.fill: parent
                visible: !comboBox.editable
                text: textField.text
                font: textField.font
                verticalAlignment: Text.AlignVCenter
                elide: Text.ElideRight
                color: textField.displayColor
            }
        }

        delegate: ItemDelegate {
            id: itemDelegate
            hoverEnabled: touchMetrics.hoverSupported
            width: root.width + 4
            height: Math.max(popupText.implicitHeight * 1.4,
                touchMetrics.adaptiveMinimumControlHeight)
            highlighted: root.currentHighLightedIndex == index

            onHoveredChanged: {
                if (hovered) {
                    root.currentHighLightedIndex = index
                }
            }

            background: Rectangle {
                color: itemDelegate.highlighted ? hifi.colors.primaryHighlight
                                                : (isLightColorScheme ? hifi.colors.dropDownPressedLight
                                                                      : hifi.colors.dropDownPressedDark)
            }

            contentItem: FiraSansSemiBold {
                id: popupText
                anchors.left: parent.left
                anchors.leftMargin: hifi.dimensions.textPadding
                anchors.verticalCenter: parent.verticalCenter
                text: comboBox.model[index] ? comboBox.model[index]
                                            : (comboBox.model.get && comboBox.model.get(index).text ?
                                                   comboBox.model.get(index).text : "")
                size: Math.round(hifi.fontSizes.textFieldInput * touchMetrics.textScale)
                color: hifi.colors.baseGray
            }
        }
        popup: Popup {
            focus: true
            y: comboBox.height - 1
            width: comboBox.width
            implicitHeight: listView.contentHeight > dropdownHeight ? dropdownHeight
                                                                    : listView.contentHeight
            padding: 0
            topPadding: 1

            onAboutToShow: root.currentHighLightedIndex = comboBox.currentIndex
            onClosed: root.currentHighLightedIndex = comboBox.currentIndex

            contentItem: ListView {
                id: listView
                focus: true
                Keys.onUpPressed: comboBox.previousItem()
                Keys.onDownPressed: comboBox.nextItem()
                Keys.onReturnPressed: comboBox.selectCurrentItem()
                Keys.onEnterPressed: comboBox.selectCurrentItem()
                Keys.onSpacePressed: comboBox.selectCurrentItem()
                Keys.onEscapePressed: comboBox.popup.close()
                clip: true
                model: comboBox.popup.visible ? comboBox.delegateModel : null
                currentIndex: root.currentHighLightedIndex
                delegate: comboBox.delegate
                ScrollBar.vertical: HifiControls.ScrollBar {
                    id: scrollbar
                    parent: listView
                    policy: ScrollBar.AsNeeded
                    visible: size < 1.0
                }
            }

            background: Rectangle {
                color: hifi.colors.baseGray
            }
        }
    }

    function textAt(index) {
        return comboBox.textAt(index);
    }

    HifiControls.Label {
        id: comboBoxLabel
        text: root.label
        colorScheme: root.colorScheme
        anchors.left: parent.left
        anchors.bottom: parent.top
        anchors.bottomMargin: 4
        visible: label != ""
    }

    Component.onCompleted: {
        isDesktop = (typeof desktop !== "undefined");
    }
}
