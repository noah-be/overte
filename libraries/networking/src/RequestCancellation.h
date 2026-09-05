// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <atomic>
#include <limits>
#include <memory>
#include <QtCore/QTimer>
#include <QtCore/QVariant>
#include <QtNetwork/QNetworkReply>

namespace overte { namespace network {
class RequestScope;
class RequestTicket {
public:
    // Other AccountManager requests remain explicitly unscoped.
    bool scoped() const { return bool(_state); }
    bool current() const {
        return !_state || ((_value & 1) && _state->load(std::memory_order_acquire) == _value);
    }
    void deactivateIfCurrent() const {
        if (_state) {
            quint64 expected = _value;
            _state->compare_exchange_strong(expected, _value & ~quint64(1), std::memory_order_acq_rel);
        }
    }
private:
    friend class RequestScope;
    std::shared_ptr<std::atomic<quint64>> _state;
    quint64 _value { 0 };
};

class RequestScope {
public:
    RequestScope() : _state(std::make_shared<std::atomic<quint64>>(3)) {}
    ~RequestScope() { _state->store(0, std::memory_order_release); }
    RequestScope(const RequestScope&) = delete;
    RequestScope& operator=(const RequestScope&) = delete;
    // A new HTTP lookup supersedes the preceding lookup, without exposing URLs
    // in tickets. Zero is permanent exhausted/destroyed state, never reusable.
    RequestTicket next() {
        RequestTicket ticket; ticket._state = _state;
        ticket._value = advance(-1);
        return ticket;
    }
    void setActive(bool active) { advance(active ? 1 : 0); }
private:
    quint64 advance(int active) {
        quint64 old = _state->load(std::memory_order_acquire);
        while (old != 0) {
            if (active >= 0 && bool(old & 1) == bool(active)) { return old; }
            const quint64 value = old > std::numeric_limits<quint64>::max() - 2 ? 0 :
                ((old & ~quint64(1)) + 2) | (active < 0 ? old & 1 : quint64(active));
            if (_state->compare_exchange_weak(old, value, std::memory_order_acq_rel)) { return value; }
        }
        return 0;
    }
    std::shared_ptr<std::atomic<quint64>> _state;
};
}} // namespace overte::network

Q_DECLARE_METATYPE(overte::network::RequestTicket)

namespace overte { namespace network {
inline bool replyCurrent(const QNetworkReply* reply) {
    const auto property = reply->property("_overte_request_ticket");
    return !property.isValid() || (property.canConvert<RequestTicket>() && property.value<RequestTicket>().current());
}
inline void watchRequest(QNetworkReply* reply, const RequestTicket& ticket) {
    if (!ticket.scoped()) { return; }
    reply->setProperty("_overte_request_ticket", QVariant::fromValue(ticket));
    // All reply operations execute in the reply's own event loop. Atomic
    // invalidation rejects callbacks immediately, even before this timer runs.
    // 20ms is a requested observation interval, NOT a hard OS-stop guarantee.
    auto timer = new QTimer(reply);
    timer->setInterval(20);
    QObject::connect(timer, &QTimer::timeout, reply, [reply, ticket, timer] {
        if (!ticket.current()) { timer->stop(); reply->abort(); }
    });
    QObject::connect(reply, &QNetworkReply::finished, timer, &QTimer::stop);
    timer->start();
}
}} // namespace overte::network
