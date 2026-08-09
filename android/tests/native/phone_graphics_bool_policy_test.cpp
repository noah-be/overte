#include "PhoneGraphicsPolicy.h"
#include "test_assertions.h"

int main() {
    using phone::graphics::parseBoolOverride;

    OVERTE_EXPECT(parseBoolOverride("1", false));
    OVERTE_EXPECT(parseBoolOverride(" ON ", false));
    OVERTE_EXPECT(parseBoolOverride("True", false));
    OVERTE_EXPECT(parseBoolOverride("enabled\n", false));
    OVERTE_EXPECT(!parseBoolOverride("0", true));
    OVERTE_EXPECT(!parseBoolOverride(" OFF ", true));
    OVERTE_EXPECT(!parseBoolOverride("False", true));
    OVERTE_EXPECT(!parseBoolOverride("DISABLED", true));

    OVERTE_EXPECT(parseBoolOverride(nullptr, true));
    OVERTE_EXPECT(!parseBoolOverride("", false));
    OVERTE_EXPECT(parseBoolOverride("yes", true));
    OVERTE_EXPECT(!parseBoolOverride("2", false));
    OVERTE_EXPECT(parseBoolOverride("true-ish", true));
    OVERTE_EXPECT(!parseBoolOverride("true-ish", false));
    OVERTE_EXPECT(parseBoolOverride("\t\r\n\f\venabled\t", false));
    OVERTE_EXPECT(!parseBoolOverride("\t\r\n\f\vdisabled\t", true));
    OVERTE_EXPECT(parseBoolOverride("ENABLED", false));
    OVERTE_EXPECT(!parseBoolOverride("Disabled", true));
    OVERTE_EXPECT(parseBoolOverride(" TRUE ", false));
    OVERTE_EXPECT(!parseBoolOverride(" FALSE ", true));
    OVERTE_EXPECT(parseBoolOverride("\xC4", true));
    OVERTE_EXPECT(!parseBoolOverride("\xC4", false));

    return 0;
}
