// SPDX-License-Identifier: Apache-2.0
#ifndef overte_DomainListRequestHistory_h
#define overte_DomainListRequestHistory_h

#include <QtGlobal>
#include <algorithm>
#include <deque>
#include <mutex>

// DomainList echoes the client's check-in timestamp, but packets are unordered.
// Associate that existing wire value with local send order. Do not infer send
// order from wall time, which can move backwards while the client is running.
class DomainListRequestHistory {
public:
    quint64 issued(quint64 wallTime) {
        std::lock_guard<std::mutex> lock(_mutex);
        // The echo token remains a microsecond timestamp during normal clock
        // progression. Keep it unique across resets, duplicate ticks and clock
        // rollback; retain the actual send time separately for RTT accounting.
        const auto token = std::max(wallTime, _lastToken + 1);
        _lastToken = token;
        _pending.push_back({ token, ++_sequence, wallTime });
        // Bound retained replies, not retry count. A fresh check-in can always
        // reconnect even if old packets have aged out during a long pause.
        if (_pending.size() > 64) { _pending.pop_front(); }
        return token;
    }

    bool accept(quint64 token, quint64* sentWallTime = nullptr) {
        std::lock_guard<std::mutex> lock(_mutex);
        const auto request = std::find_if(_pending.begin(), _pending.end(), [=](const Request& value) {
            return value.token == token;
        });
        if (request == _pending.end() || request->sequence < _acceptedSequence) { return false; }
        _acceptedSequence = request->sequence;
        if (sentWallTime) { *sentWallTime = request->wallTime; }
        // Equal sequences are allowed: each packet-list segment repeats the
        // extended header and must still deliver its part of the node list.
        return true;
    }

    void clear() {
        std::lock_guard<std::mutex> lock(_mutex);
        _pending.clear();
        _acceptedSequence = 0;
    }

private:
    struct Request { quint64 token; quint64 sequence; quint64 wallTime; };
    std::mutex _mutex;
    std::deque<Request> _pending;
    quint64 _lastToken { 0 };
    quint64 _sequence { 0 };
    quint64 _acceptedSequence { 0 };
};
#endif
