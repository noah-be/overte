// SPDX-License-Identifier: Apache-2.0
// Actual Qt 5 Settings controls, native enum boundary and short pointer input.
#include <QGuiApplication>
#include <QQmlComponent>
#include <QQmlEngine>
#include <QQmlContext>
#include <QQmlFileSelector>
#include <QQuickWindow>
#include <QQuickItem>
#include <QJSValue>
#include <QSignalSpy>
#include <QtTest/QTest>
#include <functional>
#include <cstdio>
class TabletBoundary : public QObject {
    Q_OBJECT
public:
    enum TabletAudioEvents { ButtonClick, ButtonHover, TabletOpen, TabletHandsIn, TabletHandsOut, Last };
    Q_ENUM(TabletAudioEvents)
    Q_INVOKABLE void playSound(TabletAudioEvents) {}
    Q_INVOKABLE QObject* getTablet(const QString&) { return this; }
};
class Surface : public QObject {
    Q_OBJECT
public:
    QQmlEngine* engine;
    Q_INVOKABLE void load(QUrl url, QQuickItem* parent, QJSValue callback) {
        QQmlComponent component(engine, url);
        auto object = component.beginCreate(engine->rootContext());
        if (!object) { qFatal("%s", qPrintable(component.errorString())); }
        auto item = qobject_cast<QQuickItem*>(object);
        // Match OffscreenSurface's actual parented-load lifecycle: callback
        // before attachment and completeCreate, not createObject's shortcut.
        auto result = callback.call({engine->newQObject(item)});
        if (result.isError()) { qFatal("%s", qPrintable(result.toString())); }
        item->setParent(parent);
        item->setParentItem(parent);
        component.completeCreate();
    }
};
int main(int argc, char** argv) {
    if (argc != 4) { return 1; }
    QGuiApplication app(argc, argv);
    QQmlEngine engine;
    const QString root = argv[1];
    engine.addImportPath(root + "/interface/resources/qml");
    qmlRegisterModule("TabletScriptingInterface", 1, 0);
    qmlRegisterModule("Hifi", 1, 0);
    qmlRegisterModule("PerformanceEnums", 1, 0);
    QQmlFileSelector selector(&engine);
    selector.setExtraSelectors({"android_phoneInterface", "android_interface", "android"});
    TabletBoundary tablet;
    engine.rootContext()->setContextProperty("Tablet", &tablet);
    engine.rootContext()->setContextProperty("TabletEnums", QVariant::fromValue(
        engine.evaluate("({ButtonClick:0,ButtonHover:1})")));
    engine.rootContext()->setContextProperty("HMD", QVariant::fromValue(engine.evaluate("({active:false})")));
    engine.rootContext()->setContextProperty("Preferences", QVariant::fromValue(engine.evaluate("({categories:[]})")));
    Surface surface; surface.engine = &engine;
    engine.rootContext()->setContextProperty("QmlSurface", &surface);
    QQmlComponent loader(&engine, QUrl::fromLocalFile(
        root + "/interface/resources/qml/hifi/tablet/TabletPageLoader.qml"));
    auto item = qobject_cast<QQuickItem*>(loader.create());
    if (!item) { qFatal("%s", qPrintable(loader.errorString())); }
    QQuickWindow window;
    window.resize(856, 350);
    item->setParentItem(window.contentItem());
    item->setSize(QSizeF(856, 350));
    window.show();
    if (QString(argv[3]) == "navigation") {
        QQmlComponent footer(&engine, QUrl::fromLocalFile(argv[2]));
        auto navigation = qobject_cast<QQuickItem*>(footer.create());
        if (!navigation) { fprintf(stderr, "%s\n", qPrintable(footer.errorString())); return 8; }
        navigation->setParentItem(item);
        for (const auto geometry : {QSizeF(320, 1), QSizeF(768, 1), QSizeF(1024, 1), QSizeF(1080, 2.5)}) {
            navigation->setWidth(geometry.width());
            navigation->setProperty("contentScale", geometry.height());
            QTest::qWait(50);
            bool fits = true;
            std::function<void(QQuickItem*)> inspect = [&](QQuickItem* child) {
                if (child->objectName().startsWith("nav.")) {
                    fits &= child->property("implicitTextWidth").toDouble() + 16 <= child->width();
                }
                for (auto descendant : child->childItems()) { inspect(descendant); }
            };
            inspect(navigation);
            if (!fits) { return 9; }
        }
        return 0;
    }
    if (QString(argv[3]) == "preferences") {
        QQmlComponent dialog(&engine, QUrl::fromLocalFile(argv[2]));
        auto preferences = qobject_cast<QQuickItem*>(dialog.beginCreate(engine.rootContext()));
        if (!preferences) { fprintf(stderr, "%s\n", qPrintable(dialog.errorString())); return 8; }
        preferences->setParentItem(item);
        dialog.completeCreate();
        QQmlComponent footer(&engine, QUrl::fromLocalFile(
            root + "/interface/resources/qml/hifi/tablet/TabletNavigation.qml"));
        auto navigation = qobject_cast<QQuickItem*>(footer.create());
        if (!navigation) { fprintf(stderr, "%s\n", qPrintable(footer.errorString())); return 8; }
        navigation->setParentItem(item);
        navigation->setWidth(856);
        QTest::qWait(100);
        int backControls = 0, cancelControls = 0;
        std::function<void(QQuickItem*)> inspect = [&](QQuickItem* child) {
            if (child->isVisible() && child->objectName() == "nav.back") { ++backControls; }
            if (child->isVisible() && child->objectName() == "GeneralPreferencesCancel") { ++cancelControls; }
            for (auto descendant : child->childItems()) { inspect(descendant); }
        };
        inspect(item);
        return backControls == 1 && cancelControls == 1 ? 0 : 7;
    }
    QSignalSpy messages(item, SIGNAL(sendToScript(QVariant)));
    if (!messages.isValid()) { return 2; }
    if (!QMetaObject::invokeMethod(item, "load",
            Q_ARG(QVariant, QUrl::fromLocalFile(argv[2]).toString()),
            Q_ARG(QVariant, QVariant()))) { return 2; }
    QTest::qWait(100);
    auto page = item->property("item").value<QObject*>();
    if (!page) { return 3; }
    QQuickItem* audio = nullptr;
    std::function<void(QQuickItem*)> visit = [&](QQuickItem* control) {
        if (control->objectName() == "settings.audio") { audio = control; }
        for (auto child : control->childItems()) { visit(child); }
    };
    visit(qobject_cast<QQuickItem*>(page));
    if (!audio || !audio->isVisible() || !audio->isEnabled()) { return 3; }
    const auto point = audio->mapToScene(QPointF(audio->width()/2, audio->height()/2)).toPoint();
    if (!QRect(QPoint(), window.size()).contains(point)) { return 3; }
    QTest::mouseClick(&window, Qt::LeftButton, Qt::NoModifier, point);
    QTest::qWait(120);
    if (messages.count() != 1) { return 4; }
    const auto message = messages.at(0).at(0).toMap();
    if (message.value("type") != "switchApp" || message.value("appUrl") != "hifi/audio/Audio.qml") { return 5; }
    QMetaObject::invokeMethod(audio, "activate");
    if (messages.count() != 2) { return 6; }
    return 0;
}
#include "phone-settings-click-test.moc"
