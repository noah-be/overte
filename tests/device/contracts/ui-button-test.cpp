// SPDX-License-Identifier: Apache-2.0
#include <QFile>
#include <QGuiApplication>
#include <QQmlComponent>
#include <QQmlContext>
#include <QQmlEngine>
#include <QQuickItem>
#include <QQuickWindow>
#include <QSignalSpy>
#include <QtTest/QTest>
#include <cassert>
#include <vector>
#include "ui-button-boundary.h"
static std::vector<QString> messages;
static void capture(QtMsgType, const QMessageLogContext&, const QString& text) { messages.push_back(text); }
int main(int argc, char** argv) {
    QGuiApplication app(argc, argv);
    assert(argc == 3);
    qmlRegisterUncreatableType<TabletBoundary>("TabletScriptingInterface", 1, 0, "TabletEnums", "test enum boundary");
    TabletBoundary tablet;
    QQmlEngine::setObjectOwnership(&tablet, QQmlEngine::CppOwnership);
    QQmlEngine engine;
    engine.rootContext()->setContextProperty("Tablet", &tablet);
    engine.rootContext()->setContextProperty("testPlatformOS", QString::fromLocal8Bit(argv[2]));
    engine.globalObject().setProperty("actionBoundary", engine.newQObject(&tablet));
    QFile source(QString::fromLocal8Bit(argv[1]));
    assert(source.open(QIODevice::ReadOnly));
    auto bytes = source.readAll();
    // Only OS identity is substituted, not the complete production component,
    // its handlers, styles, real Qt Controls implementation or input delivery.
    bytes.replace("Qt.platform.os", "testPlatformOS");
    QQmlComponent component(&engine);
    component.setData(bytes, QUrl::fromLocalFile(source.fileName()));
    auto* object = component.create();
    if (!object) { qFatal("%s", qPrintable(component.errorString())); }
    auto* button = qobject_cast<QQuickItem*>(object);
    assert(button);
    button->setProperty("text", "button-label-private-canary");
    button->setProperty("androidClickAction", QVariant::fromValue(engine.evaluate("(function(){actionBoundary.action();})")));
    QQuickWindow window;
    window.resize(500, 300);
    button->setParentItem(window.contentItem());
    button->setPosition(QPointF(20,20));
    button->setSize(QSizeF(200,60));
    window.show();
    QCoreApplication::processEvents();
    QSignalSpy clicked(button, SIGNAL(clicked()));
    QSignalSpy cancelled(button, SIGNAL(canceled()));
    assert(clicked.isValid() && cancelled.isValid());
    qInstallMessageHandler(capture); // Raw capture, no global payload sanitizer.
    const QPoint inside(80,40), outside(400,200);
    QTest::mouseClick(&window, Qt::LeftButton, Qt::NoModifier, inside);
    assert(clicked.count() == 1 && tablet.clicks == 1);
    assert(tablet.actions == (QString::fromLocal8Bit(argv[2]) == "android" ? 1 : 0));
    QTest::mousePress(&window, Qt::LeftButton, Qt::NoModifier, inside);
    QTest::mouseMove(&window, outside);
    QTest::mouseRelease(&window, Qt::LeftButton, Qt::NoModifier, outside);
    assert(cancelled.count() >= 1);
    assert(clicked.count() == 1 && tablet.clicks == 1); // A canceled press is not activation.
    button->forceActiveFocus(Qt::TabFocusReason);
    QTest::keyClick(&window, Qt::Key_Space);
    assert(clicked.count() == 2);
    button->setVisible(false);
    QCoreApplication::processEvents();
    assert(!button->hasActiveFocus() && button->property("focusPolicy").toInt() == Qt::NoFocus);
    QTest::keyClick(&window, Qt::Key_Space);
    assert(clicked.count() == 2);
    button->setVisible(true);
    button->forceActiveFocus(Qt::TabFocusReason);
    button->setEnabled(false);
    QCoreApplication::processEvents();
    assert(!button->hasActiveFocus() && button->property("focusPolicy").toInt() == Qt::NoFocus);
    QTest::mouseClick(&window, Qt::LeftButton, Qt::NoModifier, inside);
    assert(clicked.count() == 2);
    button->setEnabled(true);
    button->forceActiveFocus(Qt::TabFocusReason);
    assert(button->property("focusPolicy").toInt() & Qt::TabFocus);
    QTest::keyClick(&window, Qt::Key_Space);
    assert(clicked.count() == 3);
    QTest::mousePress(&window, Qt::LeftButton, Qt::NoModifier, inside);
    button->setVisible(false);
    QTest::mouseRelease(&window, Qt::LeftButton, Qt::NoModifier, inside);
    assert(clicked.count() == 3);
    button->setVisible(true);
    QTest::mousePress(&window, Qt::LeftButton, Qt::NoModifier, inside);
    button->setEnabled(false);
    QTest::mouseRelease(&window, Qt::LeftButton, Qt::NoModifier, inside);
    assert(clicked.count() == 3);
    button->setEnabled(true);
    auto parent = new QQuickItem(window.contentItem());
    parent->setSize(QSizeF(400,200));
    button->setParentItem(parent);
    button->forceActiveFocus(Qt::TabFocusReason);
    parent->setVisible(false);
    QCoreApplication::processEvents();
    assert(!button->hasActiveFocus() && button->property("focusPolicy").toInt() == Qt::NoFocus);
    parent->setVisible(true);
    button->setProperty("androidClickAction", 17); // Wrong binding is not invoked as a function.
    QTest::mouseClick(&window, Qt::LeftButton, Qt::NoModifier, inside);
    assert(clicked.count() == 4 && tablet.clicks == 4);
    for (const auto& message : messages) { assert(!message.contains("button-label-private-canary")); }
    qInstallMessageHandler(nullptr);
    delete button;
    delete parent;
}
