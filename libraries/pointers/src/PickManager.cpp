//
//  Created by Sam Gondelman 10/19/2017
//  Copyright 2017 High Fidelity, Inc.
//
//  Distributed under the Apache License, Version 2.0.
//  See the accompanying file LICENSE or http://www.apache.org/licenses/LICENSE-2.0.html
//
#include "PickManager.h"
#include "PerfStat.h"
#include "Profile.h"

PickManager::PickManager() {
    setShouldPickHUDOperator([]() { return false; });
    setCalculatePos2DFromHUDOperator([](const glm::vec3& intersection) { return glm::vec2(NAN); });
}

unsigned int PickManager::addPick(PickQuery::PickType type, const std::shared_ptr<PickQuery> pick) {
    unsigned int id = INVALID_PICK_ID;
    withWriteLock([&] {
        // Don't let the pick IDs overflow
        if (_nextPickID < UINT32_MAX) {
            id = _nextPickID++;
            _picks[type][id] = pick;
            _typeMap[id] = type;
            _totalPickCounts[type]++;
        }
    });
    return id;
}

std::shared_ptr<PickQuery> PickManager::findPick(unsigned int uid) const {
    return resultWithReadLock<std::shared_ptr<PickQuery>>([&] {
        auto type = _typeMap.find(uid);
        if (type != _typeMap.end()) {
            return _picks.find(type->second)->second.find(uid)->second;
        }
        return std::shared_ptr<PickQuery>();
    });
}

void PickManager::removePick(unsigned int uid) {
    withWriteLock([&] {
        auto typeIt = _typeMap.find(uid);
        if (typeIt != _typeMap.end()) {
            _picks[typeIt->second].erase(uid);
            _totalPickCounts[typeIt->second]--;
            _typeMap.erase(typeIt);
        }
    });
}

QVariantMap PickManager::getPickProperties(unsigned int uid) const {
    auto pick = findPick(uid);
    if (pick) {
        return pick->toVariantMap();
    }
    return QVariantMap();
}

QVariantMap PickManager::getPickScriptParameters(unsigned int uid) const {
    auto pick = findPick(uid);
    if (pick) {
        return pick->getScriptParameters();
    }
    return QVariantMap();
}

QVector<unsigned int> PickManager::getPicks() const {
    QVector<unsigned int> picks;
    withReadLock([&] {
        for (auto typeIt = _picks.cbegin(); typeIt != _picks.cend(); ++typeIt) {
            auto& picksForType = typeIt->second;
            for (auto pickIt = picksForType.cbegin(); pickIt != picksForType.cend(); ++pickIt) {
                picks.push_back(pickIt->first);
            }
        }
    });
    return picks;
}

PickResultPointer PickManager::getPrevPickResult(unsigned int uid) const {
    auto pick = findPick(uid);
    if (pick) {
        return pick->getPrevPickResult();
    }
    return PickResultPointer();
}

void PickManager::enablePick(unsigned int uid) const {
    auto pick = findPick(uid);
    if (pick) {
        pick->enable();
    }
}

void PickManager::disablePick(unsigned int uid) const {
    auto pick = findPick(uid);
    if (pick) {
        pick->disable();
    }
}

bool PickManager::isPickEnabled(unsigned int uid) const {
    auto pick = findPick(uid);
    if (pick) {
        return pick->isEnabled();
    }
    return false;
}

void PickManager::setPrecisionPicking(unsigned int uid, bool precisionPicking) const {
    auto pick = findPick(uid);
    if (pick) {
        pick->setPrecisionPicking(precisionPicking);
    }
}

void PickManager::setIgnoreItems(unsigned int uid, const QVector<QUuid>& ignore) const {
    auto pick = findPick(uid);
    if (pick) {
        pick->setIgnoreItems(ignore);
    }
}

void PickManager::setIncludeItems(unsigned int uid, const QVector<QUuid>& include) const {
    auto pick = findPick(uid);
    if (pick) {
        pick->setIncludeItems(include);
    }
}

void PickManager::setDelay(unsigned int uid, float delay) const {
    auto pick = findPick(uid);
    if (pick) {
        pick->setDelay(delay);
    }
}

Transform PickManager::getParentTransform(unsigned int uid) const {
    auto pick = findPick(uid);
    if (pick) {
        auto parentTransform = pick->parentTransform;
        if (parentTransform) {
            return parentTransform->getTransform();
        }
    }
    return Transform();
}

Transform PickManager::getResultTransform(unsigned int uid) const {
    auto pick = findPick(uid);
    if (pick) {
        return pick->getResultTransform();
    }
    return Transform();
}

PickRay PickManager::getCurrentRay(unsigned int uid) const {
    auto pick = findPick(uid);
    if (pick && pick->getType() == PickQuery::Ray) {
        return std::static_pointer_cast<Pick<PickRay>>(pick)->getMathematicalPick();
    }
    return PickRay();
}

void PickManager::update() {
    uint64_t expiry = usecTimestampNow() + _perFrameTimeBudget;
    std::unordered_map<PickQuery::PickType, std::unordered_map<unsigned int, std::shared_ptr<PickQuery>>> cachedPicks;
    withReadLock([&] {
        cachedPicks = _picks;
    });

    bool shouldPickHUD = _shouldPickHUDOperator();
#if defined(Q_OS_ANDROID)
    // The always-enabled, non-hand ray can spend several milliseconds walking
    // the entity tree even when the user is not pointing with a controller.
    // Update that background ray every fourth application update. In dense
    // domains a single entity-tree ray can take well over the entire pick
    // budget, despite there being no active controller interaction. Active
    // hand rays remain full-rate so tablet and controller latency is unchanged.
    bool hasEnabledHandRay { false };
    bool hasEnabledStylus { false };
    bool hasEnabledParabola { false };
    bool hasEnabledCollision { false };
    for (const auto& item : cachedPicks[PickQuery::Ray]) {
        const auto& pick = item.second;
        if (pick->isEnabled() && (pick->isLeftHand() || pick->isRightHand())) {
            hasEnabledHandRay = true;
            break;
        }
    }
    for (const auto& item : cachedPicks[PickQuery::Stylus]) {
        hasEnabledStylus = hasEnabledStylus || item.second->isEnabled();
    }
    for (const auto& item : cachedPicks[PickQuery::Parabola]) {
        hasEnabledParabola = hasEnabledParabola || item.second->isEnabled();
    }
    for (const auto& item : cachedPicks[PickQuery::Collision]) {
        hasEnabledCollision = hasEnabledCollision || item.second->isEnabled();
    }
    // Android has no desktop mouse cursor that needs the always-enabled
    // background ray. With the tablet closed that ray only traverses the dense
    // entity tree and can stall an update for tens of milliseconds. As soon as
    // either controller/hand ray is enabled, update the complete ray set every
    // frame so tablet interaction remains responsive.
    const bool updateRaysThisFrame = hasEnabledHandRay;
    // While a controller is interacting, background/non-hand rays must not
    // consume the budget before the UI ray that owns hover and click events.
    // Disabled hand picks remain in this set so the optimizer can clear their
    // previous results without doing intersection work.
    auto androidInteractionRays = cachedPicks[PickQuery::Ray];
    if (hasEnabledHandRay) {
        for (auto it = androidInteractionRays.begin(); it != androidInteractionRays.end();) {
            if (!it->second->isLeftHand() && !it->second->isRightHand()) {
                it = androidInteractionRays.erase(it);
            } else {
                ++it;
            }
        }
    }
#endif
    // FIXME: give each type its own expiry
    // Each type will update at least one pick, regardless of the expiry
    {
        PROFILE_RANGE_EX(picks, "StylusPicks", 0xffff0000, (uint64_t)_totalPickCounts[PickQuery::Stylus]);
        PerformanceTimer perfTimer("StylusPicks");
#if defined(Q_OS_ANDROID)
        _updatedPickCounts[PickQuery::Stylus] = hasEnabledStylus
            ? _stylusPickCacheOptimizer.update(cachedPicks[PickQuery::Stylus], _nextPickToUpdate[PickQuery::Stylus], expiry, false)
            : QVector3D();
#else
        _updatedPickCounts[PickQuery::Stylus] = _stylusPickCacheOptimizer.update(cachedPicks[PickQuery::Stylus], _nextPickToUpdate[PickQuery::Stylus], expiry, false);
#endif
    }
    {
        PROFILE_RANGE_EX(picks, "RayPicks", 0xffff0000, (uint64_t)_totalPickCounts[PickQuery::Ray]);
        PerformanceTimer perfTimer("RayPicks");
#if defined(Q_OS_ANDROID)
        if (updateRaysThisFrame) {
            _updatedPickCounts[PickQuery::Ray] = _rayPickCacheOptimizer.update(androidInteractionRays, _nextPickToUpdate[PickQuery::Ray], expiry, shouldPickHUD);
        } else {
            _updatedPickCounts[PickQuery::Ray] = QVector3D();
        }
#else
        _updatedPickCounts[PickQuery::Ray] = _rayPickCacheOptimizer.update(cachedPicks[PickQuery::Ray], _nextPickToUpdate[PickQuery::Ray], expiry, shouldPickHUD);
#endif
    }
    {
        PROFILE_RANGE_EX(picks, "ParabolaPicks", 0xffff0000, (uint64_t)_totalPickCounts[PickQuery::Parabola]);
        PerformanceTimer perfTimer("ParabolaPicks");
#if defined(Q_OS_ANDROID)
        _updatedPickCounts[PickQuery::Parabola] = hasEnabledParabola
            ? _parabolaPickCacheOptimizer.update(cachedPicks[PickQuery::Parabola], _nextPickToUpdate[PickQuery::Parabola], expiry, shouldPickHUD)
            : QVector3D();
#else
        _updatedPickCounts[PickQuery::Parabola] = _parabolaPickCacheOptimizer.update(cachedPicks[PickQuery::Parabola], _nextPickToUpdate[PickQuery::Parabola], expiry, shouldPickHUD);
#endif
    }
    {
        PROFILE_RANGE_EX(picks, "CollisionPicks", 0xffff0000, (uint64_t)_totalPickCounts[PickQuery::Collision]);
        PerformanceTimer perfTimer("CollisionPicks");
#if defined(Q_OS_ANDROID)
        _updatedPickCounts[PickQuery::Collision] = hasEnabledCollision
            ? _collisionPickCacheOptimizer.update(cachedPicks[PickQuery::Collision], _nextPickToUpdate[PickQuery::Collision], expiry, false)
            : QVector3D();
#else
        _updatedPickCounts[PickQuery::Collision] = _collisionPickCacheOptimizer.update(cachedPicks[PickQuery::Collision], _nextPickToUpdate[PickQuery::Collision], expiry, false);
#endif
    }
}

bool PickManager::isLeftHand(unsigned int uid) {
    auto pick = findPick(uid);
    if (pick) {
        return pick->isLeftHand();
    }
    return false;
}

bool PickManager::isRightHand(unsigned int uid) {
    auto pick = findPick(uid);
    if (pick) {
        return pick->isRightHand();
    }
    return false;
}

bool PickManager::isMouse(unsigned int uid) {
    auto pick = findPick(uid);
    if (pick) {
        return pick->isMouse();
    }
    return false;
}
