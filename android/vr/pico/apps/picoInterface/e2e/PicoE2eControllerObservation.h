#pragma once

namespace controller { class UserInputMapper; }

namespace overte::pico::e2e {
// Observe the same standard endpoints exposed by Controller.getValue and
// getPoseValue, after the real input mapper has processed the hardware frame.
void observeControllerFrame(const controller::UserInputMapper& mapper);
}
