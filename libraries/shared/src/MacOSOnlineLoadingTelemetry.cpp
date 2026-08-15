//
//  MacOSOnlineLoadingTelemetry.cpp
//  libraries/shared/src
//
//  Copyright 2026 Overte e.V.
//  SPDX-License-Identifier: Apache-2.0
//

#include "MacOSOnlineLoadingTelemetry.h"

#include <algorithm>
#include <array>
#include <chrono>
#include <iterator>

#include <QtCore/QCoreApplication>
#include <QtCore/QJsonDocument>
#include <QtCore/QJsonObject>
#include <QtCore/QMutex>
#include <QtCore/QMutexLocker>
#include <QtCore/QSet>

#include <shared/GlobalAppProperties.h>

namespace macos::online_loading {
namespace {

constexpr auto NAVIGATION_ENV = "OVERTE_MACOS_ONLINE_LOADING_NAVIGATION_ID";
constexpr auto LOCATION_SHA_ENV = "OVERTE_MACOS_ONLINE_LOADING_LOCATION_SHA256";
constexpr auto LOG_PREFIX = "OVERTE_MACOS_ONLINE_NAV";
constexpr int MAX_NAVIGATION_ID_LENGTH { 64 };
constexpr std::array<const char*, 10> EVENT_ORDER {{
    "url_accepted",
    "domain_connected",
    "entity_server_active",
    "entity_query",
    "entity_data",
    "entity_decode",
    "entity_tree",
    "render_handoff",
    "first_presented",
    "first_visible",
}};

struct Configuration {
    QString navigationId;
    QString locationSha256;

    bool valid() const {
        return !navigationId.isEmpty() && !locationSha256.isEmpty();
    }
};

struct TelemetryState {
    QMutex mutex;
    QString navigationId;
    QString locationSha256;
    QSet<QString> recordedEvents;
    quint64 lastMonotonicUsec { 0 };
};

TelemetryState& state() {
    static TelemetryState telemetryState;
    return telemetryState;
}

bool isLowerAlphaNumeric(char value) {
    return (value >= 'a' && value <= 'z') || (value >= '0' && value <= '9');
}

bool isSafeIdentifier(const QByteArray& value, int maximumLength) {
    if (value.isEmpty() || value.size() > maximumLength || !isLowerAlphaNumeric(value.front())) {
        return false;
    }
    return std::all_of(value.cbegin(), value.cend(), [](char character) {
        return isLowerAlphaNumeric(character) || character == '-';
    });
}

bool isSha256(const QByteArray& value) {
    return value.size() == 64 && std::all_of(value.cbegin(), value.cend(), [](char character) {
        return (character >= '0' && character <= '9') || (character >= 'a' && character <= 'f');
    });
}

bool testScriptIsActive() {
    return qApp && qApp->property(hifi::properties::TEST).isValid();
}

Configuration configuration() {
    if (!testScriptIsActive()) {
        return {};
    }
    const QByteArray navigation = qgetenv(NAVIGATION_ENV);
    const QByteArray locationSha = qgetenv(LOCATION_SHA_ENV);
    if (!isSafeIdentifier(navigation, MAX_NAVIGATION_ID_LENGTH) || !isSha256(locationSha)) {
        return {};
    }
    return { QString::fromLatin1(navigation), QString::fromLatin1(locationSha) };
}

bool safeEventOrFieldName(const char* value) {
    if (!value || !*value) {
        return false;
    }
    for (const char* cursor = value; *cursor; ++cursor) {
        if (!((*cursor >= 'a' && *cursor <= 'z') || (*cursor >= '0' && *cursor <= '9') || *cursor == '_')) {
            return false;
        }
    }
    return true;
}

int eventIndex(const char* event) {
    if (!event) {
        return -1;
    }
    const auto found = std::find_if(EVENT_ORDER.cbegin(), EVENT_ORDER.cend(), [event](const char* allowed) {
        return qstrcmp(event, allowed) == 0;
    });
    return found == EVENT_ORDER.cend() ? -1 : static_cast<int>(std::distance(EVENT_ORDER.cbegin(), found));
}

bool allowedNumericField(int index, const char* field) {
    const auto is = [field](const char* expected) { return qstrcmp(field, expected) == 0; };
    switch (index) {
        case 2:
            return is("resource_loading") || is("resource_pending");
        case 3:
            return is("bytes") || is("resource_loading") || is("resource_pending");
        case 4:
            return is("bytes") || is("packet_queue");
        case 5:
            return is("decompress_us") || is("wait_lock_us");
        case 6:
            return is("entities") || is("elements") || is("tree_us");
        case 7:
            return is("entities_pending_add") || is("renderables_pending_update");
        case 8:
            return is("present_count");
        case 9:
            return is("present_count") || is("visible_count");
        default:
            return false;
    }
}

quint64 currentSteadyClockUsec() {
    using namespace std::chrono;
    return static_cast<quint64>(duration_cast<microseconds>(steady_clock::now().time_since_epoch()).count());
}

} // namespace

bool enabled() {
    return configuration().valid();
}

QString navigationId() {
    return configuration().navigationId;
}

QString locationSha256() {
    return configuration().locationSha256;
}

bool recordOnce(const char* event, NumericFields fields) {
    return recordOnceAt(event, currentSteadyClockUsec(), fields);
}

bool recordOnceAt(const char* event, quint64 monotonicUsec, NumericFields fields) {
    const auto current = configuration();
    const int expectedIndex = eventIndex(event);
    if (!current.valid() || expectedIndex < 0) {
        return false;
    }
    for (const auto& field : fields) {
        if (!safeEventOrFieldName(field.first) || !allowedNumericField(expectedIndex, field.first) || field.second < 0) {
            return false;
        }
    }

    auto& telemetryState = state();
    QMutexLocker locker(&telemetryState.mutex);
    if (telemetryState.navigationId != current.navigationId ||
            telemetryState.locationSha256 != current.locationSha256) {
        telemetryState.navigationId = current.navigationId;
        telemetryState.locationSha256 = current.locationSha256;
        telemetryState.recordedEvents.clear();
        telemetryState.lastMonotonicUsec = 0;
    }
    const QString eventName = QString::fromLatin1(event);
    if (telemetryState.recordedEvents.contains(eventName)) {
        return false;
    }
    if (expectedIndex != telemetryState.recordedEvents.size() ||
            monotonicUsec <= telemetryState.lastMonotonicUsec) {
        return false;
    }
    telemetryState.lastMonotonicUsec = monotonicUsec;
    telemetryState.recordedEvents.insert(eventName);

    QJsonObject record {
        { "schema_version", 1 },
        { "navigation_id", current.navigationId },
        { "location_sha256", current.locationSha256 },
        { "event", eventName },
        { "monotonic_us", static_cast<double>(monotonicUsec) },
    };
    for (const auto& field : fields) {
        record.insert(QString::fromLatin1(field.first), static_cast<double>(field.second));
    }
    qInfo().noquote() << LOG_PREFIX << QJsonDocument(record).toJson(QJsonDocument::Compact);
    return true;
}

quint64 steadyClockUsec() {
    return currentSteadyClockUsec();
}

bool hasRecorded(const char* event) {
    const auto current = configuration();
    if (!current.valid() || eventIndex(event) < 0) {
        return false;
    }
    auto& telemetryState = state();
    QMutexLocker locker(&telemetryState.mutex);
    return telemetryState.navigationId == current.navigationId &&
        telemetryState.recordedEvents.contains(QString::fromLatin1(event));
}

} // namespace macos::online_loading
