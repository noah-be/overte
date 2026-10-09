// Real offscreen Qt Quick items supply the Android bridge's tree and actions.
#include <QAccessible>
#include <QGuiApplication>
#include <QJsonArray>
#include <QQmlComponent>
#include <QQmlEngine>
#include <QQuickItem>
#include <QQuickWindow>
#include <cassert>
#include "PhoneAccessibilityTree.h"

int main(int argc, char** argv) {
    QGuiApplication app(argc, argv);
    QAccessible::setActive(true);
    QQmlEngine engine;
    QQmlComponent component(&engine);
    component.setData(R"qml(import QtQuick
Item {
    width: 200; height: 100
    objectName: "tablet.home"
    Accessible.role: Accessible.Client
    Accessible.name: "Tablet home"
    property int presses: 0
    Item {
        x: 10; y: 20; width: 50; height: 30
        objectName: "app.settings"
        Accessible.role: Accessible.Button
        Accessible.name: "Settings"
        Accessible.onPressAction: parent.presses += 1
    }
    TextInput {
        x: 80; y: 20; width: 80; height: 30
        objectName: "controlled.text"
        Accessible.role: Accessible.EditableText
        Accessible.name: "Text input"
        text: "before"
    }
    Item {
        objectName: "forbidden.hidden"
        width: 20; height: 20; visible: false
        Accessible.role: Accessible.Button
        Accessible.name: "Hidden"
    }
    Item {
        objectName: "forbidden.ignored"
        width: 20; height: 20
        Accessible.role: Accessible.Button
        Accessible.ignored: true
        Accessible.name: "Ignored"
    }
    Item {
        objectName: "forbidden.outside"
        x: 250; width: 20; height: 20
        Accessible.role: Accessible.Button
        Accessible.name: "Outside"
    }
})qml", QUrl());
    auto root = qobject_cast<QQuickItem*>(component.create());
    assert(root);
    QQuickWindow offscreen;
    root->setParentItem(offscreen.contentItem());
    // The QQuickWindow stays hidden, as in the real Android render-control
    // path. The actual rendered item viewport determines exposed nodes.
    PhoneAccessibilityTree bridge;
    auto frame = bridge.snapshot(root, QSize(400, 200));
    assert(frame.value("ready").toBool());
    int buttonId = -1, textId = -1;
    const auto nodes = frame.value("nodes").toArray();
    assert(nodes.size() == 3);
    for (auto value : nodes) {
        auto node = value.toObject();
        const auto id = node.value("semanticId").toString();
        assert(!id.startsWith("forbidden."));
        if (id == "app.settings") {
            buttonId = node.value("id").toInt();
            assert(node.value("name") == "Settings");
            assert(node.value("clickable").toBool());
            assert(node.value("left").toDouble() == 20);
            assert(node.value("top").toDouble() == 40);
            assert(node.value("right").toDouble() == 120);
        }
        if (id == "controlled.text") {
            textId = node.value("id").toInt();
            assert(node.value("editable").toBool());
            assert(node.value("text") == "before");
        }
    }
    assert(buttonId != -1 && textId != -1);
    assert(bridge.action(buttonId, "press"));
    assert(root->property("presses").toInt() == 1);
    assert(bridge.action(textId, "set-text", QString::fromUtf8("Overte äöü")));
    auto input = root->findChild<QQuickItem*>("controlled.text");
    assert(input->property("text").toString() == QString::fromUtf8("Overte äöü"));
    assert(!bridge.action(textId, "set-text", QString(4097, 'a')));
    input->setProperty("readOnly", true);
    assert(!bridge.action(textId, "set-text", "forbidden read-only replacement"));
    assert(input->property("text").toString() == QString::fromUtf8("Overte äöü"));
    input->setProperty("readOnly", false);
    auto button = root->findChild<QQuickItem*>("app.settings");
    button->setEnabled(false);
    assert(!bridge.action(buttonId, "press"));
    delete button;
    assert(!bridge.action(buttonId, "press"));
    input->setVisible(false);
    assert(!bridge.action(textId, "focus"));
    assert(!bridge.action(textId, "arbitrary-action"));
    delete root;
    assert(!bridge.action(textId, "set-text", "after destruction"));
}
