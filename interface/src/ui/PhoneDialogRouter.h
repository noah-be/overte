//
// Minimal phone Back-routing boundary for Android entry points that must not
// include DialogsManager's desktop dialog dependency graph.
//

#pragma once

namespace phone {

bool closeTopmostDialog();

} // namespace phone
