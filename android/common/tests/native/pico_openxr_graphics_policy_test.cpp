#include "OpenXrGraphicsPolicy.h"

#include <cassert>
#include <cstddef>

namespace {
constexpr int TERMINATOR = 0;
constexpr int RED = 1;
constexpr int GREEN = 2;
constexpr int BLUE = 3;
constexpr int SURFACE = 4;

template<typename Value, std::size_t Size>
constexpr std::size_t arrayCount(const Value (&)[Size]) {
    return Size;
}
}

int main() {
    assert(!hasRequiredOpenXrEglColorAttributes<int>(
        nullptr, 0, TERMINATOR, RED, GREEN, BLUE));

    const int complete[] = {
        RED, 8, GREEN, 8, BLUE, 8, SURFACE, 16, TERMINATOR,
    };
    assert(hasRequiredOpenXrEglColorAttributes(
        complete, arrayCount(complete), TERMINATOR, RED, GREEN, BLUE));

    const int duplicateRed[] = {
        RED, 8, GREEN, 8, RED, 8, TERMINATOR,
    };
    assert(!hasRequiredOpenXrEglColorAttributes(
        duplicateRed, arrayCount(duplicateRed), TERMINATOR, RED, GREEN, BLUE));

    const int missingRed[] = { GREEN, 8, BLUE, 8, TERMINATOR };
    const int missingGreen[] = { RED, 8, BLUE, 8, TERMINATOR };
    const int missingBlue[] = { RED, 8, GREEN, 8, TERMINATOR };
    assert(!hasRequiredOpenXrEglColorAttributes(
        missingRed, arrayCount(missingRed), TERMINATOR, RED, GREEN, BLUE));
    assert(!hasRequiredOpenXrEglColorAttributes(
        missingGreen, arrayCount(missingGreen), TERMINATOR, RED, GREEN, BLUE));
    assert(!hasRequiredOpenXrEglColorAttributes(
        missingBlue, arrayCount(missingBlue), TERMINATOR, RED, GREEN, BLUE));

    const int truncated[] = { RED, 8, GREEN };
    const int unterminated[] = { RED, 8, GREEN, 8, BLUE, 8 };
    assert(!hasRequiredOpenXrEglColorAttributes(
        truncated, arrayCount(truncated), TERMINATOR, RED, GREEN, BLUE));
    assert(!hasRequiredOpenXrEglColorAttributes(
        unterminated, arrayCount(unterminated), TERMINATOR, RED, GREEN, BLUE));

    const int afterTerminator[] = {
        RED, 8, GREEN, 8, TERMINATOR, BLUE, 8,
    };
    assert(!hasRequiredOpenXrEglColorAttributes(
        afterTerminator, arrayCount(afterTerminator), TERMINATOR, RED, GREEN, BLUE));

    const int blueOnlyAsValue[] = {
        RED, BLUE, GREEN, 8, SURFACE, 16, TERMINATOR,
    };
    assert(!hasRequiredOpenXrEglColorAttributes(
        blueOnlyAsValue, arrayCount(blueOnlyAsValue),
        TERMINATOR, RED, GREEN, BLUE));
    return 0;
}
