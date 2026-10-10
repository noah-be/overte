// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0
#include <QCoreApplication>
#include <QDateTime>
#include <QHash>
#include <QReadWriteLock>
#include <QThread>
#include <cassert>
#include <memory>
#include <thread>
#include <vector>

using EntityItemID = int;
static thread_local int scopeDepth = 0;
struct Engine {
    struct Guard { Guard() { ++scopeDepth; } ~Guard() { --scopeDepth; } };
    auto getScopeGuard() { return std::make_unique<Guard>(); }
};
struct ScriptValue {
    ScriptValue() = default;
    ScriptValue(const ScriptValue&) { assert(scopeDepth > 0 && "ScriptValue copy without engine scope"); }
    ScriptValue& operator=(const ScriptValue&) { assert(scopeDepth > 0); return *this; }
};
enum class EntityScriptStatus { RUNNING, UNLOADED };
struct EntityScriptDetails {
    ScriptValue value;
    QString scriptText;
    EntityScriptStatus status { EntityScriptStatus::RUNNING };
    qint64 lastModified { 0 };
};
struct Consent { void invalidate() {} };
struct ScriptManager : QObject, std::enable_shared_from_this<ScriptManager> {
    std::shared_ptr<Engine> _engine = std::make_shared<Engine>();
    QHash<int, QHash<QString, std::shared_ptr<Consent>>> _entityScriptConsentRequests;
    QHash<int, int> _entityScriptLoads, _contentAvailableQueue;
    QHash<int, QHash<QString, EntityScriptDetails>> _entityScripts;
    QReadWriteLock _entityScriptsLock;
    int unloadCalls = 0, timersStopped = 0, updates = 0;
    void unloadEntityScript(const EntityItemID&, const QString&, bool);
    void unloadAllEntityScriptsForEntity(const EntityItemID&, bool);
    void unloadAllEntityScripts(bool);
    void cancelEntityScriptLoad(int, const QString&) {}
    bool getEntityScriptDetails(int id, const QString& url, EntityScriptDetails& out) {
        if (!_entityScripts.contains(id) || !_entityScripts[id].contains(url)) return false;
        out = _entityScripts[id][url]; return true;
    }
    bool isEntityScriptRunning(int id, const QString& url) {
        return _entityScripts[id][url].status == EntityScriptStatus::RUNNING;
    }
    void callEntityScriptMethodForScript(int, const QString&, const char*) { assert(scopeDepth > 0); ++unloadCalls; }
    void setEntityScriptDetails(int id, const QString& url, const EntityScriptDetails& details) {
        _entityScripts[id][url] = details;
    }
    void entityScriptDetailsUpdated() { ++updates; }
    void stopAllTimersForEntityScript(int) { ++timersStopped; }
};
#include "unload.inc"
int main(int argc, char** argv) {
    QCoreApplication app(argc, argv);
    assert(argc == 3);
    auto manager = std::make_shared<ScriptManager>();
    {
        // The run() scope has ended before a queued domain/background cleanup.
        auto previousRun = manager->_engine->getScopeGuard();
        EntityScriptDetails details; details.scriptText = "test-script";
        manager->_entityScripts[1].insert(details.scriptText, details);
        manager->_entityScriptConsentRequests[1].insert(details.scriptText, std::make_shared<Consent>());
    }
    assert(scopeDepth == 0);
    const QString entry(argv[1]), delivery(argv[2]);
    auto unload = [&] {
        if (entry == "single") manager->unloadEntityScript(1, "test-script", true);
        else if (entry == "entity") manager->unloadAllEntityScriptsForEntity(1, true);
        else manager->unloadAllEntityScripts(false);
    };
    if (delivery == "queued") {
        std::thread caller(unload); caller.join();
        assert(manager->unloadCalls == 0);
        QCoreApplication::sendPostedEvents();
    } else if (delivery == "nested") {
        auto existingRun = manager->_engine->getScopeGuard(); unload();
        assert(scopeDepth == 1);
    } else unload();
    assert(scopeDepth == 0);
    assert(manager->_entityScripts.isEmpty());
    assert(manager->_entityScriptConsentRequests.isEmpty());
    assert(manager->unloadCalls == 1 && manager->timersStopped == 1 && manager->updates >= 1);
}
