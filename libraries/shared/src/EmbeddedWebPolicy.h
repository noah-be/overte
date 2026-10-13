// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0
#pragma once

#include <QDir>
#include <QFileInfo>
#include <QString>
#include <QUrl>
#include <cstddef>
#include <cstdint>
#include <limits>

namespace overte::web {

enum class Surface { Tablet, WorldEntity };

// One policy instance per source-owned HTML surface. This is independent of
// Interface's original, process-wide contained text-only NativeWebPolicy.
// Callers own native permission prompts, input, network loading and source
// consent. A page receives only its isolated EventBridge, never app QObjects.
class EmbeddedWebSession {
public:
    using Generation = std::uint64_t;
    static constexpr std::size_t MAX_BRIDGE_BYTES = 64 * 1024;

    Generation open(const QUrl& url, Surface surface, const QString& sourceIdentity,
                    const QString& packagedDocumentRoot = QString()) {
        if (!advance()) {
            return 0;
        }
        _url = url;
        _surface = surface;
        _sourceIdentity = sourceIdentity;
        _packagedDocumentRoot = packagedDocumentRoot;
        _opened = (isNetworkURL(url) || isPackagedURL(url, packagedDocumentRoot)) &&
            !sourceIdentity.trimmed().isEmpty();
        return active() ? _generation : 0;
    }

    void close() {
        advance();
        _opened = false;
        _url = QUrl();
        _sourceIdentity.clear();
        _packagedDocumentRoot.clear();
    }

    bool setVisible(bool visible) {
        if (_visible == visible) {
            return false;
        }
        _visible = visible;
        advance();
        return true;
    }

    bool setForeground(bool foreground) {
        if (_foreground == foreground) {
            return false;
        }
        _foreground = foreground;
        advance();
        return true;
    }

    Generation generation() const { return _generation; }
    bool active() const { return _opened && _visible && _foreground && !_exhausted; }
    const QUrl& url() const { return _url; }
    Surface surface() const { return _surface; }
    const QString& sourceIdentity() const { return _sourceIdentity; }
    const QString& packagedDocumentRoot() const { return _packagedDocumentRoot; }

    bool allowsNavigation(Generation generation, const QUrl& url, bool mainFrame,
                          const QString& method) const {
        Q_UNUSED(mainFrame);
        // Cross-origin browsing/subframes are ordinary HTML capabilities.
        // Navigating does not grant a new page the original source's bridge.
        const auto verb = method.toUpper();
        return current(generation) &&
            (isNetworkURL(url) || isPackagedURL(url, _packagedDocumentRoot)) &&
            (verb == "GET" || verb == "HEAD" || verb == "POST" || verb == "PUT" ||
             verb == "PATCH" || verb == "DELETE" || verb == "OPTIONS");
    }

    bool allowsBridge(Generation generation, const QUrl& frameURL, bool mainFrame,
                      std::size_t utf8Bytes) const {
        return current(generation) && mainFrame && utf8Bytes > 0 &&
            utf8Bytes <= MAX_BRIDGE_BYTES &&
            (sameOrigin(_url, frameURL) ||
             (isPackagedURL(_url, _packagedDocumentRoot) &&
              isPackagedURL(frameURL, _packagedDocumentRoot) &&
              _url.adjusted(QUrl::RemoveQuery | QUrl::RemoveFragment) ==
                  frameURL.adjusted(QUrl::RemoveQuery | QUrl::RemoveFragment)));
    }

    // scriptUrl comes from the source owner, never an untrusted page message.
    // Remote scripts retain the existing source's explicit script consent.
    // Native callers may opt into ONE packaged resource root; no filesystem
    // capability is inferred from an HTTP document or an arbitrary file URL.
    bool allowsScriptURL(const QUrl& url, const QString& packagedResourceRoot = QString()) const {
        if (!active()) {
            return false;
        }
        if (isNetworkURL(url)) {
            return true;
        }
        return isPackagedURL(url, packagedResourceRoot);
    }

    static bool isPackagedURL(const QUrl& url, const QString& packagedResourceRoot) {
        if (!url.isValid() || url.isRelative() || !url.userInfo().isEmpty() ||
            !url.host().isEmpty() ||
            packagedResourceRoot.isEmpty()) {
            return false;
        }
        const QString path = url.path(QUrl::FullyDecoded);
        if (containsControls(path) || path.contains('\\') ||
            path.split('/').contains("..")) {
            return false;
        }
        if (url.scheme() == "qrc" && packagedResourceRoot.startsWith("qrc:/")) {
            const auto root = QDir::cleanPath(QUrl(packagedResourceRoot).path());
            const auto clean = QDir::cleanPath(path);
            return root != "/" && clean.startsWith(root + '/');
        }
        if (url.scheme() == "file" && QDir::isAbsolutePath(packagedResourceRoot)) {
            // Canonical paths also reject symlinks escaping the approved root.
            const auto root = QFileInfo(packagedResourceRoot).canonicalFilePath();
            const auto file = QFileInfo(url.toLocalFile()).canonicalFilePath();
            return !root.isEmpty() && root != "/" && !file.isEmpty() &&
                QFileInfo(file).isFile() && file.startsWith(root + '/');
        }
        return false;
    }

    static bool isNetworkURL(const QUrl& url) {
        const auto scheme = url.scheme().toLower();
        return url.isValid() && !url.isRelative() &&
            (scheme == "http" || scheme == "https") && !url.host().isEmpty() &&
            url.userInfo().isEmpty() && !containsControls(url.host(QUrl::FullyDecoded)) &&
            !containsControls(url.path(QUrl::FullyDecoded)) &&
            !containsControls(url.query(QUrl::FullyDecoded)) &&
            !containsControls(url.fragment(QUrl::FullyDecoded));
    }

    static bool sameOrigin(const QUrl& left, const QUrl& right) {
        return isNetworkURL(left) && isNetworkURL(right) &&
            left.scheme().compare(right.scheme(), Qt::CaseInsensitive) == 0 &&
            left.host().compare(right.host(), Qt::CaseInsensitive) == 0 &&
            effectivePort(left) == effectivePort(right);
    }

private:
    static bool containsControls(const QString& text) {
        for (const auto character : text) {
            if (character.unicode() < 32 || character.unicode() == 127) {
                return true;
            }
        }
        return false;
    }
    static int effectivePort(const QUrl& url) {
        return url.port(url.scheme().compare("https", Qt::CaseInsensitive) == 0 ? 443 : 80);
    }
    bool current(Generation generation) const {
        return active() && generation != 0 && generation == _generation;
    }
    bool advance() {
        if (_exhausted || _generation == std::numeric_limits<Generation>::max()) {
            _exhausted = true;
            _opened = false;
            return false;
        }
        ++_generation;
        return true;
    }
    Generation _generation { 0 };
    QUrl _url;
    QString _sourceIdentity;
    QString _packagedDocumentRoot;
    Surface _surface { Surface::Tablet };
    bool _opened { false };
    bool _visible { true };
    bool _foreground { true };
    bool _exhausted { false };
};
} // namespace overte::web
