#include <string>

#include "PhonePendingHandoff.h"
#include "test_assertions.h"

int main() {
    phone::PendingHandoff<std::string> handoff;
    std::string delivered { "unchanged" };

    OVERTE_EXPECT(!handoff.pending());
    OVERTE_EXPECT(!handoff.takeIfReady(true, delivered));

    // Empty values are still legitimate payloads unless the producer marks
    // them invalid explicitly.
    handoff.replace("");
    OVERTE_EXPECT(handoff.pending());
    OVERTE_EXPECT(handoff.takeIfReady(true, delivered));
    OVERTE_EXPECT(delivered.empty());

    handoff.clear();
    handoff.clear();
    OVERTE_EXPECT(!handoff.pending());
    OVERTE_EXPECT(delivered.empty());

    handoff.replace("hifi://first");
    OVERTE_EXPECT(handoff.pending());
    OVERTE_EXPECT(!handoff.takeIfReady(false, delivered));
    OVERTE_EXPECT(handoff.pending());
    OVERTE_EXPECT(delivered.empty());

    OVERTE_EXPECT(handoff.takeIfReady(true, delivered));
    OVERTE_EXPECT(delivered == "hifi://first");
    OVERTE_EXPECT(!handoff.pending());
    OVERTE_EXPECT(!handoff.takeIfReady(true, delivered));
    OVERTE_EXPECT(delivered == "hifi://first");

    handoff.replace("hifi://second");
    handoff.clear();
    OVERTE_EXPECT(!handoff.pending());
    OVERTE_EXPECT(!handoff.takeIfReady(true, delivered));

    return 0;
}
