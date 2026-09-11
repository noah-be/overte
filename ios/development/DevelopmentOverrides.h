// SPDX-License-Identifier: Apache-2.0
#pragma once

#include <QCoreApplication>
#include <QCryptographicHash>
#include <QDir>
#include <QFile>
#include <QJsonDocument>
#include <QJsonObject>
#include <QRegularExpression>
#include <QSaveFile>
#include <QVariant>

namespace overte { namespace ios { namespace development {
constexpr auto RESOURCE_PROPERTY = "overte.ios.development.resourcesRoot";

inline QByteArray read(const QString& path) {
    QFile file(path);
    return file.open(QIODevice::ReadOnly) ? file.readAll() : QByteArray();
}
inline QString digest(const QByteArray& bytes) {
    return QString::fromLatin1(QCryptographicHash::hash(bytes, QCryptographicHash::Sha256).toHex());
}
inline bool writeJson(const QString& path, const QJsonObject& value) {
    QSaveFile file(path);
    const auto bytes = QJsonDocument(value).toJson(QJsonDocument::Compact);
    return file.open(QIODevice::WriteOnly) && file.write(bytes) == bytes.size() && file.commit();
}
inline bool safePath(const QString& path) {
    return !path.isEmpty() && !path.startsWith('/') && !path.contains('\\') &&
        !path.contains(':') && !path.split('/').contains("..") &&
        !path.split('/').contains(".") && !path.split('/').contains("");
}
inline QString containedFile(const QString& root, const QString& relative) {
    if (!safePath(relative)) { return {}; }
    const QFileInfo file(QDir(root).filePath(relative));
    const auto canonicalRoot = QFileInfo(root).canonicalFilePath();
    const auto canonicalFile = file.canonicalFilePath();
    if (!file.isFile() || file.isSymLink() || canonicalRoot.isEmpty() ||
            !canonicalFile.startsWith(canonicalRoot + '/')) { return {}; }
    return canonicalFile;
}

// Called once before Application constructs script engines or QML surfaces.
// A revision is a process-lifetime snapshot: never mix old singletons/scripts
// with new types or mutate a QML interceptor while it is loading on a worker.
// The sole production caller is compiled only into opt-in iOS E2E builds.
inline QString initialize(const QString& documents, const QString& installation) {
    const auto root = QDir(documents).filePath("OverteDevelopment");
    if (!QDir().mkpath(root)) { return {}; }
    const auto installId = digest(installation.toUtf8());
    const QJsonObject capability {{"schema", 1}, {"installation", installId},
        {"apply", "restart"}, {"qml", true}, {"clientScripts", true}};
    writeJson(root + "/capabilities.json", capability);
    QJsonObject status {{"schema", 1}, {"installation", installId}, {"state", "bundled"}};
    QString scripts;
    const auto fail = [&](const char* reason) {
        status["state"] = "rejected";
        status["reason"] = reason;
    };
    qApp->setProperty(RESOURCE_PROPERTY, QString());
    const auto activeBytes = read(root + "/active.json");
    qApp->setProperty("overte.ios.development.ownsOverrides", QFileInfo::exists(root + "/active.json"));
    if (!activeBytes.isEmpty()) {
        const auto active = QJsonDocument::fromJson(activeBytes).object();
        const auto revision = active["revision"].toString();
        static const QRegularExpression hash("^[a-f0-9]{64}$");
        if (active["schema"].toInt() == 1 && active["disabled"].toBool()) {
            // Explicit return to the IPA; preserve revisions for rollback.
        } else if (active["schema"].toInt() != 1 || active["installation"] != installId ||
                !hash.match(revision).hasMatch()) {
            fail("invalid-or-different-installation");
        } else {
            const auto revisionRoot = root + "/revisions/" + revision;
            const auto manifestBytes = read(containedFile(revisionRoot, "manifest.json"));
            const auto manifest = QJsonDocument::fromJson(manifestBytes).object();
            const auto files = manifest["files"].toObject();
            bool valid = digest(manifestBytes) == revision && manifest["schema"].toInt() == 1 &&
                !files.isEmpty() && !QFileInfo(revisionRoot).isSymLink() &&
                QFileInfo(revisionRoot).canonicalFilePath().startsWith(QFileInfo(root).canonicalFilePath() + '/');
            for (auto it = files.begin(); valid && it != files.end(); ++it) {
                const auto name = it.key();
                const auto path = containedFile(revisionRoot, name);
                valid = (name.startsWith("resources/") || name.startsWith("scripts/")) &&
                    !path.isEmpty() && hash.match(it.value().toString()).hasMatch() &&
                    digest(read(path)) == it.value().toString();
            }
            if (!valid) {
                fail("incomplete-or-corrupt-revision");
            } else if (manifest["scripts"].toBool() && !files.contains("scripts/defaultScripts.js")) {
                fail("missing-default-script");
            } else {
                qApp->setProperty(RESOURCE_PROPERTY, revisionRoot + "/resources");
                if (manifest["scripts"].toBool()) { scripts = revisionRoot + "/scripts"; }
                status["state"] = "selected"; // Selection is not native/UI acceptance.
                status["revision"] = revision;
                status["source"] = manifest["source"];
            }
        }
    } else if (QFileInfo::exists(root + "/active.json")) {
        fail("empty-active-request");
    }
    writeJson(root + "/status.json", status);
    return scripts;
}
}}} // namespace overte::ios::development
