// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0

#ifndef overte_HTTPRequestLimits_h
#define overte_HTTPRequestLimits_h

#include <QtGlobal>
#include <limits>

// Per-listener policy. Lengths must also fit Qt5's int-sized QByteArray API.
struct HTTPRequestLimits {
    qint64 maxHeaderBytes { 64 * 1024 }; // Includes request line and final CRLF.
    qint64 maxBodyBytes { std::numeric_limits<int>::max() - qint64(1) };
    qint64 maxReservedBytes { 4LL * 1024 * 1024 * 1024 };
    qint64 memoryBodyThreshold { 10 * 1000 * 1000 };
    int maxConnections { 32 };
    int headerDeadlineMs { 30 * 1000 };
    int requestDeadlineMs { 5 * 60 * 1000 }; // Absolute, starting at accept (also for TLS).
    int idleDeadlineMs { 30 * 1000 };
    static constexpr qint64 SOCKET_BUFFER_BYTES = 64 * 1024;
};

#endif
