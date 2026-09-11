// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "DevelopmentOverrides.h"
#include <QQmlAbstractUrlInterceptor>
#include <QQmlEngine>

namespace overte { namespace ios { namespace development {
class QmlOverrideInterceptor final : public QObject, public QQmlAbstractUrlInterceptor {
public:
    QmlOverrideInterceptor(QQmlEngine* engine, const QString& root) : QObject(engine),
        _root(QFileInfo(root).canonicalFilePath()), _logicalRoot(QDir::cleanPath(root)) {}
    QUrl intercept(const QUrl& source, DataType type) override {
        Q_UNUSED(type)
        // Only app resource URLs are eligible. Qt's own module/plugin roots
        // have no counterpart in this tree. Local URLs from a redirected
        // qmldir may refer to bundled assets outside the transferred QML tree.
        if (_root.isEmpty()) { return source; }
        if (source.isLocalFile()) {
            auto local = QDir::cleanPath(source.toLocalFile());
            if (local.startsWith(_logicalRoot + '/')) {
                local = _root + local.mid(_logicalRoot.size());
            }
            if (local.startsWith(_root + '/') && !QFileInfo::exists(local)) {
                QUrl fallback("qrc:/");
                fallback.setPath('/' + local.mid(_root.size() + 1));
                fallback.setQuery(source.query());
                fallback.setFragment(source.fragment());
                return fallback;
            }
            return source;
        }
        if (source.scheme() != "qrc") { return source; }
        auto path = source.path();
        if (path.startsWith('/')) { path.remove(0, 1); }
        const auto local = containedFile(_root, path);
        if (local.isEmpty()) { return source; }
        auto result = QUrl::fromLocalFile(local);
        result.setQuery(source.query());
        result.setFragment(source.fragment());
        return result;
    }
private:
    const QString _root;
    const QString _logicalRoot;
};
}}}
