// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0

#include "OverteAddress.h"

#include <algorithm>
#include <charconv>
#include <cctype>
#include <utility>

namespace overte::ios {
namespace {

constexpr std::uint16_t DEFAULT_DOMAIN_PORT { 40102 };

std::string_view trim(std::string_view value) {
    while (!value.empty() && std::isspace(static_cast<unsigned char>(value.front())) != 0) {
        value.remove_prefix(1);
    }
    while (!value.empty() && std::isspace(static_cast<unsigned char>(value.back())) != 0) {
        value.remove_suffix(1);
    }
    return value;
}

std::string lowerASCII(std::string_view value) {
    std::string result(value);
    std::transform(result.begin(), result.end(), result.begin(), [](unsigned char character) {
        return static_cast<char>(std::tolower(character));
    });
    return result;
}

bool validPlace(std::string_view value) {
    return !value.empty() && std::all_of(value.begin(), value.end(), [](unsigned char character) {
        return std::isalnum(character) != 0 || character == '_' || character == '-';
    });
}

ParsedAddress invalid(std::string message) {
    ParsedAddress result;
    result.error = std::move(message);
    return result;
}

} // namespace

ParsedAddress parseOverteAddress(std::string_view input) {
    input = trim(input);
    if (input.empty() || input.size() > 2048) {
        return invalid("Enter an Overte place or hifi:// address.");
    }
    if (std::any_of(input.begin(), input.end(), [](unsigned char character) {
            return std::iscntrl(character) != 0;
        })) {
        return invalid("The address contains a control character.");
    }

    auto remainder = input;
    const auto schemeSeparator = remainder.find("://");
    if (schemeSeparator != std::string_view::npos) {
        const auto scheme = lowerASCII(remainder.substr(0, schemeSeparator));
        if (scheme != "hifi" && scheme != "overte") {
            return invalid("Only hifi:// and overte:// addresses are supported.");
        }
        remainder.remove_prefix(schemeSeparator + 3);
    } else if (remainder.find(':') != std::string_view::npos && remainder.front() != '[') {
        const auto possibleScheme = remainder.substr(0, remainder.find(':'));
        if (possibleScheme.find('.') == std::string_view::npos &&
            !std::all_of(possibleScheme.begin(), possibleScheme.end(), [](unsigned char character) {
                return std::isdigit(character) != 0;
            })) {
            return invalid("Use hifi:// before an address containing a port.");
        }
    }

    const auto pathStart = remainder.find_first_of("/?#");
    auto authority = remainder.substr(0, pathStart);
    auto path = pathStart == std::string_view::npos ? std::string_view {} : remainder.substr(pathStart);
    if (authority.empty() || authority.find('@') != std::string_view::npos) {
        return invalid("User lookups are not available in this preview.");
    }

    std::string_view host;
    std::string_view portText;
    if (authority.front() == '[') {
        const auto bracket = authority.find(']');
        if (bracket == std::string_view::npos) {
            return invalid("The IPv6 address is missing its closing bracket.");
        }
        host = authority.substr(1, bracket - 1);
        if (bracket + 1 < authority.size()) {
            if (authority[bracket + 1] != ':') {
                return invalid("Unexpected text after the IPv6 address.");
            }
            portText = authority.substr(bracket + 2);
        }
    } else {
        const auto colon = authority.rfind(':');
        if (colon != std::string_view::npos) {
            host = authority.substr(0, colon);
            portText = authority.substr(colon + 1);
        } else {
            host = authority;
        }
    }
    if (host.empty()) {
        return invalid("The address has no host or place name.");
    }

    ParsedAddress result;
    result.host = lowerASCII(host);
    result.path = std::string(path);
    if (!portText.empty()) {
        unsigned int parsedPort { 0 };
        const auto conversion = std::from_chars(portText.data(), portText.data() + portText.size(), parsedPort);
        if (conversion.ec != std::errc {} || conversion.ptr != portText.data() + portText.size() ||
            parsedPort == 0 || parsedPort > 65535) {
            return invalid("The domain port must be between 1 and 65535.");
        }
        result.port = static_cast<std::uint16_t>(parsedPort);
        result.explicitPort = true;
    } else {
        result.port = DEFAULT_DOMAIN_PORT;
    }

    const bool networkAddress = result.host == "localhost" || result.host.find('.') != std::string::npos ||
        result.host.find(':') != std::string::npos || result.explicitPort;
    if (!networkAddress && !validPlace(result.host)) {
        return invalid("The place name contains unsupported characters.");
    }
    result.kind = networkAddress ? AddressKind::Network : AddressKind::Place;
    const bool ipv6 = result.host.find(':') != std::string::npos;
    result.normalized = "hifi://" + std::string(ipv6 ? "[" : "") + result.host +
        std::string(ipv6 ? "]" : "") + (result.explicitPort ? ":" + std::to_string(result.port) : "") +
        result.path;
    return result;
}

} // namespace overte::ios
