// SPDX-License-Identifier: Apache-2.0
#include <QtCore/QCoreApplication>
#include <QtCore/QLoggingCategory>
#include <QtCore/QSharedPointer>
#include <QtCore/QJsonDocument>
#include <QtCore/QJsonObject>
#include <QtCore/QTimer>
#include <QtCore/QUrl>
#include <cassert>
#include <vector>
#include "security/redaction/SafeDiagnostics.h"
Q_LOGGING_CATEGORY(networking, "domain-diagnostics-test")
Q_LOGGING_CATEGORY(networking_ice, "domain-ice-diagnostics-test")
static std::vector<QString> messages;
static void capture(QtMsgType, const QMessageLogContext&, const QString& text) { messages.push_back(text); }
struct ReceivedMessage { QByteArray data; QByteArray getMessage() { return data; } };
// Packet and signal receivers/policy predicates are boundaries; actual complete
// two production methods and all 30 log expressions use real Qt without a sink sanitizer.
struct DomainHandler {
    QTimer _settingsTimer;
    QJsonObject _settingsObject, delivered;
    QUrl _errorDomainURL, redirected;
    bool _isInErrorState { false }, interstitial { false }, hard { false }, stateSignal { false };
    int _lastDomainConnectionError { -1 }, received { 0 }, refused { 0 }, refusedCode { -1 };
    QString refusedReason, refusedExtra;
    bool getInterstitialModeEnabled() { return interstitial; }
    bool isHardRefusal(int) { return hard; }
    void settingsReceived(QJsonObject value) { ++received; delivered = value; }
    void redirectErrorStateChanged(bool state) { stateSignal = state; }
    void redirectToErrorDomainURL(QUrl url) { redirected = url; }
    void domainConnectionRefused(QString reason, int code, QString extra) {
        ++refused; refusedReason = reason; refusedCode = code; refusedExtra = extra;
    }
    void processSettingsPacketList(QSharedPointer<ReceivedMessage>);
    void setRedirectErrorState(QUrl, QString, int, const QString&);
};
#include "domain-methods.inc"
int main(int argc, char** argv) {
    QCoreApplication app(argc, argv);
    qInstallMessageHandler(capture);
    QLoggingCategory::setFilterRules("*.debug=true");
#include "domain-payloads.inc"
    assert(messages.size() == 30);
    for (const auto& message : messages) { assert(message == "OVT_REDACTED"); }
    messages.clear();
    DomainHandler domain;
    auto packet = QSharedPointer<ReceivedMessage>::create();
    packet->data = R"({"private":"settings-auth-token-canary","url":"https://private.invalid/?token=secret"})";
    domain._settingsTimer.start(1000);
    domain.processSettingsPacketList(packet);
    assert(!domain._settingsTimer.isActive() && domain.received == 1);
    assert(domain.delivered == QJsonDocument::fromJson(packet->data).object());
    assert(messages.size() == 1 && messages.back() == "OVT_REDACTED");
    const QUrl url("https://private.invalid/error?token=canary");
    const QString reason("user-private-canary"), extra("auth-private-canary");
    domain.setRedirectErrorState(url, reason, 17, extra);
    assert(domain.refused == 1 && domain.refusedReason == reason && domain.refusedExtra == extra && domain.refusedCode == 17);
    domain.interstitial = domain.hard = true;
    domain.setRedirectErrorState(url, reason, 18, extra);
    assert(domain._lastDomainConnectionError == 18 && domain.stateSignal && domain.redirected == url && domain.refused == 1);
    assert(messages.size() == 2 && messages.back() == "OVT_REDACTED");
    qInstallMessageHandler(nullptr);
}
