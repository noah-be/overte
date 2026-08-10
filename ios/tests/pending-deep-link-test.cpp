// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0

#include "PendingDeepLinkStore.h"

#include <cassert>
#include <string>

using overte::ios::DeepLinkEnqueueResult;
using overte::ios::PendingDeepLinkStore;

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
    return 0;
}
