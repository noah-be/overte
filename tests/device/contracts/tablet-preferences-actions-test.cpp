// SPDX-License-Identifier: Apache-2.0
#include <QGuiApplication>
#include <QQmlComponent>
#include <QQmlContext>
#include <QQmlEngine>
#include <QQmlExpression>
#include <QQuickItem>
#include <QQuickWindow>
#include <QLoggingCategory>
#include <QtTest/QTest>
#include <cassert>
#include <vector>
static std::vector<QString> messages;
static void capture(QtMsgType, const QMessageLogContext&, const QString& text) { messages.push_back(text); }
int main(int argc, char** argv) {
    QGuiApplication app(argc, argv);
    QLoggingCategory::setFilterRules("qml.debug=true\nqml.info=true\nqml.warning=true");
    assert(argc == 3);
    const QString variant = QString::fromLocal8Bit(argv[2]);
    assert(variant == "main" || variant == "phone" || variant == "apple");
    qmlRegisterModule("TabletScriptingInterface", 1, 0);
    QQmlEngine engine;
    auto tablet = engine.evaluate("({playSound:function(){}, getTablet:function(){return testNavigation;}})");
    auto enums = engine.evaluate("({ButtonClick:2,ButtonHover:1})");
    auto hmd = engine.evaluate("({active:false})");
    engine.rootContext()->setContextProperty("Tablet", QVariant::fromValue(tablet));
    engine.rootContext()->setContextProperty("TabletEnums", QVariant::fromValue(enums));
    engine.rootContext()->setContextProperty("HMD", QVariant::fromValue(hmd));
    QQuickWindow window;
    window.resize(600,240); window.show();
    for (const char* platform : {"android", "linux", "ios"}) {
        engine.rootContext()->setContextProperty("testPlatformOS", QString::fromLatin1(platform));
        for (bool active : {false, true}) {
            hmd.setProperty("active", active);
            for (int route = 0; route < 3; ++route) {
                for (bool cancel : {false, true}) {
                    QQmlComponent component(&engine, QUrl::fromLocalFile(QString::fromLocal8Bit(argv[1])));
                    auto* root = qobject_cast<QQuickItem*>(component.create());
                    if (!root) { qFatal("%s", qPrintable(component.errorString())); }
                    root->setParentItem(window.contentItem());
                    root->setProperty("previousFlag", route == 1);
                    root->setProperty("scriptFlag", route == 2);
                    auto* navigation = root->property("navigationItem").value<QObject*>();
                    assert(navigation);
                    QQmlEngine::setObjectOwnership(navigation, QQmlEngine::CppOwnership);
                    engine.globalObject().setProperty("testNavigation", engine.newQObject(navigation));
                    auto* button = root->findChild<QQuickItem*>(cancel
                        ? (variant == "phone" ? "nav.back" : "GeneralPreferencesCancel") : "GeneralPreferencesSave");
                    assert(button);
                    const bool baseCallback = QString::fromLatin1(platform) == "android"
                        || (variant == "apple" && QString::fromLatin1(platform) == "ios");
                    assert(button->property("usesAndroidClickAction").isValid());
                    assert(button->property("usesAndroidClickAction").toBool() == baseCallback);
                    QCoreApplication::processEvents();
                    QTest::qWait(30); // Let the real Qt positioner polish before pointer hit testing.
                    const QPoint inside = button->mapToScene(QPointF(button->width()/2, button->height()/2)).toPoint();
                    const QPoint outside(590,220);
                    messages.clear(); qInstallMessageHandler(capture);
                    QQmlExpression captureProbe(engine.rootContext(), root, "console.info('capture-ready')");
                    captureProbe.evaluate();
                    bool captured = false;
                    for (const auto& message : messages) { captured = captured || message.contains("capture-ready"); }
                    assert(captured); // The raw log sink must actually receive QML console output.
                    messages.clear();
                    QTest::mousePress(&window, Qt::LeftButton, Qt::NoModifier, inside);
                    QTest::mouseMove(&window, outside);
                    QTest::mouseRelease(&window, Qt::LeftButton, Qt::NoModifier, outside);
                    assert(root->property("saves").toInt() == 0 && root->property("restores").toInt() == 0);
                    QTest::mouseClick(&window, Qt::LeftButton, Qt::NoModifier, inside);
                    if (root->property("saves").toInt() != (cancel ? 0 : 1) || root->property("restores").toInt() != (cancel ? 1 : 0)) {
                        fprintf(stderr, "case=%s hmd=%d route=%d cancel=%d saves=%d restores=%d\n", platform, active, route, cancel,
                            root->property("saves").toInt(), root->property("restores").toInt());
                    }
                    assert(root->property("saves").toInt() == (cancel ? 0 : 1));
                    assert(root->property("restores").toInt() == (cancel ? 1 : 0));
                    const bool callbackCancel = cancel && baseCallback;
                    const bool settingsBack = callbackCancel && variant == "phone";
                    assert(root->property("homes").toInt() == ((callbackCancel && !settingsBack) || (!callbackCancel && !active && route == 0) ? 1 : 0));
                    assert(root->property("previous").toInt() == (!callbackCancel && route == 1 ? 1 : 0));
                    assert(root->property("scripts").toInt() == (settingsBack || (!callbackCancel && route == 2) ? 1 : 0));
                    assert(root->property("lastMessage").toString() == (settingsBack ? "settings.back" : (!callbackCancel && route == 2 ? "returnToPreviousApp" : "")));
                    assert(root->property("pops").toInt() == (!callbackCancel && active && route == 0 ? 1 : 0));
                    if (callbackCancel) { assert(!root->property("keyboardRaised").toBool()); }
                    for (const auto& message : messages) { assert(!message.contains("category-private-canary")); }
                    qInstallMessageHandler(nullptr);
                    delete root;
                }
            }
        }
    }
}
