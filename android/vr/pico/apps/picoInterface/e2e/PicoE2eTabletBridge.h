// SPDX-License-Identifier: Apache-2.0
#pragma once

class QObject;

namespace overte::pico::e2e {

// Installs the debug-only semantic tablet observer and pointer driver.  The
// implementation remains dormant unless the repository E2E probe is the
// active --testScript.
void installTabletBridge(QObject* owner);

}  // namespace overte::pico::e2e
