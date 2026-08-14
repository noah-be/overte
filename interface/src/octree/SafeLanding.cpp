//
//  SafeLanding.cpp
//  interface/src/octree
//
//  Created by Simon Walton.
//  Copyright 2018 High Fidelity, Inc.
//
//  Distributed under the Apache License, Version 2.0.
//  See the accompanying file LICENSE or http://www.apache.org/licenses/LICENSE-2.0.html
//

#include "SafeLanding.h"
#include <SharedUtil.h>

#include "EntityTreeRenderer.h"
#include "EntitySchedulingPolicy.h"
#include "RenderableModelEntityItem.h"
#include "InterfaceLogging.h"
#include "Application.h"


CalculateEntityLoadingPriority SafeLanding::entityLoadingOperatorElevateCollidables = [](const EntityItem& entityItem) {
    return EntitySchedulingPolicy::safeLandingLoadPriority(entityItem.getCollisionless());
};

namespace {
    template<typename T> bool lessThanWraparound(int32_t a, int32_t b) {
        constexpr int32_t MAX_T_VALUE = std::numeric_limits<T>::max();
        if (b <= a) {
            b += MAX_T_VALUE;
        }
        return (b - a) < (MAX_T_VALUE / 2);
    }
}

bool SafeLanding::SequenceLessThan::operator()(const OCTREE_PACKET_SEQUENCE& a, const OCTREE_PACKET_SEQUENCE& b) const {
    return lessThanWraparound<OCTREE_PACKET_SEQUENCE>(a, b);
}

void SafeLanding::startTracking(QSharedPointer<EntityTreeRenderer> entityTreeRenderer) {
    if (!entityTreeRenderer.isNull()) {
        auto entityTree = entityTreeRenderer->getTree();
        if (entityTree && !_trackingEntities) {
            Locker lock(_lock);
            _entityTreeRenderer = entityTreeRenderer;
            _trackedEntities.clear();
            _maxTrackedEntityCount = 0;
            _sequenceStart = SafeLanding::INVALID_SEQUENCE;
            _sequenceEnd = SafeLanding::INVALID_SEQUENCE;
            _sequenceNumbers.clear();
            _trackingEntities = true;
            _startTime = usecTimestampNow();

            connect(std::const_pointer_cast<EntityTree>(entityTree).get(),
                &EntityTree::addingEntity, this, &SafeLanding::addTrackedEntity, Qt::DirectConnection);
            connect(std::const_pointer_cast<EntityTree>(entityTree).get(),
                &EntityTree::deletingEntity, this, &SafeLanding::deleteTrackedEntity);

            _prevEntityLoadingPriorityOperator = EntityTreeRenderer::getEntityLoadingPriorityOperator();
            EntityTreeRenderer::setEntityLoadingPriorityFunction(entityLoadingOperatorElevateCollidables);
        }
    }
}

void SafeLanding::addTrackedEntity(const EntityItemID& entityID) {
    if (_trackingEntities && _entityTreeRenderer) {
        Locker lock(_lock);
        auto entityTree = _entityTreeRenderer->getTree();
        if (entityTree) {
            EntityItemPointer entity = entityTree->findEntityByID(entityID);
            if (entity && !entity->isLocalEntity() && entity->getCreated() < _startTime) {
                _trackedEntities.emplace(entityID, entity);

                int32_t trackedEntityCount = (int32_t)_trackedEntities.size();
                if (trackedEntityCount > _maxTrackedEntityCount) {
                    _maxTrackedEntityCount = trackedEntityCount;
                    _trackedEntityStabilityCount = 0;
                }
            }
        }
    }
}

void SafeLanding::deleteTrackedEntity(const EntityItemID& entityID) {
    Locker lock(_lock);
    _trackedEntities.erase(entityID);
}

void SafeLanding::finishSequence(OCTREE_PACKET_SEQUENCE first, OCTREE_PACKET_SEQUENCE last) {
    Locker lock(_lock);
    if (_trackingEntities && _sequenceStart == SafeLanding::INVALID_SEQUENCE) {
        // An empty initial scene has no first entity packet. Represent it
        // as a zero-length sequence so Safe Landing can still complete.
        _sequenceStart = first == SafeLanding::INVALID_SEQUENCE ? last : first;
        _sequenceEnd = last;
    }
}

void SafeLanding::addToSequence(OCTREE_PACKET_SEQUENCE sequenceNumber) {
    Locker lock(_lock);
    _sequenceNumbers.insert(sequenceNumber);
}

void SafeLanding::updateTracking() {
    if (!_trackingEntities || !_entityTreeRenderer) {
        return;
    }

    {
        Locker lock(_lock);
#if defined(ANDROID_APP_PICO_INTERFACE)
        // On Pico the interstitial must only cover the playable handoff.  Visual assets may continue
        // streaming after the user can move; blocking safe landing on model/texture readiness caused
        // the loading screen to enter an endless "missing entities" recovery loop.
        constexpr bool requireVisualReadiness = false;
#else
        const bool enableInterstitial = DependencyManager::get<NodeList>()->getDomainHandler().getInterstitialModeEnabled();
        const bool requireVisualReadiness = enableInterstitial;
#endif
        auto entityMapIter = _trackedEntities.begin();
        while (entityMapIter != _trackedEntities.end()) {
            auto entity = entityMapIter->second;
            bool isVisuallyReady = true;
            if (requireVisualReadiness) {
                auto entityRenderable = _entityTreeRenderer->renderableForEntityId(entityMapIter->first);
                if (!entityRenderable) {
                    _entityTreeRenderer->addingEntity(entityMapIter->first);
                }
                isVisuallyReady = entity->isVisuallyReady() || (!entityRenderable && !entity->isParentPathComplete());
            }
            if (isEntityPhysicsReady(entity) && isVisuallyReady) {
                entityMapIter = _trackedEntities.erase(entityMapIter);
            } else {
                entityMapIter++;
            }
        }
        if (requireVisualReadiness) {
            _trackedEntityStabilityCount++;
        }
    }

    if (_trackedEntities.empty()) {
        // no more tracked entities --> check sequenceNumbers
        if (_sequenceStart != SafeLanding::INVALID_SEQUENCE) {
            bool shouldStop = false;
            {
                Locker lock(_lock);
                auto sequenceSize = _sequenceEnd - _sequenceStart; // this works even in rollover case
                auto startIter = _sequenceNumbers.find(_sequenceStart);
                auto endIter = _sequenceNumbers.find(_sequenceEnd - 1);

                bool missingSequenceNumbers = qApp->isMissingSequenceNumbers();
                shouldStop = (sequenceSize == 0 ||
                    (startIter != _sequenceNumbers.end() &&
                     endIter != _sequenceNumbers.end() &&
                     ((distance(startIter, endIter) == sequenceSize - 1) || !missingSequenceNumbers)));
            }
            if (shouldStop) {
                stopTracking();
            }
        }
    }
}

void SafeLanding::stopTracking() {
    Locker lock(_lock);
    if (_trackingEntities) {
        _trackingEntities = false;
        if (_entityTreeRenderer) {
            auto entityTree = _entityTreeRenderer->getTree();
            disconnect(std::const_pointer_cast<EntityTree>(entityTree).get(),
                &EntityTree::addingEntity, this, &SafeLanding::addTrackedEntity);
            disconnect(std::const_pointer_cast<EntityTree>(entityTree).get(),
                &EntityTree::deletingEntity, this, &SafeLanding::deleteTrackedEntity);
            _entityTreeRenderer.reset();
        }
        EntityTreeRenderer::setEntityLoadingPriorityFunction(_prevEntityLoadingPriorityOperator);
    }
}

void SafeLanding::reset() {
    _trackingEntities = false;
    _trackedEntities.clear();
    _maxTrackedEntityCount = 0;
    _sequenceStart = SafeLanding::INVALID_SEQUENCE;
    _sequenceEnd = SafeLanding::INVALID_SEQUENCE;
}

void SafeLanding::restartSequenceTracking() {
    Locker lock(_lock);
    if (_trackingEntities) {
        _sequenceStart = SafeLanding::INVALID_SEQUENCE;
        _sequenceEnd = SafeLanding::INVALID_SEQUENCE;
        _sequenceNumbers.clear();
    }
}

bool SafeLanding::trackingIsComplete() const {
    return !_trackingEntities && (_sequenceStart != SafeLanding::INVALID_SEQUENCE);
}

float SafeLanding::loadingProgressPercentage() {
    Locker lock(_lock);

    float entityReadyPercentage = 0.0f;
    if (_maxTrackedEntityCount > 0) {
        entityReadyPercentage = ((_maxTrackedEntityCount - _trackedEntities.size()) / (float)_maxTrackedEntityCount);
    }

    constexpr int32_t MINIMUM_TRACKED_ENTITY_STABILITY_COUNT = 15;
    if (_trackedEntityStabilityCount < MINIMUM_TRACKED_ENTITY_STABILITY_COUNT) {
        entityReadyPercentage *= 0.20f;
    }

    return entityReadyPercentage;
}

SafeLanding::LoadingStatus SafeLanding::loadingStatus() {
    Locker lock(_lock);

    LoadingStatus status;
    status.trackedEntityCount = static_cast<int32_t>(_trackedEntities.size());
    status.maximumTrackedEntityCount = _maxTrackedEntityCount;
    if (_entityTreeRenderer) {
#if defined(ANDROID_APP_PICO_INTERFACE)
        constexpr bool requireVisualReadiness = false;
#else
        const bool requireVisualReadiness =
            DependencyManager::get<NodeList>()->getDomainHandler().getInterstitialModeEnabled();
#endif
        for (const auto& trackedEntity : _trackedEntities) {
            const auto& entity = trackedEntity.second;
            if (!isEntityPhysicsReady(entity)) {
                ++status.physicsBlockedEntityCount;
            }
            if (requireVisualReadiness) {
                const auto entityRenderable = _entityTreeRenderer->renderableForEntityId(trackedEntity.first);
                const bool isVisuallyReady = entity->isVisuallyReady() ||
                    (!entityRenderable && !entity->isParentPathComplete());
                if (!isVisuallyReady) {
                    ++status.visuallyBlockedEntityCount;
                }
            }
        }
    }
    status.completionReceived = _sequenceStart != SafeLanding::INVALID_SEQUENCE;
    if (status.completionReceived) {
        status.expectedSequenceCount = static_cast<uint32_t>(_sequenceEnd - _sequenceStart);
        for (uint32_t offset = 0; offset < status.expectedSequenceCount; ++offset) {
            const auto sequence = static_cast<OCTREE_PACKET_SEQUENCE>(_sequenceStart + offset);
            if (_sequenceNumbers.find(sequence) != _sequenceNumbers.end()) {
                ++status.receivedSequenceCount;
            }
        }
    } else {
        status.receivedSequenceCount = static_cast<uint32_t>(_sequenceNumbers.size());
    }
    return status;
}

bool SafeLanding::isEntityPhysicsReady(const EntityItemPointer& entity) {
    if (entity && !entity->getCollisionless()) {
        const auto& entityType = entity->getType();
        if (entityType == EntityTypes::Model) {
            RenderableModelEntityItem * modelEntity = std::dynamic_pointer_cast<RenderableModelEntityItem>(entity).get();
            static const std::set<ShapeType> downloadedCollisionTypes
                { SHAPE_TYPE_COMPOUND, SHAPE_TYPE_SIMPLE_COMPOUND, SHAPE_TYPE_STATIC_MESH,  SHAPE_TYPE_SIMPLE_HULL };
            bool hasAABox;
            entity->getAABox(hasAABox);
            if (hasAABox && downloadedCollisionTypes.count(modelEntity->getShapeType()) != 0) {
                auto space = _entityTreeRenderer->getWorkloadSpace();
                uint8_t region = space ? space->getRegion(entity->getSpaceIndex()) : (uint8_t)workload::Region::INVALID;

                // Note: the meanings of the workload regions are:
                //   R1 = in physics simulation and willing to own simulation
                //   R2 = in physics simulation but does NOT want to own simulation
                //   R3 = not in physics simulation but kinematically animated when velocities are non-zero
                //   R4 = sorted by workload and found to be outside R3
                //   UNKNOWN = known to workload but not yet sorted
                //   INVALID = not known to workload
                // So any entity sorted into R3 or R4 is definitelyNotPhysical

                bool definitelyNotPhysical = region == workload::Region::R3 ||
                    region == workload::Region::R4 ||
                    !entity->shouldBePhysical() ||
                    modelEntity->unableToLoadCollisionShape();
                bool definitelyPhysical = entity->isInPhysicsSimulation();
                return definitelyNotPhysical || definitelyPhysical;
            }
        }
    }
    return true;
}

void SafeLanding::debugDumpSequenceIDs() const {
    qCDebug(interfaceapp) << "Sequence set size:" << _sequenceNumbers.size();

    auto itr = _sequenceNumbers.begin();
    OCTREE_PACKET_SEQUENCE p = SafeLanding::INVALID_SEQUENCE;
    if (itr != _sequenceNumbers.end()) {
        p = (*itr);
        qCDebug(interfaceapp) << "First:" << (int32_t)p;
        ++itr;
        while (itr != _sequenceNumbers.end()) {
            OCTREE_PACKET_SEQUENCE s = *itr;
            if (s != p + 1) {
                qCDebug(interfaceapp) << "Gap from" << (int32_t)p << "to" << (int32_t)s << "(exclusive)";
                p = s;
            }
            ++itr;
        }
        if (p != SafeLanding::INVALID_SEQUENCE) {
            qCDebug(interfaceapp) << "Last:" << p;
        }
    }
}
