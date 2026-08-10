//
//  VrMenuView.qml
//
//  Created by Bradley Austin Davis on 18 Jan 2016
//  Copyright 2016 High Fidelity, Inc.
//
//  Distributed under the Apache License, Version 2.0.
//  See the accompanying file LICENSE or http://www.apache.org/licenses/LICENSE-2.0.html
//

import QtQuick 2.5
import TabletScriptingInterface 1.0

import stylesUit 1.0
import "."

FocusScope {
    id: root
    implicitHeight: background.height
    implicitWidth: background.width
    objectName: "root"
    property alias currentItem: listView.currentItem
    property alias model: listView.model
    property bool isSubMenu: false
    signal selected(var item)

    HifiConstants { id: hifi }

    Rectangle {
        id: background
        anchors.fill: listView
        radius: hifi.dimensions.borderRadius
        border.width: hifi.dimensions.borderWidth
        border.color: hifi.colors.lightGrayText80
        color: hifi.colors.faintGray
        //color: isSubMenu ? hifi.colors.faintGray : hifi.colors.faintGray80
    }

    ListView {
        id: listView
        x: 0
        y: 0
        width: parent.width
        height: parent.height
        contentWidth: parent.width
        contentHeight: parent.height
        objectName: "menuList"
        property bool recalcPending: false

        topMargin: hifi.dimensions.menuPadding.y
        bottomMargin: hifi.dimensions.menuPadding.y
        onEnabledChanged: scheduleRecalcSize();
        onVisibleChanged: scheduleRecalcSize();
        onCountChanged: scheduleRecalcSize();
        focus: true
        highlightMoveDuration: 0

        highlight: Rectangle {
            anchors {
                left: parent ? parent.left : undefined
                right: parent ? parent.right : undefined
                leftMargin: hifi.dimensions.borderWidth
                rightMargin: hifi.dimensions.borderWidth
            }
            color: hifi.colors.white
        }

        delegate: TabletMenuItem {
            text: name
            source: item
            platformEnabled: phoneSupported
            onImplicitHeightChanged: listView !== null ? listView.scheduleRecalcSize() : 0
            onImplicitWidthChanged: listView !== null ? listView.scheduleRecalcSize() : 0

            MouseArea {
                enabled: name !== "" && item.enabled && phoneSupported
                anchors.fill: parent
                hoverEnabled: true
                onEntered: {
                    Tablet.playSound(TabletEnums.ButtonHover);
                    listView.currentIndex = index
                }

                onClicked: {
                    Tablet.playSound(TabletEnums.ButtonClick);
                    root.selected(item);
                }
            }
        }

        function scheduleRecalcSize() {
            if (recalcPending) {
                return;
            }
            recalcPending = true;
            Qt.callLater(recalcSize);
        }

        function recalcSize() {
            recalcPending = false;
            if (!model || model.count !== count || !visible) {
                return;
            }

            var maxWidth = width;
            var newHeight = 0;
            // Never walk the model by changing currentIndex here. Doing so
            // creates/releases delegates from inside delegate size-change
            // handlers and can trip QQmlDelegateModel's objectRef assertion.
            var delegates = contentItem.children;
            for (var i = 0; i < delegates.length; ++i) {
                var delegateItem = delegates[i];
                if (delegateItem.implicitWidth !== undefined && delegateItem.implicitWidth > maxWidth) {
                    maxWidth = delegateItem.implicitWidth;
                }
                if (delegateItem.visible && delegateItem.implicitHeight !== undefined) {
                    newHeight += delegateItem.implicitHeight;
                }
            }
            newHeight += hifi.dimensions.menuPadding.y * 2;  // White space at top and bottom.
            if (maxWidth > width) {
                width = maxWidth;
            }
            if (newHeight > contentHeight) {
                contentHeight = newHeight;
            }
        }
        
        Keys.onUpPressed: previousItem();
        Keys.onDownPressed: nextItem();
        Keys.onSpacePressed: selectCurrentItem();
        Keys.onRightPressed: selectCurrentItem();
        Keys.onReturnPressed: selectCurrentItem();
        Keys.onLeftPressed: previousPage();
    }

    function previousItem() { listView.currentIndex = (listView.currentIndex + listView.count - 1) % listView.count; }
    function nextItem() { listView.currentIndex = (listView.currentIndex + listView.count + 1) % listView.count; }
    function selectCurrentItem() { if (listView.currentIndex != -1) root.selected(currentItem.source); }
    function previousPage() { root.parent.pop(); }
}

