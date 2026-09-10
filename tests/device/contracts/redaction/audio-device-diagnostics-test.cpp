#include <QtCore/QCoreApplication>
#include <QtCore/QLoggingCategory>
#include <QtCore/QStringList>
#include "security/redaction/SafeDiagnostics.h"
#include <cassert>

Q_LOGGING_CATEGORY(audioclient, "overte.test.audio-device-diagnostics")
static QStringList messages;
static void capture(QtMsgType, const QMessageLogContext&, const QString& message) { messages.append(message); }

int main(int argc, char** argv) {
    QCoreApplication app(argc, argv);
    QLoggingCategory::setFilterRules("*.debug=true");
    auto previous = qInstallMessageHandler(capture);
    const QString canary("Private person's USB headset / private-device-id-canary");
    qCDebug(audioclient).noquote() << canary;
    assert(messages.size() == 1 && messages.first() == canary); // The actual Qt sink is active.
    messages.clear();
    // Exactly the ten complete changed original source expressions. No audio,
    // OS or user device getter exists in this compilation boundary.
#include "audio-device-sinks.inc"
    assert(messages.size() == 10);
    for (const auto& message : messages) {
        assert(message == "OVT_REDACTED" && !message.contains(canary));
    }
    qInstallMessageHandler(previous);
}
