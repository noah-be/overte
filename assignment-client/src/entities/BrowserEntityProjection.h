// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
#pragma once

#include <QJsonArray>
#include <QJsonObject>

// Export only public domain entity state. Never expose persistence-only fields
// or private user data through the browser rendering projection. The native
// entity edit/filter path remains the only authority for changes.
inline QJsonArray browserEntityProjection(const QJsonArray& entities) {
    QJsonArray result;
    for (const auto& entry : entities) {
        if (!entry.isObject()) {
            continue;
        }
        auto entity = entry.toObject();
        const auto host = entity.value("entityHostType").toString();
        if (!host.isEmpty() && host != "domain") {
            continue;
        }
        entity.remove("privateUserData");
        entity.remove("serverScripts");
        entity.remove("simulationOwner");
        entity.remove("certificateID");
        entity.remove("marketplaceID");
        result.append(entity);
    }
    return result;
}
