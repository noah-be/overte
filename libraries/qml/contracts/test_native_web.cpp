// SPDX-License-Identifier: Apache-2.0
#include "interface/src/NativeWebPolicy.h"
#include <QGuiApplication>
#include <QQmlComponent>
#include <QQmlContext>
#include <QQmlEngine>
#include <QQuickItem>
#include <cassert>
#include <thread>
using namespace overte::web;

struct NativeBoundary : Adapter {
    Session* session { nullptr };
    Request latest;
    int presents { 0 }, dismissals { 0 };
    bool accepted { true }, revokeDuringPresent { false };
    bool present(const Request& request) noexcept override {
        ++presents;
        latest = request;
        assert(session->allows(request.ticket, request.url.toString()));
        assert(session->open(QStringLiteral("https://example.org/reentrant")) == 0);
        if (revokeDuringPresent) { session->visible(false); }
        return accepted;
    }
    void dismiss(std::uint64_t ticket) noexcept override {
        ++dismissals;
        assert(!session->allows(ticket, latest.url.toString()));
        assert(session->open(QStringLiteral("https://example.org/reentrant")) == 0);
    }
};

int main(int argc, char** argv) {
    QGuiApplication app(argc, argv);
    Session session;
    NativeBoundary adapter; adapter.session = &session;
    assert(!session.install(nullptr));
    assert(session.open(QStringLiteral("https://example.org")) == 0);
    assert(session.install(&adapter));
    assert(!session.install(&adapter));
    assert(session.open(QStringLiteral("https://example.org")) == 0);
    session.visible(true);
    for (const QString& input : {QString(), QStringLiteral("http://example.org"),
         QStringLiteral("file:///tmp/input"), QStringLiteral("javascript:alert(1)"),
         QStringLiteral("data:text/html,hello"), QStringLiteral("//example.org"),
         QStringLiteral("https://user:password@example.org"), QStringLiteral("https://@example.org"),
         QStringLiteral("https://example.org:444"), QStringLiteral("https://example.org/white space"),
         QStringLiteral("https://example.org/\\evil"), QStringLiteral("https://example.org/%ZZ"),
         QStringLiteral("https://example.org/\nheader"), QString(8193,QChar('x'))}) {
        assert(session.open(input) == 0);
    }
    assert(adapter.presents == 0);
    auto first = session.open(QStringLiteral("HTTPS://Example.Org:443/a?q=private#fragment"));
    assert(first != 0 && adapter.latest.origin == QStringLiteral("https://example.org"));
    assert(session.allows(first,QStringLiteral("https://example.org/next")));
    assert(!session.allows(first,QStringLiteral("https://other.example.org/next")));
    assert(!session.allows(first,QStringLiteral("https://example.org.evil.test/next")));
    assert(!session.allows(first,QStringLiteral("http://example.org/next")));
    assert(!session.allows(first+1,QStringLiteral("https://example.org/next")));
    session.visible(true); // Duplicate visibility must not cancel current view.
    assert(session.allows(first,QStringLiteral("https://example.org")));
    auto second = session.open(QStringLiteral("https://example.org/new"));
    assert(second != first && !session.allows(first,QStringLiteral("https://example.org")));
    session.close(first); // Old UI destruction cannot close its replacement.
    assert(session.allows(second,QStringLiteral("https://example.org")));
    session.visible(false);
    assert(!session.allows(second,QStringLiteral("https://example.org")));
    session.visible(true);
    assert(!session.allows(second,QStringLiteral("https://example.org")));
    adapter.accepted = false;
    assert(session.open(QStringLiteral("https://example.org")) == 0);
    adapter.accepted = true; adapter.revokeDuringPresent = true;
    assert(session.open(QStringLiteral("https://example.org")) == 0);
    assert(adapter.dismissals == 4);

    // Global native entry points reject a foreign thread before touching state.
    std::thread foreign([] {
        assert(openNativeWeb(QStringLiteral("https://example.org")) == 0);
        assert(!nativeWebMayNavigate(1,QStringLiteral("https://example.org")));
        assert(!installNativeWebAdapter(nullptr));
        closeNativeWeb(1);
    });
    foreign.join();

    // Instantiate the ORIGINAL QML. Only the Application/native boundary is a
    // test object; there is no QtWebView, browser, target or network call.
    QQmlEngine engine;
    auto boundary = engine.evaluate(QStringLiteral(
        "({ opens:0, closes:0, openContainedNativeWeb:function(url){this.opens++; return 42;},"
        "closeContainedNativeWeb:function(ticket){this.closes++;} })"));
    engine.rootContext()->setContextProperty(QStringLiteral("ApplicationInterface"), QVariant::fromValue(boundary));
    QQmlComponent component(&engine, QUrl::fromLocalFile(QString::fromLocal8Bit(argv[1])));
    if (component.isError()) { qWarning() << component.errors(); return 2; }
    auto object = component.create();
    if (!object) { qWarning() << component.errors(); return 3; }
    object->setProperty("url", QUrl(QStringLiteral("https://example.org/test")));
    assert(boundary.property(QStringLiteral("opens")).toInt() == 0);
    QVariant opened;
    assert(QMetaObject::invokeMethod(object,"openNative",Q_RETURN_ARG(QVariant,opened)));
    assert(opened.toBool());
    assert(boundary.property(QStringLiteral("opens")).toInt() == 1);
    object->setProperty("visible",false);
    assert(boundary.property(QStringLiteral("closes")).toInt() == 1);
    assert(QMetaObject::invokeMethod(object,"openNative",Q_RETURN_ARG(QVariant,opened)));
    assert(!opened.toBool());
    object->setProperty("visible",true);
    object->setProperty("userScriptUrl",QStringLiteral("file:///test-only-script.js"));
    assert(QMetaObject::invokeMethod(object,"openNative",Q_RETURN_ARG(QVariant,opened)));
    assert(!opened.toBool());
    assert(boundary.property(QStringLiteral("opens")).toInt() == 1);
    delete object;
}
