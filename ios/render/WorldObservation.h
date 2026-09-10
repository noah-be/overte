// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <QJsonObject>
#include <QString>

namespace overte::ios {
// Actual renderer observations only. No URL, entity/account/device identifier,
// inferred artifact identity or positive acceptance result is exported.
QJsonObject worldObservation(bool foreground);
bool writeWorldObservation(const QString& directory, const QJsonObject& observation);
}
