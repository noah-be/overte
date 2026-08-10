#include <limits>

#include "PhoneGraphicsPolicy.h"
#include "test_assertions.h"

int main() {
    using phone::graphics::parseClampedUnsigned;

    constexpr unsigned int fallback { 256 };
    constexpr unsigned int minimum { 128 };
    constexpr unsigned int maximum { 384 };

    OVERTE_EXPECT(parseClampedUnsigned("256", fallback, minimum, maximum) == 256U);
    OVERTE_EXPECT(parseClampedUnsigned(" 300\n", fallback, minimum, maximum) == 300U);
    OVERTE_EXPECT(parseClampedUnsigned("0", fallback, minimum, maximum) == minimum);
    OVERTE_EXPECT(parseClampedUnsigned("127", fallback, minimum, maximum) == minimum);
    OVERTE_EXPECT(parseClampedUnsigned("385", fallback, minimum, maximum) == maximum);
    OVERTE_EXPECT(parseClampedUnsigned("999999", fallback, minimum, maximum) == maximum);

    OVERTE_EXPECT(parseClampedUnsigned(nullptr, fallback, minimum, maximum) == fallback);
    OVERTE_EXPECT(parseClampedUnsigned("", fallback, minimum, maximum) == fallback);
    OVERTE_EXPECT(parseClampedUnsigned("-1", fallback, minimum, maximum) == fallback);
    OVERTE_EXPECT(parseClampedUnsigned("12MB", fallback, minimum, maximum) == fallback);
    OVERTE_EXPECT(parseClampedUnsigned("184467440737095516160", fallback, minimum, maximum) == fallback);
    OVERTE_EXPECT(parseClampedUnsigned("256", fallback, maximum, minimum) == fallback);
    OVERTE_EXPECT(parseClampedUnsigned("+256", fallback, minimum, maximum) == 256U);
    OVERTE_EXPECT(parseClampedUnsigned("000256", fallback, minimum, maximum) == 256U);
    OVERTE_EXPECT(parseClampedUnsigned("128", fallback, minimum, maximum) == minimum);
    OVERTE_EXPECT(parseClampedUnsigned("384", fallback, minimum, maximum) == maximum);
    OVERTE_EXPECT(parseClampedUnsigned("0x100", fallback, minimum, maximum) == fallback);
    OVERTE_EXPECT(parseClampedUnsigned("256.0", fallback, minimum, maximum) == fallback);
    OVERTE_EXPECT(parseClampedUnsigned("  -1", fallback, minimum, maximum) == fallback);
    OVERTE_EXPECT(parseClampedUnsigned("++256", fallback, minimum, maximum) == fallback);
    OVERTE_EXPECT(parseClampedUnsigned("4294967295", fallback, minimum, maximum) == maximum);
    OVERTE_EXPECT(parseClampedUnsigned("4294967296", fallback, minimum, maximum) == fallback);

    return 0;
}
