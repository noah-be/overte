#pragma once

#if defined(ANDROID_APP_PHONE_INTERFACE)
#include <QThreadPool>
#include <QRunnable>
#include <atomic>
#include <functional>
#include <mutex>

// Short cache probes must not wait for full image encodes. Admission and stop
// share a lock; draining never holds it or processes owner-thread callbacks.
class PhoneKtxProbePool {
public:
    PhoneKtxProbePool() { _pool.setMaxThreadCount(1); }
    ~PhoneKtxProbePool() { stop(); }

    bool start(std::function<void()> work) {
        std::lock_guard<std::mutex> lock(_mutex);
        if (_stopping.load()) {
            return false;
        }
        _pool.start(QRunnable::create(std::move(work)));
        return true;
    }

    bool isStopping() const { return _stopping.load(); }

    void stop() {
        {
            std::lock_guard<std::mutex> lock(_mutex);
            _stopping.store(true);
        }
        // Execute accepted work so its processing counters can be balanced.
        _pool.waitForDone();
    }

private:
    std::mutex _mutex;
    std::atomic<bool> _stopping { false };
    QThreadPool _pool;
};

// Called before DependencyManager teardown, not only at static destruction.
void stopPhoneKtxHeaderProbes();
#endif
