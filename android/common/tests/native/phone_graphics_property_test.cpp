#include <algorithm>
#include <cmath>
#include <cstdint>
#include <string>

#include "PhoneGraphicsPolicy.h"
#include "test_assertions.h"

namespace {

uint64_t next(uint64_t& state) {
    state = state * UINT64_C(6364136223846793005) + UINT64_C(1442695040888963407);
    return state;
}

} // namespace

int main() {
    using phone::graphics::parseBoolOverride;
    using phone::graphics::parseClampedFloat;
    using phone::graphics::parseClampedUnsigned;

    // Fixed seed makes every generated failure exactly replayable.
    uint64_t state { UINT64_C(0x50484f4e4550524f) };
    for (int index = 0; index < 1024; ++index) {
        const unsigned requested = static_cast<unsigned>(next(state) % 10000U);
        const std::string unsignedText = " \t" + std::to_string(requested) + "\n";
        const unsigned expectedUnsigned = std::max(128U, std::min(384U, requested));
        OVERTE_EXPECT(parseClampedUnsigned(unsignedText.c_str(), 256U, 128U, 384U) == expectedUnsigned);
        OVERTE_EXPECT(parseClampedUnsigned((unsignedText + "x").c_str(), 256U, 128U, 384U) == 256U);

        const int hundredths = static_cast<int>(next(state) % 401U) - 200;
        const int magnitude = std::abs(hundredths);
        const std::string floatText = (hundredths < 0 ? "-" : "") +
            std::to_string(magnitude / 100) + "." +
            std::to_string(magnitude % 100 + 100).substr(1);
        const float parsed = parseClampedFloat(floatText.c_str(), 0.65f, 0.5f, 0.7f);
        const float requestedFloat = static_cast<float>(hundredths) / 100.0f;
        const float expectedFloat = std::max(0.5f, std::min(0.7f, requestedFloat));
        OVERTE_EXPECT(std::fabs(parsed - expectedFloat) < 0.000001f);
        OVERTE_EXPECT(parseClampedFloat((floatText + "junk").c_str(), 0.65f, 0.5f, 0.7f) == 0.65f);

        const bool expected = (next(state) & 1U) != 0;
        const char* token = expected ? "enabled" : "disabled";
        std::string varied { " \t" };
        for (const char character : std::string(token)) {
            varied += (next(state) & 1U) ? phone::graphics::asciiLower(character)
                                         : static_cast<char>(character - 'a' + 'A');
        }
        varied += "\r\n";
        OVERTE_EXPECT(parseBoolOverride(varied.c_str(), !expected) == expected);
    }
    return 0;
}
