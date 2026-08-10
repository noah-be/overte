#include <memory>

#include "PhonePendingHandoff.h"
#include "test_assertions.h"

int main() {
    phone::PendingHandoff<std::unique_ptr<int>> handoff;
    std::unique_ptr<int> delivered;

    handoff.replace(std::unique_ptr<int> { new int { 42 } });
    OVERTE_EXPECT(handoff.pending());
    OVERTE_EXPECT(handoff.takeIfReady(true, delivered));
    OVERTE_EXPECT(delivered != nullptr);
    OVERTE_EXPECT(*delivered == 42);

    handoff.replace(std::unique_ptr<int> { new int { 8 } });
    OVERTE_EXPECT(!handoff.takeIfReady(false, delivered));
    OVERTE_EXPECT(handoff.pending());
    OVERTE_EXPECT(*delivered == 42);
    OVERTE_EXPECT(handoff.takeIfReady(true, delivered));
    OVERTE_EXPECT(*delivered == 8);
    OVERTE_EXPECT(!handoff.pending());

    handoff.replace(std::unique_ptr<int> { new int { 7 } });
    handoff.replace(std::unique_ptr<int> {}, false);
    OVERTE_EXPECT(!handoff.takeIfReady(true, delivered));
    OVERTE_EXPECT(*delivered == 8);

    return 0;
}
