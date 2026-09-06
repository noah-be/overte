// SPDX-License-Identifier: Apache-2.0
// Real complete Shared header/Qt, only Apple OS transport substituted.
#include <QtCore/QtCore>
#include <cassert>
#include <vector>
#if TEST_OS_SINK
#define Q_OS_IOS 1
#endif
#define OVERTE_IOS 1
#include "libraries/shared/src/shared/IOSRuntimeLogging.h"
static std::vector<QString> qtMessages;
static int formats = 0;
struct Payload {};
QDebug operator<<(QDebug debug, const Payload&) { ++formats; return debug << "private-format-canary"; }
static void capture(QtMsgType, const QMessageLogContext&, const QString& text) { qtMessages.push_back(text); }
struct AddressManager {
    QUuid lookedUp;
    int calls { 0 };
    void lookupShareableNameForDomainID(QUuid id) { lookedUp = id; ++calls; }
};
static AddressManager address;
struct DependencyManager { template<class T> static T* get() { return &address; } };
struct DomainBoundary {
    bool connected { false }; int local { 0 }; QUuid id;
    bool isConnected() const { return connected; }
    void setLocalID(int value) { local = value; }
    void setUUID(QUuid value) { id = value; }
    void setIsConnected(bool value) { connected = value; }
};
int main(int argc, char** argv) {
    QCoreApplication app(argc, argv);
    qInstallMessageHandler(capture); // Raw sink; no global sanitizer.
    logIOSRuntimeMarker("OVT_AUTH_READY private-target-canary", Payload{}, QString("token-private-canary"));
    assert(formats == 0);
    assert(qtMessages.size() == 1 && qtMessages.back() == "OVT_REDACTED");
    logIOSRuntimeEvent(overte::security::DiagnosticEvent::ConnectionReady);
    assert(qtMessages.back() == "OVT_CONNECTION_READY");
    logIOSRuntimeEvent(static_cast<overte::security::DiagnosticEvent>(999));
    assert(qtMessages.back() == "OVT_REDACTED");
    QTemporaryDir temporary;
    assert(temporary.isValid());
    const auto path = temporary.path() + "/config-path-private-canary.json";
    QFile file(path);
    assert(file.open(QIODevice::WriteOnly));
    file.write("{\"schemaVersion\":1,\"config-secret-canary\":\"value-private-canary\"}");
    file.close();
    qputenv("OVERTE_IOS_DIAGNOSTIC_CONFIG", path.toUtf8());
    assert(iosRuntimeDiagnosticConfig().value("config-secret-canary").toString() == "value-private-canary");
    assert(qtMessages.size() == 4 && qtMessages.back() == "OVT_REDACTED");
    beginIOSRuntimeEntityEvidence();
    assert(recordIOSRuntimeTreeEntity("entity-private-canary").isEmpty());
    assert(recordIOSRuntimeRenderableEntity("entity-private-canary").isEmpty());
    const auto evidence = commitIOSRuntimeEntityEvidence();
    assert(evidence == "entity-private-canary"); // Legitimate internal state unchanged.
    logIOSRuntimeEntityEvidence(evidence);
    assert(qtMessages.size() == 6);
    DomainBoundary _domainHandler;
    const int domainLocalID = 41;
    const QUuid domainUUID("481c3941-a61b-4292-9888-ab371804e7f7");
    auto connect = [&] {
#include "nodelist-connected.inc"
    };
    connect(); connect();
    assert(_domainHandler.connected && _domainHandler.local == 41 && _domainHandler.id == domainUUID);
    assert(address.calls == 1 && address.lookedUp == domainUUID);
    assert(qtMessages.size() == 7 && qtMessages.back() == "OVT_CONNECTION_READY");
    for (const auto& message : qtMessages) {
        assert(message == "OVT_REDACTED" || message == "OVT_CONNECTION_READY");
    }
#if TEST_OS_SINK
    assert(osMessages == qtMessages); // Same constant bytes directly at public OS boundary.
#endif
    qInstallMessageHandler(nullptr);
}
