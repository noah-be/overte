// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0
// Test-only native fault substitution. The real adapter and Shared coordinator
// execute unchanged; this does not assert SecItem/locked-device behavior.
#include "../../auth/KeychainAccountAdapter.h"
#include <cassert>
#include <stdexcept>
using namespace overte::ios;
using namespace overte::security;
namespace {
SecureStoreStatus nativeStatus = SecureStoreStatus::NotFound;
AccountBytes nativeBytes;
bool throws = false;
int legacyReads = 0;
void checkKey(std::string_view key) {
    assert(key == "account-map-v1");
    if (throws) { throw std::runtime_error("synthetic native failure"); }
}
}
namespace overte::ios {
SecureStoreStatus SecureAccountStore::read(std::string_view key, AccountBytes& bytes) {
    checkKey(key);
    bytes = nativeStatus == SecureStoreStatus::Ok ? nativeBytes : AccountBytes { 99 };
    return nativeStatus;
}
SecureStoreStatus SecureAccountStore::write(std::string_view key, const AccountBytes& bytes) {
    checkKey(key);
    if (nativeStatus == SecureStoreStatus::NotFound || nativeStatus == SecureStoreStatus::Ok) {
        nativeBytes = bytes;
        return nativeStatus = SecureStoreStatus::Ok;
    }
    return nativeStatus;
}
SecureStoreStatus SecureAccountStore::remove(std::string_view key) {
    checkKey(key);
    if (nativeStatus == SecureStoreStatus::Ok || nativeStatus == SecureStoreStatus::NotFound) {
        nativeBytes.clear(); nativeStatus = SecureStoreStatus::NotFound;
        return SecureStoreStatus::Ok;
    }
    return nativeStatus;
}
}
int main() {
    auto adapter = std::make_shared<KeychainAccountAdapter>();
    AccountBytes output { 7 };
    for (auto pair : { std::pair { SecureStoreStatus::NotFound, StoreResult::Absent },
                      { SecureStoreStatus::Locked, StoreResult::Locked },
                      { SecureStoreStatus::Unavailable, StoreResult::Unavailable },
                      { SecureStoreStatus::Invalid, StoreResult::Corrupt },
                      { SecureStoreStatus::Corrupt, StoreResult::Corrupt },
                      { SecureStoreStatus::Failed, StoreResult::IoError } }) {
        nativeStatus = pair.first;
        assert(adapter->read(output) == pair.second && output.empty());
    }
    throws = true;
    assert(adapter->read(output) == StoreResult::IoError && output.empty());
    assert(adapter->write({ 1 }) == StoreResult::IoError);
    assert(adapter->erase() == StoreResult::IoError);
    throws = false;
    AccountStoreCoordinator coordinator;
    assert(coordinator.install(adapter));
    assert(!coordinator.install(adapter));
    LegacyAccountInput legacy {
        [](AccountBytes& bytes) { ++legacyReads; bytes = { 1, 2, 3 }; return StoreResult::Ok; },
        [] { return true; }
    };
    nativeStatus = SecureStoreStatus::Locked;
    assert(coordinator.read(output, legacy) == StoreResult::Locked && legacyReads == 0);
    nativeStatus = SecureStoreStatus::NotFound;
    assert(coordinator.read(output, legacy) == StoreResult::Ok);
    assert((output == AccountBytes { 1, 2, 3 }) && legacyReads == 1);
    nativeStatus = SecureStoreStatus::Locked;
    assert(coordinator.erase(legacy) == StoreResult::ReauthRequired);
    assert(coordinator.read(output, legacy) == StoreResult::ReauthRequired && output.empty());
    nativeStatus = SecureStoreStatus::Ok;
    assert(coordinator.erase(legacy) == StoreResult::Ok && nativeBytes.empty());
}
