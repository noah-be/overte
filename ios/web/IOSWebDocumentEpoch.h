// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <EmbeddedWebPolicy.h>
#include <limits>

namespace overte::ios {
// Navigation changes the document, not the source's bridge authority. Every
// newly prepared main-frame navigation gets a fresh unpredictable native nonce;
// old documents cannot claim the next epoch merely by guessing a counter.
class IOSWebDocumentEpoch {
public:
    using Generation = web::EmbeddedWebSession::Generation;
    enum class Verification { Stale, Ready, Reload, Failed };
    static bool isFragmentNavigation(const QUrl& previous, const QUrl& destination) {
        return !previous.isEmpty() && previous.isValid() && destination.isValid() &&
            previous.fragment() != destination.fragment() &&
            previous.adjusted(QUrl::RemoveFragment) == destination.adjusted(QUrl::RemoveFragment);
    }
    bool begin(Generation generation, const QUrl& frame, const QString& nonce) {
        invalidate(true);
        if (_exhausted || !generation || nonce.isEmpty()) { return false; }
        _generation = generation; _frame = frame; _nonce = nonce;
        return true;
    }
    void invalidate(bool preserveRecovery = false) {
        if (_epoch == std::numeric_limits<std::uint64_t>::max()) { _exhausted = true; }
        else { ++_epoch; }
        _generation = 0; _frame = QUrl(); _nonce.clear();
        if (!preserveRecovery) { _recoveringCache = false; }
    }
    void resetRecovery() { _recoveringCache = false; }
    Verification verify(Generation generation, std::uint64_t epoch, bool nonceMatches) {
        if (_exhausted || !generation || generation != _generation || epoch != _epoch) { return Verification::Stale; }
        if (nonceMatches) { _recoveringCache = false; return Verification::Ready; }
        if (_recoveringCache) { return Verification::Failed; }
        _recoveringCache = true;
        return Verification::Reload;
    }
    void redirected(const QUrl& frame) { if (_generation) { _frame = frame; } }
    bool accepts(Generation generation, const QString& nonce, const QUrl& frame, bool mainFrame) const {
        return !_exhausted && generation && generation == _generation && mainFrame &&
            !_nonce.isEmpty() && nonce == _nonce &&
            (web::EmbeddedWebSession::sameOrigin(_frame, frame) ||
             _frame.adjusted(QUrl::RemoveQuery | QUrl::RemoveFragment) ==
                 frame.adjusted(QUrl::RemoveQuery | QUrl::RemoveFragment));
    }
    std::uint64_t epoch() const { return _epoch; }
    const QString& nonce() const { return _nonce; }
private:
    Generation _generation { 0 };
    std::uint64_t _epoch { 0 };
    QUrl _frame;
    QString _nonce;
    bool _exhausted { false };
    bool _recoveringCache { false };
};
} // namespace overte::ios
