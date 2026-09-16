// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <functional>
#include <QtCore/QPointer>
#include <QtCore/QThread>
#include <QtNetwork/QHostInfo>
#include "RequestCancellation.h"

namespace overte { namespace network {
// Owned and used in the receiver's event-loop thread. Resolver abort is best
// effort; the ticket independently rejects replies already queued by Qt.
class ScopedHostnameLookup {
public:
    ~ScopedHostnameLookup() { cancel(); }
    void cancel() {
        _scope.setActive(false); // Invalidate BEFORE potentially reentrant abort.
        QObject::disconnect(_receiverDestroyed);
        const int previous = _lookupId;
        _lookupId = -1;
        if (previous >= 0) { QHostInfo::abortHostLookup(previous); }
    }
    bool start(const QString& hostname, QObject* receiver,
               std::function<void(const QHostInfo&)> callback) {
        cancel();
        if (!receiver || receiver->thread() != QThread::currentThread() ||
            hostname.isEmpty() || !callback) { return false; }
        _scope.setActive(true);
        const auto ticket = _scope.next();
        if (!ticket.current()) { return false; }
        QPointer<QObject> guardedReceiver(receiver);
        _receiverDestroyed = QObject::connect(receiver, &QObject::destroyed, [this, ticket] {
            if (!ticket.current()) { return; }
            ticket.deactivateIfCurrent();
            _lookupId = -1; // Qt cancels delivery with its receiver; don't reuse this ID.
        });
        _lookupId = QHostInfo::lookupHost(hostname, receiver,
            [this, ticket, guardedReceiver, callback](const QHostInfo& info) {
                if (!ticket.current() || !guardedReceiver) { return; }
                _lookupId = -1;
                QObject::disconnect(_receiverDestroyed);
                ticket.deactivateIfCurrent(); // Consume before external callback.
                callback(info);
            });
        if (_lookupId < 0) { cancel(); return false; }
        return true;
    }
private:
    RequestScope _scope;
    int _lookupId { -1 };
    QMetaObject::Connection _receiverDestroyed;
};
}} // namespace overte::network
