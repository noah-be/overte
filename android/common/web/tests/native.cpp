// Copyright 2026 Overte contributors.
// SPDX-License-Identifier: Apache-2.0
#include "NativeWebViewItem.h"
#include <QFile>
#include <QGuiApplication>
#include <QJsonDocument>
#include <QJsonArray>
#include <QTemporaryDir>
#include <QQmlEngine>
#include <QQmlComponent>
#include <memory>
#include <cassert>
class Probe : public NativeWebViewItem {
public: using NativeWebViewItem::inputMethodQuery;
};
int main(int argc, char** argv) {
    QGuiApplication app(argc, argv);
    Probe item; item.acceptForeground(true); item.setSourceIdentity("fixture-owned-surface");
    item.setUrl("https://one.test/document"); item.componentComplete();
    auto grant = item.generation(); assert(grant);
    item.acceptPage(grant, 1, QUrl("https://one.test/document"));
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
    assert(item.inputMethodQuery(Qt::ImCurrentSelection).toString() == "hello");
    assert(send(grant, 1, QUrl("https://one.test"), true,
        R"({"active":true,"sensitive":true,"text":"must-never-be-retained","cursor":3,"anchor":0})"));
    QCoreApplication::processEvents(); assert(item.inputMethodQuery(Qt::ImSurroundingText).toString().isEmpty());
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
    assert(!send(grant, 1, QUrl("https://one.test"), true, "{}"));
    item.setVisible(false); assert(!item.generation()); assert(!item.emitScriptEvent("hidden event"));
    item.setVisible(true); assert(item.generation() != grant);
    assert(!send(grant, 2, QUrl("https://one.test"), true, "{}"));
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
        assert(views[0]->userAgent() == "host-test-agent");
        assert(views[0]->hasFocus());
        adapter->setProperty("surface", "world-entity");
        assert(views[0]->presentation() == NativeWebViewItem::Texture);
        assert(adapter->metaObject()->indexOfMethod("emitScriptEvent(QVariant)") >= 0);
        assert(adapter->metaObject()->indexOfMethod("goForward()") >= 0);
    }
    return 0;
}
