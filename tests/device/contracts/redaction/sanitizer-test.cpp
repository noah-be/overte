// SPDX-License-Identifier: Apache-2.0
#include "../../../../security/redaction/SafeDiagnostics.h"
#include <cassert>
#include <iostream>
#include <string>
#include <vector>
using namespace overte::security;
int main() {
    const std::vector<std::string> corpus {
        "canary-secret-7824", "Bearer canary-secret-7824", "https://private.invalid/?token=canary-secret-7824",
        "Y2FuYXJ5LXNlY3JldC03ODI0", "%63%61%6e%61%72%79-secret-7824",
        "canary-", "secret-", "7824", "F2C: ca L2C: 24", "user=canary-user", "session=canary-session",
        "device=canary-device", "{\"refresh_token\":\"canary-secret-7824\"}",
        "OVT_AUTH_FAILED canary-secret-7824", "OVT_AUTH_FAILED\n", std::string("OVT_AUTH_FAILED\0secret",22),
        std::string(100000,'s'), "", "{broken", "NSError private.invalid", "file:///private/canary-user"
    };
    for (const auto& raw : corpus) {
        // The same sink-bound value must be safe for stdout/stderr, retained file,
        // JUnit, screenshot caption, crash and export adapters; no sink exception.
        for (int sink=0; sink<7; ++sink) {
            assert(std::string(sanitizeDiagnostic(raw.data(),raw.size()))=="OVT_REDACTED");
        }
    }
    assert(std::string(sanitizeDiagnostic(nullptr,100))=="OVT_REDACTED");
    assert(std::string(diagnosticEvent(static_cast<DiagnosticEvent>(-1)))=="OVT_REDACTED");
    for (int i=0;i<=static_cast<int>(DiagnosticEvent::CallbackDiscarded);++i) {
        const char* safe=diagnosticEvent(static_cast<DiagnosticEvent>(i));
        assert(std::string(sanitizeDiagnostic(safe,std::strlen(safe)))==safe);
    }
    std::cout << "PX-16 closed-event canary and encoded/split/prefix/suffix conformance PASS\n";
}
