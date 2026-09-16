// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <functional>
class QObject;
namespace overte::ios {
void installMemoryWarningHandler(QObject* lifetime, std::function<void()> callback);
}
