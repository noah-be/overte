// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0

#pragma once

#include <cstdint>
#include <string>
#include <string_view>

namespace overte::ios {

enum class AddressKind {
    Invalid,
    Place,
    Network,
};

struct ParsedAddress {
    AddressKind kind { AddressKind::Invalid };
    std::string host;
    std::string path;
    std::string normalized;
    std::string error;
    std::uint16_t port { 40102 };
    bool explicitPort { false };

    explicit operator bool() const { return kind != AddressKind::Invalid; }
};

ParsedAddress parseOverteAddress(std::string_view input);

} // namespace overte::ios
