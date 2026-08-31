//
//  IOSRuntimeLogging.h
//  libraries/shared/src/shared
//
//  SPDX-License-Identifier: Apache-2.0
//

#pragma once

#include <mutex>
#include <utility>

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

#if defined(Q_OS_IOS)
#include <os/log.h>
#endif

// CoreSimulator does not reliably preserve stdout/stderr from a GUI process.
// Keep Qt's normal diagnostic stream, but mirror bounded acceptance markers to
// Apple unified logging so runtime automation can observe them deterministically.
template<typename... Args>
inline void logIOSRuntimeMarker(Args&&... args) {
    QString message;
    {
        QDebug stream(&message);
        stream.noquote();
        (stream << ... << std::forward<Args>(args));
    }

    qInfo().noquote() << message;

#if defined(Q_OS_IOS)
    const QByteArray utf8 = message.toUtf8();
    os_log_info(OS_LOG_DEFAULT, "%{public}s", utf8.constData());
#endif
}

#if defined(Q_OS_IOS) || defined(OVERTE_IOS)
// World evidence is armed only after a serverless scene has parsed or a valid
// entity packet is about to be decoded. This prevents startup/UI entities from
// satisfying the world-rendering gates. A render handoff can race the commit
// on another thread, so retain one bounded UUID until both sides complete.
struct IOSRuntimeEntityEvidenceState {
    std::mutex mutex;
    bool armed { false };
    bool committed { false };
    bool emitted { false };
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
};

inline IOSRuntimeEntityEvidenceState& iosRuntimeEntityEvidenceState() {
    static IOSRuntimeEntityEvidenceState state;
    return state;
}

inline void beginIOSRuntimeEntityEvidence() {
    auto& state = iosRuntimeEntityEvidenceState();
    std::lock_guard<std::mutex> lock(state.mutex);
    state.armed = true;
    state.committed = false;
    state.emitted = false;
    state.expectedEntities.clear();
    state.renderedEntities.clear();
    state.sceneEntities.clear();
    state.drawnEntities.clear();
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

    QFile file(iosRuntimeDiagnosticConfigPath());
    if (!file.open(QIODevice::ReadOnly)) {
        return cache.config;
    }
    QJsonParseError error;
    const auto document = QJsonDocument::fromJson(file.readAll(), &error);
    if (error.error != QJsonParseError::NoError || !document.isObject()) {
        // AFC replacement is not guaranteed to be atomic. Retain the last
        // valid object and retry instead of briefly disabling all diagnostics.
        return cache.config;
    }
    cache.config = document.object();
    cache.loadedExists = true;
    cache.loadedSize = size;
    cache.loadedModifiedMs = modifiedMs;
    logIOSRuntimeMarker(
        "OVERTE_IOS_DIAGNOSTIC_CONFIG stage=reloaded",
        "keys=", cache.config.size(),
        "schema=", cache.config.value(QStringLiteral("schemaVersion")).toInt(0),
        "size=", size,
        "path=", iosRuntimeDiagnosticConfigPath());
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
        static_cast<int>(state.drawnEntities.size())
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
    state.expectedEntities.insert(entity);
    return takeIOSRuntimeEntityEvidenceIfReady(state);
}

inline QString setExpectedIOSRuntimeEntities(const QStringList& entities) {
    auto& state = iosRuntimeEntityEvidenceState();
    std::lock_guard<std::mutex> lock(state.mutex);
    if (!state.armed || state.emitted) {
        return {};
    }
    state.expectedEntities.clear();
    for (const auto& entity : entities) {
        state.expectedEntities.insert(entity);
    }
    return takeIOSRuntimeEntityEvidenceIfReady(state);
}

inline QString recordIOSRuntimeRenderableEntity(const QString& entity) {
    auto& state = iosRuntimeEntityEvidenceState();
    std::lock_guard<std::mutex> lock(state.mutex);
    if (!state.armed || state.emitted) {
        return {};
    }
    state.renderedEntities.insert(entity);
    return takeIOSRuntimeEntityEvidenceIfReady(state);
}

inline bool recordIOSRuntimeSceneEntity(const QString& entity) {
    auto& state = iosRuntimeEntityEvidenceState();
    std::lock_guard<std::mutex> lock(state.mutex);
    if (!state.armed || state.sceneEntities.contains(entity)) {
        return false;
    }
    state.sceneEntities.insert(entity);
    return true;
}

inline bool recordIOSRuntimeDrawnEntity(const QString& entity) {
    auto& state = iosRuntimeEntityEvidenceState();
    std::lock_guard<std::mutex> lock(state.mutex);
    if (!state.armed || state.drawnEntities.contains(entity)) {
        return false;
    }
    state.drawnEntities.insert(entity);
    return true;
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
