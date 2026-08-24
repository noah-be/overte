//
//  TabletMenuStack.qml
//
//  Created by Dante Ruiz  on 13 Feb 2017
//  Copyright 2016 High Fidelity, Inc.
//
//  Distributed under the Apache License, Version 2.0.
//  See the accompanying file LICENSE or http://www.apache.org/licenses/LICENSE-2.0.html
//

import QtQuick 2.5
import QtQuick.Controls 2.3

import "."

Item {
    id: root
    anchors.fill: parent
    width: parent.width
    height: parent.height
    objectName: "tabletMenuHandlerItem"

    StackView {
        anchors.fill: parent
        id: d
        objectName: "stack"

        property var menuStack: []
        property var topMenu: null;
        property var modelMaker: Component { ListModel { } }
        property var menuViewMaker: Component {
            TabletMenuView {
                id: subMenu
                onSelected: d.handleSelection(subMenu, currentItem, item, itemKind, childMenu)
            }
        }
        property var delay: Timer { // No setTimeout in QML.
            property var menuItem: null;
            interval: 0
            repeat: false
            running: false
            function trigger(item) { // Capture item and schedule asynchronous Timer.
                cancelPending();
                menuItem = item;
                start();
            }
            function cancelPending() {
                stop();
                menuItem = null;
            }
            onTriggered: {
                var pendingItem = menuItem;
                menuItem = null;
                // The menu or platform policy may have changed between touch
                // release and this deferred callback. Revalidate fail-closed.
                if (pendingItem === null ||
                        (d.isAndroidPhoneTablet() && !d.isPhoneMenuItemSupported(pendingItem))) {
                    return;
                }
                if (typeof pendingItem.trigger === "function") {
                    pendingItem.trigger();
                } else if (typeof pendingItem.triggered === "function") {
                    // Qt 6 MenuItem exposes the triggered signal but no longer
                    // provides the Qt 5 trigger() convenience method.
                    pendingItem.triggered();
                }
            }
        }

        function pushSource(path) {
            // Workaround issue https://bugreports.qt.io/browse/QTBUG-75516 in Qt 5.12.3
            // by creating the manually, instead of letting StackView do it for us.
            var item = Qt.createComponent(Qt.resolvedUrl("../../" + path));
            d.push(item);
            if (d.currentItem.sendToScript !== undefined) {
                d.currentItem.sendToScript.connect(tabletMenu.sendToScript);
            }
            d.currentItem.focus = true;
            d.currentItem.forceActiveFocus();
            if (d.currentItem.title !== undefined) {
                breadcrumbText.text = d.currentItem.title;
            }
            if (typeof bgNavBar !== "undefined") {
                d.currentItem.y = bgNavBar.height;
                d.currentItem.height -= bgNavBar.height;
            }
        }

        function popSource() {
            console.log("trying to pop page");
            closeLastMenu();
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

        function itemKind(item, childMenu) {
            if (childMenu !== null) {
                return MenuItemType.Menu;
            }
            if (item && item.type !== undefined) {
                return item.type;
            }
            return item && item.text !== undefined
                ? MenuItemType.Item : MenuItemType.Separator;
        }

        function itemLabel(item, kind, childMenu) {
            if (kind === MenuItemType.Menu) {
                return childMenu && childMenu.title !== undefined
                    ? childMenu.title : item && item.text !== undefined ? item.text : "";
            }
            return item && item.text !== undefined ? item.text : "";
        }

        function toModel(menu) {
            var result = modelMaker.createObject(tabletMenu);

            for (var i = 0; i < menuCount(menu); ++i) {
                var item = menuItemAt(menu, i);
                var childMenu = childMenuAt(menu, i);
                var kind = itemKind(item, childMenu);
                var label = itemLabel(item, kind, childMenu);
                var source = item || childMenu;
                var phoneSupported = isPhoneMenuItemSupported(source, kind, label);
                var unavailableSuffix = isAndroidPhoneTablet() && !phoneSupported
                    ? " (Unavailable on Android)" : "";
                var sourceVisible = kind === MenuItemType.Menu
                    || !source || source.visible !== false;
                var sourceEnabled = !source || source.enabled !== false;
                switch (kind) {
                case MenuItemType.Menu:
                    result.append({
                        "name": label + unavailableSuffix,
                        "item": source,
                        "itemKind": kind,
                        "childMenu": childMenu,
                        "phoneSupported": phoneSupported,
                        "itemVisible": sourceVisible,
                        "itemEnabled": sourceEnabled
                    })
                    break;
                case MenuItemType.Item:
                    if (label !== "Users Online") {
                        result.append({
                            "name": label + unavailableSuffix,
                            "item": source,
                            "itemKind": kind,
                            "childMenu": null,
                            "phoneSupported": phoneSupported,
                            "itemVisible": sourceVisible,
                            "itemEnabled": sourceEnabled
                        })
                    }
                    break;
                case MenuItemType.Separator:
                    result.append({
                        "name": "",
                        "item": source,
                        "itemKind": kind,
                        "childMenu": null,
                        "phoneSupported": true,
                        "itemVisible": sourceVisible,
                        "itemEnabled": false
                    })
                    break;
                }
            }
            return result;
        }

        function isPhoneMenuItemSupported(item, kind, label) {
            if (!isAndroidPhoneTablet()) {
                return true;
            }

            if (kind === undefined) {
                kind = item && item.type !== undefined ? item.type : MenuItemType.Item;
            }
            if (label === undefined) {
                label = item && item.text !== undefined ? item.text
                    : item && item.title !== undefined ? item.title : "";
            }
            // Fail closed at the root. New desktop menus must be reviewed before
            // the phone tablet can trigger any of their actions.
            var supportedRootMenus = ["File", "View", "Navigate", "Settings"];
            var unsupportedActions = [
                "Quit",
                "Running Scripts",
                "Asset Browser",
                "Controls...",
                // These desktop settings expose developer-only menus or alter
                // the next-start recovery flow without a Phone confirmation UI.
                "Developer Menu",
                "Ask To Reset Settings on Start",
                // This native menu action opens the legacy preferences dialog.
                // The phone's dedicated SETTINGS app remains available separately.
                "General..."
            ];
            if (topMenu === null && kind === MenuItemType.Menu
                    && supportedRootMenus.indexOf(label) === -1) {
                return false;
            }
            if (kind === MenuItemType.Item && unsupportedActions.indexOf(label) !== -1) {
                return false;
            }

            // These actions configure hardware/presentation modes which are not
            // exposed by the Android phone client.
            return !/(HMD|VR|Desktop)/i.test(label || "");
        }

        function isAndroidPhoneTablet() {
            return tabletRoot.screenSpaceMode === true;
        }

        function popMenu() {
            if (d.depth) {
                d.pop();
            }
            if (d.depth) {
                topMenu = d.currentItem;
                topMenu.focus = true;
                topMenu.forceActiveFocus();
                // show current menu level on nav bar
                if (topMenu.objectName === "" || d.depth === 1) {
                    breadcrumbText.text = "Menu";
                } else {
                    breadcrumbText.text = topMenu.objectName;
                }
            } else {
                breadcrumbText.text = "Menu";
                topMenu = null;
            }
        }

        function pushMenu(newMenu) {
            d.push({ item:newMenu, destroyOnPop: true});
            topMenu = newMenu;
            topMenu.focus = true;
            topMenu.forceActiveFocus();
        }

        function clearMenus() {
            delay.cancelPending()
            topMenu = null
            d.clear()
        }

        function clampMenuPosition(menu) {
            var margins = 0;
            if (menu.x < margins) {
                menu.x = margins
            } else if ((menu.x + menu.width + margins) > root.width) {
                menu.x = root.width - (menu.width + margins);
            }

            if (menu.y < 0) {
                menu.y = margins
            } else if ((menu.y + menu.height + margins) > root.height) {
                menu.y = root.height - (menu.height + margins);
            }
        }

        property Component exclusiveGroupMaker: Component {
            ButtonGroup {
            }
        }

        function buildMenu(menu) {
            // Menus must be childed to desktop for Z-ordering
            var newMenu = menuViewMaker.createObject(tabletMenu);
            console.debug('newMenu created: ', newMenu)

            var model = toModel(menu);

            newMenu.model = model;
            newMenu.isSubMenu = topMenu !== null;

            pushMenu(newMenu);
            return newMenu;
        }

        function handleSelection(parentMenu, selectedItem, item, kind, childMenu) {
            if (isAndroidPhoneTablet() && !selectedItem.platformEnabled) {
                return;
            }
            while (topMenu && topMenu !== parentMenu) {
                popMenu();
            }

            switch (kind) {
                case MenuItemType.Menu:
                    var menuTitle = childMenu && childMenu.title !== undefined
                        ? childMenu.title : selectedItem.text;
                    buildMenu(childMenu).objectName = menuTitle;
                    // show current menu level on nav bar
                    breadcrumbText.text = menuTitle;
                    break;

                case MenuItemType.Item:
                    console.log("Triggering " + selectedItem.text)
                    // Don't block waiting for modal dialogs and such that the menu might open.
                    delay.trigger(item);
                    break;
                }
        }

    }

    function popup(menu) {
        d.clearMenus();
        d.buildMenu(menu);
    }

    function closeLastMenu() {
        if (d.depth > 1) {
            d.popMenu();
            return true;
        }
        return false;
    }

    function previousItem() { d.topMenu.previousItem(); }
    function nextItem() { d.topMenu.nextItem(); }
    function selectCurrentItem() { d.topMenu.selectCurrentItem(); }
    function previousPage() { d.topMenu.previousPage(); }
}
