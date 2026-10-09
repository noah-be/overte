// Exercise the product control, native accessibility editing, and real key events.
#include <QAccessible>
#include <QCoreApplication>
#include <QGuiApplication>
#include <QJsonArray>
#include <QKeyEvent>
#include <QQmlComponent>
#include <QQmlEngine>
#include <QQuickWindow>
#include <cassert>
#include "PhoneAccessibilityTree.h"
#include "PhoneTextInputFixture.h"

int main(int argc, char** argv) {
    QGuiApplication app(argc, argv);
    QAccessible::setActive(true);
    assert(argc == 2);
    QQmlEngine engine;
    engine.addImportPath(QString::fromLocal8Bit(argv[1]) + "/interface/resources/qml");
    QQmlComponent component(&engine, QUrl::fromLocalFile(QString::fromLocal8Bit(argv[1])
        + "/tests/device/fixture/ControlledTextInput.qml"));
    auto panel = qobject_cast<QQuickItem*>(component.create());
    if (!panel) { qWarning() << component.errors(); }
    assert(panel);
    QQuickWindow window;
    window.resize(640, 360);
    panel->setParentItem(window.contentItem());
    window.show();
    QCoreApplication::processEvents();
    PhoneTextInputFixture fixture;
    assert(fixture.focus(panel));
    QCoreApplication::processEvents();
    const auto empty = fixture.snapshot(app.inputMethod()->isVisible());
    assert(empty.value("value").toString().isEmpty());
    assert(empty.value("focused").toBool());
    const auto beforeSubmit = empty.value("submittedCount").toInt();
    PhoneAccessibilityTree bridge;
    const auto nodes = bridge.snapshot(panel, QSize(640, 360)).value("nodes").toArray();
    int editor = -1;
    for (auto node : nodes) {
        if (node.toObject().value("semanticId").toString() == "controlled.text") {
            assert(editor == -1);
            editor = node.toObject().value("id").toInt();
        }
    }
    assert(editor != -1);
    assert(bridge.action(editor, "set-text", QString::fromUtf8("Overte E2E äöüX")));
    assert(fixture.snapshot(false).value("value").toString() == QString::fromUtf8("Overte E2E äöüX"));
    QKeyEvent backspace(QEvent::KeyPress, Qt::Key_Backspace, Qt::NoModifier);
    QCoreApplication::sendEvent(&window, &backspace);
    QKeyEvent backspaceUp(QEvent::KeyRelease, Qt::Key_Backspace, Qt::NoModifier);
    QCoreApplication::sendEvent(&window, &backspaceUp);
    QKeyEvent enter(QEvent::KeyPress, Qt::Key_Return, Qt::NoModifier);
    QCoreApplication::sendEvent(&window, &enter);
    QKeyEvent enterUp(QEvent::KeyRelease, Qt::Key_Return, Qt::NoModifier);
    QCoreApplication::sendEvent(&window, &enterUp);
    const auto edited = fixture.snapshot(false);
    assert(edited.value("value").toString() == QString::fromUtf8("Overte E2E äöü"));
    assert(edited.value("submittedCount").toInt() == beforeSubmit + 1);
    assert(fixture.dismiss());
    assert(!fixture.snapshot(false).value("focused").toBool());
    assert(!panel->isVisible());
    delete panel;
    assert(fixture.snapshot(false).isEmpty());
    assert(!fixture.dismiss());
}
