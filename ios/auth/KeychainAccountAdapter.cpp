// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0
#include "KeychainAccountAdapter.h"

namespace overte::ios {
namespace {
constexpr auto ACCOUNT_KEY = "account-map-v1";
security::StoreResult translate(SecureStoreStatus status) noexcept {
    using security::StoreResult;
    switch (status) {
        case SecureStoreStatus::Ok: return StoreResult::Ok;
        case SecureStoreStatus::NotFound: return StoreResult::Absent;
        case SecureStoreStatus::Locked: return StoreResult::Locked;
        case SecureStoreStatus::Unavailable: return StoreResult::Unavailable;
        case SecureStoreStatus::Invalid:
        case SecureStoreStatus::Corrupt: return StoreResult::Corrupt;
        case SecureStoreStatus::Failed: return StoreResult::IoError;
    }
    return StoreResult::IoError;
}
}

security::StoreResult KeychainAccountAdapter::read(security::AccountBytes& output) {
    SecureAccountStore::clear(output);
    try {
        auto status = translate(SecureAccountStore::read(ACCOUNT_KEY, output));
        if (status != security::StoreResult::Ok) { SecureAccountStore::clear(output); }
        return status;
    } catch (...) {
        SecureAccountStore::clear(output);
        return security::StoreResult::IoError;
    }
}
security::StoreResult KeychainAccountAdapter::write(const security::AccountBytes& input) {
    try { return translate(SecureAccountStore::write(ACCOUNT_KEY, input)); }
    catch (...) { return security::StoreResult::IoError; }
}
security::StoreResult KeychainAccountAdapter::erase() {
    try { return translate(SecureAccountStore::remove(ACCOUNT_KEY)); }
    catch (...) { return security::StoreResult::IoError; }
}
} // namespace overte::ios
