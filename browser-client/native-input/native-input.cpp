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
    QSharedPointer<QQuickItemGrabResult> _pendingGrab;
    double _grabToken { 0 };
    QQuickItem* ownerItem() const {
        auto* owner = parent();
        for (int depth = 0; owner && depth < 24; ++depth, owner = owner->parent()) {
            if (auto* item = qobject_cast<QQuickItem*>(owner)) return item;
        }
        return nullptr;
    }
    bool deliver(QObject* target, const QString& text, bool cut) {
        auto* item = qobject_cast<QQuickItem*>(target);
        if (!item || item->thread() != QThread::currentThread() ||
                !item->isVisible() || !item->isEnabled() || !item->hasActiveFocus() ||
                !(item->flags() & QQuickItem::ItemAcceptsInputMethod) ||
                item->property("readOnly").toBool() || (!cut && text.isEmpty()) ||
                text.toUtf8().size() > 65536) return false;
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
            if ((code < 32 && code != 9 && code != 10 && code != 13) || code == 127) return false;
        }
        QInputMethodEvent event;
        event.setCommitString(text);
        return QCoreApplication::sendEvent(item, &event) && event.isAccepted();
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
