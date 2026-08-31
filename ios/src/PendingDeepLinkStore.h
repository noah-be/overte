// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0

#pragma once

#include <cstddef>
#include <deque>
#include <mutex>
#include <string>
#include <string_view>
#include <vector>

namespace overte::ios {

enum class DeepLinkEnqueueResult {
    Accepted,
    Duplicate,
    Invalid,
    UnsupportedScheme,
    Full,
};

class PendingDeepLinkStore {
public:
    static constexpr std::size_t MAX_PENDING_URLS { 16 };
    static constexpr std::size_t MAX_URL_BYTES { 4096 };

    static PendingDeepLinkStore& instance();

    DeepLinkEnqueueResult enqueue(std::string_view url);
    std::vector<std::string> takeAll();
    std::size_t size() const;

private:
    mutable std::mutex _mutex;
    std::deque<std::string> _pending;
};

} // namespace overte::ios
