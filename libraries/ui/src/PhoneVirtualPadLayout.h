// Phone control geometry shared between UI input and presentation threads.
#pragma once
#include <cmath>
#include <cstdint>
#include <mutex>

namespace VirtualPad {
struct PhoneLayout {
    float padDiameter { 0 }, buttonDiameter { 0 }, buttonRadius { 0 };
    float centerX { 0 }, centerY { 0 }, buttonX { 0 }, jumpY { 0 }, secondaryY { 0 };
    bool buttonsVisible { false };
    uint64_t revision { 0 };
};

class PhoneLayoutMailbox {
public:
    bool publish(PhoneLayout layout) {
        const float values[] = { layout.padDiameter, layout.buttonDiameter, layout.buttonRadius,
            layout.centerX, layout.centerY, layout.buttonX, layout.jumpY, layout.secondaryY };
        for (float value : values) {
            if (!std::isfinite(value)) { return false; }
        }
        if (layout.padDiameter <= 0 || layout.buttonDiameter <= 0 || layout.buttonRadius <= 0) { return false; }
        std::lock_guard<std::mutex> lock(_mutex);
        const auto& old = _layout;
        if (old.revision && old.padDiameter == layout.padDiameter && old.buttonDiameter == layout.buttonDiameter &&
            old.buttonRadius == layout.buttonRadius && old.centerX == layout.centerX && old.centerY == layout.centerY &&
            old.buttonX == layout.buttonX && old.jumpY == layout.jumpY && old.secondaryY == layout.secondaryY &&
            old.buttonsVisible == layout.buttonsVisible) { return false; }
        layout.revision = old.revision + 1;
        _layout = layout;
        return true;
    }
    PhoneLayout read() const {
        std::lock_guard<std::mutex> lock(_mutex);
        return _layout;
    }
private:
    mutable std::mutex _mutex;
    PhoneLayout _layout;
};
}
