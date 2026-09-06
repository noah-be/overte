// SPDX-License-Identifier: Apache-2.0
#include <cassert>
#include <functional>
#include <vector>
#include <QtCore/QCoreApplication>
#include <QtCore/QLoggingCategory>
#include <QtCore/QUuid>
#include <QtNetwork/QHostInfo>
#include "libraries/networking/src/RequestCancellation.h"
#include "security/redaction/SafeDiagnostics.h"
Q_LOGGING_CATEGORY(networking_ice, "sh005.ice-test")
class ResolverBoundary : public QHostInfo {
public:
    static inline std::vector<std::function<void(const ResolverBoundary&)>> pending;
    static inline bool failStart { false };
    template<class Callback>
    static int lookupHost(const QString&, QObject*, Callback callback) {
        if (failStart) { return -1; }
        pending.emplace_back(callback);
        return 7; // Reused ID must not bypass the original generation guard.
    }
    static void abortHostLookup(int id) {
        assert(id == 7);
        ResolverBoundary info;
        info.setAddresses({ QHostAddress("127.0.0.9") });
        for (auto callback : pending) { callback(info); } // Reentrant old completion.
    }
};
#define QHostInfo ResolverBoundary
#include "libraries/networking/src/ScopedHostnameLookup.h"
enum class SocketType { UDP };
constexpr quint16 ICE_SERVER_DEFAULT_PORT = 7337;
// Socket storage, node timing receiver and reset tail are explicit boundaries;
// actual QHostAddress/QUuid and both full ICE production functions are compiled.
struct SockAddr {
    QHostAddress address;
    quint16 port { 0 };
    SockAddr() = default;
    SockAddr(SocketType, QHostAddress a, quint16 p) : address(a), port(p) {}
    const QHostAddress& getAddress() const { return address; }
    void setAddress(const QHostAddress& a) { address = a; }
    void setObjectName(const char*) {}
};
QDebug operator<<(QDebug out, const SockAddr&) { return out << "fixture socket"; }
struct LimitedNodeList { enum class ConnectionStep { SetICEServerHostname, SetICEServerSocket }; };
struct NodeList {
    int starts { 0 }, completions { 0 };
    void flagTimeForConnectionStep(LimitedNodeList::ConnectionStep step) {
        if (step == LimitedNodeList::ConnectionStep::SetICEServerHostname) { ++starts; } else { ++completions; }
    }
};
static NodeList node;
struct DependencyManager { template<class T> static T* get() { return &node; } };
class DomainHandler : public QObject {
public:
    SockAddr _iceServerSockAddr;
    QUuid _pendingDomainID, _iceClientID;
    bool _isInErrorState { false };
    int emissions { 0 };
    overte::network::ScopedHostnameLookup _hostnameLookup, _iceHostnameLookup;
    void hardReset(QString = {}) {
#include "ice-reset.inc"
        _iceServerSockAddr = SockAddr();
        _pendingDomainID = {};
        _isInErrorState = false;
    }
    void setIceServerHostnameAndID(const QString&, const QUuid&);
    void completedIceServerHostnameLookup();
    void iceSocketAndIDReceived() { ++emissions; }
};
#include "ice-original.inc"
int main(int argc, char** argv) {
    QCoreApplication app(argc, argv);
    QLoggingCategory::setFilterRules("sh005.ice-test.debug=false");
    DomainHandler domain;
    const auto firstID = QUuid::createUuid(), secondID = QUuid::createUuid();
    domain.setIceServerHostnameAndID("old.invalid", firstID);
    auto old = QHostInfo::pending.back();
    domain.setIceServerHostnameAndID("new.invalid", secondID);
    assert(domain.emissions == 0 && domain._iceServerSockAddr.getAddress().isNull());
    QHostInfo success;
    success.setAddresses({ QHostAddress("::1"), QHostAddress("127.0.0.2") });
    old(success);
    assert(domain.emissions == 0);
    auto current = QHostInfo::pending.back();
    current(success);
    current(success);
    assert(domain.emissions == 1 && domain._pendingDomainID == secondID);
    assert(domain._iceServerSockAddr.getAddress() == QHostAddress("127.0.0.2"));
    domain.setIceServerHostnameAndID("pending.invalid", firstID);
    auto cancelled = QHostInfo::pending.back();
    domain.hardReset();
    cancelled(success);
    assert(domain.emissions == 1 && domain._iceServerSockAddr.getAddress().isNull());
    domain.setIceServerHostnameAndID("127.0.0.3", firstID);
    assert(domain.emissions == 2 && domain._iceServerSockAddr.getAddress() == QHostAddress("127.0.0.3"));
    cancelled(success);
    assert(domain.emissions == 2 && domain._iceServerSockAddr.getAddress() == QHostAddress("127.0.0.3"));
    domain.setIceServerHostnameAndID("127.0.0.3", firstID);
    assert(domain.emissions == 2); // Existing identical numeric socket is not restarted.
    for (int failure = 0; failure < 3; ++failure) {
        domain.setIceServerHostnameAndID("failure.invalid", firstID);
        QHostInfo info;
        if (failure == 0) { info.setError(QHostInfo::HostNotFound); info.setAddresses(success.addresses()); }
        if (failure == 1) { info.setAddresses({ QHostAddress("::1") }); }
        QHostInfo::pending.back()(info);
        assert(domain.emissions == 2 && domain._iceServerSockAddr.getAddress().isNull());
    }
    QHostInfo::failStart = true;
    domain.setIceServerHostnameAndID("failed-launch.invalid", firstID);
    QHostInfo::failStart = false;
    assert(domain.emissions == 2);
    domain.setIceServerHostnameAndID("last.invalid", secondID);
    QHostInfo::pending.back()(success);
    assert(domain.emissions == 3 && node.completions == 3);
    std::function<void(const QHostInfo&)> dead;
    {
        DomainHandler temporary;
        temporary.setIceServerHostnameAndID("destroyed.invalid", firstID);
        dead = QHostInfo::pending.back();
    }
    dead(success);
    assert(node.completions == 3);
}
