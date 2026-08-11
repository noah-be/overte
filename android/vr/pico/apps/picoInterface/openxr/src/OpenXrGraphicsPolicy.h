#pragma once

#include <cstddef>

template<typename Attribute>
inline bool hasRequiredOpenXrEglColorAttributes(
        const Attribute* attributes,
        std::size_t count,
        Attribute terminator,
        Attribute redKey,
        Attribute greenKey,
        Attribute blueKey) {
    if (attributes == nullptr || count == 0) {
        return false;
    }

    bool hasRed = false;
    bool hasGreen = false;
    bool hasBlue = false;
    for (std::size_t i = 0; i < count;) {
        const Attribute key = attributes[i];
        if (key == terminator) {
            return hasRed && hasGreen && hasBlue;
        }
        if (i + 1 >= count) {
            return false;
        }
        hasRed |= key == redKey;
        hasGreen |= key == greenKey;
        hasBlue |= key == blueKey;
        i += 2;
    }
    return false;
}
