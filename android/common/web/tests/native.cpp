// Copyright 2026 Overte contributors.
// SPDX-License-Identifier: Apache-2.0
#include "NativeWebViewItem.h"
#include <QFile>
#include <QGuiApplication>
#include <QQuickWindow>
#include <QQuickRenderControl>
#include <QJsonDocument>
#include <QJsonArray>
#include <QTemporaryDir>
#include <QQmlEngine>
#include <QQmlComponent>
#include <QQmlFileSelector>
#include <QDir>
#include <memory>
#include <cassert>
#include <cstdio>
class Probe : public NativeWebViewItem {
public: using NativeWebViewItem::inputMethodQuery;
};
int main(int argc, char** argv) {
    qputenv("QT_QUICK_BACKEND", "software");
    QGuiApplication app(argc, argv);
    // Exercise actual native frame ingestion, Qt texture painting and premultiplied BGRA.
    QQuickRenderControl control; QQuickWindow raster(&control); raster.resize(8,8); raster.setColor(Qt::transparent);
    Probe pixels; pixels.setParentItem(raster.contentItem()); pixels.setSize(QSizeF(8,8));
    pixels.acceptForeground(true); pixels.setSourceIdentity("pixel-fixture");
    pixels.setUrl("https://one.test/frame"); pixels.componentComplete();
    auto pixelGrant = pixels.generation(); pixels.acceptPage(pixelGrant,1,QUrl("https://one.test/frame"));
    const unsigned char bgra[] = {0,0,255,255, 0,128,0,128, 255,0,0,255, 255,255,255,255};
    pixels.acceptFrame(pixelGrant,1,bgra,sizeof(bgra),2,2);
    control.initialize(nullptr); control.polishItems(); control.sync(); control.render();
    QImage painted = control.grab(); assert(!painted.isNull());
    assert(painted.pixelColor(1,1).red() > 240 && painted.pixelColor(1,1).blue() < 10);
    assert(painted.pixelColor(6,1).green() > 240 && painted.pixelColor(6,1).alpha() >= 120 && painted.pixelColor(6,1).alpha() <= 136);
    assert(painted.pixelColor(1,6).blue() > 240 && painted.pixelColor(1,6).red() < 10);
    const unsigned char rejected[] = {0,0,0,255};
    pixels.acceptFrame(pixelGrant+1,1,rejected,sizeof(rejected),1,1);
    pixels.acceptFrame(pixelGrant,2,rejected,sizeof(rejected),1,1);
    control.polishItems(); control.sync(); control.render();
    assert(control.grab().pixelColor(1,1).red() > 240);
    pixels.setParentItem(nullptr); control.invalidate();
    std::puts("PASS: actual native frame ingestion and Qt scene graph pixels preserve BGRA/row orientation/premultiplied alpha; stale source/page frames rejected");
    QQuickItem transformed; transformed.setPosition(QPointF(10, 20)); transformed.setWidth(300); transformed.setHeight(200);
    NativeWebViewItem geometry(&transformed); geometry.setPosition(QPointF(5, 48)); geometry.setWidth(100); geometry.setHeight(70);
    auto plain = geometry.sceneBounds(); assert(plain.size() == QSizeF(100, 70));
    transformed.setScale(2); auto scaled = geometry.sceneBounds(); assert(scaled.size() == QSizeF(200, 140));
    transformed.setRotation(90); auto rotated = geometry.sceneBounds(); assert(qAbs(rotated.width() - 140) < .001 && qAbs(rotated.height() - 200) < .001);
    transformed.setRotation(0); transformed.setScale(1); transformed.setClip(true);
    geometry.setPosition(QPointF(5, 48)); transformed.setWidth(80); transformed.setHeight(90);
    assert(geometry.sceneBounds().size() == QSizeF(100, 70));
    assert(geometry.sceneClipBounds() == QRectF(15, 68, 75, 42));
    transformed.setScale(2);
    assert(geometry.sceneClipBounds().size() == QSizeF(150, 84));
    transformed.setClip(false); assert(geometry.sceneClipBounds() == geometry.sceneBounds());
    transformed.setClip(true); geometry.setY(1000); assert(geometry.sceneClipBounds().isEmpty());
    Probe item; item.acceptForeground(true); item.setSourceIdentity("fixture-owned-surface");
    item.setUrl("https://one.test/document"); item.componentComplete();
    auto grant = item.generation(); assert(grant);
    item.acceptPage(grant, 1, QUrl("https://one.test/document"));
    assert(!item.allowsFileChooser(grant, 1, QUrl("https://one.test/document")));
    Probe tablet; tablet.acceptForeground(true); tablet.setSurface(NativeWebViewItem::Tablet);
    tablet.setPresentation(NativeWebViewItem::Texture); tablet.setSourceIdentity("fixture-tablet");
    tablet.setUrl("https://one.test/document"); tablet.componentComplete();
    auto tabletGrant = tablet.generation(); tablet.acceptPage(tabletGrant, 1, QUrl("https://one.test/document"));
    assert(tablet.allowsFileChooser(tabletGrant, 1, QUrl("https://one.test/document")));
    assert(!tablet.allowsFileChooser(tabletGrant, 2, QUrl("https://one.test/document")));
    assert(!tablet.allowsFileChooser(tabletGrant, 1, QUrl("https://one.test/other")));
    tablet.setVisible(false); assert(!tablet.allowsFileChooser(tabletGrant, 1, QUrl("https://one.test/document")));
    auto send = [&](quint64 generation, quint64 page, const QUrl& origin, bool main, const QByteArray& payload) {
        return item.acceptMessage(generation, page, QUrl("https://one.test/document"), origin, main, "editor", payload);
    };
    assert(!send(grant, 1, QUrl("https://foreign.test"), true, "{}"));
    assert(!send(grant, 1, QUrl("https://one.test"), false, "{}"));
    assert(!send(grant, 2, QUrl("https://one.test"), true, "{}"));
    assert(!send(grant, 1, QUrl("https://one.test"), true, QByteArray(65537, 'x')));
    assert(send(grant, 1, QUrl("https://one.test"), true,
        R"({"active":true,"text":"hello world","cursor":5,"anchor":0,"kind":"text"})"));
    QCoreApplication::processEvents();
    assert(item.inputMethodQuery(Qt::ImSurroundingText).toString() == "hello world");
    assert(item.editorFocused() && !item.editorNumeric() && !item.editorPassword());
    assert(item.inputMethodQuery(Qt::ImCurrentSelection).toString() == "hello");
    assert(send(grant, 1, QUrl("https://one.test"), true,
        R"({"active":true,"sensitive":true,"text":"must-never-be-retained","cursor":3,"anchor":0})"));
    QCoreApplication::processEvents(); assert(item.inputMethodQuery(Qt::ImSurroundingText).toString().isEmpty());
    assert(item.editorFocused() && item.editorPassword());
    QJsonObject initialization; auto* transport = item.findChild<NativeWebTransport*>(); assert(transport);
    QObject::connect(transport, &NativeWebTransport::outbound, [&](const QJsonObject& message) { if (message.value("type").toInt() == 10) initialization = message; });
    auto channel = [&](const QJsonObject& object) { return item.acceptMessage(grant, 1, QUrl("https://one.test/document"), QUrl("https://one.test"), true, "channel", QJsonDocument(object).toJson(QJsonDocument::Compact)); };
    assert(channel({{"type", 3}, {"id", 0}})); QCoreApplication::processEvents();
    assert(initialization.value("data").toObject().contains("eventBridge"));
    auto* bridge = item.findChild<NativeSurfaceBridge*>(); assert(bridge);
    int received = 0; QObject::connect(&item, &NativeWebViewItem::webEventReceived, [&](const QVariant& message) { assert(message.toString() == "safe event"); ++received; });
    assert(channel({{"type", 6}, {"object", "eventBridge"}, {"method", bridge->metaObject()->indexOfMethod("emitWebEvent(QVariant)")}, {"args", QJsonArray { "safe event" }}, {"id", 1}}));
    QCoreApplication::processEvents(); assert(received == 1);
    assert(!channel({{"type", 6}, {"object", "eventBridge"}, {"method", bridge->metaObject()->indexOfMethod("deleteLater()")}, {"args", QJsonArray {}}, {"id", 2}}));
    assert(!channel({{"type", 6}, {"object", "eventBridge"}, {"method", "forwardScriptEvent"}, {"args", QJsonArray { "injected signal" }}}));
    assert(!item.runJavaScript("1 + 2")); // Missing native provider cannot report successful execution.
    assert(item.emitScriptEvent("authorized event"));
    assert(!item.emitScriptEvent(QString(65536, QChar(0))));
    assert(!channel({{"type", 9}, {"object", "eventBridgeWrapper"}, {"property", 0}, {"value", "foreign bridge"}}));
    assert(item.allowsNavigation(grant, QUrl("https://foreign.test/page"), true, "POST"));
    assert(!item.allowsNavigation(grant, QUrl("file:///private/anything"), true, "GET"));
    item.acceptPage(grant, 2, QUrl("https://foreign.test/page"));
    item.acceptState(grant, 2, QUrl("https://foreign.test/page"), false, true, false, true, 0);
    QCoreApplication::processEvents(); assert(item.errorText().isEmpty() && !item.warningText().isEmpty());
    const QUrl foreignDocument("https://foreign.test/page"), foreignOrigin("https://foreign.test");
    auto foreign = [&](quint64 generation, quint64 page, const QUrl& document, const QUrl& origin, bool main, const QString& type, const QByteArray& payload) {
        return item.acceptMessage(generation, page, document, origin, main, type, payload);
    };
    assert(item.allowsEditorDocument(grant, 2, foreignDocument));
    assert(!item.allowsBridgeDocument(grant, 2, foreignDocument));
    assert(!item.emitScriptEvent("foreign event") && !item.runJavaScript("foreign script"));
    const QByteArray editorState = R"({"active":true,"text":"foreign document input","cursor":7,"anchor":0,"kind":"email"})";
    assert(foreign(grant, 2, foreignDocument, foreignOrigin, true, "editor", editorState));
    QCoreApplication::processEvents();
    assert(item.editorFocused() && item.inputMethodQuery(Qt::ImSurroundingText).toString() == "foreign document input");
    assert(item.inputMethodQuery(Qt::ImCurrentSelection).toString() == "foreign");
    assert(!foreign(grant, 2, foreignDocument, foreignOrigin, true, "channel", R"({"type":3,"id":0})"));
    assert(!foreign(grant, 2, foreignDocument, QUrl("https://one.test"), true, "editor", editorState));
    assert(!foreign(grant, 2, foreignDocument, foreignOrigin, false, "editor", editorState));
    assert(!foreign(grant, 1, foreignDocument, foreignOrigin, true, "editor", editorState));
    assert(!foreign(grant, 2, QUrl("https://foreign.test/another"), foreignOrigin, true, "editor", editorState));
    assert(!foreign(grant, 2, foreignDocument, foreignOrigin, true, "editor", QByteArray(65537, 'x')));
    assert(foreign(grant, 2, foreignDocument, foreignOrigin, true, "editor", editorState));
    item.acceptPage(grant, 3, QUrl("https://third.test/page"));
    QCoreApplication::processEvents(); assert(!item.editorFocused()); // A queued old document cannot restore focus.
    const QUrl thirdDocument("https://third.test/page"), thirdOrigin("https://third.test");
    assert(foreign(grant, 3, thirdDocument, thirdOrigin, true, "editor", editorState));
    QCoreApplication::processEvents(); assert(item.editorFocused());
    item.acceptForeground(false);
    assert(!foreign(grant, 3, thirdDocument, thirdOrigin, true, "editor", editorState));
    QCoreApplication::processEvents(); assert(!item.editorFocused());
    item.acceptForeground(true); grant = item.generation();
    assert(foreign(grant, 3, thirdDocument, thirdOrigin, true, "editor", editorState));
    QCoreApplication::processEvents(); assert(item.editorFocused());
    assert(!send(grant, 1, QUrl("https://one.test"), true, "{}"));
    item.setVisible(false); assert(!item.editorFocused() && !item.editorPassword()); assert(!item.generation()); assert(!item.emitScriptEvent("hidden event"));
    assert(!foreign(grant, 3, thirdDocument, thirdOrigin, true, "editor", editorState));
    item.setVisible(true); assert(item.generation() != grant);
    assert(!send(grant, 2, QUrl("https://one.test"), true, "{}"));
    item.setSourceIdentity("replacement-source");
    assert(!foreign(grant, 3, thirdDocument, thirdOrigin, true, "editor", editorState));
    QTemporaryDir root, outside; assert(root.isValid() && outside.isValid());
    QFile doc(root.filePath("page.html")); assert(doc.open(QFile::WriteOnly)); doc.write("test"); doc.close();
    QFile secret(outside.filePath("private.txt")); assert(secret.open(QFile::WriteOnly)); secret.write("private"); secret.close();
    assert(QFile::link(secret.fileName(), root.filePath("escape.txt")));
    using overte::android::web::NativeResourceMapping;
    NativeResourceMapping mapping(root.path(), 77);
    auto source = QUrl::fromLocalFile(doc.fileName()); auto browser = mapping.toBrowser(source);
    assert(browser.host() == "overte-embedded.invalid"); assert(mapping.toSource(browser) == source);
    QDir(root.path()).mkdir("nested");
    QUrl alias = QUrl::fromLocalFile(root.filePath("nested/../page.html")); assert(!mapping.accepts(alias));
    assert(QFile::link(doc.fileName(), root.filePath("alias.html")));
    QUrl internalAlias = QUrl::fromLocalFile(root.filePath("alias.html"));
    assert(mapping.accepts(internalAlias)); assert(mapping.toSource(mapping.toBrowser(internalAlias)) == source);
    assert(mapping.toSource(QUrl("https://overte-embedded.invalid/78/page.html")).isEmpty());
    assert(mapping.toSource(QUrl("https://overte-embedded.invalid/77/%2e%2e/private.txt")).isEmpty());
    assert(mapping.toSource(QUrl("https://overte-embedded.invalid/77/escape.txt")).isEmpty());
    assert(!mapping.accepts(QUrl::fromLocalFile(secret.fileName())));
    if (argc > 1) { QFile script(":/qtwebchannel/qwebchannel.js"), output(argv[1]);
        assert(script.open(QFile::ReadOnly)); assert(output.open(QFile::WriteOnly)); output.write(script.readAll()); }
    if (argc > 2) {
        QQmlEngine engine; QQmlComponent component(&engine, QUrl::fromLocalFile(argv[2]));
        assert(component.isReady()); std::unique_ptr<QObject> adapter(component.create()); assert(adapter);
        adapter->setProperty("surface", "tablet"); adapter->setProperty("userAgent", "host-test-agent");
        auto views = adapter->findChildren<NativeWebViewItem*>(); assert(views.size() == 1);
        assert(views[0]->surface() == NativeWebViewItem::Tablet);
        assert(views[0]->presentation() == NativeWebViewItem::NativeOverlay);
        adapter->setProperty("presentation", "texture");
        assert(views[0]->presentation() == NativeWebViewItem::Texture);
        adapter->setProperty("presentation", "auto");
        assert(views[0]->presentation() == NativeWebViewItem::NativeOverlay);
        assert(views[0]->userAgent() == "host-test-agent");
        assert(views[0]->hasFocus());
        adapter->setProperty("surface", "world-entity");
        assert(views[0]->presentation() == NativeWebViewItem::Texture);
        assert(adapter->metaObject()->indexOfMethod("emitScriptEvent(QVariant)") >= 0);
        assert(adapter->metaObject()->indexOfMethod("goForward()") >= 0);
        engine.addImportPath(QFileInfo(QString::fromLocal8Bit(argv[2])).absoluteDir().absoluteFilePath("../.."));
        QQmlFileSelector selector(&engine); selector.setExtraSelectors({ "android" });
        QQmlComponent module(&engine);
        module.setData("import QtQuick 2.7\nimport controls 1.0 as Controls\nControls.AndroidEmbeddedWebBackend { surface: \"tablet\"; presentation: \"texture\" }", QUrl());
        if (!module.isReady()) qWarning() << module.errors();
        assert(module.isReady()); std::unique_ptr<QObject> exported(module.create()); assert(exported);
        auto* exportedView = exported->findChild<NativeWebViewItem*>(); assert(exportedView);
        assert(exportedView->surface() == NativeWebViewItem::Tablet && exportedView->presentation() == NativeWebViewItem::Texture);
    }
    return 0;
}
