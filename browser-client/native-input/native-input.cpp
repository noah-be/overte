// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
#include <QCoreApplication>
#include <QInputMethodEvent>
#include <QKeyEvent>
#include <QQmlExtensionPlugin>
#include <QQuickItem>
#include <QThread>
#include <qqml.h>

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
private:
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
