// SPDX-License-Identifier: Apache-2.0
#include <QtCore/QCoreApplication>
#include <QtCore/QLoggingCategory>
#include <QtCore/QSharedPointer>
#include <QtCore/QUuid>
#include <cassert>
#include <vector>
#include "security/redaction/SafeDiagnostics.h"
Q_LOGGING_CATEGORY(networking, "nodelist-diagnostics-test")
Q_LOGGING_CATEGORY(networking_ice, "nodelist-ice-test")
static std::vector<QString> messages;
static void capture(QtMsgType, const QMessageLogContext&, const QString& text) {
    messages.push_back(text); // Deliberately no sanitizer in this capture sink.
}
const int NUM_BYTES_RFC4122_UUID = 16;
struct ReceivedMessage {
    std::vector<QByteArray> uuids;
    unsigned read { 0 };
    QString username;
    bool admin { false };
    QByteArray readWithoutCopy(int size) { assert(size == 16 && read < uuids.size()); return uuids[read++]; }
    QString readString() { return username; }
    void readPrimitive(bool* result) { *result = admin; }
};
struct NodeList {
    QString node, user, fingerprint;
    bool admin { false };
    unsigned signalCount { 0 };
    void processUsernameFromIDReply(QSharedPointer<ReceivedMessage> message);
    void usernameFromIDReply(QString id, QString name, QString machine, bool isAdmin) {
        ++signalCount; node = id; user = name; fingerprint = machine; admin = isAdmin;
    }
};
#include "nodelist-user-reply.inc"
int main(int argc,char** argv) {
    QCoreApplication app(argc,argv);
    qInstallMessageHandler(capture);
    QLoggingCategory::setFilterRules("*.debug=true");
#include "nodelist-diagnostic-expressions.inc"
    assert(messages.size() == 52);
    for(const auto& message : messages) { assert(message == QStringLiteral("OVT_REDACTED")); }
    messages.clear();
    auto packet = QSharedPointer<ReceivedMessage>::create();
    const QUuid node("d71e760e-941e-48fd-9b71-c8283f11b12c");
    const QUuid machine("0c6d8c3d-1714-4f9c-99df-ac541ec98b01");
    packet->uuids = {node.toRfc4122(),machine.toRfc4122()};
    packet->username = "fixture-user-private-%61uth-token-canary";
    packet->admin = true;
    NodeList list;
    list.processUsernameFromIDReply(packet);
    assert(list.signalCount == 1 && list.node == node.toString() && list.fingerprint == machine.toString());
    assert(list.user == packet->username && list.admin); // Preserve actual app data delivery.
    assert(packet->read == 2 && messages.size() == 1 && messages.front() == "OVT_REDACTED");
    qInstallMessageHandler(nullptr);
}
