// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <QString>
#include <atomic>

namespace overte::ios {
// Immutable request authority plus an atomic native-operation epoch. The main
// UIKit actor and the Qt owner share cancellation; neither can revive a retired
// operation. Photos commitment wins atomically against pre-commit cancellation.
class SnapshotExportOperation {
public:
    enum class Phase : unsigned { Queued=1, Authorizing=2, Choosing=3, Committed=4 };
    SnapshotExportOperation(QString ticket,QString path,QString action) :
        ticket(std::move(ticket)),path(std::move(path)),action(std::move(action)) {}
    const QString ticket,path,action;
    bool current() const { return _state.load()!=0; }
    bool cancelled() const { return bool(_state.load() & CANCELLED); }
    Phase phase() const { return Phase(_state.load() & ~CANCELLED); }
    bool advance(Phase phase) {
        unsigned old=_state.load();
        while(old!=0 && !(old&CANCELLED)) {
            const auto prior=Phase(old);
            const bool allowed=(prior==Phase::Queued &&
                ((action=="save" && phase==Phase::Authorizing)||(action=="share" && phase==Phase::Choosing))) ||
                (prior==Phase::Authorizing && action=="save" && phase==Phase::Committed);
            if(!allowed){return false;}
            if(_state.compare_exchange_weak(old,unsigned(phase))){return true;}
        }
        return false;
    }
    void cancel() {
        unsigned old=_state.load();
        while(old!=0 && !(old&CANCELLED) && !_state.compare_exchange_weak(old,old|CANCELLED)) {}
    }
    bool finish() { return _state.exchange(0)!=0; }
private:
    static constexpr unsigned CANCELLED=8;
    std::atomic<unsigned> _state {unsigned(Phase::Queued)};
};
} // namespace overte::ios
