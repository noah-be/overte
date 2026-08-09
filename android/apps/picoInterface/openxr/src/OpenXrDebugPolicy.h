#pragma once

#include <cstdint>

enum class OpenXrDebugLogLevel { Debug, Info, Warning, Critical };

constexpr OpenXrDebugLogLevel openXrDebugLogLevel(
        std::uint64_t severity, std::uint64_t verboseBit, std::uint64_t infoBit,
        std::uint64_t warningBit, std::uint64_t errorBit) {
    if ((severity & errorBit) != 0) {
        return OpenXrDebugLogLevel::Critical;
    }
    if ((severity & warningBit) != 0) {
        return OpenXrDebugLogLevel::Warning;
    }
    if ((severity & infoBit) != 0) {
        return OpenXrDebugLogLevel::Info;
    }
    if (severity == 0 || (severity & verboseBit) != 0) {
        return OpenXrDebugLogLevel::Debug;
    }
    return OpenXrDebugLogLevel::Critical;
}
