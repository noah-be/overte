// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0

#include "PendingDeepLinkStore.h"

#include <algorithm>
#include <cassert>
#include <string>
#include <thread>
#include <unordered_set>
#include <vector>

using overte::ios::DeepLinkEnqueueResult;
using overte::ios::PendingDeepLinkStore;

namespace {

void assertConcurrentDuplicateIsAtomic() {
    PendingDeepLinkStore store;
    constexpr std::size_t THREAD_COUNT { 32 };
    std::vector<DeepLinkEnqueueResult> results(THREAD_COUNT, DeepLinkEnqueueResult::Invalid);
    std::vector<std::thread> threads;
    threads.reserve(THREAD_COUNT);
    for (std::size_t index = 0; index < THREAD_COUNT; ++index) {
        threads.emplace_back([&store, &results, index] {
            results[index] = store.enqueue("overte://concurrency/same");
        });
    }
    for (auto& thread : threads) {
        thread.join();
    }

    assert(std::count(results.begin(), results.end(), DeepLinkEnqueueResult::Accepted) == 1);
    assert(std::count(results.begin(), results.end(), DeepLinkEnqueueResult::Duplicate) ==
        THREAD_COUNT - 1);
    assert(store.size() == 1);
    const auto pending = store.takeAll();
    assert(pending == std::vector<std::string> { "overte://concurrency/same" });
}

void assertConcurrentCapacityIsBounded() {
    PendingDeepLinkStore store;
    constexpr std::size_t THREAD_COUNT { PendingDeepLinkStore::MAX_PENDING_URLS * 2 };
    std::vector<DeepLinkEnqueueResult> results(THREAD_COUNT, DeepLinkEnqueueResult::Invalid);
    std::vector<std::thread> threads;
    threads.reserve(THREAD_COUNT);
    for (std::size_t index = 0; index < THREAD_COUNT; ++index) {
        threads.emplace_back([&store, &results, index] {
            results[index] = store.enqueue("hifi://concurrency/" + std::to_string(index));
        });
    }
    for (auto& thread : threads) {
        thread.join();
    }

    assert(std::count(results.begin(), results.end(), DeepLinkEnqueueResult::Accepted) ==
        PendingDeepLinkStore::MAX_PENDING_URLS);
    assert(std::count(results.begin(), results.end(), DeepLinkEnqueueResult::Full) ==
        THREAD_COUNT - PendingDeepLinkStore::MAX_PENDING_URLS);
    assert(store.size() == PendingDeepLinkStore::MAX_PENDING_URLS);
    const auto pending = store.takeAll();
    const std::unordered_set<std::string> unique(pending.begin(), pending.end());
    assert(unique.size() == PendingDeepLinkStore::MAX_PENDING_URLS);
    assert(store.size() == 0);
}

} // namespace

int main() {
    PendingDeepLinkStore store;
    assert(store.enqueue("overte://example/path?token=private") == DeepLinkEnqueueResult::Accepted);
    assert(store.enqueue("HIFI://example/second") == DeepLinkEnqueueResult::Accepted);
    assert(store.enqueue("overte://example/path?token=private") == DeepLinkEnqueueResult::Duplicate);
    assert(store.size() == 2);

    auto pending = store.takeAll();
    assert(pending.size() == 2);
    assert(pending[0] == "overte://example/path?token=private");
    assert(pending[1] == "HIFI://example/second");
    assert(store.size() == 0);
    assert(store.takeAll().empty());

    assert(store.enqueue("") == DeepLinkEnqueueResult::Invalid);
    assert(store.enqueue("missing-scheme") == DeepLinkEnqueueResult::Invalid);
    assert(store.enqueue(" overte://leading-space") == DeepLinkEnqueueResult::UnsupportedScheme);
    assert(store.enqueue("https://example.com") == DeepLinkEnqueueResult::UnsupportedScheme);
    assert(store.enqueue("overte://line\nbreak") == DeepLinkEnqueueResult::Invalid);
    assert(store.enqueue(std::string(PendingDeepLinkStore::MAX_URL_BYTES + 1, 'a')) ==
        DeepLinkEnqueueResult::Invalid);

    for (std::size_t index = 0; index < PendingDeepLinkStore::MAX_PENDING_URLS; ++index) {
        assert(store.enqueue("overte://capacity/" + std::to_string(index)) ==
            DeepLinkEnqueueResult::Accepted);
    }
    assert(store.enqueue("overte://capacity/overflow") == DeepLinkEnqueueResult::Full);
    assert(store.size() == PendingDeepLinkStore::MAX_PENDING_URLS);

    assertConcurrentDuplicateIsAtomic();
    assertConcurrentCapacityIsBounded();
    return 0;
}
