// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "../../security/storage/ProtectedAccountStore.h"
#include "../src/SecureAccountStore.h"

namespace overte::ios {
// Implements PX-15 v001. No schema or migration logic lives in this adapter.
class KeychainAccountAdapter final : public security::ProtectedAccountStore {
public:
    security::StoreResult read(security::AccountBytes& output) override;
    security::StoreResult write(const security::AccountBytes& input) override;
    security::StoreResult erase() override;
};
} // namespace overte::ios
