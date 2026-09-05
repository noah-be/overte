// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0
#pragma once

#include <cstddef>
#include <cstdint>
#include <string_view>
#include <vector>

namespace overte::ios {

// Native mechanism only. Shared owns serialization, migration and re-auth policy.
enum class SecureStoreStatus { Ok, NotFound, Locked, Unavailable, Invalid, Corrupt, Failed };

class SecureAccountStore final {
public:
    static constexpr std::size_t MAX_VALUE_BYTES = 1024 * 1024;
    static constexpr std::size_t MAX_KEY_BYTES = 128;

    // Opaque bounded ASCII keys, never endpoints or usernames. No logs, UI,
    // synchronization, plaintext fallback, or process-global credential cache.
    static SecureStoreStatus read(std::string_view key, std::vector<std::uint8_t>& value);
    static SecureStoreStatus write(std::string_view key, const std::vector<std::uint8_t>& value);
    static SecureStoreStatus remove(std::string_view key);
    static bool validKey(std::string_view key) noexcept;
    static void clear(std::vector<std::uint8_t>& value) noexcept;
};

} // namespace overte::ios
