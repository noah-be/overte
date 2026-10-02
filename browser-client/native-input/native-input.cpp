// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
#include <QCoreApplication>
#include <QInputMethodEvent>
#include <QKeyEvent>
#include <QQmlExtensionPlugin>
#include <QQuickItem>
#include <QQuickItemGrabResult>
#include <QQuickWindow>
#include <QPointer>
#include <QQmlEngine>
#include <QThread>
#include <qqml.h>
#include <cmath>

// Deliver the same atomic commit event as the native input method. In particular,
// do not invoke TextEdit.insert(): that interprets markup and can bypass readOnly.
class NativeInput : public QObject {
    Q_OBJECT
public:
    explicit NativeInput(QObject* parent = nullptr) : QObject(parent) {}
    Q_INVOKABLE bool commitText(QObject* target, const QString& text) {
        return deliver(target, text, false);
    }
    Q_INVOKABLE bool cutSelection(QObject* target) {
        return deliver(target, QString(), true);
    }
    // Experimental native WebEngine route: the actual active Quick delegate
    // receives one normal input-method commit, never a DOM value assignment.
    // The trusted QML callback separately binds URL/surface/revision/navigation.
    // Private diagnostic methods return only fixed stage/refusal enums.
    Q_INVOKABLE QString webCommitStage() const { return _webCommitStage; }
    Q_INVOKABLE QString webCommitGuard() const { return _webCommitGuard; }
    Q_INVOKABLE bool commitWebText(QObject* target, QObject* webRoot, const QString& text) {
        _webCommitStage = QStringLiteral("initial-target");
        _webCommitGuard = QStringLiteral("entered");
        const QPointer<NativeInput> self(this);
        const QPointer<QQuickItem> item(qobject_cast<QQuickItem*>(target));
        const QPointer<QQuickItem> root(qobject_cast<QQuickItem*>(webRoot));
        const QPointer<QQuickItem> owner(ownerItem());
        const QPointer<QQuickWindow> window(owner ? owner->window() : nullptr);
        if (!webTargetCurrent(item, root, owner, window)) return false;
        _webCommitStage = QStringLiteral("input-query");
        QInputMethodQueryEvent query(Qt::ImEnabled | Qt::ImHints);
        QCoreApplication::sendEvent(item, &query);
        // Query delivery may re-enter application code or destroy/reparent items.
        if (!self) return false;
        _webCommitStage = QStringLiteral("post-query-target");
        if (!webTargetCurrent(item, root, owner, window)) return false;
        _webCommitStage = QStringLiteral("input-enabled-query");
        if (!query.value(Qt::ImEnabled).isValid()) return refuseWebGuard("input-enabled-invalid");
        if (!query.value(Qt::ImEnabled).toBool()) return refuseWebGuard("input-enabled-false");
        _webCommitStage = QStringLiteral("delivery");
        _webCommitGuard = QStringLiteral("entered");
        _observingWebCommit = true;
        const bool accepted = deliver(item, text, false);
        if (self) { _observingWebCommit = false; _webCommitStage = QStringLiteral("delivery-returned"); }
        return accepted;
    }
    // Private whole-password native IME experiment; the expected disabled
    // password composition flag is preserved, not enabled or bypassed globally.
    Q_INVOKABLE bool commitWebPasswordText(QObject* target, QObject* webRoot, const QString& text) {
        _webCommitStage = QStringLiteral("password-initial");
        _webCommitGuard = QStringLiteral("entered");
        if (!passwordTextValid(text)) return refuseWebGuard("password-invalid-text");
        const QPointer<NativeInput> self(this);
        const QPointer<QQuickItem> item(qobject_cast<QQuickItem*>(target));
        const QPointer<QQuickItem> root(qobject_cast<QQuickItem*>(webRoot));
        const QPointer<QQuickItem> owner(ownerItem());
        const QPointer<QQuickWindow> window(owner ? owner->window() : nullptr);
        if (!webPasswordTargetCurrent(item, root, owner, window)) return false;
        _webCommitStage = QStringLiteral("password-query");
        QInputMethodQueryEvent query(Qt::ImHints);
        QCoreApplication::sendEvent(item, &query);
        if (!self) return false;
        if (!webPasswordTargetCurrent(item, root, owner, window)) return false;
        if (!query.value(Qt::ImHints).isValid()) return refuseWebGuard("password-hints-invalid");
        if (!(query.value(Qt::ImHints).toInt() & Qt::ImhHiddenText)) return refuseWebGuard("password-hints-missing");
        _webCommitStage = QStringLiteral("password-commit");
        QInputMethodEvent event;
        event.setCommitString(text);
        const bool accepted = QCoreApplication::sendEvent(item, &event) && event.isAccepted();
        if (!self) return false;
        if (!accepted) return refuseWebGuard("password-commit-refused");
        if (!webPasswordTargetCurrent(item, root, owner, window)) return false;
        _webCommitStage = QStringLiteral("password-returned");
        _webCommitGuard = QStringLiteral("native-accepted");
        return true;
    }
    // The offscreen QQuickWindow root is created in C++, without a QML engine.
    // Its QML callback grab overload refuses it. Only this helper's own GUI root
    // is eligible for the public QSize overload; no window or path API is exposed.
    Q_INVOKABLE bool grabPrivateGui(QObject* requested, double token) {
        auto* root = qobject_cast<QQuickItem*>(requested);
        auto* owner = ownerItem();
        auto* window = owner ? owner->window() : nullptr;
        if (_pendingGrab || !std::isfinite(token) || token < 1 ||
                token > 9007199254740991.0 || std::floor(token) != token ||
                !root || !window || root != window->contentItem() ||
                root->window() != window || root->thread() != QThread::currentThread() ||
                thread() != QThread::currentThread() || window->thread() != QThread::currentThread() ||
                !std::isfinite(root->width()) || !std::isfinite(root->height()) ||
                root->width() < 1 || root->height() < 1 ||
                root->width() > 2048 || root->height() > 2048) return false;
        _pendingGrab = root->grabToImage(QSize(qRound(root->width()), qRound(root->height())));
        if (!_pendingGrab) return false;
        _grabToken = token;
        QQmlEngine::setObjectOwnership(_pendingGrab.data(), QQmlEngine::CppOwnership);
        const QPointer<QQuickItem> capturedRoot(root), capturedOwner(owner);
        const QPointer<QQuickWindow> capturedWindow(window);
        QObject::connect(_pendingGrab.data(), &QQuickItemGrabResult::ready, this,
            [this, capturedRoot, capturedOwner, capturedWindow, token] {
                if (!_pendingGrab || _grabToken != token) return;
                // Retain through the synchronous QML callback without a shared-
                // pointer cycle between this result and its signal connection.
                auto result = _pendingGrab;
                const bool valid = capturedRoot && capturedOwner && capturedWindow &&
                    ownerItem() == capturedOwner && capturedOwner->window() == capturedWindow &&
                    capturedRoot->window() == capturedWindow &&
                    capturedWindow->contentItem() == capturedRoot;
                const QPointer<NativeInput> self(this);
                emit privateGuiReady(token, valid ? result.data() : nullptr);
                if (self) { _pendingGrab.clear(); _grabToken = 0; }
            });
        return true;
    }
signals:
    void privateGuiReady(double token, QObject* result);
private:
    mutable QString _webCommitStage { QStringLiteral("not-called") };
    mutable QString _webCommitGuard { QStringLiteral("not-called") };
    bool _observingWebCommit { false };
    bool refuseWebGuard(const char* reason) const { _webCommitGuard = QString::fromLatin1(reason); return false; }
    QSharedPointer<QQuickItemGrabResult> _pendingGrab;
    double _grabToken { 0 };
    QQuickItem* ownerItem() const {
        auto* owner = parent();
        for (int depth = 0; owner && depth < 24; ++depth, owner = owner->parent()) {
            if (auto* item = qobject_cast<QQuickItem*>(owner)) return item;
        }
        return nullptr;
    }
    bool webTargetCurrent(QQuickItem* item, QQuickItem* root, QQuickItem* owner,
                          QQuickWindow* window) const {
        if (!item) return refuseWebGuard("item-missing");
        if (!root) return refuseWebGuard("root-missing");
        if (!owner) return refuseWebGuard("owner-missing");
        if (!window) return refuseWebGuard("window-missing");
        if (ownerItem() != owner) return refuseWebGuard("owner-changed");
        if (thread() != QThread::currentThread()) return refuseWebGuard("helper-thread");
        if (item->thread() != QThread::currentThread()) return refuseWebGuard("item-thread");
        if (root->thread() != QThread::currentThread()) return refuseWebGuard("root-thread");
        if (owner->thread() != QThread::currentThread()) return refuseWebGuard("owner-thread");
        if (window->thread() != QThread::currentThread()) return refuseWebGuard("window-thread");
        if (owner->window() != window) return refuseWebGuard("owner-window");
        if (item->window() != window) return refuseWebGuard("item-window");
        if (root->window() != window) return refuseWebGuard("root-window");
        if (window->activeFocusItem() != item) return refuseWebGuard("window-focus");
        if (!item->hasActiveFocus()) return refuseWebGuard("item-focus");
        if (!item->isVisible()) return refuseWebGuard("item-hidden");
        if (!item->isEnabled()) return refuseWebGuard("item-disabled");
        if (!root->isVisible()) return refuseWebGuard("root-hidden");
        if (!root->isEnabled()) return refuseWebGuard("root-disabled");
        if (!(item->flags() & QQuickItem::ItemAcceptsInputMethod)) return refuseWebGuard("input-method-flag");
        auto* parent = item;
        for (int depth = 0; parent && depth < 24; ++depth, parent = parent->parentItem())
            if (parent == root) { _webCommitGuard = QStringLiteral("current"); return true; }
        return refuseWebGuard("root-ancestry");
    }
    bool webPasswordTargetCurrent(QQuickItem* item, QQuickItem* root, QQuickItem* owner,
                          QQuickWindow* window) const {
        if (!item) return refuseWebGuard("item-missing");
        if (!root) return refuseWebGuard("root-missing");
        if (!owner) return refuseWebGuard("owner-missing");
        if (!window) return refuseWebGuard("window-missing");
        if (ownerItem() != owner) return refuseWebGuard("owner-changed");
        if (thread() != QThread::currentThread()) return refuseWebGuard("helper-thread");
        if (item->thread() != QThread::currentThread()) return refuseWebGuard("item-thread");
        if (root->thread() != QThread::currentThread()) return refuseWebGuard("root-thread");
        if (owner->thread() != QThread::currentThread()) return refuseWebGuard("owner-thread");
        if (window->thread() != QThread::currentThread()) return refuseWebGuard("window-thread");
        if (owner->window() != window) return refuseWebGuard("owner-window");
        if (item->window() != window) return refuseWebGuard("item-window");
        if (root->window() != window) return refuseWebGuard("root-window");
        if (window->activeFocusItem() != item) return refuseWebGuard("window-focus");
        if (!item->hasActiveFocus()) return refuseWebGuard("item-focus");
        if (!item->isVisible()) return refuseWebGuard("item-hidden");
        if (!item->isEnabled()) return refuseWebGuard("item-disabled");
        if (!root->isVisible()) return refuseWebGuard("root-hidden");
        if (!root->isEnabled()) return refuseWebGuard("root-disabled");
        if (item->flags() & QQuickItem::ItemAcceptsInputMethod) return refuseWebGuard("password-flag-expected");
        if (QString::fromLatin1(item->metaObject()->className()) != QStringLiteral("QtWebEngineCore::RenderWidgetHostViewQtDelegateQuick")) return refuseWebGuard("password-delegate-class");
        if (!root->inherits("QQuickWebEngineView")) return refuseWebGuard("password-root-class");
        auto* parent = item;
        for (int depth = 0; parent && depth < 24; ++depth, parent = parent->parentItem())
            if (parent == root) { _webCommitGuard = QStringLiteral("current"); return true; }
        return refuseWebGuard("root-ancestry");
    }
    static bool passwordTextValid(const QString& text) {
        if (text.isEmpty() || text.size() > 65536) return false;
        uint bytes = 0;
        for (int index = 0; index < text.size(); ++index) {
            const ushort code = text.at(index).unicode();
            if (code < 32 || code == 127) return false;
            if (QChar::isHighSurrogate(code)) {
                if (++index >= text.size() || !QChar::isLowSurrogate(text.at(index).unicode())) return false;
                bytes += 4;
            } else if (QChar::isLowSurrogate(code)) return false;
            else bytes += code < 128 ? 1 : (code < 2048 ? 2 : 3);
            if (bytes > 65536) return false;
        }
        return true;
    }
    bool deliver(QObject* target, const QString& text, bool cut) {
        auto* item = qobject_cast<QQuickItem*>(target);
        if (!item || item->thread() != QThread::currentThread() ||
                !item->isVisible() || !item->isEnabled() || !item->hasActiveFocus() ||
                !(item->flags() & QQuickItem::ItemAcceptsInputMethod) ||
                item->property("readOnly").toBool() || (!cut && text.isEmpty()) ||
                text.toUtf8().size() > 65536) { if (_observingWebCommit) _webCommitGuard = QStringLiteral("delivery-guard"); return false; }
        if (cut && item->property("selectionEnd").toInt() <= item->property("selectionStart").toInt()) return false;
        if (cut) {
            // The browser exports the already-selected text to its own clipboard.
            // Native Backspace performs the corresponding atomic selection delete
            // through Qt's validator/undo path without changing the Qt clipboard.
            QKeyEvent event(QEvent::KeyPress, Qt::Key_Backspace, Qt::NoModifier);
            return QCoreApplication::sendEvent(item, &event) && event.isAccepted();
        }
        for (const auto character : text) {
            const auto code = character.unicode();
            if ((code < 32 && code != 9 && code != 10 && code != 13) || code == 127) { if (_observingWebCommit) _webCommitGuard = QStringLiteral("text-control-character"); return false; }
        }
        QInputMethodEvent event;
        event.setCommitString(text);
        const QPointer<NativeInput> self(this);
        const bool sent = QCoreApplication::sendEvent(item, &event);
        const bool accepted = sent && event.isAccepted();
        if (self && _observingWebCommit) _webCommitGuard = QStringLiteral("native-accepted");
        if (self && _observingWebCommit && !sent) _webCommitGuard = QStringLiteral("send-event-false");
        else if (self && _observingWebCommit && !accepted) _webCommitGuard = QStringLiteral("event-not-accepted");
        return accepted;
    }
};

class NativeInputPlugin : public QQmlExtensionPlugin {
    Q_OBJECT
    Q_PLUGIN_METADATA(IID QQmlExtensionInterface_iid)
public:
    void registerTypes(const char* uri) override {
        Q_ASSERT(QString::fromLatin1(uri) == QStringLiteral("BrowserNativeInput"));
        qmlRegisterType<NativeInput>(uri, 1, 0, "NativeInput");
    }
};

#include "native-input.moc"
