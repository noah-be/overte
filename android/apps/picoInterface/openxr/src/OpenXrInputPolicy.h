#pragma once

constexpr float OPENXR_VIRTUAL_TRIGGER_CLICK_THRESHOLD = 0.95f;

constexpr bool openXrVirtualTriggerPressed(bool active, float value) {
    return active && value >= OPENXR_VIRTUAL_TRIGGER_CLICK_THRESHOLD;
}
