#include <clocale>
#include <limits>

#include "PhoneGraphicsPolicy.h"
#include "test_assertions.h"

int main() {
    using phone::graphics::parseClampedFloat;

    constexpr float fallback { 0.65f };
    constexpr float minimum { 0.5f };
    constexpr float maximum { 0.7f };

    OVERTE_EXPECT(parseClampedFloat("0.6", fallback, minimum, maximum) == 0.6f);
    OVERTE_EXPECT(parseClampedFloat(" 0.55\n", fallback, minimum, maximum) == 0.55f);
    OVERTE_EXPECT(parseClampedFloat("0", fallback, minimum, maximum) == minimum);
    OVERTE_EXPECT(parseClampedFloat("100", fallback, minimum, maximum) == maximum);
    OVERTE_EXPECT(parseClampedFloat("0.5", fallback, minimum, maximum) == minimum);
    OVERTE_EXPECT(parseClampedFloat("0.7", fallback, minimum, maximum) == maximum);

    OVERTE_EXPECT(parseClampedFloat(nullptr, fallback, minimum, maximum) == fallback);
    OVERTE_EXPECT(parseClampedFloat("", fallback, minimum, maximum) == fallback);
    OVERTE_EXPECT(parseClampedFloat(" ", fallback, minimum, maximum) == fallback);
    OVERTE_EXPECT(parseClampedFloat("0.6junk", fallback, minimum, maximum) == fallback);
    OVERTE_EXPECT(parseClampedFloat("nan", fallback, minimum, maximum) == fallback);
    OVERTE_EXPECT(parseClampedFloat("inf", fallback, minimum, maximum) == fallback);
    OVERTE_EXPECT(parseClampedFloat("1e9999", fallback, minimum, maximum) == fallback);
    OVERTE_EXPECT(parseClampedFloat("0.6", fallback, maximum, minimum) == fallback);
    OVERTE_EXPECT(parseClampedFloat("+0.6", fallback, minimum, maximum) == 0.6f);
    OVERTE_EXPECT(parseClampedFloat("6e-1", fallback, minimum, maximum) == 0.6f);
    OVERTE_EXPECT(parseClampedFloat("-100", fallback, minimum, maximum) == minimum);
    OVERTE_EXPECT(parseClampedFloat("-inf", fallback, minimum, maximum) == fallback);
    OVERTE_EXPECT(parseClampedFloat("-nan", fallback, minimum, maximum) == fallback);
    OVERTE_EXPECT(parseClampedFloat("0x1p-1", fallback, minimum, maximum) == fallback);
    OVERTE_EXPECT(parseClampedFloat("0,6", fallback, minimum, maximum) == fallback);
    OVERTE_EXPECT(parseClampedFloat("++0.6", fallback, minimum, maximum) == fallback);
    OVERTE_EXPECT(parseClampedFloat("0.6 ", fallback, minimum, maximum) == 0.6f);
    OVERTE_EXPECT(parseClampedFloat("\v0.6\f", fallback, minimum, maximum) == 0.6f);

    // Parsing remains property-format/C-locale based even if the process uses
    // a locale whose decimal separator is a comma.
    const char* previousLocale = std::setlocale(LC_NUMERIC, nullptr);
    const std::string savedLocale = previousLocale ? previousLocale : "C";
    const char* localeCandidates[] = { "de_DE.UTF-8", "de_DE.utf8", "de_DE" };
    for (const auto* candidate : localeCandidates) {
        if (std::setlocale(LC_NUMERIC, candidate)) {
            OVERTE_EXPECT(parseClampedFloat("0.6", fallback, minimum, maximum) == 0.6f);
            OVERTE_EXPECT(parseClampedFloat("0,6", fallback, minimum, maximum) == fallback);
            break;
        }
    }
    std::setlocale(LC_NUMERIC, savedLocale.c_str());

    return 0;
}
