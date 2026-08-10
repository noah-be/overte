#pragma once

#include <cerrno>
#include <cmath>
#include <cstdlib>
#include <limits>
#include <locale>
#include <sstream>
#include <string>

namespace phone {
namespace graphics {

inline std::string trimPropertyValue(const char* value) {
    if (!value) {
        return {};
    }

    const std::string input { value };
    const auto first = input.find_first_not_of(" \t\n\r\f\v");
    if (first == std::string::npos) {
        return {};
    }
    const auto last = input.find_last_not_of(" \t\n\r\f\v");
    return input.substr(first, last - first + 1);
}

inline char asciiLower(char value) {
    return value >= 'A' && value <= 'Z' ? static_cast<char>(value - 'A' + 'a') : value;
}

inline bool parseBoolOverride(const char* value, bool fallback) {
    auto normalized = trimPropertyValue(value);
    for (auto& character : normalized) {
        character = asciiLower(character);
    }

    if (normalized == "1" || normalized == "on" || normalized == "true" || normalized == "enabled") {
        return true;
    }
    if (normalized == "0" || normalized == "off" || normalized == "false" || normalized == "disabled") {
        return false;
    }
    return fallback;
}

inline float parseClampedFloat(const char* value, float fallback, float minimum, float maximum) {
    const auto normalized = trimPropertyValue(value);
    if (normalized.empty() || minimum > maximum) {
        return fallback;
    }

    // Android properties use a locale-independent decimal representation.
    // A classic-locale stream preserves the former QString::toFloat contract:
    // decimal/exponent syntax is accepted, while locale commas and hex floats
    // are rejected regardless of the process locale.
    std::istringstream parser { normalized };
    parser.imbue(std::locale::classic());
    float parsed { 0.0f };
    parser >> parsed;
    if (!parser || parser.peek() != std::char_traits<char>::eof() || !std::isfinite(parsed)) {
        return fallback;
    }
    return parsed < minimum ? minimum : parsed > maximum ? maximum : parsed;
}

inline unsigned int parseClampedUnsigned(
        const char* value, unsigned int fallback, unsigned int minimum, unsigned int maximum) {
    const auto normalized = trimPropertyValue(value);
    if (normalized.empty() || normalized.front() == '-' || minimum > maximum) {
        return fallback;
    }

    char* parseEnd { nullptr };
    errno = 0;
    const unsigned long parsed = std::strtoul(normalized.c_str(), &parseEnd, 10);
    if (errno == ERANGE || parseEnd == normalized.c_str() || *parseEnd != '\0' ||
            parsed > std::numeric_limits<unsigned int>::max()) {
        return fallback;
    }

    const auto requested = static_cast<unsigned int>(parsed);
    return requested < minimum ? minimum : requested > maximum ? maximum : requested;
}

} // namespace graphics
} // namespace phone
