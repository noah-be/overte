// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0
#include "../web/NativeWebAdapter.h"
#include <QGuiApplication>
#include <QWindow>
#include <cassert>
#include <thread>

struct Native final : overte::ios::NativeWebOperations {
    overte::ios::NativeWebAdapter* adapter { nullptr };
    overte::web::Request last {};
    unsigned confirmations { 0 }, dismissals { 0 };
    bool accept { true }, cleanup { true };
    bool confirmation(const overte::web::Request& request) noexcept override {
        ++confirmations; last = request;
        assert(!adapter->mayNavigate(request.ticket, request.url.toString()));
        return accept;
    }
    bool dismiss(std::uint64_t ticket) noexcept override {
        ++dismissals;
        assert(!adapter->mayNavigate(ticket, last.url.toString()));
        assert(!adapter->confirm(ticket));
        return cleanup;
    }
};
int main(int argc, char** argv) {
    assert(overte::ios::acceptsNativeWebMime(QStringLiteral("text/plain")));
    assert(overte::ios::acceptsNativeWebMime(QStringLiteral("TEXT/PLAIN")));
    for (const auto& mime : {QString(), QStringLiteral("text/html"), QStringLiteral("application/xhtml+xml"),
                            QStringLiteral("image/svg+xml"), QStringLiteral("application/pdf")}) {
        assert(!overte::ios::acceptsNativeWebMime(mime));
    }
    QGuiApplication app(argc, argv);
    QWindow window; window.show(); window.requestActivate();
    QCoreApplication::processEvents();
    assert(QGuiApplication::applicationState() == Qt::ApplicationActive);
    Native native;
    overte::ios::NativeWebAdapter adapter(native); native.adapter = &adapter;
    using namespace overte::web;
    assert(installNativeWebAdapter(&adapter));
    const QString initial = QStringLiteral("https://example.org/private-path");
    auto first = openNativeWeb(initial);
    assert(first && native.confirmations == 1 && !adapter.mayNavigate(first, initial));
    assert(adapter.confirm(first) && !adapter.confirm(first));
    assert(adapter.mayNavigate(first, QStringLiteral("https://example.org/next")));
    assert(!adapter.mayNavigate(first, QStringLiteral("https://other.example.org/")));
    assert(!adapter.mayNavigate(first, QStringLiteral("http://example.org/")));
    auto second = openNativeWeb(initial);
    assert(second != first && native.dismissals == 1);
    assert(!adapter.confirm(first) && !adapter.mayNavigate(first, initial));
    adapter.close(first); assert(native.dismissals == 1);
    std::thread foreign([&] {
        assert(!adapter.confirm(second) && !adapter.mayNavigate(second, initial));
        assert(!adapter.present(native.last));
        adapter.close(second); adapter.dismiss(second);
    });
    foreign.join(); assert(native.dismissals == 1);
    assert(adapter.confirm(second));
    // Original process owner observes suspension; no native test session copy.
    QMetaObject::invokeMethod(&app, "applicationStateChanged", Qt::DirectConnection,
                              Q_ARG(Qt::ApplicationState, Qt::ApplicationInactive));
    assert(!adapter.mayNavigate(second, initial) && native.dismissals == 2);
    QMetaObject::invokeMethod(&app, "applicationStateChanged", Qt::DirectConnection,
                              Q_ARG(Qt::ApplicationState, Qt::ApplicationActive));
    assert(!adapter.confirm(second));
    native.accept = false;
    assert(openNativeWeb(initial) == 0 && native.dismissals == 3);
    native.accept = true;
    auto third = openNativeWeb(initial);
    assert(third && adapter.confirm(third));
    native.cleanup = false;
    adapter.close(third);
    const auto presentations = native.confirmations;
    assert(openNativeWeb(initial) == 0 && native.confirmations == presentations);
}
