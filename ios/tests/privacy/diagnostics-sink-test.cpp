// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0
#include "../../src/RedactingDiagnostics.h"
#include <QCoreApplication>
#include <QDebug>
#include <cassert>
#include <string>
#include <vector>

std::vector<std::string> output;
void captureOSLog(const char* format, const char* message) {
    assert(std::string(format) == "%{public}s");
    output.emplace_back(message);
    assert(output.back().size() <= 32);
}
int main(int argc, char** argv) {
    // The actual linked installer must protect logs even before QCoreApplication.
    qInfo().noquote() << "synthetic-private-context";
    assert(output.size() == 1 && output.back() == "OVT_REDACTED");
    QCoreApplication app(argc, argv);
    using namespace overte::ios;
    logDiagnostic(DiagnosticEvent::SecureStorageUnavailable);
    assert(output.back() == "OVT_STORAGE_UNAVAILABLE");
    qWarning().noquote() << "OVT_AUTH_REQUIRED";
    assert(output.back() == "OVT_AUTH_REQUIRED");
    for (const std::string input : {"token=canary", "OVT_AUTH_READY private", " OVT_AUTH_READY",
                                   "https://private.invalid", "OVT_AUTH_READY\n", "user@private.invalid"}) {
        logRedactedDiagnostic(input.data(), input.size());
        assert(output.back() == "OVT_REDACTED");
        qWarning().noquote() << QString::fromStdString(input);
        assert(output.back() == "OVT_REDACTED");
    }
    const char embedded[] = "OVT_AUTH_READY\0canary";
    logRedactedDiagnostic(embedded, sizeof(embedded) - 1);
    assert(output.back() == "OVT_REDACTED");
    logRedactedDiagnostic(nullptr, 0);
    assert(output.back() == "OVT_REDACTED");
}
