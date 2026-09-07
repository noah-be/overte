// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0
#include "WorldObservation.h"
#include <shared/IOSRuntimeLogging.h>
#include <QDir>
#include <QFileInfo>
#include <QJsonDocument>
#include <QSaveFile>

namespace overte::ios {
QJsonObject worldObservation(bool foreground) {
    // One locked Shared snapshot, never independent reads of generation/counts.
    const auto snapshot = iosRuntimeEntityEvidenceSnapshot();
    QJsonObject result {
        { "schemaVersion", 1 },
        { "status", "OBSERVATION_NOT_ACCEPTANCE" },
        { "sourceBinding", "EXTERNAL_CANDIDATE_REQUIRED" },
        { "artifactBinding", "EXTERNAL_INSTALLED_CODE_REQUIRED" },
        { "foreground", foreground },
        { "armed", foreground && snapshot.armed },
        { "committed", foreground && snapshot.committed },
        { "capacityExceeded", snapshot.capacityExceeded }
    };
    const bool current = foreground && snapshot.armed && !snapshot.capacityExceeded;
    result["expectedEntities"] = current ? snapshot.expected : 0;
    result["renderableEntities"] = current ? snapshot.renderables : 0;
    result["sceneEntities"] = current ? snapshot.scene : 0;
    result["drawnEntities"] = current ? snapshot.drawn : 0;
#if defined(OVERTE_IOS_WORLD_OBSERVATION_VERSION) && OVERTE_IOS_WORLD_OBSERVATION_VERSION == 1
    result["producer"] = "generation-present-v1";
    // Decimal strings retain the full uint64 range through JSON/JavaScript.
    result["generation"] = QString::number(current ? snapshot.generation : 0);
    result["acceptedPresentCalls"] = QString::number(current ? snapshot.acceptedPresentCalls : 0);
    result["rejectedPresentCalls"] = QString::number(current ? snapshot.rejectedPresentCalls : 0);
    result["lastPresentedFrame"] = QString::number(current ? snapshot.lastPresentedFrame : 0);
    result["softwareQmlImagesProduced"] = QString::number(current ? snapshot.softwareQmlImagesProduced : 0);
#else
    // The assigned source has entity observations but no frame/present join.
    // Keep that limitation explicit until General integrates the proposal.
    result["producer"] = "entity-counts-only";
#endif
    return result;
}

bool writeWorldObservation(const QString& directory, const QJsonObject& observation) {
    const QFileInfo parent(directory);
    if (!parent.isDir() || parent.isSymLink() || parent.canonicalFilePath().isEmpty()) { return false; }
    // Resolve the OS-provided container root once; system ancestor aliases are
    // allowed, while a replaced Documents directory or output symlink is not.
    const QString path = QDir(parent.canonicalFilePath()).filePath("overte-world-observation.json");
    const QFileInfo existing(path);
    if (existing.isSymLink() || (existing.exists() && !existing.isFile())) { return false; }
    const auto bytes = QJsonDocument(observation).toJson(QJsonDocument::Compact);
    if (bytes.isEmpty() || bytes.size() > 4096) { return false; }
    QSaveFile file(path);
    file.setDirectWriteFallback(false);
    if (!file.open(QIODevice::WriteOnly) ||
            !file.setPermissions(QFileDevice::ReadOwner | QFileDevice::WriteOwner) ||
            file.write(bytes) != bytes.size()) { return false; }
    return file.commit();
}
}
