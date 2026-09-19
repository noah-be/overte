// SPDX-License-Identifier: Apache-2.0
#include "../../../apps/picoInterface/security/RedactingDiagnostics.h"
#include <cassert>
#include <iostream>
#include <string>
static std::string lastTag, lastText;
static int lastLevel;
extern "C" int __android_log_write(int priority, const char* tag, const char* text) {
    lastTag = tag; lastText = text; lastLevel = priority; return 0;
}
int main() {
    using namespace overte::security;
    for (int i = -1; i <= static_cast<int>(DiagnosticEvent::CallbackDiscarded) + 1; ++i) {
        auto event = static_cast<DiagnosticEvent>(i);
        overte::pico::diagnosticError(event);
        assert(lastTag == "OvertePico" && lastText == diagnosticEvent(event) && lastLevel == ANDROID_LOG_ERROR);
        overte::pico::diagnosticWarning(event);
        assert(lastTag == "OvertePico" && lastText == diagnosticEvent(event) && lastLevel == ANDROID_LOG_WARN);
        assert(lastText == sanitizeDiagnostic(lastText.data(), lastText.size()));
    }
    std::cout << "Pico production native log wrapper PASS (captured sink, not logcat)\n";
}
