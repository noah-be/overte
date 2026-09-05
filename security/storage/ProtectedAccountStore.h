// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <algorithm>
#include <cstdint>
#include <functional>
#include <memory>
#include <mutex>
#include <vector>

namespace overte { namespace security {
using AccountBytes = std::vector<std::uint8_t>;
enum class StoreResult { Ok, Absent, Locked, Unavailable, Corrupt, IoError, ReauthRequired };
constexpr std::size_t MAX_ACCOUNT_BYTES = 1024 * 1024;

// Implement with platform protected storage. Never retain plaintext in a file,
// log or callback beyond the operation. Methods must not call back into AccountManager.
class ProtectedAccountStore {
public:
    virtual ~ProtectedAccountStore() = default;
    virtual StoreResult read(AccountBytes& output) = 0;
    virtual StoreResult write(const AccountBytes& input) = 0;
    virtual StoreResult erase() = 0;
};

inline void clearAccountBytes(AccountBytes& bytes) {
    volatile std::uint8_t* data = bytes.empty() ? nullptr : bytes.data();
    for (std::size_t i = 0; i < bytes.size(); ++i) { data[i] = 0; }
    bytes.clear();
}

// These callbacks are owned by Shared code; adapters never parse legacy files.
struct LegacyAccountInput {
    std::function<StoreResult(AccountBytes&)> read;
    std::function<bool()> erase;
};

class AccountStoreCoordinator {
public:
    // Registration is single-assignment, but a missing-adapter read does not
    // latch the registry. An owner may bind on native startup before retrying.
    bool install(std::shared_ptr<ProtectedAccountStore> adapter) {
        std::lock_guard<std::mutex> lock(_mutex);
        if (!adapter || _adapter) { return false; }
        _adapter = std::move(adapter);
        return true;
    }

    StoreResult read(AccountBytes& output, const LegacyAccountInput& legacy) {
        std::lock_guard<std::mutex> lock(_mutex);
        clearAccountBytes(output);
        if (!_adapter) { return StoreResult::Unavailable; }
        if (_quarantined) { return StoreResult::ReauthRequired; }
        AccountBytes protectedBytes;
        auto result = _adapter->read(protectedBytes);
        if (result == StoreResult::Ok) {
            if (!valid(protectedBytes)) { clearAccountBytes(protectedBytes); return quarantine(); }
            // Protected data is authoritative after interrupted migration. The
            // legacy copy must be gone before credentials become available.
            if (!legacy.erase()) { clearAccountBytes(protectedBytes); return quarantine(); }
            output.swap(protectedBytes);
            return StoreResult::Ok;
        }
        clearAccountBytes(protectedBytes);
        if (result != StoreResult::Absent) { return result; }
        AccountBytes old;
        result = legacy.read(old);
        if (result != StoreResult::Ok) { clearAccountBytes(old); return result; }
        if (!valid(old)) { clearAccountBytes(old); return quarantine(); }
        result = writeVerified(old);
        if (result == StoreResult::Ok && !legacy.erase()) { result = quarantine(); }
        if (result == StoreResult::Ok) { output.swap(old); }
        clearAccountBytes(old);
        return result;
    }

    StoreResult write(const AccountBytes& input, const LegacyAccountInput& legacy) {
        std::lock_guard<std::mutex> lock(_mutex);
        if (!_adapter) { return StoreResult::Unavailable; }
        if (_quarantined) { return StoreResult::ReauthRequired; }
        if (!valid(input)) { return StoreResult::Corrupt; }
        auto result = writeVerified(input);
        if (result == StoreResult::Ok && !legacy.erase()) { return quarantine(); }
        return result;
    }

    StoreResult erase(const LegacyAccountInput& legacy) {
        std::lock_guard<std::mutex> lock(_mutex);
        // Always remove legacy credentials on logout, including when native
        // registration is absent. Never load/migrate old data during logout.
        const bool legacyRemoved = legacy.erase();
        if (!_adapter) { _quarantined = true; return StoreResult::Unavailable; }
        auto result = _adapter->erase();
        const bool erased = result == StoreResult::Ok || result == StoreResult::Absent;
        _quarantined = !legacyRemoved || !erased;
        return _quarantined ? StoreResult::ReauthRequired : StoreResult::Ok;
    }

private:
    static bool valid(const AccountBytes& bytes) { return !bytes.empty() && bytes.size() <= MAX_ACCOUNT_BYTES; }
    StoreResult quarantine() { _quarantined = true; return StoreResult::ReauthRequired; }
    StoreResult writeVerified(const AccountBytes& bytes) {
        auto result = _adapter->write(bytes);
        if (result != StoreResult::Ok) { return quarantine(); }
        AccountBytes readback;
        result = _adapter->read(readback);
        const bool matches = result == StoreResult::Ok && readback == bytes;
        clearAccountBytes(readback);
        return matches ? StoreResult::Ok : quarantine();
    }
    std::mutex _mutex;
    std::shared_ptr<ProtectedAccountStore> _adapter;
    bool _quarantined { false };
};
}} // namespace overte::security
