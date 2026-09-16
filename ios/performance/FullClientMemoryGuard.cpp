// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0
#include "FullClientMemoryGuard.h"
#include "MemoryPressurePolicy.h"
#include "MemoryWarningHandler.h"
#include <ResourceCache.h>
#include <QGuiApplication>
#include <QPointer>
#include <QTimer>
#include <QThread>
#include <algorithm>
#include <vector>
#if defined(Q_OS_IOS)
#include <os/log.h>
#endif
namespace overte::ios {
namespace {
class MemoryGuard final : public QObject {
public:
    MemoryGuard(QObject* lifetime, std::initializer_list<MemoryCacheBudget> caches) : QObject(lifetime) {
        for (const auto& cache : caches) {
            if (cache.cache) { _caches.push_back({cache.cache, cache.bytes}); }
        }
        _normalRequests = std::min(uint32_t(2), ResourceCache::getRequestLimit());
        ResourceCache::setRequestLimit(_normalRequests);
        applyBudgets(false);
        _timer.setParent(this);
        _timer.setObjectName(QStringLiteral("iosMemoryPressureTimer"));
        _timer.setInterval(1000);
        _timer.setTimerType(Qt::CoarseTimer);
        connect(&_timer, &QTimer::timeout, this, [this] { sample(false); });
        if (auto* gui = qobject_cast<QGuiApplication*>(QCoreApplication::instance())) {
            connect(gui, &QGuiApplication::applicationStateChanged, this,
                [this](Qt::ApplicationState state) {
                    if (state == Qt::ApplicationActive) { sample(false); _timer.start(); }
                    else { _timer.stop(); }
                });
        }
        installMemoryWarningHandler(this, [this] { sample(true); });
        // Startup is always checked, even before the foreground notification.
        sample(false);
        if (QGuiApplication::applicationState() == Qt::ApplicationActive) { _timer.start(); }
    }
private:
    struct Cache { QPointer<ResourceCache> pointer; std::uint64_t budget; };
    std::vector<Cache> _caches;
    QTimer _timer;
    MemoryPressurePolicy _policy;
    MemoryPressureLevel _applied { MemoryPressureLevel::Normal };
    uint32_t _normalRequests { 2 };
    unsigned _samples { 0 };
    void applyBudgets(bool pressured) {
        unsigned index = 0;
        for (const auto& entry : _caches) {
            const auto cacheIndex = index++;
            auto cache = entry.pointer;
            if (!cache) { continue; }
            const auto budget = pressured ? uint64_t(0) : entry.budget;
            // Resource destruction and LRU mutations run on the cache owner.
            // The context suppresses queued work if shutdown deletes the cache.
            QMetaObject::invokeMethod(cache.data(), [cache, budget, cacheIndex] {
                if (!cache) { return; }
#if defined(Q_OS_IOS)
                const auto before = cache->getSizeCachedResources();
#endif
                cache->setUnusedResourceCacheSize(static_cast<qint64>(budget));
#if defined(Q_OS_IOS)
                os_log_info(OS_LOG_DEFAULT,
                    "OVT_IOS_MEMORY_CACHE_V1 cache=%{public}u budget=%{public}llu "
                    "accountedBefore=%{public}llu accountedAfter=%{public}llu totalAccounted=%{public}llu",
                    cacheIndex, static_cast<unsigned long long>(budget),
                    static_cast<unsigned long long>(before),
                    static_cast<unsigned long long>(cache->getSizeCachedResources()),
                    static_cast<unsigned long long>(cache->getSizeTotalResources()));
#else
                (void)cacheIndex;
#endif
            }, Qt::QueuedConnection);
        }
    }
    void sample(bool warning) {
        Q_ASSERT(QThread::currentThread() == thread());
        auto metrics = sampleAvailableMemory();
        if (!metrics.availableMemoryAvailable) { metrics = sampleNativeMetrics(); }
        const auto decision = _policy.update(metrics, warning);
        const bool changed = decision.level != _applied;
        if (decision.purgeUnused || changed) {
            applyBudgets(decision.level != MemoryPressureLevel::Normal);
        }
        const uint32_t desired = decision.level == MemoryPressureLevel::Critical ? 0 :
            decision.level == MemoryPressureLevel::Warning ? std::min(_normalRequests, uint32_t(1)) : _normalRequests;
        if (ResourceCache::getRequestLimit() != desired) {
            // The existing scheduler queues excess requests and drains that same
            // queue on recovery. Active requests/decodes are not cancelled.
            ResourceCache::setRequestLimit(desired);
        }
        _applied = decision.level;
#if defined(Q_OS_IOS)
        if (warning || changed || ++_samples % 5 == 0) {
            os_log_info(OS_LOG_DEFAULT,
                "OVT_IOS_MEMORY_PRESSURE_V1 availableKnown=%{public}d availableBytes=%{public}llu "
                "level=%{public}d requestLimit=%{public}u loading=%{public}u pending=%{public}u purge=%{public}d",
                int(metrics.availableMemoryAvailable), static_cast<unsigned long long>(metrics.availableMemoryBytes),
                int(decision.level), desired, ResourceCache::getLoadingRequestCount(),
                ResourceCache::getPendingRequestCount(), int(decision.purgeUnused));
        }
#endif
    }
};
}
void installFullClientMemoryGuard(QObject* lifetime, std::initializer_list<MemoryCacheBudget> caches) {
    Q_ASSERT(lifetime && QThread::currentThread() == lifetime->thread());
    new MemoryGuard(lifetime, caches);
}
}
