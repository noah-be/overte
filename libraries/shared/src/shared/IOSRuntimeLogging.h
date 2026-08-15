//
//  IOSRuntimeLogging.h
//  libraries/shared/src/shared
//
//  SPDX-License-Identifier: Apache-2.0
//

#pragma once

#include <utility>

#include <QtCore/QByteArray>
#include <QtCore/QDebug>
#include <QtCore/QString>

#if defined(Q_OS_IOS)
#include <os/log.h>
#endif

// CoreSimulator does not reliably preserve stdout/stderr from a GUI process.
// Keep Qt's normal diagnostic stream, but mirror bounded acceptance markers to
// Apple unified logging so runtime automation can observe them deterministically.
template<typename... Args>
inline void logIOSRuntimeMarker(Args&&... args) {
    QString message;
    {
        QDebug stream(&message);
        stream.noquote();
        (stream << ... << std::forward<Args>(args));
    }

    qInfo().noquote() << message;

#if defined(Q_OS_IOS)
    const QByteArray utf8 = message.toUtf8();
    os_log_info(OS_LOG_DEFAULT, "%{public}s", utf8.constData());
#endif
}
