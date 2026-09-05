// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0
#include "SecureAccountStore.h"
#include "RedactingDiagnostics.h"
#include <cassert>
#include <string>
#include <string_view>
using namespace overte::ios;
int main() {
    assert(SecureAccountStore::validKey("account-map.v1"));
    assert(!SecureAccountStore::validKey(""));
    assert(!SecureAccountStore::validKey("https://private.example/user"));
    assert(!SecureAccountStore::validKey("user@example.test"));
    assert(!SecureAccountStore::validKey(std::string_view("abc\0secret", 10)));
    assert(!SecureAccountStore::validKey(std::string(129, 'a')));
    assert(SecureAccountStore::validKey(std::string(128, 'a')));
    std::vector<std::uint8_t> value { 1, 2, 3, 4 };
    SecureAccountStore::clear(value);
    assert(value.empty());
    SecureAccountStore::clear(value);
    assert(std::string_view(diagnosticEventCode(static_cast<DiagnosticEvent>(-1))) == "unknown_event");
    for (int i = 0; i <= static_cast<int>(DiagnosticEvent::RecoveryExhausted); ++i) {
        std::string_view code = diagnosticEventCode(static_cast<DiagnosticEvent>(i));
        assert(code.size() < 64);
        for (char c : code) { assert((c >= 'a' && c <= 'z') || c == '_'); }
    }
}
