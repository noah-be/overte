// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0
#include "KeychainAccountAdapter.h"
#include "../src/RedactingDiagnostics.h"
#include <AccountManager.h>
#include <QCoreApplication>
#include <memory>

namespace {
void registerIOSAccountStore() {
    // Synchronous base-application startup, before Application's constructor
    // loads accounts. Do not defer registration to a timer or prompt for access.
    if (!AccountManager::installProtectedAccountStore(std::make_shared<overte::ios::KeychainAccountAdapter>())) {
        overte::ios::logDiagnostic(overte::ios::DiagnosticEvent::SecureStorageUnavailable);
    }
}
}
Q_COREAPP_STARTUP_FUNCTION(registerIOSAccountStore)
