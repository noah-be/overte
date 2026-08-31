//
// Minimal phone Back-routing boundary for Android entry points that must not
// include DialogsManager's desktop dialog dependency graph.
//

#pragma once

#include <QVariantMap>

namespace phone {

bool closeTopmostDialog();
bool updateTouchUiRuntimeMetrics(const QVariantMap& metrics);

} // namespace phone
