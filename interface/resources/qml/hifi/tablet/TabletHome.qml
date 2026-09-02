import QtQuick 2.7
import QtQuick.Controls 2.2
import QtGraphicalEffects 1.0
import QtQuick.Layouts 1.3

import TabletScriptingInterface 1.0

import "."
import stylesUit 1.0 as HifiStylesUit
import "../audio" as HifiAudio

Item {
    id: tablet
    objectName: "tablet"
    readonly property string semanticScreenId: "tablet.home"
    property var tabletProxy: Tablet.getTablet("com.highfidelity.interface.tablet.system");

    property var currentGridItems: null

    focus: true

    TabletTouchConfiguration {
        id: presentation
        availableWidth: tablet.width
        availableHeight: tablet.height
    }

    Rectangle {
        id: bgTopBar
        height: presentation.topBarHeight

        anchors {
            top: parent.top
            left: parent.left
            right: parent.right
        }

        gradient: Gradient {
            GradientStop {
                position: 0
                color: "#2b2b2b"
            }

            GradientStop {
                position: 1
                color: "#1e1e1e"
            }
        }

        HifiAudio.MicBarApplication {
            id: muteBar

            anchors {
                left: parent.left
                leftMargin: presentation.horizontalMargin
                verticalCenter: parent.verticalCenter
            }
        }

        SitStandToggle {
            visible: typeof HMD !== "undefined" && HMD ? HMD.active : false

            anchors {
                left: muteBar.right
                leftMargin: 10
                verticalCenter: parent.verticalCenter
            }
        }

        Item {
            id: rightContainer
            width: clockItem.width > loginItem.width ? clockItem.width + clockAmPmTextMetrics.width :
                loginItem.width + clockAmPmTextMetrics.width
            height: parent.height
            anchors.top: parent.top
            anchors.topMargin: 15
            anchors.right: parent.right
            anchors.rightMargin: presentation.horizontalMargin
            anchors.bottom: parent.bottom

            function timeChanged() {
                var date = new Date();
                clockTime.text = date.toLocaleTimeString(Qt.locale("en_US"), "h:mm ap");
                var regex = /[\sa-zA-z]+/;
                clockTime.text = clockTime.text.replace(regex, "");
                clockAmPm.text = date.toLocaleTimeString(Qt.locale("en_US"), "ap");
            }

            Timer {
                interval: 1000; running: true; repeat: true;
                onTriggered: rightContainer.timeChanged();
            }

            Item {
                id: clockAmPmItem
                width: clockAmPmTextMetrics.width
                height: clockAmPmTextMetrics.height

                anchors.top: parent.top
                anchors.right: parent.right
                TextMetrics {
                    id: clockAmPmTextMetrics
                    text: clockAmPm.text
                    font: clockAmPm.font
                }
                Text {
                    anchors.left: parent.left
                    id: clockAmPm
                    anchors.right: parent.right
                    font.capitalization: Font.AllUppercase
                    font.pixelSize: Math.round(12 * presentation.textScale)
                    font.family: "Rawline"
                    color: "#afafaf"
                }
            }

            Item {
                id: clockItem
                width: clockTimeTextMetrics.width
                height: clockTimeTextMetrics.height
                anchors {
                    top: parent.top
                    topMargin: -10
                    right: clockAmPmItem.left
                    rightMargin: 5
                }
                TextMetrics {
                    id: clockTimeTextMetrics
                    text: clockTime.text
                    font: clockTime.font
                }
                Text {
                    anchors.top: parent.top
                    anchors.right: parent.right
                    id: clockTime
                    font.bold: false
                    font.pixelSize: Math.round(36 * presentation.textScale)
                    font.family: "Rawline"
                    color: "#afafaf"
                }
            }

            Item {
                id: loginItem
                function openLogin() {
                    if (!Account.loggedIn) {
                        DialogsManager.showLoginDialog()
                    }
                }
                width: Math.max(loginTextMetrics.width, presentation.minimumTouchTarget)
                height: Math.max(loginTextMetrics.height, presentation.minimumTouchTarget)
                anchors {
                    bottom: parent.bottom
                    bottomMargin: 10
                    right: clockAmPmItem.left
                    rightMargin: 5
                }
                Text {
                    id: loginText
                    anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    text: Account.loggedIn ? tabletRoot.usernameShort : qsTr("Log in")
                    horizontalAlignment: Text.AlignRight
                    Layout.alignment: Qt.AlignRight
                    font.pixelSize: Math.round(18 * presentation.textScale)
                    font.family: "Rawline"
                    color: "#afafaf"
                }
                TextMetrics {
                    id: loginTextMetrics
                    text: loginText.text
                    font: loginText.font
                }

                MouseArea {
                    anchors.fill: parent
                    hoverEnabled: presentation.hoverSupported
                    activeFocusOnTab: !Account.loggedIn
                    Accessible.role: Accessible.Button
                    Accessible.name: loginText.text
                    Accessible.description: qsTr("Open the login dialog")
                    Accessible.ignored: Account.loggedIn
                    Accessible.onPressAction: loginItem.openLogin()
                    onClicked: loginItem.openLogin()
                    Keys.onReturnPressed: loginItem.openLogin()
                    Keys.onEnterPressed: loginItem.openLogin()
                    Keys.onSpacePressed: loginItem.openLogin()
                }
            }

            Component.onCompleted: {
                rightContainer.timeChanged();
            }
        }
    }

    Rectangle {
        id: bgMain
        gradient: Gradient {
            GradientStop {
                position: 0
                color: "#2b2b2b"
            }

            GradientStop {
                position: 1
                color: "#0f212e"
            }
        }
        anchors.bottom: parent.bottom
        anchors.right: parent.right
        anchors.left: parent.left
        anchors.top: bgTopBar.bottom

        SwipeView {
            id: swipeView
            clip: false
            currentIndex: -1
            property int previousIndex: -1
            Repeater {
                id: pageRepeater
                model: tabletProxy != null ? Math.ceil(tabletProxy.buttons.rowCount() / TabletEnums.ButtonsOnPage) : 0
                onItemAdded: {
                    item.proxyModel.sourceModel = tabletProxy != null ? tabletProxy.buttons : null;
                    item.proxyModel.pageIndex = index;
                }

                delegate: Item {
                    id: page
                    property TabletButtonsProxyModel proxyModel: TabletButtonsProxyModel {}

                    GridView {
                        id: gridView
                        flickableDirection: Flickable.AutoFlickIfNeeded
                        keyNavigationEnabled: false
                        highlightFollowsCurrentItem: false
                        // The containing SwipeView owns horizontal paging. The
                        // grid itself must not steal touchscreen drags.
                        interactive: false

                        property int previousGridIndex: -1

                        // true if any of the buttons contains mouse
                        property bool containsMouse: false

                        anchors {
                            verticalCenter: parent.verticalCenter
                            horizontalCenter: parent.horizontalCenter
                        }
                        width: Math.min(parent.width - 2 * presentation.horizontalMargin,
                            presentation.columns * (presentation.maximumButtonExtent + presentation.buttonSpacing))
                        height: Math.min(parent.height - 2 * presentation.verticalMargin,
                            rowCount * (presentation.maximumButtonExtent + presentation.buttonSpacing))

                        onCurrentIndexChanged: {
                            previousGridIndex = currentIndex
                        }

                        onMovementStarted: {
                            if (currentIndex < 0 || gridView.currentItem === undefined || gridView.contentItem.children.length - 1 < currentIndex) {
                                return;
                            }
                            var button = gridView.contentItem.children[currentIndex].children[0];
                            if (button.isActive) {
                                button.state = "active state";
                            } else {
                                button.state = "base state";
                            }
                        }

                        property int rowCount: Math.max(1, Math.ceil(count / presentation.columns))
                        property real buttonExtent: Math.min(presentation.maximumButtonExtent,
                            Math.max(1, Math.min(cellWidth - presentation.buttonSpacing,
                                cellHeight - presentation.buttonSpacing)))

                        cellWidth: width / presentation.columns
                        cellHeight: height / rowCount
                        flow: GridView.LeftToRight
                        model: page.proxyModel

                        delegate: Control {
                            id: wrapper
                            width: gridView.cellWidth
                            height: gridView.cellHeight

                            hoverEnabled: !presentation.touchOptimized

                            property bool containsMouse: gridView.containsMouse
                            onHoveredChanged: {
                                if (hovered && !gridView.containsMouse) {
                                    gridView.containsMouse = true
                                } else {
                                    gridView.containsMouse = false
                                }
                            }

                            property var proxy: modelData

                            TabletButton {
                                id: tabletButton

                                // Temporarily disable magnification
                                // scale: wrapper.hovered ? 1.25 : wrapper.containsMouse ? 0.75 : 1.0
                                // Behavior on scale { NumberAnimation { duration: 200; easing.type: Easing.Linear } }

                                anchors.centerIn: parent
                                width: gridView.buttonExtent
                                height: gridView.buttonExtent
                                hoverEnabled: !presentation.touchOptimized
                                prioritizeTap: presentation.touchOptimized
                                gridView: wrapper.GridView.view
                                buttonIndex: page.proxyModel.buttonIndex(uuid);
                                flickable: swipeView.contentItem;
                                onClicked: modelData.clicked()
                            }

                            Connections {
                                target: modelData;
                                function onPropertiesChanged() {
                                    updateProperties();
                                }
                            }

                            Component.onCompleted: updateProperties()

                            function updateProperties() {
                                var keys = Object.keys(modelData.properties).forEach(function (key) {
                                    if (tabletButton[key] !== modelData.properties[key]) {
                                        tabletButton[key] = modelData.properties[key];
                                    }
                                });
                                if (tabletButton.semanticId !== "") {
                                    tabletButton.objectName = tabletButton.semanticId;
                                }
                            }
                        }
                    }
                }
            }

            onCurrentIndexChanged: {
                if (swipeView.currentIndex < 0
                        || swipeView.itemAt(swipeView.currentIndex) === null
                        || swipeView.itemAt(swipeView.currentIndex).children[0] === null) {
                    return;
                }

                currentGridItems = swipeView.itemAt(swipeView.currentIndex).children[0];

                currentGridItems.currentIndex = (previousIndex > swipeView.currentIndex ? currentGridItems.count - 1 : 0);
                previousIndex = currentIndex;
            }

            hoverEnabled: !presentation.touchOptimized
            anchors {
                left: parent.left
                right: parent.right
                top: parent.top
                bottom: pageIndicator.top
            }
        }

        PageIndicator {
            id: pageIndicator
            currentIndex: swipeView.currentIndex
            visible: swipeView.count > 1

            delegate: Item {
                width: presentation.minimumTouchTarget
                height: presentation.minimumTouchTarget

                Rectangle {
                    property bool isHovered: false
                    anchors.centerIn: parent
                    opacity: index === pageIndicator.currentIndex || isHovered ? 0.95 : 0.45
                    implicitWidth: index === pageIndicator.currentIndex || isHovered ? 15 : 10
                    implicitHeight: implicitWidth
                    radius: width/2
                    color: isHovered && index !== pageIndicator.currentIndex ? "#1fc6a6" : "white"
                    Behavior on opacity {
                        OpacityAnimator {
                            duration: 100
                        }
                    }

                    MouseArea {
                        anchors.centerIn: parent
                        width: presentation.minimumTouchTarget
                        height: presentation.minimumTouchTarget
                        hoverEnabled: !presentation.touchOptimized
                        enabled: true
                        activeFocusOnTab: true
                        Accessible.role: Accessible.Button
                        Accessible.name: qsTr("Tablet page %1").arg(index + 1)
                        Accessible.description: index === pageIndicator.currentIndex
                            ? qsTr("Current page") : qsTr("Show page")
                        onEntered: parent.isHovered = true;
                        onExited: parent.isHovered = false;
                        onClicked: swipeView.currentIndex = index;
                        Keys.onReturnPressed: swipeView.currentIndex = index
                        Keys.onEnterPressed: swipeView.currentIndex = index
                        Keys.onSpacePressed: swipeView.currentIndex = index
                    }
                }
            }

            interactive: false
            height: presentation.pageIndicatorHeight
            anchors.bottom: closeTabletButton.top
            anchors.horizontalCenter: parent.horizontalCenter
            count: swipeView.count
        }

        Rectangle {
            id: closeTabletButton
            objectName: "androidTabletCloseButton"
            visible: presentation.showCloseButton
            enabled: visible
            width: Math.min(240, parent.width * 0.30)
            height: presentation.closeButtonHeight
            radius: 10
            color: closeTabletMouseArea.pressed ? "#169c86" : "#1fc6a6"
            border.width: 2
            border.color: "#75ead5"
            anchors.bottom: parent.bottom
            anchors.bottomMargin: presentation.closeButtonBottomMargin
            anchors.horizontalCenter: parent.horizontalCenter

            Text {
                anchors.centerIn: parent
                text: qsTr("CLOSE")
                color: "#10252d"
                font.family: "Rawline"
                font.bold: true
                font.pixelSize: Math.round(18 * presentation.textScale)
            }

            MouseArea {
                id: closeTabletMouseArea
                property string semanticId: "nav.close"
                anchors.fill: parent
                objectName: "OverteTabletClose"
                activeFocusOnTab: visible
                Accessible.id: objectName
                Accessible.role: Accessible.Button
                Accessible.name: qsTr("Close tablet")
                Accessible.description: qsTr("Return to the world controls")
                onClicked: tabletProxy.hideAndroidTablet()
                Keys.onReturnPressed: tabletProxy.hideAndroidTablet()
                Keys.onEnterPressed: tabletProxy.hideAndroidTablet()
                Keys.onSpacePressed: tabletProxy.hideAndroidTablet()
            }
        }

    }

    Component.onCompleted: {
        focus = true;
        forceActiveFocus();
    }

    Keys.onRightPressed: {
        if (!currentGridItems) {
            return;
        }

        var index = currentGridItems.currentIndex;
        currentGridItems.moveCurrentIndexRight();
        if (index === currentGridItems.count - 1 && index === currentGridItems.currentIndex) {
            if (swipeView.currentIndex < swipeView.count - 1) {
                swipeView.incrementCurrentIndex();
            }
        }
    }

    Keys.onLeftPressed: {
        if (!currentGridItems) {
            return;
        }

        var index = currentGridItems.currentIndex;
        currentGridItems.moveCurrentIndexLeft();
        if (index === 0 && index === currentGridItems.currentIndex) {
            if (swipeView.currentIndex > 0) {
                swipeView.decrementCurrentIndex();
            }
        }
    }
    Keys.onDownPressed: if (currentGridItems) currentGridItems.moveCurrentIndexDown();
    Keys.onUpPressed: if (currentGridItems) currentGridItems.moveCurrentIndexUp();
    Keys.onReturnPressed: {
        if (currentGridItems.currentItem) {
            currentGridItems.currentItem.proxy.clicked();
            if (tabletRoot) {
                tabletRoot.playButtonClickSound();
            }
        }
    }
}
