// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0

#include "PendingDeepLinkStore.h"

#include <algorithm>
#include <cctype>
#include <iterator>

namespace overte::ios {
namespace {

bool containsControlCharacter(std::string_view value) {
    return std::any_of(value.begin(), value.end(), [](unsigned char character) {
        return std::iscntrl(character) != 0;
    });
}

std::string lowerASCII(std::string_view value) {
    std::string result(value);
    std::transform(result.begin(), result.end(), result.begin(), [](unsigned char character) {
        return static_cast<char>(std::tolower(character));
    });
    return result;
}

} // namespace

PendingDeepLinkStore& PendingDeepLinkStore::instance() {
    static PendingDeepLinkStore store;
    return store;
}

DeepLinkEnqueueResult PendingDeepLinkStore::enqueue(std::string_view url) {
    if (url.empty() || url.size() > MAX_URL_BYTES || containsControlCharacter(url)) {
        return DeepLinkEnqueueResult::Invalid;
    }
    const auto separator = url.find(':');
    if (separator == std::string_view::npos || separator == 0) {
        return DeepLinkEnqueueResult::Invalid;
    }
    const auto scheme = lowerASCII(url.substr(0, separator));
    if (scheme != "overte" && scheme != "hifi") {
        return DeepLinkEnqueueResult::UnsupportedScheme;
    }

    std::lock_guard guard(_mutex);
    if (std::find(_pending.begin(), _pending.end(), url) != _pending.end()) {
        return DeepLinkEnqueueResult::Duplicate;
    }
    if (_pending.size() >= MAX_PENDING_URLS) {
        return DeepLinkEnqueueResult::Full;
    }
    _pending.emplace_back(url);
    return DeepLinkEnqueueResult::Accepted;
}

std::vector<std::string> PendingDeepLinkStore::takeAll() {
    std::lock_guard guard(_mutex);
    std::vector<std::string> result;
    result.reserve(_pending.size());
    std::move(_pending.begin(), _pending.end(), std::back_inserter(result));
    _pending.clear();
    return result;
}

std::size_t PendingDeepLinkStore::size() const {
    std::lock_guard guard(_mutex);
    return _pending.size();
}

} // namespace overte::ios
