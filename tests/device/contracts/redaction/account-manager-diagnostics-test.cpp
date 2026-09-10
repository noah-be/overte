#include <QtCore/QCoreApplication>
#include <QtCore/QDebug>
#include <QtCore/QLoggingCategory>
#include <QtCore/QUuid>
#include <QtCore/QStringList>
#include "security/redaction/SafeDiagnostics.h"
#include <cassert>

Q_LOGGING_CATEGORY(networking, "overte.test.account-diagnostics")
static QStringList messages;
static void capture(QtMsgType, const QMessageLogContext&, const QString& value) { messages.append(value); }
// Transport boundary: the complete failure method must not access its raw data.
struct QNetworkReply {
    int urlReads = 0, errorReads = 0;
    QString url() { ++urlReads; return "https://private-account-canary.invalid"; }
    QString errorString() { ++errorReads; return "token-secret-canary"; }
};
struct AccountManager {
    QUuid _sessionID;
    bool _isWaitingForKeypairResponse = true;
    void setSessionID(const QUuid&);
    void publicKeyUploadFailed(QNetworkReply*);
    void handleKeypairGenerationError();
};
#include "methods.inc"

int main(int argc, char** argv) {
    QCoreApplication application(argc, argv);
    QLoggingCategory::setFilterRules("*.debug=true");
    auto previous = qInstallMessageHandler(capture);
    const QString canary("https://private-account-canary.invalid?token=secret-canary");
    qCDebug(networking).noquote() << canary;
    assert(messages.size() == 1 && messages.first() == canary); // Positive raw-sink proof.
    messages.clear();
#include "sinks.inc"
    assert(messages.size() == 53);
    assert(messages.count("OVT_AUTH_READY") == 1 && messages.count("OVT_REDACTED") == 52);
    AccountManager manager;
    const QUuid session("c4cae808-10d5-45c3-9077-3e68a3c096aa");
    manager.setSessionID(session);
    assert(manager._sessionID == session && messages.size() == 54);
    manager.setSessionID(session);
    assert(messages.size() == 54); // Same-ID no-op preserved.
    QNetworkReply reply;
    manager.publicKeyUploadFailed(&reply);
    assert(!manager._isWaitingForKeypairResponse && messages.size() == 55);
    assert(reply.urlReads == 0 && reply.errorReads == 0);
    manager._isWaitingForKeypairResponse = true;
    manager.handleKeypairGenerationError();
    assert(!manager._isWaitingForKeypairResponse && messages.size() == 56);
    for (const auto& message : messages) {
        assert(message == "OVT_REDACTED" || message == "OVT_AUTH_READY");
        assert(!message.contains(canary) && !message.contains(session.toString()));
    }
    qInstallMessageHandler(previous);
}
