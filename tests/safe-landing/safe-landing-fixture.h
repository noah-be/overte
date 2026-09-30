// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0
// Lightweight entity/render fixtures; signal delivery and threads use real Qt.
#include <QCoreApplication>
#include <QDebug>
#include <QEvent>
#include <QObject>
#include <QSemaphore>
#include <QSharedPointer>
#include <atomic>
#include <cassert>
#include <cstdint>
#include <functional>
#include <limits>
#include <map>
#include <memory>
#include <mutex>
#include <set>
#include <thread>

struct EntityItemID {
    int value;
    EntityItemID(int id = 0) : value(id) {}
    bool operator<(const EntityItemID& other) const { return value < other.value; }
};
Q_DECLARE_METATYPE(EntityItemID)
using OCTREE_PACKET_SEQUENCE = uint16_t;
struct EntityItem {
    bool local = false;
    bool physicsReady = true;
    bool visualReady = true;
    bool isLocalEntity() const { return local; }
    quint64 getCreated() const { return 0; }
    bool getCollisionless() const { return false; }
    bool isVisuallyReady() const { return visualReady; }
    bool isParentPathComplete() const { return true; }
};
using EntityItemPointer = std::shared_ptr<EntityItem>;
using CalculateEntityLoadingPriority = std::function<float(const EntityItem&)>;
class EntityTree : public QObject {
    Q_OBJECT
public:
    EntityItemPointer entity = std::make_shared<EntityItem>();
    std::atomic<int> lookups { 0 };
    EntityItemPointer findEntityByID(const EntityItemID&) { ++lookups; return entity; }
signals:
    void addingEntity(const EntityItemID& id);
    void deletingEntity(const EntityItemID& id);
};
struct EntityTreeRenderer {
    std::shared_ptr<EntityTree> tree = std::make_shared<EntityTree>();
    std::shared_ptr<EntityTree> getTree() { return tree; }
    bool renderableForEntityId(const EntityItemID&) { return true; }
    void addingEntity(const EntityItemID&) {}
    static inline CalculateEntityLoadingPriority priority = [](const EntityItem&) { return 7.0f; };
    static auto getEntityLoadingPriorityOperator() { return priority; }
    static void setEntityLoadingPriorityFunction(CalculateEntityLoadingPriority fn) { priority = fn; }
};
struct Application {
    bool isMissingSequenceNumbers() { return true; }
} application;
#undef qApp
#define qApp (&application)
#define qCDebug(category) qDebug()
quint64 usecTimestampNow() { return 100; }
struct DomainHandler { bool enabled = true; bool getInterstitialModeEnabled() { return enabled; } };
struct NodeList { DomainHandler& getDomainHandler() { static DomainHandler d; return d; } };
struct DependencyManager {
    template<typename T> static std::shared_ptr<T> get() { static auto t = std::make_shared<T>(); return t; }
};

// The production lock is replaced only in this host harness to schedule the
// callback precisely at mutex entry. No production test hooks are required.
struct TestMutex {
    std::mutex mutex;
    static inline thread_local std::function<void()> beforeLock;
    void lock() { if (beforeLock) beforeLock(); mutex.lock(); }
    static inline thread_local std::function<void()> afterUnlock;
    void unlock() { mutex.unlock(); auto hook = afterUnlock; if (hook) hook(); }
};
