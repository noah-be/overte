// SPDX-License-Identifier: Apache-2.0
#include "NativeWebPolicy.h"
#include <QGuiApplication>
#include <QThread>

namespace overte { namespace web {
namespace {
constexpr std::uint64_t MAX_TICKET = (std::uint64_t(1) << 53) - 1; // Exact in QML numbers.
bool parse(const QString& input, QUrl& url, QString& origin) {
    if (input.isEmpty() || input.size() > 8192) { return false; }
    for (auto character : input) {
        if (character.unicode() <= 32 || character.unicode() == 127 || character == QChar('\\')) { return false; }
    }
    url = QUrl(input, QUrl::StrictMode);
    if (!url.isValid() || url.isRelative() || url.scheme().compare(QStringLiteral("https"), Qt::CaseInsensitive) != 0 ||
        url.host().isEmpty() || url.authority(QUrl::FullyEncoded).contains(QChar('@')) || url.port(443) != 443) { return false; }
    // Strict same canonical HTTPS origin; no credentials, downgrade, nonstandard
    // port, custom scheme, relative URL, automatic external window or download.
    url.setScheme(QStringLiteral("https"));
    url.setPort(-1);
    QUrl canonical;
    canonical.setScheme(QStringLiteral("https"));
    canonical.setHost(url.host().toLower());
    origin = canonical.toString(QUrl::FullyEncoded);
    return !origin.isEmpty();
}
bool guiThread() {
    return qGuiApp && QThread::currentThread() == qGuiApp->thread();
}
Session& processSession() {
    static Session session;
    static bool connected = false;
    if (!connected) {
        connected = true;
        session.visible(QGuiApplication::applicationState() == Qt::ApplicationActive);
        QObject::connect(qGuiApp, &QGuiApplication::applicationStateChanged, qGuiApp,
            [](Qt::ApplicationState state) { session.visible(state == Qt::ApplicationActive); });
        QObject::connect(qGuiApp, &QCoreApplication::aboutToQuit, qGuiApp,
            [] { session.visible(false); });
    }
    return session;
}
}

bool Session::install(Adapter* adapter) {
    if (!adapter || _adapter) { return false; }
    _adapter = adapter;
    return true;
}
void Session::invalidate() {
    const auto previous = _generation;
    const bool wasActive = _active;
    _active = false;
    _origin.clear();
    if (_generation < MAX_TICKET) { ++_generation; }
    if (wasActive && _adapter) {
        const bool dispatching = _dispatching;
        _dispatching = true;
        _adapter->dismiss(previous);
        _dispatching = dispatching;
    }
}
void Session::visible(bool value) {
    if (_visible == value) { return; }
    _visible = value;
    if (!value) { invalidate(); }
}
std::uint64_t Session::open(const QString& input) {
    QUrl url;
    QString origin;
    if (_dispatching || !_visible || !_adapter || !parse(input, url, origin) || _generation >= MAX_TICKET) { return 0; }
    invalidate(); // Old callbacks are invalid before native dismissal/new UI.
    if (_generation >= MAX_TICKET || !_visible) { return 0; }
    _origin = origin;
    _active = true;
    const auto ticket = _generation;
    _dispatching = true;
    const bool accepted = _adapter->present({ ticket, url, origin });
    _dispatching = false;
    if (!accepted) { close(ticket); return 0; }
    return _active && _generation == ticket ? ticket : 0;
}
bool Session::allows(std::uint64_t ticket, const QString& destination) const {
    QUrl url;
    QString origin;
    return _visible && _active && ticket != 0 && ticket == _generation &&
        parse(destination, url, origin) && origin == _origin;
}
void Session::close(std::uint64_t ticket) {
    if (_active && ticket == _generation) { invalidate(); }
}
bool installNativeWebAdapter(Adapter* adapter) {
    return guiThread() && processSession().install(adapter);
}
std::uint64_t openNativeWeb(const QString& input) {
    return guiThread() ? processSession().open(input) : 0;
}
bool nativeWebMayNavigate(std::uint64_t ticket, const QString& destination) {
    return guiThread() && processSession().allows(ticket, destination);
}
void closeNativeWeb(std::uint64_t ticket) {
    if (guiThread()) { processSession().close(ticket); }
}
} }
