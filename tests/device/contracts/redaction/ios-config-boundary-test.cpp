// SPDX-License-Identifier: Apache-2.0
// Entire production header and real QFile/JSON/cache; no replacement loader.
#include <QtCore/QtCore>
#include <cassert>
#include <vector>
#define OVERTE_IOS 1
#include "libraries/shared/src/shared/IOSRuntimeLogging.h"
static std::vector<QString> messages;
static void capture(QtMsgType, const QMessageLogContext&, const QString& text) { messages.push_back(text); }
int main(int argc, char** argv) {
    QCoreApplication app(argc, argv);
    qInstallMessageHandler(capture);
    QTemporaryDir temporary;
    assert(temporary.isValid());
    const auto path = temporary.path() + "/private-config-canary.json";
    qputenv("OVERTE_IOS_DIAGNOSTIC_CONFIG", path.toUtf8());
    auto replace = [&](const QByteArray& bytes) {
        QFile file(path);
        assert(file.open(QIODevice::WriteOnly | QIODevice::Truncate));
        assert(file.write(bytes) == bytes.size());
        file.close();
    };
    auto reload = [&] {
        QThread::msleep(1050); // Exercise the actual one-second reload interval.
        return iosRuntimeDiagnosticConfig();
    };
    const QByteArray first("{\"renderDiagnosticMode\":\"safe-private-canary\",\"enabled\":true}");
    replace(first);
    assert(iosRuntimeDiagnosticConfig().value("enabled").toBool());
    assert(iosRuntimeDiagnosticBool("enabled"));
    assert(messages.size() == 1);
    // Valid JSON just above the limit used to replace live renderer settings.
    const QByteArray prefix("{\"renderDiagnosticMode\":\"");
    const QByteArray suffix("\"}");
    replace(prefix + QByteArray(1024 * 1024 + 1 - prefix.size() - suffix.size(), 'x') + suffix);
    assert(reload().value("enabled").toBool());
    assert(messages.size() == 1); // Rejected input is not logged or acknowledged.
    // The limit is inclusive; the real consumer sees the accepted configuration.
    replace(prefix + QByteArray(1024 * 1024 - prefix.size() - suffix.size(), 'y') + suffix);
    assert(reload().value("renderDiagnosticMode").toString().size() == 1024 * 1024 - prefix.size() - suffix.size());
    assert(!iosRuntimeDiagnosticBool("enabled"));
    assert(messages.size() == 2);
    replace("{\"enabled\":false}");
    assert(reload().value("enabled").isBool());
    assert(messages.size() == 3);
    replace("{partial");
    assert(reload().value("enabled").isBool());
    assert(messages.size() == 3);
    assert(QFile::remove(path));
    assert(reload().isEmpty());
    replace(first);
    assert(reload().value("enabled").toBool());
    assert(messages.size() == 4);
    for (const auto& message : messages) { assert(message == "OVT_REDACTED"); }
    qInstallMessageHandler(nullptr);
}
