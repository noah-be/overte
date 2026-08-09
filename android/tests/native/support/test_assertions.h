#pragma once

#include <iostream>

namespace overte_test {

inline int reportFailure(const char* expression, const char* file, int line) {
    std::cerr << file << ':' << line << ": expectation failed: " << expression << '\n';
    return 1;
}

} // namespace overte_test

#define OVERTE_EXPECT(expression)                                                \
    do {                                                                         \
        if (!(expression)) {                                                     \
            return ::overte_test::reportFailure(#expression, __FILE__, __LINE__); \
        }                                                                        \
    } while (false)
