// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "NativeMetrics.h"

namespace overte::ios {
enum class MemoryPressureLevel { Normal, Warning, Critical };
struct MemoryPressureDecision {
    MemoryPressureLevel level { MemoryPressureLevel::Normal };
    bool purgeUnused { false };
    bool limitDownloads { false };
};

// This is an early best-effort pressure controller, not an allocation quota.
// Sample once per second while foreground. UIKit warnings must also call update.
// Hysteresis avoids continually rebuilding caches near a threshold. Failed
// samples never release an existing restriction. The footprint fallback is
// conservative and applies only when native process headroom is unavailable.
class MemoryPressurePolicy {
public:
    static constexpr std::uint64_t MIB = 1024ULL * 1024ULL;
    static constexpr std::uint64_t WARNING_HEADROOM = 512 * MIB;
    static constexpr std::uint64_t CRITICAL_HEADROOM = 256 * MIB;
    static constexpr std::uint64_t RECOVERY_HEADROOM = 768 * MIB;

    MemoryPressureDecision update(const NativeMetrics& metrics, bool nativeWarning = false) noexcept {
        auto observed = _level;
        bool recovered = false;
        if (metrics.availableMemoryAvailable) {
            observed = metrics.availableMemoryBytes <= CRITICAL_HEADROOM ? MemoryPressureLevel::Critical :
                metrics.availableMemoryBytes <= WARNING_HEADROOM ? MemoryPressureLevel::Warning : MemoryPressureLevel::Normal;
            recovered = metrics.availableMemoryBytes >= RECOVERY_HEADROOM;
        } else if (metrics.footprintAvailable && metrics.footprintBytes != 0) {
            observed = metrics.footprintBytes >= 2048 * MIB ? MemoryPressureLevel::Critical :
                metrics.footprintBytes >= 1792 * MIB ? MemoryPressureLevel::Warning : MemoryPressureLevel::Normal;
            recovered = metrics.footprintBytes < 1536 * MIB;
        }
        if (nativeWarning) {
            observed = MemoryPressureLevel::Critical;
            recovered = false;
        }
        bool purge = false;
        if (static_cast<int>(observed) > static_cast<int>(_level)) {
            _level = observed;
            purge = true;
        } else if (_level != MemoryPressureLevel::Normal && recovered) {
            if (++_recoverySamples >= 3) {
                _level = MemoryPressureLevel::Normal;
                _recoverySamples = 0;
            }
        }
        if (!recovered) { _recoverySamples = 0; }
        // A real warning can arrive after new unused resources accumulated.
        // OS callbacks are explicit events; timer samples alone cannot flood
        // eviction work while memory is owned by active scene resources.
        purge = purge || nativeWarning;
        return { _level, purge, _level != MemoryPressureLevel::Normal };
    }

private:
    MemoryPressureLevel _level { MemoryPressureLevel::Normal };
    unsigned _recoverySamples { 0 };
};
} // namespace overte::ios
