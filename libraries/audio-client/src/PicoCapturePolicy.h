// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <atomic>
#include <cstdint>
#include <limits>
namespace overte { namespace audio {
// Native visibility/permission/mute policy, not proof AudioRecord is running.
// Token zero/default is deny. Stale PCM from an earlier permission epoch fails.
class PicoCapturePolicy {
public:
    bool change(bool allowed) {
        auto previous = _state.load(std::memory_order_acquire);
        for (;;) {
            if (static_cast<bool>(previous & 1) == allowed) { return false; }
            auto next = previous > std::numeric_limits<std::uint64_t>::max() - 3
                ? std::numeric_limits<std::uint64_t>::max() - 1
                : ((previous + 2) & ~std::uint64_t(1)) | std::uint64_t(allowed);
            if (_state.compare_exchange_weak(previous, next, std::memory_order_acq_rel)) { return true; }
        }
    }
    std::uint64_t ticket() const { return _state.load(std::memory_order_acquire); }
    bool allows() const { return (ticket() & 1) != 0; }
    bool accepts(std::uint64_t token) const { return (token & 1) && token == ticket(); }
private:
    std::atomic<std::uint64_t> _state { 0 };
};
} }
