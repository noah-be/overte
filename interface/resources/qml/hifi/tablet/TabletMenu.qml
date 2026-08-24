import QtQuick 2.5
import Qt5Compat.GraphicalEffects
import QtQuick.Controls 2.3
import QtQml 2.2


import "."
import stylesUit 1.0
import "../../controls"

FocusScope {
    id: tabletMenu
    objectName: "tabletMenu"

    width: parent.width
    height: parent.height

    property var rootMenu: WrappedMenu { objectName:"rootMenu" }
    property var point: Qt.point(50, 50);
    TabletMenuStack { id: menuPopperUpper }
    property string subMenu: ""
    signal sendToScript(var message);

    HifiConstants { id: hifi }

    Rectangle {
        id: bgNavBar
        height: 90
        z: 1
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
        anchors.right: parent.right
        anchors.rightMargin: 0
        anchors.left: parent.left
        anchors.leftMargin: 0
        anchors.topMargin: 0
        anchors.top: parent.top

        HiFiGlyphs {
            id: menuRootIcon
            text: breadcrumbText.text !== "Menu" ? hifi.glyphs.backward : ""
            size: 72
            anchors.verticalCenter: parent.verticalCenter
            anchors.left: parent.left
            width: breadcrumbText.text === "Menu" ? 32 : 50
            visible: breadcrumbText.text !== "Menu"

            MouseArea {
                anchors.fill: parent
                hoverEnabled: true
                onEntered: iconColorOverlay.color = "#1fc6a6";
                onExited: iconColorOverlay.color = "#34a2c7";
                onClicked: {
                    menuPopperUpper.closeLastMenu();
                    tabletRoot.playButtonClickSound();
                }
            }
        }

        ColorOverlay {
            id: iconColorOverlay
            anchors.fill: menuRootIcon
            source: menuRootIcon
            color: "#34a2c7"
        }

        RalewayBold {
            id: breadcrumbText
            text: "Menu"
            size: 26
            color: "#e3e3e3"
            anchors.verticalCenter: parent.verticalCenter
            anchors.left: menuRootIcon.right
            anchors.leftMargin: 15
        }
    }

    function pop() {
        menuPopperUpper.closeLastMenu();
    }

    function setRootMenu(rootMenu, subMenu) {
        tabletMenu.subMenu = subMenu;
        tabletMenu.rootMenu = rootMenu;
        buildMenu()
    }

    function menuCount(menu) {
        if (!menu) {
            return 0;
        }
        if (typeof menu.count === "number") {
            return menu.count;
        }
        var legacyItems = menu["items"];
        return legacyItems ? legacyItems.length : 0;
    }

    function menuItemAt(menu, index) {
        if (!menu) {
            return null;
        }
        if (typeof menu.itemAt === "function") {
            return menu.itemAt(index);
        }
        var legacyItems = menu["items"];
        return legacyItems && index < legacyItems.length ? legacyItems[index] : null;
    }

    function childMenuAt(menu, index) {
        if (!menu) {
            return null;
        }
        if (typeof menu.menuAt === "function") {
            return menu.menuAt(index);
        }
        var item = menuItemAt(menu, index);
        return item && item.type === MenuItemType.Menu ? item : null;
    }

    function buildMenu() {
        // Build submenu if specified.
        if (subMenu !== "") {
            var index = 0;
            var foundMenu = null;
            while (foundMenu === null && index < menuCount(rootMenu)) {
                var candidate = childMenuAt(rootMenu, index);
                var candidateItem = menuItemAt(rootMenu, index);
                var candidateTitle = candidate && candidate.title !== undefined
                    ? candidate.title : candidateItem && candidateItem.text !== undefined
                        ? candidateItem.text : "";
                if (candidate && candidateTitle === subMenu) {
                    foundMenu = candidate;
                } else {
                    index += 1;
                }
            }
            subMenu = "";  // Continue with full menu after initially displaying submenu.
            if (foundMenu !== null) {
                menuPopperUpper.popup(foundMenu);
                return;
            }
        }

        // Otherwise build whole menu.
        menuPopperUpper.popup(rootMenu);
    }
}
