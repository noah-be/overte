// SPDX-License-Identifier: Apache-2.0
#pragma once

#include <QString>
#include <QUuid>
#include <atomic>
#include <memory>
#include <utility>
#include <functional>
#include <mutex>
#include <vector>

// Native-only session identity. A renderer must retire its managers when it
// invalidates this scope; invalidation alone does not abort entered native code.
class EntityScriptConsentScope {
public:
    explicit EntityScriptConsentScope(QString origin) : _origin(std::move(origin)) {}
    const QString& origin() const { return _origin; }
    const QUuid& identity() const { return _identity; }
    bool active() const { return _active.load(std::memory_order_acquire); }
    ~EntityScriptConsentScope() { invalidate(); }
    void invalidate() {
        if (!_active.exchange(false, std::memory_order_acq_rel)) { return; }
        std::vector<std::function<void()>> callbacks;
        { std::lock_guard<std::mutex> guard(_mutex); callbacks.swap(_onInvalidated); }
        // Stop hooks run without the scope lock and do not wait for a renderer
        // event loop. ScriptManager::stop provides cross-thread VM interruption.
        for (const auto& callback : callbacks) { callback(); }
    }
private:
    friend class ScriptManager;
    friend class ScriptCache;
    void onInvalidated(std::function<void()> callback) {
        {
            std::lock_guard<std::mutex> guard(_mutex);
            if (active()) { _onInvalidated.push_back(std::move(callback)); return; }
        }
        callback();
    }
    std::mutex _mutex;
    std::vector<std::function<void()>> _onInvalidated;
    const QString _origin;
    const QUuid _identity { QUuid::createUuid() };
    std::atomic<bool> _active { true };
};

class EntityScriptConsentRequest {
public:
    enum class Decision { Pending, Allowed, Declined };
    EntityScriptConsentRequest(std::shared_ptr<EntityScriptConsentScope> scope, QString source, bool forceRedownload)
        : _scope(std::move(scope)), _source(std::move(source)), _forceRedownload(forceRedownload) {}
    const QString& source() const { return _source; }
    const QString& origin() const { return _scope->origin(); }
    bool active() const { return _active.load(std::memory_order_acquire) && _scope && _scope->active(); }
    bool belongsTo(const std::shared_ptr<EntityScriptConsentScope>& scope) const { return _scope == scope; }
    bool allowed() const { return active() && _decision.load(std::memory_order_acquire) == Decision::Allowed; }
    Decision decision() const { return _decision.load(std::memory_order_acquire); }
private:
    friend class ScriptManager;
    void invalidate() { _active.store(false, std::memory_order_release); }
    bool resolve(bool allow) {
        if (!active()) { return false; }
        auto pending = Decision::Pending;
        return _decision.compare_exchange_strong(pending, allow ? Decision::Allowed : Decision::Declined);
    }
    const std::shared_ptr<EntityScriptConsentScope> _scope;
    const QString _source;
    std::atomic<Decision> _decision { Decision::Pending };
    std::atomic<bool> _active { true };
    bool _forceRedownload { false }; // owning ScriptManager thread only
};
