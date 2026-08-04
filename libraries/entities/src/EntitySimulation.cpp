//
//  EntitySimulation.cpp
//  libraries/entities/src
//
//  Created by Andrew Meadows on 2014.11.24
//  Copyright 2014 High Fidelity, Inc.
//
//  Distributed under the Apache License, Version 2.0.
//  See the accompanying file LICENSE or http://www.apache.org/licenses/LICENSE-2.0.html
//

#include "EntitySimulation.h"

#include <AACube.h>
#include <Profile.h>
#if defined(Q_OS_ANDROID)
#include <time.h>
#endif

#include "EntitiesLogging.h"
#include "MovingEntitiesOperator.h"

#if defined(Q_OS_ANDROID)
static uint64_t picoThreadCpuUsecs() {
    timespec time {};
    clock_gettime(CLOCK_THREAD_CPUTIME_ID, &time);
    return static_cast<uint64_t>(time.tv_sec) * USECS_PER_SECOND + time.tv_nsec / 1000;
}
#endif

void EntitySimulation::setEntityTree(EntityTreePointer tree) {
    if (_entityTree && _entityTree != tree) {
        _entitiesToSort.clear();
        _simpleKinematicEntities.clear();
#if defined(Q_OS_ANDROID)
        _androidKinematicCursor.reset();
#endif
        _changedEntities.clear();
        _entitiesToUpdate.clear();
        _mortalEntities.clear();
        _nextExpiry = std::numeric_limits<uint64_t>::max();
    }
    _entityTree = tree;
}

void EntitySimulation::updateEntities() {
    PerformanceTimer perfTimer("EntitySimulation::updateEntities");
    QMutexLocker lock(&_mutex);
    uint64_t now = usecTimestampNow();
#if defined(Q_OS_ANDROID)
    const uint64_t picoStart = now;
    const uint64_t picoCpuStart = picoThreadCpuUsecs();
#endif

    // these methods may accumulate entries in _entitiesToBeDeleted
    expireMortalEntities(now);
#if defined(Q_OS_ANDROID)
    const uint64_t picoAfterExpire = usecTimestampNow();
    const uint64_t picoCpuAfterExpire = picoThreadCpuUsecs();
#endif
    callUpdateOnEntitiesThatNeedIt(now);
#if defined(Q_OS_ANDROID)
    const uint64_t picoAfterCallUpdate = usecTimestampNow();
    const uint64_t picoCpuAfterCallUpdate = picoThreadCpuUsecs();
#endif
    moveSimpleKinematics(now);
#if defined(Q_OS_ANDROID)
    const uint64_t picoAfterKinematics = usecTimestampNow();
    const uint64_t picoCpuAfterKinematics = picoThreadCpuUsecs();
#endif
    sortEntitiesThatMoved();
#if defined(Q_OS_ANDROID)
    const uint64_t picoAfterSort = usecTimestampNow();
    const uint64_t picoCpuAfterSort = picoThreadCpuUsecs();
#endif
    processDeadEntities();
#if defined(Q_OS_ANDROID)
    const uint64_t picoEnd = usecTimestampNow();
    const uint64_t picoCpuEnd = picoThreadCpuUsecs();
    struct PicoSimulationStats {
        uint64_t windowStart { 0 };
        uint64_t calls { 0 };
        uint64_t expire { 0 };
        uint64_t callUpdate { 0 };
        uint64_t kinematics { 0 };
        uint64_t sort { 0 };
        uint64_t dead { 0 };
        uint64_t cpuExpire { 0 };
        uint64_t cpuCallUpdate { 0 };
        uint64_t cpuKinematics { 0 };
        uint64_t cpuSort { 0 };
        uint64_t cpuDead { 0 };
        uint64_t maximum { 0 };
    };
    static PicoSimulationStats stats;
    if (stats.windowStart == 0) {
        stats.windowStart = picoStart;
    }
    stats.calls++;
    stats.expire += picoAfterExpire - picoStart;
    stats.callUpdate += picoAfterCallUpdate - picoAfterExpire;
    stats.kinematics += picoAfterKinematics - picoAfterCallUpdate;
    stats.sort += picoAfterSort - picoAfterKinematics;
    stats.dead += picoEnd - picoAfterSort;
    stats.cpuExpire += picoCpuAfterExpire - picoCpuStart;
    stats.cpuCallUpdate += picoCpuAfterCallUpdate - picoCpuAfterExpire;
    stats.cpuKinematics += picoCpuAfterKinematics - picoCpuAfterCallUpdate;
    stats.cpuSort += picoCpuAfterSort - picoCpuAfterKinematics;
    stats.cpuDead += picoCpuEnd - picoCpuAfterSort;
    stats.maximum = std::max(stats.maximum, picoEnd - picoStart);
    if (picoEnd - stats.windowStart >= USECS_PER_SECOND) {
        const double divisor = std::max<uint64_t>(1, stats.calls);
        qInfo() << "PICO_ENTITY_SIM_STAGES"
                << "callsPerSec" << stats.calls
                << "maxMs" << stats.maximum / 1000.0
                << "expireMs" << stats.expire / divisor / 1000.0
                << "callUpdateMs" << stats.callUpdate / divisor / 1000.0
                << "kinematicsMs" << stats.kinematics / divisor / 1000.0
                << "sortMs" << stats.sort / divisor / 1000.0
                << "deadMs" << stats.dead / divisor / 1000.0
                << "cpuExpireMs" << stats.cpuExpire / divisor / 1000.0
                << "cpuCallUpdateMs" << stats.cpuCallUpdate / divisor / 1000.0
                << "cpuKinematicsMs" << stats.cpuKinematics / divisor / 1000.0
                << "cpuSortMs" << stats.cpuSort / divisor / 1000.0
                << "cpuDeadMs" << stats.cpuDead / divisor / 1000.0
                << "allEntities" << _allEntities.size()
                << "needsUpdate" << _entitiesToUpdate.size()
                << "kinematicEntities" << _simpleKinematicEntities.size()
                << "needsSort" << _entitiesToSort.size();
        stats = PicoSimulationStats {};
        stats.windowStart = picoEnd;
    }
#endif
}

void EntitySimulation::removeEntityFromInternalLists(EntityItemPointer entity) {
    // protected: _mutex lock is guaranteed
    // remove from all internal lists except _deadEntitiesToRemoveFromTree
    _entitiesToSort.remove(entity);
    _simpleKinematicEntities.remove(entity);
#if defined(Q_OS_ANDROID)
    if (_androidKinematicCursor == entity) {
        _androidKinematicCursor.reset();
    }
#endif
    _allEntities.remove(entity);
    _entitiesToUpdate.remove(entity);
    _mortalEntities.remove(entity);
    entity->setSimulated(false);
}

void EntitySimulation::prepareEntityForDelete(EntityItemPointer entity) {
    assert(entity);
    assert(entity->isDead());
    if (entity->isSimulated()) {
        QMutexLocker lock(&_mutex);
        removeEntityFromInternalLists(entity);
        if (entity->getElement()) {
            _deadEntitiesToRemoveFromTree.insert(entity);
            _entityTree->cleanupCloneIDs(entity->getEntityItemID());
        }
    }
}

// protected
void EntitySimulation::expireMortalEntities(uint64_t now) {
    if (now > _nextExpiry) {
        PROFILE_RANGE_EX(simulation_physics, "ExpireMortals", 0xffff00ff, (uint64_t)_mortalEntities.size());
        // only search for expired entities if we expect to find one
        _nextExpiry = std::numeric_limits<uint64_t>::max();
        QMutexLocker lock(&_mutex);
        SetOfEntities::iterator itemItr = _mortalEntities.begin();
        while (itemItr != _mortalEntities.end()) {
            EntityItemPointer entity = *itemItr;
            uint64_t expiry = entity->getExpiry();
            if (expiry < now) {
                itemItr = _mortalEntities.erase(itemItr);
                entity->die();
                prepareEntityForDelete(entity);
            } else {
                if (expiry < _nextExpiry) {
                    // remember the smallest _nextExpiry so we know when to start the next search
                    _nextExpiry = expiry;
                }
                ++itemItr;
            }
        }
        if (_mortalEntities.size() < 1) {
            _nextExpiry = -1;
        }
    }
}

// protected
void EntitySimulation::callUpdateOnEntitiesThatNeedIt(uint64_t now) {
    PerformanceTimer perfTimer("updatingEntities");
    QMutexLocker lock(&_mutex);
    SetOfEntities::iterator itemItr = _entitiesToUpdate.begin();
    while (itemItr != _entitiesToUpdate.end()) {
        EntityItemPointer entity = *itemItr;
        // TODO: catch transition from needing update to not as a "change"
        // so we don't have to scan for it here.
        if (!entity->needsToCallUpdate()) {
            itemItr = _entitiesToUpdate.erase(itemItr);
        } else {
            entity->update(now);
            ++itemItr;
        }
    }
}

// protected
void EntitySimulation::sortEntitiesThatMoved() {
    PROFILE_RANGE_EX(simulation_physics, "SortTree", 0xffff00ff, (uint64_t)_entitiesToSort.size());
    // NOTE: this is only for entities that have been moved by THIS EntitySimulation.
    // External changes to entity position/shape are expected to be sorted outside of the EntitySimulation.
    MovingEntitiesOperator moveOperator;
    AACube domainBounds(glm::vec3((float)-HALF_TREE_SCALE), (float)TREE_SCALE);
    SetOfEntities::iterator itemItr = _entitiesToSort.begin();
    while (itemItr != _entitiesToSort.end()) {
        EntityItemPointer entity = *itemItr;
        // check to see if this movement has sent the entity outside of the domain.
        bool success;
        AACube newCube = entity->getQueryAACube(success);
        if (success && !domainBounds.touches(newCube)) {
            qCDebug(entities) << "Entity " << entity->getEntityItemID() << " moved out of domain bounds.";
            itemItr = _entitiesToSort.erase(itemItr);
            entity->die();
            prepareEntityForDelete(entity);
        } else {
            moveOperator.addEntityToMoveList(entity, newCube);
            ++itemItr;
        }
    }
    if (moveOperator.hasMovingEntities()) {
        PerformanceTimer perfTimer("recurseTreeWithOperator");
        _entityTree->recurseTreeWithOperator(&moveOperator);
    }

    _entitiesToSort.clear();
}

void EntitySimulation::addEntityToInternalLists(EntityItemPointer entity) {
    // protected: _mutex lock is guaranteed
    if (entity->isMortal()) {
        _mortalEntities.insert(entity);
        uint64_t expiry = entity->getExpiry();
        if (expiry < _nextExpiry) {
            _nextExpiry = expiry;
        }
    }
    if (entity->needsToCallUpdate()) {
        _entitiesToUpdate.insert(entity);
    }
    _allEntities.insert(entity);
    entity->setSimulated(true);
}

void EntitySimulation::addEntity(EntityItemPointer entity) {
    QMutexLocker lock(&_mutex);
    assert(entity);
    addEntityToInternalLists(entity);

    // DirtyFlags are used to signal changes to entities that have already been added,
    // so we can clear them for this entity which has just been added.
    entity->clearDirtyFlags();
}

void EntitySimulation::changeEntity(EntityItemPointer entity) {
    QMutexLocker lock(&_mutex);
    assert(entity);
    _changedEntities.insert(entity);
}

void EntitySimulation::processChangedEntities() {
    QMutexLocker lock(&_mutex);
    PROFILE_RANGE_EX(simulation_physics, "processChangedEntities", 0xffff00ff, (uint64_t)_changedEntities.size());
    for (auto& entity : _changedEntities) {
        if (entity->isSimulated()) {
            processChangedEntity(entity);
        }
    }
    _changedEntities.clear();
}

void EntitySimulation::processChangedEntity(const EntityItemPointer& entity) {
    uint32_t dirtyFlags = entity->getDirtyFlags();

    if (dirtyFlags & (Simulation::DIRTY_LIFETIME | Simulation::DIRTY_UPDATEABLE)) {
        if (dirtyFlags & Simulation::DIRTY_LIFETIME) {
            if (entity->isMortal()) {
                _mortalEntities.insert(entity);
                uint64_t expiry = entity->getExpiry();
                if (expiry < _nextExpiry) {
                    _nextExpiry = expiry;
                }
            } else {
                _mortalEntities.remove(entity);
            }
        }
        if (dirtyFlags & Simulation::DIRTY_UPDATEABLE) {
            if (entity->needsToCallUpdate()) {
                _entitiesToUpdate.insert(entity);
            } else {
                _entitiesToUpdate.remove(entity);
            }
        }
        entity->clearDirtyFlags(Simulation::DIRTY_LIFETIME | Simulation::DIRTY_UPDATEABLE);
    }
}

void EntitySimulation::clearEntities() {
    QMutexLocker lock(&_mutex);
    _entitiesToSort.clear();
    _simpleKinematicEntities.clear();
#if defined(Q_OS_ANDROID)
    _androidKinematicCursor.reset();
#endif
    _changedEntities.clear();
    _allEntities.clear();
    _deadEntitiesToRemoveFromTree.clear();
    _entitiesToUpdate.clear();
    _mortalEntities.clear();
    _nextExpiry = std::numeric_limits<uint64_t>::max();
}

void EntitySimulation::moveSimpleKinematics(uint64_t now) {
    PROFILE_RANGE_EX(simulation_physics, "MoveSimples", 0xffff00ff, (uint64_t)_simpleKinematicEntities.size());
    SetOfEntities::iterator itemItr = _simpleKinematicEntities.begin();
#if defined(Q_OS_ANDROID)
    // A large group of cheap-looking kinematic entities can collectively hold
    // the application thread for tens of milliseconds. Process them round-robin
    // within a small per-update budget. EntityItem::simulate() uses its last
    // simulation timestamp, so an entity catches up correctly when revisited.
    // As the application update rate recovers, every entity is still refreshed
    // many times per second.
    static const uint64_t ANDROID_KINEMATIC_BUDGET_USECS = 4000;
    static const size_t ANDROID_KINEMATIC_MAX_PER_UPDATE = 2;
    const uint64_t budgetStart = usecTimestampNow();
    size_t entitiesRemaining = _simpleKinematicEntities.size();
    size_t entitiesProcessed = 0;
    if (_androidKinematicCursor) {
        auto cursorItr = _simpleKinematicEntities.find(_androidKinematicCursor);
        if (cursorItr != _simpleKinematicEntities.end()) {
            itemItr = cursorItr;
            ++itemItr;
            if (itemItr == _simpleKinematicEntities.end()) {
                itemItr = _simpleKinematicEntities.begin();
            }
        }
    }
#endif
    while (itemItr != _simpleKinematicEntities.end()) {
        EntityItemPointer entity = *itemItr;

        // The entity-server doesn't know where avatars are, so don't attempt to do simple extrapolation for
        // children of avatars.  See related code in EntityMotionState::remoteSimulationOutOfSync.
        bool ancestryIsKnown;
        entity->getMaximumAACube(ancestryIsKnown);
        bool hasAvatarAncestor = entity->hasAncestorOfType(NestableType::Avatar);

        bool isMoving = entity->isMovingRelativeToParent();
        if (isMoving && !entity->getPhysicsInfo() && ancestryIsKnown && !hasAvatarAncestor) {
            entity->simulate(now);
            if (ancestryIsKnown && !hasAvatarAncestor) {
                entity->updateQueryAACube();
            }
            _entitiesToSort.insert(entity);
            ++itemItr;
        } else {
            if (!isMoving && ancestryIsKnown && !hasAvatarAncestor) {
                // HACK: This catches most cases where the entity's QueryAACube (and spatial sorting in the EntityTree)
                // would otherwise be out of date at conclusion of its "unowned" simpleKinematicMotion.
                entity->updateQueryAACube();
                _entitiesToSort.insert(entity);
            }
            // the entity is no longer non-physical-kinematic
            itemItr = _simpleKinematicEntities.erase(itemItr);
        }
#if defined(Q_OS_ANDROID)
        _androidKinematicCursor = entity;
        ++entitiesProcessed;
        if (itemItr == _simpleKinematicEntities.end() && !_simpleKinematicEntities.empty()) {
            itemItr = _simpleKinematicEntities.begin();
        }
        if (--entitiesRemaining == 0 ||
                entitiesProcessed >= ANDROID_KINEMATIC_MAX_PER_UPDATE ||
                usecTimestampNow() - budgetStart >= ANDROID_KINEMATIC_BUDGET_USECS) {
            break;
        }
#endif
    }
}

void EntitySimulation::processDeadEntities() {
    if (_deadEntitiesToRemoveFromTree.empty()) {
        return;
    }
    std::vector<EntityItemPointer> entitiesToDeleteImmediately;
    entitiesToDeleteImmediately.reserve(_deadEntitiesToRemoveFromTree.size());
    QUuid nullSessionID;
    foreach (auto entity, _deadEntitiesToRemoveFromTree) {
        entitiesToDeleteImmediately.push_back(entity);
        entity->collectChildrenForDelete(entitiesToDeleteImmediately, nullSessionID);
    }
    if (_entityTree) {
        _entityTree->deleteEntitiesByPointer(entitiesToDeleteImmediately);
    }
    _deadEntitiesToRemoveFromTree.clear();
}
