//
//  VrMenuItem.qml
//
//  Created by Bradley Austin Davis on 29 Apr 2015
//  Copyright 2015 High Fidelity, Inc.
//
//  Distributed under the Apache License, Version 2.0.
//  See the accompanying file LICENSE or http://www.apache.org/licenses/LICENSE-2.0.html
//

import QtQuick 2.5
import "TabletMenuAdapter.js" as MenuAdapter
import QtQuick.Controls 2.3

import controlsUit 1.0
import stylesUit 1.0

Item {
    id: root
    HifiConstants { id: hifi  }
    property alias text: label.text
    property var source
    property bool platformEnabled: true
    property real touchTextScale: 1.0
    property int minimumControlHeight: 0

    implicitHeight: source !== null && MenuAdapter.isVisible(source)
        ? Math.max(2 * label.implicitHeight, minimumControlHeight) : 0
    implicitWidth: 2 * hifi.dimensions.menuPadding.x + check.width + label.width + tail.width
    visible: source !== null ? MenuAdapter.isVisible(source) : false
    // A delegate is parented to ListView's content item. Binding to that
    // parent's width forms a loop with ListView.contentWidth while delegates
    // are being created and released.
    width: ListView.view ? ListView.view.width : 0

    Item {
        id: check

        anchors {
            left: parent.left
            leftMargin: hifi.dimensions.menuPadding.x + 15
            verticalCenter: label.verticalCenter
        }

        width: checkbox.visible ? checkbox.width : radiobutton.width
        height: checkbox.visible ? checkbox.height : radiobutton.height

        CheckBox {
            id: checkbox

            width: 20
            visible: source !== null ?
                         MenuAdapter.isVisible(source) && source.type === 1 && source.checkable && !MenuAdapter.isExclusive(source) :
                         false

            Binding on checked {
                value: source.checked;
                when: source && source.type === 1 && source.checkable && !MenuAdapter.isExclusive(source);
            }
        }

        RadioButton {
            id: radiobutton

            width: 20
            visible: source !== null ?
                         MenuAdapter.isVisible(source) && source.type === 1 && source.checkable && MenuAdapter.isExclusive(source) :
                         false

            Binding on checked {
                value: source.checked;
                when: source && source.type === 1 && source.checkable && MenuAdapter.isExclusive(source);
            }
        }
    }

    RalewaySemiBold {
        id: label
        size: Math.round(20 * root.touchTextScale)
        //wrap will work only if width is set
        width: parent.width - (check.width + check.anchors.leftMargin) - tail.width
        font.capitalization: isSubMenu ? Font.MixedCase : Font.AllUppercase
        anchors.left: check.right
        anchors.verticalCenter: parent.verticalCenter
        verticalAlignment: Text.AlignVCenter
        color: source !== null ?
                   source.enabled && platformEnabled ? hifi.colors.baseGrayShadow :
                                    hifi.colors.baseGrayShadow50 :
        "transparent"

        enabled: source !== null ? MenuAdapter.isVisible(source) && platformEnabled && (source.type !== 0 ? source.enabled : false) : false
        visible: source !== null ? MenuAdapter.isVisible(source) : false
        wrapMode: Text.WordWrap
    }

    Item {
        id: separator
        anchors {
            fill: parent
            leftMargin: hifi.dimensions.menuPadding.x + check.width
            rightMargin: hifi.dimensions.menuPadding.x + tail.width
        }
        visible: source !== null ? source.type === MenuAdapter.Separator : false

        Rectangle {
            anchors {
                left: parent.left
                right: parent.right
                verticalCenter: parent.verticalCenter
            }
            height: 1
            color: hifi.colors.lightGray50
        }
    }

    Item {
        id: tail
        width: 48 + (shortcut.visible ? shortcut.width : 0)
        anchors {
            verticalCenter: parent.verticalCenter
            right: parent.right
            rightMargin: hifi.dimensions.menuPadding.x
        }

        RalewayLight {
            id: shortcut
            text: MenuAdapter.shortcut(source)
            size: Math.round(hifi.fontSizes.shortcutText * root.touchTextScale)
            color: hifi.colors.baseGrayShadow
            anchors.verticalCenter: parent.verticalCenter
            anchors.right: parent.right
            anchors.rightMargin: 15
            visible: source !== null ? MenuAdapter.isVisible(source) && text != "" : false
        }

        HiFiGlyphs {
            text: hifi.glyphs.disclosureExpand
            color: source !== null ? source.enabled && platformEnabled ? hifi.colors.baseGrayShadow : hifi.colors.baseGrayShadow25 : "transparent"
            size: Math.round(70 * root.touchTextScale)
            anchors.verticalCenter: parent.verticalCenter
            anchors.right: parent.right
            horizontalAlignment: Text.AlignRight
            visible: source !== null ? MenuAdapter.isVisible(source) && (source.type === 2) : false
        }
    }
}
