// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <QDir>
#include <QFileInfo>
#include <QStandardPaths>
#include <QStringList>

namespace overte::snapshot {
inline QString storageRoot() {
    const auto app = QStandardPaths::writableLocation(QStandardPaths::AppDataLocation);
    return app.isEmpty() ? QString() : QDir(app).filePath(QStringLiteral("Snapshots"));
}
// Native exports get a native-known root, never a page-supplied directory grant.
inline QString exportPath(const QString& path, const QString& root = storageRoot()) {
    const auto components = QDir::fromNativeSeparators(path).split('/');
    if (components.contains("..") || components.contains(".")) { return {}; }
    const QFileInfo directory(root), file(path);
    if (root.isEmpty() || !directory.isDir() || directory.isSymLink() || !file.isFile() || file.isSymLink() ||
            file.size() <= 0 || file.size() > 256LL * 1024 * 1024 ||
            !QStringList { "png", "jpg", "jpeg", "webp", "gif" }.contains(file.suffix().toLower())) { return {}; }
    const auto base = directory.canonicalFilePath();
    const auto canonical = file.canonicalFilePath();
    // Captures are direct children. The OS-owned application prefix may itself
    // be canonicalized (for example /var -> /private/var on Apple platforms).
    // Permit that native mapping, but no user-selected alias or child symlink.
    const auto parent = QDir::cleanPath(file.absolutePath());
    if (base.isEmpty() || (parent != base && parent != QDir::cleanPath(directory.absoluteFilePath())) ||
            QFileInfo(canonical).absolutePath() != base || !canonical.startsWith(base + QDir::separator())) { return {}; }
    return canonical;
}
} // namespace overte::snapshot
