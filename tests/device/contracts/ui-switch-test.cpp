// SPDX-License-Identifier: Apache-2.0
#include <QGuiApplication>
#include <QQmlComponent>
#include <QQmlContext>
#include <QQmlEngine>
#include <QQmlPropertyMap>
#include <QQmlProperty>
#include <QQuickItem>
#include <QQuickWindow>
#include <QSignalSpy>
#include <QtTest/QTest>
#include <cassert>
QQuickItem* findItem(QQuickItem* root, bool label, const QString& labelText = "Mute microphone") {
    for (auto child : root->childItems()) {
        if (label ? child->property("text").toString() == labelText :
            child->property("visualPosition").isValid() && child->property("focusPolicy").isValid()) { return child; }
        if (auto found = findItem(child, label, labelText)) { return found; }
    }
    return nullptr;
}
int main(int argc, char** argv) {
    QGuiApplication app(argc, argv);
    assert(argc == 2);
    QQmlEngine engine;
    QQmlPropertyMap audio;
    audio.insert("mutedDesktop", false); audio.insert("mutedHMD", false);
    engine.rootContext()->setContextProperty("AudioScriptingInterface", &audio);
    QQuickWindow window;
    window.resize(600,180); window.show();
    for (int mode : {0,1}) {
        audio.insert("mutedDesktop", false); audio.insert("mutedHMD", false);
        QQmlComponent component(&engine, QUrl::fromLocalFile(QString::fromLocal8Bit(argv[1])));
        auto* root = qobject_cast<QQuickItem*>(component.create());
        if (!root) { qFatal("%s", qPrintable(component.errorString())); }
        root->setParentItem(window.contentItem());
        root->setProperty("mode", mode);
        auto* control = qobject_cast<QQuickItem*>(root->property("control").value<QObject*>());
        assert(control);
        control->setPosition(QPointF(220,20)); // Fixture layout leaves room for both external labels.
        auto* native = findItem(control, false);
        auto* label = findItem(control, true);
        assert(native && label);
        assert(control->implicitHeight() >= 28);
        QTest::qWait(30);
        assert(QQmlProperty(native, "Accessible.name", QQmlEngine::contextForObject(native)).read().toString() == "Mute microphone");
        QSignalSpy clicks(control, SIGNAL(clicked())); assert(clicks.isValid());
        const auto labelPoint = label->mapToScene(QPointF(label->width()/2,label->height()/2)).toPoint();
        QTest::mouseClick(&window, Qt::LeftButton, Qt::NoModifier, labelPoint);
        assert(control->property("checked").toBool());
        assert(clicks.count() == 1); // Label must deliver the actual Audio onClicked action.
        const QString selected = mode == 0 ? "mutedDesktop" : "mutedHMD";
        const QString other = mode == 0 ? "mutedHMD" : "mutedDesktop";
        assert(audio.value(selected).toBool() && !audio.value(other).toBool());
        native->forceActiveFocus(Qt::TabFocusReason);
        QTest::keyClick(&window, Qt::Key_Space);
        assert(!control->property("checked").toBool() && !audio.value(selected).toBool() && clicks.count() == 2);
        control->setVisible(false);
        QCoreApplication::processEvents();
        assert(!native->hasActiveFocus() && native->property("focusPolicy").toInt() == Qt::NoFocus);
        assert(QMetaObject::invokeMethod(control, "chooseCheckedByUser", Q_ARG(QVariant, QVariant(true))));
        assert(!audio.value(selected).toBool());
        QTest::mouseClick(&window, Qt::LeftButton, Qt::NoModifier, labelPoint);
        assert(clicks.count() == 2);
        control->setVisible(true);
        native->forceActiveFocus(Qt::TabFocusReason);
        control->setEnabled(false);
        QCoreApplication::processEvents();
        assert(!native->hasActiveFocus() && native->property("focusPolicy").toInt() == Qt::NoFocus);
        control->setEnabled(true);
        auto sentinel = new QQuickItem(window.contentItem());
        sentinel->setActiveFocusOnTab(true); sentinel->forceActiveFocus(Qt::TabFocusReason);
        QTest::keyClick(&window, Qt::Key_Tab);
        assert(native->hasActiveFocus());
        delete sentinel;
        QTest::keyClick(&window, Qt::Key_Space);
        assert(audio.value(selected).toBool() && clicks.count() == 3);
        control->setProperty("labelTextOff", "Unmute microphone");
        QTest::qWait(30);
        auto* offLabel = findItem(control, true, "Unmute microphone"); assert(offLabel);
        const auto offPoint = offLabel->mapToScene(QPointF(offLabel->width()/2,offLabel->height()/2)).toPoint();
        QTest::mousePress(&window, Qt::LeftButton, Qt::NoModifier, offPoint);
        QTest::mouseMove(&window, QPoint(590,170));
        QTest::mouseRelease(&window, Qt::LeftButton, Qt::NoModifier, QPoint(590,170));
        assert(clicks.count() == 3 && audio.value(selected).toBool());
        QTest::mouseClick(&window, Qt::LeftButton, Qt::NoModifier, offPoint);
        assert(clicks.count() == 4 && !audio.value(selected).toBool());
        delete root;
    }
}
