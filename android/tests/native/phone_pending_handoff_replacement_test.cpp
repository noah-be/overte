#include <string>

#include "PhonePendingHandoff.h"
#include "test_assertions.h"

int main() {
    phone::PendingHandoff<std::string> handoff;
    std::string delivered;

    // Multiple Android intents before Qt startup retain only the newest URL.
    handoff.replace("hifi://first");
    handoff.replace("hifi://second");
    handoff.replace("hifi://latest");
    OVERTE_EXPECT(handoff.takeIfReady(true, delivered));
    OVERTE_EXPECT(delivered == "hifi://latest");

    // An invalid newer handoff deliberately clears a stale valid value.
    handoff.replace("hifi://stale");
    handoff.replace("", false);
    OVERTE_EXPECT(!handoff.pending());
    OVERTE_EXPECT(!handoff.takeIfReady(true, delivered));
    OVERTE_EXPECT(delivered == "hifi://latest");

    // Readiness can be observed repeatedly without consuming the pending URL.
    handoff.replace("hifi://after-startup");
    for (int attempt = 0; attempt < 100; ++attempt) {
        OVERTE_EXPECT(!handoff.takeIfReady(false, delivered));
        OVERTE_EXPECT(handoff.pending());
    }
    OVERTE_EXPECT(handoff.takeIfReady(true, delivered));
    OVERTE_EXPECT(delivered == "hifi://after-startup");

    return 0;
}
