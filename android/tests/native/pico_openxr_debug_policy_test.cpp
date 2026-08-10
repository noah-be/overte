#include "OpenXrDebugPolicy.h"

#include "support/test_assertions.h"

int main() {
    constexpr std::uint64_t VERBOSE = 1;
    constexpr std::uint64_t INFO = 16;
    constexpr std::uint64_t WARNING = 256;
    constexpr std::uint64_t ERROR = 4096;

    OVERTE_EXPECT(OpenXrDebugLogLevel::Debug ==
            openXrDebugLogLevel(0, VERBOSE, INFO, WARNING, ERROR));
    OVERTE_EXPECT(OpenXrDebugLogLevel::Debug ==
            openXrDebugLogLevel(VERBOSE, VERBOSE, INFO, WARNING, ERROR));
    OVERTE_EXPECT(OpenXrDebugLogLevel::Info ==
            openXrDebugLogLevel(INFO, VERBOSE, INFO, WARNING, ERROR));
    OVERTE_EXPECT(OpenXrDebugLogLevel::Warning ==
            openXrDebugLogLevel(WARNING, VERBOSE, INFO, WARNING, ERROR));
    OVERTE_EXPECT(OpenXrDebugLogLevel::Critical ==
            openXrDebugLogLevel(ERROR, VERBOSE, INFO, WARNING, ERROR));

    OVERTE_EXPECT(OpenXrDebugLogLevel::Warning ==
            openXrDebugLogLevel(VERBOSE | INFO | WARNING,
                                VERBOSE, INFO, WARNING, ERROR));
    OVERTE_EXPECT(OpenXrDebugLogLevel::Critical ==
            openXrDebugLogLevel(VERBOSE | ERROR,
                                VERBOSE, INFO, WARNING, ERROR));
    OVERTE_EXPECT(OpenXrDebugLogLevel::Critical ==
            openXrDebugLogLevel(1ULL << 63, VERBOSE, INFO, WARNING, ERROR));
    return 0;
}
