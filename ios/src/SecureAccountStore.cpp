// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0
#include "SecureAccountStore.h"

namespace overte::ios {
bool SecureAccountStore::validKey(std::string_view key) noexcept {
    if (key.empty() || key.size() > MAX_KEY_BYTES) {
        return false;
    }
    for (const auto c : key) {
        if (!((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') ||
              (c >= '0' && c <= '9') || c == '-' || c == '_' || c == '.')) {
            return false;
        }
    }
    return true;
}

void SecureAccountStore::clear(std::vector<std::uint8_t>& value) noexcept {
    // Overwrite the owned live bytes before releasing their logical contents.
    // This does not promise erasure of copies made by the OS/serialization layer.
    volatile std::uint8_t* bytes = value.data();
    for (std::size_t i = 0; i < value.size(); ++i) {
        bytes[i] = 0;
    }
    value.clear();
}
} // namespace overte::ios
