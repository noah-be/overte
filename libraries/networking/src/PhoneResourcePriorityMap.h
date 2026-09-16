// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0
#pragma once

#include <cfloat>
#include <cstdint>
#include <functional>
#include <mutex>

#include <QHash>
#include <QObject>
#include <QPointer>

// Defined by ResourceCache; keep this helper independently includable in tests.
uint qHash(const QPointer<QObject>& value, uint seed);

// Synchronizes existing Resource maps without changing Resource's layout.
// QHash snapshots share storage until a writer detaches. Detaching can copy or
// destroy arbitrary function captures, so prepare writes outside the mutex and
// publish only if no intervening writer changed the map generation.
class PhoneResourcePriorityMap {
public:
    using Map = QHash<QPointer<QObject>, std::function<float()>>;

    Map snapshot(const Map& map) {
        std::lock_guard<std::mutex> lock(_mutex);
        return map;
    }

    void set(Map& map, const QPointer<QObject>& owner, const std::function<float()>& operation) {
        update(map, [&](Map& next) {
            next.insert(owner, operation);
            return true;
        });
    }

    void clear(Map& map) {
        Map retired;
        {
            std::lock_guard<std::mutex> lock(_mutex);
            map.swap(retired);
            ++_generation;
        }
        // Last references to callback captures are released outside the lock.
    }

    float priority(Map& map) {
        const auto current = snapshot(map);
        if (current.isEmpty()) {
            return 0.0f;
        }
        float highest = -FLT_MAX;
        bool prune = false;
        for (auto it = current.cbegin(); it != current.cend(); ++it) {
            if (it.key().isNull() || !it.value()) {
                prune = true;
                continue;
            }
            highest = qMax(highest, it.value()());
        }
        if (prune) {
            update(map, [](Map& next) {
                bool changed = false;
                for (auto it = next.begin(); it != next.end();) {
                    if (it.key().isNull() || !it.value()) {
                        it = next.erase(it);
                        changed = true;
                    } else {
                        ++it;
                    }
                }
                return changed;
            });
        }
        // Preserve the distinction between initially empty and all pruned.
        return highest;
    }

private:
    template<typename Mutation>
    void update(Map& map, Mutation mutation) {
        for (;;) {
            Map next;
            uint64_t generation;
            {
                std::lock_guard<std::mutex> lock(_mutex);
                next = map;
                generation = _generation;
            }
            if (!mutation(next)) {
                return;
            }
            bool published = false;
            {
                std::lock_guard<std::mutex> lock(_mutex);
                if (generation == _generation) {
                    map.swap(next);
                    ++_generation;
                    published = true;
                }
            }
            if (published) {
                return;
            }
            // Both the retired map and failed candidate die outside the lock.
        }
    }

    std::mutex _mutex;
    uint64_t _generation { 0 };
};
