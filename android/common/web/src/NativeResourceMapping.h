// Copyright 2026 Overte contributors.
// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <EmbeddedWebPolicy.h>
#include <QDir>
#include <QUrl>

namespace overte::android::web {
// Root is supplied once by native product startup, never by QML/page messages.
class NativeResourceMapping {
public:
    NativeResourceMapping(QString root = {}, qint64 handle = 0) : _handle(handle) {
        _root = root.startsWith("qrc:/") ? QStringLiteral("qrc:") + QDir::cleanPath(QUrl(root).path()) : QFileInfo(root).canonicalFilePath();
    }
    const QString& root() const { return _root; }
    bool accepts(const QUrl& source) const { return overte::web::EmbeddedWebSession::isPackagedURL(source, _root); }
    QUrl canonicalSource(const QUrl& source) const {
        if (!accepts(source)) return source;
        QUrl canonical = source.scheme() == "qrc" ? QUrl("qrc:" + QDir::cleanPath(source.path())) : QUrl::fromLocalFile(QFileInfo(source.toLocalFile()).canonicalFilePath());
        canonical.setQuery(source.query()); canonical.setFragment(source.fragment()); return canonical;
    }
    QUrl toBrowser(const QUrl& source) const {
        if (!accepts(source)) return source;
        const QString prefix = _root.startsWith("qrc:/") ? QUrl(_root).path() : QDir(_root).canonicalPath();
        const QString relative = canonicalSource(source).path(QUrl::FullyDecoded).mid(prefix.size() + 1);
        QUrl result;
        result.setScheme("https"); result.setHost("overte-embedded.invalid");
        result.setPath('/' + QString::number(_handle) + '/' + relative);
        result.setQuery(source.query()); result.setFragment(source.fragment());
        return result;
    }
    QUrl toSource(const QUrl& browser) const {
        if (browser.host() != "overte-embedded.invalid") return browser;
        if (browser.scheme() != "https" || browser.port(443) != 443 || !browser.userInfo().isEmpty()) return {};
        const QString path = browser.path(QUrl::FullyDecoded), prefix = '/' + QString::number(_handle) + '/';
        if (!path.startsWith(prefix)) return {};
        const QString relative = path.mid(prefix.size());
        if (relative.isEmpty() || relative.split('/').contains("..") || relative.contains('\\')) return {};
        QUrl source = _root.startsWith("qrc:/") ? QUrl(_root + '/' + relative) : QUrl::fromLocalFile(_root + '/' + relative);
        source.setQuery(browser.query()); source.setFragment(browser.fragment());
        return accepts(source) ? canonicalSource(source) : QUrl();
    }
private:
    QString _root;
    qint64 _handle;
};
}
