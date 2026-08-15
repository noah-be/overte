//
//  MacOSOnlineLoadingTelemetry.h
//  libraries/shared/src
//
//  Copyright 2026 Overte e.V.
//  SPDX-License-Identifier: Apache-2.0
//

#pragma once

#include <initializer_list>
#include <utility>

#include <QtCore/QByteArray>
#include <QtCore/QString>
#include <QtCore/QtGlobal>

namespace macos::online_loading {

using NumericField = std::pair<const char*, qint64>;
using NumericFields = std::initializer_list<NumericField>;

// Telemetry is enabled only when Interface is running a test script and the
// benchmark supplied a strictly validated navigation identity and location
// digest. Invalid values fail closed and are never logged.
bool enabled();
QString navigationId();
QString locationSha256();

// Starts the navigation timeline only when the exact target bytes match the
// runner-provided digest. The target itself is never retained or logged.
bool beginNavigation(const QByteArray& target);

// All records use one process-wide steady-clock timeline. An event is emitted
// at most once for a navigation ID; changing the ID starts a fresh event set.
bool recordOnce(const char* event, NumericFields fields = {});
bool recordOnceAt(const char* event, quint64 monotonicUsec, NumericFields fields = {});
bool hasRecorded(const char* event);
quint64 steadyClockUsec();

} // namespace macos::online_loading
