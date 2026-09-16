// SPDX-License-Identifier: Apache-2.0
#include <cassert>
#include <vector>
#include <QtCore/QCoreApplication>
#include <QtCore/QLoggingCategory>
#include <QtCore/QUrl>
#include <QtCore/QPointer>
#include "security/redaction/SafeDiagnostics.h"
#include "libraries/networking/src/RequestCancellation.h"
Q_LOGGING_CATEGORY(networking, "address-diagnostics-test")
Q_LOGGING_CATEGORY(networking_ice, "address-diagnostics-ice-test")
std::vector<QString> messages;
void capture(QtMsgType, const QMessageLogContext&, const QString& text) {
    messages.push_back(text); // No sanitizer here: test the actual raw payload.
}
class Reply : public QNetworkReply {
public:
    Reply() {
        setError(ContentNotFoundError, "fixture-only-secret https://user:password@private.invalid/auth?token=canary");
    }
    void abort() override {}
    qint64 readData(char*, qint64) override { return 0; }
};
class AddressManager {
public:
    overte::network::RequestScope _lookupRequests;
    void handleAPIError(QNetworkReply*);
    void lookupResultIsNotFound() { ++missing; }
    void lookupResultsFinished() { ++finished; }
    QUrl _previousAPILookup { "hifi://fixture-only-private.invalid/location" };
    unsigned missing { 0 }, finished { 0 };
};
#include "address-api-error.inc"
int main(int argc, char** argv) {
    QCoreApplication app(argc, argv);
    qInstallMessageHandler(capture);
    QLoggingCategory::setFilterRules("*.debug=true");
    // Original complete sink expressions, not reimplemented logging calls.
#include "address-diagnostic-expressions.inc"
    assert(messages.size() == 19);
    for (const auto& message : messages) {
        const auto bytes = message.toUtf8();
        assert(bytes == overte::security::sanitizeDiagnostic(bytes.constData(), bytes.size()));
        assert(!bytes.contains("fixture") && !bytes.contains("private") && !bytes.contains("canary"));
    }
    messages.clear();
    AddressManager address;
    Reply reply;
    address.handleAPIError(&reply);
    assert(messages.size() == 1 && messages.front() == "OVT_CONNECTION_FAILED");
    assert(address.missing == 1 && address.finished == 1 && address._previousAPILookup.isEmpty());
    messages.clear();
    overte::network::RequestScope requests;
    const auto stale = requests.next();
    requests.setActive(false);
    reply.setProperty("_overte_request_ticket", QVariant::fromValue(stale));
    address.handleAPIError(&reply);
    assert(messages.empty() && address.missing == 1 && address.finished == 1);
    qInstallMessageHandler(nullptr);
}
