// Copyright 2026 Overte contributors.
// SPDX-License-Identifier: Apache-2.0
#include "NativeWebViewItem.h"
#include <QGuiApplication>
#include <QQuickWindow>
#include <QQmlEngine>
#include <QQmlContext>
#include <QQmlComponent>
#include <QQmlFileSelector>
#include <QPointer>
#include <QJsonDocument>
#include <QMouseEvent>
#include <QHoverEvent>
#include <QEventLoop>
#include <QTimer>
#include <QQuickItemGrabResult>
#include <cassert>
#include <memory>
#include <cstdio>

// Existing legacy JNI creation is tested separately. This boundary lets the
// real legacy Canvas/QML participate without loading an Android VM on the host.
class LegacyBoundary : public QQuickItem {
    Q_OBJECT
    Q_PROPERTY(QString url MEMBER url)
    Q_PROPERTY(QString scriptUrl MEMBER scriptUrl)
    Q_PROPERTY(QString userAgent MEMBER userAgent)
    Q_PROPERTY(bool useBackground MEMBER useBackground)
    Q_PROPERTY(QString frameSource READ frameSource)
    Q_PROPERTY(bool rendering READ rendering NOTIFY renderingChanged)
public:
    QString url, scriptUrl, userAgent;
    bool useBackground = true;
    QString frameSource() const { return {}; }
    bool rendering() const { return false; }
signals:
    void renderingChanged();
};
class BridgeBoundary : public QObject {
    Q_OBJECT
public:
    QStringList messages;
    Q_INVOKABLE void emitWebEvent(const QVariant& value) { messages << value.toString(); }
};
class KeyboardBoundary : public QObject {
    Q_OBJECT
    Q_PROPERTY(bool use3DKeyboard MEMBER use3DKeyboard)
    Q_PROPERTY(bool raised MEMBER raised)
    Q_PROPERTY(bool password MEMBER password)
public:
    bool use3DKeyboard = true, raised = false, password = false;
};
int main(int argc, char** argv) {
    qInstallMessageHandler([](QtMsgType, const QMessageLogContext&, const QString& message) {
        std::fprintf(stderr, "%s\n", qPrintable(message));
    });
    QGuiApplication app(argc, argv);
    qmlRegisterType<LegacyBoundary>("Overte.Pico", 1, 0, "PicoWebView");
    qmlRegisterModule("TabletScriptingInterface", 1, 0);
    qmlRegisterModule("Hifi", 1, 0);
    QQmlEngine engine;
    QQmlFileSelector selector(&engine);
    selector.setExtraSelectors({ "android_picoInterface", "android" });
    engine.addImportPath(argv[1]);
    BridgeBoundary bridge;
    KeyboardBoundary keyboard;
    engine.rootContext()->setContextProperty("eventBridge", &bridge);
    engine.rootContext()->setContextProperty("KeyboardScriptingInterface", &keyboard);
    QQuickWindow window;
    window.setWidth(640); window.setHeight(480); window.show();
    auto create = [&](const QString& file) {
        QQmlComponent component(&engine, QUrl::fromLocalFile(QString(argv[1]) + file));
        if (!component.isReady()) qFatal("%s", qPrintable(component.errorString()));
        auto* object = component.create();
        if (!object) qFatal("%s", qPrintable(component.errorString()));
        return object;
    };
    std::unique_ptr<QObject> adapter(create("/controls/EmbeddedWebBackend.qml"));
    auto* view = adapter->findChild<NativeWebViewItem*>(); assert(view);
    auto* adapterItem = qobject_cast<QQuickItem*>(adapter.get());
    adapterItem->setParentItem(window.contentItem()); adapterItem->setWidth(640); adapterItem->setHeight(480);
    adapter->setProperty("surface", "tablet");
    assert(view->surface() == NativeWebViewItem::Tablet);
    assert(view->presentation() == NativeWebViewItem::Texture);
    adapter->setProperty("sourceIdentity", "pico-owned-tablet");
    view->acceptForeground(true);
    adapter->setProperty("url", "https://pico.test/form");
    auto grant = view->generation(); assert(grant);
    view->acceptPage(grant, 1, QUrl("https://pico.test/form"));
    assert(view->allowsFileChooser(grant, 1, QUrl("https://pico.test/form")));
    assert(!view->allowsFileChooser(grant, 2, QUrl("https://pico.test/form")));
    assert(!view->allowsFileChooser(grant, 1, QUrl("https://foreign.test/form")));
    view->forceActiveFocus();
    auto editor = [&](const QByteArray& value) {
        assert(view->acceptMessage(grant, 1, QUrl("https://pico.test/form"), QUrl("https://pico.test"), true, "editor", value));
        QCoreApplication::processEvents();
    };
    editor(R"({"active":true,"kind":"number","sensitive":true,"cursor":0,"anchor":0})");
    assert(bridge.messages.last() == "_RAISE_KEYBOARD_NUMERIC_PASSWORD");
    assert(adapter->property("editorFocused").toBool());
    assert(adapter->property("editorNumeric").toBool());
    assert(adapter->property("editorPassword").toBool());
    assert(view->width() == 640 && view->height() == 480);
    assert(view->acceptHoverEvents());
    for (auto type : { QEvent::HoverEnter, QEvent::HoverMove, QEvent::HoverLeave }) {
        QHoverEvent event(type, QPointF(42, 60), QPointF(40, 58));
        QCoreApplication::sendEvent(view, &event); assert(event.isAccepted());
    }
    auto pointer = [&](QEvent::Type type, Qt::MouseButton button, Qt::MouseButtons buttons, bool accepted) {
        QMouseEvent event(type, QPointF(42, 60), button, buttons, Qt::NoModifier);
        QCoreApplication::sendEvent(view, &event); assert(event.isAccepted() == accepted);
    };
    pointer(QEvent::MouseMove, Qt::NoButton, Qt::LeftButton, false);
    pointer(QEvent::MouseButtonRelease, Qt::LeftButton, Qt::NoButton, false);
    pointer(QEvent::MouseButtonPress, Qt::LeftButton, Qt::LeftButton, true);
    pointer(QEvent::MouseMove, Qt::NoButton, Qt::LeftButton, true);
    pointer(QEvent::MouseButtonPress, Qt::LeftButton, Qt::LeftButton, true);
    pointer(QEvent::MouseButtonRelease, Qt::LeftButton, Qt::NoButton, true);
    pointer(QEvent::MouseMove, Qt::NoButton, Qt::LeftButton, false);
    QImage frame(4, 4, QImage::Format_ARGB32); frame.fill(QColor(220, 40, 60));
    view->acceptFrame(grant, 1, frame.constBits(), frame.sizeInBytes(), frame.width(), frame.height());
    QEventLoop paint; QTimer::singleShot(80, &paint, &QEventLoop::quit); paint.exec();
    auto capture = view->grabToImage(); assert(capture);
    if (capture->image().isNull()) {
        QEventLoop ready;
        QObject::connect(capture.data(), &QQuickItemGrabResult::ready, &ready, &QEventLoop::quit);
        QTimer::singleShot(2000, &ready, &QEventLoop::quit); ready.exec();
    }
    auto rendered = capture->image(); assert(!rendered.isNull());
    auto color = rendered.pixelColor(100, 100);
    assert(color.red() == 220 && color.green() == 40 && color.blue() == 60);
    qInfo("PASS actual Qt scene renders Pico-selected native WebView texture pixels");
    assert(!view->acceptMessage(grant, 1, QUrl("https://pico.test/form"), QUrl("https://foreign.test"), true, "editor", "{}"));
    view->acceptForeground(false); QCoreApplication::processEvents();
    assert(bridge.messages.last() == "_LOWER_KEYBOARD");
    assert(!adapter->property("editorFocused").toBool());
    assert(!view->generation());
    assert(!view->allowsFileChooser(grant, 1, QUrl("https://pico.test/form")));
    view->acceptForeground(true); QCoreApplication::processEvents();
    auto resumedGrant = view->generation(); assert(resumedGrant && resumedGrant != grant);
    assert(view->allowsFileChooser(resumedGrant, 1, QUrl("https://pico.test/form")));
    assert(!view->allowsFileChooser(grant, 1, QUrl("https://pico.test/form")));
    adapter->setProperty("surface", "world-entity");
    assert(view->surface() == NativeWebViewItem::WorldEntity && view->presentation() == NativeWebViewItem::Texture);
    assert(!view->allowsFileChooser(view->generation(), 1, QUrl("https://pico.test/form")));
    adapter.reset();

    std::unique_ptr<QObject> world(create("/Web3DSurface.qml"));
    auto* worldItem = qobject_cast<QQuickItem*>(world.get()); assert(worldItem);
    worldItem->setParentItem(window.contentItem()); worldItem->setWidth(640); worldItem->setHeight(480);
    world->setProperty("scriptUrl", "https://pico.test/client.js");
    world->setProperty("userAgent", "pico-fixture");
    world->setProperty("url", "https://pico.test/page"); QCoreApplication::processEvents();
    QPointer<NativeWebViewItem> common = world->findChild<NativeWebViewItem*>(); assert(common);
    assert(common->presentation() == NativeWebViewItem::Texture);
    assert(common->scriptUrl() == "https://pico.test/client.js");
    assert(common->userAgent() == "pico-fixture");
    world->setProperty("keyboardRaised", true); world->setProperty("passwordField", true);
    assert(keyboard.raised && keyboard.password);
    world->setProperty("keyboardRaised", false); assert(!keyboard.raised && !keyboard.password);
    keyboard.use3DKeyboard = false;
    world->setProperty("punctuationMode", true); world->setProperty("keyboardRaised", true);
    auto* panel = world->findChild<QQuickItem*>("keyboard"); assert(panel);
    assert(panel->height() == 250 && panel->isVisible());
    assert(panel->property("numeric").toBool() && panel->property("password").toBool());
    assert(common->height() == 230);
    world->setProperty("keyboardRaised", false); assert(common->height() == 480);
    world->setProperty("url", "data:text/html,<input value='inline'>");
    QCoreApplication::sendPostedEvents(nullptr, QEvent::DeferredDelete); QCoreApplication::processEvents();
    assert(!common);
    auto* legacy = world->findChild<LegacyBoundary*>(); assert(legacy);
    assert(legacy->url.startsWith("data:text/html,"));
    assert(legacy->scriptUrl == "https://pico.test/client.js");
    world->setProperty("url", "https://pico.test/next");
    QCoreApplication::sendPostedEvents(nullptr, QEvent::DeferredDelete); QCoreApplication::processEvents();
    assert(world->findChild<NativeWebViewItem*>());
    assert(!world->findChild<LegacyBoundary*>());
    world.reset();
    std::unique_ptr<QObject> physicalWorld(create("/+android_picoInterface/Web3DSurface.qml"));
    auto* physicalItem = qobject_cast<QQuickItem*>(physicalWorld.get()); assert(physicalItem);
    physicalItem->setParentItem(window.contentItem()); physicalItem->setWidth(640); physicalItem->setHeight(480);
    physicalWorld->setProperty("url", "https://pico.test/physical"); QCoreApplication::processEvents();
    assert(physicalWorld->findChild<NativeWebViewItem*>());
    physicalWorld->setProperty("url", "data:text/html,<p>physical inline</p>"); QCoreApplication::processEvents();
    assert(physicalWorld->findChild<LegacyBoundary*>());
    physicalWorld.reset();
    std::unique_ptr<QObject> tablet(create("/controls/TabletWebScreen.qml"));
    auto* tabletItem = qobject_cast<QQuickItem*>(tablet.get()); assert(tabletItem);
    tabletItem->setParentItem(window.contentItem()); tabletItem->setWidth(640); tabletItem->setHeight(480);
    tablet->setProperty("url", "https://pico.test/tablet"); QCoreApplication::processEvents();
    auto* tabletView = tablet->findChild<NativeWebViewItem*>(); assert(tabletView);
    assert(tabletView->surface() == NativeWebViewItem::Tablet);
    assert(tabletView->presentation() == NativeWebViewItem::Texture);
    tabletView->acceptForeground(true); auto tabletGrant = tabletView->generation(); assert(tabletGrant);
    tabletView->acceptPage(tabletGrant, 1, QUrl("https://pico.test/tablet")); tabletView->forceActiveFocus();
    assert(tabletView->acceptMessage(tabletGrant, 1, QUrl("https://pico.test/tablet"), QUrl("https://pico.test"), true, "editor",
        R"({"active":true,"kind":"text","text":"tablet input","cursor":12,"anchor":12})"));
    QCoreApplication::processEvents(); assert(tabletView->editorFocused());
    tablet->setProperty("keyboardRaised", true);
    assert(tabletView->editorFocused()); // Raising the QML keyboard must retain the real editor.
    assert(tabletView->height() == 182); // Existing keyboard (250) + native navigation (48).
    tablet->setProperty("keyboardRaised", false);
    assert(!tabletView->editorFocused() && tabletView->height() == 432);
    qInfo("PASS Pico selected native Texture world/tablet, editor/keyboard and lifecycle routing");
}
#include "pico-embedded-web-native-test.moc"
