// SPDX-License-Identifier: Apache-2.0
#include <cassert>
#include <functional>
#include <vector>
#include <QtCore/QCoreApplication>
#include <QtCore/QEventLoop>
#include <QtCore/QPointer>
#include <QtCore/QThread>
#include <QtCore/QUrl>
#include <QtNetwork/QHostInfo>
#include "libraries/networking/src/RequestCancellation.h"

#ifdef TEST_RESOLVER_BOUNDARY
// Only the static OS resolver boundary is substituted. Real Qt objects, thread
// checks, guarded receivers, original ticket and original lookup code remain.
class TestHostInfo : public QHostInfo {
public:
    static std::vector<std::function<void(const TestHostInfo&)>> pending;
    static unsigned aborts;
    static bool failStart;
    template<class Callback>
    static int lookupHost(const QString&, QObject*, Callback callback) {
        if (failStart) { return -1; }
        pending.emplace_back(callback);
        return 7; // Deliberately reuse OS IDs; generation must still reject old replies.
    }
    static void abortHostLookup(int id) {
        assert(id == 7);
        ++aborts;
        // Worst-case reentrant old delivery during abort, not assumed by Qt.
        TestHostInfo info;
        for (auto callback : pending) { callback(info); }
    }
};
std::vector<std::function<void(const TestHostInfo&)>> TestHostInfo::pending;
unsigned TestHostInfo::aborts = 0;
bool TestHostInfo::failStart = false;
#define QHostInfo TestHostInfo
#endif
#include "libraries/networking/src/ScopedHostnameLookup.h"

class DomainCaller : public QObject {
public:
    void start(QUrl domainURL) {
#include "domain-lookup-binding.inc"
    }
    void reset() { _hostnameLookup.cancel(); }
    void completedHostnameLookup(const QHostInfo&) { ++socketChanges; }
    unsigned socketChanges { 0 };
    overte::network::ScopedHostnameLookup _hostnameLookup;
};

int main(int argc, char** argv) {
    QCoreApplication app(argc, argv);
    QObject receiver;
    using overte::network::ScopedHostnameLookup;
#ifdef TEST_RESOLVER_BOUNDARY
    ScopedHostnameLookup lookup;
    unsigned effects = 0;
    auto apply = [&](const QHostInfo&) { ++effects; };
    assert(lookup.start("old.invalid", &receiver, apply));
    auto old = QHostInfo::pending.back();
    assert(lookup.start("new.invalid", &receiver, apply));
    assert(effects == 0 && QHostInfo::aborts == 1);
    QHostInfo info;
    old(info);
    assert(effects == 0);
    auto current = QHostInfo::pending.back();
    current(info);
    current(info);
    assert(effects == 1); // Exactly once, not even duplicate successful delivery.
    lookup.cancel();
    assert(QHostInfo::aborts == 1); // Completed OS ID must not be aborted/reused.

    assert(lookup.start("pending.invalid", &receiver, apply));
    auto cancelled = QHostInfo::pending.back();
    lookup.cancel();
    cancelled(info);
    assert(effects == 1);
    {
        ScopedHostnameLookup temporary;
        assert(temporary.start("destroyed.invalid", &receiver, apply));
    }
    QHostInfo::pending.back()(info);
    assert(effects == 1); // No dereference of destroyed lookup owner.
    auto destroyedReceiver = new QObject;
    assert(lookup.start("receiver.invalid", destroyedReceiver, apply));
    auto deliveredAfterReceiver = QHostInfo::pending.back();
    const auto abortsBeforeReceiver = QHostInfo::aborts;
    delete destroyedReceiver;
    deliveredAfterReceiver(info);
    assert(effects == 1);

    assert(!lookup.start("", &receiver, apply));
    assert(QHostInfo::aborts == abortsBeforeReceiver);
    assert(!lookup.start("invalid.invalid", nullptr, apply));
    assert(!lookup.start("invalid.invalid", &receiver, {}));
    QObject foreignReceiver;
    QThread foreignThread;
    foreignReceiver.moveToThread(&foreignThread);
    assert(!lookup.start("foreign.invalid", &foreignReceiver, apply));
    QHostInfo::failStart = true;
    assert(!lookup.start("failed.invalid", &receiver, apply));
    QHostInfo::failStart = false;
    assert(lookup.start("latest.invalid", &receiver, apply));
    QHostInfo::pending.back()(info);
    assert(effects == 2);
    DomainCaller domain;
    domain.start(QUrl("hifi://old.invalid"));
    auto previousDomain = QHostInfo::pending.back();
    domain.reset();
    domain.start(QUrl("hifi://new.invalid"));
    previousDomain(info);
    assert(domain.socketChanges == 0);
    QHostInfo::pending.back()(info);
    assert(domain.socketChanges == 1);
#else
    // Real Qt asynchronous resolver using a numeric loopback address, never a
    // public/private hostname or external network target.
    ScopedHostnameLookup lookup;
    QEventLoop loop;
    unsigned effects = 0;
    assert(lookup.start("127.0.0.1", &receiver, [&](const QHostInfo& info) {
        assert(info.error() == QHostInfo::NoError);
        assert(info.addresses().contains(QHostAddress::LocalHost));
        ++effects;
        loop.quit();
    }));
    QTimer::singleShot(2000, &loop, &QEventLoop::quit);
    loop.exec();
    assert(effects == 1);
#endif
}
