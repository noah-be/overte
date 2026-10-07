// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <QApplication>
#include <QKeyEvent>
#include <QPointer>
#include <QQuickItem>
#include <QQuickWindow>
#include <QQuickRenderControl>
#include <QThread>
#include <QWidget>
#include <QVector>
#include <cmath>

namespace BrowserApplicationKey {
struct Key { int code { 0 }; QString text; };
inline bool decode(const QString& value, Key& result) {
    if (value.size() == 1 && value.at(0).unicode() >= 32 && value.at(0).unicode() <= 126) {
        result.code = value.at(0).toUpper().unicode(); result.text = value; return true;
    }
    struct Entry { const char* name; int code; const char* text; };
    static const Entry entries[] = {
        {"Backspace", Qt::Key_Backspace, "\b"}, {"Tab", Qt::Key_Tab, "\t"},
        {"Enter", Qt::Key_Return, "\r"}, {"Delete", Qt::Key_Delete, "\x7f"},
        {"Insert", Qt::Key_Insert, ""}, {"Home", Qt::Key_Home, ""},
        {"End", Qt::Key_End, ""}, {"PageUp", Qt::Key_PageUp, ""},
        {"PageDown", Qt::Key_PageDown, ""}, {"ArrowLeft", Qt::Key_Left, ""},
        {"ArrowRight", Qt::Key_Right, ""}, {"ArrowUp", Qt::Key_Up, ""},
        {"ArrowDown", Qt::Key_Down, ""}, {"Escape", Qt::Key_Escape, "\x1b"},
        {"F1", Qt::Key_F1, ""}, {"F2", Qt::Key_F2, ""}, {"F3", Qt::Key_F3, ""},
        {"F4", Qt::Key_F4, ""}, {"F5", Qt::Key_F5, ""}, {"F6", Qt::Key_F6, ""},
        {"F7", Qt::Key_F7, ""}, {"F8", Qt::Key_F8, ""}, {"F9", Qt::Key_F9, ""},
        {"F10", Qt::Key_F10, ""}, {"F11", Qt::Key_F11, ""}, {"F12", Qt::Key_F12, ""}
    };
    for (const auto& entry : entries) if (value == QLatin1String(entry.name)) {
        result.code = entry.code; result.text = QString::fromLatin1(entry.text); return true;
    }
    return false;
}
inline bool descendant(QQuickItem* item, QQuickItem* root) {
    for (int depth = 0; item && depth < 24; ++depth, item = item->parentItem())
        if (item == root) return true;
    return false;
}
struct Target { QPointer<QWidget> main; QPointer<QWidget> canvas; };
inline bool nativeTarget(Target& target) {
    auto* application = qobject_cast<QApplication*>(QCoreApplication::instance());
    if (!application || QString::fromLatin1(application->metaObject()->className()) != QLatin1String("Application") ||
            application->thread() != QThread::currentThread() || QCoreApplication::closingDown()) return false;
    const auto windows = QApplication::topLevelWidgets();
    if (windows.size() > 64) return false;
    int mainCount = 0;
    for (auto* widget : windows) if (QString::fromLatin1(widget->metaObject()->className()) == QLatin1String("MainWindow")) {
        if (++mainCount != 1) return false;
        target.main = widget;
    }
    if (!target.main || target.main->thread() != QThread::currentThread() || !target.main->isVisible() || !target.main->isEnabled()) return false;
    struct Node { QObject* object; int depth; };
    QVector<Node> pending {{target.main, 0}};
    int nodes = 0, canvases = 0;
    while (!pending.isEmpty()) {
        const auto node = pending.takeLast();
        if (++nodes > 4096 || node.depth > 24) return false;
        if (QString::fromLatin1(node.object->metaObject()->className()) == QLatin1String("GLCanvas")) {
            auto* canvas = qobject_cast<QWidget*>(node.object);
            if (!canvas || ++canvases != 1) return false;
            target.canvas = canvas;
        }
        const auto children = node.object->children();
        if (children.size() > 4096 - nodes - pending.size()) return false;
        for (auto* child : children) pending.push_back({child, node.depth + 1});
    }
    return target.canvas && target.canvas->thread() == QThread::currentThread() &&
        target.canvas->window() == target.main && target.canvas->isVisible() && target.canvas->isEnabled();
}
inline bool targetCurrent(const Target& target) {
    return target.main && target.canvas && !QCoreApplication::closingDown() &&
        target.main->thread() == QThread::currentThread() && target.canvas->thread() == QThread::currentThread() &&
        target.canvas->window() == target.main;
}
// No direct Application fallback: GLCanvas retains its ORIGINAL OffscreenUi filter.
// That filter offers keys to QML/WebEngine first, suppresses consumed releases,
// and only then permits GLWidget -> Application -> Controller script delivery.
inline bool click(QObject* helper, QQuickItem* owner, QObject* requestedSurface, const QString& value, int modifiers) {
    const auto allowed = int(Qt::ShiftModifier | Qt::ControlModifier | Qt::AltModifier | Qt::MetaModifier);
    Key key;
    if (!decode(value, key) || (modifiers & ~allowed) != 0 || !helper || !owner ||
            helper->thread() != QThread::currentThread() || owner->thread() != QThread::currentThread()) return false;
    const QPointer<QQuickItem> surface(qobject_cast<QQuickItem*>(requestedSurface));
    const QPointer<QQuickWindow> window(owner->window());
    const QPointer<QQuickItem> focus(window ? window->activeFocusItem() : nullptr);
    if (!surface || !window || !focus || window->thread() != QThread::currentThread() ||
            surface->thread() != QThread::currentThread() || focus->thread() != QThread::currentThread() ||
            surface->window() != window || focus->window() != window || !descendant(surface, window->contentItem()) ||
            !std::isfinite(surface->width()) || !std::isfinite(surface->height()) ||
            surface->width() < 1 || surface->height() < 1 || surface->width() > 2048 || surface->height() > 2048 ||
            !surface->isVisible() || !surface->isEnabled() ||
            !focus->isVisible() || !focus->isEnabled() || !focus->hasActiveFocus() || !descendant(focus, surface)) return false;
    Target target;
    if (!nativeTarget(target) || !target.main->windowHandle() ||
            QQuickRenderControl::renderWindowFor(window) != target.main->windowHandle()) return false;
    // No timer, posted callback, clipboard, text readback or focus override.
    // Reentrant delivery may destroy a GUI object: never dereference it afterward.
    const QPointer<QObject> capturedHelper(helper);
    const QPointer<QQuickItem> capturedOwner(owner);
    QKeyEvent press(QEvent::KeyPress, key.code, Qt::KeyboardModifiers(modifiers), key.text, false, 1);
    press.ignore();
    const bool pressed = QCoreApplication::sendEvent(target.canvas, &press);
    if (!targetCurrent(target)) return false;
    // Balance the already authorized press even if a native handler changed focus
    // or cancelled/destroyed the helper. Releases cannot commit the key's text.
    QKeyEvent release(QEvent::KeyRelease, key.code, Qt::KeyboardModifiers(modifiers), key.text, false, 1);
    release.ignore();
    const bool released = QCoreApplication::sendEvent(target.canvas, &release);
    return pressed && released && capturedHelper && capturedOwner && window && surface;
}
} // namespace BrowserApplicationKey
