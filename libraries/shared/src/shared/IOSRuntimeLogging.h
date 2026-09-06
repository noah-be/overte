//
//  IOSRuntimeLogging.h
//  libraries/shared/src/shared
//
//  SPDX-License-Identifier: Apache-2.0
//

#pragma once

#include <mutex>
#include <utility>
#include <cstdint>
#include <limits>

#include <QtCore/QByteArray>
#include <QtCore/QDateTime>
#include <QtCore/QDebug>
#include <QtCore/QFile>
#include <QtCore/QFileInfo>
#include <QtCore/QJsonArray>
#include <QtCore/QJsonDocument>
#include <QtCore/QJsonObject>
#include <QtCore/QSet>
#include <QtCore/QString>
#include <QtCore/QStringList>
#include <QtCore/QStandardPaths>
#include "../../../../security/redaction/SafeDiagnostics.h"

#if defined(Q_OS_IOS)
#include <os/log.h>
#endif

// Both sinks accept the same closed event vocabulary. Public OS logging must
// not bypass the Qt sanitizer. Diagnostics are not artifact/device acceptance.
inline void logIOSRuntimeEvent(overte::security::DiagnosticEvent event) {
    const char* message = overte::security::diagnosticEvent(event);
    qInfo().noquote() << message;
#if defined(Q_OS_IOS)
    os_log_info(OS_LOG_DEFAULT, "%{public}s", message);
#endif
}

// Compatibility for existing variadic callers: discard, do not format their
// payload. Legacy marker text/identifiers are no longer an evidence channel.
template<typename... Args>
inline void logIOSRuntimeMarker(Args&&...) {
    logIOSRuntimeEvent(overte::security::DiagnosticEvent::Redacted);
}

#if defined(Q_OS_IOS) || defined(OVERTE_IOS)
// World evidence is armed only after a serverless scene has parsed or a valid
// entity packet is about to be decoded. This prevents startup/UI entities from
// satisfying the world-rendering gates. A render handoff can race the commit
// on another thread. Correlation storage is bounded independently of world size;
// exhaustion invalidates observation, never application rendering.
struct IOSRuntimeEntityEvidenceState {
    std::mutex mutex;
    std::uint64_t generation { 0 };
    bool armed { false };
    bool committed { false };
    bool emitted { false };
    bool capacityExceeded { false };
    QSet<QString> expectedEntities;
    QSet<QString> renderedEntities;
    QSet<QString> sceneEntities;
    QSet<QString> drawnEntities;
};

struct IOSRuntimeEntityEvidenceSnapshot {
    bool armed { false };
    bool committed { false };
    int expected { 0 };
    int renderables { 0 };
    int scene { 0 };
    int drawn { 0 };
    bool capacityExceeded { false };
};

// Internal diagnostic storage limits, not accepted performance/scene budgets.
constexpr int IOS_RUNTIME_MAX_OBSERVED_ENTITIES { 4096 };
constexpr int IOS_RUNTIME_MAX_ENTITY_KEY_CHARACTERS { 128 };

// Caller holds state.mutex. Preserve generation so a subsequent begin advances
// it; no partial subset may look like complete observation after overflow.
inline void invalidateIOSRuntimeEntityCapacity(IOSRuntimeEntityEvidenceState& state) {
    state.armed = false;
    state.committed = false;
    state.emitted = false;
    state.capacityExceeded = true;
    state.expectedEntities.clear();
    state.renderedEntities.clear();
    state.sceneEntities.clear();
    state.drawnEntities.clear();
}

inline bool insertIOSRuntimeEntityBounded(IOSRuntimeEntityEvidenceState& state,
                                        QSet<QString>& entities, const QString& entity) {
    if (entity.size() > IOS_RUNTIME_MAX_ENTITY_KEY_CHARACTERS ||
            (!entities.contains(entity) && entities.size() >= IOS_RUNTIME_MAX_OBSERVED_ENTITIES)) {
        invalidateIOSRuntimeEntityCapacity(state);
        return false;
    }
    entities.insert(entity);
    return true;
}

inline IOSRuntimeEntityEvidenceState& iosRuntimeEntityEvidenceState() {
    static IOSRuntimeEntityEvidenceState state;
    return state;
}

inline void beginIOSRuntimeEntityEvidence() {
    auto& state = iosRuntimeEntityEvidenceState();
    std::lock_guard<std::mutex> lock(state.mutex);
    // Never reuse a generation, including the overflow case.
    state.armed = state.generation != std::numeric_limits<std::uint64_t>::max();
    if (state.armed) {
        ++state.generation;
    }
    state.committed = false;
    state.emitted = false;
    state.capacityExceeded = false;
    state.expectedEntities.clear();
    state.renderedEntities.clear();
    state.sceneEntities.clear();
    state.drawnEntities.clear();
}

inline std::uint64_t iosRuntimeEntityEvidenceGeneration() {
    auto& state = iosRuntimeEntityEvidenceState();
    std::lock_guard<std::mutex> lock(state.mutex);
    return state.armed ? state.generation : 0;
}

// Physical iOS devices cannot receive simulator-style launch environment
// variables, and CFPreferences may retain externally replaced plist values.
// HouseArrest/AFC can replace this ordinary Documents file without resigning,
// reinstalling, rebuilding, rebooting, or (for hot-reload-aware gates) even
// restarting the app.
inline const QString& iosRuntimeDiagnosticConfigPath() {
    static const QString path = [] {
        const auto overridePath = qgetenv("OVERTE_IOS_DIAGNOSTIC_CONFIG").trimmed();
        if (!overridePath.isEmpty()) {
            return QString::fromUtf8(overridePath);
        }
        return QStandardPaths::writableLocation(QStandardPaths::DocumentsLocation) +
            QStringLiteral("/overte-ios-render-diagnostics.json");
    }();
    return path;
}

struct IOSRuntimeDiagnosticConfigCache {
    std::mutex mutex;
    QJsonObject config;
    qint64 lastCheckMs { 0 };
    qint64 loadedSize { -1 };
    qint64 loadedModifiedMs { -1 };
    bool loadedExists { false };
};

inline QJsonObject iosRuntimeDiagnosticConfig() {
    static IOSRuntimeDiagnosticConfigCache cache;
    constexpr qint64 RELOAD_INTERVAL_MS { 1000 };
    const qint64 now = QDateTime::currentMSecsSinceEpoch();
    std::lock_guard<std::mutex> lock(cache.mutex);
    if (cache.lastCheckMs != 0 && now - cache.lastCheckMs < RELOAD_INTERVAL_MS) {
        return cache.config;
    }
    cache.lastCheckMs = now;

    const QFileInfo info(iosRuntimeDiagnosticConfigPath());
    const bool exists = info.exists() && info.isFile();
    const qint64 size = exists ? info.size() : -1;
    const qint64 modifiedMs = exists ? info.lastModified().toMSecsSinceEpoch() : -1;
    if (exists == cache.loadedExists && size == cache.loadedSize &&
            modifiedMs == cache.loadedModifiedMs) {
        return cache.config;
    }

    if (!exists) {
        cache.config = QJsonObject {};
        cache.loadedExists = false;
        cache.loadedSize = -1;
        cache.loadedModifiedMs = -1;
        return cache.config;
    }

    // This hot-reloaded file is external input, not a renderer-sized payload.
    // Keep the last valid configuration during a partial/oversized replacement.
    // Check both metadata and bounded bytes: the file may grow after QFileInfo.
    constexpr qint64 MAX_CONFIG_BYTES { 1024 * 1024 };
    if (size < 0 || size > MAX_CONFIG_BYTES) {
        return cache.config;
    }
    QFile file(iosRuntimeDiagnosticConfigPath());
    if (!file.open(QIODevice::ReadOnly)) {
        return cache.config;
    }
    const auto bytes = file.read(MAX_CONFIG_BYTES + 1);
    if (file.error() != QFileDevice::NoError || bytes.size() > MAX_CONFIG_BYTES || !file.atEnd()) {
        return cache.config;
    }
    QJsonParseError error;
    const auto document = QJsonDocument::fromJson(bytes, &error);
    if (error.error != QJsonParseError::NoError || !document.isObject()) {
        // AFC replacement is not guaranteed to be atomic. Retain the last
        // valid object and retry instead of briefly disabling all diagnostics.
        return cache.config;
    }
    cache.config = document.object();
    cache.loadedExists = true;
    cache.loadedSize = size;
    cache.loadedModifiedMs = modifiedMs;
    logIOSRuntimeEvent(overte::security::DiagnosticEvent::Redacted);
    return cache.config;
}

inline QStringList iosRuntimeDiagnosticStringList(const char* key) {
    QStringList values;
    const auto array = iosRuntimeDiagnosticConfig().value(QString::fromUtf8(key)).toArray();
    for (const auto& value : array) {
        if (value.isString() && !value.toString().isEmpty()) {
            values.push_back(value.toString());
        }
    }
    return values;
}

inline bool iosRuntimeDiagnosticBool(const char* key, bool defaultValue = false) {
    const auto value = iosRuntimeDiagnosticConfig().value(QString::fromUtf8(key));
    return value.isBool() ? value.toBool() : defaultValue;
}

inline int iosRuntimeDiagnosticInt(const char* key, int defaultValue,
                                   int minimum, int maximum) {
    const auto value = iosRuntimeDiagnosticConfig().value(QString::fromUtf8(key));
    if (!value.isDouble()) {
        return defaultValue;
    }
    return qBound(minimum, value.toInt(defaultValue), maximum);
}

inline QSet<int> iosRuntimeDiagnosticIntSet(const char* key,
                                           int minimum = 0,
                                           int maximum = 0x7fffffff) {
    QSet<int> values;
    const auto array = iosRuntimeDiagnosticConfig().value(QString::fromUtf8(key)).toArray();
    for (const auto& value : array) {
        if (value.isDouble()) {
            const auto number = value.toInt(minimum - 1);
            if (number >= minimum && number <= maximum) {
                values.insert(number);
            }
        }
    }
    return values;
}

inline QByteArray iosRuntimeRenderDiagnosticMode() {
    const auto environmentMode = qgetenv("OVERTE_IOS_RENDER_DIAGNOSTIC").trimmed().toLower();
    if (!environmentMode.isEmpty()) {
        return environmentMode;
    }
    return iosRuntimeDiagnosticConfig()
        .value(QStringLiteral("renderDiagnosticMode"))
        .toString()
        .trimmed()
        .toLower()
        .toUtf8();
}

inline bool iosRuntimeRenderDiagnosticsEnabled() {
    const auto mode = iosRuntimeRenderDiagnosticMode();
    return !mode.isEmpty() && mode != "off";
}

inline IOSRuntimeEntityEvidenceSnapshot iosRuntimeEntityEvidenceSnapshot() {
    auto& state = iosRuntimeEntityEvidenceState();
    std::lock_guard<std::mutex> lock(state.mutex);
    return {
        state.armed,
        state.committed,
        static_cast<int>(state.expectedEntities.size()),
        static_cast<int>(state.renderedEntities.size()),
        static_cast<int>(state.sceneEntities.size()),
        static_cast<int>(state.drawnEntities.size()),
        state.capacityExceeded
    };
}

inline QString takeIOSRuntimeEntityEvidenceIfReady(IOSRuntimeEntityEvidenceState& state) {
    if (!state.armed || !state.committed || state.emitted) {
        return {};
    }
    for (const auto& entity : state.renderedEntities) {
        if (state.expectedEntities.contains(entity)) {
            state.emitted = true;
            return entity;
        }
    }
    return {};
}

inline QString recordIOSRuntimeTreeEntity(const QString& entity) {
    auto& state = iosRuntimeEntityEvidenceState();
    std::lock_guard<std::mutex> lock(state.mutex);
    if (!state.armed || state.emitted) {
        return {};
    }
    if (!insertIOSRuntimeEntityBounded(state, state.expectedEntities, entity)) {
        return {};
    }
    return takeIOSRuntimeEntityEvidenceIfReady(state);
}

inline QString setExpectedIOSRuntimeEntities(const QStringList& entities) {
    auto& state = iosRuntimeEntityEvidenceState();
    std::lock_guard<std::mutex> lock(state.mutex);
    if (!state.armed || state.emitted) {
        return {};
    }
    if (entities.size() > IOS_RUNTIME_MAX_OBSERVED_ENTITIES) {
        invalidateIOSRuntimeEntityCapacity(state);
        return {};
    }
    state.expectedEntities.clear();
    for (const auto& entity : entities) {
        if (!insertIOSRuntimeEntityBounded(state, state.expectedEntities, entity)) {
            return {};
        }
    }
    return takeIOSRuntimeEntityEvidenceIfReady(state);
}

inline QString recordIOSRuntimeRenderableEntity(const QString& entity) {
    auto& state = iosRuntimeEntityEvidenceState();
    std::lock_guard<std::mutex> lock(state.mutex);
    if (!state.armed || state.emitted) {
        return {};
    }
    if (!insertIOSRuntimeEntityBounded(state, state.renderedEntities, entity)) {
        return {};
    }
    return takeIOSRuntimeEntityEvidenceIfReady(state);
}

inline bool recordIOSRuntimeSceneEntity(const QString& entity, std::uint64_t generation) {
    auto& state = iosRuntimeEntityEvidenceState();
    std::lock_guard<std::mutex> lock(state.mutex);
    if (!state.armed || generation == 0 || generation != state.generation || state.sceneEntities.contains(entity)) {
        return false;
    }
    return insertIOSRuntimeEntityBounded(state, state.sceneEntities, entity);
}

inline bool recordIOSRuntimeDrawnEntity(const QString& entity) {
    auto& state = iosRuntimeEntityEvidenceState();
    std::lock_guard<std::mutex> lock(state.mutex);
    if (!state.armed || state.drawnEntities.contains(entity)) {
        return false;
    }
    return insertIOSRuntimeEntityBounded(state, state.drawnEntities, entity);
}

inline QString commitIOSRuntimeEntityEvidence() {
    auto& state = iosRuntimeEntityEvidenceState();
    std::lock_guard<std::mutex> lock(state.mutex);
    if (!state.armed || state.emitted) {
        return {};
    }
    state.committed = true;
    return takeIOSRuntimeEntityEvidenceIfReady(state);
}

inline void logIOSRuntimeEntityEvidence(const QString& entity) {
    if (entity.isEmpty()) {
        return;
    }
    logIOSRuntimeMarker("OVERTE_IOS_ENTITY_GATE entity_tree_nonempty",
                        "entity=", entity);
    logIOSRuntimeMarker("OVERTE_IOS_ENTITY_GATE render_handoff",
                        "entity=", entity);
}
#endif
