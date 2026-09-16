// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <cstdint>
#include <initializer_list>
class QObject;
class ResourceCache;
namespace overte::ios {
// Cache accounting is source-dependent, not a physical-memory quota.
struct MemoryCacheBudget { ResourceCache* cache; std::uint64_t bytes; };
void installFullClientMemoryGuard(QObject* lifetime, std::initializer_list<MemoryCacheBudget> caches);
}
