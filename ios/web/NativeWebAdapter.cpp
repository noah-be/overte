// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0
#include "NativeWebAdapter.h"
#include <QGuiApplication>
#include <QThread>

namespace overte::ios {
bool acceptsNativeWebMime(const QString& mime) {
    return mime.compare(QStringLiteral("text/plain"), Qt::CaseInsensitive) == 0;
}
namespace {
bool guiThread() { return qGuiApp && QThread::currentThread() == qGuiApp->thread(); }
}
bool NativeWebAdapter::present(const web::Request& request) noexcept {
    if (!guiThread() || _request || _nativeCleanupFailed ||
            !web::nativeWebMayNavigate(request.ticket, request.url.toString(QUrl::FullyEncoded))) {
        return false;
    }
    _request = request; // Own private input across native asynchronous confirmation.
    _confirmed = false;
    const bool accepted = _operations.confirmation(request);
    if (!accepted) { dismiss(request.ticket); }
    return accepted && _request && _request->ticket == request.ticket;
}
void NativeWebAdapter::dismiss(std::uint64_t ticket) noexcept {
    if (!guiThread() || !_request || _request->ticket != ticket) { return; }
    _request.reset(); // Invalidate local callbacks before entering native teardown.
    _confirmed = false;
    if (!_operations.dismiss(ticket)) {
        // No OS-stop receipt is fabricated. A failed teardown cannot be followed
        // by another live native view in this process.
        _nativeCleanupFailed = true;
    }
}
bool NativeWebAdapter::confirm(std::uint64_t ticket) {
    if (!guiThread() || !_request || _request->ticket != ticket || _confirmed ||
            !web::nativeWebMayNavigate(ticket, _request->url.toString(QUrl::FullyEncoded))) {
        return false;
    }
    _confirmed = true;
    return true;
}
bool NativeWebAdapter::mayNavigate(std::uint64_t ticket, const QString& destination) const {
    return guiThread() && _request && _request->ticket == ticket && _confirmed &&
        web::nativeWebMayNavigate(ticket, destination);
}
void NativeWebAdapter::close(std::uint64_t ticket) {
    if (guiThread() && _request && _request->ticket == ticket) {
        web::closeNativeWeb(ticket); // Shared invalidates first, then calls dismiss.
    }
}
} // namespace overte::ios
