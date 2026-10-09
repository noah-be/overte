// SPDX-License-Identifier: Apache-2.0
// Reproduce an accessibility query before the first Qt Quick import.
#include <QAccessible>
#include <QAccessibleActionInterface>
#include <QGuiApplication>
#include <QStyleHints>
#include <QQmlComponent>
#include <QQmlEngine>
#include <QQuickWindow>
#include <QQuickItem>
#include "PhoneQuickBootstrap.h"

int main(int argc, char** argv) {
    QGuiApplication application(argc, argv);
    if (argc != 2) { return 1; }
    QAccessible::setActive(true);
    if (QString::fromUtf8(argv[1]) == "fixed") { phoneInitializeQuickTypes(); }
    QQuickWindow early;
    QQuickItem earlyControl(early.contentItem());
    earlyControl.setActiveFocusOnTab(true);
    earlyControl.setWidth(10);
    earlyControl.setHeight(10);
    // Native focus traversal consults effectiveAccessibleRole even before
    // the Qt Quick plugin has installed an accessibility factory.
    application.styleHints()->setTabFocusBehavior(Qt::TabFocusTextControls);
    early.contentItem()->nextItemInFocusChain(true);
    application.styleHints()->setTabFocusBehavior(Qt::TabFocusAllControls);
    QQmlEngine engine;
    QQmlComponent component(&engine);
    component.setData(R"qml(import QtQuick 2.7
Item {
    width: 100; height: 100
    property int pressed: 0
    Accessible.role: Accessible.Button
    Accessible.name: "Settings"
    Accessible.onPressAction: pressed += 1
})qml", QUrl());
    auto item = qobject_cast<QQuickItem*>(component.create());
    if (!item) { return 3; }
    item->setParentItem(early.contentItem());
    auto accessible = QAccessible::queryAccessibleInterface(item);
    if (!accessible || accessible->role() != QAccessible::Button
            || accessible->text(QAccessible::Name) != "Settings") { delete item; return 4; }
    auto actions = accessible->actionInterface();
    if (!actions || !actions->actionNames().contains(QAccessibleActionInterface::pressAction())) {
        delete item; return 5;
    }
    actions->doAction(QAccessibleActionInterface::pressAction());
    const bool dispatched = item->property("pressed").toInt() == 1;
    delete item;
    return dispatched ? 0 : 6;
}
